"""Real HardwareBridge — Session path matching working pi2ps5/capture.py."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from pathlib import Path

from backend.app.bridge.commands import InputCommand
from backend.app.bridge.receiver import FrameHolderReceiver
from backend.app.bridge.state import DualSenseState
from backend.app.bridge.ticker import FeedbackTicker, TickRecord
from backend.app.vision.frame_holder import AtomicFrameHolder

logger = logging.getLogger("web2ps5.bridge.pyremoteplay")


def _load_user_profile(user: str | None) -> tuple[str, dict]:
    """Load a user profile dict from ~/.pyremoteplay/.profile.json (pi2ps5 format)."""
    path = Path.home() / ".pyremoteplay" / ".profile.json"
    if not path.is_file():
        raise RuntimeError(f"missing Remote Play profile file: {path}")
    creds = json.loads(path.read_text(encoding="utf-8"))
    if not creds:
        raise RuntimeError("Remote Play profile file is empty — run /setup")
    if user and user in creds:
        return user, creds[user]
    if user and user not in creds:
        logger.warning("user %s not in profiles; falling back to first entry", user)
    name = next(iter(creds.keys()))
    return name, creds[name]


class PyRemotePlayBridge:
    """
    Maps FeedbackTicker DualSenseState → pyremoteplay Controller.

    Connect path mirrors pi2ps5: Session(host, profile, receiver) + Controller,
    with retries — NOT RPDevice.connect() (that auth path resets on modern PS5).
    """

    def __init__(
        self,
        *,
        host: str,
        user: str | None = None,
        spectator_user: str | None = None,
        frame_width: int = 1280,
        frame_height: int = 720,
        feedback_hz: float = 60.0,
        min_press_ms: float = 80.0,
        resolution: str = "720p",
        fps: str = "high",
        quality: str = "default",
        codec: str = "h264",
        log_every_n_ticks: int = 60,
        control_only: bool = False,
        connect_retries: int = 5,
        retry_delay_s: float = 3.0,
    ) -> None:
        if not host:
            raise ValueError("ps5 host is required for pyremoteplay bridge")

        self._host = host
        self._user_pref = user
        self._spectator_user = spectator_user
        self._resolution = resolution
        self._fps = fps
        self._quality = quality
        self._codec = codec
        self._frame_width = frame_width
        self._frame_height = frame_height
        self._log_every = max(1, int(log_every_n_ticks))
        self._control_only = bool(control_only)
        self._connect_retries = max(1, int(connect_retries))
        self._retry_delay_s = float(retry_delay_s)

        self._holder = AtomicFrameHolder()
        # Lower JPEG quality = faster encode on side thread (preview only)
        self._preview_jpeg_quality = 55
        self._receiver = FrameHolderReceiver(
            self._holder,
            width=frame_width,
            height=frame_height,
            preview_jpeg_quality=self._preview_jpeg_quality,
        )
        self._session = None
        self._controller = None
        self._user: str | None = None
        self._connected = False
        self._connecting = False
        self._last_sent = DualSenseState()
        self._tick_log: deque[TickRecord] = deque(maxlen=180)
        self._connect_error: str | None = None

        self._ticker = FeedbackTicker(
            hz=feedback_hz,
            min_press_ms=min_press_ms,
            on_tick=self._on_tick,
            history_size=120,
        )

    @property
    def name(self) -> str:
        return "pyremoteplay"

    @property
    def frames(self) -> AtomicFrameHolder:
        return self._holder

    @property
    def connected(self) -> bool:
        session = self._session
        live = bool(
            session is not None
            and (
                getattr(session, "is_running", False)
                or getattr(session, "is_ready", False)
            )
        )
        return bool(self._connected and live and self._controller is not None)

    @property
    def ticker(self) -> FeedbackTicker:
        return self._ticker

    @property
    def published_count(self) -> int:
        return int(self._receiver.published)

    def raw_controller(self):
        """Direct DualSense target (same as pi2ps5 windows_gamepad_loop)."""
        if not self.connected:
            return None
        return self._controller

    async def connect(self) -> None:
        if self.connected:
            logger.info("already connected")
            return
        if self._connecting:
            raise RuntimeError("connect already in progress")

        self._connecting = True
        try:
            await self.disconnect(reason="pre-connect cleanup")
            await asyncio.sleep(0.5)

            from backend.app.bridge.av_compat import patch_pyremoteplay_av

            patch_pyremoteplay_av()
            from pyremoteplay.controller import Controller
            from pyremoteplay.session import Session

            user_name, profile = _load_user_profile(self._user_pref)
            self._user = user_name
            self._connect_error = None

            # Soft DDP probe only — Rest Mode often won't answer until wakeup
            # (pi2ps5 relies on Session.start(wakeup=True) with RegistKey).
            try:
                from pyremoteplay import RPDevice

                probe = RPDevice(self._host)
                status = await probe.async_get_status() or probe.get_status()
                if status:
                    logger.info(
                        "DDP ok host=%s name=%s on=%s",
                        self._host,
                        status.get("host-name"),
                        probe.is_on,
                    )
                else:
                    logger.warning(
                        "DDP no reply from %s — still trying Session wakeup "
                        "(Rest Mode / sticky RP slot is normal)",
                        self._host,
                    )
            except Exception as exc:
                logger.warning("DDP probe warning: %s — continuing Session start", exc)

            last_err = "unknown"
            for attempt in range(1, self._connect_retries + 1):
                logger.info(
                    "PS5 Session connect %s as %s (attempt %s/%s)",
                    self._host,
                    user_name,
                    attempt,
                    self._connect_retries,
                )
                receiver = None
                if not self._control_only:
                    self._receiver = FrameHolderReceiver(
                        self._holder,
                        width=self._frame_width,
                        height=self._frame_height,
                        preview_jpeg_quality=self._preview_jpeg_quality,
                    )
                    receiver = self._receiver

                session = Session(
                    host=self._host,
                    profile=profile,
                    receiver=receiver,
                    resolution=self._resolution,
                    fps=self._fps,
                    quality=self._quality,
                    codec=self._codec,
                )
                controller = Controller()
                controller.connect(session)
                self._session = session
                self._controller = controller

                try:
                    success = await session.start()
                except Exception as exc:
                    success = False
                    last_err = str(exc)
                    session.error = last_err
                    logger.warning("session.start raised: %s", exc)

                if success and (
                    getattr(session, "is_running", False)
                    or getattr(session, "is_ready", False)
                ):
                    controller.start()
                    await self._ticker.start()
                    self._connected = True
                    self._last_sent = DualSenseState()
                    self._connect_error = None
                    logger.info(
                        "PyRemotePlayBridge connected host=%s user=%s res=%s fps=%s",
                        self._host,
                        user_name,
                        self._resolution,
                        self._fps,
                    )
                    return

                last_err = (
                    getattr(session, "error", None)
                    or getattr(session, "disconnect_reason", None)
                    or last_err
                    or "session start failed"
                )
                logger.warning("attempt %s failed: %s", attempt, last_err)
                self._teardown_session_objects(reason=f"attempt {attempt} failed")

                if attempt < self._connect_retries:
                    busy = "another remote play" in str(last_err).lower()
                    delay = (
                        max(3.0, float(self._retry_delay_s) * 3)
                        if busy
                        else float(self._retry_delay_s)
                    )
                    logger.info(
                        "retrying in %.1fs (clearing previous RP slot%s)…",
                        delay,
                        "; host reported session busy" if busy else "",
                    )
                    await asyncio.sleep(delay)

            self._connect_error = str(last_err)
            raise RuntimeError(
                f"could not connect to PS5 after {self._connect_retries} attempts: {last_err}"
            )
        except Exception:
            await self.disconnect(reason="connect failed")
            raise
        finally:
            self._connecting = False

    def _teardown_session_objects(self, reason: str = "") -> None:
        """Sync teardown — safe from atexit / signal handlers (no await)."""
        controller = self._controller
        session = self._session
        self._controller = None
        self._session = None
        self._connected = False
        if controller is not None:
            try:
                controller.stop()
            except Exception:
                pass
            try:
                controller.disconnect()
            except Exception:
                pass
        if session is not None:
            for meth_name in ("stop", "disconnect", "close"):
                meth = getattr(session, meth_name, None)
                if callable(meth):
                    try:
                        meth()
                        break
                    except Exception:
                        logger.debug(
                            "session.%s failed (%s)", meth_name, reason, exc_info=True
                        )

    def force_disconnect_sync(self, reason: str = "process exit") -> None:
        """Best-effort RP release when the process is dying (Ctrl+C / closed terminal).

        Lifespan ``await disconnect()`` often never runs if the console is killed.
        This path must stay fully synchronous.
        """
        if not self._connected and self._session is None and self._controller is None:
            return
        logger.info("PyRemotePlayBridge force_disconnect_sync (%s)", reason)
        try:
            # FeedbackTicker may expose a sync stop; ignore if not.
            stop = getattr(self._ticker, "stop_sync", None) or getattr(
                self._ticker, "request_stop", None
            )
            if callable(stop):
                stop()
        except Exception:
            pass
        self._teardown_session_objects(reason=reason)
        try:
            self._receiver.close()
        except Exception:
            pass
        try:
            self._holder.clear()
        except Exception:
            pass
        # Brief busy-wait so the UDP teardown can leave the PS5 slot.
        time.sleep(0.4)
        logger.info("PyRemotePlayBridge force_disconnect_sync done")

    async def disconnect(self, reason: str = "requested") -> None:
        logger.info("PyRemotePlayBridge disconnect (%s)", reason)
        try:
            await self._ticker.stop()
        except Exception:
            logger.debug("ticker stop failed", exc_info=True)

        self._teardown_session_objects(reason=reason)

        try:
            self._receiver.close()
        except Exception:
            pass
        self._holder.clear()
        self._receiver = FrameHolderReceiver(
            self._holder,
            width=self._frame_width,
            height=self._frame_height,
            preview_jpeg_quality=self._preview_jpeg_quality,
        )
        self._last_sent = DualSenseState()
        # Give the PS5 time to free the Remote Play slot (sticky after hard kills).
        await asyncio.sleep(0.75)
        logger.info("PyRemotePlayBridge disconnected clean")

    async def reconnect(self) -> None:
        await self.disconnect(reason="reconnect")
        # Sticky "Another Remote Play session" often needs a longer cool-down.
        await asyncio.sleep(max(2.0, float(self._retry_delay_s) * 2))
        await self.connect()

    async def standby(self) -> None:
        session = self._session
        if session is not None and getattr(session, "is_running", False):
            try:
                session.standby()
            except Exception:
                logger.debug("session.standby failed", exc_info=True)
            await self.disconnect(reason="standby")
            return
        raise RuntimeError("cannot standby without an active session")

    async def ensure_connected(self) -> None:
        if not self.connected:
            await self.connect()

    async def apply(self, command: InputCommand) -> None:
        if not self.connected:
            raise RuntimeError("bridge is not connected")
        await self._ticker.apply(command)

    def get_state(self) -> DualSenseState:
        return self._ticker.snapshot()

    def status(self) -> dict:
        snap = self.get_state()
        frame = self._holder.get_latest()
        session = self._session
        running = bool(getattr(session, "is_running", False)) if session else False
        return {
            "name": self.name,
            "connected": self.connected,
            "connecting": self._connecting,
            "stale": bool(self._connected and session is not None and not running),
            "host": self._host,
            "user": self._user,
            "user_pref": self._user_pref,
            "spectator_user": self._spectator_user,
            "connect_error": self._connect_error,
            "feedback_hz": self._ticker.hz,
            "tick_count": self._ticker.tick_count,
            "ticker_running": self._ticker.is_running,
            "session_ready": bool(getattr(session, "is_ready", False)) if session else False,
            "session_running": running,
            "video": {
                "running": self.connected and not self._control_only,
                "fps": None,
                "published": self.published_count,
                "jpeg_encoded": getattr(self._receiver, "jpeg_encoded", 0),
                "dropped_jpeg": getattr(self._receiver, "dropped_jpeg", 0),
                "latest_id": frame.frame_id if frame else 0,
                "age_ms": (
                    round((time.monotonic() - frame.pts) * 1000.0, 1)
                    if frame is not None
                    else None
                ),
                "width": frame.width if frame else self._frame_width,
                "height": frame.height if frame else self._frame_height,
                "receiver_error": self._receiver.last_error,
                "control_only": self._control_only,
            },
            "pad": snap.to_dict(),
        }

    def recent_ticks(self, limit: int = 10) -> list[dict]:
        records = list(self._tick_log)[-limit:]
        return [{"tick": r.tick, "pts": r.pts, "state": r.state} for r in records]

    def _on_tick(self, state: DualSenseState, tick: int) -> None:
        self._tick_log.append(
            TickRecord(tick=tick, pts=time.monotonic(), state=state.to_dict())
        )
        if tick % self._log_every == 0:
            logger.debug("feedback tick=%s pad=%s", tick, state.to_dict())

        ctrl = self._controller
        if ctrl is None or not self.connected:
            if self._connected and (
                self._session is None or not getattr(self._session, "is_running", False)
            ):
                self._connected = False
                logger.warning("Remote Play session dropped; marking disconnected")
            self._last_sent = state.snapshot()
            return

        prev = self._last_sent
        for btn in state.buttons - prev.buttons:
            try:
                ctrl.button(btn.value.upper(), "press")
            except Exception:
                pass
        for btn in prev.buttons - state.buttons:
            try:
                ctrl.button(btn.value.upper(), "release")
            except Exception:
                pass
        if (state.lx, state.ly) != (prev.lx, prev.ly):
            try:
                ctrl.stick("left", point=(state.lx, state.ly))
            except Exception:
                pass
        if (state.rx, state.ry) != (prev.rx, prev.ry):
            try:
                ctrl.stick("right", point=(state.rx, state.ry))
            except Exception:
                pass
        self._last_sent = state.snapshot()
