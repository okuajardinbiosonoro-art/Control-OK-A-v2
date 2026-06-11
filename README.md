# Control OKÚA CKv2

> Aplicación de escritorio para la operación de la instalación OKÚA Jardín Biosonoro

---

## Estado del proyecto

| Campo | Valor |
|-------|-------|
| Release | RC1 — Release Interna Controlada |
| Rama principal | `main` — promovida el 2026-04-19 |
| Tag de referencia | `rc1-interna` (commit `6a16c33`) |
| Rama de trabajo activa | `desarrollo-fase-2` |
| Suite de tests | 498/498 PASAN |
| Aceptación operativa | Emitida formalmente (2026-04-19, Ticket 38.0) |

CKv2 ha completado su ciclo de Release Candidate: RC funcional → ensayo empaquetado → piloto interno → observación prolongada → observación real con hardware → aceptación formal → promoción a `main`. Es operativa para uso controlado por José David en la instalación OKÚA.

---

## Descripción general

Control OKÚA CKv2 es la aplicación principal de operación del sistema OKÚA, una instalación de jardín biosonoro que convierte señales de sensores biológicos en eventos MIDI a través de una red de nodos ESP32 distribuidos físicamente.

CKv2 cubre tres responsabilidades principales:

1. **Gestión de sesión y observación de nodos** — inicia y detiene sesiones de comunicación UDP o serial con los nodos OKÚA, visualiza su estado en tiempo real y enruta eventos MIDI hacia instrumentos virtuales o físicos.
2. **Actualizaciones OTA de firmware** — permite importar, gestionar y desplegar firmware sobre los nodos físicos de forma controlada, con soporte para despliegues individuales y campañas wave-by-wave con health gate.
3. **Módulo remoto** — expone un servidor HTTP local con portal web para administración remota de la sesión, con roles diferenciados y soporte opcional para acceso vía Tailscale.

CKv2 reemplaza la generación anterior (CKv1) con una arquitectura desacoplada, una UI basada en PySide6 (Qt6) y un ciclo de validación formal completo.

---

## Alcance funcional actual

### Qué hace hoy

| Función | Estado |
|---------|--------|
| Sesión UDP con nodos OKÚA en red local | Validado — 320 EVT + 16 STAT, 0 errores (Ticket 34.7) |
| Enrutamiento MIDI via loopMIDI | Validado — 320 mensajes sin error |
| Mapa Home con estado de cajas por sesión UDP | Validado — 5 cajas con estados coherentes |
| Árbol de nodos con filtrado y resolución por caja | Validado con nodos reales EB1 + EB2 |
| OTA Deploy individual (un nodo) | Validado — EB1: TRIGGERED → BOOT_CONFIRMED (Ticket 35.3) |
| Campaña OTA canary con health gate | Validado — EB1 canary COMPLETED, health gate PASSED (Ticket 35.6) |
| Portal remoto `/remote/` con roles | Validado — 29/29 escenarios (Ticket 35.5) |
| Control Plane F3 (PING / REQUEST_STAT_NOW / REBOOT_SOFT) | Validado via sesión UDP real |
| Preflight de readiness antes de iniciar sesión | Validado — detecta condiciones bloqueantes sin iniciar backend |
| Empaquetado como exe (one-dir, PyInstaller) | Validado visualmente — ícono, mapa, navegación, cierre |

### Módulos principales

| Módulo | Superficie en app | Descripción |
|--------|------------------|-------------|
| Home / Mapa | `Inicio` | Estado agregado de la instalación, sesión y acción principal |
| Nodos | `Nodos` | Árbol de nodos por caja, estado individual, métricas runtime |
| Diagnóstico | `Diagnóstico` | Readiness, runtime serial/UDP, preflight findings |
| Técnico / Control F3 | `Técnico` | Herramientas avanzadas, comandos de control-plane F3 |
| Firmware / OTA | `Firmware` | Catálogo, importación, despliegue individual y campañas |
| Remoto | `Remoto` | Estado y control del servidor remoto; portal `/remote/` |

---

## Arquitectura funcional

### Capas principales

```
UI (PySide6 / Qt6)
  └── ViewModels  →  SessionController
                          ├── Backends (UDP / Serial)
                          │       ├── UdpTransportAdapter
                          │       └── SerialTransportAdapter
                          ├── NodeRegistry   (estado por nodo)
                          ├── MidiRouter     (enrutamiento por bus)
                          ├── ControlPlaneRuntime  (F3 PING/STAT/REBOOT)
                          └── RecordingWriter  (session.jsonl / report.json)

Servicios complementarios
  ├── FirmwareCatalogService   (artifacts/firmware_catalog.json)
  ├── OtaDeployService
  ├── OtaCampaignService
  └── RemoteApiService         (HTTP + /remote/ portal)
```

### Flujo de sesión

1. `SessionController` ejecuta preflight de readiness antes de abrir el backend.
2. Si readiness está `blocked`, la sesión pasa a estado de error controlado con motivo legible — sin intentar el backend.
3. Si readiness es `ready` o `ready_with_warnings`, se inicia el backend (UDP o Serial).
4. El backend alimenta `NodeRegistry` por paquete parseado (EVT → estado, STAT → métricas).
5. `MidiRouter` enruta eventos musicales a los buses loopMIDI según la política por caja (determinista, no dependiente de IP).
6. Al detener, el registro de nodos se limpia para evitar nodos fantasmas en la siguiente sesión.

### Identidad de nodos y ruteo MIDI

La política es determinista y derivada exclusivamente de `node_id`:

| `node_id` | Caja | Bus MIDI | Puerto loopMIDI |
|-----------|------|----------|-----------------|
| 1–5 | Caja 1 | 0 | loopMIDI Port 1 |
| 6–10 | Caja 2 | 0 | loopMIDI Port 1 |
| 11–15 | Caja 3 | 0 | loopMIDI Port 1 |
| 16–20 | Caja 4 | 1 | loopMIDI Port 2 |
| 21–25 | Caja 5 | 1 | loopMIDI Port 2 |

Nombres lógicos de nodo: función pura de `node_id` (patrón `EB/EC/ED/EE/EF` por caja).

### Protocolo UDP (perfil `udp_jardin`)

| Puerto | Función |
|--------|---------|
| 5005 | `evt_port` — eventos musicales de nodo |
| 5006 | `stat_port` — estado de nodo |
| 5007 | `cmd_port` — comandos F3 salientes |
| 5008 | `ack_port` — ACKs de comandos F3 entrantes |

El parser OKUA valida cabecera `OKUA_HDR`, descarta datagramas malformados y clasifica por tipo (EVT / STAT). No depende de IP de origen para identificar al nodo.

---

## Capacidades validadas

### Sesión UDP y observación de nodos

- Sesión real validada con nodos EB1 (192.168.1.89, Caja 1) y EB2 (192.168.1.90, Caja 2).
- Estado ONLINE/DEGRADED/OFFLINE derivado de timestamps de recepción y umbrales configurables (`thresholds.online_ms`, `degraded_ms`, `offline_ms`).
- Observación prolongada real de 690 s con 15 muestras de proceso: sin crash, sin leak de memoria (RSS 78–105 MB), CPU ≤ 5.5 %.
- Tres pulsos `REQUEST_STAT_NOW` confirmados por ACK de nodo en condiciones reales.

### OTA Firmware

- **Despliegue individual:** selección de artifact, publicación de rollout local, disparo de `OTA_CHECK_NOW` sobre el nodo. Telemetría observable: `fetching_manifest → validating_manifest → downloading → ready_reboot → boot_validating → boot_confirmed`.
- **Campaña canary con health gate:** EB1 completó ciclo completo — wave configurada, health gate PASSED, reboot confirmado por UDP y serial.
- **Downgrade explícito:** autorizable por opción en OTA Deploy (`Permitir downgrade / reinstalar versión no más nueva`); el manifest se publica con `flags.allow_downgrade = true`.
- **Deduplicación por SHA256:** importar el mismo binario con nombre diferente no crea un artifact duplicado.

### Módulo remoto

- Servidor HTTP local con portal web en `/remote/`.
- Roles soportados: `admin`, `tecnico`, `observador` — restricciones de acceso verificadas (403 en operaciones no autorizadas).
- Modos de bind: `local_only` (loopback únicamente) y `tailscale_only` (bind exclusivo en IP Tailscale, loopback rechazado).
- Bootstrap desde store vacía validado con 3 cuentas: login, logout y cambio de rol.

### Control Plane F3

- Comandos disponibles desde UI `Técnico → Control F3`: `PING`, `REQUEST_STAT_NOW`, `REBOOT_SOFT`.
- El operador trabaja por `node_id`; la resolución `node_id → IP` usa el runtime UDP activo.
- `REBOOT_SOFT` requiere confirmación explícita antes de enviar.
- Auditoría en memoria: `command_sent`, `command_retry`, `command_ack`, `command_timeout`.
- Los eventos de control-plane se escriben en `session.jsonl`.

---

## Ruta de operación

### Ruta principal (recomendada)

```bash
python main.py
```

Ejecutar desde la raíz del repositorio en `desarrollo-fase-2`. Esta es la ruta validada íntegramente para uso controlado. Requiere entorno Python instalado (ver §Instalación).

### Ruta alternativa (ejecutable empaquetado)

```
dist/Control OKÚA CKv2/Control OKÚA CKv2.exe
```

Generado con PyInstaller 6.19.0 en formato one-dir. Validado visualmente por José David (2026-04-19): ícono OKÚA correcto en barra de título y taskbar, Home con mapa, navegación a Nodos/Diagnóstico/Técnico, cierre limpio. Es la alternativa para distribución sin entorno Python. Antes de distribuir, reemplazar `config.json` junto al exe con `config.dist.json` como base.

---

## Requisitos

| Requisito | Versión / Condición |
|-----------|---------------------|
| Sistema operativo | Windows 11 (validado en Windows 11 Home 10.0.26200) |
| Python | 3.11 o superior |
| Dependencias Python | Ver `requirements.txt` — principales: PySide6, rtmidi |
| loopMIDI | Con `loopMIDI Port 1` y `loopMIDI Port 2` activos antes de arrancar |
| Red local | Subred con nodos OKÚA activos (perfil `udp_jardin`: 192.168.1.x) |
| Firewall | Puertos UDP 5005, 5006 y 5007 abiertos para tráfico local |
| `config.json` | Presente en raíz del repo (se crea automáticamente en primer arranque) |

> **Nota:** El bus `loopMIDI Port 3` es opcional. Si no existe, la app lo reporta como aviso no bloqueante y continúa con los buses disponibles.

---

## Instalación

### 1. Crear entorno virtual

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**Linux/macOS** (entorno de desarrollo — no validado para operación):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Verificar instalación

```powershell
pip show PySide6 rtmidi
python -m compileall src main.py -q
```

Sin errores: la instalación es correcta.

### 3. Configuración inicial

Si es la primera vez:

- Copiar `config.example.json` a `config.json` en la raíz del repo y ajustar el perfil activo, **o**
- Dejar que el primer arranque cree `config.json` automáticamente y seleccionar perfil en el selector guiado.

Para arranque no interactivo en un entorno limpio:

```powershell
$env:CKV2_AUTOPROFILE = "udp_jardin"
python main.py
Remove-Item Env:CKV2_AUTOPROFILE
```

---

## Ejecución

### Arranque normal

```powershell
python main.py
```

### Qué esperar al abrir

| Elemento | Estado esperado |
|----------|----------------|
| Título de ventana | `Control OKÚA · CKv2` |
| Barra lateral | Inicio / Nodos / Diagnóstico / Técnico / Firmware / Remoto |
| Chip de estado en Home | `Sesión inactiva` |
| Mapa Home | 5 cajas visibles, sin color activo (sin sesión activa) |
| Consola | Sin traceback, sin `ERROR` en las primeras líneas |

### Primer arranque en entorno limpio

Si `config.json` no existe, la app lo crea con defaults v2 y abre el selector guiado de perfil. Seleccionar `UDP Jardín` para el perfil operativo principal. El selector no se vuelve a mostrar si el perfil ya quedó guardado.

### Notas de configuración útiles

- `config.json` en la raíz del repo es la fuente de configuración activa.
- Si está corrupto, la app lo renombra como `config.corrupt.<timestamp>.json` y regenera uno limpio.
- Si detecta una config CKv1 antigua, la migra automáticamente a v2 y guarda respaldo.
- El perfil activo se puede cambiar desde `Aplicación → Cambiar perfil`.
- Cambiar perfil o recargar configuración queda bloqueado mientras haya una sesión activa.

### Generación del ejecutable (opcional)

```powershell
pyinstaller ControlOkuaV2.spec
```

El artefacto queda en `dist/Control OKÚA CKv2/Control OKÚA CKv2.exe`.

---

## Perfiles de uso

| Profile ID | Nombre visible | Modo | Cuándo usar |
|------------|---------------|------|-------------|
| `udp_jardin` | UDP Jardín | UDP | Instalación OKÚA con nodos en red local — perfil operativo principal |
| `serial_local` | Serial local | Serial | Maestro OKÚA conectado por USB/serial — pendiente de validación con hardware |
| `lab_sim` | LAB / simulación | UDP | Pruebas reproducibles sin nodos físicos — no usar en operación real |

El perfil activo se guarda en `config.json` bajo `"profile": {"active": "<id>"}`. Al seleccionar un perfil, la app sincroniza automáticamente el modo técnico (`mode`) derivado.

---

## Operación básica

### Preflight antes de cada sesión

| # | Verificación | Cómo confirmar |
|---|-------------|----------------|
| P1 | Python disponible | `python --version` → 3.11.x o superior |
| P2 | Dependencias instaladas | `pip show PySide6 rtmidi` sin error |
| P3 | `config.json` presente con perfil correcto | Raíz del repo; `"profile": {"active": "udp_jardin"}` |
| P4 | loopMIDI activo con Port 1 y Port 2 visibles | Ícono en bandeja del sistema; dos puertos abiertos |
| P5 | Red local accesible | `ping 192.168.1.89` responde |
| P6 | Sin proceso previo colgado | Administrador de tareas sin `python main.py` activo |

### Iniciar sesión UDP

1. Verificar que el chip de estado en Home diga `Sesión inactiva`.
2. Confirmar que el perfil visible es `UDP Jardín`. Si no: `Aplicación → Cambiar perfil → UDP Jardín → Aceptar`.
3. Clic en **"Iniciar sesión"**.
4. Esperar sincronización (2–5 s con nodos activos).
5. Confirmación: chip de estado cambia, cajas con nodos ONLINE se colorean, árbol `Nodos` muestra EB1/EB2.

### Flujo mapa ↔ Nodos

1. En Home, clic sobre una caja con nodos activos.
2. Aparece CTA **"Ver nodos"**.
3. Clic → `Nodos` abre con barra de contexto de caja (`Caja: X — N nodos`).
4. Clic **"Ver caja en inicio"** → retorno a Home con caja seleccionada.

### Detener sesión y salida segura

1. Clic **"Detener sesión"** en Home (o desde `Diagnóstico`).
2. Chip regresa a `Sesión inactiva`.
3. Verificar consola — sin `ERROR` ni traceback al detener.
4. Cerrar la ventana o `Aplicación → Salir`.
5. Confirmar que el proceso Python terminó (Administrador de tareas).

### Diagnóstico y herramientas

- **Diagnóstico:** 7 campos de resumen runtime, sección "Chequeos previos" plegable con findings de readiness, estado de backend UDP/serial.
- **Técnico → Control F3:** panel para `PING`, `REQUEST_STAT_NOW`, `REBOOT_SOFT` sobre nodos identificados por `node_id`.
- **Herramientas avanzadas** (desde `Técnico`): ver config, recargar config, abrir carpeta del repo, listar salidas MIDI.

---

## Firmware y OTA

El módulo Firmware de CKv2 gestiona el ciclo de vida del firmware de los nodos OKÚA: biblioteca local de artifacts, despliegues individuales y campañas controladas.

### Firmware Manager

- Biblioteca local en `artifacts/firmware_catalog.json` + `artifacts/firmware_store/`.
- Permite importar `.bin` al managed store, inspeccionar metadata OTA, abrir OTA Deploy y eliminar artifacts mal cargados.
- La ingesta deduplica por SHA256; renombrar el archivo no crea un artifact nuevo si el contenido es idéntico.
- Estados operativos del catálogo: `current`, `beta`, `obsolete`, `situational`.

### OTA Deploy (despliegue individual)

- Selección de artifact, configuración de red (host visible al nodo, puerto HTTP), selección de nodo.
- El campo "Host visible al nodo" se autocompleta desde la metadata del artifact cuando está disponible.
- Dispara `OTA_CHECK_NOW` al nodo seleccionado.
- Telemetría observable en app: `fetching_manifest → validating_manifest → downloading → ready_reboot → boot_validating → boot_confirmed`.
- Soporte para downgrade explícito con advertencia clara.

### OTA Campaign (campaña con health gate)

- Preview de waves con soporte canary.
- Health gate configurable entre waves.
- Ciclo completo validado con hardware real: EB1 canary COMPLETED, health gate PASSED, reboot confirmado por UDP y serial (Ticket 35.6).

### Probe observable de banco

Para verificar OTA en banco con evidencia visual y serial sin modificar el artifact de producción, el firmware soporta un modo probe embebido por macro de build:
- Blink del LED onboard (GPIO2) cada segundo.
- Emisión de notas ascendentes 0–80.

---

## Módulo Remoto

CKv2 incluye un servidor HTTP local para administración remota de la instalación sin depender del acceso físico al equipo.

### Portal `/remote/`

- Interfaz web accesible en `http://<host>:<port>/remote/`.
- Bootstrap inicial desde store vacía: crear cuentas, asignar roles.
- Roles: `admin` (control total), `tecnico` (operación), `observador` (solo lectura).
- Restricciones de acceso por rol verificadas — 403 en operaciones no autorizadas.

### Modos de operación

| Modo | Comportamiento |
|------|---------------|
| `local_only` | Bind en loopback únicamente — acceso solo desde la misma máquina |
| `tailscale_only` | Bind exclusivo en IP de red Tailscale — loopback rechazado; acceso remoto seguro |

### Configuración

El módulo remoto se activa/desactiva en `config.json` bajo `remote_api.enabled`. En un `config.json` creado desde cero (primer arranque limpio), `remote_api.enabled` es `false` por defecto — sin warnings de Tailscale al arranque.

---

## Documentación complementaria

| Documento | Contenido |
|-----------|-----------|
| [`docs/status/CKV2_LIVE_STATE_2026-06-11.md`](docs/status/CKV2_LIVE_STATE_2026-06-11.md) | Estado vivo CKv2 y reconciliacion documental del baseline de campo |
| [`docs/release/FIELD_BUILD_MANIFEST.md`](docs/release/FIELD_BUILD_MANIFEST.md) | Manifiesto del build de campo y hash baseline |
| [`docs/dev/BUILD_EXE.md`](docs/dev/BUILD_EXE.md) | Proceso y cautelas para build del ejecutable |
| [`docs/ops/FIELD_RUNBOOK.md`](docs/ops/FIELD_RUNBOOK.md) | Runbook de campo para operacion pasiva y contingencias |
| [`docs/security/TOOLING_SECURITY_POLICY.md`](docs/security/TOOLING_SECURITY_POLICY.md) | Politica de seguridad para herramientas y agentes |
| [`docs/ai/AGENT_WORKFLOW.md`](docs/ai/AGENT_WORKFLOW.md) | Flujo de trabajo de agentes sobre CKv2 |
| [`docs/adr/ADR-0001-CKV2-PRODUCTION-LIGHTWEIGHT-BASELINE.md`](docs/adr/ADR-0001-CKV2-PRODUCTION-LIGHTWEIGHT-BASELINE.md) | ADR-0001: baseline de produccion liviana |
| [`docs/ui/release_candidate_runbook.md`](docs/ui/release_candidate_runbook.md) | Guía de operación de campo: preflight, arranque, operación, contingencia, rollback |
| [`docs/ui/internal_operational_acceptance.md`](docs/ui/internal_operational_acceptance.md) | Acta de aceptación operativa formal, deuda residual, mantenimiento, incidentes |
| [`docs/ui/internal_release_checklist.md`](docs/ui/internal_release_checklist.md) | Checklist de entrega interna RC1 |
| [`docs/ui/internal_release_notes_rc1.md`](docs/ui/internal_release_notes_rc1.md) | Release notes internas RC1 — bloques cerrados y validaciones clave |
| [`docs/ui/release_candidate_handoff.md`](docs/ui/release_candidate_handoff.md) | Paquete completo de evidencia de validación RC |
| [`docs/ui/post_release_early_operation_log.md`](docs/ui/post_release_early_operation_log.md) | Bitácora de operación temprana post-promoción |
| [`config.example.json`](config.example.json) | Plantilla de configuración con todos los campos documentados |

---

## Estado de validación

CKv2 RC1 fue validada en el siguiente ciclo completo:

| Fase | Resultado |
|------|-----------|
| Sesión UDP real con nodos EB1 + EB2 | PASA — 320 EVT, 16 STAT, 0 errores |
| OTA Deploy individual con hardware real | PASA — EB1: TRIGGERED → BOOT_CONFIRMED |
| Campaña OTA canary con health gate | PASA — EB1 canary COMPLETED, health gate PASSED |
| Portal remoto — bootstrap, login, roles, Tailscale | PASA — 29/29 escenarios |
| Suite completa de tests | PASA — 498/498 |
| Piloto interno controlado | PASA con observaciones menores — ninguna bloqueante |
| Observación prolongada 602 s (sin hardware) | PASA — sin crash, sin leak, CPU ≤ 7.8 % |
| Observación real 690 s (EB1 + EB2 activos) | PASA — 3 `REQUEST_STAT_NOW` con ACK, RSS 78–105 MB, CPU ≤ 5.5 % |
| Ensayo desde copia limpia (tag `rc1-interna`) | PASA — config auto-creada, perfil resuelto, proceso estable 30 s |

Validación visual confirmada por José David: arranque, navegación completa, mapa, About dialog, toasts, ejecutable empaquetado.

---

## Limitaciones y alcance actual

| ID | Limitación | Impacto |
|----|-----------|---------|
| SERIAL-1 | Sesión serial con Maestro USB no validada | Sin Maestro USB durante el ciclo; el perfil UDP cubre el flujo operativo principal |
| OTA-CAMP-1 | Campaña OTA multi-wave (>1 wave con gate intermedio) no ejecutada en hardware | Lógica multi-wave cubierta por tests; wave única validada con hardware real |
| SCOPE-1 | Validado solo con EB1 + EB2 — sin prueba con más de 2 nodos simultáneos | Técnicamente soportado; no validado con más nodos |
| SCOPE-2 | Validado únicamente en Windows 11 Home (máquina de José David) | No probado en otro entorno Windows |

CKv2 RC1 **no es** un release de producción masivo. Es un sistema para uso controlado por José David en la instalación OKÚA Jardín Biosonoro.

---

## Estructura del repositorio

```
Control-OK-A-v2/
├── main.py                        # Punto de entrada de la aplicación
├── requirements.txt               # Dependencias Python
├── config.example.json            # Plantilla de configuración
├── config.dist.json               # Config base para distribución del exe
├── ControlOkuaV2.spec             # Spec de PyInstaller (one-dir)
│
├── src/control_okua/
│   ├── app_qt/                    # Capa UI — widgets, viewmodels, contratos
│   │   ├── widgets/               # Superficies: Home, Nodos, Diagnóstico, Técnico, Firmware, Remoto
│   │   └── viewmodels/            # ViewModels desacoplados de la UI
│   ├── core/
│   │   ├── session/               # SessionController, preflight, lifecycle
│   │   ├── udp/                   # Parser OKUA, backend UDP, transport
│   │   ├── control_plane/         # F3: comandos, ACK, transacciones, runtime
│   │   ├── firmware/              # Catálogo, OTA deploy, OTA campaign, artifact agent
│   │   ├── recording/             # Recording de sesión (JSONL), report, replay
│   │   ├── registry/              # NodeRegistry — estado por nodo
│   │   ├── midi/                  # MidiRouter, buses, enrutamiento por caja
│   │   ├── profiles/              # Perfiles operativos (udp_jardin, serial_local, lab_sim)
│   │   ├── config/                # Config v2, migración, defaults
│   │   └── preflight/             # Readiness checks
│   ├── services/
│   │   ├── backends/              # SessionBackendFactory, UdpSessionBackend, SerialSessionBackend
│   │   └── remote_console_assets/ # Assets del portal /remote/
│   └── transports/
│       ├── udp/                   # UdpTransportAdapter
│       └── serial/                # SerialTransportAdapter, MidiByteStreamParser
│
├── tests/                         # Suite de tests (498 tests)
├── tools/                         # Herramientas de desarrollo (emisor UDP, listado MIDI, etc.)
├── artifacts/                     # Catálogo y store de firmware OTA
├── assets/                        # Recursos visuales (branding, íconos)
├── firmware/                      # Firmware ESP32 de los nodos OKÚA
├── docs/ui/                       # Documentación de validación y operación
└── logs/                          # Logs de sesión (session.jsonl, report.json por sesión)
```

---

## Mantenimiento y operación

### Controles por sesión

Ejecutar el preflight (§Operación básica) antes de cada sesión. En particular verificar loopMIDI activo y red local accesible.

### Controles periódicos (cada 10 sesiones o 2 semanas)

```powershell
# Suite de tests
PYTHONPATH=src python -m pytest -q
# → debe mostrar 498 passed

# Compilación limpia
python -m compileall src main.py -q
# → sin errores

# Estado del working tree
git status
# → sin cambios inesperados en src/
```

### Contingencia rápida

| Síntoma | Acción |
|---------|--------|
| Crash en arranque (`ModuleNotFoundError`) | `pip install -r requirements.txt` y reintentar |
| Sin nodos visibles en árbol | `ping 192.168.1.89` — verificar red y firewall UDP 5005/5006 |
| App no responde al detener sesión | Esperar 10 s; si sigue, `Alt+F4` y finalizar proceso en Task Manager |
| Traceback en consola durante sesión normal | Ver `release_candidate_runbook.md` §4 |

### Rollback a estado estable

```bash
git fetch origin
git checkout desarrollo-fase-2
git reset --hard 0aff3ba   # Commit estable post-validación real 37.2
PYTHONPATH=src python -m pytest -q
python main.py
```

Ver tabla completa de commits de rollback en [`docs/ui/internal_operational_acceptance.md`](docs/ui/internal_operational_acceptance.md) §Bloque 4.

### Procedure de hotfix

1. Identificar el commit que introdujo el problema.
2. Aplicar fix mínimo directamente en `desarrollo-fase-2`.
3. Rerun de tests: `PYTHONPATH=src python -m pytest -q` → 498/498 o superior.
4. Commit y push a `origin/desarrollo-fase-2`.
5. Documentar en el ticket correspondiente.

---

## Herramientas de desarrollo

| Herramienta | Propósito |
|-------------|-----------|
| `tools/udp_okua_v1_sender.py` | Emisor de tráfico OKUA v1 para pruebas locales (con `--dry-run` para vectores de referencia) |
| `tools/list_midi_ports.py` | Listado de puertos MIDI disponibles en el sistema |
| `tools/midi_smoke_test.py` | Verificación rápida del enrutamiento MIDI |
| `tools/firmware_artifact_agent.py` | Generación de artifacts OTA y probes de banco |

Verificación de compilación completa:

```powershell
python -m compileall src main.py tools
```

---

## Créditos

Control OKÚA CKv2 es parte del sistema OKÚA Jardín Biosonoro — instalación de arte sonoro que convierte señales biológicas en música mediante nodos ESP32 distribuidos en un jardín.

Diseñado y desarrollado por José David para operación interna controlada.  
Release Interna Controlada RC1 — 2026-04-19.
