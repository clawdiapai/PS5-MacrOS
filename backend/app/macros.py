"""DualSense state-timeline macros (not raw UDP)."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from backend.app.config import settings

_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$")


def macros_dir() -> Path:
    path = settings.data_dir / "macros"
    path.mkdir(parents=True, exist_ok=True)
    return path


def validate_name(name: str) -> str:
    if not _SAFE.match(name):
        raise ValueError("macro name must match [A-Za-z0-9][A-Za-z0-9_-]{0,63}")
    return name


def list_macros() -> list[str]:
    return sorted(p.stem for p in macros_dir().glob("*.json"))


def save_macro(
    name: str,
    keyframes: list[dict[str, Any]] | None = None,
    meta: dict | None = None,
    *,
    events: list[dict[str, Any]] | None = None,
) -> Path:
    name = validate_name(name)
    doc = {
        "name": name,
        "version": 2 if events else 1,
        "created_at": time.time(),
        "meta": meta or {},
        "keyframes": keyframes or [],
        "events": events or [],
    }
    path = macros_dir() / f"{name}.json"
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return path


def load_macro(name: str) -> dict[str, Any]:
    name = validate_name(name)
    path = macros_dir() / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(name)
    return json.loads(path.read_text(encoding="utf-8"))


def delete_macro(name: str) -> None:
    name = validate_name(name)
    path = macros_dir() / f"{name}.json"
    if path.is_file():
        path.unlink()


def _stick_mag(x: float, y: float) -> float:
    return (x * x + y * y) ** 0.5


def _extract_button_taps(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One tap per press/release pair, stamped at original press time."""
    open_press: dict[str, float] = {}
    taps: list[dict[str, Any]] = []
    for ev in events:
        if "btn" not in ev or "action" not in ev:
            continue
        btn = str(ev["btn"]).upper()
        action = str(ev["action"]).lower()
        t = float(ev.get("t", 0))
        if action == "press":
            open_press[btn] = t
        elif action == "release":
            t0 = open_press.pop(btn, t)
            taps.append({"t": t0, "btn": btn})
    for btn, t0 in open_press.items():
        taps.append({"t": t0, "btn": btn})
    taps.sort(key=lambda x: float(x["t"]))
    return taps


def _extract_stick_segments(
    events: list[dict[str, Any]],
    *,
    stick_deadzone: float,
) -> list[dict[str, Any]]:
    """
    Collapse raw stick spam into hold segments:
    leave deadzone → hold representative direction → return to center.
    Duration is the real recorded hold length.
    """
    segments: list[dict[str, Any]] = []
    for stick_name in ("left", "right"):
        in_seg = False
        t0 = 0.0
        samples: list[tuple[float, float, float]] = []  # t, x, y
        last_t = 0.0

        for ev in events:
            if ev.get("stick") != stick_name or "point" not in ev:
                continue
            pt = ev["point"]
            try:
                x, y = float(pt[0]), float(pt[1])
            except Exception:
                continue
            t = float(ev.get("t", 0))
            last_t = t
            mag = _stick_mag(x, y)

            if mag >= stick_deadzone:
                if not in_seg:
                    in_seg = True
                    t0 = t
                    samples = [(t, x, y)]
                else:
                    samples.append((t, x, y))
            elif in_seg:
                # Return to center ends the hold
                point = _segment_point(samples)
                segments.append(
                    {
                        "stick": stick_name,
                        "t0": t0,
                        "t1": t,
                        "point": point,
                    }
                )
                in_seg = False
                samples = []

        if in_seg and samples:
            # Still held at end of recording — close on last sample
            point = _segment_point(samples)
            segments.append(
                {
                    "stick": stick_name,
                    "t0": t0,
                    "t1": max(last_t, t0 + 0.05),
                    "point": point,
                }
            )

    segments.sort(key=lambda s: float(s["t0"]))
    return segments


def _segment_point(samples: list[tuple[float, float, float]]) -> list[float]:
    """Prefer peak-magnitude sample so direction stays decisive."""
    if not samples:
        return [0.0, 0.0]
    best = max(samples, key=lambda s: _stick_mag(s[1], s[2]))
    return [round(best[1], 3), round(best[2], 3)]


def normalize_macro_events(
    events: list[dict[str, Any]],
    *,
    gap_ms: float = 700.0,
    press_ms: float = 100.0,
    stick_deadzone: float = 0.2,
    stick_min_ms: float = 80.0,
    stick_max_ms: float = 3000.0,
) -> list[dict[str, Any]]:
    """
    Clean a raw DualSense recording into a tidy playback timeline.

    Buttons:
      - uniform short taps (press_ms)
      - fixed gap_ms between button inputs (default 700)
      - strip long human hesitations

    Sticks (different logic):
      - NOT treated as taps
      - collapse sample spam into hold segments
      - keep real hold duration (clamped stick_min_ms..stick_max_ms)
      - push → hold direction → return to center
      - buttons pressed during a hold keep relative timing inside that hold
    """
    if not events:
        return []

    gap_s = max(0.0, float(gap_ms)) / 1000.0
    press_s = max(0.05, float(press_ms)) / 1000.0
    stick_min_s = max(0.05, float(stick_min_ms)) / 1000.0
    stick_max_s = max(stick_min_s, float(stick_max_ms)) / 1000.0

    ordered = sorted(events, key=lambda e: float(e.get("t", 0)))
    taps = _extract_button_taps(ordered)
    segs = _extract_stick_segments(ordered, stick_deadzone=stick_deadzone)

    # Attach buttons that happened during a stick hold to that segment
    nested: dict[int, list[dict[str, Any]]] = {i: [] for i in range(len(segs))}
    loose: list[dict[str, Any]] = []
    for tap in taps:
        tt = float(tap["t"])
        placed = False
        for i, seg in enumerate(segs):
            if float(seg["t0"]) <= tt <= float(seg["t1"]):
                nested[i].append(tap)
                placed = True
                break
        if not placed:
            loose.append(tap)

    # Schedule: loose buttons + stick segments, by original start time
    schedule: list[tuple[str, float, Any]] = []
    for tap in loose:
        schedule.append(("btn", float(tap["t"]), tap))
    for i, seg in enumerate(segs):
        schedule.append(("seg", float(seg["t0"]), (i, seg)))
    schedule.sort(key=lambda x: x[1])

    out: list[dict[str, Any]] = []
    clock = 0.0

    def emit_button(btn: str, at: float) -> None:
        out.append({"t": round(at, 4), "btn": btn, "action": "press"})
        out.append({"t": round(at + press_s, 4), "btn": btn, "action": "release"})

    for kind, _t_orig, payload in schedule:
        if kind == "btn":
            emit_button(str(payload["btn"]), clock)
            clock += press_s + gap_s
            continue

        idx, seg = payload
        raw_dur = max(0.0, float(seg["t1"]) - float(seg["t0"]))
        dur = min(stick_max_s, max(stick_min_s, raw_dur))
        stick = str(seg["stick"])
        point = seg["point"]

        out.append({"t": round(clock, 4), "stick": stick, "point": list(point)})

        # Buttons during this hold → remap into the (possibly clamped) hold window
        span = max(raw_dur, 1e-6)
        for tap in sorted(nested[idx], key=lambda x: float(x["t"])):
            rel = (float(tap["t"]) - float(seg["t0"])) / span
            at = clock + min(max(rel * dur, 0.0), max(0.0, dur - press_s))
            emit_button(str(tap["btn"]), at)

        out.append({"t": round(clock + dur, 4), "stick": stick, "point": [0.0, 0.0]})
        clock += dur + gap_s

    out.sort(key=lambda e: float(e.get("t", 0)))
    return out

