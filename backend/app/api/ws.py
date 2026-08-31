"""WebSocket routes."""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.api.telemetry import TelemetryHub

router = APIRouter(tags=["ws"])
logger = logging.getLogger("web2ps5.ws")


@router.websocket("/ws/telemetry")
async def telemetry_socket(ws: WebSocket) -> None:
    hub: TelemetryHub = ws.app.state.telemetry
    await hub.connect(ws)
    try:
        while True:
            # Clients may send pings / acks; payload ignored for now.
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=60.0)
            except asyncio.TimeoutError:
                await hub.send(ws, {"type": "ping", "t": time.time()})
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("telemetry socket closed with error", exc_info=True)
    finally:
        await hub.disconnect(ws)
