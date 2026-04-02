# Roles remotos y autorización v1 (Ticket 30.0)

## Propósito

Congelar la matriz de roles y el contrato de autorización remota v1 sobre la API local ya existente del Ticket 29.

Este documento define:

- qué roles remotos existirán en v1,
- qué endpoints actuales podrá usar cada rol,
- qué acciones quedan prohibidas o reservadas,
- y cómo deberá evolucionar la auth actual de token único hacia autorización por rol en Ticket 30.1.

Este subticket no implementa enforcement en código. Congela el contrato para implementarlo después sin reabrir alcance.

## Base real actual

La base ya implementada en 29.1 es:

- auth mínima por bearer token técnico único,
- auditoría JSONL,
- `GET /api/v1/health`,
- `GET /api/v1/runtime/summary`,
- `GET /api/v1/nodes`,
- `GET /api/v1/nodes/{node_id}`,
- `POST /api/v1/nodes/{node_id}/actions/request-stat-now`,
- `POST /api/v1/nodes/{node_id}/actions/reboot`.

La API actual:

- consume `SessionController`,
- delega acciones al pipeline existente de control-plane,
- no habla directo con nodos,
- no duplica `CmdService`,
- no duplica `ControlTransactionService`,
- no duplica `NodeRegistry`,
- y no sustituye al servidor OTA local.

## Relación con el estado actual de 29.1

El backend publicado en 29.1 todavía usa un bearer token técnico único sin noción de rol.

Por tanto:

- el estado actual publicado es funcionalmente equivalente a un acceso técnico único con privilegio total sobre los endpoints hoy expuestos,
- pero eso es un estado transitorio de implementación,
- y no debe tomarse como el contrato final de autorización v1.

Este documento congela el contrato objetivo para Ticket 30.1:

- 29.1 = autenticación mínima ya operativa,
- 30.0 = matriz de roles y autorización congeladas,
- 30.1 = implementación real de esa autorización por rol.

## Principios de autorización v1

- Separar autenticación de autorización.
- Mantener `default deny` para todo endpoint o acción que no esté concedido explícitamente.
- Mantener `least privilege`: observador solo lectura; técnico solo acciones diagnósticas mínimas; admin operaciones críticas curadas.
- La autorización no reemplaza precondiciones operativas: una acción permitida por rol sigue fallando si no hay sesión `running`, control-plane disponible o nodo resoluble.
- Ningún rol obtiene un canal raw hacia nodos ni un bypass del runtime existente.
- Ningún rol convierte la API remota en espejo completo de la UI operator-first.

## Roles v1 congelados

### `observador`

Perfil remoto de inspección.

Capacidades:

- lectura de salud del host,
- lectura de resumen de runtime,
- lectura de lista de nodos,
- lectura de detalle por nodo.

Límites:

- no ejecuta acciones F3,
- no dispara reboot,
- no gestiona sesión,
- no gestiona OTA,
- no administra firmware,
- no consulta logs por API en esta fase.

### `tecnico`

Perfil remoto de diagnóstico operativo curado.

Capacidades:

- toda la lectura del rol observador,
- acción remota `request-stat-now`.

Límites:

- no ejecuta `reboot` remoto en v1,
- no dispara OTA,
- no gestiona campañas,
- no administra artifacts ni Firmware Manager,
- no obtiene comandos F3 arbitrarios.

Decisión clave:

`reboot` no se concede a técnico en v1 porque:

- es una acción disruptiva,
- puede afectar validación física, continuidad operativa y troubleshooting remoto,
- y el backend actual todavía no tiene una capa superior de aprobación/confirmación por rol.

Por eso, en v1 el rol técnico se limita a diagnóstico remoto y no a recuperación disruptiva.

### `admin`

Perfil remoto de operación crítica curada.

Capacidades:

- toda la lectura del rol técnico,
- `request-stat-now`,
- `reboot`.

Límites:

- tampoco obtiene un `send_raw_cmd`,
- tampoco obtiene edición remota de config,
- tampoco obtiene OTA/fleet management remoto en esta fase,
- tampoco obtiene browsing remoto de logs en esta fase,
- y no recibe endpoints que aún no existan.

## Matriz de permisos por endpoint actual

| Endpoint | Tipo | Observador | Técnico | Admin | Requiere control-plane disponible | Requiere sesión `running` | Notas |
|---|---|---|---|---|---|---|---|
| `GET /api/v1/health` | lectura | permitido | permitido | permitido | no | no | Siempre debe responder si el gateway vive; reporta indisponibilidad real de runtime/control-plane sin inventar salud. |
| `GET /api/v1/runtime/summary` | lectura | permitido | permitido | permitido | no | no | Puede devolver runtime vacío o control-plane no disponible si la sesión no está activa. |
| `GET /api/v1/nodes` | lectura | permitido | permitido | permitido | no | no | La lista puede ser vacía si no hay sesión/nodos visibles. |
| `GET /api/v1/nodes/{node_id}` | lectura | permitido | permitido | permitido | no | no | Si el nodo no existe en snapshots actuales, devuelve `404 node_not_found`. |
| `POST /api/v1/nodes/{node_id}/actions/request-stat-now` | acción | denegado | permitido | permitido | sí | sí | Acción diagnóstica curada; además requiere nodo existente y resoluble. |
| `POST /api/v1/nodes/{node_id}/actions/reboot` | acción | denegado | denegado | permitido | sí | sí | Acción disruptiva reservada a admin en v1. |

## Lectura versus acción

Se congela esta separación:

- lectura = inspección del estado actual ya calculado por CKv2,
- acción = operación remota que delega al control-plane F3 y puede cambiar comportamiento del nodo.

En v1:

- todos los endpoints `GET` actuales son de lectura,
- todos los endpoints `POST` actuales son de acción,
- y ninguna acción queda disponible para observador.

## Acciones explícitamente prohibidas por rol

### Observador

Prohibido:

- toda acción `POST`,
- cualquier reboot remoto,
- cualquier futura acción F3,
- cualquier acción OTA,
- cualquier browsing remoto de logs mientras no exista endpoint explícito,
- cualquier gestión de sesión.

### Técnico

Prohibido:

- `reboot`,
- cualquier futura acción OTA,
- campañas OTA,
- administración remota de firmware/artifacts,
- acciones de sesión,
- comandos F3 no curados explícitamente,
- endpoints raw o genéricos de comando.

### Admin

Prohibido en esta fase:

- `send_raw_cmd`,
- edición remota de configuración,
- `start_session`, `stop_session`, `reload_config`,
- OTA remota,
- Firmware Manager remoto,
- campañas OTA,
- browsing remoto de logs,
- cualquier endpoint todavía no implementado.

Punto importante:

`admin` en v1 no significa “acceso ilimitado”. Significa “máximo privilegio dentro del set curado actual”.

## Capacidades futuras y reserva por rol

### OTA remota

Estado actual:

- fuera de alcance de la API remota v1 operativa.

Reserva:

- futura exposición reservada inicialmente a `admin`.

Razón:

- involucra rollout, impacto de firmware, downgrade, observabilidad post-boot y coordinación fuerte con runbooks OTA.

### Firmware Manager remoto

Estado actual:

- fuera de alcance.

Reserva:

- `admin` solamente en una fase futura explícita.

Razón:

- toca catálogo, artifacts, ingestión, borrado y metadatos operativos.

### Campañas OTA

Estado actual:

- fuera de alcance.

Reserva:

- `admin` solamente en una fase futura explícita.

Razón:

- son operaciones de fleet management, no simples acciones por nodo.

### Acciones F3 adicionales

Estado actual:

- fuera de alcance remoto actual aunque existan app-side en otros contextos.

Clasificación futura congelada:

- `PING`: candidato a `tecnico` y `admin` si se expone más adelante como acción diagnóstica de muy bajo riesgo.
- `SET_STAT_RATE`: reservado inicialmente a `admin`.
- `SET_THROTTLE`: reservado inicialmente a `admin`.
- `OTA_CHECK_NOW`: reservado inicialmente a `admin`.
- `reset_calibration`: reservado inicialmente a `admin`, y además bloqueado hasta tener contrato y validación propios.

Regla:

- ninguna de estas acciones debe abrirse en 30.1 por inercia; cada una necesita decisión explícita de exposición remota.

### Browsing remoto de logs

Estado actual:

- fuera de alcance.

Reserva:

- si aparece en una fase futura, lo razonable será lectura para `observador`, `tecnico` y `admin`, pero con contrato aparte y filtrado explícito.

Hoy no se congela endpoint alguno para logs.

### Acciones de sesión

Estado actual:

- fuera de alcance.

Reserva:

- si algún día se evalúan `start_session`, `stop_session` o equivalentes remotos, deben arrancar como `admin` solamente.

Razón:

- afectan el runtime global del sitio, no solo un nodo.

## Contrato mínimo de autorización v1 para Ticket 30.1

Se congela una solución simple y mantenible:

- múltiples bearer tokens opacos,
- definidos localmente en el host del sitio,
- cada token mapeado a un rol fijo,
- sin JWT,
- sin claims firmados embebidos,
- sin refresh tokens,
- sin base de usuarios,
- sin login web,
- sin sesiones de usuario.

### Decisión concreta

Ticket 30.1 debe implementar un inventario local de tokens por rol.

Modelo conceptual:

- un token opaco `->` un rol fijo,
- opcionalmente un label técnico local para auditoría,
- y enforcement por endpoint/acción contra la matriz de este documento.

Ejemplo conceptual de dirección, no contrato final de config:

```json
"remote_api": {
  "auth_mode": "bearer_token_inventory",
  "tokens": [
    { "env_var": "CKV2_REMOTE_API_OBSERVER_TOKEN", "role": "observador", "label": "observer-main" },
    { "env_var": "CKV2_REMOTE_API_TECH_TOKEN", "role": "tecnico", "label": "tech-main" },
    { "env_var": "CKV2_REMOTE_API_ADMIN_TOKEN", "role": "admin", "label": "admin-main" }
  ]
}
```

La forma exacta de config podrá ajustarse en 30.1, pero se congela la decisión de arquitectura:

- no rol embebido dentro del token,
- no decodificación de claims,
- no dependencia de proveedor externo de identidad,
- y resolución local simple token `->` rol.

## Reglas de auditoría cuando exista autorización por rol

Aunque 30.0 no implementa auditoría nueva, se congela que 30.1 deberá extender la auditoría existente para incluir además:

- `role`
- `authorization_result`

Sin romper los campos ya congelados en 29.0.

## Frontera con Ticket 31

Ticket 31 no debe redefinir esta matriz de roles.

Ticket 31 podrá:

- construir consola/superficie remota,
- mejorar UX,
- presentar permisos de forma legible,
- y consumir la autorización ya implementada en 30.1.

Pero Ticket 31 no debe:

- cambiar por su cuenta qué puede hacer cada rol,
- subir privilegios implícitos,
- ni introducir un modelo alterno de roles sin versionar el contrato.

## Cierre

La matriz v1 queda congelada así:

- `observador` = solo lectura,
- `tecnico` = lectura + `request-stat-now`,
- `admin` = lectura + `request-stat-now` + `reboot`.

Y queda congelado que la evolución de 30.1 debe ir por bearer tokens opacos mapeados localmente a rol, sin abrir todavía un sistema completo de cuentas o identidad remota.
