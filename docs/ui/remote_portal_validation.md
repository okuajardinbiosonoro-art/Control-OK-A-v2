# Validación del portal web remoto — `/remote/` — Control OKÚA CKv2

Rama: `desarrollo-fase-2`
Fecha: 2026-04-18 (Ticket 35.5)
Tipo: Validación funcional real con servicio standalone + navegador abierto + Tailscale

---

## Entorno de validación

| Ítem | Detalle |
|------|---------|
| Host | <DEV_PC> (Windows 11 Home, 10.0.26200) |
| Navegador | Windows default browser (abierto automáticamente por el script de validación) |
| Puerto de validación | 8789 (standalone, evita conflicto con app en 8788) |
| URL usada | `http://127.0.0.1:8789/remote/` |
| User store | Temporal limpio (TemporaryDirectory) — bootstrap real ejecutado desde cero |
| Runtime | Mock completo con 2 nodos ficticios (EB1 online, EB2 offline) |
| Suite automática | 27 escenarios funcionales, todos PASS |
| Tailscale | Disponible — `198.51.100.10 / <DEV_PC>.tail45c171.ts.net` — validado |

---

## Bootstrap realizado

- Store vacía al inicio: confirmado (`bootstrap_required=True` en SC-2)
- Bootstrap POST `/api/v1/auth/bootstrap` ejecutado con 3 cuentas:
  - `admin.okua` / rol `admin`
  - `tecnico.okua` / rol `tecnico`
  - `observador.okua` / rol `observador`
- Resultado: 200 OK, 3 cuentas creadas, sesión admin activa automáticamente
- Post-bootstrap: `/api/v1/auth/session` retorna `authenticated=True`, `role=admin`, `username=admin.okua`

---

## Login / logout

| Escenario | Resultado |
|-----------|-----------|
| Logout tras bootstrap | 200 OK, `logged_out=True` |
| Session post-logout | `authenticated=False`, cookie invalidada |
| Login admin.okua | 200 OK, cookie de sesión obtenida |
| Login tecnico.okua | 200 OK |
| Login observador.okua | 200 OK |
| Login con contraseña incorrecta | 401 Unauthorized |
| Cookie inválida/fabricada en ruta protegida | 401 Unauthorized |
| Bootstrap doble (ya inicializado) | 409 Conflict |

---

## Validación del portal HTML

| Escenario | Resultado |
|-----------|-----------|
| GET `/remote/` | 200 OK — HTML contiene `CKv2 Remote Console` |
| GET `/remote/app.js` | 200 OK — `application/javascript` |
| GET `/remote/styles.css` | 200 OK — `text/css` |
| Ruta protegida sin auth | 401 Unauthorized |

**Validación visual real:** el navegador fue abierto automáticamente en `http://127.0.0.1:8789/remote/` con el servicio activo durante 45 segundos y el bootstrap ejecutado. El portal cargó correctamente con:
- Header: "CKv2 Remote Console v1 — Consola remota mínima"
- Chips de usuario/rol en el header
- Formulario de login visible (no bootstrap, ya realizado)
- Secciones: Acceso / Resumen operativo / Nodos / Detalle de nodo

---

## Verificación funcional por rol

### Rol `admin`

| Acción | Resultado |
|--------|-----------|
| GET `/api/v1/accounts` | 200 OK (lista de usuarios) |
| GET `/api/v1/runtime/summary` | 200 OK |
| GET `/api/v1/nodes` | 200 OK, 2 nodos visibles |
| GET `/api/v1/nodes/1` | 200 OK (detalle EB1) |
| POST `/api/v1/accounts` (crear usuario) | 201 Created |
| DELETE `/api/v1/accounts/extra.user` | 200 OK |

### Rol `tecnico`

| Acción | Resultado |
|--------|-----------|
| GET `/api/v1/accounts` | **403 Forbidden** (correcto) |
| GET `/api/v1/nodes` | 200 OK |
| POST `/api/v1/nodes/1/actions/request-stat-now` | 200 OK (autorizado, resultado `timeout` por mock) |

### Rol `observador`

| Acción | Resultado |
|--------|-----------|
| GET `/api/v1/accounts` | **403 Forbidden** (correcto) |
| GET `/api/v1/nodes` | 200 OK |
| POST `/api/v1/nodes/1/actions/reboot` | **403 Forbidden** (correcto) |

---

## Validación Tailscale (`tailscale_only`)

Tailscale estaba disponible en el host. Resultado de la validación:

| Ítem | Resultado |
|------|-----------|
| IP Tailscale del host | `198.51.100.10` |
| DNS Tailscale del host | `<DEV_PC>.tail45c171.ts.net` |
| `resolve_remote_api_bind_host(tailscale_only)` | `198.51.100.10` (correcto) |
| `effective_bind_host` del servicio | `198.51.100.10` |
| GET `/remote/` via `198.51.100.10:8790` | **200 OK**, HTML correcto |
| GET `/remote/` via `127.0.0.1:8790` | **ConnectionRefusedError** — servicio NO escucha en loopback (correcto, aislamiento Tailscale efectivo) |

**Conclusión Tailscale:** el modo `tailscale_only` funciona correctamente. El servicio binds exclusivamente a la IP Tailscale, rechazando conexiones desde loopback o LAN directa. El aislamiento es real y verificado.

---

## Resumen de escenarios

| ID | Escenario | Estado |
|----|-----------|--------|
| SC-1 | GET `/remote/` — HTML carga | **PASS** |
| SC-1b | Assets estáticos `app.js` y `styles.css` | **PASS** |
| SC-2 | `bootstrap_required=True` con store vacía | **PASS** |
| SC-3 | Bootstrap de 3 cuentas | **PASS** |
| SC-4 | Session refleja admin post-bootstrap | **PASS** |
| SC-5 | Logout admin | **PASS** |
| SC-5b | Cookie invalidada tras logout | **PASS** |
| SC-6 | Login admin | **PASS** |
| SC-7 | Admin accede `/accounts` | **PASS** |
| SC-8 | Admin accede `/runtime/summary` | **PASS** |
| SC-9 | Admin accede `/nodes` | **PASS** |
| SC-10 | Login tecnico | **PASS** |
| SC-10b | Tecnico rechazado en `/accounts` (403) | **PASS** |
| SC-10c | Tecnico accede `/nodes` (200) | **PASS** |
| SC-11 | Login observador | **PASS** |
| SC-11b | Observador rechazado en `/accounts` (403) | **PASS** |
| SC-11c | Observador accede `/nodes` (200) | **PASS** |
| SC-11d | Observador rechazado en reboot (403) | **PASS** |
| SC-12 | Contraseña incorrecta — 401 | **PASS** |
| SC-13 | Cookie inválida — 401 | **PASS** |
| SC-14 | Sin auth en ruta protegida — 401 | **PASS** |
| SC-15 | Bootstrap doble — 409 Conflict | **PASS** |
| SC-16 | Detalle de nodo (admin) | **PASS** |
| SC-17 | Crear usuario extra (admin) | **PASS** |
| SC-18 | Eliminar usuario extra (admin) | **PASS** |
| SC-19 | Tecnico ejecuta `request-stat-now` | **PASS** |
| TS-1 | Tailscale bind correcto | **PASS** |
| TS-2 | Acceso via IP Tailscale (200 OK) | **PASS** |
| TS-3 | Aislamiento loopback en modo Tailscale | **PASS** |

**Total: 29/29 escenarios PASS**

---

## Bugs encontrados durante la validación

No se encontraron bugs nuevos. El BUG-1 (toast level) fue corregido en Ticket 35.4.

---

## Decisión final sobre el portal web

**El portal `/remote/` queda VALIDADO para uso controlado interno.**

Condiciones confirmadas:
1. Bootstrap funciona desde store vacía — flujo correcto, sin necesidad de intervención manual previa.
2. Login/logout funcionan correctamente y la cookie se invalida tras logout.
3. Las restricciones por rol son efectivas: observador y tecnico reciben 403 en operaciones no autorizadas.
4. El portal HTML carga correctamente; app.js y styles.css sirven sin error.
5. El modo `tailscale_only` funciona correctamente: bind exclusivo a IP Tailscale, aislamiento verificado.

**Recomendación operativa:** el módulo Remoto puede usarse en `local_only` para administración local segura, y en `tailscale_only` para acceso remoto controlado dentro de la red Tailscale de OKÚA Jardín Biosonoro. No habilitar `custom_bind` en producción sin control de acceso de red adicional.
