"""Anchor CRUD + crop/edit from freeze or stored full frame."""

from __future__ import annotations

import asyncio
import base64
from typing import Any

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.app.config import settings
from backend.app.vision.anchors import (
    delete_anchor,
    full_frame_path,
    list_anchors,
    load_anchor_meta,
    save_anchor_targets,
    update_anchor_from_full,
    validate_anchor_id,
)
from backend.app.vision.template_match import ensure_demo_bar_anchor

router = APIRouter(prefix="/api/anchors", tags=["anchors"])


class CropRect(BaseModel):
    x: int
    y: int
    w: int = Field(ge=1)
    h: int = Field(ge=1)


class CropBody(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    x: int | None = None
    y: int | None = None
    w: int | None = Field(default=None, ge=1)
    h: int | None = Field(default=None, ge=1)
    crops: list[CropRect] | None = None
    threshold: float = Field(default=0.7, ge=0.05, le=1.0)
    note: str = ""
    match_mode: str = Field(default="all")
    match_count: int = Field(default=1, ge=1, le=32)
    frame_b64: str | None = None


class UpdateBody(BaseModel):
    crops: list[CropRect] = Field(min_length=1)
    threshold: float | None = Field(default=None, ge=0.05, le=1.0)
    match_mode: str | None = None
    match_count: int | None = Field(default=None, ge=1, le=32)
    note: str | None = None
    frame_b64: str | None = None


class DetectBody(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    threshold: float | None = Field(default=None, ge=0.05, le=1.0)
    match_mode: str | None = None
    match_count: int | None = Field(default=None, ge=1, le=32)


def _decode_frame_b64(raw: str) -> np.ndarray:
    s = raw.strip()
    if "," in s and s.lower().startswith("data:"):
        s = s.split(",", 1)[1]
    try:
        data = base64.b64decode(s, validate=False)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"invalid frame_b64: {exc}") from exc
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("could not decode frame_b64 as image")
    return img


@router.get("")
async def anchors_list() -> dict[str, Any]:
    ensure_demo_bar_anchor(settings.anchors_dir)
    return {"ok": True, "anchors": list_anchors()}


# Static paths BEFORE /{anchor_id} so they are not captured as ids
@router.get("/snapshot.jpg")
async def live_snapshot(request: Request) -> Response:
    holder = request.app.state.frame_holder
    snap = holder.get_latest()
    if snap is None:
        raise HTTPException(status_code=409, detail="no live frame")
    ok, buf = cv2.imencode(".jpg", snap.image, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        raise HTTPException(status_code=500, detail="encode failed")
    return Response(
        content=buf.tobytes(),
        media_type="image/jpeg",
        headers={"X-Frame-Id": str(snap.frame_id)},
    )


@router.post("/crop")
async def anchors_crop(request: Request, body: CropBody) -> dict[str, Any]:
    if body.frame_b64:
        try:
            frame = _decode_frame_b64(body.frame_b64)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        frame_id = None
    else:
        holder = request.app.state.frame_holder
        snap = holder.get_latest()
        if snap is None:
            raise HTTPException(status_code=409, detail="no live frame")
        frame = snap.image
        frame_id = snap.frame_id

    if body.crops:
        crops = [c.model_dump() for c in body.crops]
    elif (
        body.x is not None
        and body.y is not None
        and body.w is not None
        and body.h is not None
    ):
        crops = [{"x": body.x, "y": body.y, "w": body.w, "h": body.h}]
    else:
        raise HTTPException(status_code=400, detail="provide crops[] or x,y,w,h")

    try:
        meta = save_anchor_targets(
            body.id,
            frame,
            crops=crops,
            threshold=body.threshold,
            note=body.note,
            save_full=True,
            match_mode=body.match_mode,
            match_count=body.match_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "anchor": meta,
        "frame_id": frame_id,
        "has_full": bool(meta.get("has_full")),
        "target_count": meta.get("target_count", len(crops)),
        "match_mode": meta.get("match_mode"),
        "match_count": meta.get("match_count"),
        "full_url": f"/api/anchors/{meta['id']}/full.jpg" if meta.get("has_full") else None,
    }


@router.post("/detect")
async def anchors_detect(request: Request, body: DetectBody) -> dict[str, Any]:
    from backend.app.vision.detect import detect_anchor_on_frame

    try:
        validate_anchor_id(body.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    holder = request.app.state.frame_holder
    snap = holder.get_latest()
    if snap is None:
        raise HTTPException(status_code=409, detail="no live frame")

    result = await asyncio.to_thread(
        detect_anchor_on_frame,
        snap.image,
        body.id,
        threshold=body.threshold,
        match_mode=body.match_mode,
        match_count=body.match_count,
    )
    result["frame_id"] = snap.frame_id
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error") or "detect failed")
    return result


@router.get("/{anchor_id}/image")
async def anchor_image(anchor_id: str) -> Response:
    try:
        validate_anchor_id(anchor_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if anchor_id == "demo_bar":
        ensure_demo_bar_anchor(settings.anchors_dir)
    path = settings.anchors_dir / f"{anchor_id}.png"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="anchor not found")
    return Response(content=path.read_bytes(), media_type="image/png")


@router.get("/{anchor_id}/full.jpg")
async def anchor_full_frame(anchor_id: str) -> Response:
    try:
        validate_anchor_id(anchor_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    path = full_frame_path(anchor_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="full frame not found")
    return Response(content=path.read_bytes(), media_type="image/jpeg")


@router.get("/{anchor_id}")
async def anchor_get(anchor_id: str) -> dict[str, Any]:
    try:
        validate_anchor_id(anchor_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if anchor_id == "demo_bar":
        ensure_demo_bar_anchor(settings.anchors_dir)
    meta = load_anchor_meta(anchor_id)
    if meta is None and not (settings.anchors_dir / f"{anchor_id}.png").is_file():
        raise HTTPException(status_code=404, detail="anchor not found")
    if meta is None:
        meta = {
            "id": anchor_id,
            "crops": [],
            "has_full": full_frame_path(anchor_id).is_file(),
        }
    meta["full_url"] = (
        f"/api/anchors/{anchor_id}/full.jpg" if meta.get("has_full") else None
    )
    meta["crop_url"] = f"/api/anchors/{anchor_id}/image"
    return {"ok": True, "anchor": meta}


@router.put("/{anchor_id}")
async def anchor_update(anchor_id: str, body: UpdateBody) -> dict[str, Any]:
    try:
        validate_anchor_id(anchor_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    frame = None
    if body.frame_b64:
        try:
            frame = _decode_frame_b64(body.frame_b64)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        meta = update_anchor_from_full(
            anchor_id,
            crops=[c.model_dump() for c in body.crops],
            threshold=body.threshold,
            match_mode=body.match_mode,
            match_count=body.match_count,
            note=body.note,
            frame_bgr=frame,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "ok": True,
        "anchor": meta,
        "has_full": bool(meta.get("has_full")),
        "full_url": f"/api/anchors/{meta['id']}/full.jpg" if meta.get("has_full") else None,
    }


@router.delete("/{anchor_id}")
async def anchors_delete(anchor_id: str) -> dict[str, Any]:
    try:
        existed = delete_anchor(anchor_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not existed:
        raise HTTPException(status_code=404, detail="anchor not found")
    return {"ok": True, "deleted": anchor_id}
