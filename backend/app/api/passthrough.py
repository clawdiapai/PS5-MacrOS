"""DualSense PC → Remote Play passthrough control."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/passthrough", tags=["passthrough"])


class StartBody(BaseModel):
    pad_index: int = Field(default=0, ge=0, le=7)
    claim_ps_hold_ms: int = Field(
        default=2200,
        ge=0,
        le=5000,
        description="Hold remote PS button this long to take over from local pad (0=skip)",
    )
    open_game: bool = Field(
        default=True,
        description="After passthrough activates, sleep then press X (CROSS) to open current game",
    )
    open_game_delay_ms: int = Field(
        default=900,
        ge=0,
        le=5000,
        description="Settle delay after take-over before pressing X",
    )
    open_game_press_ms: int = Field(
        default=120,
        ge=50,
        le=1000,
        description="How long to hold CROSS when opening the game",
    )


@router.get("")
async def passthrough_status(request: Request) -> dict[str, Any]:
    pt = request.app.state.passthrough
    bridge = request.app.state.bridge
    st = bridge.status() if hasattr(bridge, "status") else {}
    return {
        "ok": True,
        **pt.status(),
        "session_user": st.get("user"),
        "spectator_user": st.get("spectator_user"),
        "hint": (
            "Remote Play session user should match the PS5 profile you want to control. "
            "Passthrough holds PS briefly to take over, then sleeps and presses X to open the game."
        ),
    }


@router.post("/start")
async def passthrough_start(request: Request, body: StartBody | None = None) -> dict[str, Any]:
    pt = request.app.state.passthrough
    body = body or StartBody()
    # Rebind in case setup swapped the bridge
    pt.bind_bridge(request.app.state.bridge)
    try:
        status = await pt.start(
            pad_index=body.pad_index,
            claim_ps_hold_ms=body.claim_ps_hold_ms,
            open_game=body.open_game,
            open_game_delay_ms=body.open_game_delay_ms,
            open_game_press_ms=body.open_game_press_ms,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **status}


@router.post("/stop")
async def passthrough_stop(request: Request) -> dict[str, Any]:
    pt = request.app.state.passthrough
    status = await pt.stop()
    return {"ok": True, **status}
