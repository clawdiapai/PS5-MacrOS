"""WebSocket telemetry hub — coalesced event broadcast to studio clients."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("web2ps5.telemetry")


class TelemetryHub:
    """Fan-out JSON events to connected WebSocket clients."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        await self.send(ws, {"type": "hello", "clients": self.client_count})

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def send(self, ws: WebSocket, event: dict[str, Any]) -> None:
        await ws.send_text(json.dumps(event, separators=(",", ":")))

    async def broadcast(self, event: dict[str, Any]) -> None:
        payload = json.dumps(event, separators=(",", ":"))
        async with self._lock:
            clients = list(self._clients)
        stale: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_text(payload)
            except Exception:
                stale.append(ws)
        if stale:
            async with self._lock:
                for ws in stale:
                    self._clients.discard(ws)
            logger.debug("dropped %s stale telemetry clients", len(stale))
