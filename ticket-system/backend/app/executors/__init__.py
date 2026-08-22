from __future__ import annotations

from ..settings import Settings
from .base import AgentResult, Executor, ExecutorError
from .devin import DevinExecutor
from .mock import MockExecutor

__all__ = [
    "AgentResult",
    "DevinExecutor",
    "Executor",
    "ExecutorError",
    "MockExecutor",
    "build_executor",
]


def build_executor(settings: Settings) -> Executor:
    if settings.executor == "devin":
        return DevinExecutor(settings)
    if settings.executor == "mock":
        return MockExecutor(settings)
    raise ExecutorError(f"unknown executor '{settings.executor}' (expected 'devin' or 'mock')")
