import asyncio
import json
from pathlib import Path

import httpx

from backend.app.devin import DevinClient, DevinConfig
from backend.app.managed_runner import ManagedWorkflowRunner
from backend.app.store import Store


def test_devin_client_creates_v3_session() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = request.read().decode()
        return httpx.Response(
            200,
            json={
                "session_id": "abc123",
                "url": "https://app.devin.ai/sessions/abc123",
                "status": "new",
                "acus_consumed": 0,
            },
        )

    config = DevinConfig(
        api_key="cog_test",
        org_id="org-test",
        repo="owner/repo",
        repo_ref="main",
        devin_mode="normal",
        max_acu_limit=2,
        poll_interval=0,
        run_timeout=30,
    )
    client = DevinClient(config, transport=httpx.MockTransport(handler))
    result = asyncio.run(
        client.create_session(
            prompt="Analyze the target",
            title="Sequence analysis",
            structured_output_schema={"type": "object"},
        )
    )

    assert result["session_id"] == "abc123"
    assert captured["path"] == "/v3/organizations/org-test/sessions"
    assert captured["authorization"] == "Bearer cog_test"
    assert '"max_acu_limit":2' in str(captured["body"])


def test_devin_client_uses_prefixed_session_routes() -> None:
    requests: list[tuple[str, str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path, request.read().decode()))
        return httpx.Response(
            200,
            json={
                "session_id": "abc123",
                "status": "running",
                "status_detail": "working",
            },
        )

    config = DevinConfig(
        api_key="personal-token",
        org_id="org-test",
        repo="owner/repo",
        repo_ref="main",
        devin_mode="normal",
        max_acu_limit=2,
        poll_interval=0,
        run_timeout=30,
    )
    client = DevinClient(config, transport=httpx.MockTransport(handler))

    asyncio.run(client.get_session("abc123"))
    asyncio.run(client.send_message("devin-abc123", "Use a 10 angstrom threshold."))

    assert requests[0] == (
        "GET",
        "/v3/organizations/org-test/sessions/devin-abc123",
        "",
    )
    assert requests[1][0:2] == (
        "POST",
        "/v3/organizations/org-test/sessions/devin-abc123/messages",
    )
    assert "10 angstrom" in requests[1][2]


def test_managed_runner_persists_mocked_sessions(tmp_path: Path) -> None:
    specialist_output = {
        "summary": "Calculated specialist evidence",
        "candidate_context": [
            {
                "mutation": "S121E",
                "position": 121,
                "value": 0.7,
                "rationale": "Calculated from the committed fixture.",
            }
        ],
    }
    ranking_output = {
        "summary": "Predicted priorities; no experimental validation.",
        "candidates": [
            {
                "mutation": mutation,
                "position": position,
                "score": 0.9 - index * 0.1,
                "distance": 12.0 + index,
                "conservation": 0.7,
                "evidence": ["KNOWN", "CALCULATED", "PREDICTED"],
                "rationale": "Evidence-weighted demonstration priority.",
                "excluded": False,
            }
            for index, (mutation, position) in enumerate(
                [
                    ("S121E", 121),
                    ("D186H", 186),
                    ("R224Q", 224),
                    ("N233K", 233),
                    ("R280A", 280),
                ]
            )
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            body = json.loads(request.read())
            title = body["title"]
            session_id = {
                "Catalyst Sequence Analysis": "sequence",
                "Catalyst Structure Analysis": "structure",
                "Catalyst Evidence Coordinator": "coordinator",
            }[title]
            return httpx.Response(
                200,
                json={
                    "session_id": session_id,
                    "url": f"https://app.devin.ai/sessions/{session_id}",
                    "status": "new",
                    "acus_consumed": 0,
                },
            )
        session_id = request.url.path.rsplit("/", maxsplit=1)[-1].removeprefix("devin-")
        return httpx.Response(
            200,
            json={
                "session_id": session_id,
                "status": "exit",
                "status_detail": "finished",
                "acus_consumed": 0.25,
                "structured_output": (
                    ranking_output if session_id == "coordinator" else specialist_output
                ),
            },
        )

    store = Store(tmp_path / "dashboard.sqlite3")
    run, agents = store.create_run(
        "Develop a PETase candidate that remains useful around 60 C.",
        "devin",
    )
    config = DevinConfig(
        api_key="cog_test",
        org_id="org-test",
        repo="owner/repo",
        repo_ref="feature",
        devin_mode="normal",
        max_acu_limit=2,
        poll_interval=0,
        run_timeout=30,
    )
    runner = ManagedWorkflowRunner(
        store,
        DevinClient(config, transport=httpx.MockTransport(handler)),
        tmp_path / "runs",
    )

    asyncio.run(runner.run(str(run["id"]), agents))

    completed = store.get_run(str(run["id"]))
    assert completed["status"] == "completed"
    assert len(completed["candidates"]) == 5
    assert len(completed["artifacts"]) == 3
    assert all(agent["external_id"] for agent in completed["agents"])
    assert sum(float(agent["acus_consumed"]) for agent in completed["agents"]) == 0.75
