import asyncio
import json
import logging
from typing import Callable

logger = logging.getLogger(__name__)


class EventBus:
    """Simple in-process pub/sub for WebSocket broadcast."""

    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, build_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subscribers.setdefault(build_id, []).append(q)
        return q

    def unsubscribe(self, build_id: str, queue: asyncio.Queue):
        subs = self._subscribers.get(build_id, [])
        if queue in subs:
            subs.remove(queue)

    async def publish(self, build_id: str, event: dict):
        subs = self._subscribers.get(build_id, [])
        dead = []
        for q in subs:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("EventBus queue full for build %s, dropping event", build_id)
            except Exception as e:
                logger.error("EventBus publish error: %s", e)
                dead.append(q)
        for q in dead:
            self.unsubscribe(build_id, q)


event_bus = EventBus()
