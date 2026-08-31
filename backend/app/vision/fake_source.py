"""Synthetic PS5-like frame generator for Phase 1 (no Remote Play required)."""

from __future__ import annotations

import threading
import time

import cv2
import numpy as np

from backend.app.vision.frame_holder import AtomicFrameHolder


class FakeFrameSource:
    """
    Background thread that paints a moving HUD into the AtomicFrameHolder.

    Produces canonical BGR frames at ``width``×``height`` and ``fps``.
    Older unread frames are dropped by the holder (latest-only semantics).
    """

    def __init__(
        self,
        holder: AtomicFrameHolder,
        *,
        width: int = 1280,
        height: int = 720,
        fps: float = 30.0,
    ) -> None:
        if width < 16 or height < 16:
            raise ValueError("frame size too small")
        if fps <= 0:
            raise ValueError("fps must be positive")

        self._holder = holder
        self._width = int(width)
        self._height = int(height)
        self._fps = float(fps)
        self._period = 1.0 / self._fps

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_at = 0.0
        self._published = 0

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def published_count(self) -> int:
        return self._published

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def size(self) -> tuple[int, int]:
        return self._width, self._height

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._started_at = time.monotonic()
        self._published = 0
        self._thread = threading.Thread(
            target=self._run,
            name="FakeFrameSource",
            daemon=True,
        )
        self._thread.start()

    def stop(self, join_timeout: float = 2.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=join_timeout)
        self._thread = None

    def _run(self) -> None:
        next_tick = time.monotonic()
        while not self._stop.is_set():
            now = time.monotonic()
            if now < next_tick:
                # Short sleep to keep timing; exit promptly on stop
                self._stop.wait(timeout=min(self._period, next_tick - now))
                continue

            elapsed = now - self._started_at
            frame = self._render(elapsed)
            self._holder.publish(frame, pts=now)
            self._published += 1

            next_tick += self._period
            # If we fell behind, skip ahead so we stay "live"
            if now - next_tick > self._period:
                next_tick = now + self._period

    def _render(self, elapsed: float) -> np.ndarray:
        w, h = self._width, self._height
        frame = np.zeros((h, w, 3), dtype=np.uint8)

        # Dark blue-gray "console" background
        frame[:, :] = (36, 28, 22)

        # Soft scanline band
        band_y = int((elapsed * 80) % h)
        y0 = max(0, band_y - 40)
        y1 = min(h, band_y + 40)
        frame[y0:y1, :] = (48, 38, 30)

        # Moving accent bar (easy template target later)
        bar_w, bar_h = 160, 48
        x = int((elapsed * 220) % (w - bar_w))
        y = h // 2 - bar_h // 2
        cv2.rectangle(frame, (x, y), (x + bar_w, y + bar_h), (80, 180, 255), thickness=-1)
        cv2.putText(
            frame,
            "WEB2PS5",
            (x + 18, y + 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (20, 20, 20),
            2,
            cv2.LINE_AA,
        )

        # HUD clock / resolution stamp
        cv2.putText(
            frame,
            f"FAKE  {w}x{h}  t={elapsed:6.2f}s",
            (24, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (220, 220, 220),
            2,
            cv2.LINE_AA,
        )
        cv2.rectangle(frame, (16, 16), (w - 16, h - 16), (70, 70, 70), 2)

        return frame
