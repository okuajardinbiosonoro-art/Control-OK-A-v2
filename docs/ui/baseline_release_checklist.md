# Checklist de cierre técnico de baseline — Control OKÚA CKv2

Rama: `desarrollo-fase-2`  
Última actualización: 2026-04-16 (Ticket 34.6 — cierre documental de baseline)

---

## Suite de pruebas

| Ítem | Estado |
| --- | --- |
| `python -m compileall src main.py` | PASA |
| `pytest` completo (467 tests) | PASA — 0 fallos |
| Fallo preexistente `test_profile_mode_consistency` | RESUELTO — test actualizado para buscar `QAction` en vez de `QPushButton` (la acción "Cambiar perfil" vive en el menú, no como botón standalone) |

---

## Icono y packaging

| Ítem | Estado |
| --- | --- |
| Icono runtime (`app_icon_path()`) | CORRECTO — prioriza `assets/branding/okua_app_icon.ico` |
| Spec principal (`ControlOkuaV2.spec`) | CORRECTO — nombre `"Control OKÚA CKv2"`, icono apunta a `assets/branding/` |
| Spec debug (`ControlOkuaV2.debug.spec`) | CORRECTO — nombre `"Control OKÚA CKv2 (debug)"`, icono actualizado a `assets/branding/` |
| Specs obsoletos (`Control OKUA v2.spec`, `Control Okua Debug.spec`) | LEGACY — apuntan a `assets/icons/` que ya no existe; no usar para builds; candidatos a borrar en release final |
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

## Estado de validación funcional (34.6)

| Ítem | Estado |
|------|--------|
| Arranque visual en máquina real | **CONFIRMADO** — validación manual real por José David (a27d2b5) |
| Navegación a Diagnóstico, Técnico, Firmware, Remoto | **PARCIAL** — observados con evidencia de bugs detectados y corregidos |
| Diálogos About, AdvancedTools | **CONFIRMADO** — abiertos, bugs detectados, corregidos |
| Toast notifications | **CONFIRMADO** — duración y microcopy ajustados tras observación real |
| Home/Inicio (mapa, chip) | **PENDIENTE** — sin mención explícita en commits post-34.5 |
| Flujo mapa ↔ Nodos ("Ver nodos") | **PENDIENTE** |
| Sesión serial (Maestro por USB) | **NO EJECUTADO** |
| Sesión UDP (nodos en red real) | **NO EJECUTADO** |

**Decisión RC: TODAVÍA NO CANDIDATA** — falta: (1) sesión real de extremo a extremo, (2) flujo mapa ↔ Nodos confirmado. Ver decisión completa en `docs/ui/baseline_functional_qa_execution.md`.

---

## Qué queda para declarar release candidate funcional

- **BLOQUEANTE 1:** Al menos una sesión real (serial con Maestro USB o UDP con nodos OKÚA) de extremo a extremo
- **BLOQUEANTE 2:** Confirmación del flujo mapa ↔ Nodos en runtime real

---

## Qué queda para tag de release final (no bloqueante para RC)

- Eliminar specs obsoletos (`Control OKUA v2.spec`, `Control Okua Debug.spec`) antes del tag de release
- Decidir destino de 4 QActions huérfanos en menú (ver QA report)
- QA funcional de pantalla Firmware (catálogo, despliegue) end-to-end
- Test de campaña OTA end-to-end con hardware real

---

## Qué NO debe reabrirse

- Diseño del mapa Home (33.x — funcional y completo)
- Design system / tokens visuales (34.0 — consolidado)
- Microcopy y branding visible (34.1 — cerrado)
- Higiene técnica de repo (34.2 — cerrado)
- Arquitectura de sesión / backend (estable)
- Navegación lateral (shell, secciones) — no reabrir sin necesidad funcional real
