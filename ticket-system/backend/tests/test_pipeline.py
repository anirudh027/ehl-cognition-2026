from __future__ import annotations

from pathlib import Path

import pytest

from app.bus import EventBus
from app.db import Database
from app.executors import MockExecutor
from app.executors.base import parse_output
from app.models import CriticOutput, TicketCreate, TicketStatus
from app.orchestrator import Orchestrator
from app.settings import load_settings


def _settings(tmp_path: Path):
    import os

    os.environ["TICKETS_DB_PATH"] = str(tmp_path / "test.db")
    os.environ["TICKETS_EXECUTOR"] = "mock"
    os.environ["TICKETS_MOCK_SPEED"] = "200"
    return load_settings()


@pytest.fixture
def pipeline(tmp_path: Path):
    settings = _settings(tmp_path)
    db = Database(settings.db_path)
    orchestrator = Orchestrator(
        db=db,
        executor=MockExecutor(settings),
        bus=EventBus(),
        max_iterations=settings.max_iterations,
        max_parallel=settings.max_parallel_subtasks,
    )
    yield db, orchestrator
    db.close()


def _ticket(db: Database, max_iterations: int = 3) -> str:
    return db.create_ticket(
        TicketCreate(
            title="Add CSV export to the reports page",
            description="Users need to download report rows as CSV.",
            repo="acme/reports",
            acceptance_criteria=["A download button exports the current filter set"],
            max_iterations=max_iterations,
        ),
        max_iterations=max_iterations,
    )


async def test_ticket_runs_to_completion(pipeline) -> None:
    db, orchestrator = pipeline
    ticket_id = _ticket(db)

    orchestrator.submit(ticket_id)
    await orchestrator.wait(ticket_id)

    ticket = db.get_ticket(ticket_id)
    assert ticket is not None
    assert ticket.status is TicketStatus.done
    assert ticket.plan is not None
    assert ticket.subtasks and all(s.status == "approved" for s in ticket.subtasks)
    assert all(s.pr_url for s in ticket.subtasks)


async def test_review_loop_requires_a_revision(pipeline) -> None:
    db, orchestrator = pipeline
    ticket_id = _ticket(db)

    orchestrator.submit(ticket_id)
    await orchestrator.wait(ticket_id)

    phases = [event.phase for event in db.list_events(ticket_id)]
    assert "changes_requested" in phases
    assert "revised" in phases
    assert phases.index("changes_requested") < phases.index("approved")

    ticket = db.get_ticket(ticket_id)
    assert ticket is not None
    assert ticket.metrics["review_rounds"] >= len(ticket.subtasks) * 2


async def test_retrospective_feeds_later_tickets(pipeline) -> None:
    db, orchestrator = pipeline
    first = _ticket(db)
    orchestrator.submit(first)
    await orchestrator.wait(first)

    learnings = db.list_learnings()
    assert learnings, "retrospective should persist learnings"

    second = _ticket(db)
    orchestrator.submit(second)
    await orchestrator.wait(second)

    ticket = db.get_ticket(second)
    assert ticket is not None
    assert ticket.plan is not None
    assert ticket.plan["learnings_applied"] == len(learnings)

    # Repeated learnings are deduplicated and their hit count grows instead.
    repeated = db.list_learnings()
    assert len(repeated) == len(learnings)
    assert max(item.hits for item in repeated) >= 2


async def test_human_feedback_resumes_implementer_session(pipeline) -> None:
    db, orchestrator = pipeline
    ticket_id = _ticket(db)
    orchestrator.submit(ticket_id)
    await orchestrator.wait(ticket_id)

    ticket = db.get_ticket(ticket_id)
    assert ticket is not None
    subtask = ticket.subtasks[0]

    await orchestrator.apply_human_feedback(ticket_id, subtask.id, "Rename the export button.")

    phases = [event.phase for event in db.list_events(ticket_id)]
    assert "human_feedback" in phases


async def test_human_feedback_resolves_an_escalated_subtask(pipeline) -> None:
    db, orchestrator = pipeline
    # One review round only, so the reviewer's first rejection escalates immediately.
    ticket_id = _ticket(db, max_iterations=1)
    orchestrator.submit(ticket_id)
    await orchestrator.wait(ticket_id)

    ticket = db.get_ticket(ticket_id)
    assert ticket is not None
    assert ticket.status is TicketStatus.needs_human
    blocked = [item for item in ticket.subtasks if item.status == "needs_human"]
    assert blocked, "expected at least one escalated subtask"

    for subtask in blocked:
        await orchestrator.apply_human_feedback(
            ticket_id, subtask.id, "Add the failure-mode test the reviewer asked for."
        )

    resolved = db.get_ticket(ticket_id)
    assert resolved is not None
    # The re-review resumes the existing critic session instead of starting a new
    # one, so the feedback can actually converge.
    assert [item.status for item in resolved.subtasks] == ["approved"] * len(resolved.subtasks)
    assert resolved.status is TicketStatus.done
    assert resolved.metrics["subtasks_blocked"] == 0
    assert resolved.metrics["review_rounds"] == sum(item.iterations for item in resolved.subtasks)


def test_parse_output_accepts_fenced_json() -> None:
    payload = """Here you go:
```json
{"verdict": "pass", "reasoning": "looks good", "comments": [], "unmet_criteria": []}
```"""
    parsed = parse_output(CriticOutput, payload)
    assert isinstance(parsed, CriticOutput)
    assert parsed.verdict == "pass"
