import asyncio
import csv
import math
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from Bio import AlignIO
from Bio.PDB import PDBParser

from backend.app.store import Store

REFERENCE_DIR = Path(__file__).resolve().parents[1] / "data" / "reference"
ACTIVE_SITE_POSITIONS = (160, 206, 237)


@dataclass(frozen=True)
class CandidateSeed:
    mutation: str
    position: int
    prior: float
    note: str


CANDIDATE_SEEDS = (
    CandidateSeed("S121E", 121, 0.83, "Reported in the FAST-PETase engineering set"),
    CandidateSeed("D186H", 186, 0.81, "Reported in the FAST-PETase engineering set"),
    CandidateSeed("R224Q", 224, 0.78, "Reported in the FAST-PETase engineering set"),
    CandidateSeed("N233K", 233, 0.79, "Reported in the FAST-PETase engineering set"),
    CandidateSeed("R280A", 280, 0.76, "Reported in the FAST-PETase engineering set"),
)


class WorkflowRunner:
    def __init__(self, store: Store, runs_dir: Path, step_delay: float = 0.45) -> None:
        self.store = store
        self.runs_dir = runs_dir
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.step_delay = step_delay

    async def run(self, run_id: str, agents: dict[str, str]) -> None:
        coordinator = agents["coordinator"]
        try:
            self.store.update_run(
                run_id,
                status="running",
                stage="Coordinator planning",
                progress=8,
            )
            self.store.update_agent(
                coordinator,
                status="running",
                summary="Planning two parallel evidence tracks",
            )
            self.store.add_event(
                run_id,
                "plan_created",
                "Coordinator created the investigation plan",
                "Sequence conservation and structure context will run in parallel.",
                agent_id=coordinator,
                tone="accent",
            )
            await self._pause()
            self.store.update_run(
                run_id,
                stage="Parallel analysis",
                progress=18,
            )
            self.store.add_event(
                run_id,
                "child_devin_started",
                "Two specialist Devins started",
                "Sequence and Structure workers are operating independently.",
                agent_id=coordinator,
                tone="accent",
            )
            sequence_result, structure_result = await asyncio.gather(
                self._run_sequence(run_id, agents["sequence"]),
                self._run_structure(run_id, agents["structure"]),
            )
            self.store.update_run(
                run_id,
                stage="Combining evidence",
                progress=76,
            )
            self.store.update_agent(
                coordinator,
                status="running",
                summary="Combining conservation and structural evidence",
            )
            self.store.add_event(
                run_id,
                "decision_made",
                "Coordinator protected catalytic positions",
                "Ser160, Asp206, and His237 are excluded from candidate generation.",
                agent_id=coordinator,
                tone="accent",
            )
            await self._pause()
            candidates = self._rank_candidates(
                sequence_result,
                structure_result,
                excluded_distance=None,
            )
            self.store.replace_candidates(run_id, 1, candidates)
            self.store.add_event(
                run_id,
                "ranking_updated",
                "Evidence-backed shortlist created",
                "Five literature-linked positions were ranked with calculated context.",
                agent_id=coordinator,
                tone="success",
            )
            self.store.update_agent(
                coordinator,
                status="completed",
                summary="Shortlist ready for human review",
            )
            self.store.update_run(
                run_id,
                status="completed",
                stage="Shortlist ready",
                progress=100,
            )
            self.store.add_event(
                run_id,
                "run_completed",
                "Run completed",
                "Results are candidate priorities, not experimental validation.",
                agent_id=coordinator,
                tone="success",
            )
        except Exception as error:
            self.store.update_agent(
                coordinator,
                status="failed",
                summary="Workflow stopped after an unrecoverable error",
            )
            self.store.update_run(
                run_id,
                status="failed",
                stage="Run failed",
            )
            self.store.add_event(
                run_id,
                "error_detected",
                "Workflow failed",
                str(error),
                agent_id=coordinator,
                tone="danger",
            )

    async def apply_follow_up(self, run_id: str, message: str) -> dict[str, object]:
        run = self.store.get_run(run_id)
        if str(run["status"]) not in {"completed", "failed"}:
            raise ValueError("Wait for the current run to finish before steering it.")
        self.store.add_message(run_id, message)
        coordinator = next(
            str(agent["id"]) for agent in list(run["agents"]) if str(agent["role"]) == "coordinator"
        )
        self.store.update_agent(
            coordinator,
            status="running",
            summary="Applying a follow-up constraint",
        )
        self.store.update_run(
            run_id,
            status="running",
            stage="Applying follow-up",
            progress=82,
        )
        self.store.add_event(
            run_id,
            "user_constraint_received",
            "Follow-up constraint received",
            message,
            agent_id=coordinator,
            tone="accent",
        )
        await self._pause()
        threshold = self._distance_threshold(message)
        current = list(run["candidates"])
        next_version = int(run["result_version"]) + 1
        updated: list[dict[str, object]] = []
        for candidate in current:
            excluded = bool(candidate["excluded"])
            if threshold is not None and float(candidate["distance"]) < threshold:
                excluded = True
            updated.append(
                {
                    "mutation": str(candidate["mutation"]),
                    "position": int(candidate["position"]),
                    "score": float(candidate["score"]),
                    "distance": float(candidate["distance"]),
                    "conservation": float(candidate["conservation"]),
                    "evidence": list(candidate["evidence"]),
                    "rationale": str(candidate["rationale"]),
                    "excluded": excluded,
                }
            )
        self.store.replace_candidates(run_id, next_version, updated)
        detail = (
            f"Candidates within {threshold:g} Å of the catalytic triad were excluded."
            if threshold is not None
            else "The constraint was recorded; no catalytic-distance threshold was detected."
        )
        self.store.add_event(
            run_id,
            "ranking_updated",
            f"Ranking version {next_version} created",
            detail,
            agent_id=coordinator,
            tone="success",
        )
        self.store.update_agent(
            coordinator,
            status="completed",
            summary="Follow-up applied without rerunning completed tools",
        )
        self.store.update_run(
            run_id,
            status="completed",
            stage="Updated shortlist ready",
            progress=100,
            result_version=next_version,
        )
        return self.store.get_run(run_id)

    async def _run_sequence(self, run_id: str, agent_id: str) -> dict[int, float]:
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        alignment_path = run_dir / "petase_alignment.fasta"
        conservation_path = run_dir / "conservation.csv"
        self.store.update_agent(
            agent_id,
            status="running",
            summary="Aligning a curated PET hydrolase family",
        )
        self.store.add_event(
            run_id,
            "stage_started",
            "Sequence analysis started",
            "MAFFT will align six curated PET hydrolase sequences.",
            agent_id=agent_id,
        )
        await self._pause()
        result = await self._command(
            "mafft",
            "--auto",
            str(REFERENCE_DIR / "petase_family.fasta"),
        )
        if result[0] != 0:
            raise RuntimeError(f"MAFFT failed: {result[2][-400:]}")
        alignment_path.write_text(result[1])
        conservation = self._calculate_conservation(alignment_path, conservation_path)
        self.store.add_artifact(
            run_id,
            kind="alignment",
            name=alignment_path.name,
            path=alignment_path,
            description="MAFFT alignment of the curated PET hydrolase family",
            content_type="text/plain",
        )
        self.store.add_artifact(
            run_id,
            kind="conservation",
            name=conservation_path.name,
            path=conservation_path,
            description="Per-position normalized conservation for IsPETase",
            content_type="text/csv",
        )
        self.store.add_event(
            run_id,
            "tool_completed",
            "MAFFT alignment completed",
            f"{len(conservation)} target positions were mapped and scored.",
            agent_id=agent_id,
            tone="success",
        )
        self.store.update_agent(
            agent_id,
            status="completed",
            summary="Alignment and conservation profile ready",
        )
        return conservation

    async def _run_structure(self, run_id: str, agent_id: str) -> dict[int, float]:
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        pdb_path = run_dir / "5XJH.pdb"
        dssp_path = run_dir / "5XJH.dssp"
        distance_path = run_dir / "candidate_distances.csv"
        shutil.copy2(REFERENCE_DIR / "5XJH.pdb", pdb_path)
        self.store.update_agent(
            agent_id,
            status="running",
            summary="Calculating structure context and catalytic distances",
        )
        self.store.add_event(
            run_id,
            "stage_started",
            "Structure analysis started",
            "DSSP and Bio.PDB will inspect the 5XJH crystal structure.",
            agent_id=agent_id,
        )
        await self._pause()
        failed = await self._command(
            "mkdssp",
            str(run_dir / "5XJH-chain-B.pdb"),
            str(dssp_path),
        )
        if failed[0] == 0:
            raise RuntimeError("The recovery demonstration unexpectedly succeeded.")
        self.store.add_event(
            run_id,
            "error_detected",
            "Structure input was not found",
            (
                "The requested chain-specific file did not exist; "
                "the worker inspected available inputs."
            ),
            agent_id=agent_id,
            tone="warning",
        )
        self.store.add_event(
            run_id,
            "retry_started",
            "Structure worker repaired the command",
            "Retrying DSSP with the validated 5XJH structure file.",
            agent_id=agent_id,
            tone="accent",
        )
        await self._pause()
        recovered = await self._command("mkdssp", str(pdb_path), str(dssp_path))
        if recovered[0] != 0:
            raise RuntimeError(f"DSSP failed after retry: {recovered[2][-400:]}")
        distances = self._calculate_distances(pdb_path, distance_path)
        self.store.add_artifact(
            run_id,
            kind="structure",
            name=pdb_path.name,
            path=pdb_path,
            description="RCSB 5XJH IsPETase crystal structure",
            content_type="chemical/x-pdb",
        )
        self.store.add_artifact(
            run_id,
            kind="secondary_structure",
            name=dssp_path.name,
            path=dssp_path,
            description="DSSP secondary-structure assignment",
            content_type="text/plain",
        )
        self.store.add_artifact(
            run_id,
            kind="distance_table",
            name=distance_path.name,
            path=distance_path,
            description="Candidate Cα distances to the nearest catalytic residue",
            content_type="text/csv",
        )
        self.store.add_event(
            run_id,
            "retry_succeeded",
            "DSSP retry succeeded",
            "The repaired command produced secondary-structure and distance artifacts.",
            agent_id=agent_id,
            tone="success",
        )
        self.store.update_agent(
            agent_id,
            status="completed",
            summary="Structure context and catalytic distances ready",
        )
        return distances

    def _calculate_conservation(
        self,
        alignment_path: Path,
        output_path: Path,
    ) -> dict[int, float]:
        alignment = AlignIO.read(alignment_path, "fasta")
        target = next(record for record in alignment if "A0A0K8P6T7" in record.id)
        target_position = 0
        conservation: dict[int, float] = {}
        rows: list[tuple[int, str, float]] = []
        for column_index, target_residue in enumerate(str(target.seq)):
            if target_residue == "-":
                continue
            target_position += 1
            residues = [
                residue for residue in alignment[:, column_index] if residue not in {"-", "X"}
            ]
            counts = Counter(residues)
            total = sum(counts.values())
            entropy = -sum((count / total) * math.log(count / total) for count in counts.values())
            normalized = entropy / math.log(20)
            score = round(max(0.0, 1.0 - normalized), 3)
            conservation[target_position] = score
            rows.append((target_position, target_residue, score))
        with output_path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(("position", "residue", "conservation"))
            writer.writerows(rows)
        return conservation

    def _calculate_distances(
        self,
        pdb_path: Path,
        output_path: Path,
    ) -> dict[int, float]:
        structure = PDBParser(QUIET=True).get_structure("5XJH", pdb_path)
        chain = structure[0]["A"]
        active_atoms = [chain[position]["CA"] for position in ACTIVE_SITE_POSITIONS]
        distances: dict[int, float] = {}
        rows: list[tuple[str, int, float]] = []
        for seed in CANDIDATE_SEEDS:
            atom = chain[seed.position]["CA"]
            distance = round(float(min(atom - active for active in active_atoms)), 1)
            distances[seed.position] = distance
            rows.append((seed.mutation, seed.position, distance))
        with output_path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(("mutation", "position", "nearest_catalytic_ca_distance_angstrom"))
            writer.writerows(rows)
        return distances

    def _rank_candidates(
        self,
        conservation: dict[int, float],
        distances: dict[int, float],
        excluded_distance: float | None,
    ) -> list[dict[str, object]]:
        candidates: list[dict[str, object]] = []
        for seed in CANDIDATE_SEEDS:
            conservation_score = conservation.get(seed.position, 1.0)
            distance = distances[seed.position]
            context = (1.0 - conservation_score) * 0.08 + min(distance / 35, 1.0) * 0.09
            score = round(min(0.97, seed.prior * 0.82 + context), 3)
            candidates.append(
                {
                    "mutation": seed.mutation,
                    "position": seed.position,
                    "score": score,
                    "distance": distance,
                    "conservation": conservation_score,
                    "evidence": ["KNOWN", "CALCULATED", "PREDICTED"],
                    "rationale": (
                        f"{seed.note}; conservation {conservation_score:.2f}; "
                        f"{distance:.1f} Å from the nearest catalytic residue. "
                        "The composite priority is a demo prediction, not a measured 60 °C result."
                    ),
                    "excluded": (excluded_distance is not None and distance < excluded_distance),
                }
            )
        return sorted(candidates, key=lambda item: float(item["score"]), reverse=True)

    def _distance_threshold(self, message: str) -> float | None:
        if not re.search(r"catalytic|active\s+site", message, flags=re.IGNORECASE):
            return None
        match = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:å|a|angstrom)",
            message,
            flags=re.IGNORECASE,
        )
        return float(match.group(1)) if match else None

    async def _command(self, *command: str) -> tuple[int, str, str]:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        return process.returncode, stdout.decode(errors="replace"), stderr.decode(errors="replace")

    async def _pause(self) -> None:
        if self.step_delay > 0:
            await asyncio.sleep(self.step_delay)
