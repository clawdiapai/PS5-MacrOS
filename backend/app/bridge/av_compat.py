"""
Compat shims ported from the working pi2ps5/capture.py TUI.

pyremoteplay 0.7.x + modern PS5 firmware + PyAV 14/18 needs:
  1) Flags.LOW_DELAY / Flags2.FAST aliases (PyAV renamed to lowercase)
  2) Skip legacy network-test stream (causes "Version not accepted" + hangs)
  3) Relax Session.is_ready / Controller._check_session so input works ASAP
  4) Harden stream send / stick updates against transient disconnects
"""

from __future__ import annotations

import logging

logger = logging.getLogger("web2ps5.bridge.av_compat")

_patched = False


def patch_pyremoteplay_av() -> None:
    """Apply all pyremoteplay runtime patches (idempotent)."""
    global _patched
    if _patched:
        return

    try:
        import av
        from pyremoteplay.controller import Controller
        from pyremoteplay.receiver import AVReceiver
        from pyremoteplay.session import Session
        from pyremoteplay.stream import RPStream
    except ImportError:
        return

    # --- 1) PyAV enum aliases (pi2ps5 style) ---
    if hasattr(av, "codec") and hasattr(av.codec, "context"):
        flags = getattr(av.codec.context, "Flags", None)
        if flags is not None and not hasattr(flags, "LOW_DELAY") and hasattr(flags, "low_delay"):
            flags.LOW_DELAY = flags.low_delay  # type: ignore[attr-defined]
        flags2 = getattr(av.codec.context, "Flags2", None)
        if flags2 is not None and not hasattr(flags2, "FAST") and hasattr(flags2, "fast"):
            flags2.FAST = flags2.fast  # type: ignore[attr-defined]

    # Audio resampler signature drift
    def _patched_audio_resampler(audio_format: str = "s16", channels=2, rate=48000):
        try:
            layout = "stereo" if channels == 2 else ("mono" if channels == 1 else channels)
            return av.audio.resampler.AudioResampler(audio_format, layout, rate)
        except Exception:
            return None

    AVReceiver.audio_resampler = staticmethod(_patched_audio_resampler)

    # --- 2) Skip broken RP network test probe (THE important one) ---
    # Forces test=False with sane MTU/RTT so session starts like pi2ps5 (~fast, no Version spam path)
    if not getattr(Session._start_stream, "_web2ps5_patched", False):
        orig_start_stream = Session._start_stream

        def fast_start_stream(self, test=True, mtu=None, rtt=None):
            return orig_start_stream(self, test=False, mtu=1454, rtt=0.010)

        fast_start_stream._web2ps5_patched = True  # type: ignore[attr-defined]
        Session._start_stream = fast_start_stream  # type: ignore[method-assign]
        logger.info("Patched Session._start_stream to skip legacy network test")

    # --- 3) Instant controller readiness ---
    Session.is_ready = property(  # type: ignore[assignment]
        lambda self: self.is_running or self.state == Session.State.READY
    )

    def safe_check_session(self) -> bool:
        if self._session is None:
            return False
        if self._session.is_stopped:
            return False
        return bool(self._session.is_running or self._session.is_ready)

    Controller._check_session = safe_check_session  # type: ignore[method-assign]

    # --- 4) Harden send / sticks ---
    if not getattr(RPStream.send, "_web2ps5_patched", False):
        orig_stream_send = RPStream.send

        def safe_stream_send(self, msg: bytes):
            if self._protocol is not None:
                try:
                    self._protocol.sendto(msg, (self._host, self._port))
                except Exception:
                    pass

        safe_stream_send._web2ps5_patched = True  # type: ignore[attr-defined]
        RPStream.send = safe_stream_send  # type: ignore[method-assign]

    if not getattr(Controller.update_sticks, "_web2ps5_patched", False):
        orig_update_sticks = Controller.update_sticks

        def safe_update_sticks(self):
            try:
                orig_update_sticks(self)
            except Exception:
                pass

        safe_update_sticks._web2ps5_patched = True  # type: ignore[attr-defined]
        Controller.update_sticks = safe_update_sticks  # type: ignore[method-assign]

    # --- 5) Low-latency decode: prefer slice threads (frame threads add lag) ---
    if not getattr(AVReceiver.video_codec, "_web2ps5_patched", False):
        orig_video_codec = AVReceiver.video_codec

        def low_latency_video_codec(codec_name: str):
            ctx = orig_video_codec(codec_name)
            try:
                import av as _av

                # Frame threading reorders / buffers → multi-second lag under load
                slice_t = getattr(_av.codec.context.ThreadType, "SLICE", None)
                if slice_t is not None:
                    ctx.thread_type = slice_t
                ctx.thread_count = 2
            except Exception:
                pass
            return ctx

        low_latency_video_codec._web2ps5_patched = True  # type: ignore[attr-defined]
        AVReceiver.video_codec = staticmethod(low_latency_video_codec)  # type: ignore[method-assign]
        logger.info("Patched AVReceiver.video_codec for slice/low-latency threads")

    # --- 6) Cap AV packet backlog — default maxlen=5000 ≈ many seconds of lag ---
    try:
        from pyremoteplay.av import AVHandler

        if not getattr(AVHandler.__init__, "_web2ps5_patched", False):
            orig_av_init = AVHandler.__init__

            def ll_av_init(self, session):
                orig_av_init(self, session)
                # ~1–2 frames of NAL units, not seconds of backlog
                self._queue = __import__("collections").deque(maxlen=180)

            ll_av_init._web2ps5_patched = True  # type: ignore[attr-defined]
            AVHandler.__init__ = ll_av_init  # type: ignore[method-assign]

        if not getattr(AVHandler.process_packet, "_web2ps5_patched", False):
            orig_process = AVHandler.process_packet

            def ll_process_packet(self):
                q = self._queue
                # Falling behind → drop old packets and resync on next key unit
                if len(q) > 90:
                    keep = 30
                    while len(q) > keep:
                        q.popleft()
                    self._waiting = True
                return orig_process(self)

            ll_process_packet._web2ps5_patched = True  # type: ignore[attr-defined]
            AVHandler.process_packet = ll_process_packet  # type: ignore[method-assign]
            logger.info("Patched AVHandler for low-latency packet drop (maxlen=180)")
    except Exception:
        logger.debug("AVHandler latency patch skipped", exc_info=True)

    # Quiet noisy RP packet / audio decoder logs (harmless with video-only)
    logging.getLogger("pyremoteplay").setLevel(logging.WARNING)
    logging.getLogger("pyremoteplay.av").setLevel(logging.CRITICAL)
    logging.getLogger("pyremoteplay.stream").setLevel(logging.WARNING)
    logging.getLogger("pyremoteplay.protobuf").setLevel(logging.CRITICAL)
    logging.getLogger("libav").setLevel(logging.CRITICAL)

    _patched = True
    logger.info("pyremoteplay compat patches applied (from pi2ps5/capture.py)")
