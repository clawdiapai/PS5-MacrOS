"""OCR target CRUD — Freeze + ROI box + expect text."""

from __future__ import annotations

import base64
from typing import Any

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.app.vision.ocr_targets import (
    delete_ocr_target,
    full_frame_path,
    list_ocr_targets,
    load_ocr_meta,
    preview_png_path,
    save_ocr_target,
    update_ocr_from_full,
    validate_ocr_id,
)

router = APIRouter(prefix="/api/ocr-targets", tags=["ocr-targets"])


class SaveOcrBody(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    x: int
    y: int
    w: int = Field(ge=1)
    h: int = Field(ge=1)
    expect: str = ""
    mode: str = "contains"
    lang: str = "eng"
    invert: bool = False
    case_sensitive: bool = False
    psm: int = Field(default=6, ge=0, le=13)
    note: str = ""
    frame_b64: str | None = None


class UpdateOcrBody(BaseModel):
    x: int
    y: int
    w: int = Field(ge=1)
    h: int = Field(ge=1)
    expect: str | None = None
    mode: str | None = None
    lang: str | None = None
    invert: bool | None = None
    case_sensitive: bool | None = None
    psm: int | None = None
    note: str | None = None
    frame_b64: str | None = None


def _decode_frame_b64(data: str) -> np.ndarray:
    raw = data.split(",", 1)[-1]
    buf = base64.b64decode(raw)
    arr = np.frombuffer(buf, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("could not decode frame_b64")
    return frame


@router.get("")
async def ocr_list() -> dict[str, Any]:
    return {"ok": True, "targets": list_ocr_targets()}


@router.get("/{ocr_id}")
async def ocr_get(ocr_id: str) -> dict[str, Any]:
    try:
        validate_ocr_id(ocr_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    meta = load_ocr_meta(ocr_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="ocr target not found")
    meta["full_url"] = (
        f"/api/ocr-targets/{ocr_id}/full.jpg" if meta.get("has_full") else None
    )
    meta["preview_url"] = f"/api/ocr-targets/{ocr_id}/image"
    return {"ok": True, "target": meta}


@router.post("")
async def ocr_create(request: Request, body: SaveOcrBody) -> dict[str, Any]:
    if body.frame_b64:
        try:
            frame = _decode_frame_b64(body.frame_b64)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        snap = request.app.state.frame_holder.get_latest()
        if snap is None:
            raise HTTPException(status_code=409, detail="no live frame")
        frame = snap.image
    try:
        meta = save_ocr_target(
            body.id,
            frame,
            x=body.x,
            y=body.y,
            w=body.w,
            h=body.h,
            expect=body.expect,
            mode=body.mode,
            lang=body.lang,
            invert=body.invert,
            case_sensitive=body.case_sensitive,
            psm=body.psm,
            note=body.note,
            save_full=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "target": meta, "has_full": meta.get("has_full")}


@router.put("/{ocr_id}")
async def ocr_update(ocr_id: str, body: UpdateOcrBody) -> dict[str, Any]:
    try:
        validate_ocr_id(ocr_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    frame = None
    if body.frame_b64:
        try:
            frame = _decode_frame_b64(body.frame_b64)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        meta = update_ocr_from_full(
            ocr_id,
            x=body.x,
            y=body.y,
            w=body.w,
            h=body.h,
            expect=body.expect,
            mode=body.mode,
            lang=body.lang,
            invert=body.invert,
            case_sensitive=body.case_sensitive,
            psm=body.psm,
            note=body.note,
            frame_bgr=frame,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "target": meta, "has_full": meta.get("has_full")}


@router.delete("/{ocr_id}")
async def ocr_delete(ocr_id: str) -> dict[str, Any]:
    try:
        validate_ocr_id(ocr_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ok = delete_ocr_target(ocr_id)
    if not ok:
        raise HTTPException(status_code=404, detail="ocr target not found")
    return {"ok": True, "deleted": ocr_id}


@router.get("/{ocr_id}/image")
async def ocr_image(ocr_id: str) -> Response:
    try:
        validate_ocr_id(ocr_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    path = preview_png_path(ocr_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="preview not found")
    return Response(content=path.read_bytes(), media_type="image/png")


@router.get("/{ocr_id}/full.jpg")
async def ocr_full(ocr_id: str) -> Response:
    try:
        validate_ocr_id(ocr_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    path = full_frame_path(ocr_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="full frame not found")
    return Response(content=path.read_bytes(), media_type="image/jpeg")
