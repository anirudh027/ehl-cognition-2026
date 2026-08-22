from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class TicketStatus(StrEnum):
    queued = "queued"
    planning = "planning"
    implementing = "implementing"
    reviewing = "reviewing"
    revising = "revising"
    retro = "retro"
    done = "done"
    needs_human = "needs_human"
    failed = "failed"


class AgentRole(StrEnum):
    planner = "planner"
    implementer = "implementer"
    critic = "critic"
    retrospective = "retrospective"


TERMINAL_STATUSES = {TicketStatus.done, TicketStatus.needs_human, TicketStatus.failed}


class TicketCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3, max_length=20_000)
    repo: str = Field(min_length=1, max_length=200, description="e.g. owner/repo")
    base_branch: str = Field(default="main", max_length=200)
    acceptance_criteria: list[str] = Field(default_factory=list)
    max_iterations: int | None = Field(default=None, ge=1, le=10)


class Subtask(BaseModel):
    id: str
    title: str
    description: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    status: str
    iterations: int = 0
    session_id: str | None = None
    session_url: str | None = None
    pr_url: str | None = None
    verdict: str | None = None


class Event(BaseModel):
    id: int
    ticket_id: str
    role: str | None
    phase: str
    message: str
    level: str
    data: dict[str, object] | None
    created_at: str


class Ticket(BaseModel):
    id: str
    title: str
    description: str
    repo: str
    base_branch: str
    acceptance_criteria: list[str]
    status: TicketStatus
    max_iterations: int
    created_at: str
    updated_at: str
    plan: dict[str, object] | None = None
    subtasks: list[Subtask] = Field(default_factory=list)
    pr_urls: list[str] = Field(default_factory=list)
    metrics: dict[str, object] = Field(default_factory=dict)
    retro: dict[str, object] | None = None


class Learning(BaseModel):
    id: int
    ticket_id: str
    kind: Literal["knowledge", "playbook", "blueprint", "metric"]
    title: str
    body: str
    hits: int
    created_at: str


# ---------------------------------------------------------------------------
# Structured-output contracts the agents must honour. These double as the
# JSON Schemas handed to the Devin API so the orchestrator never parses prose.
# ---------------------------------------------------------------------------


class PlannedSubtask(BaseModel):
    title: str
    description: str
    acceptance_criteria: list[str] = Field(default_factory=list)


class PlanOutput(BaseModel):
    summary: str
    subtasks: list[PlannedSubtask]
    risks: list[str] = Field(default_factory=list)


class ImplementationOutput(BaseModel):
    summary: str
    pr_url: str | None = None
    files_changed: list[str] = Field(default_factory=list)
    tests_run: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class CriticComment(BaseModel):
    severity: Literal["blocker", "major", "minor"]
    body: str


class CriticOutput(BaseModel):
    verdict: Literal["pass", "changes_requested"]
    reasoning: str
    comments: list[CriticComment] = Field(default_factory=list)
    unmet_criteria: list[str] = Field(default_factory=list)


class RetroLearning(BaseModel):
    kind: Literal["knowledge", "playbook", "blueprint"]
    title: str
    body: str


class RetroOutput(BaseModel):
    summary: str
    recurring_issues: list[str] = Field(default_factory=list)
    learnings: list[RetroLearning] = Field(default_factory=list)


SCHEMAS: dict[AgentRole, type[BaseModel]] = {
    AgentRole.planner: PlanOutput,
    AgentRole.implementer: ImplementationOutput,
    AgentRole.critic: CriticOutput,
    AgentRole.retrospective: RetroOutput,
}
