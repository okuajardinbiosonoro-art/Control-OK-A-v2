@echo off
setlocal
cd /d "%~dp0\.."

rem ------------------------------------------------------------
rem Field relay for the fruit diagnostic stream.
rem - Local listener: 0.0.0.0:5006
rem - Local console: touch start / touch end
rem - Remote mirror: forwarded over UDP to the host below
rem ------------------------------------------------------------
if not defined FRUIT_FIELD_PC_TAILSCALE set "FRUIT_FIELD_PC_TAILSCALE=<FIELD_PC_TAILSCALE_IP>"
if not defined FRUIT_DIAG_PC_TAILSCALE (
  echo [fruit-diag] error: define FRUIT_DIAG_PC_TAILSCALE antes de iniciar el relay.
  exit /b 1
)
set "FRUIT_DIAG_FORWARD_HOST=%FRUIT_DIAG_PC_TAILSCALE%"
set "FRUIT_DIAG_FORWARD_PORT=5006"
set "FRUIT_DIAG_FORWARD_PORT_2=5007"
set "SCRIPT_DIR=%~dp0"
set "LISTENER_PY=%SCRIPT_DIR%fruit_diag_listener.py"

if not exist "%LISTENER_PY%" (
  echo [fruit-diag] error: no se encontro el listener esperado.
  echo [fruit-diag] ruta buscada: %LISTENER_PY%
  echo [fruit-diag] verifica que el repo del PC de campo este sincronizado con la version actual.
  pause
  exit /b 1
)

set "PY_CMD=py -3"
where py >nul 2>nul
if errorlevel 1 (
  set "PY_CMD=python"
)

set "LOG_OUT=%SCRIPT_DIR%relay.out.txt"
set "LOG_ERR=%SCRIPT_DIR%relay.err.txt"

:restart
echo [fruit-diag] field Tailscale=%FRUIT_FIELD_PC_TAILSCALE%
echo [fruit-diag] diagnostic Tailscale=%FRUIT_DIAG_PC_TAILSCALE%
echo [fruit-diag] relay start %DATE% %TIME%>> "%LOG_OUT%"
echo [fruit-diag] relay start %DATE% %TIME%>> "%LOG_ERR%"
%PY_CMD% -u "%LISTENER_PY%" --bind 0.0.0.0 --port 5006 --touch-events --forward-host=%FRUIT_DIAG_FORWARD_HOST% --forward-port=%FRUIT_DIAG_FORWARD_PORT% --forward-host-2=%FRUIT_DIAG_FORWARD_HOST% --forward-port-2=%FRUIT_DIAG_FORWARD_PORT_2% >> "%LOG_OUT%" 2>> "%LOG_ERR%"
set "EXIT_CODE=%ERRORLEVEL%"
echo [fruit-diag] listener terminated con codigo %EXIT_CODE%.
echo [fruit-diag] listener terminated con codigo %EXIT_CODE% %DATE% %TIME%>> "%LOG_OUT%"
echo [fruit-diag] listener terminated con codigo %EXIT_CODE% %DATE% %TIME%>> "%LOG_ERR%"
if /I "%FRUIT_DIAG_NO_RESTART%"=="1" exit /b %EXIT_CODE%
echo [fruit-diag] reiniciando en 5 segundos. Cierra esta ventana para detener el relay.
timeout /t 5 /nobreak >nul
goto restart
