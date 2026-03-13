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

- perfil activo
- modo asociado
- backend esperado
- estado de sesion
- mensaje de sesion
- capacidades de sesion (puede iniciar/detener)
- resumen operativo
- modo tecnico
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
- `Recargar configuracion`.
- `Iniciar sesion`.
- `Detener sesion`.
- `Reiniciar error`.
- `Herramientas avanzadas`.

## Flujo de sesion actual (Ticket 3.3)

- La pestana `Operacion` ahora esta conectada a `SessionController` real.
- El estado de sesion visible refleja snapshot real (`idle`, `starting`, `running`, `stopping`, `error`).
- Con los backends placeholder actuales (sin transporte real), `Iniciar sesion` termina en `error` controlado con mensaje legible.
- `Reiniciar error` devuelve la sesion a estado inactivo.
- Mientras la sesion esta en `starting`, `running` o `stopping`, la UI bloquea cambios de perfil y recarga de config para evitar inconsistencias.

## Perfil como fuente de verdad (coherencia operacional)

- El operador trabaja por `perfil`, no por `mode`.
- `mode` se mantiene como dato tecnico derivado para compatibilidad de config/runtime.
- Al cambiar `profile.active`, la app sincroniza automaticamente `mode` segun el perfil.
- Si una config antigua trae conflicto entre `profile.active` y `mode`, se normaliza a favor del perfil con advertencia tecnica legible.

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
- Si `profile.active` existe y es valido, el runtime normaliza `mode` al valor derivado por perfil.
- Si no hay perfil activo valido, la app mantiene compatibilidad con configs heredadas sin romper el arranque.
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

## Flujo de perfiles (primer arranque)

1. La app carga `config.json`.
2. Si `profile.active` no es valido, abre selector guiado de perfil:
   - `Serial local`
   - `UDP Jardin`
   - `LAB / simulacion`
3. Al confirmar, guarda `profile.active` y ajusta `mode` asociado.
4. Si el perfil ya estaba persistido, no vuelve a preguntar automaticamente.

## Cambiar perfil desde la app

- En `Operacion`, usar `Cambiar perfil`.
- El cambio se guarda en `config.json` y refresca la vista.
- El modo tecnico (`mode`) se deriva automaticamente desde el perfil seleccionado.

## Perfil, modo y configuracion avanzada

- `profile.active` representa la intencion operativa para usuarios no tecnicos.
- `mode` sigue existiendo como dato tecnico de compatibilidad.
- `Herramientas avanzadas` concentra acciones de soporte (ver config, recargar, carpeta, MIDI) sin exponer JSON en la vista principal.

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
2. Confirmar estado inicial de sesion en `inactiva`.
3. Pulsar `Iniciar sesion` y verificar `error` controlado (backend placeholder no implementado).
4. Pulsar `Reiniciar error` y confirmar retorno a estado inactivo.
5. Validar bloqueo de `Cambiar perfil`/`Recargar configuracion` cuando la sesion no esta en estado seguro (`starting`, `running`, `stopping`).
6. Abrir `Herramientas avanzadas` y validar `Ver config`, `Abrir carpeta`, `Recargar config` y `Salidas MIDI`.
7. Cerrar y reabrir la app sin errores.

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
