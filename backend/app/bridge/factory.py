"""Bridge factory — select Fake vs pyremoteplay via settings."""

from __future__ import annotations

import logging
from typing import Any

from backend.app.config import Settings

logger = logging.getLogger("web2ps5.bridge.factory")


def create_bridge(settings: Settings) -> Any:
    """
    Build a HardwareBridge implementation.

    WEB2PS5_BRIDGE=fake|pyremoteplay
    """
    kind = (settings.bridge or "fake").strip().lower()

    if kind in ("fake", "mock"):
        from backend.app.bridge.fake import FakeHardwareBridge

        return FakeHardwareBridge(
            frame_width=settings.frame_width,
            frame_height=settings.frame_height,
            fake_fps=settings.fake_fps,
            feedback_hz=settings.feedback_hz,
            min_press_ms=settings.min_press_ms,
        )

    if kind in ("pyremoteplay", "remoteplay", "ps5", "real"):
        from backend.app.bridge.av_compat import patch_pyremoteplay_av
        from backend.app.bridge.pyremote import PyRemotePlayBridge

        patch_pyremoteplay_av()

        if not settings.ps5_host:
            raise RuntimeError(
                "WEB2PS5_BRIDGE=pyremoteplay requires WEB2PS5_PS5_HOST=<ip>"
            )
        # control_only only when explicitly using external capture — NOT the default path
        video = (settings.video_source or "remoteplay").strip().lower()
        control_only = video in ("ustreamer", "http", "hdmi", "external")
        return PyRemotePlayBridge(
            host=settings.ps5_host,
            user=settings.ps5_user or None,
            spectator_user=settings.ps5_spectator_user or None,
            frame_width=settings.frame_width,
            frame_height=settings.frame_height,
            feedback_hz=settings.feedback_hz,
            min_press_ms=settings.min_press_ms,
            resolution=settings.ps5_resolution,
            fps=settings.ps5_fps,
            quality=settings.ps5_quality,
            codec=settings.ps5_codec,
            control_only=control_only,
        )

    raise RuntimeError(f"unknown WEB2PS5_BRIDGE={kind!r} (use fake|pyremoteplay)")
