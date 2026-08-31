"""DualSense controller state model (continuous FeedbackState, not pulse packets)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DualSenseButton(str, Enum):
    CROSS = "cross"
    CIRCLE = "circle"
    SQUARE = "square"
    TRIANGLE = "triangle"
    L1 = "l1"
    R1 = "r1"
    L2 = "l2"
    R2 = "r2"
    L3 = "l3"
    R3 = "r3"
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    OPTIONS = "options"
    SHARE = "share"
    PS = "ps"
    TOUCHPAD = "touchpad"


@dataclass
class DualSenseState:
    """Mutable live pad state. Call ``snapshot()`` before leaving the ticker thread/task."""

    buttons: set[DualSenseButton] = field(default_factory=set)
    lx: float = 0.0
    ly: float = 0.0
    rx: float = 0.0
    ry: float = 0.0
    l2: float = 0.0  # 0..1
    r2: float = 0.0

    def neutralize(self) -> None:
        self.buttons.clear()
        self.lx = self.ly = self.rx = self.ry = 0.0
        self.l2 = self.r2 = 0.0

    def set_button(self, button: DualSenseButton, down: bool) -> None:
        if down:
            self.buttons.add(button)
            if button is DualSenseButton.L2:
                self.l2 = max(self.l2, 1.0)
            elif button is DualSenseButton.R2:
                self.r2 = max(self.r2, 1.0)
        else:
            self.buttons.discard(button)
            if button is DualSenseButton.L2:
                self.l2 = 0.0
            elif button is DualSenseButton.R2:
                self.r2 = 0.0

    def set_stick(self, stick: str, x: float, y: float) -> None:
        x = _clamp(x, -1.0, 1.0)
        y = _clamp(y, -1.0, 1.0)
        if stick == "left":
            self.lx, self.ly = x, y
        elif stick == "right":
            self.rx, self.ry = x, y
        else:
            raise ValueError(f"unknown stick: {stick!r}")

    def snapshot(self) -> DualSenseState:
        return DualSenseState(
            buttons=set(self.buttons),
            lx=self.lx,
            ly=self.ly,
            rx=self.rx,
            ry=self.ry,
            l2=self.l2,
            r2=self.r2,
        )

    def to_dict(self) -> dict:
        return {
            "buttons": sorted(b.value for b in self.buttons),
            "left_stick": {"x": self.lx, "y": self.ly},
            "right_stick": {"x": self.rx, "y": self.ry},
            "l2": self.l2,
            "r2": self.r2,
        }


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))
