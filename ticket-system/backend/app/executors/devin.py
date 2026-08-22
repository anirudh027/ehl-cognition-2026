from __future__ import annotations

import asyncio
import time
from typing import cast

import httpx
from pydantic import BaseModel

from ..models import AgentRole
from ..settings import Settings
from .base import AgentResult, Executor, ExecutorError, json_schema_for, parse_output

FINISHED_STATUSES = {"finished", "blocked", "expired", "exit", "suspended"}
AGENT_MESSAGE_TYPES = {"devin_message", "devin_message_sent"}


class DevinExecutor(Executor):
    """Runs each agent as a real Devin session via the public API.

    A session is created once per agent and then *resumed* with follow-up
    messages, so the implementer keeps its full context across review rounds
    instead of re-deriving it from scratch.
    """

    name = "devin"

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if not settings.devin_api_key:
            raise ExecutorError("DEVIN_API_KEY is required for the devin executor")
        self.settings = settings
        self._client = client or httpx.AsyncClient(
            base_url=settings.devin_api_base,
            headers={"Authorization": f"Bearer {settings.devin_api_key}"},
            timeout=httpx.Timeout(60.0),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def start(
        self,
        *,
        role: AgentRole,
        prompt: str,
        schema: type[BaseModel],
        title: str,
        tags: list[str],
    ) -> AgentResult:
        body: dict[str, object] = {
            "prompt": prompt,
            "title": title,
            "tags": tags,
            "structured_output_schema": json_schema_for(schema),
        }
        response = await self._client.post("/v1/sessions", json=body)
        self._raise_for_status(response, "create session")
        created = response.json()
        session_id = str(created["session_id"])
        session_url = created.get("url")
        return await self._await_result(
            role=role,
            session_id=session_id,
            session_url=session_url,
            schema=schema,
        )

    async def follow_up(
        self,
        *,
        role: AgentRole,
        session_id: str,
        message: str,
        schema: type[BaseModel],
    ) -> AgentResult:
        before = await self._get_session(session_id)
        marker = len(cast(list[object], before.get("messages") or []))
        response = await self._client.post(
            f"/v1/sessions/{session_id}/message", json={"message": message}
        )
        self._raise_for_status(response, "send message")
        return await self._await_result(
            role=role,
            session_id=session_id,
            session_url=before.get("url"),
            schema=schema,
            message_marker=marker,
        )

    async def _await_result(
        self,
        *,
        role: AgentRole,
        session_id: str,
        session_url: object,
        schema: type[BaseModel],
        message_marker: int = 0,
    ) -> AgentResult:
        deadline = time.monotonic() + self.settings.session_timeout_seconds
        while True:
            session = await self._get_session(session_id)
            status = str(session.get("status_enum") or session.get("status") or "")
            output = self._extract_output(session, schema, message_marker)
            if output is not None:
                pull_request = session.get("pull_request")
                resolved_url = session_url or session.get("url")
                pr_url = (
                    str(pull_request["url"])
                    if isinstance(pull_request, dict) and pull_request.get("url")
                    else None
                )
                return AgentResult(
                    role=role,
                    session_id=session_id,
                    session_url=str(resolved_url) if resolved_url else None,
                    output=output,
                    pr_url=pr_url,
                    status=status or "finished",
                )
            if status in FINISHED_STATUSES:
                raise ExecutorError(
                    f"session {session_id} reached status '{status}' without valid "
                    f"{schema.__name__} output"
                )
            if time.monotonic() > deadline:
                raise ExecutorError(f"session {session_id} timed out in status '{status}'")
            await asyncio.sleep(self.settings.poll_interval_seconds)

    def _extract_output(
        self,
        session: dict[str, object],
        schema: type[BaseModel],
        message_marker: int,
    ) -> BaseModel | None:
        messages = session.get("messages")
        fresh: list[object] = (
            cast(list[object], messages)[message_marker:] if isinstance(messages, list) else []
        )
        # On a follow-up turn the session still carries the previous turn's
        # structured output, which validates against the same schema, so it is
        # only trusted once the resumed session has spoken again.
        if message_marker == 0 or self._has_agent_message(fresh):
            structured = session.get("structured_output")
            if isinstance(structured, dict) and structured:
                try:
                    return parse_output(schema, structured)
                except ExecutorError:
                    return None
        for entry in reversed(fresh):
            if not isinstance(entry, dict):
                continue
            if entry.get("type") not in AGENT_MESSAGE_TYPES:
                continue
            try:
                return parse_output(schema, str(entry.get("message", "")))
            except ExecutorError:
                continue
        return None

    @staticmethod
    def _has_agent_message(entries: list[object]) -> bool:
        return any(
            isinstance(entry, dict) and entry.get("type") in AGENT_MESSAGE_TYPES
            for entry in entries
        )

    async def _get_session(self, session_id: str) -> dict[str, object]:
        response = await self._client.get(f"/v1/sessions/{session_id}")
        self._raise_for_status(response, "get session")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ExecutorError("unexpected session payload")
        return payload

    @staticmethod
    def _raise_for_status(response: httpx.Response, action: str) -> None:
        if response.is_success:
            return
        raise ExecutorError(f"devin api {action} failed ({response.status_code}): {response.text}")
