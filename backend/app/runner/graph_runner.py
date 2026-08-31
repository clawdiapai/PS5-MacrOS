"""Single-token EXEC walker for LiteGraph JSON (hybrid Blueprint-style)."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

import cv2

from backend.app.api.graphs import get_graph_document
from backend.app.api.telemetry import TelemetryHub
from backend.app.bridge import DualSenseButton, Neutral, PressButton, SetButton, SetStick
from backend.app.config import settings
from backend.app.macros import load_macro
from backend.app.vision.anchors import parse_roi

logger = logging.getLogger("web2ps5.runner")

EXEC_TYPES = {"EXEC", "EVENT", "ACTION"}


class GraphRunnerError(RuntimeError):
    pass


class GraphRunner:
    """Walks EXEC pins with a single token. Data pins resolved by pull."""

    def __init__(
        self,
        document: dict[str, Any],
        *,
        bridge: Any,
        hub: TelemetryHub,
        run_id: str,
        vars_store: dict[str, Any] | None = None,
        depth: int = 0,
    ) -> None:
        self._bridge = bridge
        self._hub = hub
        self._run_id = run_id
        self._vars = vars_store if vars_store is not None else {}
        self._depth = depth
        self._node_state: dict[int, dict[str, Any]] = {}
        graph = document.get("graph") or document
        if not isinstance(graph, dict):
            raise GraphRunnerError("document.graph must be an object")
        self._nodes: dict[int, dict[str, Any]] = {}
        for node in graph.get("nodes") or []:
            self._nodes[int(node["id"])] = node
        self._links: list[list[Any]] = list(graph.get("links") or [])
        self._data: dict[tuple[int, int], Any] = {}

    async def run(self) -> None:
        start = self._find_start()
        if start is None:
            raise GraphRunnerError("no logic/start node in graph")

        node_id: int | None = int(start["id"])
        if self._first_exec_output_slot(start) is None and self._depth == 0:
            await self._emit("run_finished", {"reason": "start_has_no_exec_out"})
            return

        try:
            while node_id is not None:
                node = self._nodes.get(node_id)
                if node is None:
                    raise GraphRunnerError(f"missing node id={node_id}")

                await self._hub.broadcast(
                    {
                        "type": "node_enter",
                        "run_id": self._run_id,
                        "node_id": node_id,
                        "node_type": node.get("type"),
                        "depth": self._depth,
                    }
                )

                next_info = await self._execute(node)

                await self._hub.broadcast(
                    {
                        "type": "node_exit",
                        "run_id": self._run_id,
                        "node_id": node_id,
                        "node_type": node.get("type"),
                        "depth": self._depth,
                    }
                )

                if next_info is None:
                    node_id = None
                else:
                    out_name, out_slot = next_info
                    node_id = self._follow_exec(node_id, out_slot, out_name)

            if self._depth == 0:
                await self._hub.broadcast(
                    {
                        "type": "run_finished",
                        "run_id": self._run_id,
                        "reason": "completed",
                    }
                )
        except asyncio.CancelledError:
            if self._depth == 0:
                try:
                    await self._bridge.apply(Neutral())
                except Exception:
                    pass
                await self._hub.broadcast(
                    {
                        "type": "run_stopped",
                        "run_id": self._run_id,
                        "reason": "cancelled",
                    }
                )
            raise
        except Exception as exc:
            if self._depth == 0:
                logger.exception("graph run failed")
                try:
                    await self._bridge.apply(Neutral())
                except Exception:
                    pass
                await self._hub.broadcast(
                    {
                        "type": "run_error",
                        "run_id": self._run_id,
                        "error": str(exc),
                    }
                )
            raise

    def _find_start(self) -> dict[str, Any] | None:
        for node in self._nodes.values():
            if node.get("type") in ("logic/start", "logic.start"):
                return node
        return None

    async def _execute(self, node: dict[str, Any]) -> tuple[str, int] | None:
        ntype = (node.get("type") or "").replace(".", "/")
        props = node.get("properties") or {}

        handlers = {
            "logic/start": self._exec_passthrough,
            "logic/branch": self._exec_branch,
            "logic/merge": self._exec_passthrough,
            "logic/and": self._exec_gate_and,
            "logic/or": self._exec_gate_or,
            "logic/not": self._exec_gate_not,
            "logic/while": self._exec_while,
            "logic/repeat": self._exec_repeat,
            "logic/retry": self._exec_retry,
            "logic/set_var": self._exec_set_var,
            "logic/get_var": self._exec_get_var,
            "logic/counter": self._exec_counter,
            "logic/subgraph": self._exec_subgraph,
            "ds/delay": self._exec_delay,
            "ds/press": self._exec_press,
            "ds/stick": self._exec_stick,
            "ds/macro": self._exec_macro,
            "ds/macro_block": self._exec_macro,
            "sys/log": self._exec_log,
            "sys/assert": self._exec_assert,
            "sys/webhook": self._exec_webhook,
            "sys/screenshot": self._exec_screenshot,
            "pwr/session": self._exec_pwr_session,
            "vis/check_state": self._exec_check_state,
            "vis/wait_anchor": self._exec_wait_anchor,
            "vis/ocr_check": self._exec_ocr_check,
            "vis/wait_ocr": self._exec_wait_ocr,
            "vis/frame_snapshot": self._exec_frame_snapshot,
            "vis/frame_changed": self._exec_frame_changed,
        }
        handler = handlers.get(ntype)
        if handler is None:
            raise GraphRunnerError(f"unsupported node type: {ntype}")
        return await handler(node, props)

    async def _exec_passthrough(self, node, props):  # noqa: ARG002
        slot = self._first_exec_output_slot(node)
        return ("EXEC", slot) if slot is not None else None

    async def _exec_delay(self, node, props):
        ms = float(props.get("ms", 500))
        await asyncio.sleep(max(0.0, ms) / 1000.0)
        return self._out(node, "EXEC")

    async def _exec_press(self, node, props):
        button = str(props.get("button", "cross"))
        duration = float(props.get("duration_ms", settings.min_press_ms))
        await self._bridge.apply(PressButton(DualSenseButton(button), duration_ms=duration))
        await asyncio.sleep(max(duration, settings.min_press_ms) / 1000.0 + 0.02)
        return self._out(node, "EXEC")

    async def _exec_stick(self, node, props):
        stick = str(props.get("stick", "left"))
        x = float(props.get("x", 0.0))
        y = float(props.get("y", 0.0))
        hold_ms = float(props.get("hold_ms", 0))
        await self._bridge.apply(SetStick(stick, x, y))  # type: ignore[arg-type]
        if hold_ms > 0:
            await asyncio.sleep(hold_ms / 1000.0)
            await self._bridge.apply(SetStick(stick, 0.0, 0.0))  # type: ignore[arg-type]
        return self._out(node, "EXEC")

    async def _exec_log(self, node, props):
        message = str(props.get("message", ""))
        # Allow {var} substitution
        try:
            message = message.format(**{k: self._vars.get(k) for k in self._vars})
        except Exception:
            pass
        await self._hub.broadcast(
            {
                "type": "log",
                "run_id": self._run_id,
                "node_id": node["id"],
                "message": message,
                "t": time.time(),
            }
        )
        return self._out(node, "EXEC")

    async def _exec_assert(self, node, props):
        cond = bool(self._resolve_input(node, "cond", default=props.get("value", True)))
        if not cond:
            msg = str(props.get("message", "assert failed"))
            raise GraphRunnerError(msg)
        return self._out(node, "EXEC")

    async def _exec_branch(self, node, props):  # noqa: ARG002
        cond = bool(self._resolve_input(node, "cond", default=False))
        name = "true" if cond else "false"
        return self._out(node, name)

    async def _exec_while(self, node, props):  # noqa: ARG002
        cond = bool(self._resolve_input(node, "cond", default=False))
        name = "body" if cond else "done"
        return self._out(node, name)

    async def _exec_repeat(self, node, props):
        nid = int(node["id"])
        st = self._node_state.setdefault(nid, {"i": 0})
        times = int(props.get("times", 1))
        if st["i"] < times:
            st["i"] += 1
            self._set_data_out(node, "index", st["i"])
            return self._out(node, "body")
        st["i"] = 0
        return self._out(node, "done")

    async def _exec_retry(self, node, props):
        """body on first/retry; success/fail outs. User wires body end back or uses subgraph."""
        nid = int(node["id"])
        st = self._node_state.setdefault(nid, {"attempt": 0, "ok": False})
        max_attempts = int(props.get("max_attempts", 3))
        # If previous body signaled ok via set_var or input
        ok_in = self._resolve_input(node, "ok", default=None)
        if ok_in is True:
            st["ok"] = True
            st["attempt"] = 0
            return self._out(node, "success")
        if st["attempt"] >= max_attempts:
            st["attempt"] = 0
            return self._out(node, "fail")
        st["attempt"] += 1
        self._set_data_out(node, "attempt", st["attempt"])
        return self._out(node, "body")

    async def _exec_gate_and(self, node, props):  # noqa: ARG002
        a = bool(self._resolve_input(node, "a", default=False))
        b = bool(self._resolve_input(node, "b", default=False))
        self._set_data_out(node, "out", a and b)
        return self._out(node, "EXEC")

    async def _exec_gate_or(self, node, props):  # noqa: ARG002
        a = bool(self._resolve_input(node, "a", default=False))
        b = bool(self._resolve_input(node, "b", default=False))
        self._set_data_out(node, "out", a or b)
        return self._out(node, "EXEC")

    async def _exec_gate_not(self, node, props):  # noqa: ARG002
        a = bool(self._resolve_input(node, "a", default=False))
        self._set_data_out(node, "out", not a)
        return self._out(node, "EXEC")

    async def _exec_set_var(self, node, props):
        name = str(props.get("name", "x"))
        value = self._resolve_input(node, "value", default=props.get("value"))
        # coerce from property string if needed
        if value is None:
            value = props.get("value", "")
        self._vars[name] = value
        await self._hub.broadcast(
            {
                "type": "var_set",
                "run_id": self._run_id,
                "name": name,
                "value": value,
            }
        )
        return self._out(node, "EXEC")

    async def _exec_get_var(self, node, props):
        name = str(props.get("name", "x"))
        value = self._vars.get(name, props.get("default"))
        self._set_data_out(node, "value", value)
        return self._out(node, "EXEC")

    async def _exec_counter(self, node, props):
        name = str(props.get("name", "count"))
        op = str(props.get("op", "inc"))
        cur = int(self._vars.get(name, 0) or 0)
        if op == "inc":
            cur += int(props.get("by", 1))
        elif op == "dec":
            cur -= int(props.get("by", 1))
        elif op == "set":
            cur = int(props.get("value", 0))
        elif op == "reset":
            cur = 0
        self._vars[name] = cur
        self._set_data_out(node, "value", cur)
        return self._out(node, "EXEC")

    async def _exec_subgraph(self, node, props):
        if self._depth >= 5:
            raise GraphRunnerError("subgraph nesting limit (5)")
        name = str(props.get("graph", ""))
        if not name:
            raise GraphRunnerError("logic/subgraph requires properties.graph")
        try:
            document = get_graph_document(name)
        except FileNotFoundError as exc:
            raise GraphRunnerError(f"subgraph not found: {name}") from exc
        child = GraphRunner(
            document,
            bridge=self._bridge,
            hub=self._hub,
            run_id=self._run_id,
            vars_store=self._vars,
            depth=self._depth + 1,
        )
        await child.run()
        return self._out(node, "EXEC")

    async def _exec_macro(self, node, props):
        """Play embedded events (from Record on node) or a saved macro file."""
        events = props.get("events") or []
        name = str(props.get("macro") or props.get("name") or "")

        if not events and name:
            try:
                doc = load_macro(name)
            except FileNotFoundError as exc:
                raise GraphRunnerError(f"macro not found: {name}") from exc
            events = doc.get("events") or []
            if not events and doc.get("keyframes"):
                await self._play_keyframes(doc["keyframes"])
                return self._out(node, "EXEC")

        if not events:
            raise GraphRunnerError(
                "ds/macro_block has no recorded events — click Record on the node first"
            )

        await self._play_events(events)
        return self._out(node, "EXEC")

    async def _play_events(self, events: list[dict[str, Any]]) -> None:
        """Event timeline: {t, btn, action} / {t, stick, point} — pi2ps5 style."""
        ctrl = getattr(self._bridge, "raw_controller", None)
        if callable(ctrl):
            ctrl = ctrl()
        t0 = time.monotonic()
        for ev in events:
            target = float(ev.get("t", 0))
            delay = target - (time.monotonic() - t0)
            if delay > 0:
                await asyncio.sleep(delay)
            if "btn" in ev and "action" in ev:
                btn = str(ev["btn"]).upper()
                action = str(ev["action"]).lower()
                if ctrl is not None:
                    try:
                        ctrl.button(btn, action)
                        continue
                    except Exception:
                        pass
                try:
                    await self._bridge.apply(
                        SetButton(DualSenseButton(btn.lower()), action == "press")
                    )
                except Exception:
                    pass
            elif "stick" in ev and "point" in ev:
                stick = str(ev["stick"])
                point = ev["point"]
                x, y = float(point[0]), float(point[1])
                if ctrl is not None:
                    try:
                        ctrl.stick(stick, point=(x, y))
                        continue
                    except Exception:
                        pass
                await self._bridge.apply(SetStick(stick, x, y))  # type: ignore[arg-type]
        if ctrl is not None:
            try:
                ctrl.stick("left", point=(0.0, 0.0))
                ctrl.stick("right", point=(0.0, 0.0))
            except Exception:
                pass
        else:
            await self._bridge.apply(Neutral())

    async def _play_keyframes(self, keyframes: list[dict[str, Any]]) -> None:
        t0 = time.monotonic()
        for kf in keyframes:
            target = float(kf.get("t_ms", 0)) / 1000.0
            delay = target - (time.monotonic() - t0)
            if delay > 0:
                await asyncio.sleep(delay)
            buttons = set(kf.get("buttons") or [])
            cur = self._bridge.get_state()
            for b in DualSenseButton:
                want = b.value in buttons
                have = b in cur.buttons
                if want and not have:
                    await self._bridge.apply(SetButton(b, True))
                elif have and not want:
                    await self._bridge.apply(SetButton(b, False))
            ls = kf.get("left_stick") or {"x": 0, "y": 0}
            rs = kf.get("right_stick") or {"x": 0, "y": 0}
            await self._bridge.apply(SetStick("left", float(ls.get("x", 0)), float(ls.get("y", 0))))
            await self._bridge.apply(SetStick("right", float(rs.get("x", 0)), float(rs.get("y", 0))))
        await self._bridge.apply(Neutral())

    async def _exec_webhook(self, node, props):
        import httpx

        url = str(props.get("url", ""))
        if not url.startswith(("http://", "https://")):
            raise GraphRunnerError("sys/webhook url must be http(s)")
        message = str(props.get("message", "Web2PS5 event"))
        include_shot = bool(props.get("screenshot", False))
        payload: dict[str, Any] = {"content": message, "run_id": self._run_id}
        files = None
        data = None
        if include_shot:
            snap = self._bridge.frames.get_latest()
            if snap is not None:
                ok, buf = cv2.imencode(".jpg", snap.image, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if ok:
                    # Discord-style multipart
                    files = {"file": ("screenshot.jpg", buf.tobytes(), "image/jpeg")}
                    data = {"content": message}
        async with httpx.AsyncClient(timeout=15.0) as client:
            if files:
                resp = await client.post(url, data=data, files=files)
            else:
                # Discord webhook JSON
                resp = await client.post(url, json=payload)
            if resp.status_code >= 400:
                raise GraphRunnerError(f"webhook failed: {resp.status_code} {resp.text[:200]}")
        return self._out(node, "EXEC")

    async def _exec_screenshot(self, node, props):
        snap = self._bridge.frames.get_latest()
        if snap is None:
            raise GraphRunnerError("no frame for screenshot")
        name = str(props.get("name", f"shot_{int(time.time())}"))
        path = settings.screenshots_dir / f"{name}.png"
        settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(cv2.imwrite, str(path), snap.image)
        self._set_data_out(node, "path", str(path))
        await self._hub.broadcast(
            {
                "type": "screenshot",
                "run_id": self._run_id,
                "path": str(path),
                "frame_id": snap.frame_id,
            }
        )
        return self._out(node, "EXEC")

    async def _exec_pwr_session(self, node, props):
        action = str(props.get("action", "connect"))
        if action == "connect":
            await self._bridge.connect()
        elif action == "disconnect":
            await self._bridge.disconnect()
        elif action == "standby":
            await self._bridge.standby()
        else:
            raise GraphRunnerError(f"unknown pwr/session action: {action}")
        return self._out(node, "EXEC")

    async def _exec_check_state(self, node, props):
        result = await self._match_once(node, props)
        self._set_data_out(node, "matched", bool(result["matched"]))
        self._set_data_out(node, "score", float(result["score"]))
        await self._hub.broadcast({"type": "match_score", "run_id": self._run_id, **result})
        return self._out(node, "EXEC")

    async def _ocr_once(self, node, props, *, frame=None) -> dict:
        from backend.app.vision.ocr import OcrUnavailableError, ocr_check
        from backend.app.vision.ocr_targets import load_ocr_meta, roi_tuple_from_meta

        ocr_id = str(
            self._resolve_input(
                node, "ocr_id", default=props.get("ocr_id") or props.get("id") or ""
            )
            or ""
        ).strip()
        meta = load_ocr_meta(ocr_id) if ocr_id else None

        expect = str(
            self._resolve_input(
                node,
                "expect",
                default=props.get("expect")
                if props.get("expect") not in (None, "")
                else (meta or {}).get("expect", ""),
            )
        )
        mode = str(
            props.get("mode")
            or (meta or {}).get("mode")
            or "contains"
        ).lower()
        if mode not in ("contains", "equals", "regex"):
            mode = "contains"
        lang = str(props.get("lang") or (meta or {}).get("lang") or "eng")
        invert = bool(
            props["invert"]
            if "invert" in props and props.get("invert") is not None
            else (meta or {}).get("invert", False)
        )
        case_sensitive = bool(
            props["case_sensitive"]
            if "case_sensitive" in props and props.get("case_sensitive") is not None
            else (meta or {}).get("case_sensitive", False)
        )
        psm = int(props.get("psm") or (meta or {}).get("psm") or 6)

        roi = parse_roi(self._resolve_input(node, "roi", default=props.get("roi")))
        if roi is None:
            roi = roi_tuple_from_meta(meta)

        if frame is None:
            snap = self._bridge.frames.get_latest()
            if snap is None:
                raise GraphRunnerError("no frame available")
            frame = snap.image
            frame_id = snap.frame_id
        else:
            frame_id = None

        try:
            result = await asyncio.to_thread(
                ocr_check,
                frame,
                expect,
                roi=roi,
                mode=mode,  # type: ignore[arg-type]
                lang=lang,
                invert=invert,
                case_sensitive=case_sensitive,
                psm=psm,
            )
        except OcrUnavailableError as exc:
            raise GraphRunnerError(str(exc)) from exc
        result["node_id"] = node["id"]
        result["frame_id"] = frame_id
        result["ocr_id"] = ocr_id or None
        result["expect"] = expect
        # Preview overlay uses the search ROI as a box
        if roi is not None:
            result["boxes"] = [
                {
                    "index": 0,
                    "x": int(roi[0]),
                    "y": int(roi[1]),
                    "w": int(roi[2]),
                    "h": int(roi[3]),
                    "score": 1.0 if result.get("matched") else 0.0,
                    "hit": bool(result.get("matched")),
                    "found": True,
                    "kind": "ocr",
                    "label": str(result.get("text") or "")[:48],
                    "expect": expect,
                }
            ]
            fh, fw = frame.shape[:2]
            result["frame_size"] = {"width": fw, "height": fh}
        else:
            result["boxes"] = []
        return result

    async def _exec_ocr_check(self, node, props):
        result = await self._ocr_once(node, props)
        self._set_data_out(node, "matched", bool(result["matched"]))
        self._set_data_out(node, "text", str(result.get("text") or ""))
        await self._hub.broadcast(
            {"type": "ocr_check", "run_id": self._run_id, **result}
        )
        return self._out(node, "EXEC")

    async def _exec_wait_ocr(self, node, props):
        timeout_ms = float(props.get("timeout_ms", 10000))
        poll_ms = float(props.get("poll_ms", 200))
        deadline = time.monotonic() + max(0.0, timeout_ms) / 1000.0
        prev_id = 0
        last = None
        while time.monotonic() < deadline:
            snap = await asyncio.to_thread(
                self._bridge.frames.wait_newer, prev_id, poll_ms / 1000.0
            )
            if snap is None:
                snap = self._bridge.frames.get_latest()
            if snap is not None:
                prev_id = snap.frame_id
                last = await self._ocr_once(node, props, frame=snap.image)
                last["frame_id"] = snap.frame_id
                await self._hub.broadcast(
                    {
                        "type": "ocr_wait_progress",
                        "run_id": self._run_id,
                        "node_id": node["id"],
                        "matched": last["matched"],
                        "text": last.get("text"),
                        "ocr_id": last.get("ocr_id"),
                        "expect": last.get("expect"),
                        "boxes": last.get("boxes") or [],
                        "frame_size": last.get("frame_size"),
                        "hits": 1 if last.get("matched") else 0,
                        "target_count": len(last.get("boxes") or []),
                        "remaining_ms": max(
                            0, int((deadline - time.monotonic()) * 1000)
                        ),
                    }
                )
                if last["matched"]:
                    self._set_data_out(node, "matched", True)
                    self._set_data_out(node, "text", str(last.get("text") or ""))
                    return self._out(node, "found")
            await asyncio.sleep(0)
        self._set_data_out(node, "matched", False)
        self._set_data_out(node, "text", str((last or {}).get("text") or ""))
        return self._out(node, "timeout")

    def _frame_slot_key(self, props: dict[str, Any]) -> str:
        name = str(props.get("name") or props.get("key") or "default").strip() or "default"
        return f"__frame_fp::{name}"

    async def _exec_frame_snapshot(self, node, props):
        from backend.app.vision.frame_diff import frame_fingerprint

        snap = self._bridge.frames.get_latest()
        if snap is None:
            raise GraphRunnerError("no frame available")
        fp = await asyncio.to_thread(frame_fingerprint, snap.image)
        key = self._frame_slot_key(props)
        self._vars[key] = fp
        await self._hub.broadcast(
            {
                "type": "frame_snapshot",
                "run_id": self._run_id,
                "node_id": node["id"],
                "name": key,
            }
        )
        return self._out(node, "EXEC")

    async def _exec_frame_changed(self, node, props):
        from backend.app.vision.frame_diff import frame_fingerprint, frames_differ

        snap = self._bridge.frames.get_latest()
        if snap is None:
            raise GraphRunnerError("no frame available")
        key = self._frame_slot_key(props)
        prev = self._vars.get(key)
        cur = await asyncio.to_thread(frame_fingerprint, snap.image)
        thr = float(props.get("threshold", 0.02) or 0.02)
        if prev is None:
            changed, score = True, 1.0
        else:
            changed, score = await asyncio.to_thread(
                frames_differ, prev, cur, threshold=thr
            )
        if bool(props.get("update", True)):
            self._vars[key] = cur
        self._set_data_out(node, "changed", bool(changed))
        self._set_data_out(node, "score", float(score))
        await self._hub.broadcast(
            {
                "type": "frame_changed",
                "run_id": self._run_id,
                "node_id": node["id"],
                "changed": bool(changed),
                "score": float(score),
                "threshold": thr,
            }
        )
        return self._out(node, "EXEC")

    async def _exec_wait_anchor(self, node, props):
        timeout_ms = float(props.get("timeout_ms", 10000))
        poll_ms = float(props.get("poll_ms", 100))
        deadline = time.monotonic() + max(0.0, timeout_ms) / 1000.0
        prev_id = 0
        last = None
        while time.monotonic() < deadline:
            snap = await asyncio.to_thread(
                self._bridge.frames.wait_newer, prev_id, poll_ms / 1000.0
            )
            if snap is None:
                snap = self._bridge.frames.get_latest()
            if snap is not None:
                prev_id = snap.frame_id
                last = await self._match_once(node, props, frame=snap.image, frame_id=snap.frame_id)
                await self._hub.broadcast(
                    {
                        "type": "wait_progress",
                        "run_id": self._run_id,
                        "node_id": node["id"],
                        "score": last["score"],
                        "matched": last["matched"],
                        "remaining_ms": max(0, int((deadline - time.monotonic()) * 1000)),
                    }
                )
                if last["matched"]:
                    self._set_data_out(node, "matched", True)
                    self._set_data_out(node, "score", last["score"])
                    return self._out(node, "found")
            await asyncio.sleep(0)  # allow cancel
        self._set_data_out(node, "matched", False)
        self._set_data_out(node, "score", float(last["score"]) if last else 0.0)
        return self._out(node, "timeout")

    async def _match_once(
        self,
        node: dict[str, Any],
        props: dict[str, Any],
        *,
        frame=None,
        frame_id: int | None = None,
    ) -> dict[str, Any]:
        from backend.app.vision.detect import detect_anchor_on_frame

        anchor_id = str(
            self._resolve_input(node, "anchor", default=props.get("anchor_id", "demo_bar"))
        )
        threshold = float(
            self._resolve_input(node, "threshold", default=props.get("threshold", 0.7))
        )
        roi = parse_roi(self._resolve_input(node, "roi", default=props.get("roi")))

        if frame is None:
            snap = self._bridge.frames.get_latest()
            if snap is None:
                raise GraphRunnerError("no frame available")
            frame = snap.image
            frame_id = snap.frame_id

        result = await asyncio.to_thread(
            detect_anchor_on_frame,
            frame,
            anchor_id,
            threshold=threshold,
            match_mode=props.get("match_mode"),
            match_count=props.get("match_count"),
            roi=roi,
        )
        if not result.get("ok"):
            raise GraphRunnerError(
                result.get("error") or f"anchor not found: {anchor_id}"
            )
        result["node_id"] = node["id"]
        result["frame_id"] = frame_id
        result["roi"] = list(roi) if roi else None
        return result

    def _out(self, node: dict[str, Any], name: str) -> tuple[str, int] | None:
        slot = self._exec_output_slot(node, name)
        return (name, slot) if slot is not None else None

    def _set_data_out(self, node: dict[str, Any], name: str, value: Any) -> None:
        slot = self._data_output_slot(node, name)
        if slot is not None:
            self._data[(int(node["id"]), slot)] = value

    def _resolve_input(self, node: dict[str, Any], name: str, default: Any = None) -> Any:
        inputs = node.get("inputs") or []
        for inp in inputs:
            if not isinstance(inp, dict) or inp.get("name") != name:
                continue
            link_id = inp.get("link")
            if link_id is None:
                return default
            link = self._link_by_id(int(link_id))
            if link is None:
                return default
            origin_id = int(link[1])
            origin_slot = int(link[2])
            key = (origin_id, origin_slot)
            if key in self._data:
                return self._data[key]
            return default
        return default

    def _follow_exec(
        self, origin_id: int, origin_slot: int | None, out_name: str
    ) -> int | None:
        if origin_slot is None:
            return None
        for link in self._links:
            if len(link) < 5:
                continue
            if int(link[1]) != int(origin_id) or int(link[2]) != int(origin_slot):
                continue
            link_type = str(link[5]) if len(link) > 5 else ""
            if link_type.upper() in {"BOOL", "FLOAT", "STRING", "VEC2", "VEC4"}:
                continue
            return int(link[3])
        return None

    def _link_by_id(self, link_id: int) -> list[Any] | None:
        for link in self._links:
            if link and int(link[0]) == link_id:
                return link
        return None

    def _first_exec_output_slot(self, node: dict[str, Any]) -> int | None:
        outputs = node.get("outputs") or []
        for idx, out in enumerate(outputs):
            if isinstance(out, dict) and self._is_exec_type(out.get("type"), out.get("name")):
                return idx
        return 0 if outputs else None

    def _exec_output_slot(self, node: dict[str, Any], name: str) -> int | None:
        outputs = node.get("outputs") or []
        for idx, out in enumerate(outputs):
            if isinstance(out, dict) and out.get("name") == name:
                return idx
        for idx, out in enumerate(outputs):
            if isinstance(out, dict) and self._is_exec_type(out.get("type"), out.get("name")):
                return idx
        return None

    def _data_output_slot(self, node: dict[str, Any], name: str) -> int | None:
        outputs = node.get("outputs") or []
        for idx, out in enumerate(outputs):
            if isinstance(out, dict) and out.get("name") == name:
                return idx
        return None

    @staticmethod
    def _is_exec_type(type_name: Any, slot_name: Any = None) -> bool:
        t = str(type_name or "").upper()
        n = str(slot_name or "").lower()
        if t in EXEC_TYPES:
            return True
        return n in {
            "exec",
            "true",
            "false",
            "found",
            "timeout",
            "body",
            "done",
            "success",
            "fail",
        }

    async def _emit(self, type_name: str, extra: dict[str, Any] | None = None) -> None:
        payload = {"type": type_name, "run_id": self._run_id}
        if extra:
            payload.update(extra)
        await self._hub.broadcast(payload)
