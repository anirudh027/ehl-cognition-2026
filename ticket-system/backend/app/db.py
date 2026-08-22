from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .models import (
    Event,
    Learning,
    Subtask,
    Ticket,
    TicketCreate,
    TicketStatus,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    repo TEXT NOT NULL,
    base_branch TEXT NOT NULL,
    acceptance_criteria TEXT NOT NULL,
    status TEXT NOT NULL,
    max_iterations INTEGER NOT NULL,
    plan TEXT,
    metrics TEXT NOT NULL DEFAULT '{}',
    retro TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subtasks (
    id TEXT PRIMARY KEY,
    ticket_id TEXT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    acceptance_criteria TEXT NOT NULL,
    status TEXT NOT NULL,
    iterations INTEGER NOT NULL DEFAULT 0,
    session_id TEXT,
    session_url TEXT,
    pr_url TEXT,
    verdict TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL,
    role TEXT,
    phase TEXT NOT NULL,
    message TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'info',
    data TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_ticket ON events(ticket_id, id);

CREATE TABLE IF NOT EXISTS learnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    hits INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE(kind, title)
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Database:
    """Thin synchronous SQLite wrapper; all writes are serialised by a lock."""

    def __init__(self, path: Path) -> None:
        self.path = path
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    # -- tickets ----------------------------------------------------------
    def create_ticket(self, payload: TicketCreate, max_iterations: int) -> str:
        ticket_id = f"tkt_{uuid.uuid4().hex[:10]}"
        now = _now()
        with self._tx() as conn:
            conn.execute(
                """INSERT INTO tickets (id, title, description, repo, base_branch,
                       acceptance_criteria, status, max_iterations, metrics, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    ticket_id,
                    payload.title,
                    payload.description,
                    payload.repo,
                    payload.base_branch,
                    json.dumps(payload.acceptance_criteria),
                    TicketStatus.queued.value,
                    payload.max_iterations or max_iterations,
                    json.dumps({}),
                    now,
                    now,
                ),
            )
        return ticket_id

    def set_status(self, ticket_id: str, status: TicketStatus) -> None:
        with self._tx() as conn:
            conn.execute(
                "UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, _now(), ticket_id),
            )

    def set_plan(self, ticket_id: str, plan: dict[str, object]) -> None:
        with self._tx() as conn:
            conn.execute(
                "UPDATE tickets SET plan = ?, updated_at = ? WHERE id = ?",
                (json.dumps(plan), _now(), ticket_id),
            )

    def set_retro(self, ticket_id: str, retro: dict[str, object]) -> None:
        with self._tx() as conn:
            conn.execute(
                "UPDATE tickets SET retro = ?, updated_at = ? WHERE id = ?",
                (json.dumps(retro), _now(), ticket_id),
            )

    def merge_metrics(self, ticket_id: str, updates: dict[str, object]) -> None:
        with self._tx() as conn:
            row = conn.execute(
                "SELECT metrics FROM tickets WHERE id = ?", (ticket_id,)
            ).fetchone()
            current: dict[str, object] = json.loads(row["metrics"]) if row else {}
            current.update(updates)
            conn.execute(
                "UPDATE tickets SET metrics = ?, updated_at = ? WHERE id = ?",
                (json.dumps(current), _now(), ticket_id),
            )

    def get_ticket(self, ticket_id: str) -> Ticket | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM tickets WHERE id = ?", (ticket_id,)
            ).fetchone()
        if row is None:
            return None
        return self._hydrate(row)

    def list_tickets(self, limit: int = 100) -> list[Ticket]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM tickets ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._hydrate(row) for row in rows]

    def _hydrate(self, row: sqlite3.Row) -> Ticket:
        subtasks = self.list_subtasks(row["id"])
        return Ticket(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            repo=row["repo"],
            base_branch=row["base_branch"],
            acceptance_criteria=json.loads(row["acceptance_criteria"]),
            status=TicketStatus(row["status"]),
            max_iterations=row["max_iterations"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            plan=json.loads(row["plan"]) if row["plan"] else None,
            subtasks=subtasks,
            pr_urls=[s.pr_url for s in subtasks if s.pr_url],
            metrics=json.loads(row["metrics"]),
            retro=json.loads(row["retro"]) if row["retro"] else None,
        )

    # -- subtasks ---------------------------------------------------------
    def add_subtask(
        self,
        ticket_id: str,
        position: int,
        title: str,
        description: str,
        acceptance_criteria: list[str],
    ) -> str:
        subtask_id = f"sub_{uuid.uuid4().hex[:10]}"
        with self._tx() as conn:
            conn.execute(
                """INSERT INTO subtasks (id, ticket_id, position, title, description,
                       acceptance_criteria, status)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    subtask_id,
                    ticket_id,
                    position,
                    title,
                    description,
                    json.dumps(acceptance_criteria),
                    "queued",
                ),
            )
        return subtask_id

    def update_subtask(self, subtask_id: str, **fields: object) -> None:
        if not fields:
            return
        allowed = {
            "status",
            "iterations",
            "session_id",
            "session_url",
            "pr_url",
            "verdict",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unknown subtask fields: {sorted(unknown)}")
        assignments = ", ".join(f"{key} = ?" for key in fields)
        with self._tx() as conn:
            conn.execute(
                f"UPDATE subtasks SET {assignments} WHERE id = ?",
                (*fields.values(), subtask_id),
            )

    def list_subtasks(self, ticket_id: str) -> list[Subtask]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM subtasks WHERE ticket_id = ? ORDER BY position", (ticket_id,)
            ).fetchall()
        return [
            Subtask(
                id=row["id"],
                title=row["title"],
                description=row["description"],
                acceptance_criteria=json.loads(row["acceptance_criteria"]),
                status=row["status"],
                iterations=row["iterations"],
                session_id=row["session_id"],
                session_url=row["session_url"],
                pr_url=row["pr_url"],
                verdict=row["verdict"],
            )
            for row in rows
        ]

    # -- events -----------------------------------------------------------
    def add_event(
        self,
        ticket_id: str,
        phase: str,
        message: str,
        role: str | None = None,
        level: str = "info",
        data: dict[str, object] | None = None,
    ) -> Event:
        created_at = _now()
        with self._tx() as conn:
            cursor = conn.execute(
                """INSERT INTO events (ticket_id, role, phase, message, level, data, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    ticket_id,
                    role,
                    phase,
                    message,
                    level,
                    json.dumps(data) if data is not None else None,
                    created_at,
                ),
            )
            event_id = int(cursor.lastrowid or 0)
        return Event(
            id=event_id,
            ticket_id=ticket_id,
            role=role,
            phase=phase,
            message=message,
            level=level,
            data=data,
            created_at=created_at,
        )

    def list_events(self, ticket_id: str, after_id: int = 0) -> list[Event]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE ticket_id = ? AND id > ? ORDER BY id",
                (ticket_id, after_id),
            ).fetchall()
        return [
            Event(
                id=row["id"],
                ticket_id=row["ticket_id"],
                role=row["role"],
                phase=row["phase"],
                message=row["message"],
                level=row["level"],
                data=json.loads(row["data"]) if row["data"] else None,
                created_at=row["created_at"],
            )
            for row in rows
        ]

    # -- learnings --------------------------------------------------------
    def upsert_learning(self, ticket_id: str, kind: str, title: str, body: str) -> None:
        with self._tx() as conn:
            conn.execute(
                """INSERT INTO learnings (ticket_id, kind, title, body, created_at)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(kind, title) DO UPDATE SET
                       hits = hits + 1,
                       body = excluded.body,
                       ticket_id = excluded.ticket_id""",
                (ticket_id, kind, title, body, _now()),
            )

    def list_learnings(self, limit: int = 50) -> list[Learning]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM learnings ORDER BY hits DESC, id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            Learning(
                id=row["id"],
                ticket_id=row["ticket_id"],
                kind=row["kind"],
                title=row["title"],
                body=row["body"],
                hits=row["hits"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
