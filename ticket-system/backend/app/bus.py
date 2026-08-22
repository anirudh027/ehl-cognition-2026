from __future__ import annotations

import asyncio
from collections import defaultdict

from .models import Event

QUEUE_MAXSIZE = 512


class EventBus:
    """Fan-out of ticket events to any number of SSE subscribers."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[Event]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, ticket_id: str) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        async with self._lock:
            self._subscribers[ticket_id].add(queue)
        return queue

    async def unsubscribe(self, ticket_id: str, queue: asyncio.Queue[Event]) -> None:
        async with self._lock:
            self._subscribers[ticket_id].discard(queue)
            if not self._subscribers[ticket_id]:
                del self._subscribers[ticket_id]

    def publish(self, event: Event) -> None:
        for ticket_id in (event.ticket_id, "*"):
            for queue in tuple(self._subscribers.get(ticket_id, ())):
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    continue
