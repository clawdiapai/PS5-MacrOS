"""Front-facing console actions (Rest / Wake / status). Extensible later."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger("web2ps5.console")
router = APIRouter(prefix="/api/console", tags=["console"])

REST_GRAPH = "rest_ps5"
OPEN_FORTNITE_GRAPH = "open_fortnite"


async def _ensure_bridge_and_stop_passthrough(request: Request) -> Any:
    bridge = request.app.state.bridge
    pt = getattr(request.app.state, "passthrough", None)
    if pt is not None and getattr(pt, "active", False):
        await pt.stop()
    if not getattr(bridge, "connected", False):
        try:
            await bridge.connect()
        except Exception as exc:
            raise HTTPException(
                status_code=409,
                detail=f"bridge not connected: {exc}",
            ) from exc
    return bridge


async def _start_graph(request: Request, graph_name: str) -> dict[str, Any]:
    await _ensure_bridge_and_stop_passthrough(request)
    runs = request.app.state.runs
    try:
        snap = await runs.start(graph_name)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("console start %s failed", graph_name)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "run": snap, "graph": graph_name}


@router.get("/status")
async def console_status(request: Request) -> dict[str, Any]:
    bridge = request.app.state.bridge
    runs = request.app.state.runs
    bstat = bridge.status() if hasattr(bridge, "status") else {}
    rstat = runs.snapshot()
    return {
        "ok": True,
        "bridge": {
            "connected": bool(getattr(bridge, "connected", False)),
            "connecting": bool(bstat.get("connecting")),
            "host": bstat.get("host"),
            "user": bstat.get("user"),
            "connect_error": bstat.get("connect_error"),
            "stale": bstat.get("stale"),
        },
        "run": rstat,
        "actions": {
            "rest_graph": REST_GRAPH,
            "open_fortnite_graph": OPEN_FORTNITE_GRAPH,
        },
    }


@router.post("/wake")
async def console_wake(request: Request) -> dict[str, Any]:
    """Wake / reconnect Remote Play (Session.start uses wakeup=True)."""
    bridge = request.app.state.bridge
    pt = getattr(request.app.state, "passthrough", None)
    if pt is not None and getattr(pt, "active", False):
        await pt.stop()

    try:
        if hasattr(bridge, "reconnect"):
            await bridge.reconnect()
        else:
            await bridge.disconnect(reason="console wake")
            await bridge.connect()
    except Exception as exc:
        logger.exception("console wake failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if pt is not None:
        pt.bind_bridge(bridge)
    return {"ok": True, "bridge": bridge.status()}


@router.post("/rest")
async def console_rest(request: Request) -> dict[str, Any]:
    """Run the rest_ps5 graph (Control Center → power → Rest Mode)."""
    return await _start_graph(request, REST_GRAPH)


@router.post("/open-fortnite")
async def console_open_fortnite(request: Request) -> dict[str, Any]:
    """Run open_fortnite (long-PS → seek → OCR Fortnite → CROSS)."""
    return await _start_graph(request, OPEN_FORTNITE_GRAPH)


@router.post("/stop")
async def console_stop(request: Request) -> dict[str, Any]:
    runs = request.app.state.runs
    snap = await runs.stop()
    return {"ok": True, "run": snap}
