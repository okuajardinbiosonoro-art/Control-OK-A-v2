# Paquete de entrega — Release Candidate Funcional — Control OKÚA CKv2

Rama: `desarrollo-fase-2`  
Fecha de freeze: 2026-04-16 (Ticket 34.8 — paquete documental cerrado en 35.0-correctivo)  
Estado: **Release Candidate Funcional**

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
| Click en cajas del mapa en la app viva | El agente no puede observar la pantalla; capa de datos OK | Mínimo — confirmar interactivamente antes del release final |
| CTA "Ver nodos" y panel Nodos con barra de contexto en UI viva | Ídem | Mínimo |
| Sesión serial con Maestro USB | Sin Maestro USB conectado durante la validación | No bloqueante — Camino B (UDP) cubre el requisito RC |
| Campaña OTA end-to-end | Requiere firmware compatible en nodos | Pendiente para próximo ciclo |
| QA funcional de pantalla Firmware (catálogo, despliegue) | Alcance post-RC | Pendiente |

---

## Cómo arrancarla

### Requisitos

```
Python 3.11+
pip install -r requirements.txt
loopMIDI (o equivalente) con al menos un puerto MIDI virtual abierto
config.json con perfil activo configurado (ver config.example.json)
```

### Artefacto principal

**Ruta principal: `python main.py` desde el repositorio en `desarrollo-fase-2`.**  
El `.exe` empaquetado (`ControlOkuaV2.spec`) es alternativa secundaria para distribución futura. Esta RC fue validada desde fuente.

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
4. **La validación visual interactiva del mapa** (click en cajas, CTA "Ver nodos") quedó pendiente de confirmación por José David en sesión interactiva.
5. **Cambios no comprometidos en el working tree** (`.vscode`, `firmware`, `ota_deploy_dialog`, `remote_auth_service`) son trabajo en curso de José David — no forman parte de esta RC.

---

## Deuda residual clasificada

### No bloqueante para esta RC

| Ítem | Descripción | Cuándo resolver |
|------|-------------|----------------|
| 4 QActions huérfanos en menú | `view_diagnostics_action`, `toggle_preflight_action`, `firmware_manager_action`, `advanced_tools_action` — creados pero no añadidos a ningún menú visible | Próximo ciclo de UI |
| Validación visual interactiva del mapa | Click en cajas, CTA "Ver nodos", barra de contexto — no observado por agente | Antes del release final, por José David |
| Sesión serial con Maestro USB | No ejecutada — sin Maestro USB en el entorno de validación | Cuando haya Maestro disponible |

### Pendiente para release final (no bloqueante para RC)

| Ítem | Descripción |
|------|-------------|
| QA funcional de pantalla Firmware | Catálogo, importación, despliegue OTA end-to-end |
| Campaña OTA end-to-end | Requiere firmware compatible en nodos |
| `ControlOkuaV2.debug.spec` | Gitignoreado — herramienta local de builds de depuración; no comprometer ni distribuir |

### Deuda de firmware (independiente de RC GUI)

| Ítem | Descripción |
|------|-------------|
| Working tree firmware no comprometido | `okua_node_udp_v1.ino` tiene cambios locales con `OKUA_DEFAULT_ACTIVE_MODE`, `OKUA_DEFAULT_ACTIVE_SENSOR`, `OKUA_DEFAULT_ACTIVE_FRUIT_VARIANT`. El servicio `artifact_agent_service._extract_build_profile` y `_extract_default_target_kind` ya manejan defines indirectos (fix en 34.8). Comprometer cuando esté listo. |
| `okua_node_secrets.example.h` modificado | Cambio no comprometido en working tree — parte del mismo ciclo firmware |

---

## Qué sigue después de esta RC

1. **Confirmación visual interactiva** por José David: click en cajas del mapa, CTA "Ver nodos", navegación a Nodos con barra de contexto.
2. **Sesión serial** con Maestro USB conectado, si se necesita para el flujo de operación.
3. **QA de pantalla Firmware** — catálogo y despliegue OTA.
4. **Comprometer cambios de firmware** en una rama de firmware dedicada.
5. **Tag de release** en `main` cuando José David confirme los puntos anteriores.
