import asyncio
import json
import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from backend.app.devin import DevinClient, DevinConfig
from backend.app.managed_runner import ManagedWorkflowRunner
from backend.app.models import FollowUpCreate, RunCreate
from backend.app.runner import WorkflowRunner
from backend.app.store import Store

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCAL_DIR = PROJECT_ROOT / "backend" / ".local"


def create_app(
    database_path: Path | None = None,
    runs_dir: Path | None = None,
    step_delay: float | None = None,
) -> FastAPI:
    local_dir = database_path.parent if database_path is not None else DEFAULT_LOCAL_DIR
    database = database_path or local_dir / "dashboard.sqlite3"
    artifacts = runs_dir or local_dir / "runs"
    delay = (
        step_delay
        if step_delay is not None
        else float(os.environ.get("BIO_DASHBOARD_STEP_DELAY", "0.45"))
    )
    store = Store(database)
    local_runner = WorkflowRunner(store, artifacts, delay)
    devin_config = DevinConfig.from_environment()
    managed_runner = (
        ManagedWorkflowRunner(store, DevinClient(devin_config), artifacts)
        if devin_config is not None
        else None
    )
    tasks: set[asyncio.Task[None]] = set()
    app = FastAPI(
        title="Bioengineering Orchestration Dashboard",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health() -> dict[str, object]:
        tools = {
            command: shutil.which(command) is not None
            for command in ("mafft", "mkdssp", "mmseqs", "foldseek")
        }
        return {
            "status": "ok",
            "default_mode": "local",
            "devin_mode_available": managed_runner is not None,
            "tools": tools,
        }

    @app.get("/api/runs")
    async def list_runs(limit: int = Query(default=20, ge=1, le=100)) -> list[dict[str, object]]:
        return store.list_runs(limit)

    @app.post("/api/runs", status_code=201)
    async def create_run(payload: RunCreate) -> dict[str, object]:
        if payload.mode == "devin" and managed_runner is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Managed Devin mode requires DEVIN_API_KEY with a supported cog_ "
                    "service-user key or personal access token, plus DEVIN_ORG_ID."
                ),
            )
        run, agents = store.create_run(payload.objective.strip(), payload.mode)
        store.add_event(
            str(run["id"]),
            "run_started",
            "Run accepted",
            (
                "Managed Devin sessions are being prepared."
                if payload.mode == "devin"
                else "The local coordinator is preparing the scientific workflow."
            ),
            tone="accent",
        )
        selected_runner = managed_runner if payload.mode == "devin" else local_runner
        if selected_runner is None:
            raise HTTPException(status_code=503, detail="Managed Devin mode is unavailable.")
        task = asyncio.create_task(selected_runner.run(str(run["id"]), agents))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        return store.get_run(str(run["id"]))

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str) -> dict[str, object]:
        try:
            return store.get_run(run_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Run not found") from error

    @app.post("/api/runs/{run_id}/messages")
    async def follow_up(run_id: str, payload: FollowUpCreate) -> dict[str, object]:
        try:
            run = store.get_run(run_id)
            selected_runner = managed_runner if run["mode"] == "devin" else local_runner
            if selected_runner is None:
                raise ValueError("Managed Devin mode is not configured on this server.")
            return await selected_runner.apply_follow_up(run_id, payload.message.strip())
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Run not found") from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @app.post("/api/runs/{run_id}/traces/refresh")
    async def refresh_traces(run_id: str) -> dict[str, object]:
        try:
            run = store.get_run(run_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Run not found") from error
        if run["mode"] != "devin" or managed_runner is None:
            raise HTTPException(
                status_code=409,
                detail="Session traces are only available for managed Devin runs.",
            )
        try:
            return await managed_runner.refresh_traces(run_id)
        except RuntimeError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @app.get("/api/runs/{run_id}/events")
    async def stream_events(
        run_id: str,
        request: Request,
        after: int = Query(default=0, ge=0),
    ) -> StreamingResponse:
        try:
            store.get_run(run_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Run not found") from error

        async def event_stream() -> AsyncIterator[str]:
            cursor = after
            while not await request.is_disconnected():
                events = store.events_after(run_id, cursor)
                for event in events:
                    cursor = int(event["id"])
                    yield f"id: {cursor}\nevent: run_event\ndata: {json.dumps(event)}\n\n"
                yield ": heartbeat\n\n"
                await asyncio.sleep(0.75)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/artifacts/{artifact_id}")
    async def download_artifact(artifact_id: str) -> FileResponse:
        try:
            path, name, content_type = store.get_artifact_path(artifact_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Artifact not found") from error
        resolved = path.resolve()
        if not resolved.is_relative_to(artifacts.resolve()) or not resolved.is_file():
            raise HTTPException(status_code=404, detail="Artifact file not found")
        return FileResponse(resolved, media_type=content_type, filename=name)

    return app


app = create_app()
