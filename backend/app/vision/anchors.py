"""Anchor asset helpers (PNG + JSON metadata)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from backend.app.config import settings

_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$")


def anchors_dir() -> Path:
    settings.anchors_dir.mkdir(parents=True, exist_ok=True)
    return settings.anchors_dir


def validate_anchor_id(anchor_id: str) -> str:
    if not _SAFE.match(anchor_id):
        raise ValueError("anchor id must match [A-Za-z0-9][A-Za-z0-9_-]{0,63}")
    return anchor_id


def full_frame_path(anchor_id: str) -> Path:
    """Full screenshot saved alongside each tiny crop (for later retargeting)."""
    return anchors_dir() / f"{anchor_id}_full.jpg"


def _is_primary_anchor_png(stem: str) -> bool:
    """Skip companion files: *_full, *_t0, *_t1, …"""
    if stem.endswith("_full"):
        return False
    if "_t" in stem:
        # foo_t0 / foo_t12
        tail = stem.rsplit("_t", 1)[-1]
        if tail.isdigit():
            return False
    return True


def target_png_path(anchor_id: str, index: int) -> Path:
    if index <= 0:
        return anchors_dir() / f"{anchor_id}.png"
    return anchors_dir() / f"{anchor_id}_t{index}.png"


def list_anchors() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for png in sorted(anchors_dir().glob("*.png")):
        if not _is_primary_anchor_png(png.stem):
            continue
        meta_path = png.with_suffix(".json")
        meta: dict[str, Any] = {"id": png.stem}
        if meta_path.is_file():
            try:
                meta.update(json.loads(meta_path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                pass
        meta["id"] = png.stem
        meta["has_png"] = True
        meta["has_full"] = full_frame_path(png.stem).is_file()
        crops = meta.get("crops")
        meta["target_count"] = len(crops) if isinstance(crops, list) and crops else 1
        out.append(meta)
    return out


def _clamp_crop(
    frame_bgr: np.ndarray, x: int, y: int, w: int, h: int
) -> tuple[int, int, int, int]:
    fh, fw = frame_bgr.shape[:2]
    x = max(0, min(int(x), fw - 1))
    y = max(0, min(int(y), fh - 1))
    w = max(1, min(int(w), fw - x))
    h = max(1, min(int(h), fh - y))
    return x, y, w, h


def save_anchor_crop(
    anchor_id: str,
    frame_bgr: np.ndarray,
    *,
    x: int,
    y: int,
    w: int,
    h: int,
    threshold: float = 0.7,
    note: str = "",
    save_full: bool = True,
    match_mode: str = "all",
    match_count: int = 1,
) -> dict[str, Any]:
    """Save a single-target anchor (compat wrapper)."""
    return save_anchor_targets(
        anchor_id,
        frame_bgr,
        crops=[{"x": x, "y": y, "w": w, "h": h}],
        threshold=threshold,
        note=note,
        save_full=save_full,
        match_mode=match_mode,
        match_count=match_count,
    )


def save_anchor_targets(
    anchor_id: str,
    frame_bgr: np.ndarray,
    *,
    crops: list[dict[str, Any]],
    threshold: float = 0.7,
    note: str = "",
    save_full: bool = True,
    match_mode: str = "all",
    match_count: int = 1,
) -> dict[str, Any]:
    """
    Save one or more crop templates from the same frozen frame.

    Files:
      - ``{id}.png``           first target (backward compatible)
      - ``{id}_t1.png`` …      extra targets
      - ``{id}_full.jpg``      full screenshot for later retargeting
      - ``{id}.json``          crops + match_mode + match_count
    """
    anchor_id = validate_anchor_id(anchor_id)
    if not crops:
        raise ValueError("at least one crop target is required")

    mode = str(match_mode or "all").lower().strip()
    if mode not in ("all", "any", "at_least"):
        raise ValueError("match_mode must be all|any|at_least")
    need = max(1, int(match_count))

    fh, fw = frame_bgr.shape[:2]
    normalized: list[dict[str, int]] = []
    for i, raw in enumerate(crops):
        x, y, w, h = _clamp_crop(
            frame_bgr,
            int(raw["x"]),
            int(raw["y"]),
            int(raw["w"]),
            int(raw["h"]),
        )
        crop = frame_bgr[y : y + h, x : x + w].copy()
        path = target_png_path(anchor_id, i)
        cv2.imwrite(str(path), crop)
        normalized.append({"x": x, "y": y, "w": w, "h": h})

    # Remove stale extra target PNGs from a previous save with more crops
    for stale in anchors_dir().glob(f"{anchor_id}_t*.png"):
        tail = stale.stem.rsplit("_t", 1)[-1]
        if tail.isdigit() and int(tail) >= len(normalized):
            stale.unlink()

    full_name = f"{anchor_id}_full.jpg"
    full_saved = False
    if save_full:
        ok, buf = cv2.imencode(
            ".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 90]
        )
        if ok:
            full_frame_path(anchor_id).write_bytes(buf.tobytes())
            full_saved = True

    existing = load_anchor_meta(anchor_id) or {}
    # Retake / save with a full frame clears LEGACY import flag
    legacy = False if full_saved else bool(existing.get("legacy"))
    meta = {
        "id": anchor_id,
        "threshold": float(threshold),
        "crop": normalized[0],  # compat
        "crops": normalized,
        "target_count": len(normalized),
        "match_mode": mode,
        "match_count": need,
        "frame_size": {"width": fw, "height": fh},
        "full": full_name if full_saved else None,
        "has_full": full_saved,
        "legacy": legacy,
        "note": note,
    }
    # Preserve import provenance fields when re-saving
    for key in ("source", "pi2ps5_state", "pi2ps5_name", "pi2ps5_priority", "pi2ps5_templates", "search_roi"):
        if key in existing and key not in meta:
            meta[key] = existing[key]
    (anchors_dir() / f"{anchor_id}.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    return meta


def load_anchor_meta(anchor_id: str) -> dict[str, Any] | None:
    path = anchors_dir() / f"{anchor_id}.json"
    if not path.is_file():
        return None
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    meta["has_full"] = full_frame_path(anchor_id).is_file()
    crops = meta.get("crops")
    if not isinstance(crops, list) or not crops:
        crop = meta.get("crop")
        if isinstance(crop, dict):
            meta["crops"] = [crop]
            meta["target_count"] = 1
        else:
            meta["crops"] = []
            meta["target_count"] = 0
    else:
        meta["target_count"] = len(crops)
    if "match_mode" not in meta:
        meta["match_mode"] = "all"
    if "match_count" not in meta:
        meta["match_count"] = 1
    return meta


def update_anchor_from_full(
    anchor_id: str,
    *,
    crops: list[dict[str, Any]],
    threshold: float | None = None,
    match_mode: str | None = None,
    match_count: int | None = None,
    note: str | None = None,
    frame_bgr: np.ndarray | None = None,
) -> dict[str, Any]:
    """
    Re-cut templates for an existing anchor.

    Uses ``frame_bgr`` if given, else the stored ``{id}_full.jpg``.
    Keeps / refreshes the full screenshot.
    """
    anchor_id = validate_anchor_id(anchor_id)
    existing = load_anchor_meta(anchor_id) or {}

    if frame_bgr is None:
        full = full_frame_path(anchor_id)
        if not full.is_file():
            raise FileNotFoundError(f"no full frame for {anchor_id}")
        frame_bgr = cv2.imread(str(full), cv2.IMREAD_COLOR)
        if frame_bgr is None:
            raise ValueError("could not read full frame")
        save_full = False  # already on disk
    else:
        save_full = True

    return save_anchor_targets(
        anchor_id,
        frame_bgr,
        crops=crops,
        threshold=float(
            threshold if threshold is not None else existing.get("threshold", 0.7)
        ),
        note=note if note is not None else str(existing.get("note") or ""),
        save_full=save_full,
        match_mode=str(
            match_mode
            if match_mode is not None
            else existing.get("match_mode")
            or "all"
        ),
        match_count=int(
            match_count
            if match_count is not None
            else existing.get("match_count")
            or 1
        ),
    )


def list_anchor_template_paths(anchor_id: str) -> list[Path]:
    """Ordered template PNG paths for an anchor (multi-target aware)."""
    anchor_id = validate_anchor_id(anchor_id)
    meta = load_anchor_meta(anchor_id)
    paths: list[Path] = []
    if meta and isinstance(meta.get("crops"), list) and meta["crops"]:
        for i in range(len(meta["crops"])):
            p = target_png_path(anchor_id, i)
            if p.is_file():
                paths.append(p)
    if not paths:
        primary = anchors_dir() / f"{anchor_id}.png"
        if primary.is_file():
            paths.append(primary)
    return paths


def delete_anchor(anchor_id: str) -> bool:
    anchor_id = validate_anchor_id(anchor_id)
    png = anchors_dir() / f"{anchor_id}.png"
    meta = anchors_dir() / f"{anchor_id}.json"
    full = full_frame_path(anchor_id)
    extras = list(anchors_dir().glob(f"{anchor_id}_t*.png"))
    existed = png.is_file() or meta.is_file() or full.is_file() or bool(extras)
    if png.is_file():
        png.unlink()
    if meta.is_file():
        meta.unlink()
    if full.is_file():
        full.unlink()
    for p in extras:
        p.unlink()
    return existed


def parse_roi(raw: Any) -> tuple[int, int, int, int] | None:
    """Accept [x,y,w,h] or {x,y,w,h} or 'x,y,w,h'."""
    if raw is None:
        return None
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) != 4:
            return None
        raw = [int(float(p)) for p in parts]
    if isinstance(raw, dict):
        return int(raw["x"]), int(raw["y"]), int(raw["w"]), int(raw["h"])
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        return int(raw[0]), int(raw[1]), int(raw[2]), int(raw[3])
    return None
