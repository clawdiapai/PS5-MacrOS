"""First-run onboarding: PSN OAuth, device probe/register, .env write, connect test."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.config import ROOT_DIR, Settings, settings

logger = logging.getLogger("web2ps5.setup")
router = APIRouter(prefix="/api/setup", tags=["setup"])

ENV_PATH = ROOT_DIR / ".env"


def _pyremoteplay_available() -> tuple[bool, str]:
    try:
        import pyremoteplay  # noqa: F401
        from pyremoteplay.receiver import AVReceiver  # noqa: F401
        import av  # noqa: F401

        return True, f"pyremoteplay ok ({getattr(pyremoteplay, '__version__', '?')})"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _profiles_summary() -> list[dict[str, Any]]:
    try:
        from pyremoteplay import RPDevice

        profiles = RPDevice.get_profiles()
        names = list(getattr(profiles, "usernames", None) or profiles.get_users() or [])
        return [{"name": str(n), "has_id": True} for n in names]
    except Exception as exc:  # noqa: BLE001
        logger.debug("profiles summary failed: %s", exc)
        return []


def compute_setup_status() -> dict[str, Any]:
    rp_ok, rp_msg = _pyremoteplay_available()
    profiles = _profiles_summary() if rp_ok else []
    host = (settings.ps5_host or "").strip()
    bridge = (settings.bridge or "fake").strip().lower()
    env_exists = ENV_PATH.is_file()
    skipped = bool(settings.setup_skipped)

    steps = {
        "deps": rp_ok,
        "psn_profile": len(profiles) > 0,
        "host_configured": bool(host),
        "bridge_remote": bridge in ("pyremoteplay", "remoteplay", "ps5", "real"),
        "env_file": env_exists,
        "registered_hint": False,  # filled after probe
    }
    # Complete = explicit flag OR full remote path configured
    remote_ready = (
        steps["deps"]
        and steps["psn_profile"]
        and steps["host_configured"]
        and steps["bridge_remote"]
    )
    complete = bool(settings.setup_complete) or remote_ready or skipped

    return {
        "ok": True,
        "complete": complete,
        "skipped": skipped,
        "steps": steps,
        "deps_message": rp_msg,
        "profiles": profiles,
        "bridge": bridge,
        "ps5_host": host,
        "ps5_user": settings.ps5_user,
        "ps5_spectator_user": settings.ps5_spectator_user,
        "auto_connect": settings.auto_connect,
        "env_path": str(ENV_PATH),
        "needs_wizard": not complete,
        "next": "done" if complete else _next_step(steps),
        "roles": {
            "control": "Used for macros / DualSense injection (active Remote Play session)",
            "spectator": "Second PSN account registered on the console; not used for input",
        },
    }


def _next_step(steps: dict[str, bool]) -> str:
    if not steps["deps"]:
        return "deps"
    if not steps["psn_profile"]:
        return "psn"
    if not steps["host_configured"]:
        return "device"
    if not steps["bridge_remote"]:
        return "save"
    return "done"


@router.get("/status")
async def setup_status() -> dict[str, Any]:
    return compute_setup_status()


@router.post("/install-deps")
async def install_deps() -> dict[str, Any]:
    """Best-effort install of requirements-remoteplay.txt."""
    req = ROOT_DIR / "requirements-remoteplay.txt"
    if not req.is_file():
        raise HTTPException(status_code=500, detail="requirements-remoteplay.txt missing")
    proc = await asyncio.create_subprocess_exec(
        os.sys.executable,
        "-m",
        "pip",
        "install",
        "-r",
        str(req),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out_b, _ = await proc.communicate()
    out = (out_b or b"").decode("utf-8", errors="replace")[-4000:]
    ok, msg = _pyremoteplay_available()
    return {
        "ok": ok,
        "returncode": proc.returncode,
        "message": msg,
        "log_tail": out,
    }


@router.get("/oauth/url")
async def oauth_url() -> dict[str, Any]:
    ok, msg = _pyremoteplay_available()
    if not ok:
        raise HTTPException(status_code=503, detail=f"pyremoteplay unavailable: {msg}")
    from pyremoteplay import oauth

    return {"ok": True, "url": oauth.get_login_url()}


class OAuthBody(BaseModel):
    redirect_url: str = Field(min_length=8)


@router.post("/oauth/complete")
async def oauth_complete(body: OAuthBody) -> dict[str, Any]:
    ok, msg = _pyremoteplay_available()
    if not ok:
        raise HTTPException(status_code=503, detail=f"pyremoteplay unavailable: {msg}")
    from pyremoteplay import RPDevice, oauth

    try:
        # Preferred helper when available
        profiles = RPDevice.get_profiles()
        if hasattr(profiles, "new_user"):
            user_profile = profiles.new_user(body.redirect_url.strip(), save=True)
        else:
            account = oauth.get_account_info(body.redirect_url.strip())
            user_profile = oauth.format_user_account(account)
            profiles.update_user(user_profile)
            profiles.save()
        name = getattr(user_profile, "name", None) or str(user_profile)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"OAuth failed: {exc}") from exc
    return {"ok": True, "user": name, "profiles": _profiles_summary()}


class ProbeBody(BaseModel):
    host: str = Field(min_length=3)


@router.post("/probe")
async def probe_host(body: ProbeBody) -> dict[str, Any]:
    ok, msg = _pyremoteplay_available()
    if not ok:
        raise HTTPException(status_code=503, detail=f"pyremoteplay unavailable: {msg}")
    from pyremoteplay import RPDevice

    host = body.host.strip()
    device = RPDevice(host)
    status = await device.async_get_status()
    if not status:
        status = device.get_status() or {}
    users = []
    try:
        users = list(device.get_users() or [])
    except Exception:
        users = []
    return {
        "ok": bool(status),
        "host": host,
        "status": status if isinstance(status, dict) else {"raw": str(status)},
        "is_on": bool(getattr(device, "is_on", False)),
        "type": getattr(device, "type", None) or (status or {}).get("host-type"),
        "registered_users": users,
    }


@router.post("/discover")
async def discover_hosts() -> dict[str, Any]:
    """LAN DDP broadcast scan for a few seconds (Windows-safe)."""
    ok, msg = _pyremoteplay_available()
    if not ok:
        raise HTTPException(status_code=503, detail=f"pyremoteplay unavailable: {msg}")
    from pyremoteplay.tracker import DeviceTracker

    tracker = DeviceTracker()
    try:
        # DeviceTracker.add_callback(host, callback) — per-host only.
        # Discovery works by broadcasting; devices appear in tracker.devices.
        await tracker._setup(tracker.local_port)  # noqa: SLF001
        tracker.start()
        for _ in range(8):
            await tracker._poll()  # noqa: SLF001
            await asyncio.sleep(0.4)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                f"discover failed: {exc}. "
                "You can type the PS5 IP manually and click Probe instead."
            ),
        ) from exc
    finally:
        try:
            tracker.shutdown()
            tracker.close()
        except Exception:
            pass

    devices: list[dict[str, Any]] = []
    for host, device in (tracker.devices or {}).items():
        status = getattr(device, "status", None) or {}
        if not status:
            continue
        devices.append(
            {
                "host": host,
                "status": status if isinstance(status, dict) else {},
                "type": getattr(device, "host_type", None)
                or (status.get("host-type") if isinstance(status, dict) else None),
                "name": (status.get("host-name") if isinstance(status, dict) else None),
                "is_on": bool(getattr(device, "is_on", False)),
            }
        )
    return {
        "ok": True,
        "devices": devices,
        "hint": None
        if devices
        else "No consoles answered the scan. Enter the PS5 IP manually and Probe.",
    }


class RegisterBody(BaseModel):
    host: str
    user: str
    pin: str = Field(min_length=4, max_length=12)


@router.post("/register")
async def register_device(body: RegisterBody) -> dict[str, Any]:
    ok, msg = _pyremoteplay_available()
    if not ok:
        raise HTTPException(status_code=503, detail=f"pyremoteplay unavailable: {msg}")
    from pyremoteplay import RPDevice

    device = RPDevice(body.host.strip())
    status = await device.async_get_status() or device.get_status()
    if not status:
        raise HTTPException(status_code=400, detail="host unreachable / no status")
    pin = body.pin.strip()
    try:
        if hasattr(device, "async_register"):
            result = await device.async_register(body.user.strip(), pin, save=True)
        else:
            result = device.register(body.user.strip(), pin, save=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"register failed: {exc}") from exc
    users = []
    try:
        users = list(device.get_users() or [])
    except Exception:
        users = []
    return {"ok": True, "result": result, "registered_users": users}


class SaveConfigBody(BaseModel):
    host: str
    user: str = ""  # control / macros
    spectator_user: str = ""  # optional view-only profile name
    bridge: str = "pyremoteplay"
    auto_connect: bool = True
    resolution: str = "720p"
    fps: str = "high"
    apply_now: bool = True


def _write_env(values: dict[str, str]) -> None:
    existing: dict[str, str] = {}
    if ENV_PATH.is_file():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, _, v = s.partition("=")
            existing[k.strip()] = v.strip()
    existing.update(values)
    lines = [
        "# Web2PS5 configuration — written by setup wizard",
        "",
    ]
    for k in sorted(existing.keys()):
        lines.append(f"{k}={existing[k]}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


@router.post("/save")
async def save_config(request: Request, body: SaveConfigBody) -> dict[str, Any]:
    host = body.host.strip()
    if not host:
        raise HTTPException(status_code=400, detail="host required")

    control = body.user.strip()
    spectator = body.spectator_user.strip()
    if spectator and control and spectator == control:
        raise HTTPException(
            status_code=400,
            detail="control and spectator must be different PSN accounts",
        )

    values = {
        "WEB2PS5_BRIDGE": body.bridge.strip() or "pyremoteplay",
        "WEB2PS5_PS5_HOST": host,
        "WEB2PS5_PS5_USER": control,
        "WEB2PS5_PS5_SPECTATOR_USER": spectator,
        "WEB2PS5_AUTO_CONNECT": "true" if body.auto_connect else "false",
        "WEB2PS5_PS5_RESOLUTION": body.resolution,
        "WEB2PS5_PS5_FPS": body.fps,
        "WEB2PS5_SETUP_COMPLETE": "true",
        "WEB2PS5_SETUP_SKIPPED": "false",
    }
    for k, v in values.items():
        os.environ[k] = v
    _write_env(values)

    # Refresh module-level settings object fields
    fresh = Settings()
    for field in fresh.model_fields:
        setattr(settings, field, getattr(fresh, field))

    applied = False
    connect_error = None
    if body.apply_now:
        try:
            from backend.app.bridge import create_bridge

            old = getattr(request.app.state, "bridge", None)
            if old is not None:
                try:
                    await old.disconnect()
                except Exception:
                    logger.exception("old bridge disconnect failed")
            bridge = create_bridge(settings)
            if settings.auto_connect:
                try:
                    await bridge.connect()
                except Exception as exc:  # noqa: BLE001
                    connect_error = str(exc)
                    logger.warning("post-setup connect failed: %s", exc)
            request.app.state.bridge = bridge
            request.app.state.frame_holder = bridge.frames
            if hasattr(request.app.state, "runs") and request.app.state.runs is not None:
                request.app.state.runs._bridge = bridge  # noqa: SLF001
            if hasattr(request.app.state, "passthrough") and request.app.state.passthrough is not None:
                request.app.state.passthrough.bind_bridge(bridge)
            applied = True
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"apply failed: {exc}") from exc

    return {
        "ok": True,
        "env_path": str(ENV_PATH),
        "applied": applied,
        "connect_error": connect_error,
        "status": compute_setup_status(),
        "bridge": request.app.state.bridge.status() if applied else None,
    }


@router.post("/skip-fake")
async def skip_fake(request: Request) -> dict[str, Any]:
    """Mark onboarding skipped — stay on Fake bridge for studio-only use."""
    values = {
        "WEB2PS5_BRIDGE": "fake",
        "WEB2PS5_AUTO_CONNECT": "true",
        "WEB2PS5_SETUP_SKIPPED": "true",
        "WEB2PS5_SETUP_COMPLETE": "false",
    }
    for k, v in values.items():
        os.environ[k] = v
    _write_env(values)
    fresh = Settings()
    for field in fresh.model_fields:
        setattr(settings, field, getattr(fresh, field))
    return {"ok": True, "status": compute_setup_status(), "mode": "fake"}
