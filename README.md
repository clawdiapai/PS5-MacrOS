# Web2PS5

Visual node automation studio for PlayStation 5 (ComfyUI-style canvas, Blueprint-style EXEC + data).

- **Frontend:** litegraph.js authoring + Anchor Studio + live MJPEG
- **Backend:** FastAPI GraphRunner, vision, Fake or pyremoteplay hardware bridge

See `BUILD_STATE.md` for phase history and decisions.  
See `TASK.md` for the original architecture brief.

## Status

**Build complete (Phases 0–6).** Default mode is Fake (no PS5 required).

## Run

**Fake console:**

```bat
run.bat
```

**Real PS5:**

1. Copy `.env.example` → `.env` and set `WEB2PS5_PS5_HOST`
2. Ensure a Remote Play profile exists (`~/.pyremoteplay`)
3. Run `run-ps5.bat`

Open http://127.0.0.1:8000/

## Layout

```
backend/app/     FastAPI, bridges, runner, vision
frontend/        litegraph studio + Anchor Studio
data/            graphs, anchors, macros, screenshots
BUILD_STATE.md   resumable tracker
```

## Smoke tests

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
python backend\scripts\smoke_complete.py
```
