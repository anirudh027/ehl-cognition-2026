from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .bus import EventBus
from .db import Database
from .executors import build_executor
from .models import Event, Learning, Ticket, TicketCreate
from .orchestrator import Orchestrator
from .settings import Settings, load_settings

logger = logging.getLogger(__name__)

SSE_KEEPALIVE_SECONDS = 15.0


class FeedbackRequest(BaseModel):
    feedback: str = Field(min_length=3, max_length=10_000)


class HealthResponse(BaseModel):
    status: str
    executor: str
    devin_configured: bool
    max_iterations: int


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    db = Database(settings.db_path)
    bus = EventBus()
    orchestrator = Orchestrator(
        db=db,
        executor=build_executor(settings),
        bus=bus,
        max_iterations=settings.max_iterations,
        max_parallel=settings.max_parallel_subtasks,
    )
    app.state.db = db
    app.state.bus = bus
    app.state.orchestrator = orchestrator
    try:
        yield
    finally:
        await orchestrator.shutdown()
        db.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Ticket System", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings or load_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    _register_routes(app)
    return app


def get_db(request: Request) -> Database:
    db = request.app.state.db
    assert isinstance(db, Database)
    return db


def get_bus(request: Request) -> EventBus:
    bus = request.app.state.bus
    assert isinstance(bus, EventBus)
    return bus


def get_orchestrator(request: Request) -> Orchestrator:
    orchestrator = request.app.state.orchestrator
    assert isinstance(orchestrator, Orchestrator)
    return orchestrator


def _register_routes(app: FastAPI) -> None:
    @app.get("/api/health", response_model=HealthResponse)
    def health(request: Request) -> HealthResponse:
        settings: Settings = request.app.state.settings
        return HealthResponse(
            status="ok",
            executor=settings.executor,
            devin_configured=settings.devin_available,
            max_iterations=settings.max_iterations,
        )

    @app.post("/api/tickets", response_model=Ticket, status_code=201)
    async def create_ticket(
        payload: TicketCreate,
        request: Request,
        db: Database = Depends(get_db),
        orchestrator: Orchestrator = Depends(get_orchestrator),
    ) -> Ticket:
        settings: Settings = request.app.state.settings
        ticket_id = db.create_ticket(payload, settings.max_iterations)
        orchestrator.submit(ticket_id)
        ticket = db.get_ticket(ticket_id)
        if ticket is None:  # pragma: no cover - just created
            raise HTTPException(status_code=500, detail="ticket vanished after creation")
        return ticket

    @app.get("/api/tickets", response_model=list[Ticket])
    def list_tickets(db: Database = Depends(get_db)) -> list[Ticket]:
        return db.list_tickets()

    @app.get("/api/tickets/{ticket_id}", response_model=Ticket)
    def get_ticket(ticket_id: str, db: Database = Depends(get_db)) -> Ticket:
        ticket = db.get_ticket(ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="ticket not found")
        return ticket

    @app.get("/api/tickets/{ticket_id}/events", response_model=list[Event])
    def list_events(
        ticket_id: str, after: int = 0, db: Database = Depends(get_db)
    ) -> list[Event]:
        if db.get_ticket(ticket_id) is None:
            raise HTTPException(status_code=404, detail="ticket not found")
        return db.list_events(ticket_id, after_id=after)

    @app.post("/api/tickets/{ticket_id}/subtasks/{subtask_id}/feedback", status_code=202)
    async def send_feedback(
        ticket_id: str,
        subtask_id: str,
        payload: FeedbackRequest,
        db: Database = Depends(get_db),
        orchestrator: Orchestrator = Depends(get_orchestrator),
    ) -> dict[str, str]:
        ticket = db.get_ticket(ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="ticket not found")
        subtask = next((item for item in ticket.subtasks if item.id == subtask_id), None)
        if subtask is None:
            raise HTTPException(status_code=404, detail="subtask not found")
        if subtask.session_id is None:
            raise HTTPException(
                status_code=409, detail="subtask has no implementer session to resume yet"
            )
        asyncio.create_task(
            orchestrator.apply_human_feedback(ticket_id, subtask_id, payload.feedback)
        )
        return {"status": "accepted"}

    @app.get("/api/learnings", response_model=list[Learning])
    def list_learnings(db: Database = Depends(get_db)) -> list[Learning]:
        return db.list_learnings()

    @app.get("/api/tickets/{ticket_id}/stream")
    async def stream(
        ticket_id: str,
        request: Request,
        after: int = 0,
        db: Database = Depends(get_db),
        bus: EventBus = Depends(get_bus),
    ) -> StreamingResponse:
        if db.get_ticket(ticket_id) is None:
            raise HTTPException(status_code=404, detail="ticket not found")
        queue = await bus.subscribe(ticket_id)

        async def event_source() -> AsyncIterator[str]:
            try:
                for event in db.list_events(ticket_id, after_id=after):
                    yield _sse(event)
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(
                            queue.get(), timeout=SSE_KEEPALIVE_SECONDS
                        )
                    except TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    yield _sse(event)
            finally:
                await bus.unsubscribe(ticket_id, queue)

        return StreamingResponse(
            event_source(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )


def _sse(event: Event) -> str:
    return f"id: {event.id}\nevent: ticket\ndata: {json.dumps(event.model_dump())}\n\n"


app = create_app()
