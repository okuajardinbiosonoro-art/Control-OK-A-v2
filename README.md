# Control-OK-A-v2

## Arranque rapido

### 1) Crear entorno virtual

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2) Ejecutar en desarrollo

```powershell
python main.py
```

### 3) Build con PyInstaller

```powershell
pyinstaller ControlOkuaV2.spec
```

El ejecutable queda en `dist/Control Okua.exe`.

## Estado actual de la app (UX)

La ventana principal usa flujo operator-first:

- Pestaña inicial `Operacion` con resumen operativo y acciones rapidas.
- Pestaña `Nodos` con estructura preparada (tabla vacia y estado sin datos en vivo).
- Pestaña `Diagnostico` con resumen tecnico y advertencias de configuracion.

En `Operacion` aparecen tarjetas de estado para:

- modo activo
- transporte configurado
- MIDI
- logging
- estado general

Las acciones tecnicas se movieron a `Herramientas avanzadas`:

- ruta de `config.json`
- abrir carpeta de config
- ver config JSON
- recargar config
- widget de salidas MIDI

La app todavia no inicia una sesion de transporte desde esta UI; por eso se informa estado `sesion no iniciada` o `no disponible aun` donde aplica.

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

Notas de consistencia runtime:

- Si `mode` es invalido o `null`, la app pide seleccionar modo al iniciar y persiste el valor.
- Si `midi.outputs` llega vacio o invalido, se restauran defaults (`0/1/2 -> loopMIDI Port 1/2/3`).

## Validacion y pruebas

### Compileall

```powershell
python -m compileall src main.py tools
```

### Test puro del view-model (sin UI)

Con `pytest` instalado:

```powershell
python -m pytest -q tests/test_main_window_vm.py
```

### Abrir la app

```powershell
python main.py
```

Smoke corto automatizado (opcional):

```powershell
$env:CKV2_AUTOCLOSE_MS='1200'
python main.py
Remove-Item Env:CKV2_AUTOCLOSE_MS
```

### Smoke manual basico

1. Verificar que la primera pestaña sea `Operacion`.
2. Confirmar que la pantalla principal no sea config-first.
3. Abrir `Herramientas avanzadas` y validar `Ver config`, `Abrir carpeta`, `Recargar config` y `Salidas MIDI`.
4. Cambiar modo desde UI, cerrar, reabrir y confirmar persistencia.

## Prueba MIDI (LoopMIDI / Ableton)

Requisitos:

- Tener instalado LoopMIDI.
- Crear un puerto de salida (por ejemplo `loopMIDI Port 1`).
- Configurar ese nombre en `config.json` dentro de `midi.outputs`.

Comandos:

```powershell
python tools/list_midi_ports.py
python tools/midi_smoke_test.py
```

Si falla:

- Si `available_outputs=[]`, abrir LoopMIDI y crear al menos `loopMIDI Port 1`.
- Verificar que el nombre del puerto en `config.json` coincida exactamente con el nombre real.
- Comparar `midi.outputs` de `config.json` contra la salida de `python tools/list_midi_ports.py`.

### Troubleshooting nombres loopMIDI (Windows)

- En Windows, loopMIDI puede aparecer con sufijo numerico (ejemplo: `loopMIDI Port 1 1`) aunque en config este como `loopMIDI Port 1`.
- CKv2 intenta resolver automaticamente por prefijo y muestra el mapeo resuelto en logs.
- Para actualizar `config.json` con los nombres exactos resueltos (opt-in):

```powershell
$env:CKV2_AUTOFIX_OUTPUTS='1'
python tools/midi_smoke_test.py
Remove-Item Env:CKV2_AUTOFIX_OUTPUTS
```
