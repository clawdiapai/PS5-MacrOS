"""Fake HardwareBridge — synthetic frames + FeedbackTicker logging (no UDP)."""

from __future__ import annotations

import logging
import time
from collections import deque

from backend.app.bridge.commands import InputCommand
from backend.app.bridge.state import DualSenseState
from backend.app.bridge.ticker import FeedbackTicker, TickRecord
from backend.app.vision.fake_source import FakeFrameSource
from backend.app.vision.frame_holder import AtomicFrameHolder

logger = logging.getLogger("web2ps5.bridge.fake")


class FakeHardwareBridge:
    """
    Phase 1 stand-in for pyremoteplay.

    Owns AtomicFrameHolder + FakeFrameSource + FeedbackTicker.
    Each tick logs DualSenseState (debug) and keeps a short history for the API.
    """

    def __init__(
        self,
        *,
        frame_width: int = 1280,
        frame_height: int = 720,
        fake_fps: float = 30.0,
        feedback_hz: float = 60.0,
        min_press_ms: float = 80.0,
        log_every_n_ticks: int = 60,
    ) -> None:
        self._holder = AtomicFrameHolder()
        self._source = FakeFrameSource(
            self._holder,
            width=frame_width,
            height=frame_height,
            fps=fake_fps,
        )
        self._log_every = max(1, int(log_every_n_ticks))
        self._tick_log: deque[TickRecord] = deque(maxlen=180)
        self._connected = False

        self._ticker = FeedbackTicker(
            hz=feedback_hz,
            min_press_ms=min_press_ms,
            on_tick=self._on_tick,
            history_size=120,
        )

    @property
    def name(self) -> str:
        return "fake"

    @property
    def frames(self) -> AtomicFrameHolder:
        return self._holder

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def source(self) -> FakeFrameSource:
        return self._source

    @property
    def ticker(self) -> FeedbackTicker:
        return self._ticker

    @property
    def published_count(self) -> int:
        return int(self._source.published_count)

    async def connect(self) -> None:
        if self._connected:
            return
        self._source.start()
        await self._ticker.start()
        self._connected = True
        logger.info(
            "FakeHardwareBridge connected (video=%sx%s@%sfps, feedback=%sHz)",
            self._source.size[0],
            self._source.size[1],
            self._source.fps,
            self._ticker.hz,
        )

    def force_disconnect_sync(self, reason: str = "process exit") -> None:
        self._connected = False
        try:
            self._source.stop()
        except Exception:
            pass
        try:
            self._holder.clear()
        except Exception:
            pass
        logger.info("FakeHardwareBridge force_disconnect_sync (%s)", reason)

    async def disconnect(self, reason: str = "requested") -> None:
        if not self._connected and not self._ticker.is_running:
            self._source.stop()
            self._holder.clear()
            return
        await self._ticker.stop()
        self._source.stop()
        self._holder.clear()
        self._connected = False
        logger.info("FakeHardwareBridge disconnected (%s)", reason)

    async def reconnect(self) -> None:
        await self.disconnect(reason="reconnect")
        await self.connect()

    async def standby(self) -> None:
        # No-op for fake; real bridge will issue rest-mode.
        logger.info("FakeHardwareBridge standby (no-op)")

    async def ensure_connected(self) -> None:
        if not self._connected:
            await self.connect()

    async def apply(self, command: InputCommand) -> None:
        if not self._connected:
            raise RuntimeError("bridge is not connected")
        await self._ticker.apply(command)

    def get_state(self) -> DualSenseState:
        return self._ticker.snapshot()

    def status(self) -> dict:
        snap = self.get_state()
        frame = self._holder.get_latest()
        return {
            "name": self.name,
            "connected": self._connected,
            "feedback_hz": self._ticker.hz,
            "tick_count": self._ticker.tick_count,
            "ticker_running": self._ticker.is_running,
            "video": {
                "running": self._source.is_running,
                "fps": self._source.fps,
                "published": self._source.published_count,
                "latest_id": frame.frame_id if frame else 0,
                "width": frame.width if frame else None,
                "height": frame.height if frame else None,
            },
            "pad": snap.to_dict(),
        }

    def recent_ticks(self, limit: int = 10) -> list[dict]:
        records = list(self._tick_log)[-limit:]
        return [
            {"tick": r.tick, "pts": r.pts, "state": r.state}
            for r in records
        ]

    def _on_tick(self, state: DualSenseState, tick: int) -> None:
        self._tick_log.append(
            TickRecord(tick=tick, pts=time.monotonic(), state=state.to_dict())
        )
        if tick % self._log_every == 0:
            logger.debug("feedback tick=%s pad=%s", tick, state.to_dict())
