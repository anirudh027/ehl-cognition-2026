from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import load_settings


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    os.environ["TICKETS_DB_PATH"] = str(tmp_path / "api.db")
    os.environ["TICKETS_EXECUTOR"] = "mock"
    os.environ["TICKETS_MOCK_SPEED"] = "200"
    with TestClient(create_app(load_settings())) as test_client:
        yield test_client


def test_health_reports_executor(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["executor"] == "mock"


def test_create_ticket_and_poll_until_done(client: TestClient) -> None:
    response = client.post(
        "/api/tickets",
        json={
            "title": "Add rate limiting to the public API",
            "description": "Protect /v1/search from abuse.",
            "repo": "acme/api",
            "acceptance_criteria": ["429 after 100 requests per minute"],
        },
    )
    assert response.status_code == 201
    ticket_id = response.json()["id"]

    for _ in range(400):
        ticket = client.get(f"/api/tickets/{ticket_id}").json()
        if ticket["status"] in {"done", "needs_human", "failed"}:
            break
        time.sleep(0.05)

    assert ticket["status"] == "done"
    assert ticket["pr_urls"]
    assert ticket["retro"] is not None

    events = client.get(f"/api/tickets/{ticket_id}/events").json()
    assert {"planned", "implemented", "approved", "retro_done"} <= {e["phase"] for e in events}

    assert client.get("/api/learnings").json()


def test_unknown_ticket_is_404(client: TestClient) -> None:
    assert client.get("/api/tickets/tkt_missing").status_code == 404
    assert client.get("/api/tickets/tkt_missing/events").status_code == 404


def test_feedback_requires_known_subtask(client: TestClient) -> None:
    ticket_id = client.post(
        "/api/tickets",
        json={
            "title": "Fix flaky login test",
            "description": "It fails on CI once in ten runs.",
            "repo": "acme/web",
        },
    ).json()["id"]

    response = client.post(
        f"/api/tickets/{ticket_id}/subtasks/sub_missing/feedback",
        json={"feedback": "Please also cover the SSO path."},
    )
    assert response.status_code == 404
