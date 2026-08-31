"""Uvicorn access-log filters — drop high-frequency studio chatter."""

from __future__ import annotations

import logging
import re

# Paths (and prefixes) that poll often and drown useful logs.
_QUIET_PATHS = (
    "/api/anchors/detect",
    "/api/health",
    "/api/console/status",
    "/api/vision/ocr",
    "/api/passthrough",
    "/api/preview/",
    "/api/frame/meta",
    "/ws/telemetry",
)

# uvicorn.access message looks like:
#   127.0.0.1:12345 - "POST /api/anchors/detect HTTP/1.1" 200
_REQ = re.compile(r'"[A-Z]+ ([^"?\s]+)')


class QuietAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        m = _REQ.search(msg)
        path = m.group(1) if m else msg
        for quiet in _QUIET_PATHS:
            if path == quiet or path.startswith(quiet):
                return False
        return True


def install_quiet_access_log() -> None:
    """Attach QuietAccessFilter to uvicorn.access (idempotent)."""
    log = logging.getLogger("uvicorn.access")
    for f in log.filters:
        if isinstance(f, QuietAccessFilter):
            return
    log.addFilter(QuietAccessFilter())
