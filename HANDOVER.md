# Web2PS5 / psMacrOS — Handover for the Next Agent

**Written:** 2026-08-29  
**Workspace:** `C:\Users\Uzzo\Documents\grok\psMacrOS`  
**You have this file and the workspace only.** There is **no** prior chat transcript. Treat this document as your entire briefing.

---

## 0. Who you are talking to / what this project is

**psMacrOS** (product name in UI: **Web2PS5**) is a **ComfyUI/Blueprint-style visual automation studio** for PlayStation 5 Remote Play:

- Frontend: vendored **litegraph.js** graph editor + floating/canvas UI tools  
- Backend: **FastAPI** + GraphRunner  
- Control path: **pyremoteplay** Session + DualSense (PC DualSense passthrough and/or graph-driven presses)  
- Vision: OpenCV template matching on live Remote Play frames  

**Sibling / legacy project to study:** `C:\Users\Uzzo\Documents\pi2ps5`  
That repo already runs Fortnite / Save-the-World automation with a **priority scene/state machine**, many anchors, and macros. Your job is to **bring those logics into Web2PS5** if the node set is sufficient—or **plan missing pieces with the user** if not.

---

## 1. Your mission (do this in order)

1. **Explore** `C:\Users\Uzzo\Documents\pi2ps5`, especially:
   - Scenes/states: `pi2ps5\anchors\states_config.json`
   - Macros: `pi2ps5\anchors\keyboard_macro.json` and any other macro JSON under `anchors\`
   - Runtime behavior: `pi2ps5\capture.py`, `pi2ps5\vision_pilot.py`
   - Optional API: `pi2ps5\app\api\states.py`, `pi2ps5\app\api\macros.py`

2. **Figure out** whether Web2PS5 already has **enough nodes** to recreate those logics as litegraph graphs.
   - **If yes:** start porting as much as possible (anchors → `data/anchors/`, macros → `data/macros/`, flows → graphs under `data/graphs/`).
   - **If no:** **stop inventing a large new architecture alone.** Plan further development **with the user** (what nodes/runtime changes are needed). Especially discuss anything like a priority “every-frame state scanner” or special `DISCOVER_NAVIGATION` behavior.

3. **Anchors imported from pi2ps5 will NOT have reference full-frame screenshots** (`{id}_full.jpg`).
   - Mark them clearly as **LEGACY**.
   - When the user opens/edits one, **prompt for an optional retake** (Freeze → Confirm) so a full reference frame can be attached later.
   - Matching may still use the legacy crop PNG until they retake.

---

## 2. How to run this app

```bat
cd C:\Users\Uzzo\Documents\grok\psMacrOS
run.bat
```

- Studio: `http://127.0.0.1:8000/`  
- First-run setup: `http://127.0.0.1:8000/setup` (until setup complete/skipped)  
- After changing frontend JS/CSS, bump `?v=` query on scripts in `frontend/index.html` and hard-refresh.

### Current PS5 / PSN context (from `.env`)

- Bridge: `pyremoteplay`  
- Host: `192.168.1.61`  
- Control user: `ShervUZZO`  
- Spectator user: `automa_convinto`  
- Profiles live in `~/.pyremoteplay/.profile.json`

---

## 3. Architecture snapshot (Web2PS5)

| Layer | Location | Role |
|-------|----------|------|
| Studio UI | `frontend/` (`nodes.js`, `ui_nodes.js`, `studio.js`) | litegraph authoring |
| API | `backend/app/api/` | graphs, runs, anchors, macros, preview, passthrough, session, setup |
| Graph execution | `backend/app/runner/graph_runner.py` | Single EXEC token; hybrid EXEC + data |
| Remote Play | `backend/app/bridge/pyremote.py`, `av_compat.py`, `receiver.py` | Session+Controller; low-latency patches |
| DualSense passthrough | `backend/app/bridge/passthrough.py` | PC pad → RP; after start: sleep ~900ms then press **CROSS** |
| Vision | `backend/app/vision/` | frame holder, template match, detect, anchors |
| Macros | `backend/app/macros.py` | normalize: buttons uniform + 700ms gaps; sticks = hold segments |
| Data | `data/anchors/`, `data/macros/`, `data/graphs/` | runtime assets |

Also see `BUILD_STATE.md` and `README.md` for phase history (may be slightly stale vs this handover).

---

## 4. Nodes you already have

### Logic
`logic/start`, `branch`, `while`, `repeat`, `retry`, `and` / `or` / `not`, `set_var`, `get_var`, `counter`, `subgraph`

### DualSense / timing
`ds/delay`, `ds/press`, `ds/stick`, `ds/macro`, `ds/macro_block` (in-node record; **normalize ON by default**)

### Vision
`vis/check_state` — one-shot match  
`vis/wait_anchor` — wait until match / timeout; multi-target (`all` / `any` / `at_least N`); Freeze / Confirm / Saved list / edit  

### System / power
`sys/log`, `sys/assert`, `sys/webhook`, `sys/screenshot`, `pwr/session`

### Canvas UI tools (zoom with graph)
`ui/preview` (live + detection overlays), `ui/anchors` (library), `ui/macros`, `ui/telemetry`

---

## 5. What is in pi2ps5 (what you must recreate)

### Scenes = `anchors\states_config.json` (**31 states**)

Each state has roughly: `id`, `name`, `priority`, `anchor_template`, optional fallback/secondary templates, `roi`, `threshold`, `action_type`, `action_payload`.

**Action type mix:**

| Type | Count | Notes |
|------|------:|-------|
| `BUTTON_CLICK` | 20 | One button + `delay_after` |
| `WAIT` | 5 | Detect / hold |
| `MACRO_SEQUENCE` | 4 | Inline `steps[]` (`btn`, `press_ms`, `wait_ms`) |
| `MACRO_FILE` | 1 | Uses `keyboard_macro.json` |
| `DISCOVER_NAVIGATION` | 1 | Custom lobby/carousel (`02_LOBBY`) — likely needs design discussion |

**State ids (priority order in file):**  
`00_START_FORTNITE`, `01_STARTING`, `03_CLAIM`, `26_DISMISS_MODAL`, `25_SURVEY_SKIP`, `30_SEARCH_RESULTS`, `29_DISCOVER_KEYBOARD`, `28_DISCOVER_SEARCH_FOCUSED`, `07_STW_COLLECT`, `08_HESTIA`, `09_OLD_LOBBY_QUESTS`, `10_TWINE_WORLD_MAP`, `10_OLD_LOBBY_MAP`, `14_TRAVELLING_LOBBY`, `11_TWINE_MAP`, `12_TWINE_SELECTED`, `13_COMMUNITY_LOOKOUT`, `15_STW_FINAL_LAUNCH`, `17_SHIELD_INVENTORY`, `18_SHIELD_MENU`, `19_SHIELD_CONFIRM`, `21_ENDURANCE_BETWEEN`, `20_ENDURANCE_ACTIVE`, `16_SHIELD_NOT_STARTED`, `22_ENDURANCE_ENDED`, `23_MATCHMAKE_HOMEBASE`, `24_REWARDS_CONTINUE`, `06_CONNECTING`, `04_STW_READY`, `05_STW_QUEUED`, `02_LOBBY`

### Macros
- `pi2ps5\anchors\keyboard_macro.json` — D-pad / button timeline for typing on the PS5 virtual keyboard  
- Sequences embedded in states as `MACRO_SEQUENCE`

### Anchors
- Hundreds of PNG/JPG under `pi2ps5\anchors\` and project root  
- These are **template crops** (and ad-hoc full-ish JPGs). They are **not** Web2PS5 `{id}_full.jpg` authoring pairs.

### Important coordinate warning
pi2ps5 `roi` in config is often **`[y1, y2, x1, x2]`** (row/col ranges).  
Web2PS5 crops/ROI use **`x, y, w, h`**. Convert carefully; do not copy arrays blindly.

### Runtime model difference
- **pi2ps5:** priority state machine scanning frames continuously.  
- **Web2PS5 GraphRunner:** **linear EXEC** token (wait → press → …).  
Approximating “always watch many scenes” may need a loop of checks, subgraphs, or a **new** priority node—**ask the user** before building a full state-machine engine.

---

## 6. Gap cheat-sheet (enough vs not enough)

### Usually mappable with existing nodes
| pi2ps5 | Web2PS5 |
|--------|---------|
| Detect → button | `vis/wait_anchor` → `ds/press` (+ `ds/delay`) |
| Detect → wait | `wait_anchor` / `check_state` + delay |
| Button sequences | `ds/macro_block` or press/delay chain |
| Keyboard macro file | Import into `data/macros/` + `ds/macro_block` / `ds/macro` |
| Fallback templates | Multi-target (`any` / `at_least`) or two wait nodes |

### Likely needs user planning
| Gap | Why |
|-----|-----|
| `DISCOVER_NAVIGATION` | Custom Discover/lobby navigation |
| True priority multi-state arbiter | Not how GraphRunner works today |
| Binary/`_bin` template variants | Match pipeline is plain OpenCV template match |
| One-click import of `states_config.json` → graph | Not built yet |

---

## 7. LEGACY anchors — required UX when porting

Imported pi2ps5 templates **will not** have `{id}_full.jpg`.

**You must:**

1. Tag meta e.g. `legacy: true`, `has_full: false`.  
2. In any list/editor (`ui/anchors`, `vis/wait_anchor`, `vis/check_state`), make it **obvious**:  
   **`LEGACY — no reference screenshot`**.  
3. On open/edit, **prompt optional retake**, e.g.  
   *“This legacy anchor has no full freeze. Retake now to enable reference editing? [Retake] [Keep legacy crop]”*  
4. Retake = existing Freeze → adjust boxes → Confirm (writes `_full.jpg`, clears legacy).  
5. Do **not** block matching on missing full frames; retake is optional.

---

## 8. Suggested first concrete steps

1. Read `states_config.json` fully; produce a table: state id → proposed node chain (or “needs new node”).  
2. Share the **enough / not enough** verdict with the user.  
3. If enough:  
   - Import templates into `data/anchors/` as **LEGACY**  
   - Import `keyboard_macro.json`  
   - Build graphs for BUTTON_CLICK / WAIT / MACRO_* paths first  
4. Live-test on the connected PS5 path (passthrough / Remote Play already wired).  
5. Only then design missing nodes with the user.

---

## 9. Key files (Web2PS5)

```
backend/app/main.py
backend/app/config.py
backend/app/runner/graph_runner.py
backend/app/vision/anchors.py
backend/app/vision/detect.py
backend/app/macros.py
backend/app/bridge/pyremote.py
backend/app/bridge/passthrough.py
backend/app/bridge/av_compat.py
frontend/js/nodes.js
frontend/js/ui_nodes.js
frontend/js/studio.js
frontend/index.html
data/anchors/
data/macros/
data/graphs/
```

## Key files (pi2ps5)

```
C:\Users\Uzzo\Documents\pi2ps5\anchors\states_config.json
C:\Users\Uzzo\Documents\pi2ps5\anchors\keyboard_macro.json
C:\Users\Uzzo\Documents\pi2ps5\capture.py
C:\Users\Uzzo\Documents\pi2ps5\vision_pilot.py
C:\Users\Uzzo\Documents\pi2ps5\app\api\states.py
C:\Users\Uzzo\Documents\pi2ps5\app\api\macros.py
```

---

## 10. Recent product behavior (so you don’t rediscover it)

- Macro **normalize** defaults ON (uniform presses + 700ms gaps; sticks use hold-segment logic). Untick for raw.  
- Preview lag was fixed by keeping JPEG off the AV decode thread + dropping AV backlog.  
- UI panels are **canvas nodes** (`ui/*`), not a fixed sidebar.  
- Anchors support multi-target + match modes; Saved list / edit on wait/check nodes; library on `ui/anchors`.  
- Capture UI layout: content band **between** slots and widgets (`widgets_start_y`) so lists aren’t hidden under buttons.  
- Passthrough ON → settle sleep → **CROSS** to open current game.

---

## 11. Definition of done for *your* first stretch

- [ ] You understand pi2ps5 scenes + macros without needing prior chat context  
- [ ] You give the user a clear **enough / not enough** assessment  
- [ ] You either port what you can **or** propose missing tools with the user  
- [ ] Any imported anchors are **LEGACY**-labeled with **optional retake** prompt  
- [ ] You do not silently replace GraphRunner with a priority engine without approval  

**User preference:** stop and plan with them when tools are missing; port aggressively when tools already exist.
