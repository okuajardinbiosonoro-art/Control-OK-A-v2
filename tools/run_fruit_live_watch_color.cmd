@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

powershell -NoProfile -ExecutionPolicy Bypass -File tools\fruit_live_watch_color.ps1
pause
