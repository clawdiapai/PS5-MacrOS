"""Smoke-test AtomicFrameHolder + FakeFrameSource without starting the web server."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.vision import AtomicFrameHolder, FakeFrameSource


def main() -> int:
    holder = AtomicFrameHolder()
    source = FakeFrameSource(holder, width=1280, height=720, fps=30.0)
    source.start()

    try:
        first = holder.wait_newer(0, timeout=2.0)
        if first is None:
            print("FAIL: no first frame")
            return 1
        print(
            f"first frame_id={first.frame_id} shape={first.image.shape} "
            f"dtype={first.image.dtype}"
        )

        second = holder.wait_newer(first.frame_id, timeout=2.0)
        if second is None:
            print("FAIL: wait_newer timed out")
            return 1
        if second.frame_id <= first.frame_id:
            print("FAIL: frame_id did not advance")
            return 1
        print(f"newer frame_id={second.frame_id} (delta={second.frame_id - first.frame_id})")

        # Drop-old semantics: sleep then get_latest should be far ahead of second
        time.sleep(0.35)
        latest = holder.get_latest()
        assert latest is not None
        if latest.frame_id <= second.frame_id:
            print("FAIL: latest did not advance while sleeping")
            return 1
        print(
            f"latest frame_id={latest.frame_id} published={source.published_count} "
            f"(dropped unread frames as expected)"
        )

        # Timeout path
        timed_out = holder.wait_newer(latest.frame_id + 10_000, timeout=0.05)
        if timed_out is not None:
            print("FAIL: expected timeout None")
            return 1
        print("timeout path ok")

        print("PASS")
        return 0
    finally:
        source.stop()
        holder.clear()


if __name__ == "__main__":
    raise SystemExit(main())
