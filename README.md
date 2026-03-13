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

- En desarrollo: copiar `config.example.json` a `config.json` en la raiz del repo.
- En ejecutable PyInstaller: `config.json` junto a `Control Okua.exe`.
- Si falta `config.json`, se crea automaticamente con defaults v2.
- Si el archivo esta corrupto, se renombra a `config.corrupt.<timestamp>.json` y se regenera.
- Si detecta CKv1, se crea `config.v1.backup.<timestamp>.json` y se migra a v2.

Campos principales:

- `mode`: `"serial"` o `"udp"` (puede iniciar como `null` antes de seleccionar).
- `serial`: baudrate, running_status, flush_ms, max_silence_s, auto_reconnect, port.
- `udp`: bind_ip, evt_port (5005), stat_port (5006), cmd_port (5007), rcvbuf_bytes.
- `midi.outputs`: mapping explicito de buses (`"0"`..`"255"`) a nombre de puerto.
- `thresholds`: `online_ms < degraded_ms < offline_ms`.

## Seleccion de modo

- En primer arranque, si `mode` no esta definido o es invalido, la app pide elegir `Serial` o `Ethernet/UDP`.
- La seleccion se guarda inmediatamente en `config.json`.
- Para cambiar de modo luego, editar `config.json` manualmente (mas adelante se agregara desde UI).

## UI base

- La ventana principal muestra:
  - modo actual
  - ruta del `config.json`
  - advertencias recientes de configuracion
  - resumen de config
  - panel de salidas MIDI configuradas y puertos detectados
- Acciones disponibles:
  - `Cambiar modo...`: reusa el selector Serial/UDP y guarda el nuevo valor en `config.json`
  - `Recargar config`: vuelve a leer el archivo y refresca toda la UI
  - `Abrir carpeta`: abre la carpeta que contiene `config.json`
  - `Ver config`: muestra el JSON actual en solo lectura

## Prueba MIDI (LoopMIDI / Ableton)

- Requisitos:
  - Tener instalado LoopMIDI.
  - Crear un puerto de salida (por ejemplo `loopMIDI Port 1`).
  - Configurar ese nombre en `config.json` dentro de `midi.outputs`, por ejemplo:
    - `"outputs": {"0": "loopMIDI Port 1"}`
- Comando:
  - `python tools/list_midi_ports.py`
  - `python tools/midi_smoke_test.py`
- Que esperar:
  - `list_midi_ports.py` muestra backend, entradas y salidas detectadas por Mido/RtMidi.
  - El script envia una secuencia corta de notas MIDI.
  - En Ableton deberia verse actividad MIDI de entrada (o sonido si la pista esta armada).
- Si falla:
  - Si `available_outputs=[]`, abrir LoopMIDI y crear al menos `loopMIDI Port 1`.
  - Verificar que el nombre del puerto en `config.json` coincida exactamente con el nombre real.
  - Comparar `midi.outputs` de `config.json` contra la salida de `python tools/list_midi_ports.py`.
  - Si `midi.outputs` queda vacio o invalido, la app lo restaura automaticamente a defaults (`0/1/2 -> loopMIDI Port 1/2/3`) y guarda el archivo.

### Troubleshooting nombres loopMIDI (Windows)

- En Windows, loopMIDI puede aparecer con sufijo numerico (por ejemplo `loopMIDI Port 1 1`) aunque en config este como `loopMIDI Port 1`.
- CKv2 intenta resolver automaticamente por prefijo (`loopMIDI Port 1` -> `loopMIDI Port 1 1`) y muestra el mapeo resuelto en logs.
- Para listar los nombres reales detectados por Mido/RtMidi:
  - `python tools/list_midi_ports.py`
- Para actualizar `config.json` con los nombres exactos resueltos (opt-in):
  - `$env:CKV2_AUTOFIX_OUTPUTS='1'`
  - `python tools/midi_smoke_test.py`
  - `Remove-Item Env:CKV2_AUTOFIX_OUTPUTS`
