@echo off
setlocal

rem Instala una tarea programada que abre el relay del diagnóstico de fruta
rem en cada inicio de sesión del usuario actual.

set "SCRIPT_DIR=%~dp0"
set "RUNNER=%SCRIPT_DIR%run_fruit_diag_field_relay.cmd"
set "TASK_NAME=OKUA Fruit Diag Relay EB1"

if not exist "%RUNNER%" (
  echo [fruit-diag] error: no se encontro el lanzador esperado:
  echo %RUNNER%
  pause
  exit /b 1
)

schtasks /Create /F /SC ONLOGON /RL LIMITED /TN "%TASK_NAME%" /TR "cmd.exe /c ""%RUNNER%"""
if errorlevel 1 (
  echo [fruit-diag] error: no se pudo crear la tarea programada.
  pause
  exit /b 1
)

schtasks /Change /TN "%TASK_NAME%" /ENABLE >nul 2>nul

echo [fruit-diag] tarea programada instalada: %TASK_NAME%
echo [fruit-diag] se ejecutara al iniciar sesion el usuario actual.
pause
