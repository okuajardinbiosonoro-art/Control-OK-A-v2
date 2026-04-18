# Release Notes Internas — Control OKÚA CKv2 — RC1 / Release Interna Controlada

Rama: `desarrollo-fase-2`  
Fecha: 2026-04-18 (Ticket 36.0)  
Estado: **Release Interna Controlada — ciclo RC cerrado**

---

## Resumen

Control OKÚA CKv2 alcanza su primera release interna controlada tras el ciclo RC funcional completo. La aplicación es operativa para uso controlado por José David en la instalación OKÚA Jardín Biosonoro.

El artefacto principal es la ejecución desde fuente con `python main.py` en la rama `desarrollo-fase-2`. El `.exe` empaquetado existe pero no es la ruta operativa validada de esta release.

---

## Bloques cerrados en este ciclo

| Ticket | Bloque | Resultado |
|--------|--------|-----------|
| 33.x | Mapa Home — arquitectura y capa de datos | CERRADO |
| 34.0 | Design system y tokens visuales | CERRADO |
| 34.1 | Microcopy y branding visible | CERRADO |
| 34.2 | Higiene técnica de repo | CERRADO |
| 34.3 | Packaging baseline — PyInstaller | CERRADO — `dist/Control OKÚA CKv2.exe` generado |
| 34.5 | Validación visual real por José David | CERRADO — arranque, navegación, About, toasts |
| 34.7 | Sesión UDP real con nodos EB1 + EB2 | CERRADO — 320 EVT, 16 STAT, 0 errores |
| 34.8 | Suite de tests + correcciones finales | CERRADO — 494/494 pasan |
| 35.0 | Runbook operativo + paquete documental | CERRADO |
| 35.1 | Limpieza QActions huérfanos en menú | CERRADO — 4 acciones eliminadas |
| 35.2 | QA funcional Firmware Manager / OTA UI | CERRADO |
| 35.3 | OTA Deploy end-to-end con hardware real | CERRADO — EB1 TRIGGERED → BOOT_CONFIRMED |
| 35.4 | QA módulo Remoto — código y suite | CERRADO — 33/33 tests; BUG-1 corregido |
| 35.5 | Portal `/remote/` validado con navegador y Tailscale | CERRADO — 29/29 escenarios PASS |
| 35.6 | Campaña OTA end-to-end con hardware real | CERRADO — EB1 canary COMPLETED, health gate PASSED |
| 36.0 | Freeze, release notes y cierre del ciclo RC | ESTE TICKET |

---

## Validaciones más importantes ejecutadas

| Validación | Resultado | Ticket |
|-----------|-----------|--------|
| Sesión UDP real — perfil `udp_jardin` | 320 EVT + 16 STAT, 0 errores, detención limpia | 34.7 |
| Mapa Home — confirmación visual interactiva | CONFIRMADO por José David (2026-04-18) | Post-35.6 |
| OTA Deploy individual con hardware real | EB1 TRIGGERED → ACK_MATCHED → BOOT_CONFIRMED | 35.3 |
| Campaña OTA wave-by-wave con hardware real | EB1 canary, COMPLETED, health gate PASSED, reboot confirmado UDP+serial | 35.6 |
| Portal `/remote/` — bootstrap, login, roles, Tailscale | 29/29 escenarios PASS | 35.5 |
| Suite completa de tests | 494/494 PASAN | 34.8 → 35.x |

---

## Bugs críticos resueltos en el ciclo

| Bug | Descripción | Ticket |
|-----|-------------|--------|
| OTA Deploy rollout group overflow / white pit | `QVBoxLayout` reemplazado por `QSplitter` con geometría calculada desde primeros principios | 34.6 / 35.2 |
| Toast level hardcodeado en fallo de servicio remoto | `level="success"` fijo → verifica `service_state != "running"` antes de elegir nivel | 35.4 |
| 4 QActions huérfanos en menú principal | `view_diagnostics_action`, `toggle_preflight_action`, `firmware_manager_action`, `advanced_tools_action` eliminados de `main_window.py` | 35.1 |
| `_extract_build_profile` / `_extract_default_target_kind` no manejaban defines indirectos | Soporte para `ACTIVE_MODE OKUA_DEFAULT_ACTIVE_MODE` y `ACTIVE_SENSOR OKUA_DEFAULT_ACTIVE_SENSOR` | 34.8 |

---

## Limitaciones conocidas no bloqueantes

| ID | Limitación | Impacto operativo |
|----|-----------|------------------|
| SERIAL-1 | Sesión serial con Maestro USB no validada | Sin Maestro USB durante el ciclo; Camino B (UDP) cubre el requisito operativo |
| OTA-CAMP-1 | Campaña OTA multi-wave (más de 1 wave con gate intermedio) no ejecutada en hardware | Lógica multi-wave cubierta por tests; wave única validada con hardware real |
| SCOPE-1 | Validado solo con EB1 + EB2 en subred 192.168.1.x | Sin prueba con más de 2 nodos simultáneos |
| SCOPE-2 | Validado únicamente en la máquina de José David (Windows 11 Home, josecillo) | No probado en otro entorno Windows |

---

## Artefacto principal

**`python main.py`** desde la raíz del repositorio, rama `desarrollo-fase-2`.

Commit de cierre del ciclo RC: **`1e1f474`** (mapa Home confirmado — último commit pre-36.0).

El `.exe` empaquetado (`dist/Control OKÚA CKv2.exe`, PyInstaller 6.19.0) fue generado y verificado en 34.3 pero **no es la ruta operativa validada** para esta release. Usar solo si se requiere distribución sin entorno Python.

---

## Recomendación de uso interno

Esta release es apta para uso controlado por José David en la instalación OKÚA Jardín Biosonoro bajo las siguientes condiciones:

1. Usar `python main.py` — no el `.exe`.
2. Seguir el preflight del runbook (`release_candidate_runbook.md` §1) antes de cada sesión.
3. Perfil operativo recomendado: `udp_jardin` con nodos EB1 + EB2 en red local.
4. No usar `lab_sim` en instalación productiva.
5. Para OTA: usar el Firmware Manager con el artifact `is_current=True` adecuado al nodo.
6. Para acceso remoto: habilitar módulo Remoto en `local_only` o `tailscale_only` según necesidad.

Para contingencia, ver `release_candidate_runbook.md` §4.
