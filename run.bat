@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtualenv...
  python -m venv .venv
  if errorlevel 1 (
    echo Failed to create .venv. Is Python on PATH?
    pause
    exit /b 1
  )
  echo Installing dependencies...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo pip install failed.
    pause
    exit /b 1
  )
)

echo Starting Web2PS5 at http://127.0.0.1:8000/
echo Opens the studio. Setup wizard only if onboarding is incomplete.
echo.
echo IMPORTANT: Prefer Ctrl+C to stop (releases Remote Play).
echo Closing the window X is handled too, but Ctrl+C is safest.
echo For hot-reload during coding use run-dev.bat (can stick the PS5 RP slot).
echo.
REM Open studio (not /setup). studio.js redirects to /setup only when needed.
powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8000/'"
REM No --reload here: reloader orphans Remote Play sessions when the console dies.
".venv\Scripts\python.exe" tools\run_server.py
if errorlevel 1 pause
endlocal
