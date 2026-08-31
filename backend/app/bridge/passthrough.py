"""Physical PC DualSense → pyremoteplay Controller (pi2ps5-style low-latency loop)."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

logger = logging.getLogger("web2ps5.passthrough")

# Same SDL layout pi2ps5/capture.py uses for Windows DualSense
_SDL_BUTTON_MAP = {
    0: "CROSS",
    1: "CIRCLE",
    2: "SQUARE",
    3: "TRIANGLE",
    4: "SHARE",
    5: "PS",
    6: "OPTIONS",
    7: "L3",
    8: "R3",
    9: "L1",
    10: "R1",
    11: "UP",
    12: "DOWN",
    13: "LEFT",
    14: "RIGHT",
    15: "TOUCHPAD",
}


class PassThroughService:
    """
    DualSense → Remote Play controller at ~125 Hz (asyncio.sleep(0.008)),
    matching pi2ps5 windows_gamepad_loop — no FeedbackTicker in the path.
    """

    def __init__(self, bridge: Any, *, hz: float = 125.0, deadzone: float = 0.08) -> None:
        self._bridge = bridge
        self._period = 1.0 / max(60.0, float(hz))
        self._deadzone = float(deadzone)
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._pad_index = 0
        self._pad_name = ""
        self._error: str | None = None
        self._frames = 0
        self._ticker_was_running = False
        self._recording = False
        self._record_t0 = 0.0
        self._events: list[dict[str, Any]] = []

    @property
    def active(self) -> bool:
        return self._task is not None and not self._task.done()

    def status(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "pad_index": self._pad_index,
            "pad_name": self._pad_name,
            "frames": self._frames,
            "error": self._error,
            "poll_hz": round(1.0 / self._period, 1),
            "recording": self._recording,
            "event_count": len(self._events),
            "devices": self.list_devices(),
        }

    def start_recording(self) -> None:
        self._events = []
        self._record_t0 = time.monotonic()
        self._recording = True

    def stop_recording(self) -> list[dict[str, Any]]:
        self._recording = False
        return list(self._events)

    def _rec(self, **payload: Any) -> None:
        if not self._recording:
            return
        self._events.append(
            {"t": round(time.monotonic() - self._record_t0, 4), **payload}
        )

    @staticmethod
    def list_devices() -> list[dict[str, Any]]:
        try:
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
            import pygame

            if not pygame.get_init():
                pygame.init()
            if not pygame.joystick.get_init():
                pygame.joystick.init()
            pygame.event.pump()
            out = []
            for i in range(pygame.joystick.get_count()):
                js = pygame.joystick.Joystick(i)
                js.init()
                out.append({"index": i, "name": js.get_name(), "guid": js.get_guid()})
            return out
        except Exception as exc:  # noqa: BLE001
            return [{"error": str(exc)}]

    def bind_bridge(self, bridge: Any) -> None:
        self._bridge = bridge

    def _controller(self):
        ctrl = getattr(self._bridge, "raw_controller", None)
        if callable(ctrl):
            ctrl = ctrl()
        return ctrl

    async def start(
        self,
        pad_index: int = 0,
        *,
        claim_ps_hold_ms: int = 1800,
        open_game: bool = True,
        open_game_delay_ms: int = 900,
        open_game_press_ms: int = 120,
    ) -> dict[str, Any]:
        if self.active:
            return self.status()
        if not getattr(self._bridge, "connected", False):
            raise RuntimeError("bridge not connected — use RP Reconnect first")

        devices = self.list_devices()
        if not devices or devices[0].get("error"):
            raise RuntimeError("No gamepad found. Plug DualSense into the PC (USB preferred).")
        if pad_index < 0 or pad_index >= len(devices):
            raise RuntimeError(f"pad_index {pad_index} out of range ({len(devices)} devices)")

        self._pad_index = pad_index
        self._pad_name = str(devices[pad_index].get("name") or "")
        self._error = None
        self._frames = 0

        # Stop FeedbackTicker so it cannot overwrite sticks/buttons mid-passthrough
        ticker = getattr(self._bridge, "ticker", None)
        self._ticker_was_running = bool(ticker and getattr(ticker, "is_running", False))
        if self._ticker_was_running and ticker is not None:
            await ticker.stop()
            logger.info("FeedbackTicker paused for passthrough")

        if claim_ps_hold_ms > 0:
            await self._claim_controller(claim_ps_hold_ms)

        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="dualsense-passthrough")
        logger.info(
            "passthrough ON pad=%s (%s) @ %.0fHz",
            pad_index,
            self._pad_name,
            1.0 / self._period,
        )

        # After take-over settles, press X (CROSS) to open/resume the highlighted game
        if open_game:
            await self._press_open_game(
                delay_ms=open_game_delay_ms,
                press_ms=open_game_press_ms,
            )

        return self.status()

    async def stop(self) -> dict[str, Any]:
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

        ctrl = self._controller()
        if ctrl is not None:
            try:
                ctrl.stick("left", point=(0.0, 0.0))
                ctrl.stick("right", point=(0.0, 0.0))
            except Exception:
                pass

        # Resume ticker for graph/API control
        ticker = getattr(self._bridge, "ticker", None)
        if self._ticker_was_running and ticker is not None and getattr(self._bridge, "connected", False):
            try:
                await ticker.start()
            except Exception:
                logger.debug("ticker restart failed", exc_info=True)
        self._ticker_was_running = False
        logger.info("passthrough OFF")
        return self.status()

    async def _claim_controller(self, hold_ms: int) -> None:
        ctrl = self._controller()
        if ctrl is None:
            return
        logger.info("claim focus: hold PS %sms", hold_ms)
        try:
            ctrl.button("PS", "press")
            await asyncio.sleep(max(0.4, hold_ms / 1000.0))
            ctrl.button("PS", "release")
            await asyncio.sleep(0.05)
        except Exception:
            logger.debug("PS claim failed", exc_info=True)

    async def _press_open_game(
        self,
        *,
        delay_ms: int = 900,
        press_ms: int = 120,
    ) -> None:
        """Sleep after passthrough claim, then tap CROSS (X) to open current game."""
        ctrl = self._controller()
        if ctrl is None:
            return
        delay_s = max(0.0, float(delay_ms) / 1000.0)
        press_s = max(0.05, float(press_ms) / 1000.0)
        logger.info(
            "open game: sleep %.0fms then CROSS %.0fms",
            delay_s * 1000.0,
            press_s * 1000.0,
        )
        try:
            if delay_s > 0:
                await asyncio.sleep(delay_s)
            ctrl.button("CROSS", "press")
            await asyncio.sleep(press_s)
            ctrl.button("CROSS", "release")
            await asyncio.sleep(0.05)
        except Exception:
            logger.debug("open-game CROSS press failed", exc_info=True)

    async def _run(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame

        if not pygame.get_init():
            pygame.init()
        if not pygame.joystick.get_init():
            pygame.joystick.init()

        js = pygame.joystick.Joystick(self._pad_index)
        js.init()

        last_btn: dict[int, bool] = {}
        last_hat: dict[str, bool] = {}
        last_left = (0.0, 0.0)
        last_right = (0.0, 0.0)
        last_l2 = False
        last_r2 = False
        dz = self._deadzone

        try:
            while not self._stop.is_set():
                ctrl = self._controller()
                if ctrl is None:
                    await asyncio.sleep(0.05)
                    continue

                pygame.event.pump()
                nbtn = js.get_numbuttons()
                naxis = js.get_numaxes()

                for idx, name in _SDL_BUTTON_MAP.items():
                    if idx >= nbtn:
                        continue
                    down = bool(js.get_button(idx))
                    prev = last_btn.get(idx, False)
                    if down != prev:
                        last_btn[idx] = down
                        action = "press" if down else "release"
                        try:
                            ctrl.button(name, action)
                            self._rec(btn=name, action=action)
                        except Exception:
                            pass

                if js.get_numhats() > 0:
                    hx, hy = js.get_hat(0)
                    for key, want in (
                        ("UP", hy == 1),
                        ("DOWN", hy == -1),
                        ("LEFT", hx == -1),
                        ("RIGHT", hx == 1),
                    ):
                        prev = last_hat.get(key, False)
                        if want != prev:
                            last_hat[key] = want
                            action = "press" if want else "release"
                            try:
                                ctrl.button(key, action)
                                self._rec(btn=key, action=action)
                            except Exception:
                                pass

                lx = round(js.get_axis(0), 3) if naxis > 0 else 0.0
                ly = round(js.get_axis(1), 3) if naxis > 1 else 0.0
                rx = round(js.get_axis(2), 3) if naxis > 2 else 0.0
                ry = round(js.get_axis(3), 3) if naxis > 3 else 0.0
                if abs(lx) < dz:
                    lx = 0.0
                if abs(ly) < dz:
                    ly = 0.0
                if abs(rx) < dz:
                    rx = 0.0
                if abs(ry) < dz:
                    ry = 0.0

                if naxis > 4:
                    l2 = js.get_axis(4) > 0.1
                    if l2 != last_l2:
                        last_l2 = l2
                        action = "press" if l2 else "release"
                        try:
                            ctrl.button("L2", action)
                            self._rec(btn="L2", action=action)
                        except Exception:
                            pass
                if naxis > 5:
                    r2 = js.get_axis(5) > 0.1
                    if r2 != last_r2:
                        last_r2 = r2
                        action = "press" if r2 else "release"
                        try:
                            ctrl.button("R2", action)
                            self._rec(btn="R2", action=action)
                        except Exception:
                            pass

                left = (lx, ly)
                if left != last_left:
                    try:
                        ctrl.stick("left", point=left)
                        last_left = left
                        self._rec(stick="left", point=list(left))
                    except Exception:
                        pass
                right = (rx, ry)
                if right != last_right:
                    try:
                        ctrl.stick("right", point=right)
                        last_right = right
                        self._rec(stick="right", point=list(right))
                    except Exception:
                        pass

                self._frames += 1
                await asyncio.sleep(self._period)
        except Exception as exc:  # noqa: BLE001
            self._error = str(exc)
            logger.exception("passthrough loop failed")
