# Paquete de entrega — Release Candidate Funcional — Control OKÚA CKv2

Rama: `desarrollo-fase-2`  
Fecha de freeze: 2026-04-18 (Ticket 36.0 — ciclo RC cerrado, release interna consolidada)  
Estado: **Release Interna Controlada — ciclo RC cerrado**

---

## Qué es esta RC

Control OKÚA CKv2 es la aplicación de escritorio para Windows que opera la instalación OKÚA de jardín sonoro. Gestiona sesiones de comunicación con nodos Maestro por serial (USB) o UDP (red local), visualiza el estado agregado de los nodos por caja, enruta eventos MIDI y permite campañas de actualización OTA de firmware.

Esta RC congela la baseline funcional validada operativamente. No es un release final de producción masivo; es el paquete operativo validado apto para uso controlado por José David en la instalación.

---

## Qué quedó validado

### Validado por agente (programático con hardware real)

| Ítem | Evidencia | Ticket |
|------|-----------|--------|
| Sesión UDP real — perfil `udp_jardin` | 320 EVT + 16 STAT, 0 errores, detención limpia | 34.7 |
| Nodos EB1/Caja 1 (192.168.1.89) y EB2/Caja 2 (192.168.1.90) ONLINE | uptime ~30 h, rssi −13/−15 dBm, fw 1.0 | 34.7 |
| MIDI enrutado via loopMIDI Port 1 + loopMIDI Port 2 | 320 mensajes sin error | 34.7 |
| Flujo mapa ↔ Nodos — capa de datos | ViewModels con datos reales, filtrado y resolución inversa correctos | 34.7 |
| Estado del mapa por caja (ONLINE/DEGRADED/OFFLINE) | 5 cajas renderizadas con datos reales | 34.7 |
| Suite completa de tests | 491/491 PASAN — 0 fallos | 34.8 |
| Compilación limpia | `compileall` sin errores | 34.8 |
| QA funcional Firmware Manager / OTA UI | Catálogo, despliegue y campaña validados en UI y VM | 35.2 |
| Campaña OTA end-to-end con hardware real (EB1 canary) | `COMPLETED`, health gate `PASSED`, reboot confirmado por UDP y serial | 35.6 |

### Validado visualmente por José David

| Ítem | Evidencia | Ticket |
|------|-----------|--------|
| Arranque visual de app en Windows 11 | Commit a27d2b5: bugs visuales detectados y corregidos en sesión real | 34.5 |
| Secciones Diagnóstico, Técnico, Firmware, Remoto navegadas | Bugs detectados y corregidos en esas secciones | 34.5 |
| About dialog profesional abierto | Reemplazó QMessageBox genérico tras observación real | 34.5 |
| AdvancedToolsDialog limpiado | Sección duplicada detectada y eliminada | 34.5 |
| Toast notifications duración y microcopy | Ajustados tras observación visual | 34.5 |

---

## Qué NO quedó validado

| Ítem | Razón | Impacto |
|------|-------|---------|
| Sesión serial con Maestro USB | Sin Maestro USB conectado durante la validación | No bloqueante — Camino B (UDP) cubre el requisito RC |

---

## Cómo arrancarla

### Requisitos

```
Python 3.11+
pip install -r requirements.txt
loopMIDI (o equivalente) con al menos un puerto MIDI virtual abierto
config.json con perfil activo configurado o primer arranque resuelto con selector guiado / `CKV2_AUTOPROFILE=udp_jardin`
```

### Artefacto principal

**Ruta principal: `python main.py` desde el repositorio en `desarrollo-fase-2`.**  
El `.exe` empaquetado (`ControlOkuaV2.spec`) es alternativa secundaria para distribución futura. Esta RC fue validada desde fuente.

Si `config.json` no existe en el primer arranque, la app lo crea y puede pedir perfil. En un entorno limpio, la ruta no interactiva validada fue `CKV2_AUTOPROFILE=udp_jardin` antes de `python main.py`.

### Arranque

```bash
python main.py
```

### Perfiles disponibles

| Profile ID | Nombre visible | Modo | Cuándo usar |
|------------|---------------|------|-------------|
| `udp_jardin` | UDP Jardín | UDP | Instalación OKÚA con nodos en red local |
| `serial_local` | Serial local | Serial | Maestro OKÚA conectado por USB/serial |
| `lab_sim` | LAB / simulación | UDP | Pruebas reproducibles sin nodos físicos |

El perfil activo se configura en `config.json` bajo `"profile": {"active": "<id>"}`.
Si el archivo parte vacío o inexistente, el primer arranque guiado también es válido siempre que se explicite el perfil antes de seguir.

### Puertos UDP esperados (perfil `udp_jardin`)

| Puerto | Uso |
|--------|-----|
| 5005 | `evt_port` — eventos de nodo |
| 5006 | `stat_port` — estado de nodo |
| 5007 | `cmd_port` — comandos |

### Configuración mínima necesaria

- `config.json` con `"mode": "udp"` y perfil activo `udp_jardin`
- loopMIDI Port 1 y loopMIDI Port 2 disponibles (configurados en `config.json["midi"]["outputs"]`)
- Red local con nodos OKÚA activos en la subred (confirmado: 192.168.1.89 y 192.168.1.90 activos)

---

## Precauciones de uso controlado

1. **No es un release de producción masivo.** Es la RC validada para uso interno/controlado de José David.
2. **No usar los specs legacy** — `Control OKUA v2.spec` fue eliminado del repo en 34.8; `Control Okua Debug.spec` siempre estuvo gitignoreado. El spec válido para builds es `ControlOkuaV2.spec`.
3. **El perfil `lab_sim` es de laboratorio** — no esperar nodos reales con él.
4. **Cambios no comprometidos en el working tree** (`.vscode`, `firmware`, `ota_deploy_dialog`, `remote_auth_service`) son trabajo en curso de José David — no forman parte de esta RC.

---

## Deuda residual clasificada

### No bloqueante para esta RC

| Ítem | Descripción | Cuándo resolver |
|------|-------------|----------------|
| Sesión serial con Maestro USB | No ejecutada — sin Maestro USB en el entorno de validación | Cuando haya Maestro disponible |

### Pendiente para release final (no bloqueante para RC)

| Ítem | Descripción |
|------|-------------|
| `ControlOkuaV2.debug.spec` | Gitignoreado — herramienta local de builds de depuración; no comprometer ni distribuir |

### Deuda de firmware (independiente de RC GUI)

| Ítem | Descripción |
|------|-------------|
| Working tree firmware no comprometido | `okua_node_udp_v1.ino` tiene cambios locales con `OKUA_DEFAULT_ACTIVE_MODE`, `OKUA_DEFAULT_ACTIVE_SENSOR`, `OKUA_DEFAULT_ACTIVE_FRUIT_VARIANT`. El servicio `artifact_agent_service._extract_build_profile` y `_extract_default_target_kind` ya manejan defines indirectos (fix en 34.8). Comprometer cuando esté listo. |
| `okua_node_secrets.example.h` modificado | Cambio no comprometido en working tree — parte del mismo ciclo firmware |

---

## Decisión de cierre del ciclo RC

**El ciclo RC queda cerrado como Release Interna Controlada RC1 (Ticket 36.0, 2026-04-18).**

Todas las pendientes no bloqueantes quedaron resueltas:

- Mapa Home — confirmación visual interactiva: **CONFIRMADO por José David (2026-04-18)**
- QA Firmware/OTA: **VALIDADO** (35.2 / 35.3 / 35.6)
- Módulo Remoto y portal: **VALIDADO** (35.4 / 35.5)
- Suite de tests 494/494: **PASAN**

## Qué sigue después de esta release

1. **Sesión serial** con Maestro USB conectado, si se necesita para el flujo de operación.
2. **Comprometer cambios de firmware** en rama dedicada cuando el ciclo de firmware esté listo.
3. **Tag de release en `main`** cuando se decida promover a release oficial.
4. **Campaña OTA multi-wave** (más de 1 wave con gate intermedio) en el próximo ciclo operativo.

## Ensayo 36.1 — reproducibilidad operativa

Ensayo ejecutado sobre una copia limpia del repositorio en `C:\Users\JOSE DAVID\AppData\Local\Temp\okua_rehearsal_clean` con un venv nuevo.

### Qué funcionó

- `python main.py` arrancó desde una base limpia.
- La primera ejecución creó `config.json` automáticamente.
- El selector de perfil quedó resuelto con `CKV2_AUTOPROFILE=udp_jardin` para un arranque no interactivo.
- Home, Nodos, Diagnóstico y Técnico fueron navegados con la ventana abierta.
- La sesión UDP subió a `running` y volvió a `idle` con cierre limpio.

### Qué hubo que ajustar

- Instalar `pytest` aparte para la validación automática.
- Aceptar que `loopMIDI Port 3` no estaba presente en esta máquina; la app lo trató como aviso no bloqueante y siguió con los buses disponibles.
- Documentar explícitamente el primer arranque limpio para que no dependa de contexto oral.

### Decisión

La entrega interna es reproducible en una copia limpia, siempre que el primer arranque deje claro el perfil operativo. En esta máquina, la ruta validada fue `CKV2_AUTOPROFILE=udp_jardin` + `python main.py`.

Para operación inmediata: ver `release_candidate_runbook.md`.
