@echo off
setlocal
cd /d "%~dp0\.."
set "EXTRA_ARGS="
if defined FRUIT_DIAG_FORWARD_HOST set "EXTRA_ARGS=%EXTRA_ARGS% --forward-host=%FRUIT_DIAG_FORWARD_HOST%"
if defined FRUIT_DIAG_FORWARD_PORT set "EXTRA_ARGS=%EXTRA_ARGS% --forward-port=%FRUIT_DIAG_FORWARD_PORT%"
set "PY_CMD=py -3"
where py >nul 2>nul
if errorlevel 1 (
  set "PY_CMD=python"
)
%PY_CMD% -u tools\fruit_diag_listener.py --bind 0.0.0.0 --port 5006 --touch-events %EXTRA_ARGS%
pause
