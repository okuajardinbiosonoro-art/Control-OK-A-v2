# Bitácora de operación temprana post-promoción — Control OKÚA CKv2

Rama: `desarrollo-fase-2`
Fecha de inicio: 2026-04-19 (Ticket 40.0)
Período cubierto: 2026-04-19 (post-promoción de `rc1-interna` a `main`)
Clasificación: **OPERACIÓN TEMPRANA LIMPIA — sin incidentes**

---

## Bloque 1 — Contexto de apertura

| Ítem | Valor |
|------|-------|
| Fecha de promoción a `main` | 2026-04-19 (Ticket 39.0) |
| Commit actual de `main` y tag `rc1-interna` | `6a16c33` |
| Commit actual de `desarrollo-fase-2` | `dd81cf3` (docs 39.1 — post-promotion rehearsal) |
| Suite al apertura del período | 498/498 PASAN (confirmado en 39.1) |
| Estado de deuda bloqueante | NINGUNA — clasificada en 38.0 |

---

## Bloque 2 — Sesiones documentadas en el período

### Sesión 1 — Ensayo post-promoción desde tag `rc1-interna` (Ticket 39.1)

| Campo | Valor |
|-------|-------|
| Fecha | 2026-04-19 |
| Tipo | Ensayo controlado desde worktree limpio |
| Fuente | Tag `rc1-interna` (commit `6a16c33`) |
| Directorio | `C:/Temp/okua_rc1_39_1` (sin `config.json` previo) |
| Método de arranque | `CKV2_AUTOPROFILE=udp_jardin PYTHONPATH=src python main.py` |
| Suite ejecutada | `PYTHONPATH=src python -m pytest --tb=short -q` |
| Resultado suite | **498/498 PASAN — 0 fallos** |
| Arranque | `config.json` creado automáticamente, perfil resuelto, `remote_api` silencioso |
| Estabilidad | Proceso vivo a 12 s y 30 s — sin crash |
| Terminación | Limpia — exit code 143 (SIGTERM normal) |
| Bugs de código encontrados | **NINGUNO** |
| Bugs de documentación | README.md — ruta del exe desactualizada (corregido en 39.1) |
| Nodos hardware | No conectados (ensayo de consumibilidad, no operativo) |

**Evaluación:** PASA completamente. Ver acta completa en [`post_promotion_rehearsal.md`](post_promotion_rehearsal.md).

---

## Bloque 3 — Clasificación de incidentes del período

| ID | Tipo | Descripción | Severidad | Estado |
|----|------|-------------|-----------|--------|
| DOC-40-1 | Documentación | README.md documentaba ruta de exe en formato one-file sin tilde; el artefacto real es one-dir con tilde. | MENOR | **CORREGIDO** en 39.1 |

**Incidentes de código:** NINGUNO
**Incidentes de runtime:** NINGUNO
**Incidentes de suite:** NINGUNO
**Regresiones:** NINGUNA

---

## Bloque 4 — Estado del sistema al cierre del período

| Aspecto | Estado |
|---------|--------|
| Suite de tests | 498/498 PASAN |
| Código | Sin cambios desde `6a16c33` (aceptación 38.0) |
| Documentación | Completa y sincronizada post-39.1 |
| Tag `rc1-interna` | Publicado en origin — apunta a `6a16c33` |
| `main` | Promovida, sin divergencia respecto a `desarrollo-fase-2` en código |
| Deuda residual abierta | Sin variación respecto a 38.0 (SERIAL-1, OTA-CAMP-1, SCOPE-1, SCOPE-2) |

---

## Bloque 5 — Decisión sobre familia 40.x

**No se abre una familia correctiva 40.x.**

Razones:
1. El único hallazgo del período fue un error de documentación menor (README.md), corregido in-situ en 39.1 sin impacto en código ni en operación.
2. El comportamiento de runtime en la sesión 1 fue íntegramente el esperado.
3. La suite se mantiene en 498/498 sin ningún fallo.
4. No se detectó ningún incidente de runtime, regresión, degradación de memoria o comportamiento inesperado.

**Decisión: operación temprana limpia. La Release Interna Controlada RC1 es estable en condiciones post-promoción.**

---

## Bloque 6 — Plan de continuación

| Acción | Cuándo | Criterio |
|--------|--------|---------|
| Continuar sesiones operativas con hardware (EB1 + EB2) | Próximas sesiones de campo | Estándar de uso controlado per runbook §2–3 |
| Revisión de deuda residual SERIAL-1 | Cuando haya Maestro USB disponible | Sesión serial con Maestro confirmada |
| Revisión de deuda OTA-CAMP-1 | Próximo ciclo de actualización multi-nodo | Campaña >1 wave en hardware real |
| Apertura de familia 40.x | Solo si se detecta incidente en operación continuada | Criterio de incidente moderado o crítico per `internal_operational_acceptance.md` §Bloque 3 |

El runbook operativo vigente es [`release_candidate_runbook.md`](release_candidate_runbook.md).
El acta de aceptación vigente es [`internal_operational_acceptance.md`](internal_operational_acceptance.md).

---

## Cierre del período de seguimiento temprano

**El período de seguimiento temprano post-promoción queda cerrado sin incidentes de código.**
**Control OKÚA CKv2 — RC1 entra en fase de operación controlada continuada.**
