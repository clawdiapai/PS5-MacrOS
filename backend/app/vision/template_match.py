"""OpenCV template matching helpers (always call via asyncio.to_thread)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class MatchResult:
    score: float
    matched: bool
    loc: tuple[int, int] | None


def match_template(
    image_bgr: np.ndarray,
    template_bgr: np.ndarray,
    *,
    threshold: float = 0.7,
    roi: tuple[int, int, int, int] | None = None,
) -> MatchResult:
    if image_bgr is None or template_bgr is None:
        return MatchResult(score=0.0, matched=False, loc=None)

    ox = oy = 0
    search = image_bgr
    if roi is not None:
        x, y, w, h = roi
        fh, fw = image_bgr.shape[:2]
        x = max(0, min(int(x), fw - 1))
        y = max(0, min(int(y), fh - 1))
        w = max(1, min(int(w), fw - x))
        h = max(1, min(int(h), fh - y))
        search = image_bgr[y : y + h, x : x + w]
        ox, oy = x, y

    if template_bgr.shape[0] > search.shape[0] or template_bgr.shape[1] > search.shape[1]:
        return MatchResult(score=0.0, matched=False, loc=None)

    img_g = cv2.cvtColor(search, cv2.COLOR_BGR2GRAY)
    tpl_g = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
    result = cv2.matchTemplate(img_g, tpl_g, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    score = float(max_val)
    return MatchResult(
        score=score,
        matched=score >= float(threshold),
        loc=(int(max_loc[0]) + ox, int(max_loc[1]) + oy),
    )


def load_template(path: Path) -> np.ndarray | None:
    if not path.is_file():
        return None
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    return img


def ensure_demo_bar_anchor(anchors_dir: Path) -> Path:
    """
    Bake a small orange 'WEB2PS5' bar patch matching FakeFrameSource colors.

    Used by vis.check_state in Phase 1 without Anchor Studio.
    """
    anchors_dir.mkdir(parents=True, exist_ok=True)
    path = anchors_dir / "demo_bar.png"
    if path.is_file():
        return path

    bar_w, bar_h = 160, 48
    patch = np.zeros((bar_h, bar_w, 3), dtype=np.uint8)
    patch[:, :] = (80, 180, 255)  # BGR orange used by FakeFrameSource
    cv2.putText(
        patch,
        "WEB2PS5",
        (18, 32),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (20, 20, 20),
        2,
        cv2.LINE_AA,
    )
    cv2.imwrite(str(path), patch)
    meta = anchors_dir / "demo_bar.json"
    meta.write_text(
        '{"id":"demo_bar","threshold":0.7,"note":"auto-generated for Phase 1"}',
        encoding="utf-8",
    )
    return path
