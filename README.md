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

- Pestaña inicial `Operacion` con resumen operativo compacto, acciones rapidas y bloques de actividad runtime (serial/UDP).
- Pestaña `Estado actual` con el detalle largo de sesion en tarjetas tecnicas, scroll interno y layout responsive (2 columnas en ancho amplio, 1 columna en ancho estrecho).
- Pestaña `Nodos` con tabla real por nodo (estado, ultimo visto, pps, perdida, RSSI y ultimo note/vel) alimentada desde snapshots del `SessionController`.
- Pestaña `Diagnostico` con resumen tecnico, advertencias de configuracion, detalle del ultimo preflight y runtime serial/UDP.

En `Operacion` tambien aparece el bloque `Preparacion de sesion`, que resume:

- readiness actual (`Lista`, `Lista con advertencias`, `No lista`)
- resumen corto del ultimo preflight
- conteo de bloqueos/advertencias
- motivo principal y nota de separacion entre readiness/config y runtime/backend

En `Operacion` tambien aparece el bloque `Actividad serial`, con resumen compacto de:

- estado serial (`Activo`, `Sin actividad reciente`, `Con error`, `No disponible`)
- puerto actual (si aplica)
- mensajes procesados
- ultimo error y actividad reciente

En `Operacion` tambien aparece el bloque `Actividad UDP`, con resumen compacto de:

- estado UDP (`Activo`, `Sin actividad reciente`, `Con error`, `No disponible`)
- bind y puertos EVT/STAT
- contadores basicos EVT/STAT
- ultimo error y actividad reciente

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

## Flujo de sesion y readiness (Tickets 3.3 + 4.x)

- La pestana `Operacion` esta conectada a `SessionController` real y muestra snapshot de sesion (`idle`, `starting`, `running`, `stopping`, `error`).
- Antes de intentar backend, `SessionController` ejecuta preflight/readiness puro.
- Si readiness esta `blocked`, no intenta backend y la sesion pasa a `error` controlado con motivo de configuracion.
- Si readiness esta `ready` o `ready_with_warnings`, se intenta backend.
- `Operacion` muestra el resumen de readiness y `Diagnostico` muestra findings (severidad, codigo, mensaje, detalle).
- La UI distingue fallo por readiness/configuracion vs fallo posterior de backend/runtime.
- `Reiniciar error` devuelve la sesion a estado inactivo y refresca readiness visible.
- Mientras la sesion esta en `starting`, `running` o `stopping`, la UI bloquea cambios de perfil y recarga de config para evitar inconsistencias.

## Flujo serial real (Tickets 5.1 a 5.3)

- Existe parser incremental MIDI por bytes (`MidiByteStreamParser`) para stream serial.
- Existe `SerialTransportAdapter` real con lectura, parseo y metricas runtime.
- El backend serial real se integra en el lifecycle de sesion via `SessionBackendFactory` + `SessionController`.
- El flujo en arquitectura es: `Serial -> parser -> backend serial -> MidiRouter`.
- `SessionController` solo deja la sesion en `running` si el backend serial arranca realmente.
- `Operacion` muestra actividad serial resumida y `Diagnostico` muestra detalle tecnico de runtime serial.

## Flujo UDP runtime y NodeRegistry (Tickets 6.x + 7.x)

- Existe parser binario UDP OKUA (`OKUA_HDR + EVT + STAT`) con validaciones y descarte controlado.
- Existe `UdpTransportAdapter` real con bind, recepcion en background y metricas runtime.
- Existe `UdpSessionBackend` real integrado al lifecycle de sesion via `SessionBackendFactory` + `SessionController`.
- El flujo en arquitectura es: `UDP -> parser OKUA -> backend UDP -> MidiRouter (EVT)` y `STAT -> runtime interno`.
- `SessionController` solo deja la sesion en `running` si el backend UDP arranca realmente (sin `running` falso).
- El backend UDP alimenta `NodeRegistry` por paquete parseado (`EVT -> observe_evt`, `STAT -> observe_stat`) sin duplicar parser ni dominio.
- `SessionController` expone `get_node_snapshots()` y `get_node_registry_summary()` para consumo UI.
- La pestaña `Nodos` usa esos snapshots como fuente de verdad (sin recalcular estado/pps/perdida en UI).
- La UI distingue estado de runtime UDP (Operacion/Diagnostico) vs estado por nodo (pestaña Nodos).
- La pestaña `Nodos` no inventa datos en no-UDP: muestra mensaje de no aplicacion. En UDP corriendo sin trafico, muestra estado vacio coherente.
- `Operacion` muestra actividad UDP resumida y `Diagnostico` muestra detalle tecnico de runtime UDP.
- `Estado actual` concentra el detalle largo de sesion de forma responsive para evitar saturar `Operacion`.
- `NodeRegistry` se reinicia por sesion UDP, evitando nodos fantasmas entre stop/restart.

## Recording por sesion y replay basico (Tickets 8.x)

- El recording por sesion ya esta integrado al lifecycle real via `SessionController` cuando `logging.enabled=true`.
- El formato canonico de evidencia es `JSONL` (archivo `session.jsonl` por sesion).
- Los artefactos por sesion se guardan en `logs/sessions/<session_id>/`:
  - `session.jsonl`
  - `report.json`
- El flujo puede dejar evidencia util incluso si `start_session()` falla (por preflight bloqueado o error de backend).
- `report.json` resume metadatos finales de sesion y contadores agregados observados durante el intento/ejecucion.
- El replay basico ya existe y se alimenta desde `session.jsonl`, usando como fuente canonica:
  - `event_type = midi_event`
  - `ts_rel_ms` para timing relativo
- El replay ignora eventos no musicales para reproduccion (ej. `udp_evt`, `serial_message`, runtime snapshots), que se mantienen para analisis/post-mortem.
- La separacion de responsabilidades queda en:
  - lifecycle real: `SessionController` + backends
  - recording: `core/recording` (writer + accumulator + report)
  - replay: `core/recording` (loader/extractor/replayer basico)

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
- `profile.active`: perfil operativo activo (`serial_local`, `udp_jardin`, `lab_sim`, `udp_bench_lab`) o `null`.
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
- `lab_sim`: uso de laboratorio/simulacion sobre runtime UDP real.
- `udp_bench_lab`: compatibilidad explicita de laboratorio para BenchPktV0 (ver=0/len=32).

Cada perfil define:

- nombre corto
- descripcion
- modo esperado (`serial` o `udp`)
- nivel de uso
- resumen operativo para UI

Regla practica entre perfiles UDP:

- `udp_jardin`: flujo productivo final; acepta solo protocolo OKUA v1.
- `udp_bench_lab`: compatibilidad de laboratorio para nodos BenchPktV0 actuales.

Compatibilidad:

- Si `profile.active` falta o es `null`, el arranque sigue siendo compatible y la app solicita perfil.
- `mode` tecnico permanece para compatibilidad interna y herramientas avanzadas.

## Flujo de perfiles (primer arranque)

1. La app carga `config.json`.
2. Si `profile.active` no es valido, abre selector guiado de perfil:
   - `Serial local`
   - `UDP Jardin`
   - `LAB / simulacion`
   - `UDP Bench LAB`
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

### Emisor de prueba UDP OKUA v1 (recomendado)

```powershell
# Vectores de referencia (sin enviar trafico)
python tools/udp_okua_v1_sender.py --dry-run

# Trafico OKUA v1 para CKv2 local
python tools/udp_okua_v1_sender.py --host 127.0.0.1 --evt-port 5005 --stat-port 5006 --count 50 --interval-ms 20
```

Referencia tecnica de compatibilidad:

- `docs/protocol/udp_bench_vs_okua_v1.md`

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
3. Verificar en `Operacion` los bloques `Preparacion de sesion`, `Actividad serial` y `Actividad UDP`.
4. Verificar en `Diagnostico` el bloque de preflight y los bloques de runtime serial/UDP.
5. Verificar la pestaña `Estado actual`:
   - detalle navegable con scroll interno
   - 2 columnas en ancho amplio
   - 1 columna en ancho estrecho
6. Caso serial con config valida declarativa: readiness `Lista` o `Lista con advertencias`; al iniciar, validar:
   - si hay puerto/hardware disponible, sesion serial en `running`
   - si no hay puerto/hardware disponible, error runtime serial legible y sin `running` falso
7. Caso UDP con config valida declarativa: readiness `Lista` o `Lista con advertencias`; al iniciar, validar:
   - backend UDP en `running` si bind correcto
   - actividad/contadores en bloques UDP cuando hay trafico
   - error runtime legible y sin `running` falso cuando hay fallo de bind/config
8. Pestaña `Nodos` en sesion no-UDP: validar mensaje de no aplicacion (sin nodos inventados).
9. Pestaña `Nodos` en UDP corriendo sin trafico: validar estado vacio coherente.
10. Pestaña `Nodos` en UDP con trafico: validar tabla visible con filas reales y columnas coherentes.
11. Stop/restart de sesion UDP: validar limpieza visual y ausencia de nodos fantasmas.
12. Perfil `udp_bench_lab`: validar compatibilidad bench (EVT/STAT/PING/PONG) sin error de version.
13. Perfil `udp_jardin`: validar que BenchPktV0 siga rechazado con diagnostico de incompatibilidad.
12. Caso config invalida para readiness: validar estado `No lista` y findings bloqueantes en `Diagnostico`.
13. Pulsar `Reiniciar error` y confirmar retorno a estado inactivo con refresco visual coherente.
14. Validar bloqueo de `Cambiar perfil`/`Recargar configuracion` cuando la sesion no esta en estado seguro (`starting`, `running`, `stopping`).
15. Abrir `Herramientas avanzadas` y validar `Ver config`, `Abrir carpeta`, `Recargar config` y `Salidas MIDI`.
16. Cerrar y reabrir la app sin errores.

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
