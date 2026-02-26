# Control-OK-A-v2

## Ticket 0 — Arranque

### 1) Crear entorno virtual

Windows (PowerShell):

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

Linux/macOS:

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

### 2) Ejecutar en desarrollo

python main.py

### 3) Build con PyInstaller

pyinstaller ControlOkuaV2.spec

El ejecutable queda en:

dist/Control Okua.exe

Para ejecutarlo (PowerShell):

.\dist\Control` Okua.exe

## Config (v2)

- En desarrollo: `config.json` en la raiz del repo.
- En ejecutable PyInstaller: `config.json` junto a `Control Okua.exe`.
- Si falta `config.json`, se crea automaticamente con defaults v2.
- Si el archivo esta corrupto, se renombra a `config.corrupt.<timestamp>.json` y se regenera.
- Si detecta CKv1, se crea `config.v1.backup.<timestamp>.json` y se migra a v2.

Campos principales:

- `mode`: `"serial"` o `"udp"`.
- `serial`: baudrate, running_status, flush_ms, max_silence_s, auto_reconnect, port.
- `udp`: bind_ip, evt_port (5005), stat_port (5006), cmd_port (5007), rcvbuf_bytes.
- `midi.outputs`: mapping explicito de buses (`"0"`..`"255"`) a nombre de puerto.
- `thresholds`: `online_ms < degraded_ms < offline_ms`.
