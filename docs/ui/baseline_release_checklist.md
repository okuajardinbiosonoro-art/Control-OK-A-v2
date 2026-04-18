# Checklist de cierre técnico de baseline — Control OKÚA CKv2

Rama: `desarrollo-fase-2`  
Última actualización: 2026-04-17 (Ticket 35.3 — protocolo de validación OTA hardware preparado)

---

## Suite de pruebas

| Ítem | Estado |
| --- | --- |
| `python -m compileall src main.py` | PASA |
| `pytest` completo (494 tests) | PASA — 494/494, 0 fallos (estado post-35.2) |
| Fallo preexistente `test_profile_mode_consistency` | RESUELTO en 34.3 |
| Fallos pre-existentes `test_artifact_agent_service` (9) | RESUELTO en 34.8 — `_extract_build_profile` y `_extract_default_target_kind` ya manejan defines indirectos (`ACTIVE_MODE OKUA_DEFAULT_ACTIVE_MODE`, `ACTIVE_SENSOR OKUA_DEFAULT_ACTIVE_SENSOR`) |

---

## Icono y packaging

| Ítem | Estado |
| --- | --- |
| Icono runtime (`app_icon_path()`) | CORRECTO — prioriza `assets/branding/okua_app_icon.ico` |
| Spec principal (`ControlOkuaV2.spec`) | CORRECTO — nombre `"Control OKÚA CKv2"`, icono apunta a `assets/branding/` |
| Spec debug (`ControlOkuaV2.debug.spec`) | LOCAL/GITIGNOREADO — herramienta local de builds de depuración; no comprometer ni distribuir; decisión cerrada en 35.0-correctivo |
| `Control OKUA v2.spec` | ELIMINADO en 34.8 — ya no existe en el repo |
| `Control Okua Debug.spec` | GITIGNOREADO — no comprometido; apuntaba a `assets/icons/` inexistente; no usar |
| `APP_DISPLAY_NAME` / `APP_ABOUT_NAME` en `design_system.py` | CORRECTO — `"Control OKÚA · CKv2"` / `"Control OKÚA CKv2"` |
| Build de packaging (Ticket 34.3) | EXITOSO — `dist/Control OKÚA CKv2.exe` generado con PyInstaller 6.19.0 |

---

## Widgets y módulos críticos

| Widget / módulo | Estado |
| --- | --- |
| `home_map_panel.py` | Tracked en git, funcional |
| `toast_manager.py` | Tracked en git, funcional |
| `config_view_dialog.py` | Tracked en git, funcional |
| `midi_outputs_widget.py` | Tracked en git desde 34.2 — columna "Salida configurada" incluida |
| `navigation_shell.py` | Subtítulo Diagnóstico: "diagnóstico y runtime" |
| `control_plane_panel.py` | Botón "Solicitar STAT" (era "Pedir STAT") |
| `main_window_vm.py` | Textos de estado sin "aún" residual |

---

## Archivos intencionalmente no versionados

| Archivo / carpeta | Razón |
| --- | --- |
| `src/control_okua/app_qt/widgets/*.py` (excepciones explícitas) | Directorio marcado como espacio de experimentos UI; sólo versionar con excepción explícita en `.gitignore` |
| `artifacts/` | Screenshots y evidencias de desarrollo |
| `logs/` | Salida de runtime |
| `config.json` (local) | Configuración local de usuario |

---

## Branding visible (34.0 + 34.1 + 34.5)

- Nombre de app: `Control OKÚA · CKv2` en titlebar y taskbar
- Icono en runtime: cargado desde `assets/branding/okua_app_icon.ico`
- Títulos de diálogos OTA: "Campaña OTA" / "Despliegue OTA" (era inglés) — labels internos humanizados en 34.5b
- Menú: Aplicación + Ayuda únicamente
- Secciones laterales: Inicio / Nodos / Diagnóstico / Técnico / Firmware / Remoto
- About dialog: AboutDialog profesional con versión, perfil activo, plataforma, transporte (reemplaza QMessageBox genérico — 34.5)
- Sección "Técnico": sub-tab renombrado "Control F3" → "Comandos" en toda la app (34.5b)

---

## Estado de validación funcional (34.7 — FINAL)

| Ítem | Estado |
|------|--------|
| Arranque visual en máquina real | **CONFIRMADO** — validación manual real por José David (a27d2b5) |
| Navegación a Diagnóstico, Técnico, Firmware, Remoto | **PARCIAL-CONFIRMADO** — observados con bugs detectados y corregidos |
| Diálogos About, AdvancedTools | **CONFIRMADO** — abiertos, bugs detectados, corregidos |
| Toast notifications | **CONFIRMADO** — duración y microcopy ajustados tras observación real |
| Sesión UDP real (nodos en red) | **CONFIRMADO** — EB1/Caja 1 + EB2/Caja 2; 320 EVT, 16 STAT, 0 errores (34.7) |
| Flujo mapa ↔ Nodos (capa de datos) | **CONFIRMADO** — ViewModels + filtrado por caja validados con datos reales (34.7) |
| Home/Inicio (mapa visual) | **PENDIENTE** — mapa visual interactivo no observado por agente; capa de datos OK |
| Sesión serial (Maestro por USB) | **NO EJECUTADO** — sin Maestro USB; Camino B cubre el requisito |

**Decisión RC: CANDIDATA A RELEASE FUNCIONAL** — sesión UDP real ejecutada sin errores; flujo mapa↔Nodos validado con datos reales; validación visual ya confirmada por José David.

Ver acta completa en `docs/ui/baseline_functional_qa_execution.md` (sección "Validación operativa real — Ticket 34.7").

---

## Qué queda para tag de release final (no bloqueante para RC)

- ~~Decidir destino de `ControlOkuaV2.debug.spec`~~ — CERRADO en 35.0-correctivo: mantener gitignoreado como herramienta local de depuración
- ~~4 QActions huérfanos en menú~~ — ELIMINADOS en 35.1: `view_diagnostics_action`, `toggle_preflight_action`, `firmware_manager_action`, `advanced_tools_action` eliminados de `main_window.py`; referencias residuales limpiadas
- Confirmación visual interactiva del mapa por José David (click en cajas, CTA "Ver nodos")
- ~~QA funcional de Firmware Manager / OTA UI (catálogo, campaña, despliegue)~~ — UI/flujo EJECUTADO en 35.2; end-to-end OTA real pendiente de hardware compatible
- Test de OTA Deploy end-to-end con hardware real — protocolo preparado en 35.3 ([`firmware_ota_hardware_validation.md`](firmware_ota_hardware_validation.md)); ejecución pendiente de sesión con José David y hardware
- Test de campaña OTA end-to-end con hardware real — pendiente de hardware y ciclo posterior

---

## Qué NO debe reabrirse

- Diseño del mapa Home (33.x — funcional y completo)
- Design system / tokens visuales (34.0 — consolidado)
- Microcopy y branding visible (34.1 — cerrado)
- Higiene técnica de repo (34.2 — cerrado)
- Arquitectura de sesión / backend (estable)
- Navegación lateral (shell, secciones) — no reabrir sin necesidad funcional real
