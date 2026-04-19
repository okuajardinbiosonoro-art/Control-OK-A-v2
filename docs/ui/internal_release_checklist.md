# Checklist de entrega interna — Control OKÚA CKv2 — RC1

Rama: `desarrollo-fase-2`  
Fecha: 2026-04-18 (Ticket 36.0)  
Referencia operativa completa: [`release_candidate_runbook.md`](release_candidate_runbook.md)

---

## Artefacto principal

| Ítem | Valor |
|------|-------|
| Ruta de ejecución | `python main.py` desde raíz del repo, rama `desarrollo-fase-2` |
| Commit de cierre de ciclo RC | `1e1f474` |
| Alternativa empaquetada | `dist/Control OKÚA CKv2.exe` (PyInstaller 6.19.0) — viable para distribución; verificación visual pendiente de José David (ver 36.2) |

---

## Entorno mínimo

| Requisito | Valor |
|-----------|-------|
| Sistema operativo | Windows 11 |
| Python | 3.11+ |
| Dependencias | `pip install -r requirements.txt` (PySide6, rtmidi y dependencias) |
| MIDI virtual | loopMIDI con Port 1 y Port 2 activos antes de arrancar |
| Red | Subred 192.168.1.x con nodos EB1 (`.89`) y EB2 (`.90`) activos (perfil `udp_jardin`) |
| Configuración | `config.json` en raíz del repo (ver `config.example.json`) |

> Nota de 36.1: en una copia limpia, el primer arranque puede crear `config.json` y abrir el selector de perfil. Para un ensayo no interactivo, usa `CKV2_AUTOPROFILE=udp_jardin`.

---

## Preflight antes de usar

| # | Verificación | Cómo confirmar |
|---|-------------|----------------|
| P1 | Python disponible | `python --version` → `3.11.x` o superior |
| P2 | Dependencias instaladas | `pip show PySide6 rtmidi` sin error |
| P3 | `config.json` presente | Archivo existe en raíz del repo, o fue creado por el primer arranque |
| P4 | Perfil activo correcto | `config.json` → `"profile": {"active": "udp_jardin"}`; si viene `null`, completar el selector guiado o usar `CKV2_AUTOPROFILE=udp_jardin` |
| P5 | loopMIDI activo | Ícono en bandeja; Port 1 y Port 2 visibles |
| P6 | Red local accesible | `ping 192.168.1.89` responde |
| P7 | Sin proceso previo colgado | Administrador de tareas sin `python main.py` activo |

---

## Superficies principales verificadas

| Superficie | Estado |
|-----------|--------|
| Arranque visual — título `Control OKÚA · CKv2`, barra lateral | VALIDADO — José David (34.5) |
| Mapa Home — estado de cajas por sesión UDP | VALIDADO — capa de datos (34.7) + confirmación visual interactiva por José David (2026-04-18) |
| Flujo mapa → Nodos — CTA "Ver nodos", barra de contexto | CONFIRMADO — José David (2026-04-18) |
| Nodos — árbol, columnas, filtrado | VALIDADO con datos reales (34.7) |
| Diagnóstico — resumen runtime, chequeos previos | VALIDADO visualmente (34.5) |
| Técnico → Comandos — botón "Solicitar STAT" | VALIDADO visualmente (34.5) |
| About dialog profesional | VALIDADO — reemplazó QMessageBox (34.5) |
| Toast notifications — duración y nivel | VALIDADO — BUG-1 (35.4) corregido |

---

## Firmware / OTA

| Ítem | Estado |
|------|--------|
| Firmware Manager — catálogo, filtros, detalle de artefacto | VALIDADO (35.2) |
| OTA Deploy UI — layout, configuración de red, nodos | VALIDADO (35.2) |
| OTA Campaign UI — preview de waves, canary, health gate | VALIDADO (35.2) |
| OTA Deploy con hardware real | VALIDADO — EB1 TRIGGERED → BOOT_CONFIRMED (35.3) |
| Campaña OTA con hardware real | VALIDADO — EB1 canary COMPLETED, health gate PASSED, reboot confirmado (35.6) |

---

## Módulo Remoto / portal

| Ítem | Estado |
|------|--------|
| Suite de tests módulo Remoto | VALIDADO — 33/33 tests (35.4) |
| Portal `/remote/` — HTML, `app.js`, `styles.css` | VALIDADO — 200 OK en navegador real (35.5) |
| Bootstrap desde store vacía — 3 cuentas | VALIDADO (35.5) |
| Login/logout — roles admin, tecnico, observador | VALIDADO (35.5) |
| Restricciones por rol (403 en operaciones no autorizadas) | VALIDADO (35.5) |
| Modo `tailscale_only` — bind exclusivo, loopback rechazado | VALIDADO — `100.88.127.119` (35.5) |

---

## Contingencia básica

| Síntoma | Acción inmediata |
|---------|-----------------|
| Crash en arranque (`ModuleNotFoundError`) | `pip install -r requirements.txt` y reintentar |
| Sin nodos visibles en árbol | `ping 192.168.1.89` — verificar red y firewall UDP 5005/5006 |
| App no responde al detener sesión | Esperar 10 s; si sigue, `Alt+F4` y finalizar proceso en Task Manager |
| Rollback al último estado verificado | `git reset --hard 1e1f474` → `python main.py` |

Ver contingencia completa en `release_candidate_runbook.md` §4.

---

## Limitaciones no bloqueantes

| ID | Limitación |
|----|-----------|
| SERIAL-1 | Sesión serial con Maestro USB no validada en esta RC |
| OTA-CAMP-1 | Campaña OTA multi-wave (más de 1 wave con gate intermedio) no ejecutada en hardware |
| SCOPE-1 | Validado solo con EB1 + EB2 en la subred de José David |
| SCOPE-2 | No validado en otro entorno Windows fuera de la máquina de José David |

---

## Decisión de cierre

**El ciclo RC queda cerrado. Este checklist es evidencia de entrega de la Release Interna Controlada RC1.**

Para contexto completo de validación: [`release_candidate_handoff.md`](release_candidate_handoff.md)  
Para release notes: [`internal_release_notes_rc1.md`](internal_release_notes_rc1.md)  
Para operación de campo: [`release_candidate_runbook.md`](release_candidate_runbook.md)
