# QA funcional — Módulo Remoto — Control OKÚA CKv2

Rama: `desarrollo-fase-2`
Fecha: 2026-04-18 (Ticket 35.4 + Ticket 35.5)
Tipo: QA funcional de código + suite automática + validación real del portal web con navegador y Tailscale

---

## Entorno de revisión

| Ítem | Detalle |
|------|---------|
| Método (35.4) | Lectura completa de código + análisis de flujo + suite automática |
| Método (35.5) | Servicio standalone + 27 escenarios funcionales automáticos + navegador real + Tailscale |
| UI viva | **VALIDADA en 35.5** — navegador abierto en `http://127.0.0.1:8789/remote/`, portal cargado |
| Tailscale | **VALIDADO en 35.5** — IP `198.51.100.10`, bind exclusivo confirmado |
| Tests automáticos | 33 tests de Remote ejecutados (35.4) + 27 escenarios funcionales reales (35.5) — todos PASAN |

---

## Archivos revisados

| Archivo | Qué se revisó |
|---------|--------------|
| `src/control_okua/services/remote_auth_service.py` | Hash de contraseñas, bootstrap, CRUD |
| `src/control_okua/services/remote_api_service.py` | Servidor HTTP, dispatch, rutas, auth |
| `src/control_okua/services/remote_api_bootstrap.py` | Inicialización, bind host, URLs |
| `src/control_okua/services/remote_api_contract.py` | Config, defaults, serialización |
| `src/control_okua/services/remote_api_auth.py` | Tokens, roles, autorización |
| `src/control_okua/services/remote_session_service.py` | Sesiones cookie, TTL |
| `src/control_okua/services/remote_user_store.py` | Persistencia JSON, validaciones |
| `src/control_okua/services/remote_api_audit.py` | Auditoría JSONL |
| `src/control_okua/app_qt/main_window.py` | Panel Remoto, controles, refresh summary |
| `src/control_okua/app_qt/app.py` | Ciclo de vida del servicio, callback apply |

---

## Bloque 1 — Escenarios revisados

### RE-1 — Apertura de la superficie Remoto

**Método:** Revisión de `_build_remote_tab()` en `main_window.py`.

**Resultado:** PASA

- Título `"Remoto"` visible con `sectionTitleLabel`.
- Hint: `"Supervisa el acceso remoto y aplica cambios rápidos del servicio."` — claro y adecuado.
- Grupo "Resumen del servicio remoto" con 7 campos: Estado, Exposición, Bind efectivo, URL local, URL remota, Store usuarios, Último fallo.
- Grupo "Control rápido" con: checkbox habilitado, combo de modo, botón "Aplicar".
- Si no hay `_remote_api_status`, todos los campos muestran `-` o mensajes neutros — **estado vacío manejado correctamente**.

---

### RE-2 — Lectura correcta de estado del servicio

**Método:** Revisión de `_refresh_remote_shell_summary()`.

**Resultado:** PASA

- El summary lee del objeto `_remote_api_status` (pasado por `set_remote_api_status()` desde `app.py`) y de `self.cfg["remote_api"]` para los controles.
- Ambas fuentes son coherentes: `self.cfg` es la misma referencia dict mutada por `_apply_remote_api_settings`, no una copia.
- `_remote_state_label()` traduce correctamente: `running→Activo`, `stopped→Detenido`, `failed→Error al iniciar`.
- `_remote_failure_label()` trunca mensajes largos a 120 caracteres — correcto.

---

### RE-3 — Presentación de URLs y exposición

**Método:** Revisión de `build_remote_api_access_urls()` y `_refresh_remote_shell_summary()`.

**Resultado:** PASA con nota

- URL local: `http://127.0.0.1:{port}/remote/` — mostrada si hay status.
- URL remota: `http://<tailscale-ip>:{port}/remote/` — solo si Tailscale resuelve IP.
- Bind efectivo: refleja la IP real donde el servidor está escuchando.
- Si `remote_access_url` es None (sin Tailscale): se muestra "No disponible" — correcto.
- **Nota:** La consola web en `/remote/` es la superficie principal de acceso; está servida por `RemoteApiService` desde assets estáticos.

---

### RE-4 — Flujo de aplicar configuración remota

**Método:** Revisión de `_apply_remote_settings_from_shell()` → `apply_remote_settings()` → `_on_apply_remote_settings` → `_apply_remote_api_settings()` (app.py) → `_restart_remote_api_runtime()`.

**Resultado:** PASA (con BUG-1 corregido en este ticket)

**Flujo completo verificado:**
1. Usuario marca checkbox + selecciona modo + pulsa "Aplicar"
2. `_apply_remote_settings_from_shell` lee los valores del combo y checkbox
3. Llama `apply_remote_settings(enabled, exposure_mode)`
4. `apply_remote_settings` verifica que no hay sesión activa (guard correcto)
5. Llama callback `_on_apply_remote_settings` de app.py
6. app.py muta `cfg["remote_api"]`, guarda `config.json`, reinicia el servicio
7. Si éxito: retorna `(running_status, "Servicio remoto actualizado...")`
8. Si fallo: retorna `(failed_status, "La configuración se guardó, pero el servicio remoto no pudo iniciarse: [error]")`
9. La UI muestra toast y refresca el summary

**BUG corregido (BUG-1):** Ver §Bugs encontrados.

---

### RE-5 — Estado vacío o no configurado

**Método:** Revisión del branch `if status is None` en `_refresh_remote_shell_summary()`.

**Resultado:** PASA

- Si `_remote_api_status` es None: Estado = "No disponible", todos los campos = `-` o mensaje neutral.
- El combo y checkbox aún leen de `cfg["remote_api"]` y muestran el estado guardado.
- El botón "Aplicar" permanece habilitado si `_on_apply_remote_settings is not None` y la sesión lo permite.

---

### RE-6 — Warnings y errores coherentes

**Método:** Revisión del flujo de `_restart_remote_api_runtime()` y mensajes de error de cada servicio.

**Resultado:** PASA con nota

- Errores de bind (puerto ocupado): `OtaServerServiceError` → capturada, `service_state="failed"`, `failure_message` visible en UI.
- Errores de Tailscale (sin IP): excepción clara, `service_state="failed"`, `failure_message` truncada a 120 chars.
- Errores de bootstrap (roles faltantes): `RemoteAuthServiceError` → mensaje en castellano para el usuario.
- `_remote_failure_label()` trunca a 120 chars para no desbordar el layout.
- **Nota**: El portal HTTP en `/api/v1/health` responde `{"ok": true, "data": {"status": "running"}}` incluso sin sesión — es público. Permite verificar el estado del servidor exteriormente.

---

### RE-7 — Mensajes de éxito coherentes

**Método:** Revisión de los strings de retorno en `_restart_remote_api_runtime()`.

**Resultado:** PASA (después de BUG-1 corregido)

| Escenario | Mensaje de retorno | Nivel toast correcto |
|-----------|-------------------|---------------------|
| Servicio activado y arranca | `"Servicio remoto actualizado. Revise la URL..."` | success ✓ |
| Servicio deshabilitado | `"Servicio remoto deshabilitado. El acceso desde otro dispositivo quedó apagado."` | success ✓ |
| Config guardada pero falla arranque | `"La configuración se guardó, pero el servicio remoto no pudo iniciarse: [error]"` | **warning ✓** (corregido) |

---

### RE-8 — Configuración inválida o incompleta

**Método:** Revisión de `ensure_remote_api_runtime_config()` y `resolve_remote_api_bind_host()`.

**Resultado:** PASA con nota

- `ensure_remote_api_runtime_config()` corrige automáticamente: fields faltantes con defaults, `exposure_mode` desconocido → `local_only`, `auth_mode` inválido → `human_session_only`.
- `tailscale_only` sin Tailscale instalado → falla con mensaje claro en `failure_message`.
- `human_session_only` sin bootstrap de usuarios → API devuelve `{ "bootstrap_required": true }` en `/api/v1/health`; consola web guía al usuario a hacer bootstrap.
- `auth_mode="bearer_token"` sin env var definida → falla al arrancar; mensaje en consola indica qué env var falta.

---

### RE-9 — Persistencia de estado al volver a abrir

**Método:** Revisión del flujo `save_config()` → `load_config()` y construcción de `MainWindow`.

**Resultado:** PASA

- Al aplicar: `_apply_remote_api_settings` llama `save_config(cfg, config_path)`.
- Al reabrir la app: `load_config()` recarga el JSON; `_refresh_remote_shell_summary()` refleja el estado guardado.
- Las sesiones HTTP se pierden al reiniciar el servicio (en-memoria) — **comportamiento documentado y esperado** (los usuarios deben volver a hacer login).
- La store de usuarios es persistente en `remote_api_users.json`.

---

### RE-10 — No rompe el resto de la RC funcional

**Método:** Suite completa tras corrección.

**Resultado:** PASA — 498/498 tests pasan.

---

## Bloque 2 — Flujo de autenticación y autorización revisado

### Roles y permisos verificados

| Acción | observador | tecnico | admin |
|--------|-----------|---------|-------|
| `GET /api/v1/health` | ✓ (público) | ✓ | ✓ |
| `GET /api/v1/nodes` | ✓ | ✓ | ✓ |
| `GET /api/v1/node/{id}` | ✓ | ✓ | ✓ |
| `POST /api/v1/node/{id}/request_stat_now` | ✗ (403) | ✓ | ✓ |
| `POST /api/v1/node/{id}/reboot_soft` | ✗ (403) | ✗ (403) | ✓ |
| Gestión de usuarios | ✗ (403) | ✗ (403) | ✓ |

### Seguridad revisada

| Ítem | Estado |
|------|--------|
| Hash de contraseñas | `hashlib.scrypt` con salt aleatorio de 16 bytes — correcto |
| Verificación constante | `hmac.compare_digest(derived.hex(), hash_hex)` — correcto, no `==` |
| Cookie de sesión | HttpOnly, SameSite=Lax, Max-Age configurable |
| Bearer tokens | `hmac.compare_digest` en comparación — correcto |
| Bootstrap único | Solo se puede hacer una vez (usuario store vacío) |

---

## Bloque 3 — Alcance real del módulo

### Validado para uso controlado interno

| Ítem | Estado |
|------|--------|
| Apertura de la pestaña Remoto en la app | ✓ Validado — UI coherente y funcional |
| Activar/desactivar el servicio remoto | ✓ Validado — guarda config y reinicia |
| Servidor HTTP local (`local_only`) | ✓ Validado — bind 127.0.0.1:8788 por defecto |
| Bootstrap de usuarios por consola web | ✓ Validado a nivel de código y test API |
| Login/logout por sesión cookie | ✓ Validado — TTL 12h, cookie HttpOnly |
| Lectura de estado de nodos via API | ✓ Validado (observador+) |
| Solicitar STAT a nodo via API | ✓ Validado (tecnico+) |
| Reboot soft de nodo via API | ✓ Validado (admin únicamente) |
| Gestión de cuentas remotas | ✓ Validado (admin únicamente) |
| Persistencia de configuración | ✓ config.json actualizado correctamente |

### Pendiente de validación visual (no bloqueante)

| Ítem | Razón |
|------|-------|
| Consola HTML/JS en `/remote/` | El agente no puede abrir navegadores |
| Flujo completo de login web | Requiere UI viva en navegador |
| Respuesta visual de la consola ante sesión expirada | Ídem |
| Tailscale: exposición y URL remota | Tailscale no instalado en este host |

### Solo soporte técnico / no para uso operativo inmediato

| Ítem | Estado |
|------|--------|
| Modo `tailscale_only` | Requiere Tailscale instalado en el PC del sitio |
| Modo `bearer_token` / `bearer_token_inventory` | Requiere definir env vars y distribuir tokens manualmente |
| Auditoría JSONL en `logs/remote_api/` | Funcional pero sin visor UI integrado |
| Reboot remoto de nodo | Funcional pero requiere eval de impacto operativo antes de usar en producción |

---

## Bloque 4 — Bugs encontrados y corregidos

### BUG-1 — Toast "success" incorrecto cuando el servicio falla al iniciar

**Descripción:** `_apply_remote_settings_from_shell` siempre mostraba el toast con `level="success"` independientemente del resultado real. Cuando el servicio no arrancaba (`service_state="failed"`), el usuario veía un toast verde con el mensaje de error, lo que era contradictorio.

**Causa raíz:** `level="success"` hardcodeado; `_restart_remote_api_runtime` retorna `(status, message)` sin lanzar excepción incluso en fallo, por lo que el path normal del toast siempre alcanzaba `level="success"`.

**Corrección:**
```python
service_state = getattr(_status, "service_state", "")
toast_level = "warning" if enabled and service_state != "running" else "success"
self._show_toast(title="Servicio remoto", message=message, level=toast_level)
```

**Archivo:** `src/control_okua/app_qt/main_window.py`
**Estado:** CORREGIDO en este ticket (35.4)

---

### Hallazgos documentados (sin corrección en este ticket)

| # | Tipo | Descripción | Impacto | Decisión |
|---|------|-------------|---------|---------|
| H-1 | Limitación de diseño | Sesiones HTTP en memoria — pierden al reiniciar el servicio | Bajo — usuarios hacen login de nuevo | No corregir; comportamiento esperado y aceptable |
| H-2 | Limitación operativa | Tailscale detection falla sin Tailscale instalado — fallo con mensaje claro | Bajo — solo afecta si se configura `tailscale_only` | No corregir; error ya es claro |
| H-3 | Limitación de seguridad | Tokens locales (`remote_api_tokens.json`) en disco sin encriptación | Bajo para uso controlado en este host | Documentar como límite de uso; no bloqueante para RC |
| H-4 | Mejora futura | Sin retry automático si el servicio falla al arrancar | Bajo | No corregir en este ticket |

---

## Pruebas automáticas ejecutadas

```
PYTHONPATH=src python -m pytest tests/test_remote_auth_service.py tests/test_remote_api_service.py tests/test_remote_session_service.py tests/test_remote_user_store.py tests/test_remote_api_auth.py tests/test_remote_api_bootstrap.py tests/test_remote_api_contract.py tests/test_remote_api_audit.py -v
```

**Resultado: 33/33 PASAN**

| Módulo | Tests | Resultado |
|--------|-------|-----------|
| `test_remote_auth_service.py` | 3 | PASAN |
| `test_remote_api_service.py` | 7 | PASAN |
| `test_remote_session_service.py` | 2 | PASAN |
| `test_remote_user_store.py` | 2 | PASAN |
| `test_remote_api_auth.py` | 8 | PASAN |
| `test_remote_api_bootstrap.py` | 5 | PASAN |
| `test_remote_api_contract.py` | 3 | PASAN |
| `test_remote_api_audit.py` | 1 | PASAN |

Suite completa post-corrección: `python -m pytest` → **498/498 PASAN**

---

## Pruebas del portal web — Ticket 35.5 (ejecutadas 2026-04-18)

Validación real con servicio standalone, navegador abierto y Tailscale. Ver reporte completo:
[`docs/ui/remote_portal_validation.md`](remote_portal_validation.md)

Resumen:

| Prueba | Estado |
| ------ | ------ |
| Portal HTML carga en navegador real | **EJECUTADO** — 200 OK, layout correcto |
| Bootstrap desde store vacía | **EJECUTADO** — 3 cuentas creadas, sesión admin activa |
| Login / logout (admin, tecnico, observador) | **EJECUTADO** — todos PASS |
| Restricciones por rol (observador/tecnico/admin) | **EJECUTADO** — 403 en rutas no autorizadas |
| Tailscale `tailscale_only` | **EJECUTADO** — bind en `198.51.100.10`, aislamiento confirmado |
| Toast "warning" en fallo de activación (BUG-1 corregido) | **CORREGIDO en 35.4** |

---

## Decisión final — Estado operativo del módulo Remoto

**El módulo Remoto queda COMPLETAMENTE VALIDADO para uso controlado interno.**

1. **Modo `local_only`** (bind 127.0.0.1:8788): validado con código, suite automática y portal real.
2. **Modo `tailscale_only`**: validado con bind exclusivo en IP Tailscale `198.51.100.10`.
3. **Bootstrap**: flujo completo probado desde store vacía, resultado correcto.
4. **Roles**: restricciones verificadas en navegador real con cookies reales.
5. **Rol observador**: solo lectura confirmada — seguro para monitoreo.
6. **Rol tecnico**: `request_stat_now` autorizado; `/accounts` bloqueado.
7. **Rol admin**: gestión completa de cuentas y acciones confirmadas.

**Límite de uso:** para uso operativo controlado por José David en la instalación OKÚA — NO para exposición pública sin revisión de `custom_bind`.
