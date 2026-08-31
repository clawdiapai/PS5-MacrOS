"""Macro record / playback — DualSense event timelines for ds/macro_block nodes."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.macros import (
    delete_macro,
    list_macros,
    load_macro,
    normalize_macro_events,
    save_macro,
    validate_name,
)

router = APIRouter(prefix="/api/macros", tags=["macros"])


class SaveMacroBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    events: list[dict[str, Any]] = Field(default_factory=list)
    keyframes: list[dict[str, Any]] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class RecordStartBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    ensure_passthrough: bool = True
    pad_index: int = 0


@router.get("")
async def macros_list() -> dict[str, Any]:
    return {"ok": True, "macros": list_macros()}


@router.get("/{name}")
async def macros_get(name: str) -> dict[str, Any]:
    try:
        doc = load_macro(name)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "macro": doc}


@router.put("/{name}")
async def macros_put(name: str, body: SaveMacroBody) -> dict[str, Any]:
    if body.name != name:
        raise HTTPException(status_code=400, detail="name mismatch")
    try:
        path = save_macro(
            name,
            body.keyframes,
            body.meta,
            events=body.events,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "name": name, "events": len(body.events), "path": str(path)}


@router.delete("/{name}")
async def macros_delete(name: str) -> dict[str, Any]:
    try:
        validate_name(name)
        delete_macro(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "deleted": name}


@router.post("/record/start")
async def record_start(request: Request, body: RecordStartBody) -> dict[str, Any]:
    """
    Start recording DualSense press/stick events via passthrough.

    Turns passthrough ON if needed, then captures every button/stick change
    until /record/stop.
    """
    bridge = request.app.state.bridge
    pt = request.app.state.passthrough
    if not bridge.connected:
        raise HTTPException(status_code=409, detail="Remote Play not connected")
    try:
        validate_name(body.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    pt.bind_bridge(bridge)
    if body.ensure_passthrough and not pt.active:
        try:
            await pt.start(pad_index=body.pad_index, claim_ps_hold_ms=1200)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not pt.active:
        raise HTTPException(
            status_code=409,
            detail="passthrough must be ON to record (enable Pass-through or set ensure_passthrough)",
        )

    pt.start_recording()
    return {
        "ok": True,
        "recording": True,
        "name": body.name,
        "passthrough": pt.status(),
        "hint": "Play your sequence on the DualSense, then Stop on the node / Stop Rec",
    }


class RecordStopBody(BaseModel):
    name: str = Field(default="demo", min_length=1, max_length=64)
    normalize: bool = True
    gap_ms: float = Field(default=700.0, ge=0, le=5000)
    press_ms: float = Field(default=100.0, ge=50, le=1000)


@router.post("/record/stop")
async def record_stop_active(
    request: Request,
    body: RecordStopBody | None = None,
    name: str | None = None,
    normalize: bool = True,
) -> dict[str, Any]:
    """Stop recording and return events (also saves to data/macros/{name}.json)."""
    pt = request.app.state.passthrough
    if body is not None:
        name = body.name
        normalize = body.normalize
        gap_ms = body.gap_ms
        press_ms = body.press_ms
    else:
        name = name or "demo"
        gap_ms = 700.0
        press_ms = 100.0

    try:
        validate_name(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not pt.status().get("recording"):
        raise HTTPException(status_code=409, detail="not currently recording")

    raw = pt.stop_recording()
    events = (
        normalize_macro_events(raw, gap_ms=gap_ms, press_ms=press_ms)
        if normalize
        else raw
    )
    path = save_macro(
        name,
        keyframes=[],
        meta={
            "source": "passthrough_events",
            "saved_at": time.time(),
            "raw_count": len(raw),
            "count": len(events),
            "normalized": bool(normalize),
            "gap_ms": gap_ms,
            "press_ms": press_ms,
        },
        events=events,
    )
    return {
        "ok": True,
        "recording": False,
        "name": name,
        "events": events,
        "raw_count": len(raw),
        "count": len(events),
        "normalized": bool(normalize),
        "path": str(path),
    }


@router.post("/record/stop/{name}")
async def record_stop_named(
    request: Request,
    name: str,
    normalize: bool = True,
    gap_ms: float = 700.0,
    press_ms: float = 100.0,
) -> dict[str, Any]:
    return await record_stop_active(
        request,
        body=RecordStopBody(
            name=name, normalize=normalize, gap_ms=gap_ms, press_ms=press_ms
        ),
    )


class NormalizeBody(BaseModel):
    name: str = Field(default="demo", min_length=1, max_length=64)
    events: list[dict[str, Any]] = Field(default_factory=list)
    keyframes: list[dict[str, Any]] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
    gap_ms: float = Field(default=700.0, ge=0, le=5000)
    press_ms: float = Field(default=100.0, ge=50, le=1000)


@router.post("/normalize")
async def normalize_existing(body: NormalizeBody) -> dict[str, Any]:
    """Normalize an events list (for re-processing a node without re-recording)."""
    gap_ms = float(body.meta.get("gap_ms", body.gap_ms) if body.meta else body.gap_ms)
    press_ms = float(
        body.meta.get("press_ms", body.press_ms) if body.meta else body.press_ms
    )
    events = normalize_macro_events(body.events, gap_ms=gap_ms, press_ms=press_ms)
    return {
        "ok": True,
        "events": events,
        "count": len(events),
        "normalized": True,
        "gap_ms": gap_ms,
        "press_ms": press_ms,
    }
