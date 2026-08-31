"""Latest-frame ring buffer (size=1) for tear-safe vision ingest."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class FrameSnapshot:
    """Newest frame. ``image`` is a copy unless obtained via get_latest(copy=False)."""

    frame_id: int
    pts: float
    width: int
    height: int
    image: np.ndarray  # BGR uint8


class AtomicFrameHolder:
    """
    Size-1 latest-frame holder.

    publish(..., copy=False) takes ownership of a contiguous buffer (no extra memcpy).
    Preview can encode under the lock with copy=False to avoid a second full-frame copy.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._frame_id: int = 0
        self._pts: float = 0.0
        self._image: np.ndarray | None = None
        self._jpeg: bytes | None = None  # optional pre-encoded preview JPEG
        self._jpeg_id: int = 0  # frame_id the jpeg was encoded from

    @property
    def latest_id(self) -> int:
        with self._lock:
            return self._frame_id

    def clear(self) -> None:
        with self._cond:
            self._frame_id = 0
            self._pts = 0.0
            self._image = None
            self._jpeg = None
            self._jpeg_id = 0
            self._cond.notify_all()

    def publish(
        self,
        image: np.ndarray,
        pts: float | None = None,
        *,
        copy: bool = True,
        jpeg: bytes | None = None,
    ) -> int:
        """Store newest frame. Set copy=False if ``image`` is exclusively owned."""
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError(f"expected HxWx3 BGR frame, got shape={image.shape}")
        if image.dtype != np.uint8:
            raise ValueError(f"expected uint8 frame, got dtype={image.dtype}")

        owned = (
            np.ascontiguousarray(image)
            if not copy and image.flags["C_CONTIGUOUS"]
            else np.ascontiguousarray(image.copy())
        )
        stamp = time.monotonic() if pts is None else float(pts)

        with self._cond:
            self._frame_id += 1
            self._pts = stamp
            self._image = owned
            if jpeg is not None:
                self._jpeg = jpeg
                self._jpeg_id = self._frame_id
            # else keep prior jpeg (may be 1–2 frames stale) so preview never blocks
            frame_id = self._frame_id
            self._cond.notify_all()
            return frame_id

    def get_latest(self, *, copy: bool = True) -> FrameSnapshot | None:
        with self._lock:
            if self._image is None or self._frame_id == 0:
                return None
            return self._snapshot_unlocked(copy=copy)

    def set_jpeg(self, frame_id: int, jpeg: bytes) -> bool:
        """Attach preview JPEG if it is not older than what we already have."""
        with self._lock:
            if frame_id < self._jpeg_id:
                return False
            # Accept even if a newer BGR already arrived — still fresher preview
            if frame_id < self._frame_id - 3:
                return False
            self._jpeg = jpeg
            self._jpeg_id = frame_id
            self._cond.notify_all()
            return True

    def get_latest_jpeg(self) -> tuple[int, bytes] | None:
        """Return (jpeg_frame_id, jpeg_bytes) if a pre-encoded preview exists."""
        with self._lock:
            if self._jpeg is None or self._jpeg_id == 0:
                return None
            return self._jpeg_id, self._jpeg

    def wait_newer(
        self,
        prev_id: int,
        timeout: float | None = None,
        *,
        copy: bool = True,
    ) -> FrameSnapshot | None:
        deadline = None if timeout is None else time.monotonic() + timeout

        with self._cond:
            while self._frame_id <= prev_id:
                if deadline is None:
                    self._cond.wait()
                else:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return None
                    self._cond.wait(timeout=remaining)
                if self._image is None or self._frame_id == 0:
                    if deadline is not None and time.monotonic() >= deadline:
                        return None
            if self._image is None:
                return None
            return self._snapshot_unlocked(copy=copy)

    def wait_newer_jpeg(
        self,
        prev_id: int,
        timeout: float | None = None,
    ) -> tuple[int, bytes] | None:
        """Wait until a JPEG newer than prev_id is available (by jpeg_id)."""
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._cond:
            while self._jpeg is None or self._jpeg_id <= prev_id:
                if deadline is None:
                    self._cond.wait()
                else:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return None
                    self._cond.wait(timeout=remaining)
                if self._frame_id == 0 and self._jpeg is None:
                    if deadline is not None and time.monotonic() >= deadline:
                        return None
            if self._jpeg is None:
                return None
            return self._jpeg_id, self._jpeg

    def _snapshot_unlocked(self, *, copy: bool = True) -> FrameSnapshot:
        assert self._image is not None
        h, w = self._image.shape[:2]
        img = (
            np.ascontiguousarray(self._image.copy())
            if copy
            else self._image
        )
        return FrameSnapshot(
            frame_id=self._frame_id,
            pts=self._pts,
            width=w,
            height=h,
            image=img,
        )
