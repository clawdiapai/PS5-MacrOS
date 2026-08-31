"""Input commands applied by the FeedbackTicker (never hold a socket lock across duration)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union

from backend.app.bridge.state import DualSenseButton


@dataclass(frozen=True, slots=True)
class PressButton:
    """Edge press: set button down, auto-release after duration_ms (min enforced by ticker)."""

    button: DualSenseButton
    duration_ms: float = 80.0


@dataclass(frozen=True, slots=True)
class SetButton:
    """Explicit down/up (for holds and chords)."""

    button: DualSenseButton
    down: bool


@dataclass(frozen=True, slots=True)
class SetStick:
    stick: Literal["left", "right"]
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class Neutral:
    """Force all buttons/axes to rest."""


InputCommand = Union[PressButton, SetButton, SetStick, Neutral]
