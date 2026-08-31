"""Smoke-test Phase 1.4: graphs, runs, MJPEG, WebSocket telemetry."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:8000"


def _ensure_deps() -> None:
    try:
        import httpx  # noqa: F401
        import websockets  # noqa: F401
    except ImportError:
        print("Installing httpx+websockets for smoke…")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "httpx", "websockets"],
        )


async def main() -> int:
    import httpx
    import websockets

    async with httpx.AsyncClient(base_url=BASE, timeout=10.0) as client:
        health = (await client.get("/api/health")).json()
        phase = str(health.get("phase") or "")
        if not phase.startswith("1."):
            print(f"FAIL: unexpected phase {phase}")
            return 1
        print("health ok", phase)

        graph_name = "smoke_demo"
        doc = {
            "name": graph_name,
            "version": 1,
            "graph": {
                "last_node_id": 2,
                "last_link_id": 1,
                "nodes": [
                    {
                        "id": 1,
                        "type": "logic/start",
                        "inputs": [],
                        "outputs": [
                            {"name": "EXEC", "type": "EXEC", "links": [1]}
                        ],
                        "properties": {},
                    },
                    {
                        "id": 2,
                        "type": "ds/delay",
                        "inputs": [
                            {"name": "EXEC", "type": "EXEC", "link": 1}
                        ],
                        "outputs": [
                            {"name": "EXEC", "type": "EXEC", "links": None}
                        ],
                        "properties": {"ms": 15000},
                    },
                ],
                "links": [[1, 1, 0, 2, 0, "EXEC"]],
            },
        }
        put = await client.put(f"/api/graphs/{graph_name}", json=doc)
        put.raise_for_status()
        got = (await client.get(f"/api/graphs/{graph_name}")).json()
        if not got.get("ok"):
            print("FAIL: get graph", got)
            return 1
        print("graph save/load ok")

        async with client.stream("GET", "/api/preview/mjpeg") as resp:
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "")
            if "multipart" not in ctype:
                print("FAIL: bad mjpeg content-type", ctype)
                return 1
            buf = b""
            async for chunk in resp.aiter_bytes():
                buf += chunk
                if b"\xff\xd8" in buf and b"\xff\xd9" in buf:
                    break
                if len(buf) > 2_000_000:
                    print("FAIL: mjpeg too large without JPEG markers")
                    return 1
        print("mjpeg chunk ok", len(buf), "bytes")

        events: list[dict] = []
        async with websockets.connect("ws://127.0.0.1:8000/ws/telemetry") as ws:
            hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
            if hello.get("type") != "hello":
                print("FAIL: expected hello", hello)
                return 1
            events.append(hello)

            start = await client.post("/api/runs", json={"graph": graph_name})
            start.raise_for_status()
            start_body = start.json()
            if start_body.get("status") != "running":
                print("FAIL: run not running", start_body)
                return 1

            deadline = time.monotonic() + 3
            saw_started = False
            while time.monotonic() < deadline:
                ev = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
                events.append(ev)
                if ev.get("type") == "run_started":
                    saw_started = True
                    break
            if not saw_started:
                print("FAIL: no run_started", events)
                return 1
            print("ws run_started ok")

            stop = await client.post("/api/runs/stop")
            stop.raise_for_status()
            saw_stopped = False
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                ev = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
                events.append(ev)
                if ev.get("type") == "run_stopped":
                    saw_stopped = True
                    break
            if not saw_stopped:
                print("FAIL: no run_stopped", events)
                return 1
            print("ws run_stopped ok")

        await client.delete(f"/api/graphs/{graph_name}")
        print("PASS")
        return 0


if __name__ == "__main__":
    _ensure_deps()
    raise SystemExit(asyncio.run(main()))
