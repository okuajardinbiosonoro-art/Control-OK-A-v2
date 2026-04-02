# Servicio remoto local del sitio v1 (Ticket 29.0)

## Propósito

Congelar el contrato mínimo del servicio remoto local del sitio para CKv2 antes de implementar su backend real.

Este servicio v1 se define como una API/gateway local que corre en el PC del sitio y que:

- consume el runtime real ya existente de CKv2,
- expone lectura remota curada del estado operativo,
- expone un conjunto mínimo de acciones F3 curadas,
- exige autenticación técnica fuerte,
- y deja auditoría mínima por cada acción remota.

Este documento congela alcance y fronteras. No implementa todavía el servicio completo, no abre puertos reales y no introduce una consola nueva.

## Principios de diseño

- El servicio remoto no crea una segunda fuente de verdad: lee de `SessionController`, `NodeRegistry` y snapshots canónicos ya existentes.
- El servicio remoto no duplica `CmdService`, `ControlTransactionService`, `NodeRegistry` ni `OtaServerService`.
- El servicio remoto no habla directo con nodos por un protocolo paralelo ni abre una segunda implementación CMD/ACK fuera del pipeline actual.
- El servicio remoto es un gateway local del sitio; Tailscale o cualquier otro transporte remoto futuro son una capa de acceso, no una nueva capa de dominio.
- La API v1 es deliberadamente pequeña: primero lectura confiable y dos acciones curadas.
- Toda acción remota debe ser autenticada, auditable y correlacionable.

## Arquitectura de alto nivel

```text
Cliente remoto futuro (Ticket 30 / Ticket 31)
    -> red de acceso futura (por ejemplo Tailscale)
    -> servicio remoto local del sitio
    -> SessionController
         -> snapshots de sesión/runtime
         -> NodeRegistry y snapshots de nodos
         -> ControlPlaneRuntime
             -> ControlTransactionService
                 -> CmdService + AckListener
```

Separación explícita:

- `SessionController` sigue siendo la fachada de runtime real.
- El servicio remoto solo adapta HTTP/JSON + auth + auditoría.
- Toda acción remota delega al runtime y al pipeline de comando ya existente (`SessionController -> ControlPlaneRuntime -> ControlTransactionService -> CmdService`).
- El servidor OTA local existente sigue sirviendo `manifest.json` y bins OTA; no pasa a ser API general del sitio.

## Frontera de responsabilidades

### Lo que sí pertenece al servicio remoto v1

- exponer salud técnica del host CKv2,
- exponer resumen de runtime de sesión,
- exponer snapshots de nodos ya calculados por CKv2,
- ejecutar acciones F3 remotas curadas por `node_id`,
- validar auth técnica mínima,
- registrar auditoría remota mínima por request y por acción.

### Lo que sigue perteneciendo al servidor OTA existente

- servir `manifest.json` y `firmware.bin` por HTTP,
- publicar rollouts desde artifacts locales,
- resolver URLs OTA del rollout,
- mantener el árbol `artifacts/ota_publish/`,
- operar como backend técnico de distribución OTA, no como gateway general remoto.

### Lo que queda fuera de Ticket 29

- consola móvil o web,
- vista de mapa o layout final,
- roles/permisos completos por usuario,
- administración remota de catálogo de firmware,
- publicación remota de rollouts,
- campañas OTA remotas,
- browsing remoto de logs/sesiones,
- streaming en tiempo real,
- WebSockets/SSE,
- multi-tenant o multi-sitio,
- endurecimiento final de despliegue de red.

### Relación con Ticket 30 y Ticket 31

- Ticket 29 define y luego implementa el gateway local autenticado/auditado.
- Ticket 30 consumirá este contrato desde una superficie remota; no redefine dominio ni control-plane.
- Ticket 31 podrá construir una superficie más elaborada sobre el mismo contrato o una evolución compatible, pero no debe forzar a reabrir el núcleo v1 aquí.

## Auth mínima congelada para Ticket 29

Se congela una auth técnica única y fuerte, sin roles.

Esquema:

- `Authorization: Bearer <remote_api_token>`

Requisitos del token:

- token opaco único por sitio,
- generado fuera del repo,
- mínimo 32 bytes aleatorios,
- almacenado como secreto local del host,
- nunca embebido en el repo ni en artifacts.

Política v1:

- un solo token técnico da acceso al contrato completo v1,
- no hay roles por endpoint,
- no hay refresh token,
- no hay sesión de usuario,
- no hay cookies,
- no hay login UI.

Identidad mínima de actor:

- `actor_type = technical_token`
- `actor_id = remote_api_token:<fingerprint_corto>`

El fingerprint corto debe derivarse localmente del secreto real para auditoría y troubleshooting sin registrar el token completo.

## Auditoría mínima congelada

Toda request autenticada debe generar un evento auditable.

Campos mínimos:

- `ts_utc`
- `request_id`
- `actor_type`
- `actor_id`
- `origin_remote_addr`
- `origin_via`
- `http_method`
- `path`
- `action`
- `node_id`
- `result`
- `status_code`
- `session_state`
- `correlation.cmd_seq`
- `correlation.nonce`

Semántica mínima:

- `origin_via` distingue al menos `local_lan`, `tailscale` o `unknown`.
- `action` identifica la operación lógica, no solo el path. Ejemplos: `health.read`, `nodes.read`, `node.request_stat_now`, `node.reboot`.
- `result` debe ser compacto y legible: `ok`, `denied`, `invalid`, `unavailable`, `timeout`, `ack_matched`, `send_error`, etc.
- Cuando la acción use control-plane, la auditoría debe enlazar el resultado remoto con la correlación técnica existente (`cmd_seq`, `nonce` y estado final).

Persistencia mínima esperada:

- log apéndice local dedicado del servicio remoto,
- formato simple y estable, preferiblemente JSONL,
- separado del árbol OTA,
- sin reemplazar el recording de sesión existente.

## Fuente de verdad para la API

La API v1 debe mapear directamente a capacidades ya existentes:

- salud y estado de sesión desde `SessionController`,
- resumen de nodos desde `SessionController.get_node_registry_summary()`,
- nodos desde `SessionController.get_node_snapshots()`,
- detalle por nodo desde `SessionController.get_node_snapshot(node_id)` y `SessionController.get_control_plane_node_snapshot(node_id)`,
- acciones F3 por `SessionController.send_control_request_stat_now(...)` y `SessionController.send_control_reboot_soft(...)`.

Restricción clave:

- si la sesión no está `running`, la API puede seguir respondiendo salud técnica, pero no debe fingir runtime activo ni permitir acciones F3.
- aun con sesión `running`, la API remota no envía paquetes a nodos por fuera del pipeline existente; solo delega sobre el runtime integrado de CKv2.

## Contrato HTTP/JSON v1

Convenciones comunes:

- prefijo base: `/api/v1`
- contenido: `application/json`
- toda respuesta incluye `ok`
- toda respuesta incluye `meta.request_id`
- timestamps serializados en UTC ISO-8601 cuando apliquen

Forma general exitosa:

```json
{
  "ok": true,
  "data": {},
  "meta": {
    "request_id": "8f7f6d68f0b7460f",
    "api_version": "v1"
  }
}
```

Forma general de error:

```json
{
  "ok": false,
  "error": {
    "code": "control_plane_unavailable",
    "message": "Control-plane requiere sesion UDP/LAB running."
  },
  "meta": {
    "request_id": "8f7f6d68f0b7460f",
    "api_version": "v1"
  }
}
```

## Endpoints mínimos de lectura

### `GET /api/v1/health`

Objetivo:

- comprobar que el proceso host responde,
- verificar si CKv2 tiene sesión activa,
- verificar si el control-plane remoto es utilizable.

Respuesta `200`:

```json
{
  "ok": true,
  "data": {
    "service": "ckv2-remote-site-service",
    "status": "ok",
    "session": {
      "state": "running",
      "profile_id": "udp_jardin",
      "mode": "udp",
      "backend_kind": "udp"
    },
    "control_plane": {
      "available": true,
      "listener_active": true
    }
  },
  "meta": {
    "request_id": "req_01",
    "api_version": "v1"
  }
}
```

Notas:

- `status = ok` significa que el gateway responde, no que todos los nodos estén sanos.
- si la sesión no está corriendo, la respuesta sigue siendo `200` con `control_plane.available = false`.

### `GET /api/v1/runtime/summary`

Objetivo:

- exponer un resumen técnico compacto del runtime actual sin listar nodo por nodo.

Respuesta `200`:

```json
{
  "ok": true,
  "data": {
    "session": {
      "state": "running",
      "profile_id": "udp_jardin",
      "mode": "udp",
      "backend_kind": "udp",
      "message": "Sesion iniciada: UDP backend activo."
    },
    "nodes": {
      "total_nodes": 3,
      "online_count": 2,
      "degraded_count": 1,
      "offline_count": 0,
      "calibrating_count": 0,
      "total_pps_evt": 24.0,
      "total_pps_stat": 3.0
    },
    "control_plane": {
      "available": true,
      "listener_active": true,
      "ack_port": 5008,
      "pending_count": 0,
      "commands_sent_total": 5,
      "command_retry_total": 1,
      "command_ack_total": 4,
      "command_timeout_total": 0,
      "invalid_ack_total": 0,
      "unmatched_ack_total": 0
    }
  },
  "meta": {
    "request_id": "req_02",
    "api_version": "v1"
  }
}
```

Notas:

- este endpoint resume; no reemplaza `GET /nodes`.
- no debe recalcular dominio fuera de `SessionController`.

### `GET /api/v1/nodes`

Objetivo:

- devolver la lista canónica de nodos observados por el runtime actual.

Respuesta `200`:

```json
{
  "ok": true,
  "data": {
    "nodes": [
      {
        "node_id": 11,
        "label": "EB3",
        "box_label": "Caja 3",
        "status": "online",
        "health_summary": "trafico reciente y stat estable",
        "last_seen_age_s": 0.4,
        "last_stat_age_s": 0.9,
        "pps_evt": 8.0,
        "pps_stat": 1.0,
        "loss_evt_pct": 0.0,
        "loss_stat_pct": 0.0,
        "rssi_dbm": -57,
        "last_uptime_s": 913,
        "fw_version": "1.0",
        "ota": {
          "state_key": "idle",
          "error_key": "none",
          "pending_reboot": false,
          "pending_verify": false,
          "health_confirmed": true
        },
        "control_plane": {
          "resolved_ip": "192.168.88.31",
          "resolution_status": "resolved",
          "transaction_active": false,
          "last_command_name": "REQUEST_STAT_NOW",
          "last_final_status": "ack_matched",
          "last_tx_finished_at": "2026-04-02T20:11:43.551Z",
          "message": "Ultimo resultado de control-plane: ack_matched."
        }
      }
    ]
  },
  "meta": {
    "request_id": "req_03",
    "api_version": "v1"
  }
}
```

Notas:

- la lista solo contiene nodos realmente conocidos por el runtime actual.
- `box_label` es una vista derivada de la política existente `node_id -> caja`; no introduce un nuevo dominio.
- v1 no exige ordenar por otra cosa que `node_id`.

### `GET /api/v1/nodes/{node_id}`

Objetivo:

- devolver detalle técnico de un nodo concreto ya conocido por el runtime.

Respuesta `200`:

```json
{
  "ok": true,
  "data": {
    "node_id": 11,
    "label": "EB3",
    "box_label": "Caja 3",
    "runtime": {
      "status": "online",
      "health_summary": "trafico reciente y stat estable",
      "status_reason": "stat reciente y sin perdida relevante",
      "last_seen_age_s": 0.4,
      "last_stat_age_s": 0.9,
      "status_age_s": 12.2,
      "pps_evt": 8.0,
      "pps_stat": 1.0,
      "loss_evt_pct": 0.0,
      "loss_stat_pct": 0.0,
      "rssi_dbm": -57,
      "vbat_mv": 4090,
      "free_heap": 201344,
      "last_uptime_s": 913,
      "reset_reason": 1,
      "fw_major": 1,
      "fw_minor": 0
    },
    "ota": {
      "state_key": "idle",
      "error_key": "none",
      "check_pending": false,
      "pending_reboot": false,
      "pending_verify": false,
      "health_confirmed": true
    },
    "control_plane": {
      "resolved_ip": "192.168.88.31",
      "resolution_status": "resolved",
      "resolution_age_s": 0.6,
      "transaction_active": false,
      "last_command_name": "REQUEST_STAT_NOW",
      "last_cmd_seq": 42,
      "last_nonce": 123456789,
      "last_final_status": "ack_matched",
      "last_ack_stage": 1,
      "last_status_code": 0,
      "last_err_detail": 0,
      "last_error_message": null,
      "last_tx_started_at": "2026-04-02T20:11:43.101Z",
      "last_tx_finished_at": "2026-04-02T20:11:43.551Z",
      "last_reboot_verification_status": "confirmed",
      "last_reboot_verification_summary": "Nodo visible tras reboot esperado.",
      "message": "Ultimo resultado de control-plane: ack_matched."
    }
  },
  "meta": {
    "request_id": "req_04",
    "api_version": "v1"
  }
}
```

Errores esperados:

- `404 node_not_found` si el nodo no existe en snapshots actuales.
- `400 invalid_node_id` si el path no representa un `node_id` válido.

## Endpoints curados de acción

Las acciones remotas de Ticket 29 son deliberadamente mínimas. Se congelan solo dos.

### `POST /api/v1/nodes/{node_id}/actions/request-stat-now`

Objetivo:

- disparar `REQUEST_STAT_NOW` F3 sobre un nodo resuelto por runtime real.

Body v1:

```json
{}
```

Respuesta `200`:

```json
{
  "ok": true,
  "data": {
    "action": "request_stat_now",
    "node_id": 11,
    "result": {
      "command_name": "REQUEST_STAT_NOW",
      "final_status": "ack_matched",
      "attempt_count": 1,
      "cmd_seq": 42,
      "nonce": 123456789,
      "ack_stage": 1,
      "status_code": 0,
      "err_detail": 0,
      "elapsed_ms": 118.4
    }
  },
  "meta": {
    "request_id": "req_05",
    "api_version": "v1"
  }
}
```

### `POST /api/v1/nodes/{node_id}/actions/reboot`

Objetivo:

- disparar `REBOOT_SOFT` curado y auditable.

Body v1:

```json
{
  "delay_ms": 0
}
```

Restricción:

- `delay_ms` es opcional y debe permanecer acotado a un rango conservador definido por la implementación futura.

Respuesta `200`:

```json
{
  "ok": true,
  "data": {
    "action": "reboot",
    "node_id": 11,
    "result": {
      "command_name": "REBOOT_SOFT",
      "final_status": "ack_matched",
      "attempt_count": 1,
      "cmd_seq": 43,
      "nonce": 123456790,
      "ack_stage": 1,
      "status_code": 0,
      "err_detail": 0,
      "elapsed_ms": 121.7
    }
  },
  "meta": {
    "request_id": "req_06",
    "api_version": "v1"
  }
}
```

## Acciones permitidas en Ticket 29

Permitidas:

- `request_stat_now`
- `reboot`

Explícitamente no permitidas en este subticket:

- `ping`
- `set_stat_rate`
- `set_throttle`
- `ota_check_now`
- cualquier acción de Firmware Manager
- cualquier operación sobre campañas OTA
- cualquier operación sobre catálogo de firmware

### Decisión sobre `reset_calibration`

`reset_calibration` queda fuera de Ticket 29.

Razón:

- no forma parte del conjunto F3 mínimo ya consolidado app-side,
- no existe aquí como acción curada ya validada de extremo a extremo,
- y abrirla en remoto reabre alcance de firmware/seguridad/semántica que este subticket precisamente debe congelar.

Si se necesita más adelante, debe entrar como subticket explícito con:

- contrato F3 definido,
- validación firmware-side,
- justificación operacional,
- criterios de auditoría y seguridad propios.

## Errores v1 congelados

Códigos mínimos:

- `unauthorized`
- `invalid_request`
- `invalid_node_id`
- `node_not_found`
- `session_not_running`
- `control_plane_unavailable`
- `node_unresolved`
- `command_failed`
- `internal_error`

Semántica HTTP mínima:

- `401` para `unauthorized`
- `400` para `invalid_request` e `invalid_node_id`
- `404` para `node_not_found`
- `409` para `session_not_running`, `control_plane_unavailable` y `node_unresolved`
- `502` para `command_failed` cuando la transacción F3 falla de forma operativa pero el gateway sí respondió
- `500` para `internal_error`

## Endpoint opcional no congelado en v1 core

`GET /api/v1/boxes/summary` no queda como requisito del contrato mínimo cerrado en 29.0.

Se permite solo si, en una iteración posterior de Ticket 29, puede derivarse de forma directa desde snapshots existentes sin abrir dominio nuevo.

Si aparece más adelante, debe cumplir estas restricciones:

- derivado únicamente de `node_id -> caja` ya existente,
- sin crear estado paralelo al `NodeRegistry`,
- sin afectar la forma base de `GET /nodes`.

## Acciones explícitamente prohibidas por ahora

- publicar rollouts OTA por la API remota,
- servir `manifest.json` o `firmware.bin` desde esta API,
- borrar/importar firmware remotamente,
- cambiar perfiles de operación remotamente,
- iniciar o detener sesión remotamente en v1,
- exponer configuraciones crudas o secretos,
- exponer escritura arbitraria sobre comandos F3,
- exponer un endpoint genérico `send_raw_cmd`,
- convertir la API en espejo completo de la UI de escritorio.

## Relación con Tailscale

Tailscale es una decisión de conectividad y exposición futura del gateway del sitio. No cambia el contrato funcional v1.

En concreto, este ticket congela:

- paths,
- payloads,
- respuestas,
- auth mínima,
- auditoría mínima.

Y deja fuera por ahora:

- bind definitivo,
- política de puertos,
- ACLs específicas de red,
- publicación real a través de Tailscale,
- endurecimiento de sistema operativo/firewall.

## Cierre de alcance de Ticket 29.0

Con este contrato v1 queda congelado que Ticket 29 construirá un gateway local, autenticado y auditado, apoyado en el runtime real ya existente de CKv2 y limitado a lectura operativa más dos acciones F3 curadas.

No se abre aquí backend completo, consola final, OTA remota ni sistema completo de roles.
