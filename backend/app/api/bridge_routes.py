"""Hardware bridge probe endpoints."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.bridge import (
    DualSenseButton,
    Neutral,
    PressButton,
    SetButton,
    SetStick,
)

router = APIRouter(prefix="/api/bridge", tags=["bridge"])


class BridgeCommandBody(BaseModel):
    type: Literal["press", "set_button", "set_stick", "neutral"]
    button: str | None = None
    down: bool | None = None
    duration_ms: float = Field(default=80.0, ge=1.0)
    stick: Literal["left", "right"] | None = None
    x: float = 0.0
    y: float = 0.0


@router.get("/state")
async def bridge_state(request: Request) -> dict[str, Any]:
    bridge = request.app.state.bridge
    return {
        "ok": True,
        **bridge.status(),
        "recent_ticks": bridge.recent_ticks(5),
    }


@router.post("/command")
async def bridge_command(request: Request, body: BridgeCommandBody) -> dict[str, Any]:
    bridge = request.app.state.bridge
    if not bridge.connected:
        raise HTTPException(status_code=409, detail="bridge not connected")

    try:
        cmd = _parse_command(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await bridge.apply(cmd)
    return {
        "ok": True,
        "applied": body.model_dump(),
        "pad": bridge.get_state().to_dict(),
        "tick_count": bridge.ticker.tick_count,
    }


def _parse_command(body: BridgeCommandBody):
    if body.type == "neutral":
        return Neutral()

    if body.type == "press":
        if not body.button:
            raise ValueError("press requires button")
        return PressButton(
            button=DualSenseButton(body.button),
            duration_ms=body.duration_ms,
        )

    if body.type == "set_button":
        if not body.button or body.down is None:
            raise ValueError("set_button requires button and down")
        return SetButton(button=DualSenseButton(body.button), down=body.down)

    if body.type == "set_stick":
        if not body.stick:
            raise ValueError("set_stick requires stick")
        return SetStick(stick=body.stick, x=body.x, y=body.y)

    raise ValueError(f"unsupported type: {body.type}")
