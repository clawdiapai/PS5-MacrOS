"""Remote Play session connect / disconnect / standby."""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.config import Settings, settings

logger = logging.getLogger("web2ps5.session")
router = APIRouter(prefix="/api/session", tags=["session"])


class ConnectBody(BaseModel):
    host: str | None = Field(default=None, description="Override WEB2PS5_PS5_HOST")
    user: str | None = Field(default=None, description="Override WEB2PS5_PS5_USER (control)")


class SwitchUserBody(BaseModel):
    """Reconnect Remote Play as a different registered PSN user (control account)."""

    user: str = Field(min_length=1)
    spectator_user: str | None = None
    persist: bool = True


@router.get("")
async def session_status(request: Request) -> dict[str, Any]:
    bridge = request.app.state.bridge
    return {
        "ok": True,
        "bridge": bridge.status(),
        "configured_control": settings.ps5_user,
        "configured_spectator": settings.ps5_spectator_user,
        "note": (
            "To control a profile's game, Remote Play must connect AS that profile. "
            "Use POST /api/session/switch-user if you need to change control."
        ),
    }


async def _rebuild_bridge(request: Request) -> Any:
    from backend.app.bridge import create_bridge
    import backend.app.main as app_main

    old = request.app.state.bridge
    pt = getattr(request.app.state, "passthrough", None)
    if pt is not None and pt.active:
        await pt.stop()
    try:
        await old.disconnect()
    except Exception:
        logger.exception("disconnect before rebuild failed")
        # Ensure PS5 slot is released even if async disconnect failed
        fn = getattr(old, "force_disconnect_sync", None)
        if callable(fn):
            try:
                fn("rebuild fallback")
            except Exception:
                logger.exception("force_disconnect_sync during rebuild failed")

    bridge = create_bridge(settings)
    if settings.auto_connect:
        await bridge.connect()
    request.app.state.bridge = bridge
    request.app.state.frame_holder = bridge.frames
    app_main._shutdown_bridge = bridge  # noqa: SLF001 — keep atexit target current
    if hasattr(request.app.state, "runs") and request.app.state.runs is not None:
        request.app.state.runs._bridge = bridge  # noqa: SLF001
    if pt is not None:
        pt.bind_bridge(bridge)
    return bridge


@router.post("/connect")
async def session_connect(request: Request, body: ConnectBody | None = None) -> dict[str, Any]:
    bridge = request.app.state.bridge
    body = body or ConnectBody()

    if body.user or body.host:
        if body.host:
            os.environ["WEB2PS5_PS5_HOST"] = body.host.strip()
            settings.ps5_host = body.host.strip()
        if body.user:
            os.environ["WEB2PS5_PS5_USER"] = body.user.strip()
            settings.ps5_user = body.user.strip()
        # Rebuild so PyRemotePlayBridge picks up new user/host
        try:
            bridge = await _rebuild_bridge(request)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"ok": True, "bridge": bridge.status(), "rebuilt": True}

    try:
        await bridge.connect()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "bridge": bridge.status(), "rebuilt": False}


@router.post("/switch-user")
async def switch_user(request: Request, body: SwitchUserBody) -> dict[str, Any]:
    """Change control (and optional spectator) then reconnect."""
    os.environ["WEB2PS5_PS5_USER"] = body.user.strip()
    settings.ps5_user = body.user.strip()
    if body.spectator_user is not None:
        os.environ["WEB2PS5_PS5_SPECTATOR_USER"] = body.spectator_user.strip()
        settings.ps5_spectator_user = body.spectator_user.strip()

    if body.persist:
        # merge into .env via Settings rewrite of key fields
        from backend.app.api.setup import ENV_PATH, _write_env

        _write_env(
            {
                "WEB2PS5_PS5_USER": settings.ps5_user,
                "WEB2PS5_PS5_SPECTATOR_USER": settings.ps5_spectator_user,
            }
        )

    try:
        bridge = await _rebuild_bridge(request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "ok": True,
        "control": settings.ps5_user,
        "spectator": settings.ps5_spectator_user,
        "bridge": bridge.status(),
        "env_path": str(ENV_PATH) if body.persist else None,
    }


@router.post("/disconnect")
async def session_disconnect(request: Request) -> dict[str, Any]:
    """Clean disconnect: stop passthrough + run, then tear down RP session."""
    pt = getattr(request.app.state, "passthrough", None)
    runs = getattr(request.app.state, "runs", None)
    if pt is not None and getattr(pt, "active", False):
        await pt.stop()
    if runs is not None and getattr(runs, "snapshot", None):
        try:
            snap = runs.snapshot()
            if snap.get("active"):
                await runs.stop()
        except Exception:
            logger.exception("stop run during disconnect failed")

    bridge = request.app.state.bridge
    await bridge.disconnect(reason="api disconnect")
    return {"ok": True, "bridge": bridge.status()}


@router.post("/reconnect")
async def session_reconnect(request: Request) -> dict[str, Any]:
    """
    Force teardown of any hung session, wait for the PS5 slot to free, reconnect.

    Use this when a previous connection is stuck and a normal connect fails.
    """
    pt = getattr(request.app.state, "passthrough", None)
    runs = getattr(request.app.state, "runs", None)
    if pt is not None and getattr(pt, "active", False):
        await pt.stop()
    if runs is not None:
        try:
            snap = runs.snapshot()
            if snap.get("active"):
                await runs.stop()
        except Exception:
            logger.exception("stop run during reconnect failed")

    bridge = request.app.state.bridge
    try:
        if hasattr(bridge, "reconnect"):
            await bridge.reconnect()
        else:
            await bridge.disconnect(reason="reconnect")
            await bridge.connect()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if pt is not None:
        pt.bind_bridge(bridge)
    return {"ok": True, "bridge": bridge.status()}


@router.post("/standby")
async def session_standby(request: Request) -> dict[str, Any]:
    bridge = request.app.state.bridge
    pt = getattr(request.app.state, "passthrough", None)
    if pt is not None and getattr(pt, "active", False):
        await pt.stop()
    try:
        await bridge.standby()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "bridge": bridge.status()}
