import time
from pathlib import Path

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from backend.app.main import create_app


def wait_for_completion(client: TestClient, run_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        response.raise_for_status()
        run = response.json()
        if run["status"] in {"completed", "failed"}:
            return run
        time.sleep(0.05)
    raise AssertionError("Run did not settle")


def test_local_run_and_follow_up(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("DEVIN_API_KEY", raising=False)
    monkeypatch.delenv("DEVIN_ORG_ID", raising=False)
    app = create_app(
        database_path=tmp_path / "dashboard.sqlite3",
        runs_dir=tmp_path / "runs",
        step_delay=0,
    )
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["tools"]["mafft"] is True
        response = client.post(
            "/api/runs",
            json={
                "objective": (
                    "Develop a PET-degrading enzyme that remains useful around 60 °C "
                    "while preserving catalytic function."
                )
            },
        )
        assert response.status_code == 201
        run_id = response.json()["id"]
        run = wait_for_completion(client, run_id)
        assert run["status"] == "completed"
        assert len(run["agents"]) == 3
        assert len(run["artifacts"]) == 5
        assert len(run["candidates"]) == 5
        event_types = {event["type"] for event in run["events"]}
        assert {"error_detected", "retry_started", "retry_succeeded"} <= event_types

        constrained = client.post(
            f"/api/runs/{run_id}/messages",
            json={"message": "Exclude mutations within 10 Å of the catalytic site."},
        )
        assert constrained.status_code == 200
        updated = constrained.json()
        assert updated["result_version"] == 2
        assert any(candidate["excluded"] for candidate in updated["candidates"])
        assert any(not candidate["excluded"] for candidate in updated["candidates"])

        artifact = updated["artifacts"][0]
        download = client.get(f"/api/artifacts/{artifact['id']}")
        assert download.status_code == 200
        assert download.content

        assert all(agent["traces"] == [] for agent in updated["agents"])
        traces = client.post(f"/api/runs/{run_id}/traces/refresh")
        assert traces.status_code == 409
        missing = client.post("/api/runs/does-not-exist/traces/refresh")
        assert missing.status_code == 404


def test_managed_mode_requires_supported_credentials(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEVIN_API_KEY", "apk_legacy")
    monkeypatch.setenv("DEVIN_ORG_ID", "org-test")
    app = create_app(
        database_path=tmp_path / "dashboard.sqlite3",
        runs_dir=tmp_path / "runs",
        step_delay=0,
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/runs",
            json={
                "objective": "Develop a stable PETase candidate with catalytic function.",
                "mode": "devin",
            },
        )
    assert response.status_code == 503
    assert "cog_" in response.json()["detail"]
