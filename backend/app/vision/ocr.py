"""Optional Tesseract OCR helpers (pytesseract)."""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

import cv2
import numpy as np

logger = logging.getLogger("web2ps5.vision.ocr")

MatchMode = Literal["contains", "equals", "regex"]


class OcrUnavailableError(RuntimeError):
    """Raised when pytesseract or the Tesseract binary is missing."""


def tesseract_status() -> dict[str, Any]:
    from backend.app.vision.tesseract_bootstrap import (
        configure_if_present,
        find_tesseract,
    )

    configure_if_present()
    try:
        import pytesseract
    except ImportError:
        return {
            "ok": False,
            "pytesseract": False,
            "tesseract": False,
            "detail": "pytesseract missing — will auto-pip-install on first OCR use",
        }
    exe = find_tesseract()
    try:
        ver = pytesseract.get_tesseract_version()
        return {
            "ok": True,
            "pytesseract": True,
            "tesseract": True,
            "version": str(ver),
            "cmd": str(exe) if exe else getattr(
                pytesseract.pytesseract, "tesseract_cmd", None
            ),
        }
    except Exception as exc:
        return {
            "ok": False,
            "pytesseract": True,
            "tesseract": False,
            "cmd": str(exe) if exe else None,
            "detail": str(exc),
            "hint": "POST /api/vision/ocr/ensure to download & install locally into tools/tesseract/",
        }


def _crop_roi(
    frame_bgr: np.ndarray, roi: tuple[int, int, int, int] | None
) -> np.ndarray:
    if roi is None:
        return frame_bgr
    x, y, w, h = [int(v) for v in roi]
    fh, fw = frame_bgr.shape[:2]
    x = max(0, min(x, fw - 1))
    y = max(0, min(y, fh - 1))
    w = max(1, min(w, fw - x))
    h = max(1, min(h, fh - y))
    return frame_bgr[y : y + h, x : x + w]


def _preprocess(bgr: np.ndarray, *, invert: bool) -> np.ndarray:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # Upscale small ROIs — Tesseract struggles under ~30px text height
    h, w = gray.shape[:2]
    if max(h, w) < 120:
        scale = max(2, int(160 / max(h, w)))
        gray = cv2.resize(gray, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    if invert:
        thr = cv2.bitwise_not(thr)
    return thr


def normalize_text(s: str) -> str:
    s = (s or "").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n+", " ", s)
    return s.strip()


def read_text(
    frame_bgr: np.ndarray,
    *,
    roi: tuple[int, int, int, int] | None = None,
    lang: str = "eng",
    invert: bool = False,
    psm: int = 6,
    auto_install: bool = True,
) -> str:
    """OCR a frame (optional ROI). Auto-bootstraps Tesseract when needed."""
    from backend.app.vision.tesseract_bootstrap import ensure_tesseract

    boot = ensure_tesseract(install_if_missing=auto_install)
    if not boot.get("ok"):
        raise OcrUnavailableError(boot.get("detail") or "Tesseract unavailable")

    import pytesseract

    crop = _crop_roi(frame_bgr, roi)
    if crop.size == 0:
        return ""
    img = _preprocess(crop, invert=invert)
    config = f"--psm {int(psm)}"
    try:
        raw = pytesseract.image_to_string(img, lang=lang or "eng", config=config)
    except Exception as exc:
        # One retry after forced bootstrap (PATH / cmd may have been stale)
        if auto_install:
            boot2 = ensure_tesseract(install_if_missing=True)
            if boot2.get("ok"):
                try:
                    raw = pytesseract.image_to_string(
                        img, lang=lang or "eng", config=config
                    )
                except Exception as exc2:
                    raise OcrUnavailableError(str(exc2)) from exc2
            else:
                raise OcrUnavailableError(str(exc)) from exc
        else:
            raise OcrUnavailableError(str(exc)) from exc
    return normalize_text(raw)


def text_matches(
    haystack: str,
    expect: str,
    *,
    mode: MatchMode = "contains",
    case_sensitive: bool = False,
) -> bool:
    a = haystack if case_sensitive else haystack.lower()
    b = expect if case_sensitive else expect.lower()
    b = (b or "").strip()
    if not b:
        return bool(a)
    if mode == "equals":
        return a.strip() == b
    if mode == "regex":
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            return re.search(expect, haystack, flags) is not None
        except re.error:
            return False
    # contains (default)
    return b in a


def ocr_check(
    frame_bgr: np.ndarray,
    expect: str,
    *,
    roi: tuple[int, int, int, int] | None = None,
    mode: MatchMode = "contains",
    lang: str = "eng",
    invert: bool = False,
    case_sensitive: bool = False,
    psm: int = 6,
) -> dict[str, Any]:
    text = read_text(frame_bgr, roi=roi, lang=lang, invert=invert, psm=psm)
    matched = text_matches(text, expect, mode=mode, case_sensitive=case_sensitive)
    return {
        "ok": True,
        "matched": matched,
        "text": text,
        "expect": expect,
        "mode": mode,
        "roi": list(roi) if roi else None,
    }
