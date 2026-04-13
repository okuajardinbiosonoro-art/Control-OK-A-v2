# Checklist de cierre técnico de baseline — Control OKÚA CKv2

Rama: `desarrollo-fase-2`  
Última actualización: 2026-04-13 (Ticket 34.2)

---

## Suite de pruebas

| Ítem | Estado |
|------|--------|
| `python -m compileall src main.py` | PASA |
| `pytest` completo (467 tests) | PASA — 0 fallos |
| Fallo preexistente `test_profile_mode_consistency` | RESUELTO — test actualizado para buscar `QAction` en vez de `QPushButton` (la acción "Cambiar perfil" vive en el menú, no como botón standalone) |

---

## Icono y packaging

| Ítem | Estado |
|------|--------|
| Icono runtime (`app_icon_path()`) | CORRECTO — prioriza `assets/branding/okua_app_icon.ico` |
| Spec principal (`ControlOkuaV2.spec`) | CORRECTO — nombre `"Control OKÚA CKv2"`, icono apunta a `assets/branding/` |
| Spec debug (`ControlOkuaV2.debug.spec`) | CORRECTO — nombre `"Control OKÚA CKv2 (debug)"`, icono actualizado a `assets/branding/` |
| Specs obsoletos (`Control OKUA v2.spec`, `Control Okua Debug.spec`) | LEGACY — apuntan a `assets/icons/` que ya no existe; no usar para builds; candidatos a borrar en release final |
| `APP_DISPLAY_NAME` / `APP_ABOUT_NAME` en `design_system.py` | CORRECTO — `"Control OKÚA · CKv2"` / `"Control OKÚA CKv2"` |

---

## Widgets y módulos críticos

| Widget / módulo | Estado |
|-----------------|--------|
| `home_map_panel.py` | Tracked en git, funcional |
| `toast_manager.py` | Tracked en git, funcional |
| `config_view_dialog.py` | Tracked en git, funcional |
| `midi_outputs_widget.py` | AHORA tracked en git — excepción `.gitignore` añadida; columna "Salida configurada" (fix 34.1) incluida |
| `navigation_shell.py` | Subtítulo Diagnóstico: "diagnóstico y runtime" |
| `control_plane_panel.py` | Botón "Solicitar STAT" (era "Pedir STAT") |
| `main_window_vm.py` | Textos de estado sin "aún" residual |

---

## Archivos intencionalmente no versionados

| Archivo / carpeta | Razón |
|-------------------|-------|
| `src/control_okua/app_qt/widgets/*.py` (excepciones explícitas) | Directorio marcado como espacio de experimentos UI; sólo versionar con excepción explícita en `.gitignore` |
| `artifacts/` | Screenshots y evidencias de desarrollo |
| `logs/` | Salida de runtime |
| `config.json` (local) | Configuración local de usuario |

---

## Branding visible (34.0 + 34.1)

- Nombre de app: `Control OKÚA · CKv2` en titlebar y taskbar
- Icono en runtime: cargado desde `assets/branding/okua_app_icon.ico`
- Títulos de diálogos OTA: "Campaña OTA" / "Despliegue OTA" (era inglés)
- Menú: Aplicación + Ayuda únicamente
- Secciones laterales: Inicio / Nodos / Diagnóstico / Técnico / Firmware / Remoto
- About dialog: identidad de marca, sin texto genérico

---

## Qué queda para QA funcional / release final

- Smoke completo en hardware real (Maestro + nodos)
- Verificación de sesión serial con equipo físico
- Verificación de sesión UDP en red real
- Test de campaña OTA end-to-end
- Build de PyInstaller con `ControlOkuaV2.spec` y smoke del ejecutable
- Eliminar specs obsoletos (`Control OKUA v2.spec`, `Control Okua Debug.spec`) antes del tag de release
- QA funcional de pantalla Firmware (catálogo, despliegue)
- QA funcional de pantalla Remoto (servicio, dropdown "Solo este equipo")

---

## Qué NO debe reabrirse

- Diseño del mapa Home (33.x — funcional y completo)
- Design system / tokens visuales (34.0 — consolidado)
- Microcopy y branding visible (34.1 — cerrado)
- Arquitectura de sesión / backend (estable)
- Navegación lateral (shell, secciones) — no reabrir sin necesidad funcional real
