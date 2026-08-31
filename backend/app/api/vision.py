"""Vision utilities (OCR probe, etc.)."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.vision.anchors import parse_roi
from backend.app.vision.ocr import OcrUnavailableError, ocr_check, tesseract_status

router = APIRouter(prefix="/api/vision", tags=["vision"])


class OcrBody(BaseModel):
    ocr_id: str | None = Field(default=None, max_length=64)
    expect: str = Field(default="", max_length=256)
    mode: Literal["contains", "equals", "regex"] = "contains"
    lang: str = Field(default="eng", max_length=32)
    invert: bool = False
    case_sensitive: bool = False
    psm: int = Field(default=6, ge=0, le=13)
    roi: list[int] | None = Field(
        default=None, description="Optional [x,y,w,h] search region"
    )


@router.get("/ocr/status")
async def ocr_status() -> dict[str, Any]:
    return {"ok": True, **tesseract_status()}


@router.post("/ocr/ensure")
async def ocr_ensure() -> dict[str, Any]:
    """Download/install a local Tesseract into tools/tesseract/ if missing."""
    from backend.app.vision.tesseract_bootstrap import ensure_tesseract

    result = await asyncio.to_thread(ensure_tesseract, install_if_missing=True)
    return {"ok": bool(result.get("ok")), **result}


@router.post("/ocr")
async def ocr_probe(request: Request, body: OcrBody) -> dict[str, Any]:
    from backend.app.vision.ocr_targets import load_ocr_meta, roi_tuple_from_meta

    holder = request.app.state.frame_holder
    snap = holder.get_latest()
    if snap is None:
        raise HTTPException(status_code=409, detail="no live frame")

    meta = load_ocr_meta(body.ocr_id) if body.ocr_id else None
    expect = (body.expect or "").strip() or str((meta or {}).get("expect") or "")
    mode = str((meta or {}).get("mode") or body.mode or "contains")
    lang = str((meta or {}).get("lang") or body.lang or "eng")
    invert = bool((meta or {}).get("invert")) if meta else bool(body.invert)
    case_sensitive = (
        bool((meta or {}).get("case_sensitive"))
        if meta
        else bool(body.case_sensitive)
    )
    psm = int((meta or {}).get("psm") or body.psm or 6)

    roi = parse_roi(body.roi)
    if roi is None:
        roi = roi_tuple_from_meta(meta)

    try:
        result = await asyncio.to_thread(
            ocr_check,
            snap.image,
            expect,
            roi=roi,
            mode=mode,  # type: ignore[arg-type]
            lang=lang,
            invert=invert,
            case_sensitive=case_sensitive,
            psm=psm,
        )
    except OcrUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Overlay-friendly box = the OCR search ROI (hit when text matched)
    boxes: list[dict[str, Any]] = []
    if roi is not None:
        boxes.append(
            {
                "index": 0,
                "x": int(roi[0]),
                "y": int(roi[1]),
                "w": int(roi[2]),
                "h": int(roi[3]),
                "score": 1.0 if result.get("matched") else 0.0,
                "hit": bool(result.get("matched")),
                "found": True,
                "kind": "ocr",
                "label": str(result.get("text") or "")[:48],
                "expect": expect,
            }
        )
    fh, fw = snap.image.shape[:2]
    result["frame_id"] = snap.frame_id
    result["ocr_id"] = body.ocr_id
    result["boxes"] = boxes
    result["hits"] = 1 if result.get("matched") else 0
    result["target_count"] = len(boxes)
    result["frame_size"] = {"width": fw, "height": fh}
    return result
