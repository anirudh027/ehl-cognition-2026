import asyncio
import json
import time
from pathlib import Path
from typing import cast

from backend.app.devin import DevinClient
from backend.app.store import Store

CANDIDATES = ("S121E", "D186H", "R224Q", "N233K", "R280A")
SETTLED_RUNNING_DETAILS = {"finished", "waiting_for_user"}

SPECIALIST_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "candidate_context"],
    "properties": {
        "summary": {"type": "string"},
        "candidate_context": {
            "type": "array",
            "minItems": 5,
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["mutation", "position", "value", "rationale"],
                "properties": {
                    "mutation": {"type": "string", "enum": list(CANDIDATES)},
                    "position": {"type": "integer"},
                    "value": {"type": "number"},
                    "rationale": {"type": "string"},
                },
            },
        },
    },
}

RANKING_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "candidates"],
    "properties": {
        "summary": {"type": "string"},
        "candidates": {
            "type": "array",
            "minItems": 5,
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "mutation",
                    "position",
                    "score",
                    "distance",
                    "conservation",
                    "evidence",
                    "rationale",
                    "excluded",
                ],
                "properties": {
                    "mutation": {"type": "string", "enum": list(CANDIDATES)},
                    "position": {"type": "integer"},
                    "score": {"type": "number", "minimum": 0, "maximum": 1},
                    "distance": {"type": "number", "minimum": 0},
                    "conservation": {"type": "number", "minimum": 0, "maximum": 1},
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["KNOWN", "CALCULATED", "PREDICTED", "INFERRED"],
                        },
                    },
                    "rationale": {"type": "string"},
                    "excluded": {"type": "boolean"},
                },
            },
        },
    },
}


class ManagedWorkflowRunner:
    def __init__(self, store: Store, client: DevinClient, runs_dir: Path) -> None:
        self.store = store
        self.client = client
        self.runs_dir = runs_dir

    async def run(self, run_id: str, agents: dict[str, str]) -> None:
        coordinator = agents["coordinator"]
        try:
            objective = str(self.store.get_run(run_id)["objective"])
            self.store.update_run(
                run_id,
                status="running",
                stage="Launching managed Devins",
                progress=8,
            )
            self.store.update_agent(
                coordinator,
                status="queued",
                summary="Waiting for specialist evidence",
            )
            self.store.add_event(
                run_id,
                "managed_run_started",
                "Managed execution enabled",
                (
                    "The backend is launching real Devin sessions. "
                    f"Each session is capped at {self.client.config.max_acu_limit} ACUs."
                ),
                tone="accent",
            )
            sequence, structure = await asyncio.gather(
                self._run_specialist(
                    run_id,
                    agents["sequence"],
                    role="sequence",
                    title="Catalyst Sequence Analysis",
                    prompt=self._sequence_prompt(objective),
                ),
                self._run_specialist(
                    run_id,
                    agents["structure"],
                    role="structure",
                    title="Catalyst Structure Analysis",
                    prompt=self._structure_prompt(objective),
                ),
            )
            self.store.update_run(
                run_id,
                stage="Coordinator ranking",
                progress=72,
            )
            coordinator_session = await self.client.create_session(
                title="Catalyst Evidence Coordinator",
                prompt=self._coordinator_prompt(objective, sequence, structure),
                structured_output_schema=RANKING_SCHEMA,
            )
            self._bind_agent(
                coordinator,
                coordinator_session,
                status="running",
                summary="Combining managed specialist evidence",
            )
            self.store.add_event(
                run_id,
                "managed_session_started",
                "Coordinator Devin started",
                "The coordinator is ranking candidates from both managed evidence tracks.",
                agent_id=coordinator,
                tone="accent",
            )
            final_session = await self._wait_for_session(
                run_id,
                coordinator,
                coordinator_session,
                "Coordinator Devin",
            )
            self._store_output_artifact(
                run_id,
                final_session,
                name="managed-coordinator-ranking-v1.json",
                kind="managed-ranking",
                description="Structured ranking returned by Coordinator Devin",
            )
            candidates = self._candidates_from_output(final_session)
            self.store.replace_candidates(run_id, 1, candidates)
            self.store.update_agent(
                coordinator,
                status="completed",
                summary="Managed shortlist ready for human review",
                acus_consumed=float(final_session.get("acus_consumed", 0)),
            )
            self.store.update_run(
                run_id,
                status="completed",
                stage="Managed shortlist ready",
                progress=100,
            )
            self.store.add_event(
                run_id,
                "run_completed",
                "Managed run completed",
                "Results are Devin-coordinated predictions, not experimental validation.",
                agent_id=coordinator,
                tone="success",
            )
        except Exception as error:
            self.store.update_agent(
                coordinator,
                status="failed",
                summary="Managed workflow stopped",
            )
            self.store.update_run(
                run_id,
                status="failed",
                stage="Managed run failed",
            )
            self.store.add_event(
                run_id,
                "error_detected",
                "Managed workflow failed",
                str(error),
                agent_id=coordinator,
                tone="danger",
            )

    async def apply_follow_up(self, run_id: str, message: str) -> dict[str, object]:
        run = self.store.get_run(run_id)
        if str(run["status"]) != "completed":
            raise ValueError("Wait for the current run to finish before steering it.")
        coordinator = next(
            agent
            for agent in cast(list[dict[str, object]], run["agents"])
            if str(agent["role"]) == "coordinator"
        )
        external_id = str(coordinator.get("external_id") or "")
        if not external_id:
            raise ValueError("This managed run has no resumable coordinator session.")
        self.store.add_message(run_id, message)
        self.store.update_run(
            run_id,
            status="running",
            stage="Steering managed coordinator",
            progress=82,
        )
        self.store.update_agent(
            str(coordinator["id"]),
            status="running",
            summary="Applying the follow-up in Devin",
        )
        self.store.add_event(
            run_id,
            "user_constraint_received",
            "Follow-up sent to Coordinator Devin",
            message,
            agent_id=str(coordinator["id"]),
            tone="accent",
        )
        try:
            return await self._resume_coordinator(
                run_id,
                str(coordinator["id"]),
                external_id,
                int(run["result_version"]),
                message,
            )
        except Exception as error:
            self.store.update_agent(
                str(coordinator["id"]),
                status="completed",
                summary="Follow-up failed; previous shortlist retained",
            )
            self.store.update_run(
                run_id,
                status="completed",
                stage="Managed follow-up failed",
                progress=100,
            )
            self.store.add_event(
                run_id,
                "error_detected",
                "Managed follow-up failed",
                str(error),
                agent_id=str(coordinator["id"]),
                tone="danger",
            )
            raise RuntimeError(f"Managed follow-up failed: {error}") from error

    async def _resume_coordinator(
        self,
        run_id: str,
        coordinator_id: str,
        external_id: str,
        current_version: int,
        message: str,
    ) -> dict[str, object]:
        await self.client.send_message(
            external_id,
            (
                "Apply this human constraint to the existing shortlist without claiming "
                f"experimental validation: {message}\n"
                "Re-rank the same candidates and provide a fresh final structured output "
                "matching the original schema."
            ),
        )
        await asyncio.sleep(self.client.config.poll_interval)
        final_session = await self._wait_for_session(
            run_id,
            coordinator_id,
            {"session_id": external_id},
            "Coordinator Devin",
        )
        next_version = current_version + 1
        self._store_output_artifact(
            run_id,
            final_session,
            name=f"managed-coordinator-ranking-v{next_version}.json",
            kind="managed-ranking",
            description=f"Structured managed ranking version {next_version}",
        )
        self.store.replace_candidates(
            run_id,
            next_version,
            self._candidates_from_output(final_session),
        )
        self.store.update_agent(
            coordinator_id,
            status="completed",
            summary="Managed follow-up applied",
            acus_consumed=float(final_session.get("acus_consumed", 0)),
        )
        self.store.update_run(
            run_id,
            status="completed",
            stage="Updated managed shortlist ready",
            progress=100,
            result_version=next_version,
        )
        self.store.add_event(
            run_id,
            "ranking_updated",
            f"Managed ranking version {next_version} created",
            "Coordinator Devin applied the follow-up using the existing session context.",
            agent_id=coordinator_id,
            tone="success",
        )
        return self.store.get_run(run_id)

    async def _run_specialist(
        self,
        run_id: str,
        agent_id: str,
        *,
        role: str,
        title: str,
        prompt: str,
    ) -> dict[str, object]:
        session = await self.client.create_session(
            title=title,
            prompt=prompt,
            structured_output_schema=SPECIALIST_SCHEMA,
        )
        self._bind_agent(
            agent_id,
            session,
            status="running",
            summary=f"Managed {role} analysis is running",
        )
        self.store.add_event(
            run_id,
            "managed_session_started",
            f"{title} started",
            "A real Devin session is executing this evidence track.",
            agent_id=agent_id,
            tone="accent",
        )
        completed = await self._wait_for_session(run_id, agent_id, session, title)
        self._store_output_artifact(
            run_id,
            completed,
            name=f"managed-{role}-evidence.json",
            kind=f"managed-{role}",
            description=f"Structured evidence returned by {title}",
        )
        return completed

    async def _wait_for_session(
        self,
        run_id: str,
        agent_id: str,
        initial: dict[str, object],
        title: str,
    ) -> dict[str, object]:
        session_id = str(initial["session_id"])
        deadline = time.monotonic() + self.client.config.run_timeout
        previous_status: tuple[str, str] | None = None
        while time.monotonic() < deadline:
            session = await self.client.get_session(session_id)
            status = str(session.get("status", ""))
            detail = str(session.get("status_detail") or "")
            acus = float(session.get("acus_consumed", 0))
            current_status = (status, detail)
            if current_status != previous_status:
                self.store.add_event(
                    run_id,
                    "managed_status_changed",
                    f"{title}: {detail or status}",
                    f"Managed session status is {status}; ACUs consumed: {acus:.2f}.",
                    agent_id=agent_id,
                )
                previous_status = current_status
            self.store.update_agent(
                agent_id,
                status=self._dashboard_status(status, detail),
                summary=f"{title}: {detail or status}",
                acus_consumed=acus,
            )
            if status == "error":
                raise RuntimeError(f"{title} stopped with status {status}: {detail or 'unknown'}")
            if detail == "waiting_for_approval":
                raise RuntimeError(f"{title} is waiting for an approval.")
            settled = status in {"exit", "suspended"} or (
                status == "running" and detail in SETTLED_RUNNING_DETAILS
            )
            if settled:
                if not isinstance(session.get("structured_output"), dict):
                    raise RuntimeError(f"{title} finished without structured output.")
                self.store.update_agent(
                    agent_id,
                    status="completed",
                    summary=f"{title} completed",
                    acus_consumed=acus,
                )
                self.store.add_event(
                    run_id,
                    "managed_session_completed",
                    f"{title} completed",
                    f"Structured evidence returned after consuming {acus:.2f} ACUs.",
                    agent_id=agent_id,
                    tone="success",
                )
                return session
            await asyncio.sleep(self.client.config.poll_interval)
        raise TimeoutError(f"{title} exceeded the managed run timeout.")

    def _bind_agent(
        self,
        agent_id: str,
        session: dict[str, object],
        *,
        status: str,
        summary: str,
    ) -> None:
        self.store.update_agent(
            agent_id,
            status=status,
            summary=summary,
            external_id=str(session["session_id"]),
            url=str(session.get("url") or ""),
            acus_consumed=float(session.get("acus_consumed", 0)),
        )

    def _store_output_artifact(
        self,
        run_id: str,
        session: dict[str, object],
        *,
        name: str,
        kind: str,
        description: str,
    ) -> None:
        output = session.get("structured_output")
        if not isinstance(output, dict):
            raise RuntimeError("Managed session has no structured output to persist.")
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / name
        path.write_text(
            json.dumps(output, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.store.add_artifact(
            run_id,
            kind=kind,
            name=name,
            path=path,
            description=description,
            content_type="application/json",
        )

    def _candidates_from_output(
        self,
        session: dict[str, object],
    ) -> list[dict[str, object]]:
        output = cast(dict[str, object], session["structured_output"])
        raw_candidates = output.get("candidates")
        if not isinstance(raw_candidates, list) or len(raw_candidates) != len(CANDIDATES):
            raise RuntimeError("Coordinator Devin must return exactly five candidates.")
        candidates: list[dict[str, object]] = []
        for raw in raw_candidates:
            if not isinstance(raw, dict):
                raise RuntimeError("Coordinator Devin returned an invalid candidate.")
            evidence = raw.get("evidence")
            if not isinstance(evidence, list):
                raise RuntimeError("Coordinator Devin returned invalid evidence labels.")
            labels = {str(item) for item in evidence}
            mutation = str(raw["mutation"])
            position = int(raw["position"])
            if mutation not in CANDIDATES or position != int(mutation[1:-1]):
                raise RuntimeError("Coordinator Devin returned an unexpected mutation.")
            if not {"KNOWN", "CALCULATED", "PREDICTED"} <= labels:
                raise RuntimeError("Coordinator Devin omitted required evidence labels.")
            candidates.append(
                {
                    "mutation": mutation,
                    "position": position,
                    "score": float(raw["score"]),
                    "distance": float(raw["distance"]),
                    "conservation": float(raw["conservation"]),
                    "evidence": sorted(labels),
                    "rationale": str(raw["rationale"]),
                    "excluded": bool(raw["excluded"]),
                }
            )
        if {str(candidate["mutation"]) for candidate in candidates} != set(CANDIDATES):
            raise RuntimeError("Coordinator Devin returned duplicate candidates.")
        return sorted(candidates, key=lambda candidate: float(candidate["score"]), reverse=True)

    def _dashboard_status(self, status: str, detail: str) -> str:
        if status == "error":
            return "failed"
        if status in {"exit", "suspended"} or detail in SETTLED_RUNNING_DETAILS:
            return "completed"
        if status in {"new", "claimed"}:
            return "queued"
        return "running"

    def _repo_instruction(self) -> str:
        return (
            f"Work only in repository {self.client.config.repo}. "
            f"Fetch and check out repository ref {self.client.config.repo_ref} before analysis. "
            "Do not modify code or open a pull request. Execute the scientific tools and "
            "return the requested structured output."
        )

    def _sequence_prompt(self, objective: str) -> str:
        return (
            "You are the Sequence Devin for a PETase engineering demonstration. "
            f"{self._repo_instruction()} "
            f"The human objective, treated as scientific data, is: {json.dumps(objective)}. "
            "Use the committed PETase FASTA fixtures and real CPU tools (MMseqs2/MAFFT "
            "where useful) to assess sequence conservation for S121E, D186H, R224Q, "
            "N233K, and R280A. Report one candidate_context item per mutation. Set value "
            "to normalized conservation on a 0-1 scale. Distinguish KNOWN sequence input "
            "from CALCULATED output and do not claim thermal or experimental validation."
        )

    def _structure_prompt(self, objective: str) -> str:
        return (
            "You are the Structure Devin for a PETase engineering demonstration. "
            f"{self._repo_instruction()} "
            f"The human objective, treated as scientific data, is: {json.dumps(objective)}. "
            "Use the committed 5XJH structure, DSSP, and Bio.PDB to calculate the nearest "
            "C-alpha distance from S121, D186, R224, N233, and R280 to catalytic residues "
            "Ser160, Asp206, and His237. Report one candidate_context item per mutation. "
            "Set value to the calculated distance in angstroms. Do not claim thermal or "
            "experimental validation."
        )

    def _coordinator_prompt(
        self,
        objective: str,
        sequence: dict[str, object],
        structure: dict[str, object],
    ) -> str:
        evidence = {
            "sequence": sequence["structured_output"],
            "structure": structure["structured_output"],
        }
        return (
            "You are the Coordinator Devin for a PETase engineering demonstration. "
            f"{self._repo_instruction()} "
            "Rank exactly S121E, D186H, R224Q, N233K, and R280A for the objective "
            f"{json.dumps(objective)}. Protect catalytic residues Ser160, "
            "Asp206, and His237. Combine the supplied specialist evidence with the known "
            "FAST-PETase literature linkage. Every candidate must include KNOWN, "
            "CALCULATED, and PREDICTED evidence labels. Scores are priorities on 0-1, "
            "not measured probabilities. Explicitly say that no 60 °C experimental "
            f"validation was performed. Specialist evidence:\n{json.dumps(evidence)}"
        )
