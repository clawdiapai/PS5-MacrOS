"""Run lifecycle API — single-flight GraphRunner ownership."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.api.graphs import get_graph_document
from backend.app.api.telemetry import TelemetryHub
from backend.app.bridge import Neutral
from backend.app.runner import GraphRunner, GraphRunnerError

router = APIRouter(prefix="/api/runs", tags=["runs"])

RunStatus = Literal["idle", "running", "stopping", "error"]


class StartRunBody(BaseModel):
    graph: str = Field(min_length=1, max_length=64)


class RunController:
    """Single active run per hardware session."""

    def __init__(self, bridge: Any, hub: TelemetryHub) -> None:
        self._bridge = bridge
        self._hub = hub
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._run_id: str | None = None
        self._graph: str | None = None
        self._status: RunStatus = "idle"
        self._started_at: float | None = None
        self._error: str | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "status": self._status,
            "run_id": self._run_id,
            "graph": self._graph,
            "started_at": self._started_at,
            "error": self._error,
            "active": self._task is not None and not self._task.done(),
        }

    async def start(self, graph_name: str) -> dict[str, Any]:
        async with self._lock:
            if self._task is not None and not self._task.done():
                raise HTTPException(status_code=409, detail="a run is already active")
            if not self._bridge.connected:
                raise HTTPException(status_code=409, detail="bridge not connected")

            try:
                document = get_graph_document(graph_name)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="graph not found") from None
            except HTTPException:
                raise

            run_id = uuid.uuid4().hex[:12]
            self._run_id = run_id
            self._graph = graph_name
            self._status = "running"
            self._started_at = time.time()
            self._error = None
            self._task = asyncio.create_task(
                self._execute(run_id, graph_name, document),
                name=f"run-{run_id}",
            )
            return self.snapshot()

    async def stop(self) -> dict[str, Any]:
        async with self._lock:
            task = self._task
            if task is None or task.done():
                self._status = "idle"
                return self.snapshot()
            self._status = "stopping"

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        async with self._lock:
            self._task = None
            self._status = "idle"
        return self.snapshot()

    async def _execute(
        self,
        run_id: str,
        graph_name: str,
        document: dict[str, Any],
    ) -> None:
        node_count = 0
        graph = document.get("graph") or {}
        if isinstance(graph, dict) and isinstance(graph.get("nodes"), list):
            node_count = len(graph["nodes"])

        await self._hub.broadcast(
            {
                "type": "run_started",
                "run_id": run_id,
                "graph": graph_name,
                "node_count": node_count,
                "mode": "graph_runner",
            }
        )

        try:
            runner = GraphRunner(
                document,
                bridge=self._bridge,
                hub=self._hub,
                run_id=run_id,
            )
            await runner.run()
            async with self._lock:
                if self._run_id == run_id:
                    self._status = "idle"
                    self._task = None
                    self._error = None
        except asyncio.CancelledError:
            async with self._lock:
                if self._run_id == run_id:
                    self._status = "idle"
                    self._task = None
            raise
        except GraphRunnerError as exc:
            async with self._lock:
                if self._run_id == run_id:
                    self._status = "error"
                    self._error = str(exc)
                    self._task = None
            try:
                await self._bridge.apply(Neutral())
            except Exception:
                pass
        except Exception as exc:
            async with self._lock:
                if self._run_id == run_id:
                    self._status = "error"
                    self._error = str(exc)
                    self._task = None
            try:
                await self._bridge.apply(Neutral())
            except Exception:
                pass
            await self._hub.broadcast(
                {
                    "type": "run_error",
                    "run_id": run_id,
                    "error": str(exc),
                }
            )


@router.get("/current")
async def current_run(request: Request) -> dict[str, Any]:
    runs: RunController = request.app.state.runs
    return {"ok": True, **runs.snapshot()}


@router.post("")
async def start_run(request: Request, body: StartRunBody) -> dict[str, Any]:
    runs: RunController = request.app.state.runs
    snap = await runs.start(body.graph)
    return {"ok": True, **snap}


@router.post("/stop")
async def stop_run(request: Request) -> dict[str, Any]:
    runs: RunController = request.app.state.runs
    snap = await runs.stop()
    return {"ok": True, **snap}
