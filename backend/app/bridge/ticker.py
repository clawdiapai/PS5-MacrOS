"""Fixed-rate DualSense FeedbackTicker — owns state mutations and timed releases."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from backend.app.bridge.commands import (
    InputCommand,
    Neutral,
    PressButton,
    SetButton,
    SetStick,
)
from backend.app.bridge.state import DualSenseButton, DualSenseState

TickHandler = Callable[[DualSenseState, int], Awaitable[None] | None]


@dataclass(frozen=True, slots=True)
class TickRecord:
    tick: int
    pts: float
    state: dict


class FeedbackTicker:
    """
    Emits DualSenseState at ``hz`` and applies timed button releases.

    ``apply()`` mutates state immediately (same event loop). Press durations are
    release *deadlines* on this tick loop — never a lock held across sleep(duration).
    ``apply_nowait()`` enqueues for the next tick (sync/cross-thread helpers).
    """

    def __init__(
        self,
        *,
        hz: float = 60.0,
        min_press_ms: float = 80.0,
        on_tick: TickHandler | None = None,
        history_size: int = 120,
    ) -> None:
        if hz <= 0:
            raise ValueError("hz must be positive")
        self._hz = float(hz)
        self._period = 1.0 / self._hz
        self._min_press_ms = float(min_press_ms)
        self._on_tick = on_tick
        self._history_size = max(1, int(history_size))

        self._state = DualSenseState()
        self._commands: asyncio.Queue[InputCommand] = asyncio.Queue()
        # button -> release deadline (monotonic)
        self._releases: dict[DualSenseButton, float] = {}

        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._tick_count = 0
        self._history: deque[TickRecord] = deque(maxlen=self._history_size)

    @property
    def hz(self) -> float:
        return self._hz

    @property
    def tick_count(self) -> int:
        return self._tick_count

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def snapshot(self) -> DualSenseState:
        return self._state.snapshot()

    def recent_ticks(self, limit: int = 10) -> list[TickRecord]:
        if limit <= 0:
            return []
        items = list(self._history)
        return items[-limit:]

    async def apply(self, command: InputCommand) -> None:
        """Apply immediately so callers can read updated state after await."""
        self._apply_command(command, time.monotonic())

    def apply_nowait(self, command: InputCommand) -> None:
        """Queue for the next tick (safe from sync contexts via call_soon_threadsafe)."""
        self._commands.put_nowait(command)

    async def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="FeedbackTicker")

    async def stop(self) -> None:
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
        self._state.neutralize()
        self._releases.clear()

    async def _run(self) -> None:
        next_tick = time.monotonic()
        while not self._stop.is_set():
            now = time.monotonic()
            if now < next_tick:
                try:
                    await asyncio.wait_for(
                        self._stop.wait(),
                        timeout=min(self._period, next_tick - now),
                    )
                    break
                except asyncio.TimeoutError:
                    continue

            await self._drain_commands()
            self._apply_releases(time.monotonic())

            self._tick_count += 1
            snap = self._state.snapshot()
            self._history.append(
                TickRecord(
                    tick=self._tick_count,
                    pts=time.monotonic(),
                    state=snap.to_dict(),
                )
            )

            if self._on_tick is not None:
                result = self._on_tick(snap, self._tick_count)
                if asyncio.iscoroutine(result) or isinstance(result, Awaitable):
                    await result  # type: ignore[arg-type]

            next_tick += self._period
            if time.monotonic() - next_tick > self._period:
                next_tick = time.monotonic() + self._period

    async def _drain_commands(self) -> None:
        while True:
            try:
                cmd = self._commands.get_nowait()
            except asyncio.QueueEmpty:
                return
            self._apply_command(cmd, time.monotonic())

    def _apply_command(self, cmd: InputCommand, now: float) -> None:
        if isinstance(cmd, Neutral):
            self._state.neutralize()
            self._releases.clear()
            return

        if isinstance(cmd, SetButton):
            self._state.set_button(cmd.button, cmd.down)
            if not cmd.down:
                self._releases.pop(cmd.button, None)
            return

        if isinstance(cmd, SetStick):
            self._state.set_stick(cmd.stick, cmd.x, cmd.y)
            return

        if isinstance(cmd, PressButton):
            duration = max(float(cmd.duration_ms), self._min_press_ms) / 1000.0
            self._state.set_button(cmd.button, True)
            self._releases[cmd.button] = now + duration
            return

        raise TypeError(f"unsupported command: {type(cmd)!r}")

    def _apply_releases(self, now: float) -> None:
        due = [btn for btn, deadline in self._releases.items() if now >= deadline]
        for btn in due:
            self._state.set_button(btn, False)
            del self._releases[btn]
