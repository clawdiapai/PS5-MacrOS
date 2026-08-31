"""Tiny frame fingerprints for 'did the screen change?' navigation checks."""

from __future__ import annotations

import numpy as np


def frame_fingerprint(frame_bgr: np.ndarray, *, size: int = 64) -> np.ndarray:
    """Downscale grayscale fingerprint for cheap comparisons."""
    import cv2

    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (size, size), interpolation=cv2.INTER_AREA)
    return small.astype(np.float32)


def frames_differ(
    a: np.ndarray,
    b: np.ndarray,
    *,
    threshold: float = 0.02,
) -> tuple[bool, float]:
    """
    Return (changed, score) where score is mean abs diff in 0..1.
    ``changed`` is True when score >= threshold.
    """
    if a.shape != b.shape:
        return True, 1.0
    score = float(np.mean(np.abs(a - b)) / 255.0)
    return score >= float(threshold), score
