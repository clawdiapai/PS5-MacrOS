"""Smoke-test GraphRunner: start → delay → check_state → log via API + WS."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time


BASE = "http://127.0.0.1:8000"


def _ensure_deps() -> None:
    try:
        import httpx  # noqa: F401
        import websockets  # noqa: F401
    except ImportError:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "httpx", "websockets"]
        )


def _demo_graph() -> dict:
    # Minimal LiteGraph-shaped document matching frontend node types
    return {
        "name": "runner_demo",
        "version": 1,
        "graph": {
            "last_node_id": 4,
            "last_link_id": 3,
            "nodes": [
                {
                    "id": 1,
                    "type": "logic/start",
                    "pos": [60, 140],
                    "inputs": [],
                    "outputs": [{"name": "EXEC", "type": "EXEC", "links": [1]}],
                    "properties": {},
                },
                {
                    "id": 2,
                    "type": "ds/delay",
                    "pos": [260, 140],
                    "inputs": [{"name": "EXEC", "type": "EXEC", "link": 1}],
                    "outputs": [{"name": "EXEC", "type": "EXEC", "links": [2]}],
                    "properties": {"ms": 150},
                },
                {
                    "id": 3,
                    "type": "vis/check_state",
                    "pos": [480, 120],
                    "inputs": [{"name": "EXEC", "type": "EXEC", "link": 2}],
                    "outputs": [
                        {"name": "EXEC", "type": "EXEC", "links": [3]},
                        {"name": "matched", "type": "BOOL", "links": None},
                        {"name": "score", "type": "FLOAT", "links": None},
                    ],
                    "properties": {"anchor_id": "demo_bar", "threshold": 0.5},
                },
                {
                    "id": 4,
                    "type": "sys/log",
                    "pos": [740, 140],
                    "inputs": [{"name": "EXEC", "type": "EXEC", "link": 3}],
                    "outputs": [{"name": "EXEC", "type": "EXEC", "links": None}],
                    "properties": {"message": "runner smoke ok"},
                },
            ],
            "links": [
                [1, 1, 0, 2, 0, "EXEC"],
                [2, 2, 0, 3, 0, "EXEC"],
                [3, 3, 0, 4, 0, "EXEC"],
            ],
            "groups": [],
            "config": {},
            "version": 0.4,
        },
    }


async def main() -> int:
    import httpx
    import websockets

    async with httpx.AsyncClient(base_url=BASE, timeout=20.0) as client:
        health = (await client.get("/api/health")).json()
        phase = health.get("phase")
        if not str(phase).startswith("1."):
            print("FAIL: bad phase", phase)
            return 1
        print("health", phase)

        doc = _demo_graph()
        put = await client.put("/api/graphs/runner_demo", json=doc)
        put.raise_for_status()

        events: list[dict] = []
        async with websockets.connect("ws://127.0.0.1:8000/ws/telemetry") as ws:
            hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
            assert hello.get("type") == "hello"

            start = await client.post("/api/runs", json={"graph": "runner_demo"})
            start.raise_for_status()
            assert start.json().get("status") == "running"

            deadline = time.monotonic() + 8
            saw = set()
            while time.monotonic() < deadline:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
                ev = json.loads(raw)
                events.append(ev)
                t = ev.get("type")
                if t:
                    saw.add(t)
                if t == "run_finished":
                    break
                if t == "run_error":
                    print("FAIL: run_error", ev)
                    return 1

            needed = {"run_started", "node_enter", "match_score", "log", "run_finished"}
            missing = needed - saw
            if missing:
                print("FAIL: missing events", missing)
                print("seen", saw)
                for e in events:
                    print(e)
                return 1

            match_ev = next(e for e in events if e.get("type") == "match_score")
            print(
                "match score=",
                match_ev.get("score"),
                "matched=",
                match_ev.get("matched"),
            )
            if not match_ev.get("matched"):
                print("FAIL: demo_bar did not match fake frame")
                return 1

        # wait until idle
        for _ in range(20):
            cur = (await client.get("/api/runs/current")).json()
            if cur.get("status") == "idle":
                break
            await asyncio.sleep(0.05)

        await client.delete("/api/graphs/runner_demo")
        print("PASS")
        return 0


if __name__ == "__main__":
    _ensure_deps()
    raise SystemExit(asyncio.run(main()))
