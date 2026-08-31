# Web2PS5 — BUILD_STATE

**Last updated:** 2026-08-28  
**Current phase:** **BUILD COMPLETE** + first-run Setup wizard  
**Protocol:** Keep building within a phase; only stop when blocked or a decision is required.

---

## Phase status

| Phase | Name | Status |
|---|---|---|
| 0 | Architecture evaluation & plan lock | **Complete** |
| 1 | Glass Cockpit + Fake Console | **Complete** |
| 2 | Real `PyRemotePlayBridge` | **Complete** |
| 3 | Anchor Studio + ROI + `wait_anchor` | **Complete** |
| 4 | Variables, gates, while/repeat/retry, counters | **Complete** |
| 5 | Macro record/playback, webhooks, session power | **Complete** |
| 6 | Subgraphs + polish + finalize | **Complete** |

---

## How to run

```bat
run.bat
```

Opens **http://127.0.0.1:8000/setup** (first-run wizard).  
Studio redirects there until setup is complete or skipped (Fake mode).

### What still needs *your* live testing

| Test | Status in code | Needs you |
|---|---|---|
| Fake studio / GraphRunner / anchors | Verified by smoke | Smoke / UI glance |
| Setup wizard UI | Implemented | Walk through `/setup` |
| PSN OAuth (if no profile) | API wired | Browser login + paste redirect URL |
| Probe PS5 IP / LAN scan | API wired | Console on LAN |
| Register with Remote Play PIN | API wired | PIN from PS5 link-device screen |
| Live stream + DualSense inject | Bridge wired | After save & connect |
| Discord webhook node | Implemented | Real webhook URL |

**PS5 connection:** yes — `PyRemotePlayBridge` is in place. It was **not** live-verified here. Your machine already has PSN profiles (`ShervUZZO`, `automa_convinto`); wizard should jump to the **device** step.

### Smoke

```powershell
python backend\scripts\smoke_bridge_factory.py
python backend\scripts\smoke_complete.py
```

---

## Feature map (what shipped)

### Runtime
- FastAPI + WS telemetry + MJPEG preview
- `AtomicFrameHolder` + Fake / pyremoteplay bridges
- FeedbackTicker DualSense state machine
- Single-token GraphRunner (hybrid EXEC + data)

### Nodes
- **logic:** start, branch, while, repeat, retry, and/or/not, set_var, get_var, counter, subgraph
- **ds:** delay, press, stick, macro
- **vis:** check_state, wait_anchor (found/timeout)
- **sys:** log, assert, webhook, screenshot
- **pwr:** session (connect/disconnect/standby)

### Authoring
- litegraph canvas + glow
- Anchor Studio (snapshot → drag crop → save)
- Macro Rec/Stop (samples pad state timeline)

### APIs
- `/api/graphs`, `/api/runs`, `/api/bridge`, `/api/session`
- `/api/anchors`, `/api/macros`, `/api/preview/mjpeg`, `/ws/telemetry`

---

## Escape hatches / known limits

- **chiaki-ng:** not wired; swap via `HardwareBridge` if pyremoteplay dies on firmware.
- **Parallel EXEC:** still forbidden (single token).
- **Live PS5:** requires registered Remote Play profile + LAN host.
- **Webhook:** posts JSON or Discord-style multipart; allowlist not enforced yet.
- **Subgraph depth:** capped at 5.

---

## Next (optional future)

- Chiaki-ng FFI bridge
- OCR / color_gate nodes
- Macro timeline editor UI
- Graph fork/join with pad arbitration
- Auth / webhook URL allowlist
