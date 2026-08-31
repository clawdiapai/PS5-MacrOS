"""Locate or install a local Tesseract binary for end users (Windows-first)."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path
from typing import Any

from backend.app.config import ROOT_DIR

logger = logging.getLogger("web2ps5.vision.tesseract_bootstrap")

_TESS_INSTALLER_NAME = "tesseract-ocr-w64-setup-5.5.0.20241111.exe"

# Try several hosts — digi.bib.uni-mannheim.de often times out on some networks.
_TESS_INSTALLER_URLS = (
    # GitHub release asset (usually reachable)
    "https://github.com/tesseract-ocr/tesseract/releases/download/5.5.0/"
    "tesseract-ocr-w64-setup-5.5.0.20241111.exe",
    # SourceForge mirror
    "https://downloads.sourceforge.net/project/tesseract-ocr.mirror/5.5.0/"
    "tesseract-ocr-w64-setup-5.5.0.20241111.exe",
    # UB Mannheim primary
    "https://digi.bib.uni-mannheim.de/tesseract/"
    "tesseract-ocr-w64-setup-5.5.0.20241111.exe",
)

# Drop an installer here to skip the download entirely.
_LOCAL_INSTALLER_CANDIDATES = (
    ROOT_DIR / "tools" / _TESS_INSTALLER_NAME,
    ROOT_DIR / "tools" / "tesseract-installer.exe",
)

_lock = threading.Lock()
_configured_cmd: str | None = None
# Avoid re-running multi-minute downloads on every wait_ocr poll.
_cached_ok: dict[str, Any] | None = None
_cached_fail: dict[str, Any] | None = None
_cached_fail_at: float = 0.0
_FAIL_COOLDOWN_S = 120.0


def local_tesseract_dir() -> Path:
    d = ROOT_DIR / "tools" / "tesseract"
    d.mkdir(parents=True, exist_ok=True)
    return d


def local_tesseract_exe() -> Path:
    return local_tesseract_dir() / "tesseract.exe"


def _manual_help() -> str:
    return (
        "Could not auto-install Tesseract (network blocked or winget unavailable).\n"
        "Fix options:\n"
        f"  1) Download {_TESS_INSTALLER_NAME} and place it at:\n"
        f"       {ROOT_DIR / 'tools' / _TESS_INSTALLER_NAME}\n"
        "     then POST /api/vision/ocr/ensure or re-run the OCR node.\n"
        "  2) Or run in a terminal:\n"
        "       winget install -e --id UB-Mannheim.TesseractOCR "
        "--accept-package-agreements --accept-source-agreements\n"
        "  3) Or install from:\n"
        "       https://github.com/tesseract-ocr/tesseract/releases/tag/5.5.0"
    )


def _candidate_exes() -> list[Path]:
    out: list[Path] = []
    local = local_tesseract_exe()
    if local.is_file():
        out.append(local)
    which = shutil.which("tesseract")
    if which:
        out.append(Path(which))
    for base in (
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Tesseract-OCR",
        Path.home() / "AppData" / "Local" / "Programs" / "Tesseract-OCR",
    ):
        cand = base / "tesseract.exe"
        if cand.is_file():
            out.append(cand)
    seen: set[str] = set()
    uniq: list[Path] = []
    for p in out:
        key = str(p.resolve()) if p.exists() else str(p)
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    return uniq


def _apply_pytesseract_cmd(exe: Path) -> None:
    global _configured_cmd
    import pytesseract

    cmd = str(exe)
    pytesseract.pytesseract.tesseract_cmd = cmd
    _configured_cmd = cmd
    tessdata = exe.parent / "tessdata"
    if tessdata.is_dir():
        os.environ["TESSDATA_PREFIX"] = str(tessdata)


def _ensure_pytesseract_package() -> None:
    try:
        import pytesseract  # noqa: F401
        return
    except ImportError:
        pass
    logger.info("Installing pytesseract into the current environment…")
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "install", "pytesseract>=0.3.10"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "pip install pytesseract failed:\n"
            + (proc.stdout or "")[-1000:]
            + (proc.stderr or "")[-1000:]
        )


def _probe_exe(exe: Path) -> bool:
    try:
        proc = subprocess.run(
            [str(exe), "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return proc.returncode == 0 and (
            "tesseract" in (proc.stdout or "").lower()
            or "tesseract" in (proc.stderr or "").lower()
        )
    except Exception:
        return False


def find_tesseract() -> Path | None:
    for exe in _candidate_exes():
        if exe.is_file() and _probe_exe(exe):
            return exe
    return None


def _find_local_installer() -> Path | None:
    for p in _LOCAL_INSTALLER_CANDIDATES:
        if p.is_file() and p.stat().st_size > 1_000_000:
            return p
    return None


def _download_installer(dest: Path) -> str:
    """Try each mirror; return the URL that succeeded."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    for url in _TESS_INSTALLER_URLS:
        logger.info("Downloading Tesseract installer from %s …", url)
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Web2PS5-tesseract-bootstrap/1.0"},
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                got = 0
                tmp = dest.with_suffix(dest.suffix + ".partial")
                with open(tmp, "wb") as out:
                    while True:
                        chunk = resp.read(1024 * 256)
                        if not chunk:
                            break
                        out.write(chunk)
                        got += len(chunk)
                if total and got < total * 0.9:
                    raise RuntimeError(f"incomplete download ({got}/{total})")
                if got < 1_000_000:
                    raise RuntimeError(f"download too small ({got} bytes)")
                tmp.replace(dest)
            logger.info("Downloaded %s (%s MB)", dest.name, got // (1024 * 1024))
            return url
        except Exception as exc:
            logger.warning("Download failed from %s: %s", url, exc)
            errors.append(f"{url}: {exc}")
            try:
                partial = dest.with_suffix(dest.suffix + ".partial")
                if partial.is_file():
                    partial.unlink()
            except Exception:
                pass
    raise RuntimeError("All Tesseract download mirrors failed:\n" + "\n".join(errors))


def _silent_install_windows(installer: Path, target_dir: Path) -> None:
    """NSIS silent install into a user-writable project folder."""
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = str(target_dir.resolve())
    cmd = [str(installer), "/S", f"/D={dest}"]
    logger.info("Installing Tesseract silently → %s", dest)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            "Tesseract silent install failed "
            f"(code {proc.returncode}): {(proc.stdout or '')[-500]} {(proc.stderr or '')[-500]}"
        )
    exe = target_dir / "tesseract.exe"
    if not exe.is_file():
        raise RuntimeError(
            f"Tesseract install finished but {exe} is missing — try installing manually"
        )


def _try_winget_install() -> bool:
    winget = shutil.which("winget")
    if not winget:
        logger.info("winget not on PATH — skipping")
        return False
    logger.info("Trying winget install UB-Mannheim.TesseractOCR …")
    proc = subprocess.run(
        [
            winget,
            "install",
            "-e",
            "--id",
            "UB-Mannheim.TesseractOCR",
            "--accept-package-agreements",
            "--accept-source-agreements",
            "--disable-interactivity",
        ],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    logger.info(
        "winget exit=%s\n%s",
        proc.returncode,
        ((proc.stdout or "") + (proc.stderr or ""))[-1500:],
    )
    # 0 = installed, -1978335189 / other codes may mean already installed
    return find_tesseract() is not None


def ensure_tesseract(*, install_if_missing: bool = True) -> dict[str, Any]:
    """
    Make sure pytesseract + a working tesseract.exe are available.

    Windows bootstrap order when missing:
      1) Local installer dropped in tools/
      2) winget install UB-Mannheim.TesseractOCR  (no Mannheim CDN needed)
      3) Download from GitHub / SourceForge / Mannheim mirrors
    """
    import time as _time

    global _cached_ok, _cached_fail, _cached_fail_at

    with _lock:
        if _cached_ok and _cached_ok.get("ok"):
            exe = Path(str(_cached_ok.get("cmd") or ""))
            if exe.is_file():
                _apply_pytesseract_cmd(exe)
                return dict(_cached_ok)

        try:
            _ensure_pytesseract_package()
        except Exception as exc:
            return {"ok": False, "installed": False, "detail": str(exc)}

        existing = find_tesseract()
        if existing is not None:
            _apply_pytesseract_cmd(existing)
            _cached_ok = {
                "ok": True,
                "installed": False,
                "cmd": str(existing),
                "source": "existing",
            }
            _cached_fail = None
            return dict(_cached_ok)

        if not install_if_missing:
            return {
                "ok": False,
                "installed": False,
                "detail": "Tesseract binary not found",
            }

        # Don't re-hammer dead mirrors on every wait_ocr poll
        if (
            _cached_fail
            and (_time.monotonic() - _cached_fail_at) < _FAIL_COOLDOWN_S
        ):
            return dict(_cached_fail)

        if sys.platform != "win32":
            return {
                "ok": False,
                "installed": False,
                "detail": (
                    "Auto-install is Windows-only for now. "
                    "Install tesseract via your package manager "
                    "(e.g. apt install tesseract-ocr)."
                ),
            }

        target = local_tesseract_dir()
        errors: list[str] = []

        # 1) User-dropped installer
        local_inst = _find_local_installer()
        if local_inst is not None:
            try:
                logger.info("Using local installer %s", local_inst)
                _silent_install_windows(local_inst, target)
                exe = local_tesseract_exe()
                if _probe_exe(exe):
                    _apply_pytesseract_cmd(exe)
                    _cached_ok = {
                        "ok": True,
                        "installed": True,
                        "cmd": str(exe),
                        "source": "local_installer",
                    }
                    return dict(_cached_ok)
                errors.append(f"local installer ran but probe failed: {exe}")
            except Exception as exc:
                logger.exception("Local installer failed")
                errors.append(f"local installer: {exc}")

        # 2) winget FIRST (works when Mannheim/GitHub CDN is blocked)
        try:
            if _try_winget_install():
                exe = find_tesseract()
                if exe is not None:
                    _apply_pytesseract_cmd(exe)
                    _cached_ok = {
                        "ok": True,
                        "installed": True,
                        "cmd": str(exe),
                        "source": "winget",
                    }
                    return dict(_cached_ok)
            errors.append("winget did not yield a working tesseract.exe")
        except Exception as exc:
            logger.exception("winget install failed")
            errors.append(f"winget: {exc}")

        # Re-check — winget may have installed while find raced
        existing = find_tesseract()
        if existing is not None:
            _apply_pytesseract_cmd(existing)
            _cached_ok = {
                "ok": True,
                "installed": True,
                "cmd": str(existing),
                "source": "existing_after_winget",
            }
            return dict(_cached_ok)

        # 3) Download mirrors → silent install into tools/tesseract
        try:
            with tempfile.TemporaryDirectory(prefix="web2ps5-tess-") as tmp:
                installer = Path(tmp) / _TESS_INSTALLER_NAME
                url = _download_installer(installer)
                _silent_install_windows(installer, target)
                try:
                    shutil.copy2(installer, ROOT_DIR / "tools" / _TESS_INSTALLER_NAME)
                except Exception:
                    pass
            exe = local_tesseract_exe()
            if _probe_exe(exe):
                _apply_pytesseract_cmd(exe)
                logger.info("Tesseract ready at %s (from %s)", exe, url)
                _cached_ok = {
                    "ok": True,
                    "installed": True,
                    "cmd": str(exe),
                    "source": "download",
                    "url": url,
                }
                return dict(_cached_ok)
            errors.append(f"download install probe failed: {exe}")
        except Exception as exc:
            logger.exception("Tesseract download/install failed")
            errors.append(f"download: {exc}")

        detail = _manual_help() + "\n\nAttempts:\n- " + "\n- ".join(errors)
        _cached_fail = {"ok": False, "installed": False, "detail": detail}
        _cached_fail_at = _time.monotonic()
        return dict(_cached_fail)


def configure_if_present() -> bool:
    """Best-effort: point pytesseract at a found binary without downloading."""
    try:
        _ensure_pytesseract_package()
    except Exception:
        return False
    exe = find_tesseract()
    if exe is None:
        return False
    _apply_pytesseract_cmd(exe)
    return True
