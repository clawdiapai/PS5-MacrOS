"""FastAPI entrypoint — Phase 2 adds selectable pyremoteplay bridge."""

from __future__ import annotations

import asyncio
import atexit
import logging
import signal
import sys
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api import build_api_router
from backend.app.api.runs import RunController
from backend.app.api.telemetry import TelemetryHub
from backend.app.bridge import create_bridge
from backend.app.bridge.passthrough import PassThroughService
from backend.app.config import settings
from backend.app.logging_filters import install_quiet_access_log
from backend.app.vision.frame_holder import AtomicFrameHolder

logger = logging.getLogger("web2ps5.main")
install_quiet_access_log()

# Live bridge for atexit / signal cleanup when lifespan finally never runs
# (closed terminal, kill, uvicorn --reload child tear-down).
_shutdown_bridge: Any = None
_shutdown_passthrough: Any = None
_hooks_installed = False


def _sync_release_remote_play(reason: str = "process exit") -> None:
    """Release the PS5 Remote Play slot without awaiting (signal/atexit safe)."""
    global _shutdown_bridge, _shutdown_passthrough
    pt = _shutdown_passthrough
    bridge = _shutdown_bridge
    if pt is not None:
        try:
            stop = getattr(pt, "stop_sync", None)
            if callable(stop):
                stop()
            else:
                # Best effort: mark inactive if exposed
                if hasattr(pt, "_active"):
                    pt._active = False  # noqa: SLF001
        except Exception:
            logger.debug("passthrough sync stop failed", exc_info=True)
    if bridge is not None:
        try:
            fn = getattr(bridge, "force_disconnect_sync", None)
            if callable(fn):
                fn(reason)
            else:
                # Fallback: tear down common attrs if present
                for attr in ("_controller", "_session"):
                    obj = getattr(bridge, attr, None)
                    if obj is None:
                        continue
                    for meth in ("stop", "disconnect", "close"):
                        m = getattr(obj, meth, None)
                        if callable(m):
                            try:
                                m()
                            except Exception:
                                pass
        except Exception:
            logger.exception("sync Remote Play release failed (%s)", reason)


def _install_process_exit_hooks() -> None:
    """Ensure RP disconnect runs on Ctrl+C / console close / normal exit."""
    global _hooks_installed
    if _hooks_installed:
        return
    _hooks_installed = True
    atexit.register(lambda: _sync_release_remote_play("atexit"))

    def _handler(signum: int, _frame: Any) -> None:
        name = signum
        try:
            name = signal.Signals(signum).name
        except Exception:
            pass
        logger.warning("signal %s — releasing Remote Play slot", name)
        _sync_release_remote_play(f"signal {name}")
        # Re-raise default behavior for SIGINT so uvicorn also stops.
        if signum == getattr(signal, "SIGINT", None):
            raise KeyboardInterrupt

    for sig_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _handler)
        except Exception:
            logger.debug("could not install handler for %s", sig_name, exc_info=True)

    # Windows: console window X / Ctrl+C often arrives as CTRL_CLOSE_EVENT
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            HandlerRoutine = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
            # CTRL_C_EVENT=0, CTRL_BREAK=1, CTRL_CLOSE=2, CTRL_LOGOFF=5, CTRL_SHUTDOWN=6
            def _console_handler(ctrl_type: int) -> bool:
                if ctrl_type in (0, 1, 2, 5, 6):
                    _sync_release_remote_play(f"win console ctrl={ctrl_type}")
                    # Return False so the process still terminates after cleanup.
                    return False
                return False

            _handler_ref = HandlerRoutine(_console_handler)
            # Keep a ref so GC does not collect the callback.
            _install_process_exit_hooks._win_handler = _handler_ref  # type: ignore[attr-defined]
            ctypes.windll.kernel32.SetConsoleCtrlHandler(_handler_ref, True)
            logger.info("Windows console close handler installed (RP release)")
        except Exception:
            logger.debug("SetConsoleCtrlHandler failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _shutdown_bridge, _shutdown_passthrough
    settings.ensure_dirs()
    _install_process_exit_hooks()
    # Point pytesseract at Program Files / tools/tesseract if already installed
    # (avoids OCR nodes re-attempting a blocked CDN download on every poll).
    try:
        from backend.app.vision.tesseract_bootstrap import configure_if_present

        if configure_if_present():
            logger.info("Tesseract binary detected at startup")
        else:
            logger.info(
                "Tesseract not found yet — will bootstrap on first OCR use"
            )
    except Exception:
        logger.debug("Tesseract startup probe skipped", exc_info=True)

    hub = TelemetryHub()
    bridge = create_bridge(settings)
    _shutdown_bridge = bridge
    video_ingest = None

    # External HDMI / ustreamer video (Pi capture) → AtomicFrameHolder
    vs = (settings.video_source or "").strip().lower()
    if vs in ("ustreamer", "http", "hdmi", "external"):
        from backend.app.vision.ustreamer import UstreamerFrameSource

        url = (settings.video_url or "").strip()
        if not url:
            logger.error(
                "WEB2PS5_VIDEO_SOURCE=%s requires WEB2PS5_VIDEO_URL "
                "(e.g. http://192.168.1.64:8080/stream)",
                vs,
            )
        else:
            video_ingest = UstreamerFrameSource(
                bridge.frames,
                url,
                width=settings.frame_width,
                height=settings.frame_height,
            )
            video_ingest.start()
            logger.info("ustreamer video ingest started: %s", url)

    if settings.auto_connect:
        try:
            # Don't block app boot for a long RP retry storm — background it.
            async def _bg_connect():
                try:
                    await bridge.connect()
                    logger.info(
                        "background auto_connect ok bridge=%s",
                        getattr(bridge, "name", type(bridge).__name__),
                    )
                except Exception:
                    logger.exception(
                        "auto_connect failed for bridge=%s — use RP Reconnect in UI",
                        getattr(bridge, "name", type(bridge).__name__),
                    )

            asyncio.create_task(_bg_connect(), name="auto-connect-rp")
        except Exception:
            logger.exception("failed to schedule auto_connect")
    else:
        logger.info(
            "auto_connect disabled; call POST /api/session/connect when ready "
            "(bridge=%s)",
            getattr(bridge, "name", type(bridge).__name__),
        )

    runs = RunController(bridge, hub)
    # ~125 Hz like pi2ps5 windows_gamepad_loop (not feedback_hz)
    passthrough = PassThroughService(bridge, hz=125.0)
    _shutdown_passthrough = passthrough

    app.state.telemetry = hub
    app.state.bridge = bridge
    app.state.frame_holder = bridge.frames
    app.state.runs = runs
    app.state.passthrough = passthrough
    app.state.video_ingest = video_ingest

    try:
        yield
    finally:
        try:
            await passthrough.stop()
        except Exception:
            logger.exception("passthrough stop during shutdown")
        if video_ingest is not None:
            try:
                await video_ingest.stop()
            except Exception:
                logger.exception("video ingest stop failed")
        await runs.stop()
        try:
            await bridge.disconnect()
        except Exception:
            logger.exception("bridge disconnect during shutdown")
            # Last resort if async path failed mid-teardown
            _sync_release_remote_play("lifespan finally fallback")
        finally:
            _shutdown_bridge = None
            _shutdown_passthrough = None


app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)
app.include_router(build_api_router())


@app.get("/api/health")
async def health(request: Request) -> dict[str, Any]:
    bridge = request.app.state.bridge
    hub: TelemetryHub = request.app.state.telemetry
    runs: RunController = request.app.state.runs
    ingest = getattr(request.app.state, "video_ingest", None)
    video_info: dict[str, Any] = {
        "source": settings.video_source,
        "url": settings.video_url or None,
    }
    if ingest is not None:
        video_info.update(
            {
                "running": ingest.is_running,
                "published": ingest.published_count,
                "error": ingest.last_error,
            }
        )
    return {
        "status": "ok",
        "app": settings.app_name,
        "phase": "6.0-complete",
        "bridge_mode": settings.bridge,
        "video": video_info,
        "auto_connect": settings.auto_connect,
        "frame": {
            "width": settings.frame_width,
            "height": settings.frame_height,
        },
        "feedback_hz": settings.feedback_hz,
        "min_press_ms": settings.min_press_ms,
        "preview_fps": settings.preview_fps,
        "telemetry_clients": hub.client_count,
        "run": runs.snapshot(),
        "bridge": bridge.status(),
    }


@app.get("/api/frame/meta")
async def frame_meta(request: Request) -> dict[str, Any]:
    holder: AtomicFrameHolder = request.app.state.frame_holder
    bridge = request.app.state.bridge
    snap = holder.get_latest()
    published = getattr(bridge, "published_count", None)
    if published is None:
        published = bridge.status().get("video", {}).get("published", 0)
    if snap is None:
        return {
            "ok": False,
            "reason": "no_frame",
            "bridge_connected": bridge.connected,
            "published": published,
        }
    return {
        "ok": True,
        "frame_id": snap.frame_id,
        "pts": snap.pts,
        "width": snap.width,
        "height": snap.height,
        "dtype": str(snap.image.dtype),
        "shape": list(snap.image.shape),
        "bridge_connected": bridge.connected,
        "published": published,
    }


@app.get("/api/version", response_class=PlainTextResponse)
async def version() -> str:
    return "0.2.0"


# Frontend assets — never mount StaticFiles at "/" (it swallows WebSocket upgrades).
_frontend = settings.frontend_dir
if _frontend.is_dir():
    css_dir = _frontend / "css"
    js_dir = _frontend / "js"
    vendor_dir = _frontend / "vendor"
    if css_dir.is_dir():
        app.mount("/css", StaticFiles(directory=str(css_dir)), name="css")
    if js_dir.is_dir():
        app.mount("/js", StaticFiles(directory=str(js_dir)), name="js")
    if vendor_dir.is_dir():
        app.mount("/vendor", StaticFiles(directory=str(vendor_dir)), name="vendor")

    @app.get("/")
    async def control_home() -> FileResponse:
        return FileResponse(_frontend / "control.html")

    @app.get("/control")
    async def control_alias() -> FileResponse:
        return FileResponse(_frontend / "control.html")

    @app.get("/studio")
    async def studio_index() -> FileResponse:
        return FileResponse(_frontend / "index.html")

    @app.get("/setup")
    async def setup_wizard() -> FileResponse:
        return FileResponse(_frontend / "setup.html")
