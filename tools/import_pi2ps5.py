#!/usr/bin/env python3
"""Import pi2ps5 states/macros into Web2PS5 as LEGACY anchors + editable graphs.

- Templates → data/anchors/{state_id}.png (+ _tN for fallback/secondary)
- Meta tagged legacy:true, has_full:false; ROI converted [y1,y2,x1,x2]→[x,y,w,h]
- keyboard_macro.json + MACRO_SEQUENCE → data/macros/*.json (event timelines)
- Linear STW path → data/graphs/stw_endurance_path.json (editable litegraph nodes)

Does NOT invent a priority scanner or DISCOVER_NAVIGATION node.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PI2 = Path(r"C:\Users\Uzzo\Documents\pi2ps5")
PI2_ANCHORS = PI2 / "anchors"
OUT_ANCHORS = ROOT / "data" / "anchors"
OUT_MACROS = ROOT / "data" / "macros"
OUT_GRAPHS = ROOT / "data" / "graphs"

# Config template name → on-disk file used by vision_pilot/capture runtime
TEMPLATE_ALIAS: dict[str, str] = {
    "anchor_press_start.png": "anchor_press_start_x.png",
    "home_icon_selected.png": "anchor_01_starting.png",
    "home_icon_unselected.png": "anchor_01_starting_v2.png",
    "play_tab.png": "anchor_02_play.png",
    "stw_logo.png": "anchor_stw_title.png",
    "connecting_text.png": "anchor_connecting.png",
    "connecting_lobby.png": "anchor_connecting_lobby.png",
    "anchor_yellow_play_button.png": "anchor_yellow_play.png",
    "anchor_collect_rewards.png": "anchor_collect_all.png",
    "anchor_hestia_logo.png": "anchor_08_hestia.png",
    "anchor_world_twine_logo.png": "anchor_world_twine.png",
    "anchor_stonewood_logo.png": "anchor_stonewood_map.png",
    "anchor_twine_peaks_selected.png": "anchor_twine_title.png",
    "anchor_community_lookout_square.png": "anchor_community_lookout.png",
    "anchor_yellow_launch_triangle.png": "anchor_yellow_launch.png",
    "anchor_activate_storm_shield.png": "anchor_activate_shield.png",
    "anchor_storm_shield_menu.png": "anchor_card_endurance.png",
    "anchor_endurance_modal_title.png": "anchor_endurance_modal_title.png",
    "anchor_storm_shield_confirm.png": "anchor_start_endurance.png",
    "anchor_endurance_between_defense.png": "anchor_endurance_defense.png",
    "anchor_endurance_active.png": "anchor_endurance_word.png",
    "anchor_storm_shield_active_title.png": "anchor_storm_shield_title.png",
    "anchor_endurance_ended_team_score.png": "anchor_team_score.png",
    "anchor_matchmake_homebase_circle.png": "anchor_matchmake_homebase.png",
    "anchor_rewards_continue_cross.png": "anchor_rewards_continue.png",
    "anchor_inventory_top_text.png": "anchor_inventory_tab.png",
    "anchor_starting_storm_shield_yellow.png": "anchor_starting_shield.png",
    "anchor_cancel_matchmaking.png": "anchor_cancel_button.png",
    "anchor_claim_button.png": "anchor_claim_button.png",
    "anchor_dismiss_modal.png": "anchor_dismiss_modal.png",
    "anchor_survey_skip.png": "anchor_survey_skip.png",
    "anchor_search_islands_results.png": "anchor_search_islands_results.png",
    "anchor_search_stw_card.png": "anchor_search_stw_card.png",
    "anchor_keyboard_open.png": "anchor_keyboard_open.png",
    "anchor_search_bar_focused.png": "anchor_search_bar_focused.png",
    "anchor_quests_tab.png": "anchor_quests_tab.png",
    "anchor_play_with_others.png": "anchor_play_with_others.png",
    "anchor_rewards_open.png": "anchor_rewards_open.png",
}

# Prefer live runtime button choices when they disagree with states_config
RUNTIME_ACTIONS: dict[str, dict] = {
    "01_STARTING": {"type": "BUTTON_CLICK", "button": "circle", "delay_after": 2.0},
    "25_SURVEY_SKIP": {"type": "BUTTON_CLICK", "button": "triangle", "delay_after": 1.0},
    "26_DISMISS_MODAL": {
        "type": "MACRO_SEQUENCE",
        "steps": [
            {"btn": "DOWN", "press_ms": 100, "wait_ms": 150},
            {"btn": "CROSS", "press_ms": 120, "wait_ms": 500},
        ],
    },
    "07_STW_COLLECT": {"type": "BUTTON_CLICK", "button": "triangle", "delay_after": 1.0},
    "08_HESTIA": {"type": "BUTTON_CLICK", "button": "touchpad", "delay_after": 1.5},
    "16_SHIELD_NOT_STARTED": {"type": "BUTTON_CLICK", "button": "up", "delay_after": 1.0},
    "11_TWINE_MAP": {
        "type": "MACRO_SEQUENCE",
        "steps": [
            {"btn": "RIGHT", "press_ms": 100, "wait_ms": 200},
            {"btn": "CROSS", "press_ms": 120, "wait_ms": 500},
        ],
    },
}

# Extra Discover helper templates (for later DISCOVER_NAV design; still LEGACY)
DISCOVER_HELPERS = [
    ("02_LOBBY", "play_tab.png"),
    ("02_LOBBY_CAROUSEL", "anchor_stw_carousel_card.png"),
    ("02_LOBBY_CAROUSEL_HI", "anchor_stw_carousel_card_hi.png"),
    ("02_LOBBY_MODE_TITLE", "anchor_stw_mode_title.png"),
    ("02_LOBBY_FOCUS_CORNER", "anchor_card_focus_corner.png"),
    ("02_DISCOVER_TAB", "anchor_discover_tab.png"),
]

# Per-state annotations for ui/note nodes (what to match + what the graph does)
SCENE_NOTES: dict[str, dict[str, str]] = {
    "00_START_FORTNITE": {
        "heading": "00 — Fortnite title",
        "text": (
            "MATCH: 'Press X to Start' / title splash (bottom-center).\n"
            "THEN: press CROSS, wait 1.5s.\n"
            "RETAKE: full title screen with the press-start prompt visible."
        ),
    },
    "01_STARTING": {
        "heading": "01 — PS5 home / Fortnite icon",
        "text": (
            "MATCH: Fortnite icon on PS5 home (top-left tile area); fallback = unselected icon.\n"
            "THEN: press CIRCLE (runtime; config said CROSS).\n"
            "RETAKE: home row with Fortnite focused or unfocused."
        ),
    },
    "28_DISCOVER_SEARCH_FOCUSED": {
        "heading": "28 — Discover search focused",
        "text": (
            "MATCH: Discover search bar focused (top-left search field glow).\n"
            "THEN: CROSS opens on-screen keyboard.\n"
            "RETAKE: Discover with search field active/highlighted."
        ),
    },
    "29_DISCOVER_KEYBOARD": {
        "heading": "29 — Virtual keyboard macro",
        "text": (
            "MATCH: PS5 OSK / keyboard panel open (mid screen).\n"
            "THEN: macro_block types SAVE THE WORLD then R2 submit (~15s timeline).\n"
            "RETAKE: full keyboard visible; keep crop of keyboard chrome."
        ),
    },
    "30_SEARCH_RESULTS": {
        "heading": "30 — Search results → STW",
        "text": (
            "MATCH: Islands search results header OR STW result card (any).\n"
            "THEN: DOWN, DOWN, CROSS, CROSS to open first card.\n"
            "RETAKE: results list after searching Save The World."
        ),
    },
    "04_STW_READY": {
        "heading": "04 — STW lobby ready",
        "text": (
            "MATCH: STW title AND yellow Play (all / both templates).\n"
            "THEN: TRIANGLE to launch/queue.\n"
            "RETAKE: STW main lobby with yellow Play ready."
        ),
    },
    "05_STW_QUEUED": {
        "heading": "05 — STW queued (wait)",
        "text": (
            "MATCH: STW title AND cancel-matchmaking control (both).\n"
            "THEN: hold/wait only — no press.\n"
            "RETAKE: matchmaking / queued lobby with Cancel visible."
        ),
    },
    "06_CONNECTING": {
        "heading": "06 — Connecting (wait)",
        "text": (
            "MATCH: 'Connecting' text (bottom-left) OR lobby connecting art (any).\n"
            "THEN: wait/hold through load.\n"
            "RETAKE: connecting / loading into Fortnite."
        ),
    },
    "07_STW_COLLECT": {
        "heading": "07 — Collect rewards",
        "text": (
            "MATCH: Collect-all / rewards prompt (bottom-right).\n"
            "THEN: TRIANGLE (runtime; config said SQUARE).\n"
            "RETAKE: post-mission chest / collect-all HUD."
        ),
    },
    "08_HESTIA": {
        "heading": "08 — Hestia room",
        "text": (
            "MATCH: Hestia logo / blue load room (bottom-right).\n"
            "THEN: TOUCHPAD (runtime; config said CROSS).\n"
            "RETAKE: Hestia spawn / blue interstitial."
        ),
    },
    "09_OLD_LOBBY_QUESTS": {
        "heading": "09 — Quests tab → Map",
        "text": (
            "MATCH: Quests tab selected in old STW lobby (top tabs).\n"
            "THEN: R1 to move to Map tab.\n"
            "RETAKE: lobby with Quests tab active."
        ),
    },
    "10_OLD_LOBBY_MAP": {
        "heading": "10a — Stonewood on world map",
        "text": (
            "MATCH: Stonewood logo on world map (left/mid).\n"
            "THEN: RIGHT×3 + CROSS toward Twine.\n"
            "RETAKE: world map focused on Stonewood."
        ),
    },
    "10_TWINE_WORLD_MAP": {
        "heading": "10b — Twine on world map",
        "text": (
            "MATCH: Twine Peaks logo highlighted on world map.\n"
            "THEN: CROSS to enter Twine.\n"
            "RETAKE: world map with Twine selected."
        ),
    },
    "11_TWINE_MAP": {
        "heading": "11 — Twine zone map",
        "text": (
            "MATCH: 'Play with Others' / Twine zone chrome (bottom-left).\n"
            "THEN: RIGHT + CROSS (runtime; config said UP+CROSS) to Storm Shield.\n"
            "RETAKE: Twine zone map with PWO / SS node visible."
        ),
    },
    "12_TWINE_SELECTED": {
        "heading": "12 — Twine Storm Shield selected",
        "text": (
            "MATCH: Twine Storm Shield node selected (bottom-right panel).\n"
            "THEN: CROSS.\n"
            "RETAKE: SS node highlighted on Twine map."
        ),
    },
    "13_COMMUNITY_LOOKOUT": {
        "heading": "13 — Community Lookout modal",
        "text": (
            "MATCH: blue Community Lookout / launch modal (bottom-right).\n"
            "THEN: SQUARE.\n"
            "RETAKE: that blue launch modal fully visible."
        ),
    },
    "15_STW_FINAL_LAUNCH": {
        "heading": "15 — Yellow Launch",
        "text": (
            "MATCH: yellow Launch prompt (bottom-right; triangle hint).\n"
            "THEN: TRIANGLE.\n"
            "RETAKE: STW lobby yellow Launch ready."
        ),
    },
    "14_TRAVELLING_LOBBY": {
        "heading": "14 — Travelling (wait)",
        "text": (
            "MATCH: 'Starting Storm Shield' / travelling yellow banner.\n"
            "THEN: wait only.\n"
            "RETAKE: travelling / loading-into-SS screen."
        ),
    },
    "16_SHIELD_NOT_STARTED": {
        "heading": "16 — SS loaded, not started",
        "text": (
            "MATCH: Activate Storm Shield / SS loaded prompt (center band).\n"
            "THEN: UP (runtime; config said TOUCHPAD) to open menu path.\n"
            "RETAKE: inside SS before Endurance start."
        ),
    },
    "17_SHIELD_INVENTORY": {
        "heading": "17 — Inventory → Shield tab",
        "text": (
            "MATCH: Inventory top text / tab chrome.\n"
            "THEN: R1×4 to Storm Shield tab.\n"
            "RETAKE: in-game menu on Inventory tab."
        ),
    },
    "18_SHIELD_MENU": {
        "heading": "18 — Endurance menu/modal",
        "text": (
            "MATCH: Storm Shield menu card OR Endurance modal title (any).\n"
            "THEN: CROSS to proceed.\n"
            "RETAKE: Endurance overview / start card."
        ),
    },
    "19_SHIELD_CONFIRM": {
        "heading": "19 — Confirm Endurance",
        "text": (
            "MATCH: final Start Endurance / confirm (bottom-right).\n"
            "THEN: CROSS.\n"
            "RETAKE: confirm dialog before waves."
        ),
    },
    "20_ENDURANCE_ACTIVE": {
        "heading": "20 — Wave active (wait)",
        "text": (
            "MATCH: Endurance/wave HUD text OR storm-shield active title (any).\n"
            "THEN: wait through combat.\n"
            "RETAKE: in-wave HUD (top banner)."
        ),
    },
    "21_ENDURANCE_BETWEEN": {
        "heading": "21 — Between waves (wait)",
        "text": (
            "MATCH: defense prep / between-waves banner (top center).\n"
            "THEN: wait only.\n"
            "RETAKE: intermission countdown HUD."
        ),
    },
    "22_ENDURANCE_ENDED": {
        "heading": "22 — Team score",
        "text": (
            "MATCH: Team Score / endurance finished screen (top center).\n"
            "THEN: CIRCLE to leave.\n"
            "RETAKE: end-of-run scoreboard."
        ),
    },
    "23_MATCHMAKE_HOMEBASE": {
        "heading": "23 — Matchmake homebase",
        "text": (
            "MATCH: return-to-homebase / matchmake prompt (bottom-right).\n"
            "THEN: CIRCLE to cancel/dismiss.\n"
            "RETAKE: that homebase queue modal."
        ),
    },
    "24_REWARDS_CONTINUE": {
        "heading": "24 — Rewards continue",
        "text": (
            "MATCH: rewards continue CROSS hint OR open-chest art (any).\n"
            "THEN: CROSS.\n"
            "RETAKE: post-match rewards chest screen."
        ),
    },
    "03_CLAIM": {
        "heading": "03 — Claim popup (interrupt)",
        "text": (
            "MATCH: Claim button on BR/event popup (bottom-center).\n"
            "THEN: CROSS.\n"
            "RETAKE: any claim/reward modal."
        ),
    },
    "26_DISMISS_MODAL": {
        "heading": "26 — Dismiss modal (interrupt)",
        "text": (
            "MATCH: Dismiss button on announcement modal.\n"
            "THEN: DOWN + CROSS (runtime sequence).\n"
            "RETAKE: event/announcement modal with Dismiss."
        ),
    },
    "25_SURVEY_SKIP": {
        "heading": "25 — Survey skip (interrupt)",
        "text": (
            "MATCH: survey / rating skip control.\n"
            "THEN: TRIANGLE (runtime; config said CROSS).\n"
            "RETAKE: post-match survey screen."
        ),
    },
    "02_LOBBY": {
        "heading": "02 — Lobby / Discover (NOT IN LINEAR)",
        "text": (
            "MATCH: Play tab selected.\n"
            "ACTION: DISCOVER_NAVIGATION (carousel logic) — deferred; needs design.\n"
            "Helper crops: carousel card, focus corner, STW title."
        ),
    },
}

# Linear editable happy path (skips DISCOVER_NAVIGATION; uses Discover search path)
LINEAR_PATH = [
    "00_START_FORTNITE",
    "01_STARTING",
    "28_DISCOVER_SEARCH_FOCUSED",
    "29_DISCOVER_KEYBOARD",
    "30_SEARCH_RESULTS",
    "04_STW_READY",
    "05_STW_QUEUED",
    "06_CONNECTING",
    "07_STW_COLLECT",
    "08_HESTIA",
    "09_OLD_LOBBY_QUESTS",
    "10_OLD_LOBBY_MAP",
    "10_TWINE_WORLD_MAP",
    "11_TWINE_MAP",
    "12_TWINE_SELECTED",
    "13_COMMUNITY_LOOKOUT",
    "15_STW_FINAL_LAUNCH",
    "14_TRAVELLING_LOBBY",
    "16_SHIELD_NOT_STARTED",
    "17_SHIELD_INVENTORY",
    "18_SHIELD_MENU",
    "19_SHIELD_CONFIRM",
    "20_ENDURANCE_ACTIVE",
    "21_ENDURANCE_BETWEEN",
    "22_ENDURANCE_ENDED",
    "23_MATCHMAKE_HOMEBASE",
    "24_REWARDS_CONTINUE",
]


def resolve_template(name: str) -> Path | None:
    if not name:
        return None
    disk = TEMPLATE_ALIAS.get(name, name)
    path = PI2_ANCHORS / disk
    if path.is_file():
        return path
    # try as-is under anchors
    path2 = PI2_ANCHORS / name
    if path2.is_file():
        return path2
    return None


def roi_yx_to_xywh(roi: list[int]) -> list[int]:
    """pi2ps5 [y1,y2,x1,x2] → Web2PS5 [x,y,w,h]."""
    y1, y2, x1, x2 = [int(v) for v in roi]
    return [x1, y1, max(1, x2 - x1), max(1, y2 - y1)]


def btn_lower(name: str) -> str:
    m = {
        "CROSS": "cross",
        "CIRCLE": "circle",
        "SQUARE": "square",
        "TRIANGLE": "triangle",
        "L1": "l1",
        "R1": "r1",
        "L2": "l2",
        "R2": "r2",
        "UP": "up",
        "DOWN": "down",
        "LEFT": "left",
        "RIGHT": "right",
        "TOUCHPAD": "touchpad",
        "OPTIONS": "options",
        "SHARE": "share",
        "PS": "ps",
        "DPAD_UP": "up",
        "DPAD_DOWN": "down",
        "DPAD_LEFT": "left",
        "DPAD_RIGHT": "right",
    }
    return m.get(str(name).upper(), str(name).lower())


def steps_to_events(steps: list[dict]) -> list[dict]:
    events: list[dict] = []
    t = 0.0
    for step in steps:
        btn = str(step["btn"]).upper()
        press_ms = float(step.get("press_ms", 100))
        wait_ms = float(step.get("wait_ms", 200))
        events.append({"t": round(t, 3), "btn": btn, "action": "press"})
        t += press_ms / 1000.0
        events.append({"t": round(t, 3), "btn": btn, "action": "release"})
        t += wait_ms / 1000.0
    return events


def copy_template(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def import_state_anchor(state: dict) -> dict:
    sid = state["id"]
    thr = float(state.get("threshold", 0.7))
    roi_raw = state.get("roi") or [0, 720, 0, 1280]
    search_roi = roi_yx_to_xywh(roi_raw)

    primary_name = state.get("anchor_template") or ""
    fallback_name = state.get("fallback_template") or ""
    secondary_name = state.get("secondary_template") or ""

    primary = resolve_template(primary_name)
    if primary is None:
        return {"id": sid, "ok": False, "error": f"missing template {primary_name}"}

    copy_template(primary, OUT_ANCHORS / f"{sid}.png")
    templates = [primary.name]
    crops: list[dict] = []
    # Placeholder crop boxes (no full frame); matching uses PNG files by index
    crops.append({"x": search_roi[0], "y": search_roi[1], "w": search_roi[2], "h": search_roi[3]})

    match_mode = "all"
    extra = resolve_template(fallback_name) if fallback_name else None
    if extra is None and secondary_name:
        extra = resolve_template(secondary_name)
        if extra:
            match_mode = "all"  # AND
    elif extra is not None:
        match_mode = "any"  # OR fallback

    if extra is not None:
        copy_template(extra, OUT_ANCHORS / f"{sid}_t1.png")
        templates.append(extra.name)
        crops.append(
            {"x": search_roi[0], "y": search_roi[1], "w": search_roi[2], "h": search_roi[3]}
        )

    meta = {
        "id": sid,
        "threshold": thr,
        "legacy": True,
        "has_full": False,
        "full": None,
        "crop": crops[0],
        "crops": crops,
        "target_count": len(crops),
        "match_mode": match_mode,
        "match_count": 1,
        "search_roi": search_roi,
        "frame_size": {"width": 1280, "height": 720},
        "source": "pi2ps5",
        "pi2ps5_state": sid,
        "pi2ps5_name": state.get("name", ""),
        "pi2ps5_priority": state.get("priority"),
        "pi2ps5_action_type": state.get("action_type"),
        "pi2ps5_templates": templates,
        "note": "LEGACY — no reference screenshot (imported from pi2ps5)",
    }
    (OUT_ANCHORS / f"{sid}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {"id": sid, "ok": True, "templates": templates, "match_mode": match_mode}


def import_helper_anchor(aid: str, template_name: str) -> dict:
    src = resolve_template(template_name)
    if src is None:
        src = PI2_ANCHORS / template_name
        if not src.is_file():
            return {"id": aid, "ok": False, "error": f"missing {template_name}"}
    copy_template(src, OUT_ANCHORS / f"{aid}.png")
    meta = {
        "id": aid,
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
        "source": "pi2ps5",
        "pi2ps5_templates": [src.name],
        "note": "LEGACY helper — no reference screenshot (Discover/lobby)",
    }
    (OUT_ANCHORS / f"{aid}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {"id": aid, "ok": True}


def save_macro(name: str, events: list[dict], meta: dict | None = None) -> None:
    OUT_MACROS.mkdir(parents=True, exist_ok=True)
    doc = {
        "name": name,
        "version": 2,
        "created_at": time.time(),
        "meta": {
            "source": "pi2ps5_import",
            "normalized": False,
            **(meta or {}),
        },
        "keyframes": [],
        "events": events,
    }
    (OUT_MACROS / f"{name}.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")


def resolved_action(state: dict) -> dict:
    sid = state["id"]
    if sid in RUNTIME_ACTIONS:
        return RUNTIME_ACTIONS[sid]
    at = state.get("action_type")
    payload = state.get("action_payload") or {}
    if at == "BUTTON_CLICK":
        return {
            "type": "BUTTON_CLICK",
            "button": btn_lower(payload.get("button", "CROSS")),
            "delay_after": float(payload.get("delay_after", 1.0)),
        }
    if at == "MACRO_SEQUENCE":
        return {"type": "MACRO_SEQUENCE", "steps": list(payload.get("steps") or [])}
    if at == "MACRO_FILE":
        return {"type": "MACRO_FILE", "file": payload.get("file", "keyboard_macro.json")}
    if at == "WAIT":
        return {"type": "WAIT"}
    if at == "DISCOVER_NAVIGATION":
        return {"type": "DISCOVER_NAVIGATION"}
    return {"type": at or "UNKNOWN"}


# Slot schemas must match frontend/js/nodes.js constructors.
# LiteGraph only draws wires when each node's inputs[].link / outputs[].links
# reference entries in graph.links — a bare links[] array is not enough.
NODE_SLOTS: dict[str, dict[str, list[tuple[str, str]]]] = {
    "logic/start": {"inputs": [], "outputs": [("EXEC", "EXEC")]},
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
    "ds/macro": {"inputs": [("EXEC", "EXEC")], "outputs": [("EXEC", "EXEC")]},
    "ds/macro_block": {"inputs": [("EXEC", "EXEC")], "outputs": [("EXEC", "EXEC")]},
    "sys/log": {"inputs": [("EXEC", "EXEC")], "outputs": [("EXEC", "EXEC")]},
    "ui/preview": {"inputs": [], "outputs": []},
    "ui/note": {"inputs": [], "outputs": []},
}


class GraphBuilder:
    """Build a LiteGraph-compatible document with real slot wiring."""

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
        slots = NODE_SLOTS.get(ntype)
        if slots is None:
            raise KeyError(f"unknown node type for slots: {ntype}")
        nid = self._nid
        self._nid += 1
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
            "inputs": [
                {"name": name, "type": typ, "link": None} for name, typ in slots["inputs"]
            ],
            "outputs": [
                {"name": name, "type": typ, "links": None}
                for name, typ in slots["outputs"]
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
        if origin_slot < 0 or origin_slot >= len(origin["outputs"]):
            raise IndexError(f"bad origin slot {origin_slot} on node {origin_id}")
        if target_slot < 0 or target_slot >= len(target["inputs"]):
            raise IndexError(f"bad target slot {target_slot} on node {target_id}")

        lid = self._lid
        self._lid += 1
        self.links.append(
            [lid, origin_id, origin_slot, target_id, target_slot, typ]
        )

        out = origin["outputs"][origin_slot]
        if out["links"] is None:
            out["links"] = []
        out["links"].append(lid)

        inp = target["inputs"][target_slot]
        if inp["link"] is not None:
            raise ValueError(
                f"input {target_slot} on node {target_id} already linked"
            )
        inp["link"] = lid
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
                "extra": {"source": "pi2ps5_import", "editable": True},
                "version": 0.4,
            },
        }


def build_linear_graph(states_by_id: dict[str, dict]) -> dict:
    """Editable litegraph: start → (wait→action→delay)* → log done.

    Each scene is ordinary vis/wait_anchor + ds/press|ds/macro_block + ds/delay.
    Layout: one scene per row (readable), EXEC snakes top→bottom.
    """
    g = GraphBuilder()
    x0, y0 = 80.0, 80.0
    row_h = 170.0
    col = {"note": 0.0, "wait": 360.0, "act": 680.0, "tail": 920.0}

    g.add(
        "ui/note",
        "note.overview",
        [x0, y0 - 20],
        {
            "heading": "STW endurance path (linear)",
            "text": (
                "EXEC flows top→bottom. Each row: wait for scene → press/macro → delay.\n"
                "Not a priority scanner — interrupts live in stw_interrupts.\n"
                "02_LOBBY Discover carousel is deferred.\n"
                "LEGACY anchors: open wait node to preview crop; Freeze to retake full frame."
            ),
        },
        size=[340, 130],
    )

    start_id = g.add("logic/start", "logic.start", [x0 + col["wait"], y0], {})
    prev_id, prev_slot = start_id, 0
    row = 1

    for sid in LINEAR_PATH:
        state = states_by_id.get(sid)
        if not state:
            continue
        action = resolved_action(state)
        if action["type"] == "DISCOVER_NAVIGATION":
            continue

        y = y0 + row * row_h
        meta_path = OUT_ANCHORS / f"{sid}.json"
        thr = 0.7
        roi = None
        match_mode = "all"
        match_count = 1
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            thr = float(meta.get("threshold", 0.7))
            roi = meta.get("search_roi")
            match_mode = meta.get("match_mode") or "all"
            match_count = int(meta.get("match_count") or 1)

        note = SCENE_NOTES.get(sid) or {
            "heading": sid,
            "text": state.get("description") or state.get("name") or sid,
        }
        g.add(
            "ui/note",
            f"note.{sid}",
            [x0 + col["note"], y],
            {"heading": note["heading"], "text": note["text"]},
            size=[340, 150],
        )

        wait_id = g.add(
            "vis/wait_anchor",
            f"wait.{sid}",
            [x0 + col["wait"], y],
            {
                "anchor_id": sid,
                "threshold": thr,
                "timeout_ms": 120000,
                "poll_ms": 100,
                "roi": roi,
                "match_mode": match_mode,
                "match_count": match_count,
                "targets": [],
                "edit_mode": "create",
                "capture_hint": f"LEGACY wait: {sid}",
            },
            size=[260, 120],
        )
        # prev EXEC → wait EXEC in (slot 0)
        g.connect(prev_id, prev_slot, wait_id, 0)
        # wait.found is output slot 0
        found_slot = 0

        act_type = action["type"]
        if act_type == "WAIT":
            delay_id = g.add(
                "ds/delay",
                f"hold.{sid}",
                [x0 + col["act"], y],
                {"ms": 800},
            )
            g.connect(wait_id, found_slot, delay_id, 0)
            prev_id, prev_slot = delay_id, 0
        elif act_type == "BUTTON_CLICK":
            press_id = g.add(
                "ds/press",
                f"press.{sid}",
                [x0 + col["act"], y],
                {"button": action["button"], "duration_ms": 120},
            )
            g.connect(wait_id, found_slot, press_id, 0)
            delay_after_ms = int(float(action.get("delay_after", 1.0)) * 1000)
            delay_id = g.add(
                "ds/delay",
                f"delay.{sid}",
                [x0 + col["tail"], y],
                {"ms": delay_after_ms},
            )
            g.connect(press_id, 0, delay_id, 0)
            prev_id, prev_slot = delay_id, 0
        elif act_type in ("MACRO_SEQUENCE", "MACRO_FILE"):
            if act_type == "MACRO_SEQUENCE":
                events = steps_to_events(action["steps"])
                macro_name = f"seq_{sid}"
            else:
                kb_path = OUT_MACROS / "keyboard_save_the_world.json"
                events = (
                    json.loads(kb_path.read_text(encoding="utf-8")).get("events") or []
                )
                macro_name = "keyboard_save_the_world"
            macro_id = g.add(
                "ds/macro_block",
                f"macro.{sid}",
                [x0 + col["act"], y],
                {
                    "name": macro_name,
                    "events": events,
                    "event_count": len(events),
                    "recording": False,
                    "normalize": False,
                    "gap_ms": 700,
                    "press_ms": 100,
                },
                size=[220, 100],
            )
            g.connect(wait_id, found_slot, macro_id, 0)
            prev_id, prev_slot = macro_id, 0
        else:
            log_id = g.add(
                "sys/log",
                f"skip.{sid}",
                [x0 + col["act"], y],
                {"message": f"unmapped action for {sid}: {act_type}"},
            )
            g.connect(wait_id, found_slot, log_id, 0)
            prev_id, prev_slot = log_id, 0

        row += 1

    done_y = y0 + row * row_h
    done_id = g.add(
        "sys/log",
        "path.done",
        [x0 + col["wait"], done_y],
        {"message": "stw_endurance_path finished (linear; no priority scanner)"},
    )
    g.connect(prev_id, prev_slot, done_id, 0)

    g.add(
        "ui/preview",
        "ui.preview",
        [x0 + col["tail"] + 280, y0],
        {"live": True, "detections": True, "watch": ""},
        size=[640, 400],
    )

    return g.document(
        "stw_endurance_path",
        (
            "Editable linear port of pi2ps5 STW path. "
            "Flow: Start → for each scene wait_anchor(found) → press/macro/delay → next. "
            "Skips 02_LOBBY DISCOVER_NAVIGATION. "
            "Interrupts (claim/dismiss/survey) are in stw_interrupts."
        ),
    )


def build_interrupt_graph(states_by_id: dict[str, dict]) -> dict:
    """Separate editable chains for high-priority interrupt scenes (manual Start)."""
    interrupts = ["03_CLAIM", "26_DISMISS_MODAL", "25_SURVEY_SKIP"]
    g = GraphBuilder()
    y = 100.0

    g.add(
        "ui/note",
        "note.interrupts_overview",
        [40, 20],
        {
            "heading": "Interrupt handlers (manual)",
            "text": (
                "High-priority popups from pi2ps5. Each row is its own Start→wait→action chain.\n"
                "Run one when that modal appears — until a priority scanner exists."
            ),
        },
        size=[420, 100],
    )

    for sid in interrupts:
        state = states_by_id.get(sid)
        if not state:
            continue
        action = resolved_action(state)
        x = 80.0
        note = SCENE_NOTES.get(sid) or {
            "heading": sid,
            "text": state.get("description") or sid,
        }
        g.add(
            "ui/note",
            f"note.{sid}",
            [x, y],
            {"heading": note["heading"], "text": note["text"]},
            size=[320, 140],
        )
        x += 360
        start_id = g.add("logic/start", f"start.{sid}", [x, y], {})
        x += 220

        meta_path = OUT_ANCHORS / f"{sid}.json"
        thr, roi, mode = 0.7, None, "all"
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            thr = float(meta.get("threshold", 0.7))
            roi = meta.get("search_roi")
            mode = meta.get("match_mode") or "all"

        wait_id = g.add(
            "vis/wait_anchor",
            f"wait.{sid}",
            [x, y],
            {
                "anchor_id": sid,
                "threshold": thr,
                "timeout_ms": 60000,
                "poll_ms": 100,
                "roi": roi,
                "match_mode": mode,
                "match_count": 1,
                "targets": [],
                "edit_mode": "create",
                "capture_hint": f"LEGACY interrupt: {sid}",
            },
            size=[260, 120],
        )
        g.connect(start_id, 0, wait_id, 0)
        x += 300

        if action["type"] == "BUTTON_CLICK":
            press_id = g.add(
                "ds/press",
                f"press.{sid}",
                [x, y],
                {"button": action["button"], "duration_ms": 120},
            )
            g.connect(wait_id, 0, press_id, 0)
        elif action["type"] == "MACRO_SEQUENCE":
            events = steps_to_events(action["steps"])
            macro_id = g.add(
                "ds/macro_block",
                f"macro.{sid}",
                [x, y],
                {
                    "name": f"seq_{sid}",
                    "events": events,
                    "event_count": len(events),
                    "recording": False,
                    "normalize": False,
                    "gap_ms": 700,
                    "press_ms": 100,
                },
                size=[220, 100],
            )
            g.connect(wait_id, 0, macro_id, 0)

        y += 220

    return g.document(
        "stw_interrupts",
        "Editable one-shot handlers for claim/dismiss/survey. Run manually until priority scanner exists.",
    )


def main() -> None:
    cfg_path = PI2_ANCHORS / "states_config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    states = cfg.get("states") or []
    states_by_id = {s["id"]: s for s in states}

    OUT_ANCHORS.mkdir(parents=True, exist_ok=True)
    OUT_MACROS.mkdir(parents=True, exist_ok=True)
    OUT_GRAPHS.mkdir(parents=True, exist_ok=True)

    report: dict = {"anchors": [], "helpers": [], "macros": [], "graphs": [], "skipped": []}

    for state in states:
        r = import_state_anchor(state)
        report["anchors"].append(r)

    for aid, tname in DISCOVER_HELPERS:
        # Avoid clobbering 02_LOBBY state import if present
        if aid == "02_LOBBY" and (OUT_ANCHORS / "02_LOBBY.png").is_file():
            continue
        report["helpers"].append(import_helper_anchor(aid, tname))

    # keyboard macro
    kb_src = PI2_ANCHORS / "keyboard_macro.json"
    kb_events = json.loads(kb_src.read_text(encoding="utf-8"))
    save_macro(
        "keyboard_save_the_world",
        kb_events,
        {"pi2ps5_file": "keyboard_macro.json", "purpose": "type SAVE THE WORLD + R2"},
    )
    report["macros"].append("keyboard_save_the_world")

    # MACRO_SEQUENCE (+ runtime override sequences)
    for state in states:
        sid = state["id"]
        action = resolved_action(state)
        if action["type"] == "MACRO_SEQUENCE":
            events = steps_to_events(action["steps"])
            name = f"seq_{sid}"
            save_macro(name, events, {"pi2ps5_state": sid, "kind": "MACRO_SEQUENCE"})
            report["macros"].append(name)

    # Also ensure runtime-only sequences that aren't MACRO_SEQUENCE in config
    for sid, action in RUNTIME_ACTIONS.items():
        if action["type"] == "MACRO_SEQUENCE":
            name = f"seq_{sid}"
            if name not in report["macros"]:
                save_macro(
                    name,
                    steps_to_events(action["steps"]),
                    {"pi2ps5_state": sid, "kind": "RUNTIME_OVERRIDE"},
                )
                report["macros"].append(name)

    linear = build_linear_graph(states_by_id)
    (OUT_GRAPHS / "stw_endurance_path.json").write_text(
        json.dumps(linear, indent=2), encoding="utf-8"
    )
    report["graphs"].append("stw_endurance_path")

    interrupts = build_interrupt_graph(states_by_id)
    (OUT_GRAPHS / "stw_interrupts.json").write_text(
        json.dumps(interrupts, indent=2), encoding="utf-8"
    )
    report["graphs"].append("stw_interrupts")

    # Port map for humans
    rows = []
    for state in sorted(states, key=lambda s: int(s.get("priority") or 999)):
        action = resolved_action(state)
        rows.append(
            {
                "priority": state.get("priority"),
                "id": state["id"],
                "name": state.get("name"),
                "action_type": state.get("action_type"),
                "resolved": action,
                "in_linear_graph": state["id"] in LINEAR_PATH
                and action["type"] != "DISCOVER_NAVIGATION",
                "needs_design": action["type"] == "DISCOVER_NAVIGATION",
                "node_chain": _chain_summary(action, state["id"]),
            }
        )
    port_map = {
        "written": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "verdict": "partial — linear editable graphs OK; priority scanner + DISCOVER_NAV deferred",
        "states": rows,
        "import_report": report,
    }
    (ROOT / "data" / "pi2ps5_port_map.json").write_text(
        json.dumps(port_map, indent=2), encoding="utf-8"
    )

    ok_a = sum(1 for a in report["anchors"] if a.get("ok"))
    fail_a = [a for a in report["anchors"] if not a.get("ok")]
    print(f"Anchors: {ok_a}/{len(report['anchors'])} ok")
    if fail_a:
        print("Failed:", fail_a)
    print(f"Helpers: {len(report['helpers'])}")
    print(f"Macros: {len(report['macros'])}")
    print(f"Graphs: {report['graphs']}")
    print("Wrote data/pi2ps5_port_map.json")


def _chain_summary(action: dict, sid: str) -> str:
    t = action["type"]
    if t == "BUTTON_CLICK":
        return f"vis/wait_anchor({sid}) → ds/press({action['button']}) → ds/delay"
    if t == "WAIT":
        return f"vis/wait_anchor({sid}) → ds/delay(hold)"
    if t == "MACRO_SEQUENCE":
        return f"vis/wait_anchor({sid}) → ds/macro_block(seq_{sid}, events inline)"
    if t == "MACRO_FILE":
        return f"vis/wait_anchor({sid}) → ds/macro_block(keyboard_save_the_world, events inline)"
    if t == "DISCOVER_NAVIGATION":
        return "NEEDS DESIGN — not ported as black-box"
    return f"unmapped ({t})"


if __name__ == "__main__":
    main()
