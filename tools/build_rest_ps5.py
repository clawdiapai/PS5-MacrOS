#!/usr/bin/env python3
"""Scaffold REST-PS5: placeholder anchors + compact editable graph rest_ps5.json."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_ANCHORS = ROOT / "data" / "anchors"
OUT_GRAPHS = ROOT / "data" / "graphs"

PLACEHOLDERS = [
    {
        "id": "rest_ps_menu_open",
        "from": "01_STARTING.png",
        "note": "PLACEHOLDER — Freeze Control Center / PS menu open chrome",
    },
    {
        "id": "rest_power_icon_selected",
        "from": "00_START_FORTNITE.png",
        "note": "PLACEHOLDER — Freeze power icon SELECTED on CC bottom row",
    },
    {
        "id": "rest_power_menu",
        "from": "26_DISMISS_MODAL.png",
        "note": "PLACEHOLDER — Freeze power options sheet (Rest Mode visible)",
    },
]

NODE_SLOTS: dict[str, dict[str, list[tuple[str, str]]]] = {
    "logic/start": {"inputs": [], "outputs": [("EXEC", "EXEC")]},
    "logic/branch": {
        "inputs": [("EXEC", "EXEC"), ("cond", "BOOL")],
        "outputs": [("true", "EXEC"), ("false", "EXEC")],
    },
    "logic/merge": {
        "inputs": [("a", "EXEC"), ("b", "EXEC")],
        "outputs": [("EXEC", "EXEC")],
    },
    "logic/repeat": {
        "inputs": [("EXEC", "EXEC")],
        "outputs": [("body", "EXEC"), ("done", "EXEC"), ("index", "FLOAT")],
    },
    "vis/check_state": {
        "inputs": [("EXEC", "EXEC"), ("anchor", "STRING"), ("roi", "VEC4")],
        "outputs": [("EXEC", "EXEC"), ("matched", "BOOL"), ("score", "FLOAT")],
    },
    "vis/wait_anchor": {
        "inputs": [("EXEC", "EXEC"), ("anchor", "STRING"), ("roi", "VEC4")],
        "outputs": [
            ("found", "EXEC"),
            ("timeout", "EXEC"),
            ("matched", "BOOL"),
            ("score", "FLOAT"),
        ],
    },
    "ds/press": {"inputs": [("EXEC", "EXEC")], "outputs": [("EXEC", "EXEC")]},
    "ds/delay": {"inputs": [("EXEC", "EXEC")], "outputs": [("EXEC", "EXEC")]},
    "sys/log": {"inputs": [("EXEC", "EXEC")], "outputs": [("EXEC", "EXEC")]},
    "ui/note": {"inputs": [], "outputs": []},
    "ui/preview": {"inputs": [], "outputs": []},
}


class GraphBuilder:
    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.links: list[list] = []
        self._by_id: dict[int, dict] = {}
        self._nid = 1
        self._lid = 1

    def add(
        self,
        ntype: str,
        title: str,
        pos: list[float],
        props: dict,
        *,
        size: list[float] | None = None,
    ) -> int:
        slots = NODE_SLOTS[ntype]
        nid = self._nid
        self._nid += 1
        # Collapse heavy capture nodes by default so the flow stays readable;
        # double-click the title bar in LiteGraph to expand for Freeze/edit.
        collapsed = ntype in ("vis/check_state", "vis/wait_anchor")
        node = {
            "id": nid,
            "type": ntype,
            "pos": pos,
            "size": size or [180, 80],
            "flags": {"collapsed": True} if collapsed else {},
            "order": 0,
            "mode": 0,
            "title": title,
            "properties": props,
            "inputs": [
                {"name": n, "type": t, "link": None} for n, t in slots["inputs"]
            ],
            "outputs": [
                {"name": n, "type": t, "links": None} for n, t in slots["outputs"]
            ],
        }
        self.nodes.append(node)
        self._by_id[nid] = node
        return nid

    def connect(
        self,
        origin_id: int,
        origin_slot: int,
        target_id: int,
        target_slot: int,
        typ: str = "EXEC",
    ) -> int:
        origin = self._by_id[origin_id]
        target = self._by_id[target_id]
        if target["inputs"][target_slot]["link"] is not None:
            raise ValueError(
                f"input {target_slot} on node {target_id} ({target['title']}) already linked"
            )
        lid = self._lid
        self._lid += 1
        self.links.append([lid, origin_id, origin_slot, target_id, target_slot, typ])
        out = origin["outputs"][origin_slot]
        if out["links"] is None:
            out["links"] = []
        out["links"].append(lid)
        target["inputs"][target_slot]["link"] = lid
        return lid

    def document(self, name: str, note: str) -> dict:
        return {
            "name": name,
            "version": 1,
            "note": note,
            "graph": {
                "last_node_id": self._nid - 1,
                "last_link_id": self._lid - 1,
                "nodes": self.nodes,
                "links": self.links,
                "groups": [],
                "config": {},
                "extra": {"source": "rest_ps5_scaffold", "editable": True},
                "version": 0.4,
            },
        }


def ensure_placeholders() -> None:
    """Create missing scaffold anchors only — never overwrite a user Freeze."""
    OUT_ANCHORS.mkdir(parents=True, exist_ok=True)
    for item in PLACEHOLDERS:
        dest = OUT_ANCHORS / f"{item['id']}.png"
        meta_path = OUT_ANCHORS / f"{item['id']}.json"
        if dest.is_file() and meta_path.is_file():
            try:
                existing = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = {}
            # Keep anything the user has captured (full frame) or non-scaffold meta
            if existing.get("has_full") or existing.get("source") != "rest_ps5_scaffold":
                print("anchor", item["id"], "kept (user/captured)")
                continue
            if existing.get("source") == "rest_ps5_scaffold":
                print("anchor", item["id"], "kept (scaffold already present)")
                continue
        src = OUT_ANCHORS / item["from"]
        if not src.is_file():
            pngs = sorted(
                p for p in OUT_ANCHORS.glob("*.png") if not p.stem.endswith("_full")
            )
            if not pngs:
                raise SystemExit(f"no source png for {item['id']}")
            src = pngs[0]
        shutil.copy2(src, dest)
        meta = {
            "id": item["id"],
            "threshold": 0.8,
            "legacy": True,
            "has_full": False,
            "full": None,
            "crop": {"x": 0, "y": 0, "w": 1, "h": 1},
            "crops": [{"x": 0, "y": 0, "w": 1, "h": 1}],
            "target_count": 1,
            "match_mode": "all",
            "match_count": 1,
            "frame_size": {"width": 1280, "height": 720},
            "source": "rest_ps5_scaffold",
            "note": item["note"],
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        print("anchor", item["id"], "←", src.name)


def build_graph() -> dict:
    """Brick 1 (CC open/reset) + Brick 2 (DOWN then RIGHT until power)."""
    g = GraphBuilder()

    CHK = [240, 110]
    PRESS = [170, 70]
    DELAY = [160, 70]
    LOGIC = [180, 80]

    # Tools (left)
    g.add(
        "ui/note",
        "note.overview",
        [40, 40],
        {
            "heading": "REST-PS5 — Bricks 1–3",
            "text": (
                "1) ps-menu-icon → PS×2 or PS×1\n"
                "2) DOWN → RIGHT until power-icon-selected\n"
                "3) CROSS → wait power menu → CROSS (Rest)\n\n"
                "Freeze rest_power_menu while the Rest sheet is open."
            ),
        },
        size=[360, 200],
    )
    g.add(
        "ui/preview",
        "ui.preview",
        [40, 280],
        {"live": True, "detections": True, "watch": ""},
        size=[360, 240],
    )

    x = 480.0
    y = 120.0

    g.add(
        "ui/note",
        "note.brick1",
        [x, 40],
        {
            "heading": "Brick 1 — Control Center",
            "text": (
                "TRUE = open → PS → delay → PS → delay\n"
                "FALSE = closed → PS → delay\n"
                "Both join → Brick 2"
            ),
        },
        size=[520, 100],
    )

    start = g.add("logic/start", "start", [x, y], {}, size=LOGIC)

    check_menu = g.add(
        "vis/check_state",
        "check.menu_open?",
        [x + 260, y],
        {
            "anchor_id": "ps-menu-icon",
            "threshold": 0.8,
            "roi": None,
            "match_mode": "any",
            "match_count": 1,
            "targets": [],
            "edit_mode": "create",
            "capture_hint": "ps-menu-icon — any of 3 crops = CC open",
        },
        size=CHK,
    )
    g.connect(start, 0, check_menu, 0)

    branch = g.add(
        "logic/branch", "branch.menu_open?", [x + 580, y], {}, size=LOGIC
    )
    g.connect(check_menu, 0, branch, 0)
    g.connect(check_menu, 1, branch, 1, "BOOL")

    # TRUE: already open → close + reopen
    yt = y - 200
    g.add(
        "ui/note",
        "note.true",
        [x + 820, yt - 70],
        {
            "heading": "TRUE — menu already open",
            "text": "PS closes it, PS opens it again (cursor reset to top).",
        },
        size=[340, 60],
    )
    ps_close = g.add(
        "ds/press",
        "PS (close)",
        [x + 820, yt],
        {"button": "ps", "duration_ms": 120},
        size=PRESS,
    )
    g.connect(branch, 0, ps_close, 0)
    d_close = g.add(
        "ds/delay", "delay 600ms", [x + 1080, yt], {"ms": 600}, size=DELAY
    )
    g.connect(ps_close, 0, d_close, 0)
    ps_reopen = g.add(
        "ds/press",
        "PS (reopen)",
        [x + 1340, yt],
        {"button": "ps", "duration_ms": 120},
        size=PRESS,
    )
    g.connect(d_close, 0, ps_reopen, 0)
    d_reopen = g.add(
        "ds/delay", "delay 700ms", [x + 1600, yt], {"ms": 700}, size=DELAY
    )
    g.connect(ps_reopen, 0, d_reopen, 0)

    # FALSE: closed → open once
    yf = y + 220
    g.add(
        "ui/note",
        "note.false",
        [x + 820, yf - 70],
        {
            "heading": "FALSE — menu not on screen",
            "text": "Press PS once to open Control Center.",
        },
        size=[340, 60],
    )
    ps_open = g.add(
        "ds/press",
        "PS (open)",
        [x + 820, yf],
        {"button": "ps", "duration_ms": 120},
        size=PRESS,
    )
    g.connect(branch, 1, ps_open, 0)
    d_open = g.add(
        "ds/delay", "delay 700ms ", [x + 1080, yf], {"ms": 700}, size=DELAY
    )
    g.connect(ps_open, 0, d_open, 0)

    # Join brick 1
    y_join = yf + 160
    merge = g.add(
        "logic/merge", "merge.menu_ready", [x + 1600, y_join], {}, size=LOGIC
    )
    g.connect(d_reopen, 0, merge, 0)
    g.connect(d_open, 0, merge, 1)

    # ========== BRICK 2 ==========
    y2 = y_join + 220
    g.add(
        "ui/note",
        "note.brick2",
        [x, y2],
        {
            "heading": "Brick 2 — DOWN, then RIGHT to power",
            "text": (
                "1) DPAD DOWN (leave top row → bottom icons)\n"
                "2) Loop ≤12: if power-icon-selected → Brick 3; else RIGHT\n"
                "Uses your Freeze: power-icon-selected"
            ),
        },
        size=[480, 120],
    )

    y = y2 + 160
    press_down = g.add(
        "ds/press",
        "DOWN",
        [x, y],
        {"button": "down", "duration_ms": 120},
        size=PRESS,
    )
    g.connect(merge, 0, press_down, 0)
    d_down = g.add(
        "ds/delay", "delay after DOWN", [x + 260, y], {"ms": 450}, size=DELAY
    )
    g.connect(press_down, 0, d_down, 0)

    # merge: first entry after DOWN, or loop-back after RIGHT
    merge_loop = g.add(
        "logic/merge", "merge.search_loop", [x + 520, y], {}, size=LOGIC
    )
    g.connect(d_down, 0, merge_loop, 0)

    repeat = g.add(
        "logic/repeat",
        "repeat ×12",
        [x + 780, y],
        {"times": 12},
        size=LOGIC,
    )
    g.connect(merge_loop, 0, repeat, 0)

    check_power = g.add(
        "vis/check_state",
        "check.power_selected?",
        [x + 1060, y],
        {
            "anchor_id": "power-icon-selected",
            "threshold": 0.8,
            "roi": None,
            "match_mode": "all",
            "match_count": 1,
            "targets": [],
            "edit_mode": "create",
            "capture_hint": "power-icon-selected — bottom-row power focused",
        },
        size=CHK,
    )
    g.connect(repeat, 0, check_power, 0)

    branch_power = g.add(
        "logic/branch", "branch.on_power?", [x + 1400, y], {}, size=LOGIC
    )
    g.connect(check_power, 0, branch_power, 0)
    g.connect(check_power, 1, branch_power, 1, "BOOL")

    # FALSE → RIGHT → loop
    y_nudge = y + 200
    g.add(
        "ui/note",
        "note.nudge",
        [x + 1400, y_nudge - 70],
        {
            "heading": "FALSE — not on power",
            "text": "Press RIGHT, wait, loop back.",
        },
        size=[280, 60],
    )
    press_right = g.add(
        "ds/press",
        "RIGHT",
        [x + 1400, y_nudge],
        {"button": "right", "duration_ms": 100},
        size=PRESS,
    )
    g.connect(branch_power, 1, press_right, 0)
    d_right = g.add(
        "ds/delay", "delay after RIGHT", [x + 1660, y_nudge], {"ms": 350}, size=DELAY
    )
    g.connect(press_right, 0, d_right, 0)
    g.connect(d_right, 0, merge_loop, 1)

    log_fail = g.add(
        "sys/log",
        "FAIL: no power",
        [x + 780, y_nudge + 120],
        {"message": "REST-PS5 brick2: power icon not found after 12 RIGHTs"},
        size=[300, 90],
    )
    g.connect(repeat, 1, log_fail, 0)

    # ========== BRICK 3 — Rest ==========
    y3 = y_nudge + 280
    g.add(
        "ui/note",
        "note.brick3",
        [x, y3],
        {
            "heading": "Brick 3 — open power sheet → Rest",
            "text": (
                "CROSS opens the power options sheet.\n"
                "wait.rest_power_menu confirms it (Freeze that anchor).\n"
                "Second CROSS sends Rest Mode."
            ),
        },
        size=[480, 110],
    )

    y = y3 + 150
    cross1 = g.add(
        "ds/press",
        "CROSS open sheet",
        [x, y],
        {"button": "cross", "duration_ms": 120},
        size=PRESS,
    )
    g.connect(branch_power, 0, cross1, 0)

    d_sheet = g.add(
        "ds/delay", "delay before wait", [x + 260, y], {"ms": 400}, size=DELAY
    )
    g.connect(cross1, 0, d_sheet, 0)

    WAIT = [240, 120]
    wait_menu = g.add(
        "vis/wait_anchor",
        "wait.power_menu?",
        [x + 520, y],
        {
            "anchor_id": "rest_power_menu",
            "threshold": 0.75,
            "timeout_ms": 5000,
            "poll_ms": 100,
            "roi": None,
            "match_mode": "all",
            "match_count": 1,
            "targets": [],
            "edit_mode": "create",
            "capture_hint": "Freeze power options sheet (Rest Mode visible)",
        },
        size=WAIT,
    )
    g.connect(d_sheet, 0, wait_menu, 0)

    cross2 = g.add(
        "ds/press",
        "CROSS Rest",
        [x + 860, y],
        {"button": "cross", "duration_ms": 120},
        size=PRESS,
    )
    g.connect(wait_menu, 0, cross2, 0)  # found only

    d_done = g.add(
        "ds/delay", "delay after Rest", [x + 1120, y], {"ms": 500}, size=DELAY
    )
    g.connect(cross2, 0, d_done, 0)

    log_ok = g.add(
        "sys/log",
        "OK: Rest sent",
        [x + 1380, y],
        {"message": "REST-PS5 brick3: Rest requested"},
        size=[240, 80],
    )
    g.connect(d_done, 0, log_ok, 0)

    log_no_sheet = g.add(
        "sys/log",
        "FAIL: no power menu",
        [x + 520, y + 180],
        {"message": "REST-PS5 brick3: power menu did not appear after CROSS"},
        size=[320, 90],
    )
    g.connect(wait_menu, 1, log_no_sheet, 0)  # timeout

    return g.document(
        "rest_ps5",
        "REST-PS5: CC reset → DOWN/RIGHT to power-icon-selected → CROSS → wait rest_power_menu → CROSS Rest.",
    )


def main() -> None:
    ensure_placeholders()
    OUT_GRAPHS.mkdir(parents=True, exist_ok=True)
    doc = build_graph()
    path = OUT_GRAPHS / "rest_ps5.json"
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    gr = doc["graph"]
    print(f"wrote {path} nodes={len(gr['nodes'])} links={len(gr['links'])}")


if __name__ == "__main__":
    main()
