from __future__ import annotations

import json

from pydantic import BaseModel

from .models import (
    CriticOutput,
    ImplementationOutput,
    Learning,
    PlanOutput,
    RetroOutput,
    Subtask,
    Ticket,
)

MAX_LEARNINGS_IN_PROMPT = 8


def _schema_contract(schema: type[BaseModel]) -> str:
    return (
        "When you are done, send exactly one final message containing ONLY a JSON object "
        f"matching this schema (no prose, no markdown fence needed):\n"
        f"{json.dumps(schema.model_json_schema(), indent=2)}"
    )


def _criteria_block(criteria: list[str]) -> str:
    if not criteria:
        return "- (none stated; infer them from the description and state your assumptions)"
    return "\n".join(f"- {item}" for item in criteria)


def learnings_block(learnings: list[Learning]) -> str:
    """Render accumulated learnings so each new ticket starts smarter."""
    relevant = [item for item in learnings if item.kind in {"knowledge", "playbook"}]
    if not relevant:
        return "No prior learnings recorded yet."
    lines = [
        f"- [{item.kind}] {item.title} (seen {item.hits}x): {item.body}"
        for item in relevant[:MAX_LEARNINGS_IN_PROMPT]
    ]
    return "\n".join(lines)


def planner_prompt(ticket: Ticket, learnings: list[Learning]) -> str:
    return f"""You are the PLANNER agent of an automated delivery pipeline. Do NOT write code and do NOT open a pull request.

Ticket: {ticket.id}
Title: {ticket.title}
Repository: {ticket.repo}
Base branch: {ticket.base_branch}

Description:
{ticket.description}

Acceptance criteria:
{_criteria_block(ticket.acceptance_criteria)}

Lessons learned from previous tickets in this pipeline — respect them:
{learnings_block(learnings)}

Your job: read enough of {ticket.repo} to split this ticket into 1-4 subtasks that can each be
implemented and reviewed as a single pull request. Each subtask must be independently verifiable
and have concrete acceptance criteria. Order them so that later subtasks can build on earlier ones.

{_schema_contract(PlanOutput)}"""


def implementer_prompt(ticket: Ticket, subtask: Subtask, learnings: list[Learning]) -> str:
    return f"""You are an IMPLEMENTER agent of an automated delivery pipeline. Implement exactly one subtask and open a pull request for it.

Ticket: {ticket.id} — {ticket.title}
Repository: {ticket.repo}
Base branch: {ticket.base_branch}

Subtask: {subtask.title}

Subtask description:
{subtask.description}

Subtask acceptance criteria:
{_criteria_block(subtask.acceptance_criteria)}

Original ticket description for context:
{ticket.description}

Lessons learned from previous tickets in this pipeline — respect them:
{learnings_block(learnings)}

Rules:
- Stay inside the scope of this subtask; another agent owns the others.
- Run the repository's tests and linters before opening the pull request.
- A reviewer agent will critique your PR against the acceptance criteria above, so make the
  change defensible: tests for the failure modes, docs where the repo documents behaviour.

{_schema_contract(ImplementationOutput)}"""


def revision_prompt(comments: list[str], unmet_criteria: list[str]) -> str:
    comment_block = "\n".join(f"- {comment}" for comment in comments) or "- (see reasoning above)"
    unmet_block = "\n".join(f"- {item}" for item in unmet_criteria) or "- (none listed)"
    return f"""The reviewer agent requested changes on your pull request.

Review comments:
{comment_block}

Acceptance criteria still unmet:
{unmet_block}

Address every comment in the same pull request (push follow-up commits to your existing branch),
re-run tests and linters, then report again using the same JSON schema as before."""


def critic_prompt(ticket: Ticket, subtask: Subtask, implementation: dict[str, object]) -> str:
    return f"""You are the REVIEWER agent of an automated delivery pipeline. You did NOT write this code. Be strict and specific.

Ticket: {ticket.id} — {ticket.title}
Repository: {ticket.repo}
Subtask: {subtask.title}

Subtask acceptance criteria:
{_criteria_block(subtask.acceptance_criteria)}

Ticket-level acceptance criteria:
{_criteria_block(ticket.acceptance_criteria)}

What the implementer reported:
{json.dumps(implementation, indent=2)}

Your job: review the pull request against the acceptance criteria. Check out the branch, read the
diff, and run the tests yourself — do not trust the implementer's report. Return
verdict "pass" only if every acceptance criterion is met and CI-relevant checks pass. Otherwise
return "changes_requested" with actionable comments; each comment must name a file or behaviour.
Do NOT fix the code yourself.

{_schema_contract(CriticOutput)}"""


def retro_prompt(ticket: Ticket, transcript: list[dict[str, object]]) -> str:
    return f"""You are the RETROSPECTIVE agent of an automated delivery pipeline. Do NOT write code.

Ticket: {ticket.id} — {ticket.title}
Repository: {ticket.repo}

Machine-readable record of what happened (plan, implementations, reviews, revisions):
{json.dumps(transcript, indent=2)}

Your job: identify what caused review rounds, then turn that into durable guidance that will make
the NEXT ticket converge in fewer rounds. Only propose learnings that generalise beyond this
ticket. Use kind "knowledge" for repo facts and conventions, "playbook" for a repeatable
procedure, and "blueprint" for environment/setup fixes.

{_schema_contract(RetroOutput)}"""
