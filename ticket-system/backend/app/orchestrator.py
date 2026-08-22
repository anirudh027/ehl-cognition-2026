from __future__ import annotations

import asyncio
import logging

from . import prompts
from .bus import EventBus
from .db import Database
from .executors import AgentResult, Executor, ExecutorError
from .models import (
    AgentRole,
    CriticOutput,
    ImplementationOutput,
    PlanOutput,
    RetroOutput,
    Subtask,
    Ticket,
    TicketStatus,
)

logger = logging.getLogger(__name__)


class Orchestrator:
    """Drives a ticket through plan -> implement -> review -> revise -> retro.

    The review loop is the self-improving part: a critic agent (always a
    different session than the implementer) either passes the work or sends
    concrete comments back into the implementer's *existing* session. What the
    critic kept complaining about is distilled by a retrospective agent into
    learnings that are injected into every later ticket's prompts.
    """

    def __init__(
        self,
        db: Database,
        executor: Executor,
        bus: EventBus,
        max_iterations: int,
        max_parallel: int = 2,
    ) -> None:
        self.db = db
        self.executor = executor
        self.bus = bus
        self.default_max_iterations = max_iterations
        self.max_parallel = max(1, max_parallel)
        self._tasks: dict[str, asyncio.Task[None]] = {}

    # -- public API -------------------------------------------------------
    def submit(self, ticket_id: str) -> None:
        if ticket_id in self._tasks and not self._tasks[ticket_id].done():
            return
        task = asyncio.create_task(self._guarded_run(ticket_id), name=f"ticket-{ticket_id}")
        self._tasks[ticket_id] = task

    async def wait(self, ticket_id: str) -> None:
        task = self._tasks.get(ticket_id)
        if task is not None:
            await task

    async def shutdown(self) -> None:
        for task in tuple(self._tasks.values()):
            task.cancel()
        for task in tuple(self._tasks.values()):
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - best-effort drain
                pass
        await self.executor.close()

    # -- pipeline ---------------------------------------------------------
    async def _guarded_run(self, ticket_id: str) -> None:
        try:
            await self._run(ticket_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI as a failure event
            logger.exception("ticket %s failed", ticket_id)
            self._emit(ticket_id, "error", f"Pipeline failed: {exc}", level="error")
            self._set_status(ticket_id, TicketStatus.failed)

    async def _run(self, ticket_id: str) -> None:
        ticket = self._require_ticket(ticket_id)
        self._emit(
            ticket_id,
            "queued",
            f"Ticket accepted for {ticket.repo} (executor: {self.executor.name})",
        )

        plan = await self._plan(ticket)
        ticket = self._require_ticket(ticket_id)

        self._set_status(ticket_id, TicketStatus.implementing)
        semaphore = asyncio.Semaphore(max(1, min(len(ticket.subtasks) or 1, self.max_parallel)))
        results = await asyncio.gather(
            *(self._deliver_subtask(ticket, subtask, semaphore) for subtask in ticket.subtasks),
            return_exceptions=True,
        )

        passed = 0
        blocked = 0
        for subtask, result in zip(ticket.subtasks, results, strict=True):
            if isinstance(result, BaseException):
                blocked += 1
                self.db.update_subtask(subtask.id, status="failed", verdict="error")
                self._emit(
                    ticket_id,
                    "subtask_failed",
                    f"{subtask.title}: {result}",
                    level="error",
                    data={"subtask_id": subtask.id},
                )
            elif result:
                passed += 1
            else:
                blocked += 1

        ticket = self._require_ticket(ticket_id)
        self.db.merge_metrics(
            ticket_id,
            {
                "subtasks": len(ticket.subtasks),
                "subtasks_passed": passed,
                "subtasks_blocked": blocked,
                "review_rounds": sum(subtask.iterations for subtask in ticket.subtasks),
                "risks_flagged": len(plan.risks),
            },
        )

        await self._retrospective(self._require_ticket(ticket_id))

        final = TicketStatus.done if blocked == 0 else TicketStatus.needs_human
        self._set_status(ticket_id, final)
        self._emit(
            ticket_id,
            "finished",
            (
                "All subtasks approved by the reviewer agent."
                if final is TicketStatus.done
                else f"{blocked} subtask(s) need a human: review the comments and send feedback."
            ),
            level="success" if final is TicketStatus.done else "warning",
        )

    async def _plan(self, ticket: Ticket) -> PlanOutput:
        self._set_status(ticket.id, TicketStatus.planning)
        self._emit(
            ticket.id,
            "planning",
            "Planner agent is breaking the ticket down",
            role="planner",
        )
        learnings = self.db.list_learnings()
        result = await self.executor.start(
            role=AgentRole.planner,
            prompt=prompts.planner_prompt(ticket, learnings),
            schema=PlanOutput,
            title=f"[plan] {ticket.title}",
            tags=["ticket-system", "planner", ticket.id],
        )
        plan = self._expect(result, PlanOutput)
        self.db.set_plan(
            ticket.id,
            {
                "summary": plan.summary,
                "risks": plan.risks,
                "session_url": result.session_url,
                "learnings_applied": len(learnings),
            },
        )
        for position, planned in enumerate(plan.subtasks):
            self.db.add_subtask(
                ticket.id,
                position,
                planned.title,
                planned.description,
                planned.acceptance_criteria,
            )
        self._emit(
            ticket.id,
            "planned",
            f"Plan ready: {len(plan.subtasks)} subtask(s), "
            f"{len(learnings)} prior learning(s) applied",
            role="planner",
            data={
                "summary": plan.summary,
                "risks": plan.risks,
                "session_url": result.session_url,
            },
        )
        return plan

    async def _deliver_subtask(
        self, ticket: Ticket, subtask: Subtask, semaphore: asyncio.Semaphore
    ) -> bool:
        async with semaphore:
            return await self._implement_and_review(ticket, subtask)

    async def _implement_and_review(self, ticket: Ticket, subtask: Subtask) -> bool:
        self.db.update_subtask(subtask.id, status="implementing")
        self._emit(
            ticket.id,
            "implementing",
            f"Implementer agent started: {subtask.title}",
            role="implementer",
            data={"subtask_id": subtask.id},
        )
        learnings = self.db.list_learnings()
        result = await self.executor.start(
            role=AgentRole.implementer,
            prompt=prompts.implementer_prompt(ticket, subtask, learnings),
            schema=ImplementationOutput,
            title=f"[impl] {subtask.title}",
            tags=["ticket-system", "implementer", ticket.id],
        )
        implementation = self._expect(result, ImplementationOutput)
        pr_url = result.pr_url or implementation.pr_url
        self.db.update_subtask(
            subtask.id,
            status="reviewing",
            session_id=result.session_id,
            session_url=result.session_url,
            pr_url=pr_url,
        )
        self._emit(
            ticket.id,
            "implemented",
            f"{subtask.title}: {implementation.summary}",
            role="implementer",
            data={
                "subtask_id": subtask.id,
                "pr_url": pr_url,
                "session_url": result.session_url,
                "files_changed": implementation.files_changed,
            },
        )

        critic_session: str | None = None
        max_iterations = ticket.max_iterations or self.default_max_iterations

        for iteration in range(1, max_iterations + 1):
            self._set_status(ticket.id, TicketStatus.reviewing)
            self.db.update_subtask(subtask.id, iterations=iteration, status="reviewing")
            critique, critic_session = await self._review(
                ticket, subtask, implementation, critic_session
            )
            self.db.update_subtask(subtask.id, critic_session_id=critic_session)

            if critique.verdict == "pass":
                self.db.update_subtask(subtask.id, status="approved", verdict="pass")
                self._emit(
                    ticket.id,
                    "approved",
                    f"{subtask.title} approved after {iteration} review round(s)",
                    role="critic",
                    level="success",
                    data={"subtask_id": subtask.id, "pr_url": pr_url},
                )
                return True

            comments = [f"[{c.severity}] {c.body}" for c in critique.comments]
            self._emit(
                ticket.id,
                "changes_requested",
                f"{subtask.title}: reviewer requested changes ({len(comments)} comment(s))",
                role="critic",
                level="warning",
                data={
                    "subtask_id": subtask.id,
                    "comments": comments,
                    "unmet_criteria": critique.unmet_criteria,
                    "reasoning": critique.reasoning,
                },
            )

            if iteration == max_iterations:
                break

            self._set_status(ticket.id, TicketStatus.revising)
            self.db.update_subtask(subtask.id, status="revising")
            revision = await self.executor.follow_up(
                role=AgentRole.implementer,
                session_id=result.session_id,
                message=prompts.revision_prompt(comments, critique.unmet_criteria),
                schema=ImplementationOutput,
            )
            implementation = self._expect(revision, ImplementationOutput)
            pr_url = revision.pr_url or implementation.pr_url or pr_url
            self.db.update_subtask(subtask.id, pr_url=pr_url)
            self._emit(
                ticket.id,
                "revised",
                f"{subtask.title}: {implementation.summary}",
                role="implementer",
                data={"subtask_id": subtask.id, "pr_url": pr_url, "iteration": iteration},
            )

        self.db.update_subtask(subtask.id, status="needs_human", verdict="changes_requested")
        self._emit(
            ticket.id,
            "escalated",
            f"{subtask.title} still failing review after {max_iterations} round(s)",
            role="critic",
            level="error",
            data={"subtask_id": subtask.id, "pr_url": pr_url},
        )
        return False

    async def _review(
        self,
        ticket: Ticket,
        subtask: Subtask,
        implementation: ImplementationOutput,
        critic_session: str | None,
    ) -> tuple[CriticOutput, str]:
        self._emit(
            ticket.id,
            "reviewing",
            f"Reviewer agent is checking {subtask.title} against its acceptance criteria",
            role="critic",
            data={"subtask_id": subtask.id},
        )
        payload = implementation.model_dump()
        if critic_session is None:
            result = await self.executor.start(
                role=AgentRole.critic,
                prompt=prompts.critic_prompt(ticket, subtask, payload),
                schema=CriticOutput,
                title=f"[review] {subtask.title}",
                tags=["ticket-system", "critic", ticket.id],
            )
        else:
            result = await self.executor.follow_up(
                role=AgentRole.critic,
                session_id=critic_session,
                message=prompts.critic_prompt(ticket, subtask, payload),
                schema=CriticOutput,
            )
        return self._expect(result, CriticOutput), result.session_id

    async def _retrospective(self, ticket: Ticket) -> None:
        self._set_status(ticket.id, TicketStatus.retro)
        self._emit(
            ticket.id,
            "retro",
            "Retrospective agent is distilling learnings for the next ticket",
            role="retrospective",
        )
        transcript: list[dict[str, object]] = [
            {
                "phase": event.phase,
                "role": event.role,
                "message": event.message,
                "data": event.data,
            }
            for event in self.db.list_events(ticket.id)
            if event.phase
            in {"planned", "implemented", "changes_requested", "revised", "approved", "escalated"}
        ]
        try:
            result = await self.executor.start(
                role=AgentRole.retrospective,
                prompt=prompts.retro_prompt(ticket, transcript),
                schema=RetroOutput,
                title=f"[retro] {ticket.title}",
                tags=["ticket-system", "retrospective", ticket.id],
            )
            retro = self._expect(result, RetroOutput)
        except ExecutorError as exc:
            self._emit(ticket.id, "retro_failed", f"Retrospective skipped: {exc}", level="warning")
            return

        for learning in retro.learnings:
            self.db.upsert_learning(ticket.id, learning.kind, learning.title, learning.body)
        self.db.set_retro(
            ticket.id,
            {
                "summary": retro.summary,
                "recurring_issues": retro.recurring_issues,
                "learnings": [item.model_dump() for item in retro.learnings],
                "session_url": result.session_url,
            },
        )
        self._emit(
            ticket.id,
            "retro_done",
            f"{len(retro.learnings)} learning(s) recorded for future tickets",
            role="retrospective",
            level="success",
            data={
                "summary": retro.summary,
                "recurring_issues": retro.recurring_issues,
                "learnings": [item.model_dump() for item in retro.learnings],
            },
        )

    # -- human in the loop ------------------------------------------------
    async def apply_human_feedback(self, ticket_id: str, subtask_id: str, feedback: str) -> None:
        ticket = self._require_ticket(ticket_id)
        subtask = next((item for item in ticket.subtasks if item.id == subtask_id), None)
        if subtask is None:
            raise KeyError(f"unknown subtask {subtask_id}")
        if subtask.session_id is None:
            raise ValueError("subtask has no implementer session to resume")

        self._emit(
            ticket_id,
            "human_feedback",
            "Human feedback sent back into the implementer session",
            data={"subtask_id": subtask_id, "feedback": feedback},
        )
        self.db.update_subtask(
            subtask_id, status="revising", iterations=subtask.iterations + 1
        )
        self._set_status(ticket_id, TicketStatus.revising)
        revision = await self.executor.follow_up(
            role=AgentRole.implementer,
            session_id=subtask.session_id,
            message=prompts.revision_prompt([feedback], []),
            schema=ImplementationOutput,
        )
        implementation = self._expect(revision, ImplementationOutput)
        pr_url = revision.pr_url or implementation.pr_url or subtask.pr_url
        self.db.update_subtask(subtask_id, pr_url=pr_url, status="reviewing")
        self._emit(
            ticket_id,
            "revised",
            f"{subtask.title}: {implementation.summary}",
            role="implementer",
            data={"subtask_id": subtask_id, "pr_url": pr_url},
        )

        critique, critic_session = await self._review(
            ticket, subtask, implementation, subtask.critic_session_id
        )
        self.db.update_subtask(subtask_id, critic_session_id=critic_session)
        if critique.verdict == "pass":
            self.db.update_subtask(subtask_id, status="approved", verdict="pass")
            self._emit(
                ticket_id,
                "approved",
                f"{subtask.title} approved after human feedback",
                role="critic",
                level="success",
                data={"subtask_id": subtask_id, "pr_url": pr_url},
            )
        else:
            self.db.update_subtask(subtask_id, status="needs_human", verdict="changes_requested")
            self._emit(
                ticket_id,
                "changes_requested",
                f"{subtask.title}: reviewer still requests changes",
                role="critic",
                level="warning",
                data={
                    "subtask_id": subtask_id,
                    "comments": [f"[{c.severity}] {c.body}" for c in critique.comments],
                },
            )

        subtasks = self._require_ticket(ticket_id).subtasks
        remaining = [item for item in subtasks if item.status != "approved"]
        self.db.merge_metrics(
            ticket_id,
            {
                "subtasks_passed": len(subtasks) - len(remaining),
                "subtasks_blocked": len(remaining),
                "review_rounds": sum(item.iterations for item in subtasks),
            },
        )
        self._set_status(
            ticket_id, TicketStatus.needs_human if remaining else TicketStatus.done
        )

    # -- helpers ----------------------------------------------------------
    def _require_ticket(self, ticket_id: str) -> Ticket:
        ticket = self.db.get_ticket(ticket_id)
        if ticket is None:
            raise KeyError(f"unknown ticket {ticket_id}")
        return ticket

    def _set_status(self, ticket_id: str, status: TicketStatus) -> None:
        self.db.set_status(ticket_id, status)
        self._emit(ticket_id, "status", status.value, data={"status": status.value})

    def _emit(
        self,
        ticket_id: str,
        phase: str,
        message: str,
        role: str | None = None,
        level: str = "info",
        data: dict[str, object] | None = None,
    ) -> None:
        event = self.db.add_event(ticket_id, phase, message, role=role, level=level, data=data)
        self.bus.publish(event)

    @staticmethod
    def _expect[T](result: AgentResult, schema: type[T]) -> T:
        if not isinstance(result.output, schema):
            raise ExecutorError(
                f"expected {schema.__name__} from {result.role.value}, got "
                f"{type(result.output).__name__}"
            )
        return result.output
