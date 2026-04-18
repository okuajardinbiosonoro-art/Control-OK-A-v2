# QA funcional — Firmware Manager / OTA UI — Control OKÚA CKv2

Rama: `desarrollo-fase-2`  
Fecha: 2026-04-17 (Ticket 35.2)  
Tipo: QA funcional de UI/flujo — sin hardware OTA real

---

## Superficies revisadas

| Superficie | Archivo |
|------------|---------|
| Firmware Manager | `src/control_okua/app_qt/firmware_manager_dialog.py` |
| OTA Deploy | `src/control_okua/app_qt/ota_deploy_dialog.py` |
| OTA Campaign | `src/control_okua/app_qt/ota_campaign_dialog.py` |
| ViewModels Firmware | `src/control_okua/app_qt/viewmodels/firmware_manager_vm.py` |
| ViewModels OTA | `src/control_okua/app_qt/viewmodels/ota_deploy_vm.py`, `ota_campaign_vm.py` |
| Tests | `tests/test_ota_dialog_layout.py`, `test_ota_campaign_dialog_layout.py`, `test_firmware_manager_vm.py`, `test_ota_deploy_vm.py`, `test_ota_campaign_vm.py` |

---

## Escenarios revisados — Firmware Manager

| # | Escenario | Resultado |
|---|-----------|---------|
| FM-1 | Apertura del gestor sin catálogo — estado vacío | PASA — muestra `empty_title_label` y `empty_hint_label` con mensaje claro |
| FM-2 | Catálogo con artefactos — tabla visible con columnas y ordenación por fecha desc | PASA — `QTableView` con `FirmwareCatalogTableModel`, sort indicator en col 9 |
| FM-3 | Botones de acción — estado inicial | PASA — "Marcar como current" y "Borrar firmware" deshabilitados hasta selección; "Importar firmware…" siempre activo; "Recargar catálogo" siempre activo |
| FM-4 | Botones OTA — dependencia de `session_controller` | PASA — "Despliegue OTA…" y "Campaña OTA…" deshabilitados si no hay `SessionController`; guard correcto en `_on_ota_deploy_clicked` y `_on_ota_campaign_clicked` |
| FM-5 | Selección de artefacto — panel detalle se actualiza | PASA — `_render_detail` actualiza 17 campos escalares, changelog y notas; `current_summary_label` refleja selección |
| FM-6 | Filtros de búsqueda, target y status | PASA — `filter_firmware_catalog_rows` filtrado correcto; conteo en `summary_label` coherente |
| FM-7 | Filtro "Sólo current" | PASA — restringe a artefactos `is_current=True` |
| FM-8 | Selección vacía tras filtro | PASA — `_render_detail(None)` limpia el panel de detalle |
| FM-9 | Texto de confirmación al marcar current | PASA — `build_mark_current_confirmation_text` genera texto claro con nombre y target |
| FM-10 | Texto de confirmación al borrar | PASA — muestra nombre, artifact_id, ruta y advertencia de disco |
| FM-11 | "Abrir carpeta del firmware" | PASA — `_open_managed_store_folder` crea el directorio si no existe y abre el explorador |
| FM-12 | Notify sin `_on_notify` externo | PASA — fallback a `QMessageBox.warning` / `.information` según nivel |

---

## Escenarios revisados — OTA Deploy

| # | Escenario | Resultado |
|---|-----------|---------|
| OD-1 | Apertura sin artefactos ni nodos | PASA — catálogo vacío; combo firmware vacío; mensaje "Sin firmware seleccionado." y "No hay nodos conectados." |
| OD-2 | Estado inicial de botones | PASA — "Publicar actualización" deshabilitado; "Actualizar estados" y "Abrir carpeta" deshabilitados |
| OD-3 | Layout — secciones no se superponen a 1120×760 | PASA — `test_ota_deploy_no_section_overlap_base_size` |
| OD-4 | Layout — secciones no se superponen a 1920×1080 | PASA — `test_ota_deploy_no_section_overlap_wide_size` |
| OD-5 | Layout — secciones no se superponen a 1366×768 | PASA — `test_ota_deploy_no_section_overlap_compact_size` |
| OD-6 | Rollout group contiene todos sus campos | PASA — 8 filas (IP, bind, puerto, token, canal, timeout, reintentos, downgrade) dentro del grupo |
| OD-7 | Nodos group — legibilidad mínima | PASA — lista, botón y hint separados sin solapamiento |
| OD-8 | Panel de detalle oculto antes del despliegue | PASA — `details_edit.isVisible() == False` en estado inicial |
| OD-9 | `allow_downgrade` — confirmación de advertencia antes de desplegar | PASA — QMessageBox con texto claro antes de proceder |
| OD-10 | Validación sin artefacto seleccionado | PASA — `QMessageBox.warning` con mensaje apropiado |
| OD-11 | Validación sin nodos seleccionados | PASA — `QMessageBox.warning` con mensaje apropiado |
| OD-12 | `reload_artifacts` / `reload_nodes` — no crash con sesión vacía | PASA — stub `get_node_snapshots` devuelve `[]`; UI queda estable |
| OD-13 | Timer de refresco se detiene en `closeEvent` | PASA — `_refresh_timer.stop()` en `closeEvent` |

---

## Escenarios revisados — OTA Campaign

| # | Escenario | Resultado |
|---|-----------|---------|
| OC-1 | Apertura sin artefactos ni nodos | PASA — combos vacíos; hints claros; lista de nodos con mensaje de sesión inactiva |
| OC-2 | Estado inicial de botones de campaña | PASA — "Iniciar primera ola" deshabilitado; "Continuar", "Pausar", "Abortar", "Actualizar estado" todos deshabilitados |
| OC-3 | "Validación previa: Activada" (toggle) | PASA — `require_canary_checkbox` checkable; al desactivar se actualiza el label y deshabilita `canary_list` |
| OC-4 | Preview de distribución de olas | PASA — `wave_preview_label` se actualiza al cambiar nodos o wave_size |
| OC-5 | Sincronización canary → nodos de campaña | PASA — `_sync_canary_selection` oculta nodos canary que no estén en la selección de campaña |
| OC-6 | Layout — secciones no solapadas a 1600×900 | PASA — `test_ota_campaign_middle_and_bottom_sections_do_not_overlap` |
| OC-7 | Rollout group — todos los controles visibles y legibles | PASA — 7 controles ≥ 200px ancho, dentro del grupo, ≥ 30px alto |
| OC-8 | Estrategia de olas — canary list legible y separada de wave_spin | PASA — lista ≥ 120px, separación clara |
| OC-9 | Panel de detalle oculto antes de campaña | PASA — `details_edit.isVisible() == False` inicial |
| OC-10 | Tabla de resultados se vuelve dominante al mostrar detalle | PASA — `splitter.sizes()[0] >= splitter.sizes()[1]` |
| OC-11 | Configuración inválida — sin firmware elegible | PASA — `OtaCampaignValidationError` atrapada, `QMessageBox.warning` |
| OC-12 | Timer se detiene en `closeEvent` | PASA — `_refresh_timer.stop()` |
| OC-13 | Preselección de artefacto desde Firmware Manager | PASA — `preselected_artifact_id` resuelto en `reload_artifacts` |

---

## Bugs encontrados

### BUG-1 — OTA Deploy: rollout group overflow / white pit / solapamiento de secciones

**Descripción:** El grupo "Configuración de red" en `OtaDeployDialog` desbordaba visualmente hacia el área de resultados a causa de un layout `QVBoxLayout` que sub-asignaba espacio mínimo. El panel de detalles (`details_edit`) tampoco se inicializaba correctamente al primer despliegue, dejando un espacio vacío visible.

**Causa raíz:** `QVBoxLayout` distribuye espacio según `sizeHint` calculado antes de que QSS aplique padding, subestimando ~50 px. Con el grupo de 8 filas eso causaba desbordamiento visible.

**Corrección:** `QVBoxLayout` reemplazado por `QSplitter(Vertical)` con `setChildrenCollapsible(False)`. El rollout group ahora usa `QGridLayout` + altura mínima calculada desde primeros principios (`content_min_h + _HEADER_V`). Panel de detalles inicializado oculto y revelado con `setSizes([75%, 25%])` en el primer despliegue.

**Archivo:** `src/control_okua/app_qt/ota_deploy_dialog.py`  
**Tests añadidos:** `test_ota_dialog_layout.py` — 14 nuevos tests de layout/geometría (ver §Pruebas automáticas)  
**Estado:** CORREGIDO — en working tree antes de este ticket; comprometido en 35.2

---

## Bugs documentados (sin corrección en este ticket)

Ninguno. El único bug detectado fue BUG-1, ya corregido en working tree.

---

## Qué NO quedó validado — OTA end-to-end real

| Ítem | Razón | Cuándo |
|------|-------|--------|
| Despliegue OTA real con nodo ESP32 | Sin firmware OTA-compatible en nodos durante esta QA | Próximo ciclo |
| Campaña OTA ola a ola con nodos reales | Ídem — requiere firmware y protocolo HTTP OTA activo | Próximo ciclo |
| Servidor OTA activo (`OtaServerService`) | No levantado durante esta QA de UI | Con hardware |
| Confirmación de `ack` del nodo | Requiere nodo con firmware compatible | Con hardware |

**La UI, el flujo, los estados visuales, validaciones y mensajes del módulo Firmware/OTA quedaron validados. El end-to-end OTA real permanece pendiente de hardware compatible.**

---

## Pruebas automáticas ejecutadas

```
PYTHONPATH=src python -m pytest tests/test_ota_dialog_layout.py tests/test_ota_campaign_dialog_layout.py tests/test_ota_campaign_vm.py tests/test_ota_deploy_vm.py tests/test_firmware_manager_vm.py -v
```

**Resultado: 35/35 PASAN**

| Módulo | Tests | Resultado |
|--------|-------|---------|
| `test_ota_dialog_layout.py` | 15 | PASAN |
| `test_ota_campaign_dialog_layout.py` | 10 | PASAN |
| `test_ota_campaign_vm.py` | 2 | PASAN |
| `test_ota_deploy_vm.py` | 4 | PASAN |
| `test_firmware_manager_vm.py` | 5 | PASAN |

`python -m compileall src main.py` — **PASA**

---

## Estado documental

- `baseline_release_checklist.md` → ítem "QA funcional de pantalla Firmware" marcado como EJECUTADO en 35.2
