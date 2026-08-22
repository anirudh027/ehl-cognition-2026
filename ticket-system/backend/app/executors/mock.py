from __future__ import annotations

import asyncio
import itertools
import re
from dataclasses import dataclass, field

from pydantic import BaseModel

from ..models import (
    AgentRole,
    CriticComment,
    CriticOutput,
    ImplementationOutput,
    PlannedSubtask,
    PlanOutput,
    RetroLearning,
    RetroOutput,
)
from ..settings import Settings
from .base import AgentResult, Executor, ExecutorError

_TITLE = re.compile(r"^Title:\s*(.+)$", re.MULTILINE)
_REPO = re.compile(r"^Repository:\s*(.+)$", re.MULTILINE)
_SUBTASK = re.compile(r"^Subtask:\s*(.+)$", re.MULTILINE)
_TICKET_TITLE = re.compile(r"^Ticket:\s*\S+\s+—\s*(.+)$", re.MULTILINE)


def _field(pattern: re.Pattern[str], prompt: str, fallback: str) -> str:
    match = pattern.search(prompt)
    return match.group(1).strip() if match else fallback


@dataclass
class _SessionState:
    role: AgentRole
    prompt: str
    turns: int = 0
    history: list[str] = field(default_factory=list)


class MockExecutor(Executor):
    """Deterministic stand-in for Devin, so the loop is demoable without a key.

    The critic deliberately requests changes on its first pass over each
    subtask and accepts the revision, which exercises the full
    implement -> review -> revise -> retro cycle.
    """

    name = "mock"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._sessions: dict[str, _SessionState] = {}
        self._ids = itertools.count(1)

    @property
    def _delay(self) -> float:
        speed = max(self.settings.mock_speed, 0.01)
        return 1.2 / speed

    async def start(
        self,
        *,
        role: AgentRole,
        prompt: str,
        schema: type[BaseModel],
        title: str,
        tags: list[str],
    ) -> AgentResult:
        session_id = f"mock-{role.value}-{next(self._ids)}"
        self._sessions[session_id] = _SessionState(role=role, prompt=prompt)
        return await self._respond(session_id, schema, prompt)

    async def follow_up(
        self,
        *,
        role: AgentRole,
        session_id: str,
        message: str,
        schema: type[BaseModel],
    ) -> AgentResult:
        state = self._sessions.get(session_id)
        if state is None:
            raise ExecutorError(f"unknown mock session {session_id}")
        state.history.append(message)
        return await self._respond(session_id, schema, message)

    async def _respond(
        self, session_id: str, schema: type[BaseModel], message: str
    ) -> AgentResult:
        state = self._sessions[session_id]
        state.turns += 1
        await asyncio.sleep(self._delay)
        output = self._build(state, message)
        if not isinstance(output, schema):
            raise ExecutorError(
                f"mock produced {type(output).__name__}, expected {schema.__name__}"
            )
        pr_url = output.pr_url if isinstance(output, ImplementationOutput) else None
        return AgentResult(
            role=state.role,
            session_id=session_id,
            session_url=f"https://app.devin.ai/sessions/{session_id}",
            output=output,
            pr_url=pr_url,
        )

    def _build(self, state: _SessionState, message: str) -> BaseModel:
        title = _field(_TITLE, state.prompt, "") or _field(
            _TICKET_TITLE, state.prompt, "the requested change"
        )
        repo = _field(_REPO, state.prompt, "owner/repo")
        subtask = _field(_SUBTASK, state.prompt, title)
        slug = re.sub(r"[^a-z0-9]+", "-", subtask.lower()).strip("-")[:40] or "change"

        if state.role is AgentRole.planner:
            return PlanOutput(
                summary=f"Deliver '{title}' in {repo} as independently reviewable slices.",
                subtasks=[
                    PlannedSubtask(
                        title=f"Implement core behaviour for {title}",
                        description=(
                            f"Add the primary logic and data model changes needed for '{title}'."
                        ),
                        acceptance_criteria=[
                            "Core behaviour implemented behind the documented interface",
                            "Unit tests cover the happy path and one failure mode",
                        ],
                    ),
                    PlannedSubtask(
                        title=f"Wire up entry points and docs for {title}",
                        description=(
                            "Expose the new behaviour through the app's entry points and "
                            "document usage in the README."
                        ),
                        acceptance_criteria=[
                            "Entry point calls the new logic",
                            "README documents the new behaviour",
                        ],
                    ),
                ],
                risks=[
                    "Requirements in the ticket may be ambiguous about error handling",
                    f"No CI history for {repo} in this run, so test coverage is unverified",
                ],
            )

        if state.role is AgentRole.implementer:
            revision = state.turns > 1
            return ImplementationOutput(
                summary=(
                    f"Addressed review feedback for '{subtask}'."
                    if revision
                    else f"Implemented '{subtask}'."
                ),
                pr_url=f"https://github.com/{repo}/pull/{1000 + abs(hash(slug)) % 900}",
                files_changed=[f"src/{slug}.py", f"tests/test_{slug}.py"],
                tests_run=["pytest -q"] + (["ruff check ."] if revision else []),
                open_questions=[] if revision else ["Should errors surface to the UI or logs?"],
            )

        if state.role is AgentRole.critic:
            first_pass = state.turns == 1
            if first_pass:
                return CriticOutput(
                    verdict="changes_requested",
                    reasoning=(
                        f"'{subtask}' is functionally close but not defensible yet: error "
                        "paths are untested and the change is undocumented."
                    ),
                    comments=[
                        CriticComment(
                            severity="major",
                            body=(
                                "Add a test for the failure mode named in the "
                                "acceptance criteria."
                            ),
                        ),
                        CriticComment(
                            severity="minor",
                            body=(
                                "Document the new behaviour where the rest of the "
                                "flow is documented."
                            ),
                        ),
                    ],
                    unmet_criteria=["Unit tests cover the happy path and one failure mode"],
                )
            return CriticOutput(
                verdict="pass",
                reasoning=f"Revision for '{subtask}' addresses every blocking comment.",
                comments=[],
                unmet_criteria=[],
            )

        escalated = "escalated" in state.prompt
        return RetroOutput(
            summary=(
                f"'{title}' stalled: at least one subtask escalated to a human because "
                "the reviewer's comments were not fully addressed."
                if escalated
                else f"'{title}' converged after one revision round per subtask."
            ),
            recurring_issues=[
                "Implementers ship happy-path tests only until the critic asks for failure cases",
                "Documentation updates are skipped unless named in the acceptance criteria",
            ],
            learnings=[
                RetroLearning(
                    kind="knowledge",
                    title=f"Testing expectations for {repo}",
                    body=(
                        "Every change must land with a failure-mode test alongside the "
                        "happy-path test; the reviewer blocks otherwise."
                    ),
                ),
                RetroLearning(
                    kind="playbook",
                    title="Feature ticket checklist",
                    body=(
                        "1. Restate acceptance criteria as tests. 2. Implement. 3. Run tests "
                        "and lint. 4. Update docs. 5. Open PR referencing the ticket."
                    ),
                ),
            ],
        )
