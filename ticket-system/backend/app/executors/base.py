from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from ..models import AgentRole

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


class ExecutorError(RuntimeError):
    """Raised when an agent run cannot produce a usable structured result."""


@dataclass
class AgentResult:
    """Outcome of a single agent turn, always carrying a validated payload."""

    role: AgentRole
    session_id: str
    session_url: str | None
    output: BaseModel
    pr_url: str | None = None
    status: str = "finished"
    extra: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return self.output.model_dump()


class Executor(ABC):
    """Runs one agent turn to completion and returns structured output.

    Implementations own their own concurrency: `start` and `follow_up` block
    (asynchronously) until the agent has produced schema-valid output.
    """

    name: str

    @abstractmethod
    async def start(
        self,
        *,
        role: AgentRole,
        prompt: str,
        schema: type[BaseModel],
        title: str,
        tags: list[str],
    ) -> AgentResult: ...

    @abstractmethod
    async def follow_up(
        self,
        *,
        role: AgentRole,
        session_id: str,
        message: str,
        schema: type[BaseModel],
    ) -> AgentResult: ...

    async def close(self) -> None:
        return None


def parse_output(schema: type[BaseModel], payload: object) -> BaseModel:
    """Validate an agent payload against its schema.

    Accepts a dict (structured output) or a string containing a JSON object,
    which is what an agent falls back to when structured output is unset.
    """
    candidate: object = payload
    if isinstance(payload, str):
        match = _JSON_BLOCK.search(payload)
        text = match.group(1) if match else payload[payload.find("{") : payload.rfind("}") + 1]
        try:
            candidate = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ExecutorError(f"agent output was not JSON: {exc}") from exc
    if not isinstance(candidate, dict):
        raise ExecutorError(f"agent output was not an object: {type(candidate).__name__}")
    try:
        return schema.model_validate(candidate)
    except ValidationError as exc:
        raise ExecutorError(f"agent output failed {schema.__name__} validation: {exc}") from exc


def json_schema_for(schema: type[BaseModel]) -> dict[str, object]:
    return schema.model_json_schema()
