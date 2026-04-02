# Consola remota móvil/web mínima v1 (Ticket 31.0)

## Propósito

Congelar el alcance funcional, la arquitectura mínima y la estrategia UX de la primera consola remota que consumirá la API del servicio remoto local ya existente en CKv2.

Este subticket define:

- qué forma tomará la primera consola remota,
- cómo se desplegará,
- qué vistas mínimas tendrá,
- cómo se comportará por rol,
- cómo actualizará datos,
- y qué partes del roadmap quedan explícitamente fuera.

Este documento no implementa todavía la consola completa. No cambia el contrato remoto de Ticket 29 ni la matriz de roles de Ticket 30.

## Base real sobre la que se apoya

La consola v1 se diseña sobre capacidades ya existentes y publicadas:

- servicio remoto local del sitio,
- API HTTP/JSON local,
- autorización real por rol,
- auditoría JSONL,
- endpoints actualmente disponibles:
  - `GET /api/v1/health`
  - `GET /api/v1/runtime/summary`
  - `GET /api/v1/nodes`
  - `GET /api/v1/nodes/{node_id}`
  - `POST /api/v1/nodes/{node_id}/actions/request-stat-now`
  - `POST /api/v1/nodes/{node_id}/actions/reboot`
- roles vigentes:
  - `observador`
  - `tecnico`
  - `admin`

Restricción estructural:

- la consola es solo una superficie consumidora de esa API;
- no redefine dominio;
- no habla directo con nodos;
- no duplica `SessionController`, `NodeRegistry`, `ControlTransactionService` ni `CmdService`;
- y no sustituye al servidor OTA.

## Decisión arquitectónica congelada

La primera consola remota será una consola web responsiva mínima, usable desde navegador móvil o desktop, sin app nativa.

### Forma de despliegue elegida

Se congela como recomendación técnica para 31.1:

- frontend estático muy liviano,
- servido por el mismo host local del sitio,
- idealmente desde el mismo proceso/servicio remoto que hoy expone `/api/v1`,
- accesible desde navegador del celular o laptop por LAN/Tailscale.

### Razón técnica

Esta forma se elige porque:

- evita abrir un segundo servicio HTTP innecesario,
- evita CORS y complejidad de same-origin,
- simplifica despliegue en el PC del sitio,
- reduce moving parts para soporte de campo,
- permite una implementación sin framework pesado,
- y es suficiente para una consola operativa mínima.

Queda desaconsejado en v1:

- app móvil nativa,
- frontend con build pipeline complejo,
- SPA grande con framework pesado,
- despliegue separado que obligue a configurar otro proceso o reverse proxy.

## Superficie objetivo

La superficie objetivo de v1 es:

- navegador móvil moderno,
- layout responsivo pensado primero para celular en orientación vertical,
- legible también en desktop,
- servido por el host del sitio,
- consumido remotamente vía Tailscale o LAN según el entorno.

La consola v1 no busca reemplazar la UI local operator-first. Busca ofrecer una superficie remota mínima, robusta y entendible para consulta y dos acciones curadas.

## Arquitectura mínima propuesta

```text
Navegador móvil/desktop
    -> consola web estática mínima
    -> mismo host/proceso del servicio remoto local
        -> /api/v1/*
        -> runtime real de CKv2
```

Dirección recomendada para 31.1:

- archivos estáticos simples: `html + css + javascript`,
- `fetch()` contra la API existente,
- sin bundler obligatorio,
- sin dependencia runtime de Node.js en el sitio,
- sin backend extra de frontend.

## Vistas mínimas congeladas

La v1 mínima debe tener estas vistas o secciones:

### 1. Vista de salud / resumen

Objetivo:

- confirmar que el host responde,
- mostrar si la sesión está `idle` o `running`,
- mostrar si el control-plane está disponible,
- y mostrar un resumen compacto del estado operativo general.

Datos fuente:

- `GET /api/v1/health`
- `GET /api/v1/runtime/summary`

Contenido mínimo:

- estado del gateway,
- estado de sesión,
- perfil activo si existe,
- backend activo,
- disponibilidad de control-plane,
- totales de nodos si existen,
- mensaje técnico de sesión si aplica.

### 2. Lista de nodos

Objetivo:

- ver el conjunto actual de nodos observados por el runtime.

Datos fuente:

- `GET /api/v1/nodes`

Contenido mínimo por fila/tarjeta:

- `node_id`
- `label`
- `box_label`
- `status`
- `health_summary`
- `last_seen_age_s`
- `pps_evt`
- `pps_stat`
- `fw_version`
- `control_plane.resolution_status`

La v1 no necesita tabla compleja. En móvil puede resolverse mejor como lista de tarjetas compactas.

### 3. Detalle de nodo

Objetivo:

- inspeccionar un nodo concreto con mayor nivel técnico,
- mostrar claramente si está en condición accionable o no.

Datos fuente:

- `GET /api/v1/nodes/{node_id}`

Contenido mínimo:

- cabecera con `node_id`, `label`, `box_label`, `status`,
- bloque runtime,
- bloque OTA solo informativo,
- bloque control-plane,
- bloque de acciones remotas curadas.

### 4. Estado de autenticación/autorización

Objetivo:

- hacer visible al operador si el token no fue aceptado,
- si el rol no alcanza,
- o si la operación está fuera de permiso.

Estados mínimos a cubrir:

- `401 unauthorized`
- `403 forbidden`
- token ausente,
- token inválido,
- rol insuficiente.

### 5. Estado `idle` y estado de control-plane no disponible

La consola v1 debe representar explícitamente:

- sesión `idle`,
- control-plane no disponible,
- nodo no resoluble,
- nodo no encontrado,
- y errores remotos operativos como `session_not_running`, `control_plane_unavailable` o `node_unresolved`.

No debe maquillar estos estados ni simular disponibilidad que el backend no reporta.

## Principios UX congelados

- No replicar la UI completa local de CKv2.
- No introducir mapa complejo en esta fase.
- No abrir branding final en esta fase.
- No mostrar acciones fuera del set curado actual.
- Priorizar legibilidad, robustez y claridad de estado antes que riqueza visual.
- Hacer evidente si una acción fue denegada por rol versus fallida por condición operativa.
- Mantener navegación simple, con muy pocos niveles.
- Optimizar para uso rápido desde celular, con textos claros y botones grandes solo donde hagan falta.

## Comportamiento por rol

La matriz de permisos sigue siendo la publicada en Ticket 30. La consola no la redefine; solo la representa.

### `observador`

Debe poder:

- ver salud/resumen,
- ver lista de nodos,
- ver detalle de nodo.

No debe poder:

- ejecutar `request-stat-now`,
- ejecutar `reboot`.

Representación UX recomendada:

- en v1, las acciones remotas deben aparecer bloqueadas o no mostrarse,
- pero si el frontend se equivoca, el backend sigue siendo la fuente de verdad y responderá `403`.

### `tecnico`

Debe poder:

- todo lo que ve `observador`,
- ejecutar `request-stat-now`.

No debe poder:

- ejecutar `reboot`.

Representación UX recomendada:

- `request-stat-now` visible y utilizable,
- `reboot` visible como restringido o ausente según el modo elegido de UI,
- cualquier `403` debe mostrarse como “acción no permitida para este rol”, no como error interno.

### `admin`

Debe poder:

- todo lo que ve `tecnico`,
- ejecutar `request-stat-now`,
- ejecutar `reboot`.

Incluso para `admin`, la consola v1 no debe mostrar:

- OTA remota,
- Firmware Manager remoto,
- campañas OTA,
- acciones F3 adicionales,
- controles de sesión.

## Regla de representación de acciones restringidas

Como la API actual no expone un endpoint extra de descubrimiento de rol, se congela una estrategia conservadora para 31.1:

- el frontend puede manejar un “role hint” local asociado al token configurado en la consola para decidir qué controles mostrar o bloquear;
- pero la fuente de verdad final sigue siendo el backend;
- toda respuesta `403 forbidden` debe tratarse como autoridad final, aunque la UI hubiera habilitado algo por error.

Recomendación concreta:

- para v1, preferir mostrar controles no permitidos en estado deshabilitado cuando eso ayude a explicar capacidades del rol;
- si eso complica demasiado la implementación mínima, se permite ocultarlos;
- en ambos casos, el backend sigue siendo la única autoridad real.

## Estrategia de actualización de datos

Se congela polling HTTP simple y controlado.

No se congelan para v1:

- WebSocket,
- SSE,
- canal push,
- streaming en vivo continuo.

### Recomendación mínima para 31.1

- vista de resumen: polling cada 3 a 5 segundos,
- lista de nodos: polling cada 3 a 5 segundos,
- detalle de nodo: polling cada 2 a 4 segundos mientras esté visible,
- pausa de polling cuando la pestaña no está visible si sale barato implementarlo,
- botón de refresh manual siempre disponible.

Razón:

- la API actual ya soporta lectura HTTP simple,
- la consola v1 no necesita complejidad de sincronización en tiempo real,
- y polling corto controlado es suficiente para una superficie operativa mínima.

## Manejo de errores mínimo esperado

La consola v1 debe diferenciar al menos:

- `401 unauthorized`
- `403 forbidden`
- `404 node_not_found`
- `409 session_not_running`
- `409 control_plane_unavailable`
- `409 node_unresolved`
- `502 command_failed`
- errores de red al host

Semántica UX mínima:

- `401` = token ausente o inválido,
- `403` = token válido pero rol insuficiente,
- `409` = permiso correcto, pero el runtime real no permite ejecutar ahora,
- `502` = la transacción fue intentada y falló operativamente.

Esto es importante para no mezclar “no autorizado” con “sistema disponible pero no accionable”.

## Exclusiones explícitas de la consola v1

La consola remota v1 no debe incluir:

- mapa operativo,
- overlay live complejo,
- branding final,
- visualización rica de topología,
- dashboards decorativos,
- OTA remota,
- Firmware Manager remoto,
- campañas OTA,
- browsing remoto de logs,
- acciones de sesión,
- edición remota de configuración,
- acciones F3 no curadas,
- autenticación web compleja,
- sistema de cuentas,
- WebSocket/SSE,
- framework frontend pesado por conveniencia.

## Frontera con Ticket 32, Ticket 33 y Ticket 34

### Ticket 32 — mapa operativo v1

Queda fuera de esta fase:

- representación espacial,
- mapa por cajas o layout operativo,
- navegación visual por ubicación.

31.0 solo congela consola textual/operativa mínima.

### Ticket 33 — overlay live

Queda fuera:

- capa de actualización más rica,
- eventos visuales en vivo,
- overlays o indicadores dinámicos avanzados,
- optimizaciones de realtime.

31.0 se queda en polling simple.

### Ticket 34 — branding y acabado visual

Queda fuera:

- identidad visual final,
- refinamiento gráfico,
- diseño de producto más pulido,
- sistema visual definitivo.

31.0 prioriza robustez funcional y claridad operativa.

## Recomendación técnica para 31.1

La implementación recomendada para 31.1 es:

- frontend estático mínimo servido por el mismo servicio remoto,
- una sola página simple o navegación muy liviana,
- `fetch()` a la API ya existente,
- polling simple,
- layout responsivo mobile-first,
- sin framework pesado,
- sin bundler obligatorio,
- sin endpoints nuevos si no son estrictamente necesarios.

Estructura mínima razonable para 31.1:

- pantalla inicial de conexión/token,
- vista resumen,
- vista lista de nodos,
- vista detalle de nodo,
- acciones curadas en detalle de nodo según rol,
- manejo claro de `401`, `403` y `409`.

## Cierre

La consola remota v1 queda congelada como una consola web responsiva mínima, servida por el host local del sitio, consumiendo la API ya existente y sin absorber todavía mapa, overlay live ni branding final.

Su propósito no es replicar toda la app local, sino ofrecer una superficie remota ligera, confiable y segura para:

- leer salud/resumen,
- ver nodos,
- ver detalle técnico por nodo,
- y ejecutar solo las acciones ya curadas por el backend según rol.
