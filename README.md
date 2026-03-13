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

- perfil operativo
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

Acciones operativas visibles:

- `Cambiar perfil`: abre selector guiado de perfil operativo.
- `Cambiar modo`: selector tecnico de compatibilidad (fallback).
- `Recargar configuracion`.
- `Herramientas avanzadas`.

La app todavia no inicia una sesion de transporte desde esta UI; por eso se informa estado `sesion no iniciada` o `no disponible aun` donde aplica.

## Config (v2)

- En desarrollo: copiar `config.example.json` a `config.json` en la raiz del repo.
- En ejecutable PyInstaller: `config.json` junto a `Control Okua.exe`.
- Si falta `config.json`, se crea automaticamente con defaults v2.
- Si el archivo esta corrupto, se renombra a `config.corrupt.<timestamp>.json` y se regenera.
- Si detecta CKv1, se crea `config.v1.backup.<timestamp>.json` y se migra a v2.

Campos principales:

- `mode`: `"serial"` o `"udp"` (puede iniciar como `null` antes de seleccionar).
- `profile.active`: perfil operativo activo (`serial_local`, `udp_jardin`, `lab_sim`) o `null`.
- `serial`: baudrate, running_status, flush_ms, max_silence_s, auto_reconnect, port.
- `udp`: bind_ip, evt_port (5005), stat_port (5006), cmd_port (5007), rcvbuf_bytes.
- `midi.outputs`: mapping explicito de buses (`"0"`..`"255"`) a nombre de puerto.
- `thresholds`: `online_ms < degraded_ms < offline_ms`.

Notas de consistencia runtime:

- Si `profile.active` es `null` o invalido, la app pide seleccionar perfil al iniciar.
- Si `profile.active` existe y es valido, el runtime alinea `mode` al perfil esperado.
- Si no hay perfil activo y `mode` es invalido, se usa el selector de modo tecnico como fallback de compatibilidad.
- Si `midi.outputs` llega vacio o invalido, se restauran defaults (`0/1/2 -> loopMIDI Port 1/2/3`).

## Perfiles operativos

El sistema soporta una capa de perfiles operativos para trabajar sin pensar primero en JSON tecnico:

- `serial_local`: uso con Maestro conectado por USB/Serial.
- `udp_jardin`: uso en instalacion OKUA por red UDP.
- `lab_sim`: uso de laboratorio/simulacion; la sesion/simulador aun no estan integrados.

Cada perfil define:

- nombre corto
- descripcion
- modo esperado (`serial` o `udp`)
- nivel de uso
- resumen operativo para UI

Compatibilidad:

- Si `profile.active` falta o es `null`, el arranque sigue siendo compatible y la app solicita perfil.
- `mode` tecnico permanece para compatibilidad interna y herramientas avanzadas.

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

### Test puro de perfiles operativos

Con `pytest` instalado:

```powershell
python -m pytest -q tests/test_profile_service.py
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
