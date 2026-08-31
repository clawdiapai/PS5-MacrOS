"""Smoke-test bridge factory + pyremoteplay construct (no live PS5 required)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.bridge.factory import create_bridge
from backend.app.bridge import PressButton, DualSenseButton
from backend.app.config import Settings


async def main() -> int:
    fake = create_bridge(Settings(bridge="fake", auto_connect=True))
    await fake.connect()
    assert fake.connected
    assert fake.name == "fake"
    frame = fake.frames.wait_newer(0, timeout=2.0)
    assert frame is not None
    await fake.apply(PressButton(DualSenseButton.CROSS, duration_ms=80))
    await asyncio.sleep(0.05)
    assert DualSenseButton.CROSS in fake.get_state().buttons
    await fake.disconnect()
    print("fake bridge ok")

    real = create_bridge(Settings(bridge="pyremoteplay", ps5_host="192.0.2.1"))
    assert real.name == "pyremoteplay"
    assert real.connected is False
    st = real.status()
    assert st["host"] == "192.0.2.1"
    print("pyremoteplay construct ok (not connecting to live host)")

    try:
        create_bridge(Settings(bridge="pyremoteplay", ps5_host=""))
        print("FAIL: expected missing host error")
        return 1
    except RuntimeError as exc:
        print("missing host guarded:", exc)

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
