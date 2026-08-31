#!/usr/bin/env python3
"""Launch Web2PS5 with a reliable Remote Play teardown on exit.

Why not bare ``uvicorn --reload``?
  The reloader parent often kills the worker without running FastAPI lifespan,
  which leaves the PS5 Remote Play slot occupied ("Another Remote Play session…").

This launcher:
  - runs uvicorn in-process (no --reload by default)
  - still relies on main.py atexit / console-close hooks for sync disconnect
  - optional WEB2PS5_RELOAD=1 for local JS/Python hot reload (accept sticky-slot risk)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def main() -> int:
    import uvicorn

    from backend.app.logging_filters import install_quiet_access_log

    install_quiet_access_log()

    host = os.environ.get("WEB2PS5_BIND_HOST", "127.0.0.1")
    port = int(os.environ.get("WEB2PS5_BIND_PORT", "8000"))
    reload_on = os.environ.get("WEB2PS5_RELOAD", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    if reload_on:
        print(
            "WARNING: WEB2PS5_RELOAD=1 — if you kill the console, the PS5 RP "
            "slot may stick. Prefer Ctrl+C, or use RP Disconnect first."
        )

    # lifespan + atexit in backend.app.main handle disconnect
    # Access log still on, but detect/health/preview spam is filtered.
    uvicorn.run(
        "backend.app.main:app",
        host=host,
        port=port,
        reload=reload_on,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
