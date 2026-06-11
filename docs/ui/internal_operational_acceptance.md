# Acta de aceptación operativa interna — Control OKÚA CKv2 — RC1

Rama: `desarrollo-fase-2`  
Fecha: 2026-04-19 (Ticket 38.0)  
Estado: **ACEPTADA para operación interna controlada**

---

## Bloque 1 — Aceptación operativa explícita

**Control OKÚA CKv2 Release Interna Controlada RC1 queda formalmente aceptada para operación interna controlada por José David en la instalación OKÚA Jardín Biosonoro.**

Esta aceptación se basa en:

| Evidencia | Resultado | Ticket |
|-----------|-----------|--------|
| Sesión UDP real con nodos EB1 + EB2 | 320 EVT + 16 STAT, 0 errores, detención limpia | 34.7 |
| Mapa Home — confirmación visual interactiva | CONFIRMADO por José David (2026-04-18) | Post-35.6 |
| OTA Deploy individual con hardware real | EB1 TRIGGERED → ACK_MATCHED → BOOT_CONFIRMED | 35.3 |
| Campaña OTA end-to-end con hardware real | EB1 canary COMPLETED, health gate PASSED | 35.6 |
| Portal remoto — bootstrap, login, roles, Tailscale | 29/29 escenarios PASS | 35.5 |
| Suite completa de tests | 498/498 PASAN | 37.0 |
| Piloto interno controlado — arranque, estabilidad, cierre | PASA con observaciones menores | 37.0 |
| Observación prolongada 602 s — sin hardware | PASA completamente — sin crash, sin leak | 37.1 |
| Observación prolongada real 690 s — EB1/EB2 vivos | PASA completamente — 3 REQUEST_STAT_NOW con ACK | 37.2 |

### Límites de uso aceptados

Esta aceptación es válida bajo las siguientes condiciones:

1. **Operador único:** José David en `<DEV_PC>` (Windows 11 Home, 10.0.26200).
2. **Ruta de operación:** `python main.py` desde la raíz del repositorio, rama `desarrollo-fase-2`.
3. **Perfil operativo:** `udp_jardin` con nodos EB1 (192.0.2.10) y EB2 (192.0.2.10) en la subred local.
4. **Dependencias externas:** loopMIDI con Port 1 y Port 2 activos antes de arrancar.
5. **Máximo de nodos validado:** 2 nodos simultáneos (EB1 + EB2). Más nodos son posibles técnicamente pero no han sido validados.

### Condiciones que invalidan esta aceptación

La aceptación deja de ser válida si:

- Se detecta un crash reproducible en condiciones normales de uso.
- Se detecta pérdida de datos o corrupción de config/catálogo.
- Se cambia de máquina, sistema operativo o entorno Python sin nueva validación.
- Se actualiza PySide6 o rtmidi sin rerun de suite + validación visual.
- Se fusiona código de otra rama sin ciclo de validación.

---

## Bloque 2 — Deuda residual no bloqueante

La siguiente deuda existe pero no bloquea el uso operativo controlado actual:

### Deuda de validación

| ID | Ítem | Prioridad | Cuándo resolver |
|----|------|-----------|----------------|
| SERIAL-1 | Sesión serial con Maestro USB no validada | Media | Cuando haya Maestro conectado disponible |
| OTA-CAMP-1 | Campaña OTA multi-wave (>1 wave con gate intermedio) no validada en hardware | Baja | Próximo ciclo operativo |
| SCOPE-1 | Validado solo con 2 nodos (EB1 + EB2) | Baja | Cuando haya más nodos disponibles |
| SCOPE-2 | Validado solo en `<DEV_PC>` — no probado en otro entorno Windows | Baja | Si se requiere otra máquina |

### Deuda de firmware

| ID | Ítem | Estado |
|----|------|--------|
| FW-1 | `okua_node_udp_v1.ino` con cambios locales no comprometidos (`OKUA_DEFAULT_ACTIVE_MODE`, `OKUA_DEFAULT_ACTIVE_SENSOR`, `OKUA_DEFAULT_ACTIVE_FRUIT_VARIANT`) | Working tree — comprometer cuando esté listo |
| FW-2 | `okua_node_secrets.example.h` modificado no comprometido | Working tree — comprometer junto a FW-1 |

### Deuda operativa menor

| ID | Ítem | Nota |
|----|------|------|
| OPS-1 | Mensajes de aviso de `remote_api` al arranque cuando `tailscale_only` está activo sin Tailscale | Esperado — desactivar `remote_api.enabled` o tener Tailscale activo para eliminarlos |
| OPS-2 | `dist/config.json` contiene config personal de José David (ports MIDI locales) | No es un bug — no distribuir sin reemplazar con `config.dist.json` |
| OPS-3 | Tag de release en `main` no creado | Decisión de José David; no bloqueante para uso operativo en `desarrollo-fase-2` |

---

## Bloque 3 — Plan de seguimiento y mantenimiento

### Controles recomendados por sesión de uso

Antes de cada sesión operativa, ejecutar el preflight del runbook (`release_candidate_runbook.md` §1):

| # | Verificación |
|---|-------------|
| P1 | `python --version` → 3.11.x o superior |
| P2 | `pip show PySide6 rtmidi` sin error |
| P3 | `config.json` presente y con perfil correcto |
| P4 | loopMIDI activo con Port 1 y Port 2 visibles |
| P5 | Red local accesible (`ping 192.0.2.10`) |
| P6 | Sin proceso previo colgado en Task Manager |

### Controles recomendados cada 10 sesiones o cada 2 semanas

| Control | Cómo verificar |
|---------|---------------|
| Suite de tests | `PYTHONPATH=src python -m pytest -q` → debe mostrar 498/498 PASAN |
| Compilación limpia | `python -m compileall src main.py -q` → sin errores |
| Estado del working tree | `git status` → sin cambios inesperados en `src/` |
| Logs de sesión si están activos | Revisar `logs/` por errores repetitivos o warnings nuevos |

### Síntomas que requieren investigación antes de continuar

- Crash en arranque no relacionado con loopMIDI o config.
- Traceback en consola durante una sesión normal.
- Chip de estado en Home muestra estado inconsistente con nodos activos.
- MIDI deja de enrutar mensajes sin cambio de config.
- El mapa Home no colorea cajas aunque los nodos reportan ONLINE en el árbol.

### Síntomas que ameritan abrir una nueva familia de tickets

- Regresión en funcionalidad ya validada que reaparece tras un `git pull`.
- Comportamiento no documentado en OTA con más de 1 wave.
- Errores reproducibles en sesión serial (cuando se valide con Maestro USB).
- Cambio de entorno o hardware que requiera nueva validación formal.

---

## Bloque 4 — Criterios de incidente y rollback

### Clasificación de incidentes

| Clase | Definición | Acción |
|-------|-----------|--------|
| **Menor** | Warning nuevo en consola, UX confusa sin pérdida de datos, comportamiento inesperado no reproducible | Registrar en un ticket de observación; no detener operación |
| **Moderado** | Bug reproducible en una función específica, no bloquea el flujo principal | Abrir ticket de bugfix acotado; aplicar hotfix directo en `desarrollo-fase-2` |
| **Crítico** | Crash reproducible en condiciones normales, pérdida de datos, corrupción de config o catálogo | Detener uso operativo; aplicar rollback; abrir ciclo de investigación |

### Procedimiento de hotfix (incidente moderado)

1. Identificar el commit que introdujo el bug (`git bisect` si es necesario).
2. Aplicar fix mínimo y acotado directamente en `desarrollo-fase-2`.
3. Rerun de tests: `PYTHONPATH=src python -m pytest -q` → 498/498 o superior.
4. Rerun de `compileall`: `python -m compileall src main.py -q`.
5. Commit y push a `origin/desarrollo-fase-2`.
6. Documentar en ticket correspondiente.

### Procedimiento de rollback (incidente crítico)

```bash
git fetch origin
git checkout desarrollo-fase-2
git reset --hard <COMMIT_ESTABLE>
PYTHONPATH=src python -m pytest -q
python main.py
```

**Referencias de rollback estables disponibles:**

| Commit | Estado | Descripción |
|--------|--------|-------------|
| `0aff3ba` | **ACTUAL — preferido** | Post-37.2: suite 498/498, observación real validada |
| `3075640` | Estable | Post-37.1: suite 498/498, observación prolongada |
| `c9e978b` | Estable | Post-37.0: suite 498/498, piloto confirmado |
| `1e1f474` | RC1 freeze original | Suite 494/494 — baseline original de RC1 |

> Para rollback en incidente crítico: usar `0aff3ba` (HEAD actual). Si el HEAD en sí es el origen del problema, usar `c9e978b`.

### Documentación de contingencia operativa

Para problemas durante sesión operativa (no de código), ver `release_candidate_runbook.md` §4.

---

## Bloque 5 — Estado documental consolidado

El ciclo de documentación de la RC1 queda completo con los siguientes documentos:

| Documento | Propósito | Estado |
|-----------|----------|--------|
| `release_candidate_handoff.md` | Qué es la RC, evidencia de validación, deuda residual | CERRADO — actualizado post-37.2 |
| `release_candidate_runbook.md` | Guía de operación de campo | VIGENTE |
| `internal_release_checklist.md` | Checklist de entrega interna | CERRADO — actualizado post-37.2 |
| `internal_release_notes_rc1.md` | Release notes internas | CERRADO — actualizado post-37.2 |
| `internal_release_packaged_rehearsal.md` | Ensayo de la ruta `.exe` empaquetada | CERRADO — validación visual confirmada |
| `internal_operational_pilot.md` | Piloto interno 37.0 | CERRADO |
| `internal_operational_observation.md` | Observación prolongada 37.1 (sin hardware) | CERRADO |
| `internal_operational_observation_real.md` | Observación real 37.2 (con EB1 + EB2) | CERRADO |
| **`internal_operational_acceptance.md`** | **Este documento — aceptación formal** | **ESTE TICKET** |

---

## Decisión final

**Control OKÚA CKv2 RC1 queda formalmente aceptada para operación interna controlada.**

El ciclo de validación está completo: RC funcional → ensayo desde fuente → ensayo empaquetado → piloto interno → observación prolongada → observación real con hardware → aceptación formal.

No quedan pendientes bloqueantes para el uso operativo controlado por José David.
