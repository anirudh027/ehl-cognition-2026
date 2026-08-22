import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            objective TEXT NOT NULL,
            mode TEXT NOT NULL,
            status TEXT NOT NULL,
            stage TEXT NOT NULL,
            progress INTEGER NOT NULL,
            result_version INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            parent_id TEXT,
            role TEXT NOT NULL,
            name TEXT NOT NULL,
            status TEXT NOT NULL,
            summary TEXT NOT NULL,
            external_id TEXT,
            url TEXT,
            acus_consumed REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            agent_id TEXT,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            detail TEXT NOT NULL,
            tone TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS artifacts (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            path TEXT NOT NULL,
            description TEXT NOT NULL,
            content_type TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS candidates (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            version INTEGER NOT NULL,
            mutation TEXT NOT NULL,
            position INTEGER NOT NULL,
            score REAL NOT NULL,
            distance REAL NOT NULL,
            conservation REAL NOT NULL,
            evidence TEXT NOT NULL,
            rationale TEXT NOT NULL,
            excluded INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
        with self._lock, self._connect() as connection:
            connection.executescript(schema)
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(agents)").fetchall()
            }
            migrations = {
                "external_id": "ALTER TABLE agents ADD COLUMN external_id TEXT",
                "url": "ALTER TABLE agents ADD COLUMN url TEXT",
                "acus_consumed": (
                    "ALTER TABLE agents ADD COLUMN acus_consumed REAL NOT NULL DEFAULT 0"
                ),
            }
            for column, statement in migrations.items():
                if column not in columns:
                    connection.execute(statement)

    def create_run(
        self,
        objective: str,
        mode: str = "local",
    ) -> tuple[dict[str, object], dict[str, str]]:
        run_id = uuid4().hex[:12]
        created_at = timestamp()
        coordinator_id = uuid4().hex[:10]
        sequence_id = uuid4().hex[:10]
        structure_id = uuid4().hex[:10]
        agents = [
            (coordinator_id, None, "coordinator", "Coordinator Devin"),
            (sequence_id, coordinator_id, "sequence", "Sequence Devin"),
            (structure_id, coordinator_id, "structure", "Structure Devin"),
        ]
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs
                (id, objective, mode, status, stage, progress, result_version,
                 created_at, updated_at)
                VALUES (?, ?, ?, 'queued', 'Preparing run', 2, 1, ?, ?)
                """,
                (run_id, objective, mode, created_at, created_at),
            )
            connection.executemany(
                """
                INSERT INTO agents
                (id, run_id, parent_id, role, name, status, summary, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'queued', 'Waiting to start', ?, ?)
                """,
                [
                    (agent_id, run_id, parent_id, role, name, created_at, created_at)
                    for agent_id, parent_id, role, name in agents
                ],
            )
        agent_ids = {
            "coordinator": coordinator_id,
            "sequence": sequence_id,
            "structure": structure_id,
        }
        return self.get_run(run_id), agent_ids

    def update_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        stage: str | None = None,
        progress: int | None = None,
        result_version: int | None = None,
    ) -> None:
        values: dict[str, str | int] = {"updated_at": timestamp()}
        if status is not None:
            values["status"] = status
        if stage is not None:
            values["stage"] = stage
        if progress is not None:
            values["progress"] = progress
        if result_version is not None:
            values["result_version"] = result_version
        assignments = ", ".join(f"{key} = ?" for key in values)
        with self._lock, self._connect() as connection:
            connection.execute(
                f"UPDATE runs SET {assignments} WHERE id = ?",
                (*values.values(), run_id),
            )

    def update_agent(
        self,
        agent_id: str,
        *,
        status: str,
        summary: str,
        external_id: str | None = None,
        url: str | None = None,
        acus_consumed: float | None = None,
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE agents
                SET status = ?,
                    summary = ?,
                    external_id = COALESCE(?, external_id),
                    url = COALESCE(?, url),
                    acus_consumed = COALESCE(?, acus_consumed),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    summary,
                    external_id,
                    url,
                    acus_consumed,
                    timestamp(),
                    agent_id,
                ),
            )

    def add_event(
        self,
        run_id: str,
        event_type: str,
        title: str,
        detail: str,
        *,
        agent_id: str | None = None,
        tone: str = "neutral",
    ) -> dict[str, object]:
        created_at = timestamp()
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO events
                (run_id, agent_id, type, title, detail, tone, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, agent_id, event_type, title, detail, tone, created_at),
            )
            event_id = cursor.lastrowid
        return {
            "id": event_id,
            "run_id": run_id,
            "agent_id": agent_id,
            "type": event_type,
            "title": title,
            "detail": detail,
            "tone": tone,
            "created_at": created_at,
        }

    def add_artifact(
        self,
        run_id: str,
        *,
        kind: str,
        name: str,
        path: Path,
        description: str,
        content_type: str,
    ) -> dict[str, object]:
        artifact_id = uuid4().hex[:12]
        created_at = timestamp()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO artifacts
                (id, run_id, kind, name, path, description, content_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    run_id,
                    kind,
                    name,
                    str(path),
                    description,
                    content_type,
                    created_at,
                ),
            )
        return {
            "id": artifact_id,
            "run_id": run_id,
            "kind": kind,
            "name": name,
            "description": description,
            "content_type": content_type,
            "created_at": created_at,
        }

    def replace_candidates(
        self,
        run_id: str,
        version: int,
        candidates: list[dict[str, object]],
    ) -> None:
        rows = [
            (
                uuid4().hex[:12],
                run_id,
                version,
                str(candidate["mutation"]),
                int(candidate["position"]),
                float(candidate["score"]),
                float(candidate["distance"]),
                float(candidate["conservation"]),
                json.dumps(candidate["evidence"]),
                str(candidate["rationale"]),
                int(bool(candidate["excluded"])),
            )
            for candidate in candidates
        ]
        with self._lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM candidates WHERE run_id = ? AND version = ?",
                (run_id, version),
            )
            connection.executemany(
                """
                INSERT INTO candidates
                (id, run_id, version, mutation, position, score, distance, conservation,
                 evidence, rationale, excluded)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def add_message(self, run_id: str, body: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO messages (id, run_id, body, created_at) VALUES (?, ?, ?, ?)",
                (uuid4().hex[:12], run_id, body, timestamp()),
            )

    def get_run(self, run_id: str) -> dict[str, object]:
        with self._lock, self._connect() as connection:
            run = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            if run is None:
                raise KeyError(run_id)
            agents = connection.execute(
                "SELECT * FROM agents WHERE run_id = ? ORDER BY created_at, role",
                (run_id,),
            ).fetchall()
            events = connection.execute(
                "SELECT * FROM events WHERE run_id = ? ORDER BY id",
                (run_id,),
            ).fetchall()
            artifacts = connection.execute(
                """
                SELECT id, run_id, kind, name, description, content_type, created_at
                FROM artifacts WHERE run_id = ? ORDER BY created_at
                """,
                (run_id,),
            ).fetchall()
            candidates = connection.execute(
                """
                SELECT id, run_id, version, mutation, position, score, distance, conservation,
                       evidence, rationale, excluded
                FROM candidates
                WHERE run_id = ? AND version = ?
                ORDER BY excluded, score DESC
                """,
                (run_id, int(run["result_version"])),
            ).fetchall()
            messages = connection.execute(
                "SELECT id, body, created_at FROM messages WHERE run_id = ? ORDER BY created_at",
                (run_id,),
            ).fetchall()
        candidate_rows: list[dict[str, object]] = []
        for candidate in candidates:
            row = dict(candidate)
            row["evidence"] = json.loads(str(row["evidence"]))
            row["excluded"] = bool(row["excluded"])
            candidate_rows.append(row)
        result = dict(run)
        result["agents"] = [dict(agent) for agent in agents]
        result["events"] = [dict(event) for event in events]
        result["artifacts"] = [dict(artifact) for artifact in artifacts]
        result["candidates"] = candidate_rows
        result["messages"] = [dict(message) for message in messages]
        return result

    def list_runs(self, limit: int = 20) -> list[dict[str, object]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, objective, mode, status, stage, progress, result_version,
                       created_at, updated_at
                FROM runs ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def events_after(self, run_id: str, event_id: int) -> list[dict[str, object]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE run_id = ? AND id > ? ORDER BY id",
                (run_id, event_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_artifact_path(self, artifact_id: str) -> tuple[Path, str, str]:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT path, name, content_type FROM artifacts WHERE id = ?",
                (artifact_id,),
            ).fetchone()
        if row is None:
            raise KeyError(artifact_id)
        return Path(str(row["path"])), str(row["name"]), str(row["content_type"])
