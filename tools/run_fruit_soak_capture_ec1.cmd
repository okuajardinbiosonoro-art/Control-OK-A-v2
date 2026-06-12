@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0\.."

powershell -NoProfile -ExecutionPolicy Bypass -Command "$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'; $soak = Join-Path (Join-Path (Get-Location) 'artifacts') ('fruit_soak_' + $stamp + '_ec1'); & .\tools\start_fruit_soak_capture_live.ps1 -SoakDir $soak"
if errorlevel 1 exit /b 1

echo [fruit-soak][EC1] capture listeners launched. Keep the watcher window open until 4 pm.
pause
