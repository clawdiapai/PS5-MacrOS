"""Named OCR targets — Freeze full frame + ROI box + expect text (like anchors)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from backend.app.config import settings

_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$")


def ocr_dir() -> Path:
    settings.ocr_dir.mkdir(parents=True, exist_ok=True)
    return settings.ocr_dir


def validate_ocr_id(ocr_id: str) -> str:
    if not _SAFE.match(ocr_id):
        raise ValueError("ocr id must match [A-Za-z0-9][A-Za-z0-9_-]{0,63}")
    return ocr_id


def full_frame_path(ocr_id: str) -> Path:
    return ocr_dir() / f"{ocr_id}_full.jpg"


def preview_png_path(ocr_id: str) -> Path:
    return ocr_dir() / f"{ocr_id}.png"


def meta_path(ocr_id: str) -> Path:
    return ocr_dir() / f"{ocr_id}.json"


def list_ocr_targets() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted(ocr_dir().glob("*.json")):
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta = {"id": path.stem}
        oid = str(meta.get("id") or path.stem)
        meta["id"] = oid
        meta["has_full"] = full_frame_path(oid).is_file()
        meta["has_preview"] = preview_png_path(oid).is_file()
        out.append(meta)
    return out


def load_ocr_meta(ocr_id: str) -> dict[str, Any] | None:
    ocr_id = validate_ocr_id(ocr_id)
    path = meta_path(ocr_id)
    if not path.is_file():
        return None
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    meta["id"] = ocr_id
    meta["has_full"] = full_frame_path(ocr_id).is_file()
    meta["has_preview"] = preview_png_path(ocr_id).is_file()
    return meta


def _clamp(
    frame_bgr: np.ndarray, x: int, y: int, w: int, h: int
) -> tuple[int, int, int, int]:
    fh, fw = frame_bgr.shape[:2]
    x = max(0, min(int(x), fw - 1))
    y = max(0, min(int(y), fh - 1))
    w = max(1, min(int(w), fw - x))
    h = max(1, min(int(h), fh - y))
    return x, y, w, h


def save_ocr_target(
    ocr_id: str,
    frame_bgr: np.ndarray,
    *,
    x: int,
    y: int,
    w: int,
    h: int,
    expect: str = "",
    mode: str = "contains",
    lang: str = "eng",
    invert: bool = False,
    case_sensitive: bool = False,
    psm: int = 6,
    note: str = "",
    save_full: bool = True,
) -> dict[str, Any]:
    ocr_id = validate_ocr_id(ocr_id)
    mode = str(mode or "contains").lower().strip()
    if mode not in ("contains", "equals", "regex"):
        raise ValueError("mode must be contains|equals|regex")

    x, y, w, h = _clamp(frame_bgr, x, y, w, h)
    crop = frame_bgr[y : y + h, x : x + w].copy()
    cv2.imwrite(str(preview_png_path(ocr_id)), crop)

    full_saved = False
    if save_full:
        ok, buf = cv2.imencode(
            ".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 90]
        )
        if ok:
            full_frame_path(ocr_id).write_bytes(buf.tobytes())
            full_saved = True

    fh, fw = frame_bgr.shape[:2]
    meta = {
        "id": ocr_id,
        "expect": str(expect or ""),
        "mode": mode,
        "lang": str(lang or "eng"),
        "invert": bool(invert),
        "case_sensitive": bool(case_sensitive),
        "psm": int(psm),
        "roi": {"x": x, "y": y, "w": w, "h": h},
        "crop": {"x": x, "y": y, "w": w, "h": h},
        "crops": [{"x": x, "y": y, "w": w, "h": h}],
        "frame_size": {"width": fw, "height": fh},
        "full": f"{ocr_id}_full.jpg" if full_saved else None,
        "has_full": full_saved,
        "note": note,
    }
    meta_path(ocr_id).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def update_ocr_from_full(
    ocr_id: str,
    *,
    x: int,
    y: int,
    w: int,
    h: int,
    expect: str | None = None,
    mode: str | None = None,
    lang: str | None = None,
    invert: bool | None = None,
    case_sensitive: bool | None = None,
    psm: int | None = None,
    note: str | None = None,
    frame_bgr: np.ndarray | None = None,
) -> dict[str, Any]:
    ocr_id = validate_ocr_id(ocr_id)
    existing = load_ocr_meta(ocr_id) or {}
    if frame_bgr is None:
        full = full_frame_path(ocr_id)
        if not full.is_file():
            raise FileNotFoundError(f"no full frame for {ocr_id}")
        frame_bgr = cv2.imread(str(full), cv2.IMREAD_COLOR)
        if frame_bgr is None:
            raise ValueError("could not read full frame")
        save_full = False
    else:
        save_full = True

    return save_ocr_target(
        ocr_id,
        frame_bgr,
        x=x,
        y=y,
        w=w,
        h=h,
        expect=expect if expect is not None else str(existing.get("expect") or ""),
        mode=mode if mode is not None else str(existing.get("mode") or "contains"),
        lang=lang if lang is not None else str(existing.get("lang") or "eng"),
        invert=bool(invert if invert is not None else existing.get("invert", False)),
        case_sensitive=bool(
            case_sensitive
            if case_sensitive is not None
            else existing.get("case_sensitive", False)
        ),
        psm=int(psm if psm is not None else existing.get("psm") or 6),
        note=note if note is not None else str(existing.get("note") or ""),
        save_full=save_full,
    )


def delete_ocr_target(ocr_id: str) -> bool:
    ocr_id = validate_ocr_id(ocr_id)
    existed = False
    for p in (meta_path(ocr_id), preview_png_path(ocr_id), full_frame_path(ocr_id)):
        if p.is_file():
            p.unlink()
            existed = True
    return existed


def roi_tuple_from_meta(meta: dict[str, Any] | None) -> tuple[int, int, int, int] | None:
    if not meta:
        return None
    roi = meta.get("roi") or meta.get("crop")
    if isinstance(roi, dict):
        try:
            return int(roi["x"]), int(roi["y"]), int(roi["w"]), int(roi["h"])
        except (KeyError, TypeError, ValueError):
            return None
    return None
