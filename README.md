# Control OKUA CKv2

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

El ejecutable queda en `dist/Control OKUA CKv2.exe`.

## Estado actual de la app (UX)

La ventana principal usa una shell no modal con navegación lateral persistente y un stack interno con tabs ocultas:

- Superficies principales: `Inicio`, `Nodos`, `Diagnóstico`, `Firmware`, `Técnico`, `Remoto`.
- Vista `Estado actual` disponible bajo demanda desde la propia app, sin ocupar la portada.
- `Inicio` es la entrada principal y usa el plano real del repo como protagonista visual.
- `Nodos` sigue agrupando cajas desplegables (`Caja 1` a `Caja 5`) con nombres lógicos (`EB1`, `EC1`, `...`).
- `Diagnóstico` concentra resumen técnico, advertencias y panel de preflight desplegable.
- `Técnico` integra `Control F3` y herramientas avanzadas.
- `Firmware` deja visible el acceso al `Firmware Manager`.
- `Remoto` queda confirmado como superficie principal de primer nivel porque ya expone estado y control rápido del servicio remoto sin depender del diálogo avanzado.
- `Inicio` queda definida como portada limpia: mapa protagonista, estado breve de sesión y una única acción principal visible.
- El detalle operativo y técnico vive fuera de la portada:
  - `Estado actual` concentra el resumen largo de sesión
  - `Diagnóstico` concentra readiness, advertencias y runtime
  - `Técnico` concentra control avanzado y herramientas delicadas
  - `Remoto` concentra el estado y acceso del servicio remoto

Acciones y menú principal:

- `Inicio` mantiene una acción primaria visible: `Iniciar sesión` o `Detener sesión`, según el estado real.
- Las acciones secundarias de la Home se reducen a `Estado actual` y `Reiniciar error` dentro de `Más`.
- `Cambiar perfil` queda como ruta única bajo `Aplicación`.
- Menú superior reducido:
  - `Aplicación`: `Cambiar perfil`, `Recargar configuración`, `Salir`
  - `Ayuda`: `Acerca de`

## Flujo de sesion y readiness (Tickets 3.3 + 4.x)

- La Home `Inicio` está conectada a `SessionController` real y muestra un resumen breve de sesión (`idle`, `starting`, `running`, `stopping`, `error`).
- Antes de intentar backend, `SessionController` ejecuta preflight/readiness puro.
- Si readiness esta `blocked`, no intenta backend y la sesion pasa a `error` controlado con motivo de configuracion.
- Si readiness esta `ready` o `ready_with_warnings`, se intenta backend.
- `Inicio` mantiene la portada limpia y `Diagnostico` muestra findings (severidad, codigo, mensaje, detalle).
- La UI distingue fallo por readiness/configuracion vs fallo posterior de backend/runtime.
- `Reiniciar error` devuelve la sesion a estado inactivo y refresca readiness visible.
- Mientras la sesion esta en `starting`, `running` o `stopping`, la UI bloquea cambios de perfil y recarga de config para evitar inconsistencias.

## Flujo serial real (Tickets 5.1 a 5.3)

- Existe parser incremental MIDI por bytes (`MidiByteStreamParser`) para stream serial.
- Existe `SerialTransportAdapter` real con lectura, parseo y metricas runtime.
- El backend serial real se integra en el lifecycle de sesion via `SessionBackendFactory` + `SessionController`.
- El flujo en arquitectura es: `Serial -> parser -> backend serial -> MidiRouter`.
- `SessionController` solo deja la sesion en `running` si el backend serial arranca realmente.
- `Diagnostico` muestra el detalle tecnico de runtime serial sin recargar la portada `Inicio`.

## Flujo UDP runtime y NodeRegistry (Tickets 6.x + 7.x)

- Existe parser binario UDP OKUA (`OKUA_HDR + EVT + STAT`) con validaciones y descarte controlado.
- Existe `UdpTransportAdapter` real con bind, recepcion en background y metricas runtime.
- Existe `UdpSessionBackend` real integrado al lifecycle de sesion via `SessionBackendFactory` + `SessionController`.
- El flujo en arquitectura es: `UDP -> parser OKUA -> backend UDP -> MidiRouter (EVT)` y `STAT -> runtime interno`.
- `SessionController` solo deja la sesion en `running` si el backend UDP arranca realmente (sin `running` falso).
- El backend UDP alimenta `NodeRegistry` por paquete parseado (`EVT -> observe_evt`, `STAT -> observe_stat`) sin duplicar parser ni dominio.
- `SessionController` expone `get_node_snapshots()` y `get_node_registry_summary()` para consumo UI.
- La pestaña `Nodos` usa esos snapshots como fuente de verdad (sin recalcular estado/pps/perdida en UI).
- La UI distingue estado de runtime UDP (`Diagnostico`) vs estado por nodo (pestaña Nodos).
- La pestaña `Nodos` no inventa datos en no-UDP: muestra mensaje de no aplicacion. En UDP corriendo sin trafico, muestra estado vacio coherente.
- `Diagnostico` muestra el detalle tecnico de runtime UDP.
- `Estado actual` concentra el detalle largo de sesion de forma responsive para evitar saturar `Inicio`.
- `NodeRegistry` se reinicia por sesion UDP, evitando nodos fantasmas entre stop/restart.

## Identidad de nodos y ruteo MIDI

La política es explícita y determinista, y no depende de IP/router:

- Identidad de nodo: `node_id`.
- Nombre lógico: función pura de `node_id` (patrón `EB/EC/ED/EE/EF` por caja).
- Caja: función pura de `node_id` (`1..5 -> Caja 1`, `6..10 -> Caja 2`, etc.).
- Bus MIDI: función pura de caja:
  - `Caja 1` a `Caja 3` -> `midi_bus=0` (LoopMIDI 1)
  - `Caja 4` a `Caja 5` -> `midi_bus=1` (LoopMIDI 2)

Precedencia en runtime UDP:

- CKv2 deriva el bus efectivo desde `node_id -> caja -> midi_bus`.
- Si el paquete trae otro `midi_bus`, prevalece la política por caja.

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
- `profile.active`: perfil operativo activo (`serial_local`, `udp_jardin`, `lab_sim`) o `null`.
- `serial`: baudrate, running_status, flush_ms, max_silence_s, auto_reconnect, port.
- `udp`: bind_ip, evt_port (5005), stat_port (5006), cmd_port (5007), rcvbuf_bytes.
- `midi.outputs`: mapping explicito de buses (`"0"`..`"255"`) a nombre de puerto.
- `thresholds`: `online_ms < degraded_ms < offline_ms`.

## Control Plane F3 (Ticket 14.1)

- El emisor app-side de `OKUA_CMD` usa secreto compartido via entorno:
  - `CKV2_CONTROL_SECRET` (preferido)
  - `CKV2_CONTROL_SECRET_FILE` (ruta opcional a archivo local no trackeado)
- Si no hay secreto configurado, el servicio de comandos falla de forma explicita y no envia paquetes.
- El estado local de nonce (`last_control_epoch_s`) se persiste en `control_plane_state.json` para mantener monotonia entre reinicios.
- En este ticket, el servicio es estrictamente send-only al `CMD_PORT=5007` y no abre listener de `ACK_PORT=5008`.

## Control Plane F3 (Ticket 14.2)

- Existe `AckListenerService` aislado para `OKUA_ACK` con bind explícito en `ACK_PORT=5008`.
- El parseo de ACK es estricto (`28 bytes`, `magic`, `version`, `type`) y clasifica datagramas inválidos.
- Existe `PendingCommandStore` para correlación básica por `cmd_seq + cmd_id_echo + nonce_echo` con resultados:
  - `MATCHED`
  - `UNMATCHED_ACK`
  - `INVALID_ACK`
- Aún no se implementan timeout/retry ni auditoría persistente final (quedan para 14.3+).

## Control Plane F3 (Ticket 14.3)

- Existe `ControlTransactionService` para ejecutar transacciones F3 sin UI.
- El flujo cubre:
  - envío de CMD
  - registro de pendiente
  - espera de ACK
  - retry controlado
  - cierre de resultado
- Timeout y retries son configurables por transacción.
- Los retries reutilizan exactamente `cmd_seq` y `nonce` del comando lógico original.
- La auditoría básica expone eventos en memoria como:
  - `command_sent`
  - `command_retry`
  - `command_ack`
  - `command_timeout`
- `INVALID_ACK` y `UNMATCHED_ACK` se observan durante la espera sin cerrar prematuramente la transacción.

## Control Plane F3 (Ticket 14.4)

- Existe un panel mínimo en `Técnico` para ejecutar transacciones F3 sin usar consola.
- La UI expone solo:
  - `PING`
  - `REQUEST_STAT_NOW`
  - `REBOOT_SOFT`
- El panel consume `ControlTransactionService` y muestra resultado legible (`final_status`, `cmd_seq`, `nonce`, `attempt_count`, detalles ACK).
- El operador usa solo `node_id`; la IP del nodo se resuelve automáticamente en background desde runtime UDP.
- `REBOOT_SOFT` requiere confirmación explícita antes de enviar.
- Durante ejecución, el panel deshabilita controles y mantiene la ventana responsive.

## Control Plane F3 (Ticket 14.5)

- Bloque app-side F3 mínimo consolidado para:
  - `PING`
  - `REQUEST_STAT_NOW`
  - `REBOOT_SOFT`
- Validación de cierre separada por niveles:
  - nivel 1: local/fake (obligatorio)
  - nivel 2: integración app-side por loopback UDP local
  - nivel 3: nodo ESP32 real (cuando haya hardware disponible)
- Se mantiene el alcance actual sin abrir `SET_*`.
- Documento canónico de cierre del bloque:
  - `docs/app/control_plane_f3_app_minimal.md`

## Control Plane F3 (Ticket 15)

- El runtime de control-plane quedó integrado al lifecycle de `SessionController` (start/stop de sesión UDP/LAB).
- El despacho de comandos desde capas superiores opera por `node_id`; la resolución `node_id -> ip` usa el runtime real de sesión.
- Los eventos de control-plane (`command_sent`, `command_retry`, `command_ack`, `command_timeout`) se escriben en el `session.jsonl` existente.
- Se expone `ControlPlaneRuntimeSnapshot` para consumo de UI/diagnóstico con contadores, último resultado y estado por nodo.
- Se expone snapshot canónico por nodo desde backend/session:
  - `SessionController.get_control_plane_node_snapshots()`
  - `SessionController.get_control_plane_node_snapshot(node_id)`
- El estado canónico por nodo distingue `resolved/stale/unresolved` e incluye último resultado F3 + resumen de verificación de reboot.
- El panel técnico `Técnico` consume la API integrada de `SessionController` (sin instancias privadas de runtime en widgets).

## Firmware catalog, artifacts y OTA local

- La app ya mantiene una biblioteca local de firmware en:
  - `artifacts/firmware_catalog.json`
  - `artifacts/firmware_store/`
- `Firmware Manager` permite:
  - importar `.bin` al managed store
  - inspeccionar metadata OTA
  - abrir `OTA Deploy`
  - borrar artifacts mal cargados desde la propia UI
- La ingesta deduplica por `sha256`; cambiar el nombre del archivo no crea un artifact nuevo si el contenido es el mismo.
- Los estados operativos del catálogo son:
  - `current`
  - `beta`
  - `obsolete`
  - `situational`
- Para pruebas de banco, comparación, probes y builds de red, la convención actual es usar `situational`.

## Agente de artifacts OTA

- Existe un agente reusable para generar artifacts OTA y probes de banco:
  - `src/control_okua/core/firmware/artifact_agent_service.py`
  - `tools/firmware_artifact_agent.py`
- El agente soporta:
  - clon del baseline actual
  - comparativos OTA-compatible
  - probe observable de banco
  - perfiles de red por artifact
- Los exports del agente se guardan bajo:
  - `artifacts/ota_artifact_agent/`
- El sidecar `artifact_build_overrides.h` exportado por el agente redacta credenciales sensibles (`password`, `secret`) para no dejar esos datos en claro en los outputs operativos.

## Probe observable de banco

- El firmware soporta un modo de prueba observable embebido por macro de build:
  - blink del LED onboard (`GPIO2`) cada segundo
  - emisión de notas ascendentes `0..80`
  - reinicio de la secuencia a `0` al llegar a `80`
- Este probe se usa para verificar en banco una OTA física real con evidencia visual y serial, sin cambiar `target_kind`, `target_variant` ni `build_profile`.

## OTA Deploy actual

- `OTA Deploy` publica un rollout local y dispara `OTA_CHECK_NOW` sobre nodos seleccionados explícitamente.
- El campo `Host visible al nodo` ya se autocompleta desde el `PC_IP` embebido en la metadata del artifact cuando ese dato está presente en `notes/source_notes`.
- Esto evita publicar por error un artifact de una red hacia el host de otra red.
- La telemetría OTA observable en app distingue, entre otros:
  - `fetching_manifest`
  - `validating_manifest`
  - `downloading`
  - `ready_reboot`
  - `boot_validating`
  - `boot_confirmed`

## Downgrade OTA explícito

- La política OTA actual no obliga a “inventar” bins nuevos solo para volver atrás.
- `OTA Deploy` ya permite autorizar un downgrade con advertencia explícita:
  - opción: `Permitir downgrade / reinstalar versión no más nueva`
- Cuando se activa:
  - el manifest se publica con `flags.allow_downgrade = true`
  - el firmware acepta instalar una versión más vieja o no más nueva solo si ese permiso viene explícito en el rollout
- Si no se activa esa opción, se mantiene la protección normal contra downgrade accidental.

## Perfiles de red embebidos

- El firmware soporta overrides de build para:
  - `SSID`
  - `password`
  - `OKUA_CONTROL_SECRET`
  - `WIFI_CHANNEL`
  - `PC_IP`
- Esto permite generar bins específicos por red sin depender del `okua_node_secrets.h` local del momento.
- La convención de banco actual usa perfiles por red para `ED1`:
  - `KITTY`
  - `MARIANA`
  - `MIKROTIK`
- Cada perfil puede tener:
  - un baseline `1.0.0-dev`
  - un probe observable `1.0.1-dev`

## Control Plane F3 (Tickets 16.1 a 16.4RRR)

- Existe snapshot canónico backend-side por nodo para control-plane F3:
  - `SessionController.get_control_plane_node_snapshots()`
  - `SessionController.get_control_plane_node_snapshot(node_id)`
- El snapshot por nodo incluye identidad/resolución, estado transaccional, ACK relevante, reboot verification y señales runtime (`uptime/reset_reason/boot_marker`).
- La resolución `node_id -> ip` usa contrato tipado estable `str | None` y cache rica interna (`ControlPlaneResolvedIp`) sin exponer objetos en la API de resolución.
- La correlación multi-nodo está aislada: ACK de un nodo no cierra transacción de otro y no contamina snapshots cruzados.
- La vista técnica `Control F3` consume snapshot backend-side por nodo y muestra evidencia compacta por secciones (estado del nodo, última transacción, último ACK, reinicio, bitácora).
- Se corrigió la coherencia atómica de render de última transacción/ACK:
  - no mezcla parcial entre snapshot y fallback local;
  - `ack_matched` no convive con timeout del mismo resultado;
  - `timeout` mantiene ACK ausente de forma explícita.
- Se implementó write-back canónico por nodo al cerrar transacciones (`PING`, `REQUEST_STAT_NOW`, `REBOOT_SOFT`) para evitar supervivencia de estado stale:
  - precedencia por `cmd_seq` más nuevo;
  - con `cmd_seq` igual, gana el paquete más completo;
  - estado transaccional de control-plane es session-scoped y se limpia en start/stop/reset/reload.
- El fallback local de UI quedó relegado a ventana transitoria corta y ya no es fuente principal de verdad cuando el snapshot backend-side está actualizado.
- Alcance funcional se mantiene sin abrir comandos `SET_*`.

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

Cada perfil define:

- nombre corto
- descripcion
- modo esperado (`serial` o `udp`)
- nivel de uso
- resumen operativo para UI

Regla practica entre perfiles UDP:

- `udp_jardin`: flujo productivo final sobre protocolo OKUA.
- `lab_sim`: ruta de pruebas/simulación sobre backend UDP.

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

- Usar `Aplicación > Cambiar perfil`.
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

Referencia técnica de protocolo:

- `docs/protocol/udp_bench_vs_okua_v1.md` (documento histórico comparativo)

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

1. Verificar que la primera superficie sea `Inicio`.
2. Confirmar estado inicial de sesion en `inactiva`.
3. Verificar en `Inicio` la acción principal, el mapa protagonista y el resumen breve de sesión.
4. Verificar en `Diagnostico` el bloque de preflight y los bloques de runtime serial/UDP.
5. Abrir `Estado actual` desde la Home y validar:
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
10. Pestaña `Nodos` en UDP con trafico: validar agrupación por cajas (`Caja 1..5`), nombres lógicos (`EB1`, `EC1`, ...) y expandir/colapsar.
11. En nodos de `Caja 1..3` validar ruteo a LoopMIDI 1 (`bus=0`); en `Caja 4..5` validar LoopMIDI 2 (`bus=1`).
12. Stop/restart de sesion UDP: validar limpieza visual y ausencia de nodos fantasmas.
13. Caso config invalida para readiness: validar estado `No lista` y findings bloqueantes en `Diagnostico`.
14. Pulsar `Reiniciar error` y confirmar retorno a estado inactivo con refresco visual coherente.
15. Validar bloqueo de `Cambiar perfil`/`Recargar configuracion` cuando la sesion no esta en estado seguro (`starting`, `running`, `stopping`).
16. Abrir `Ayuda > Acerca de` y confirmar información básica.
17. Abrir `Herramientas avanzadas` desde `Técnico` y validar `Ver config`, `Abrir carpeta`, `Recargar config` y `Salidas MIDI`.
18. Cerrar y reabrir la app sin errores.

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
