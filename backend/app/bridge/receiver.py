"""pyremoteplay AVReceiver → AtomicFrameHolder (decode hot-path stays tiny)."""

from __future__ import annotations

import logging
import queue
import threading
import time

import cv2
import numpy as np

from backend.app.vision.frame_holder import AtomicFrameHolder

logger = logging.getLogger("web2ps5.bridge.receiver")

try:
    from pyremoteplay.receiver import AVReceiver
except ImportError:  # pragma: no cover
    AVReceiver = object  # type: ignore[misc,assignment]


class FrameHolderReceiver(AVReceiver):  # type: ignore[misc]
    """
    Decode BGR and publish latest frame.

    CRITICAL for latency: do NOT JPEG-encode on the AV worker thread.
    pyremoteplay's AVHandler queue is huge (5000); any slow handle_video
    backs up packets and produces multi-second preview lag.

    Pattern matches pi2ps5: publish raw BGR immediately; JPEG for MJPEG
    preview is encoded on a drop-frame side worker (queue maxsize=1).
    """

    def __init__(
        self,
        holder: AtomicFrameHolder,
        *,
        width: int = 1280,
        height: int = 720,
        preview_jpeg_quality: int = 55,
    ) -> None:
        super().__init__()
        self._holder = holder
        self._width = int(width)
        self._height = int(height)
        self._jpeg_quality = int(preview_jpeg_quality)
        self.published = 0
        self.jpeg_encoded = 0
        self.dropped_jpeg = 0
        self.last_error: str | None = None
        self._last_publish_mono = 0.0

        # Decode directly to BGR — avoids rgb24→bgr24 reformat on every frame
        try:
            self.video_format = "bgr24"
        except Exception:
            pass
        if hasattr(self, "_video_format"):
            self._video_format = "bgr24"

        self._jpeg_q: queue.Queue = queue.Queue(maxsize=1)
        self._jpeg_stop = threading.Event()
        self._jpeg_thread = threading.Thread(
            target=self._jpeg_worker,
            name="web2ps5-jpeg",
            daemon=True,
        )
        self._jpeg_thread.start()

    def _jpeg_worker(self) -> None:
        while not self._jpeg_stop.is_set():
            try:
                item = self._jpeg_q.get(timeout=0.2)
            except queue.Empty:
                continue
            if item is None:
                break
            frame_id, arr = item
            try:
                # Downscale for preview only — analysis frame stays full-res in holder
                h, w = arr.shape[:2]
                if w > 960:
                    small = cv2.resize(
                        arr, (960, int(h * 960 / w)), interpolation=cv2.INTER_AREA
                    )
                else:
                    small = arr
                ok, buf = cv2.imencode(
                    ".jpg",
                    small,
                    [int(cv2.IMWRITE_JPEG_QUALITY), self._jpeg_quality],
                )
                if ok:
                    self._holder.set_jpeg(frame_id, buf.tobytes())
                    self.jpeg_encoded += 1
            except Exception as exc:  # noqa: BLE001
                logger.debug("jpeg worker failed: %s", exc)

    def handle_video(self, frame) -> None:  # av.VideoFrame
        """Hot path — must stay cheap or AV packet queue balloons."""
        try:
            if hasattr(frame, "to_ndarray"):
                arr = frame.to_ndarray(format="bgr24")
            else:
                arr = np.ascontiguousarray(frame)
            if arr.dtype != np.uint8:
                arr = arr.astype(np.uint8, copy=False)

            h, w = arr.shape[:2]
            if w != self._width or h != self._height:
                arr = cv2.resize(
                    arr, (self._width, self._height), interpolation=cv2.INTER_AREA
                )
            elif not arr.flags["C_CONTIGUOUS"]:
                arr = np.ascontiguousarray(arr)

            # Own the buffer for the holder; JPEG worker gets a separate view/copy
            frame_id = self._holder.publish(arr, copy=False, jpeg=None)
            self.published += 1
            self._last_publish_mono = time.monotonic()
            self.last_error = None

            # Drop-if-busy JPEG (pi2ps5 needs_frame / maxsize=1 pattern)
            try:
                # Shallow copy for encoder so holder can replace image next frame
                self._jpeg_q.put_nowait((frame_id, arr.copy()))
            except queue.Full:
                self.dropped_jpeg += 1
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            logger.debug("handle_video failed: %s", exc)

    def handle_audio(self, frame) -> None:  # noqa: ARG002
        return

    def handle_audio_data(self, buf: bytes) -> None:  # noqa: ARG002
        """Drop audio entirely — avoids PyAV spam + saves decode CPU."""
        return

    def close(self) -> None:
        self._jpeg_stop.set()
        try:
            self._jpeg_q.put_nowait(None)
        except queue.Full:
            try:
                _ = self._jpeg_q.get_nowait()
            except queue.Empty:
                pass
            try:
                self._jpeg_q.put_nowait(None)
            except queue.Full:
                pass
        try:
            super().close()
        except Exception:
            pass
