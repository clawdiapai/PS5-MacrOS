#!/usr/bin/env python3
"""OPEN FORTNITE: long-PS → seek with RIGHT (flip to LEFT at end) → OCR Fortnite → CROSS."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "graphs"

NODE_SLOTS = {
    "logic/start": {"inputs": [], "outputs": [("EXEC", "EXEC")]},
    "logic/branch": {
        "inputs": [("EXEC", "EXEC"), ("cond", "BOOL")],
        "outputs": [("true", "EXEC"), ("false", "EXEC")],
    },
    "logic/merge": {
        "inputs": [("a", "EXEC"), ("b", "EXEC")],
        "outputs": [("EXEC", "EXEC")],
    },
    "ds/press": {"inputs": [("EXEC", "EXEC")], "outputs": [("EXEC", "EXEC")]},
    "ds/delay": {"inputs": [("EXEC", "EXEC")], "outputs": [("EXEC", "EXEC")]},
    "vis/frame_snapshot": {"inputs": [("EXEC", "EXEC")], "outputs": [("EXEC", "EXEC")]},
    "vis/frame_changed": {
        "inputs": [("EXEC", "EXEC")],
        "outputs": [("EXEC", "EXEC"), ("changed", "BOOL"), ("score", "FLOAT")],
    },
    "vis/ocr_check": {
        "inputs": [
            ("EXEC", "EXEC"),
            ("ocr_id", "STRING"),
            ("expect", "STRING"),
            ("roi", "VEC4"),
        ],
        "outputs": [("EXEC", "EXEC"), ("matched", "BOOL"), ("text", "STRING")],
    },
    "sys/log": {"inputs": [("EXEC", "EXEC")], "outputs": [("EXEC", "EXEC")]},
    "ui/note": {"inputs": [], "outputs": []},
    "ui/preview": {"inputs": [], "outputs": []},
}


class GB:
    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.links: list[list] = []
        self._by: dict[int, dict] = {}
        self._n = 1
        self._l = 1

    def add(self, ntype, title, pos, props, size=None):
        slots = NODE_SLOTS[ntype]
        nid = self._n
        self._n += 1
        node = {
            "id": nid,
            "type": ntype,
            "pos": pos,
            "size": size or [180, 80],
            "flags": {},
            "order": 0,
            "mode": 0,
            "title": title,
            "properties": props,
            "inputs": [{"name": a, "type": b, "link": None} for a, b in slots["inputs"]],
            "outputs": [
                {"name": a, "type": b, "links": None} for a, b in slots["outputs"]
            ],
        }
        self.nodes.append(node)
        self._by[nid] = node
        return nid

    def connect(self, oid, oslot, tid, tslot, typ="EXEC"):
        lid = self._l
        self._l += 1
        self.links.append([lid, oid, oslot, tid, tslot, typ])
        out = self._by[oid]["outputs"][oslot]
        if out["links"] is None:
            out["links"] = []
        out["links"].append(lid)
        if self._by[tid]["inputs"][tslot]["link"] is not None:
            raise ValueError(f"input busy {self._by[tid]['title']} slot {tslot}")
        self._by[tid]["inputs"][tslot]["link"] = lid
        return lid

    def doc(self, name, note):
        return {
            "name": name,
            "version": 1,
            "note": note,
            "graph": {
                "last_node_id": self._n - 1,
                "last_link_id": self._l - 1,
                "nodes": self.nodes,
                "links": self.links,
                "groups": [],
                "config": {},
                "extra": {"source": "open_fortnite"},
                "version": 0.4,
            },
        }


def build_fixed():
    """Rebuild with merge before CROSS so both OCR paths can launch."""
    g = GB()
    P, D, L = [170, 70], [160, 70], [170, 80]

    g.add(
        "ui/note",
        "note",
        [40, 40],
        {
            "heading": "OPEN FORTNITE",
            "text": (
                "1) Long-press PS (700ms)\n"
                "2) RIGHT until OCR Fortnite — if screen stops changing, flip LEFT\n"
                "3) CROSS when OCR matches\n\n"
                "OCR target: fortnite_text (your boxed ROI)."
            ),
        },
        size=[400, 180],
    )
    g.add(
        "ui/preview",
        "ui.preview",
        [40, 260],
        {"live": True, "detections": True, "watch": ""},
        size=[400, 240],
    )

    x, y = 500.0, 80.0
    start = g.add("logic/start", "start", [x, y], {}, size=L)
    ps = g.add(
        "ds/press",
        "PS long 700ms",
        [x + 220, y],
        {"button": "ps", "duration_ms": 700},
        size=P,
    )
    g.connect(start, 0, ps, 0)
    d0 = g.add("ds/delay", "settle 500ms", [x + 460, y], {"ms": 500}, size=D)
    g.connect(ps, 0, d0, 0)

    # RIGHT loop
    y_r = y + 160
    g.add(
        "ui/note",
        "note.right",
        [x, y_r - 70],
        {"heading": "Seek RIGHT", "text": "OCR miss → keep RIGHT. No screen change → LEFT."},
        size=[340, 55],
    )
    merge_r = g.add("logic/merge", "merge.right_loop", [x, y_r], {}, size=L)
    g.connect(d0, 0, merge_r, 0)

    snap_r = g.add(
        "vis/frame_snapshot", "snap before RIGHT", [x + 240, y_r], {"name": "nav"}, size=L
    )
    g.connect(merge_r, 0, snap_r, 0)
    right = g.add(
        "ds/press", "RIGHT", [x + 500, y_r], {"button": "right", "duration_ms": 120}, size=P
    )
    g.connect(snap_r, 0, right, 0)
    d_r = g.add("ds/delay", "after RIGHT", [x + 720, y_r], {"ms": 350}, size=D)
    g.connect(right, 0, d_r, 0)
    ch_r = g.add(
        "vis/frame_changed",
        "moved after RIGHT?",
        [x + 960, y_r],
        {"name": "nav", "threshold": 0.02, "update": True},
        size=[200, 90],
    )
    g.connect(d_r, 0, ch_r, 0)
    br_ch_r = g.add("logic/branch", "branch.RIGHT moved?", [x + 1240, y_r], {}, size=L)
    g.connect(ch_r, 0, br_ch_r, 0)
    g.connect(ch_r, 1, br_ch_r, 1, "BOOL")

    ocr_r = g.add(
        "vis/ocr_check",
        "ocr Fortnite?",
        [x + 1500, y_r - 30],
        {
            "ocr_id": "fortnite_text",
            "expect": "Fortnite",
            "mode": "contains",
            "lang": "eng",
            "invert": False,
            "targets": [],
            "edit_mode": "edit",
            "capture_hint": "fortnite_text",
        },
        size=[260, 110],
    )
    g.connect(br_ch_r, 0, ocr_r, 0)
    br_ocr_r = g.add("logic/branch", "branch.OCR R?", [x + 1840, y_r - 30], {}, size=L)
    g.connect(ocr_r, 0, br_ocr_r, 0)
    g.connect(ocr_r, 1, br_ocr_r, 1, "BOOL")
    g.connect(br_ocr_r, 1, merge_r, 1)  # OCR miss → keep RIGHT

    # LEFT loop
    y_l = y_r + 220
    g.add(
        "ui/note",
        "note.left",
        [x, y_l - 70],
        {
            "heading": "Seek LEFT",
            "text": "RIGHT hit the end (no frame change). Travel LEFT.",
        },
        size=[340, 55],
    )
    merge_l = g.add("logic/merge", "merge.left_loop", [x, y_l], {}, size=L)
    g.connect(br_ch_r, 1, merge_l, 0)  # wall on RIGHT

    snap_l = g.add(
        "vis/frame_snapshot", "snap before LEFT", [x + 240, y_l], {"name": "nav"}, size=L
    )
    g.connect(merge_l, 0, snap_l, 0)
    left = g.add(
        "ds/press", "LEFT", [x + 500, y_l], {"button": "left", "duration_ms": 120}, size=P
    )
    g.connect(snap_l, 0, left, 0)
    d_l = g.add("ds/delay", "after LEFT", [x + 720, y_l], {"ms": 350}, size=D)
    g.connect(left, 0, d_l, 0)
    ch_l = g.add(
        "vis/frame_changed",
        "moved after LEFT?",
        [x + 960, y_l],
        {"name": "nav", "threshold": 0.02, "update": True},
        size=[200, 90],
    )
    g.connect(d_l, 0, ch_l, 0)
    br_ch_l = g.add("logic/branch", "branch.LEFT moved?", [x + 1240, y_l], {}, size=L)
    g.connect(ch_l, 0, br_ch_l, 0)
    g.connect(ch_l, 1, br_ch_l, 1, "BOOL")

    log_fail = g.add(
        "sys/log",
        "FAIL: not found",
        [x + 1500, y_l + 130],
        {"message": "OPEN FORTNITE: both ends reached without Fortnite OCR"},
        size=[320, 90],
    )
    g.connect(br_ch_l, 1, log_fail, 0)

    ocr_l = g.add(
        "vis/ocr_check",
        "ocr Fortnite? L",
        [x + 1500, y_l - 30],
        {
            "ocr_id": "fortnite_text",
            "expect": "Fortnite",
            "mode": "contains",
            "lang": "eng",
            "invert": False,
            "targets": [],
            "edit_mode": "edit",
            "capture_hint": "fortnite_text",
        },
        size=[260, 110],
    )
    g.connect(br_ch_l, 0, ocr_l, 0)
    br_ocr_l = g.add("logic/branch", "branch.OCR L?", [x + 1840, y_l - 30], {}, size=L)
    g.connect(ocr_l, 0, br_ocr_l, 0)
    g.connect(ocr_l, 1, br_ocr_l, 1, "BOOL")
    g.connect(br_ocr_l, 1, merge_l, 1)  # OCR miss → keep LEFT

    # Launch merge (OCR hit from R or L)
    merge_go = g.add("logic/merge", "merge.launch", [x + 2100, y_r + 80], {}, size=L)
    g.connect(br_ocr_r, 0, merge_go, 0)
    g.connect(br_ocr_l, 0, merge_go, 1)

    cross = g.add(
        "ds/press",
        "CROSS open",
        [x + 2340, y_r + 80],
        {"button": "cross", "duration_ms": 120},
        size=P,
    )
    g.connect(merge_go, 0, cross, 0)
    d_ok = g.add("ds/delay", "after CROSS", [x + 2580, y_r + 80], {"ms": 400}, size=D)
    g.connect(cross, 0, d_ok, 0)
    log_ok = g.add(
        "sys/log",
        "OK: opened Fortnite",
        [x + 2820, y_r + 80],
        {"message": "OPEN FORTNITE: CROSS on Fortnite"},
        size=[240, 80],
    )
    g.connect(d_ok, 0, log_ok, 0)

    return g.doc(
        "open_fortnite",
        "Long-PS → RIGHT seek (flip LEFT at end) → OCR fortnite_text → CROSS.",
    )


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    doc = build_fixed()
    path = OUT / "open_fortnite.json"
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(f"wrote {path} nodes={len(doc['graph']['nodes'])} links={len(doc['graph']['links'])}")


if __name__ == "__main__":
    main()
