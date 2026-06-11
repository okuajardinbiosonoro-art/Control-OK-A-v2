@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

set "PY_CMD=py -3"
where py >nul 2>nul
if errorlevel 1 (
  set "PY_CMD=python"
)

%PY_CMD% -u tools\live_diagnostics_panel.py --label EC1
pause
