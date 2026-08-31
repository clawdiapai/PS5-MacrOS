"""End-to-end smoke: wait_anchor found + anchors API (fake bridge)."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time


BASE = os.environ.get("WEB2PS5_SMOKE_BASE", "http://127.0.0.1:8000")


def _ensure_deps() -> None:
    try:
        import httpx  # noqa: F401
        import websockets  # noqa: F401
    except ImportError:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "httpx", "websockets"]
        )


async def main() -> int:
    import httpx
    import websockets

    async with httpx.AsyncClient(base_url=BASE, timeout=30.0) as client:
        health = (await client.get("/api/health")).json()
        print("phase", health.get("phase"), "bridge", health.get("bridge_mode"))

        anchors = (await client.get("/api/anchors")).json()
        assert anchors.get("ok")
        print("anchors", [a["id"] for a in anchors.get("anchors", [])])

        snap = await client.get("/api/anchors/snapshot.jpg")
        snap.raise_for_status()
        print("snapshot bytes", len(snap.content))

        # Crop a region likely covering the moving bar path (center band)
        crop = await client.post(
            "/api/anchors/crop",
            json={
                "id": "smoke_crop",
                "x": 400,
                "y": 300,
                "w": 200,
                "h": 120,
                "threshold": 0.5,
            },
        )
        crop.raise_for_status()
        print("crop ok", crop.json().get("anchor", {}).get("id"))

        doc = {
            "name": "complete_demo",
            "version": 1,
            "graph": {
                "last_node_id": 4,
                "last_link_id": 3,
                "nodes": [
                    {
                        "id": 1,
                        "type": "logic/start",
                        "inputs": [],
                        "outputs": [{"name": "EXEC", "type": "EXEC", "links": [1]}],
                        "properties": {},
                    },
                    {
                        "id": 2,
                        "type": "vis/wait_anchor",
                        "inputs": [{"name": "EXEC", "type": "EXEC", "link": 1}],
                        "outputs": [
                            {"name": "found", "type": "EXEC", "links": [2]},
                            {"name": "timeout", "type": "EXEC", "links": [3]},
                            {"name": "matched", "type": "BOOL", "links": None},
                            {"name": "score", "type": "FLOAT", "links": None},
                        ],
                        "properties": {
                            "anchor_id": "demo_bar",
                            "threshold": 0.5,
                            "timeout_ms": 4000,
                            "poll_ms": 50,
                        },
                    },
                    {
                        "id": 3,
                        "type": "sys/log",
                        "inputs": [{"name": "EXEC", "type": "EXEC", "link": 2}],
                        "outputs": [{"name": "EXEC", "type": "EXEC", "links": None}],
                        "properties": {"message": "FOUND"},
                    },
                    {
                        "id": 4,
                        "type": "sys/log",
                        "inputs": [{"name": "EXEC", "type": "EXEC", "link": 3}],
                        "outputs": [{"name": "EXEC", "type": "EXEC", "links": None}],
                        "properties": {"message": "TIMEOUT"},
                    },
                ],
                "links": [
                    [1, 1, 0, 2, 0, "EXEC"],
                    [2, 2, 0, 3, 0, "EXEC"],
                    [3, 2, 1, 4, 0, "EXEC"],
                ],
            },
        }
        await client.put("/api/graphs/complete_demo", json=doc)

        events: list[dict] = []
        ws_base = BASE.replace("http://", "ws://").replace("https://", "wss://")
        async with websockets.connect(f"{ws_base}/ws/telemetry") as ws:
            await asyncio.wait_for(ws.recv(), timeout=3)
            start = await client.post("/api/runs", json={"graph": "complete_demo"})
            start.raise_for_status()

            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                ev = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                events.append(ev)
                if ev.get("type") in ("run_finished", "run_error", "run_stopped"):
                    break

        types = {e.get("type") for e in events}
        logs = [e for e in events if e.get("type") == "log"]
        print("event types", sorted(t for t in types if t))
        print("logs", [e.get("message") for e in logs])
        if "run_error" in types:
            print("FAIL", [e for e in events if e.get("type") == "run_error"])
            return 1
        if not any(e.get("message") == "FOUND" for e in logs):
            print("FAIL: expected FOUND log")
            for e in events:
                print(e)
            return 1

        await client.delete("/api/graphs/complete_demo")
        await client.delete("/api/anchors/smoke_crop")
        print("PASS")
        return 0


if __name__ == "__main__":
    _ensure_deps()
    raise SystemExit(asyncio.run(main()))
