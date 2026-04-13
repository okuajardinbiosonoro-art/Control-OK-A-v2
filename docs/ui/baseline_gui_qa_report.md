# QA de baseline GUI — Control OKÚA CKv2

Rama: `desarrollo-fase-2`  
Fecha QA: 2026-04-13 (Ticket 34.3)  
Tipo de QA: code-audit + validación de tests + smoke de packaging

---

## Superficies y flujos revisados

### Inicio (Home)
- Layout correcto: status chip, subtitle operativo, botones "Iniciar/Detener sesión", "Más"
- Mapa `HomeMapPanel` presente con `minimumHeight >= 480`, sin `QScrollArea`
- Señales conectadas: `boxSelectionChanged` → contexto Nodos; `viewNodesRequested` → navega a Nodos
- Botones de acceso rápido ocultos correctamente cuando no aplican
- `home_status_chip` con texto inicial "Sesión inactiva"
- Sin scroll visible no deseado

### Nodos
- `QTreeWidget` con 7 columnas: Nodo, Estado, Último visto, PPS, Pérdida, RSSI, Última nota/vel
- Context bar ("Sin filtro de caja activo") se muestra/oculta según sincronización de mapa
- Botón "Ver todos" y "Ver caja en inicio" correctamente ubicados
- Sincronización mapa ↔ Nodos: `build_map_nodes_sync_context_for_box` / `_for_node` correctamente integrados

### Diagnóstico
- 7 campos en Resumen de sistema: Perfil, Archivo de config, Modo, Transporte, MIDI, Registro, Estado
- Sección "Chequeos previos" plegable con toggle, correctamente oculta por defecto
- Tabla de hallazgos preflight con 4 columnas: Severidad, Código, Mensaje, Detalle
- Grupos "Detalle serial" y "Detalle UDP" visibles según backend activo
- Subtítulo en nav: "Salud del sistema, diagnóstico y runtime." ✓

### Técnico
- Dos tabs: "Resumen" y "Control F3"
- Resumen: acceso a "Estado de sesión" + "Herramientas avanzadas"
- Control F3: `ControlPlanePanel` completo, botón "Solicitar STAT" ✓

### Firmware
- Hint: "Gestiona catálogo, versiones y despliegues OTA desde una vista única."
- Botón "Abrir gestor de firmware" (primary) + "Ir a Técnico" (secondary)
- Resumen de catálogo con 4 campos: Catálogo, Artifacts, Ruta, Nota OTA

### Remoto
- Resumen con 7 campos: Estado, Exposición, Bind efectivo, URL local, URL remota, Store usuarios, Último fallo
- Dropdown: "Solo este equipo" / "Solo red Tailscale" ✓ (bug corregido en este ticket)
- Botón "Aplicar servicio remoto" + enlace a "Herramientas avanzadas"

---

## Diálogos y ventanas secundarias

| Diálogo | Título | Estado |
|---------|--------|--------|
| Estado de sesión | "Estado de sesión" | Modal=False, modeless ✓ |
| Cambiar perfil | "Perfil de operación" | QDialog modal, 3 perfiles con radiobuttons ✓ |
| Gestor de firmware | "Gestor de firmware" | QDialog con catálogo, filtros, detalle ✓ |
| Herramientas avanzadas | "Centro técnico" | QDialog con config, remoto y firmware ✓ |
| Campaña OTA | "Campaña OTA" | ✓ (corregido en 34.1) |
| Despliegue OTA | "Despliegue OTA" | ✓ (corregido en 34.1) |
| About / Ayuda | "Acerca de" | QMessageBox con identidad de marca ✓ |
| Toasts | — | Animación slide+fade, auto-dismiss, posición bottom-right ✓ |

---

## Mapa — QA específica

| Ítem | Estado |
|------|--------|
| 5 cajas configuradas | ✓ |
| Estado agregado visible por caja | ✓ |
| Selección de caja → contexto en Nodos | ✓ |
| CTA "Ver nodos" → navega a Nodos con contexto | ✓ |
| Retorno a Inicio desde Nodos ("Ver caja en inicio") | ✓ |
| Sin scroll no deseado en Home | ✓ |
| minimumHeight >= 480 | ✓ |

---

## Bugs encontrados y resueltos

| # | Archivo | Bug | Fix |
|---|---------|-----|-----|
| 1 | `main_window.py:886` | Dropdown Tailscale: `"Solo Tailscale"` inconsistente con `advanced_tools_dialog.py` (`"Solo red Tailscale"`) | Corregido: `"Solo red Tailscale"` en ambos |

## Bugs encontrados y NO corregidos (fuera de alcance)

| # | Archivo | Observación | Razón no corregida |
|---|---------|-------------|---------------------|
| 1 | `main_window.py:285–293` | 4 QActions definidos en `_build_menu_bar` (`view_diagnostics_action`, `toggle_preflight_action`, `firmware_manager_action`, `advanced_tools_action`) no están añadidos a ningún menú | Decidir si deben ir en un menú es una decisión de UX/feature, fuera de alcance de QA |
| 2 | `main_window.py:400–407` | `change_profile_button` y `reset_session_error_button` son widgets huérfanos (sin parent, sin layout), ocultos permanentemente | Funcionalidad cubierta por QAction en menú y menu action; limpiar en futuro refactor |

---

## Smoke de empaquetado

| Ítem | Resultado |
|------|-----------|
| PyInstaller versión | 6.19.0 |
| Spec utilizado | `ControlOkuaV2.spec` |
| Nombre de ejecutable | `"Control OKÚA CKv2"` ✓ |
| Icono resuelto | `assets/branding/okua_app_icon.ico` ✓ |
| Assets incluidos | `assets/` y `remote_console_assets/` ✓ |
| Resultado del build | EXITOSO — `dist/Control OKÚA CKv2.exe` (54.7 MB) |
| Warnings en warn file | Solo módulos Unix/macOS opcionales (esperado en Windows) |
| Errores de build | Ninguno |

---

## Pruebas automáticas

| Prueba | Resultado |
|--------|-----------|
| `python -m compileall src main.py` | PASA — sin errores |
| `pytest` completo | 467 passed, 0 failed |

---

## Decisión final

**Baseline aprobada para cierre técnico y avance a QA funcional de campo.**

### Justificación
- Suite 100% verde (467/467)
- Build de packaging exitoso sin errores
- Único bug de consistencia encontrado y corregido (dropdown Tailscale)
- Todos los flujos principales revisados y funcionalmente coherentes en código
- Branding, microcopy y chrome correctos (34.0 + 34.1)
- Higiene técnica cerrada (34.2)

### Pendiente para QA de campo / release final
- Smoke de runtime en hardware real (Maestro + nodos)
- QA de sesión serial y UDP en red real
- Build de release final con firma (si aplica)
- Eliminar specs obsoletos (`Control OKUA v2.spec`, `Control Okua Debug.spec`)
- Decidir destino de los 4 QActions huérfanos del menú
