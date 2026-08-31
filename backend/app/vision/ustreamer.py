"""Pull MJPEG from ustreamer (HDMI capture) into AtomicFrameHolder."""

from __future__ import annotations

import asyncio
import logging

import cv2
import httpx
import numpy as np

from backend.app.vision.frame_holder import AtomicFrameHolder

logger = logging.getLogger("web2ps5.vision.ustreamer")


class UstreamerFrameSource:
    """
    Background async reader for ustreamer HTTP MJPEG.

    Typical URL: http://<pi-ip>:8080/stream
    """

    def __init__(
        self,
        holder: AtomicFrameHolder,
        url: str,
        *,
        width: int = 1280,
        height: int = 720,
    ) -> None:
        if not url:
            raise ValueError("ustreamer url is required")
        self._holder = holder
        self._url = url.strip()
        self._width = int(width)
        self._height = int(height)
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._published = 0
        self._error: str | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def published_count(self) -> int:
        return self._published

    @property
    def url(self) -> str:
        return self._url

    @property
    def last_error(self) -> str | None:
        return self._error

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="ustreamer-ingest")

    async def stop(self) -> None:
        self._stop.set()
        task = self._task
        if task is not None:
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except asyncio.TimeoutError:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._task = None

    async def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                await self._stream_once()
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self._error = str(exc)
                logger.warning("ustreamer ingest error: %s — retry in %.1fs", exc, backoff)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=backoff)
                    break
                except asyncio.TimeoutError:
                    backoff = min(10.0, backoff * 1.5)

    async def _stream_once(self) -> None:
        timeout = httpx.Timeout(connect=5.0, read=None, write=10.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("GET", self._url) as resp:
                resp.raise_for_status()
                self._error = None
                logger.info("ustreamer connected %s", self._url)
                buf = b""
                async for chunk in resp.aiter_bytes():
                    if self._stop.is_set():
                        return
                    if not chunk:
                        continue
                    buf += chunk
                    # Keep buffer bounded
                    if len(buf) > 8_000_000:
                        buf = buf[-2_000_000:]
                    while True:
                        soi = buf.find(b"\xff\xd8")
                        eoi = buf.find(b"\xff\xd9", soi + 2) if soi >= 0 else -1
                        if soi < 0 or eoi < 0:
                            break
                        jpg = buf[soi : eoi + 2]
                        buf = buf[eoi + 2 :]
                        frame = await asyncio.to_thread(self._decode, jpg)
                        if frame is not None:
                            self._holder.publish(frame)
                            self._published += 1

    def _decode(self, jpg: bytes) -> np.ndarray | None:
        arr = np.frombuffer(jpg, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        h, w = img.shape[:2]
        if w != self._width or h != self._height:
            img = cv2.resize(img, (self._width, self._height), interpolation=cv2.INTER_AREA)
        return img
