@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Create the venv first by running run.bat once.
  pause
  exit /b 1
)

echo Starting Web2PS5 DEV mode ^(uvicorn --reload^) at http://127.0.0.1:8000/
echo WARNING: killing this window can leave "Another Remote Play session" stuck.
echo Prefer Ctrl+C, or click RP Disconnect in the studio before quitting.
echo.
set WEB2PS5_RELOAD=1
powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8000/'"
".venv\Scripts\python.exe" tools\run_server.py
if errorlevel 1 pause
endlocal
