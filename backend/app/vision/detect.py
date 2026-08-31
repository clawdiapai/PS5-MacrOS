"""Live anchor detection helpers (template match → overlay boxes)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from backend.app.config import settings
from backend.app.vision.anchors import list_anchor_template_paths, load_anchor_meta
from backend.app.vision.template_match import (
    ensure_demo_bar_anchor,
    load_template,
    match_template,
)

# When matching without an explicit ROI, search near each authored crop so a
# template cannot "win" on a similar icon elsewhere on the screen.
_DEFAULT_CROP_PAD_PX = 72


def _padded_crop_roi(
    crop: dict[str, Any],
    *,
    pad: int = _DEFAULT_CROP_PAD_PX,
) -> tuple[int, int, int, int] | None:
    try:
        x = int(crop["x"])
        y = int(crop["y"])
        w = int(crop["w"])
        h = int(crop["h"])
    except (KeyError, TypeError, ValueError):
        return None
    # Ignore placeholder 1×1 scaffold crops
    if w < 8 or h < 8:
        return None
    return (x - pad, y - pad, w + 2 * pad, h + 2 * pad)


def _roi_for_target(
    meta: dict[str, Any] | None,
    index: int,
    *,
    explicit_roi: tuple[int, int, int, int] | None,
) -> tuple[int, int, int, int] | None:
    """Prefer node ROI; else padded authored crop; else meta.search_roi; else full frame."""
    if explicit_roi is not None:
        return explicit_roi
    crops = (meta or {}).get("crops")
    if isinstance(crops, list) and index < len(crops) and isinstance(crops[index], dict):
        local = _padded_crop_roi(crops[index])
        if local is not None:
            return local
    search = (meta or {}).get("search_roi")
    if isinstance(search, (list, tuple)) and len(search) == 4:
        try:
            return (int(search[0]), int(search[1]), int(search[2]), int(search[3]))
        except (TypeError, ValueError):
            pass
    return None


def detect_anchor_on_frame(
    frame_bgr: np.ndarray,
    anchor_id: str,
    *,
    threshold: float | None = None,
    match_mode: str | None = None,
    match_count: int | None = None,
    roi: tuple[int, int, int, int] | None = None,
) -> dict[str, Any]:
    """
    Match all templates for ``anchor_id`` on ``frame_bgr``.

    Search region (per target):
      1. Explicit ``roi`` from the caller/node (whole-anchor override)
      2. Else padded box around that target's authored crop (location-bound)
      3. Else ``meta.search_roi``
      4. Else full frame

    Returns overlay-friendly ``boxes`` with x,y,w,h + score/hit per target.
    """
    anchors = settings.anchors_dir
    if anchor_id == "demo_bar":
        ensure_demo_bar_anchor(anchors)
        paths = [Path(anchors) / "demo_bar.png"]
        meta: dict[str, Any] | None = None
    else:
        paths = list_anchor_template_paths(anchor_id)
        meta = load_anchor_meta(anchor_id)

    if not paths:
        return {
            "ok": False,
            "anchor_id": anchor_id,
            "error": "anchor not found",
            "boxes": [],
            "matched": False,
            "hits": 0,
            "target_count": 0,
        }

    thr = float(
        threshold
        if threshold is not None
        else (meta or {}).get("threshold", 0.7)
    )
    mode = str(
        match_mode
        or (meta or {}).get("match_mode")
        or "all"
    ).lower()
    need = int(
        match_count
        if match_count is not None
        else (meta or {}).get("match_count")
        or 1
    )
    need = max(1, need)

    fh, fw = frame_bgr.shape[:2]
    boxes: list[dict[str, Any]] = []
    scores: list[float] = []
    hits = 0
    used_rois: list[list[int] | None] = []

    for i, path in enumerate(paths):
        template = load_template(path)
        if template is None:
            continue
        th, tw = template.shape[:2]
        target_roi = _roi_for_target(meta, i, explicit_roi=roi)
        result = match_template(
            frame_bgr, template, threshold=thr, roi=target_roi
        )
        score = float(result.score)
        scores.append(score)
        hit = bool(result.matched)
        if hit:
            hits += 1
        loc = result.loc
        used_rois.append(list(target_roi) if target_roi else None)
        boxes.append(
            {
                "index": i,
                "x": int(loc[0]) if loc else 0,
                "y": int(loc[1]) if loc else 0,
                "w": int(tw),
                "h": int(th),
                "score": round(score, 4),
                "hit": hit,
                "found": loc is not None,
                "search_roi": list(target_roi) if target_roi else None,
            }
        )

    if not scores:
        return {
            "ok": False,
            "anchor_id": anchor_id,
            "error": "templates missing",
            "boxes": [],
            "matched": False,
            "hits": 0,
            "target_count": 0,
            "frame_size": {"width": fw, "height": fh},
        }

    if mode == "any":
        matched = hits >= 1
    elif mode == "at_least":
        matched = hits >= min(need, len(scores))
    else:
        matched = hits >= len(scores)

    score = min(scores) if mode == "all" else max(scores)
    return {
        "ok": True,
        "anchor_id": anchor_id,
        "score": round(float(score), 4),
        "scores": [round(s, 4) for s in scores],
        "hits": hits,
        "target_count": len(scores),
        "match_mode": mode,
        "match_count": need,
        "matched": matched,
        "threshold": thr,
        "boxes": boxes,
        "frame_size": {"width": fw, "height": fh},
        "loc": [boxes[0]["x"], boxes[0]["y"]] if boxes else None,
        "locs": [[b["x"], b["y"]] for b in boxes],
        "search_rois": used_rois,
        "location_bound": any(r is not None for r in used_rois),
    }
