@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Run run.bat once first to create the venv.
  pause
  exit /b 1
)

if not exist ".env" (
  echo No .env found. Copy .env.example to .env and set WEB2PS5_PS5_HOST.
  pause
  exit /b 1
)

echo Installing / verifying Remote Play extras...
".venv\Scripts\python.exe" -m pip install -r requirements-remoteplay.txt
if errorlevel 1 (
  echo Failed to install requirements-remoteplay.txt
  pause
  exit /b 1
)

REM Force pyremoteplay mode for this process (overrides .env bridge if needed)
set WEB2PS5_BRIDGE=pyremoteplay

echo Starting Web2PS5 ^(pyremoteplay^) at http://127.0.0.1:8000/
echo Press Ctrl+C to stop.
echo.
".venv\Scripts\python.exe" -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
if errorlevel 1 pause
endlocal
