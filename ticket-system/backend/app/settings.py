from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "tickets.db"
DEFAULT_ALLOWED_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


@dataclass(frozen=True)
class Settings:
    """Runtime configuration, resolved from the environment."""

    executor: str
    devin_api_base: str
    devin_api_key: str | None
    db_path: Path
    max_iterations: int
    max_parallel_subtasks: int
    poll_interval_seconds: float
    session_timeout_seconds: float
    mock_speed: float
    allowed_origins: tuple[str, ...]

    @property
    def devin_available(self) -> bool:
        return bool(self.devin_api_key)


def load_settings() -> Settings:
    api_key = os.environ.get("DEVIN_API_KEY") or None
    executor = os.environ.get("TICKETS_EXECUTOR", "devin" if api_key else "mock").lower()
    db_path = Path(os.environ.get("TICKETS_DB_PATH", str(DEFAULT_DB_PATH)))
    return Settings(
        executor=executor,
        devin_api_base=os.environ.get("DEVIN_API_BASE", "https://api.devin.ai"),
        devin_api_key=api_key,
        db_path=db_path,
        max_iterations=int(os.environ.get("TICKETS_MAX_ITERATIONS", "3")),
        max_parallel_subtasks=int(os.environ.get("TICKETS_MAX_PARALLEL", "2")),
        poll_interval_seconds=float(os.environ.get("TICKETS_POLL_INTERVAL", "10")),
        session_timeout_seconds=float(os.environ.get("TICKETS_SESSION_TIMEOUT", "5400")),
        mock_speed=float(os.environ.get("TICKETS_MOCK_SPEED", "1")),
        allowed_origins=_origins(os.environ.get("TICKETS_ALLOWED_ORIGINS")),
    )


def _origins(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return DEFAULT_ALLOWED_ORIGINS
    return tuple(part.strip() for part in raw.split(",") if part.strip())
