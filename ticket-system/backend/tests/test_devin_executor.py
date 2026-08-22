from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.executors.devin import DevinExecutor
from app.models import AgentRole, CriticOutput
from app.settings import Settings

STALE = {
    "verdict": "changes_requested",
    "reasoning": "stale critique from the previous round",
    "comments": [{"severity": "blocker", "body": "fix the first thing"}],
    "unmet_criteria": [],
}
FRESH = {
    "verdict": "pass",
    "reasoning": "fresh critique after the follow-up",
    "comments": [],
    "unmet_criteria": [],
}


def _settings() -> Settings:
    return Settings(
        executor="devin",
        devin_api_base="https://api.devin.test",
        devin_api_key="apk_test",
        db_path=Path("/tmp/unused.db"),
        max_iterations=1,
        max_parallel_subtasks=1,
        poll_interval_seconds=0,
        session_timeout_seconds=5,
        mock_speed=1,
        allowed_origins=("http://localhost:5173",),
    )


def _executor(handler: object) -> DevinExecutor:
    client = httpx.AsyncClient(
        base_url="https://api.devin.test",
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
    )
    return DevinExecutor(_settings(), client=client)


@pytest.mark.asyncio
async def test_follow_up_waits_for_the_new_turn() -> None:
    """A resumed session must not hand back the previous turn's output."""
    polls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal polls
        if request.method == "POST":
            return httpx.Response(200, json={"session_id": "devin-1"})
        polls += 1
        messages: list[dict[str, str]] = [{"type": "devin_message", "message": "first round done"}]
        structured = STALE
        # The stale structured output is still attached to the session until the
        # resumed run produces a new agent message.
        if polls > 2:
            messages = [
                *messages,
                {"type": "user_message", "message": "please re-review"},
                {"type": "devin_message", "message": "second round done"},
            ]
            structured = FRESH
        return httpx.Response(
            200,
            json={
                "status": "working",
                "url": "https://app.devin.ai/sessions/1",
                "messages": messages,
                "structured_output": structured,
            },
        )

    executor = _executor(handler)
    result = await executor.follow_up(
        role=AgentRole.critic,
        session_id="devin-1",
        message="re-review please",
        schema=CriticOutput,
    )
    await executor.close()

    assert isinstance(result.output, CriticOutput)
    assert result.output.verdict == "pass"
    assert result.output.reasoning == FRESH["reasoning"]


@pytest.mark.asyncio
async def test_start_accepts_structured_output_immediately() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"session_id": "devin-2"})
        return httpx.Response(
            200,
            json={
                "status": "finished",
                "messages": [],
                "structured_output": FRESH,
                "pull_request": {"url": "https://github.com/o/r/pull/7"},
            },
        )

    executor = _executor(handler)
    result = await executor.start(
        role=AgentRole.critic,
        prompt="review",
        schema=CriticOutput,
        title="critic",
        tags=["t"],
    )
    await executor.close()

    assert isinstance(result.output, CriticOutput)
    assert result.output.verdict == "pass"
    assert result.pr_url == "https://github.com/o/r/pull/7"
