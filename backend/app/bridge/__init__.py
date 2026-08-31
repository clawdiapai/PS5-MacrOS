"""Hardware bridge abstractions (Fake in Phase 1, pyremoteplay in Phase 2)."""

from backend.app.bridge.base import HardwareBridge
from backend.app.bridge.commands import (
    InputCommand,
    Neutral,
    PressButton,
    SetButton,
    SetStick,
)
from backend.app.bridge.factory import create_bridge
from backend.app.bridge.fake import FakeHardwareBridge
from backend.app.bridge.state import DualSenseButton, DualSenseState
from backend.app.bridge.ticker import FeedbackTicker

__all__ = [
    "DualSenseButton",
    "DualSenseState",
    "FakeHardwareBridge",
    "FeedbackTicker",
    "HardwareBridge",
    "InputCommand",
    "Neutral",
    "PressButton",
    "SetButton",
    "SetStick",
    "create_bridge",
]
