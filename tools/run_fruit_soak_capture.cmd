@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0\.."

powershell -NoProfile -ExecutionPolicy Bypass -File tools\start_fruit_soak_capture_live.ps1
if errorlevel 1 exit /b 1

echo [fruit-soak] capture listeners launched. Keep the watcher window open until 4 pm.
pause
