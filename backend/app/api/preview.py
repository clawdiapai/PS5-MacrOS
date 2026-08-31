"""MJPEG preview — prefer pre-encoded JPEGs from the receiver (low latency)."""

from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator

import cv2
import numpy as np
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from backend.app.config import settings
from backend.app.vision.frame_holder import AtomicFrameHolder

router = APIRouter(tags=["preview"])


def _encode_jpeg(image, quality: int) -> bytes:
    ok, buf = cv2.imencode(
        ".jpg",
        image,
        [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)],
    )
    if not ok:
        raise RuntimeError("jpeg encode failed")
    return buf.tobytes()


def _placeholder_bgr(message: str, detail: str = "") -> np.ndarray:
    w, h = settings.frame_width, settings.frame_height
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = (28, 24, 20)
    cv2.putText(img, "Web2PS5", (40, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (180, 180, 180), 2)
    cv2.putText(img, message[:80], (40, 160), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (100, 180, 255), 2)
    if detail:
        y = 220
        for line in detail.split("\n")[:6]:
            cv2.putText(img, line[:90], (40, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (140, 140, 140), 1)
            y += 36
    return img


def _status_message(request: Request) -> tuple[str, str]:
    bridge = getattr(request.app.state, "bridge", None)
    if bridge is None:
        return "No bridge", "Server still starting…"
    try:
        st: dict[str, Any] = bridge.status()
    except Exception as exc:  # noqa: BLE001
        return "Bridge error", str(exc)
    if st.get("connecting"):
        return "Connecting to PS5…", f"host={st.get('host')} user={st.get('user_pref')}"
    if st.get("connected"):
        pub = (st.get("video") or {}).get("published", 0)
        if not pub:
            err = (st.get("video") or {}).get("receiver_error")
            return "Connected — waiting for video", err or "decoder has not published yet"
        return "Streaming", ""
    err = st.get("connect_error") or "not connected"
    return "Remote Play not connected", f"{err}\nhost={st.get('host')} · RP Reconnect"


def _encode_preview_jpeg(image, quality: int) -> bytes:
    """Fallback encode — downscale so we never stall the MJPEG loop."""
    h, w = image.shape[:2]
    if w > 960:
        image = cv2.resize(image, (960, int(h * 960 / w)), interpolation=cv2.INTER_AREA)
    return _encode_jpeg(image, quality)


async def _mjpeg_frames(request: Request, holder: AtomicFrameHolder) -> AsyncIterator[bytes]:
    # ~30 FPS; never wait long for a JPEG — prefer live over perfect
    period = 1.0 / max(1.0, min(60.0, settings.preview_fps if settings.preview_fps >= 20 else 30.0))
    quality = settings.preview_jpeg_quality
    prev_id = 0
    boundary = b"--frame\r\n"
    last_placeholder = 0.0

    while True:
        if await request.is_disconnected():
            break
        loop_start = time.monotonic()

        # Short wait for side-thread JPEG; fall back quickly to latest BGR
        got = await asyncio.to_thread(holder.wait_newer_jpeg, prev_id, min(period, 0.02))
        if got is not None and got[0] > prev_id:
            frame_id, jpg = got
            prev_id = frame_id
            header = (
                b"Content-Type: image/jpeg\r\n"
                + f"Content-Length: {len(jpg)}\r\n".encode("ascii")
                + b"X-Frame-Id: "
                + str(frame_id).encode("ascii")
                + b"\r\n\r\n"
            )
            yield boundary + header + jpg + b"\r\n"
        else:
            snap = await asyncio.to_thread(lambda: holder.get_latest(copy=False))
            if snap is not None and snap.frame_id > prev_id:
                prev_id = snap.frame_id
                # Prefer any cached jpeg for this-or-newer id
                cached = await asyncio.to_thread(holder.get_latest_jpeg)
                if cached is not None and cached[0] >= prev_id:
                    prev_id = cached[0]
                    jpg = cached[1]
                else:
                    jpg = await asyncio.to_thread(
                        _encode_preview_jpeg, snap.image, quality
                    )
                header = (
                    b"Content-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(jpg)}\r\n".encode("ascii")
                    + b"X-Frame-Id: "
                    + str(prev_id).encode("ascii")
                    + b"\r\n\r\n"
                )
                yield boundary + header + jpg + b"\r\n"
            else:
                now = time.monotonic()
                if now - last_placeholder >= 0.5:
                    last_placeholder = now
                    msg, detail = _status_message(request)
                    jpg = await asyncio.to_thread(
                        _encode_jpeg, _placeholder_bgr(msg, detail), quality
                    )
                    header = (
                        b"Content-Type: image/jpeg\r\n"
                        + f"Content-Length: {len(jpg)}\r\n".encode("ascii")
                        + b"X-Frame-Id: 0\r\n\r\n"
                    )
                    yield boundary + header + jpg + b"\r\n"

        elapsed = time.monotonic() - loop_start
        if elapsed < period:
            await asyncio.sleep(period - elapsed)


@router.get("/api/preview/mjpeg")
async def mjpeg_preview(request: Request) -> StreamingResponse:
    holder: AtomicFrameHolder = request.app.state.frame_holder
    return StreamingResponse(
        _mjpeg_frames(request, holder),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
        },
    )
