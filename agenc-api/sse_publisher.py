"""SSE fan-out to connected dashboard EventSource clients."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class SsePublisher:
    """Owns subscriber queues only; callers format SSE frames via publish()."""

    __slots__ = ("_clients",)

    def __init__(self) -> None:
        self._clients: list[asyncio.Queue[str]] = []

    def subscribe(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue()
        self._clients.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[str]) -> None:
        try:
            self._clients.remove(q)
        except ValueError:
            pass

    async def publish(self, event: str, data: dict[str, Any]) -> None:
        msg = f"event: {event}\ndata: {json.dumps(data)}\n\n"
        for q in list(self._clients):
            try:
                await q.put(msg)
            except Exception as e:
                logger.warning("sse publish put failed: %s", e)

    @property
    def subscriber_count(self) -> int:
        return len(self._clients)


publisher = SsePublisher()
