@echo off
setlocal
cd /d "%~dp0\.."

rem Consola de diagnostico de fruta para el PC de observacion.
rem Espera una copia de FRUITDIAG reenviada desde el PC de campo.

set "DIAG_BIND=0.0.0.0"
set "DIAG_PORT=5007"
set "PY_CMD=py -3"
where py >nul 2>nul
if errorlevel 1 (
  set "PY_CMD=python"
)

%PY_CMD% -u tools\fruit_diag_listener.py --bind %DIAG_BIND% --port %DIAG_PORT%
pause
