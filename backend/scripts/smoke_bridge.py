"""Smoke-test FakeHardwareBridge + FeedbackTicker without relying on HTTP alone."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.bridge import (
    DualSenseButton,
    FakeHardwareBridge,
    PressButton,
    SetStick,
)


async def main() -> int:
    bridge = FakeHardwareBridge(
        frame_width=1280,
        frame_height=720,
        fake_fps=30.0,
        feedback_hz=60.0,
        min_press_ms=80.0,
    )
    await bridge.connect()

    try:
        # Video still flowing through the bridge-owned holder
        frame = bridge.frames.wait_newer(0, timeout=2.0)
        if frame is None:
            print("FAIL: no video frame from bridge")
            return 1
        print(f"video ok frame_id={frame.frame_id} shape={frame.image.shape}")

        # Wait for ticker to spin
        t0 = time.monotonic()
        while bridge.ticker.tick_count < 10:
            if time.monotonic() - t0 > 2.0:
                print("FAIL: ticker did not advance")
                return 1
            await asyncio.sleep(0.02)
        ticks_a = bridge.ticker.tick_count
        print(f"ticker running ticks={ticks_a}")

        # Press should assert then auto-release (>= min 80ms)
        await bridge.apply(PressButton(DualSenseButton.CROSS, duration_ms=80))
        await asyncio.sleep(0.02)
        mid = bridge.get_state()
        if DualSenseButton.CROSS not in mid.buttons:
            print(f"FAIL: cross not down after press: {mid.to_dict()}")
            return 1
        print("cross down ok")

        await asyncio.sleep(0.12)
        after = bridge.get_state()
        if DualSenseButton.CROSS in after.buttons:
            print(f"FAIL: cross still down after release window: {after.to_dict()}")
            return 1
        print("cross auto-release ok")

        # Stick mutate without serializing behind a press lock
        await bridge.apply(SetStick("left", 0.5, -0.25))
        await asyncio.sleep(0.02)
        stick = bridge.get_state()
        if abs(stick.lx - 0.5) > 1e-6 or abs(stick.ly + 0.25) > 1e-6:
            print(f"FAIL: stick not applied: {stick.to_dict()}")
            return 1
        print("stick ok", stick.to_dict()["left_stick"])

        ticks_b = bridge.ticker.tick_count
        if ticks_b <= ticks_a:
            print("FAIL: ticks did not advance during input test")
            return 1
        print(f"ticks advanced {ticks_a} -> {ticks_b}")

        print("PASS")
        return 0
    finally:
        await bridge.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
