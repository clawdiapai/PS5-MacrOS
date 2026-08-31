"""HardwareBridge protocol — swappable Fake / pyremoteplay / chiaki-ng."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.app.bridge.commands import InputCommand
from backend.app.bridge.state import DualSenseState
from backend.app.vision.frame_holder import AtomicFrameHolder


@runtime_checkable
class HardwareBridge(Protocol):
    """Narrow surface GraphRunner and API talk to."""

    @property
    def frames(self) -> AtomicFrameHolder: ...

    @property
    def connected(self) -> bool: ...

    @property
    def name(self) -> str: ...

    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    async def standby(self) -> None: ...

    async def apply(self, command: InputCommand) -> None: ...

    def get_state(self) -> DualSenseState: ...
