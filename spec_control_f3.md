# spec_control_f3.md

## 1. Proposito

Congelar el contrato tecnico de Fase 3 (F3) para control UDP OKUA v1 en CKv2, definiendo sin ambiguedad `OKUA_CMD` y `OKUA_ACK`, sus codigos, reglas de seguridad minima y auditoria.

Este documento es normativo para implementacion futura en firmware y app.

## 2. Alcance y fuera de alcance

Alcance:
- Formato binario final de `OKUA_CMD` y `OKUA_ACK`.
- Semantica de `cmd_id`, `status_code`, `err_detail`, `nonce`, `auth_tag32`.
- Politicas de ACK, timeout, retry, idempotencia, anti-replay, rate-limit.
- Reglas de broadcast.
- Contrato de auditoria para `session.jsonl`.

Fuera de alcance:
- Implementacion runtime de firmware receptor CMD/ACK.
- Implementacion runtime en app (`cmd_service.py`, UI de comandos, cambios SessionController).
- OTA cliente/servidor.
- API remota movil/servidor.
- Cifrado de canal, auth multiusuario completa.
- Cambios productivos en parser UDP, NodeRegistry, backends, firmware.

## 3. Invariantes heredados de OKUA v1

Invariantes obligatorios heredados:
- Endianness: little-endian.
- Magic: `0x4B4F`.
- Version: `1`.
- Header comun `OkuaHdr` de 8 bytes: `<HBBHH>`.
  - `magic:u16`, `version:u8`, `type:u8`, `node_id:u16`, `seq:u16`.
- Tipos de paquete:
  - `EVT=1`
  - `STAT=2`
  - `CMD=3`
  - `ACK=4`
- Tamaños ya operativos:
  - `OKUA_EVT=20` bytes
  - `OKUA_STAT=28` bytes

## 4. Puertos y flujo de red

Puertos de F3 (plano de control separado del plano de datos):
- `EVT_PORT=5005` (nodo -> app)
- `STAT_PORT=5006` (nodo -> app)
- `CMD_PORT=5007` (app -> nodo)
- `ACK_PORT=5008` (nodo -> app)

Flujo unicast:
1. App envia `OKUA_CMD` a `<node_ip>:5007`.
2. Nodo responde `OKUA_ACK` a `<source_ip_de_CMD>:5008`.

Flujo broadcast (`node_id_target=0`):
1. App envia `OKUA_CMD` a broadcast de red en `5007`.
2. Cada nodo elegible responde `OKUA_ACK` unicast al `source_ip` en `5008`.

## 5. Decisiones de compatibilidad con el header actual

Decision cerrada:
- `OKUA_CMD` y `OKUA_ACK` **deben reutilizar** `OkuaHdr` sin variante.

Reglas cerradas:
- `cmd_seq` **es** `hdr.seq` (fuente unica de verdad).
- Queda prohibido duplicar `cmd_seq` en payload.
- En `CMD`, `hdr.node_id` es `node_id_target` (`0` = broadcast).
- En `ACK`, `hdr.node_id` es `node_id_responder` (nunca `0`).
- En `ACK`, `hdr.seq` debe ser eco exacto del `hdr.seq` del `CMD` correlacionado.

Justificacion breve:
- Reusar `OkuaHdr` mantiene coherencia con firmware/app actual, evita duplicacion y reduce riesgo de incompatibilidad.

## 6. Especificacion final de OKUA_CMD

### 6.1 Layout byte a byte

Tamano total `OKUA_CMD`: **28 bytes** (`header=8` + `payload=20`).

Empaquetado obligatorio:
- Header: `<HBBHH>`
- Payload CMD: `<BBHHQ2sI>`
- Paquete total: `<HBBHHBBHHQ2sI>`

Offsets:
- `0..1`   `magic:u16` (`0x4B4F`)
- `2`      `version:u8` (`1`)
- `3`      `type:u8` (`3`)
- `4..5`   `node_id_target:u16` (`0`=broadcast)
- `6..7`   `cmd_seq:u16` (via `hdr.seq`)
- `8`      `cmd_id:u8`
- `9`      `cmd_flags:u8`
- `10..11` `arg0:u16`
- `12..13` `arg1:u16`
- `14..21` `nonce:u64`
- `22..23` `rsv0:2 bytes` (deben ser `0x0000` en v1)
- `24..27` `auth_tag32:u32`

### 6.2 Semantica campo por campo

- `cmd_id`: identifica comando segun tabla de la seccion 8.
- `cmd_flags` (v1):
  - bit0 `ack_required`: debe ser `1` en v1.
  - bit1 `is_retry`: `0` en primer envio, `1` en reintentos.
  - bit2 `broadcast_intent`: debe ser `1` si `node_id_target=0`, y `0` en unicast.
  - bit3..bit7: reservados, deben ser `0`.
- `arg0/arg1`: argumentos del comando segun seccion 8.
- `nonce`: anti-replay e idempotencia (seccion 12). En v1 se codifica como:
  - high 32 bits: `control_epoch_s`
  - low 32 bits: `cmd_counter`
- `rsv0`: reservado para evolucion futura, debe enviarse en cero y debe ignorarse en recepcion v1.
- `auth_tag32`: autenticacion minima (seccion 12).

## 7. Especificacion final de OKUA_ACK

### 7.1 Layout byte a byte

Tamano total `OKUA_ACK`: **28 bytes** (`header=8` + `payload=20`).

Empaquetado obligatorio:
- Header: `<HBBHH>`
- Payload ACK: `<BBBBHHQI>`
- Paquete total: `<HBBHHBBBBHHQI>`

Offsets:
- `0..1`   `magic:u16` (`0x4B4F`)
- `2`      `version:u8` (`1`)
- `3`      `type:u8` (`4`)
- `4..5`   `node_id_responder:u16` (nunca `0`)
- `6..7`   `cmd_seq_echo:u16` (eco exacto de CMD)
- `8`      `cmd_id_echo:u8`
- `9`      `ack_stage:u8`
- `10`     `status_code:u8`
- `11`     `ack_flags:u8`
- `12..13` `err_detail:u16`
- `14..15` `retry_after_ms:u16`
- `16..23` `nonce_echo:u64`
- `24..27` `auth_tag32:u32`

### 7.2 Semantica campo por campo

- `ack_stage`:
  - `1=ACCEPTED` (validado y admitido; puede ser diferido)
  - `2=EXECUTED` (aplicado sincronicamente antes del ACK)
  - `3=REJECTED` (no admitido; sin side-effect)
  - `0` reservado/prohibido.
- `status_code`: catalogo cerrado en seccion 9.
- `ack_flags` (v1):
  - bit0 `duplicate_ack`: ACK reenviado desde cache idempotente.
  - bit1 `broadcast_response`: ACK originado por CMD broadcast.
  - bit2 `execution_deferred`: comando aceptado pero ejecucion no finalizada al emitir ACK.
  - bit3..bit7: reservados, deben ser `0`.
- `err_detail`: catalogo cerrado en seccion 10.
- `retry_after_ms`: solo aplica para `RATE_LIMITED` y `BUSY`; en otros casos debe ser `0`.
- `nonce_echo`: eco exacto del nonce de CMD.
- `auth_tag32`: autenticacion minima para ACK (seccion 12).

Reglas de consistencia obligatorias:
- Si `ack_stage in {ACCEPTED, EXECUTED}` entonces `status_code=OK` y `err_detail=NONE`.
- Si `ack_stage=REJECTED` entonces `status_code` debe ser una causa especifica (`INVALID_AUTH`, `INVALID_ARG`, `UNSUPPORTED_CMD`, `RATE_LIMITED`, `REPLAY_REJECTED`, `BUSY` o `INTERNAL_ERROR`).

## 8. Tabla de comandos v1

| cmd_id | Nombre | Objetivo | Args | Broadcast | Requiere ACK | Restricciones | Notas operativas |
|---|---|---|---|---|---|---|---|
| `0x01` | `PING` | Salud/control-plane reachability | `arg0=0`, `arg1=0` | Si | Si | Sin side-effects | ACK recomendado `EXECUTED` |
| `0x02` | `REBOOT_SOFT` | Reinicio suave de nodo | `arg0=delay_ms (50..5000, 0=>200)`, `arg1=0` | No | Si | Prohibido broadcast | ACK debe emitirse antes de reinicio |
| `0x03` | `SET_PROFILE` | Cambiar perfil operativo interno del nodo | `arg0=profile_id (1..255)`, `arg1=0` | No | Si | `profile_id` debe existir en firmware | ACK `EXECUTED` si aplica inmediato |
| `0x04` | `SET_THROTTLE` | Ajustar limite de salida/control | `arg0=percent (0..100)`, `arg1=0` | No | Si | Rango estricto | ACK `EXECUTED` si aplica inmediato |
| `0x05` | `SET_STAT_RATE` | Cambiar periodo de STAT | `arg0=period_ms (100..10000)`, `arg1=0` | No | Si | No broadcast en v1 | ACK `EXECUTED` si aplica inmediato |
| `0x06` | `SET_DEBUG` | Ajustar verbosidad de debug del nodo | `arg0=level (0..3)`, `arg1=0` | No | Si | No broadcast en v1 | ACK `EXECUTED` si aplica inmediato |
| `0x07` | `REQUEST_STAT_NOW` | Solicitar STAT inmediato fuera de cadencia | `arg0=0`, `arg1=0` | Si | Si | Debe disparar al menos 1 STAT pronto | ACK recomendado `ACCEPTED` + `execution_deferred=1` |

## 9. Tabla de status_code

| status_code | Nombre | Semantica |
|---|---|---|
| `0x00` | `OK` | Comando aceptado/ejecutado segun `ack_stage` |
| `0x01` | `RESERVED` | Reservado; no debe emitirse en v1 |
| `0x02` | `INVALID_AUTH` | `auth_tag32` invalido o secreto no coincide |
| `0x03` | `INVALID_ARG` | Argumentos invalidos para `cmd_id` |
| `0x04` | `UNSUPPORTED_CMD` | `cmd_id` no soportado por firmware |
| `0x05` | `RATE_LIMITED` | Limite de tasa excedido |
| `0x06` | `REPLAY_REJECTED` | Falla anti-replay/idempotencia invalida |
| `0x07` | `BUSY` | Nodo temporalmente no apto para ejecutar |
| `0x08` | `INTERNAL_ERROR` | Error interno no clasificable |

## 10. Tabla de err_detail

| err_detail | Nombre | Uso esperado |
|---|---|---|
| `0x0000` | `NONE` | Sin detalle adicional |
| `0x0001` | `ARG0_OUT_OF_RANGE` | `arg0` fuera de rango |
| `0x0002` | `ARG1_OUT_OF_RANGE` | `arg1` fuera de rango |
| `0x0003` | `PROFILE_ID_UNKNOWN` | `SET_PROFILE` con id no existente |
| `0x0004` | `THROTTLE_INVALID` | `SET_THROTTLE` invalido |
| `0x0005` | `STAT_RATE_INVALID` | `SET_STAT_RATE` invalido |
| `0x0006` | `DEBUG_LEVEL_INVALID` | `SET_DEBUG` invalido |
| `0x0007` | `BROADCAST_NOT_ALLOWED` | `cmd_id` no permitido en broadcast |
| `0x0008` | `NONCE_REUSED` | Nonce repetido ya usado |
| `0x0009` | `NONCE_OUT_OF_WINDOW` | Nonce fuera de ventana anti-replay |
| `0x000A` | `AUTH_TAG_MISMATCH` | Tag no valida contenido |
| `0x000B` | `RATE_LIMIT_EXCEEDED` | Exceso de tasa detectado |
| `0x000C` | `NODE_STATE_BLOCKED` | Estado operativo no apto |
| `0x000D` | `CMD_IN_PROGRESS` | Comando bloqueado por otro en curso |
| `0x000E` | `MALFORMED_PACKET` | Frame bien tipado pero invalido internamente |

## 11. Reglas de ACK, timeout, retry e idempotencia

Semantica de ACK cerrada:
- Un `ACK` con `status_code=OK` significa:
  - `ack_stage=ACCEPTED`: comando validado y admitido; puede estar programado/diferido.
  - `ack_stage=EXECUTED`: comando aplicado antes de emitir ACK.
- No existe en v1 un segundo ACK de finalizacion. Solo un ACK por intento logico.

Regla especifica `REBOOT_SOFT`:
- Debe responder `ACK` **antes** de ejecutar reinicio.
- Debe usar `ack_stage=ACCEPTED`, `status_code=OK`, `execution_deferred=1`.
- No debe esperarse ACK posterior al reboot para cerrar comando.

Timeout/retry en app:
- Unicast:
  - `base_timeout_ms=300`.
  - `max_retries=2` (hasta 3 envios totales).
  - Backoff exponencial por intento: `300ms`, `600ms`, `1200ms`.
- Retry debe reutilizar exactamente `cmd_seq`, `nonce`, `cmd_id`, `arg0`, `arg1`.
- Retry debe recomputar `auth_tag32` sobre bytes identicos (resultado igual).
- No debe reintentarse automaticamente si llega `INVALID_AUTH`, `INVALID_ARG`, `UNSUPPORTED_CMD`, `REPLAY_REJECTED`.
- Si llega `RATE_LIMITED` o `BUSY`, se recomienda reintento unico respetando `retry_after_ms`.

Politica de cierre de broadcast (v1):
- `broadcast_collect_window_ms=1000`.
- Al enviar broadcast, la app debe abrir una ventana de coleccion de ACKs por `1000ms`.
- Si se recibio al menos un ACK, la app puede cerrar antes por inactividad de `200ms` sin nuevos ACKs.
- La operacion broadcast debe cerrar por tiempo y produce resultado fan-out parcial (no all-or-nothing).
- No debe haber retry automatico de broadcast en v1.

Idempotencia en nodo:
- El nodo debe garantizar ejecucion **a lo sumo una vez** por llave:
  - `(source_ip, cmd_seq, nonce, cmd_id, arg0, arg1)`.
- Debe existir cache de deduplicacion minima de `128` entradas con TTL `120s`.
- Si llega duplicado exacto dentro de TTL, el nodo no debe re-ejecutar; debe reenviar el mismo ACK con `duplicate_ack=1`.
- Si `nonce/cmd_seq` coinciden pero payload no coincide, debe rechazar con `REPLAY_REJECTED`.

## 12. Seguridad minima operativa

### 12.1 auth_tag32

Definicion cerrada:
- Algoritmo recomendado: `HMAC-SHA256` con secreto compartido.
- Truncamiento: primeros 4 bytes del digest (`digest[0:4]`) interpretados `u32 little-endian`.
- Comparacion en recepcion: tiempo constante.

Cobertura exacta:
- `CMD`: HMAC sobre bytes `0..23` del paquete (header + payload sin `auth_tag32`).
- `ACK`: HMAC sobre bytes `0..23` del paquete (header + payload sin `auth_tag32`).
- No se incluyen metadatos UDP (IP/puertos).

### 12.2 nonce

Definicion cerrada:
- Tamano: `u64`.
- Formato obligatorio:
  - high 32 bits: `control_epoch_s`.
  - low 32 bits: `cmd_counter`.
- `control_epoch_s` debe ser monotono entre reinicios de la app.
- La app debe persistir `last_control_epoch_s`.
- Al iniciar sesion de control, la app debe usar:
  - `control_epoch_s = max(unix_time_s, last_control_epoch_s + 1)`.
- Si el reloj local retrocede, la regla anterior sigue siendo obligatoria.
- `cmd_counter` inicia en `0` por sesion de control y debe incrementarse por cada comando logico nuevo.
- Reintentos deben reutilizar exactamente el mismo nonce.

### 12.3 anti-replay

Politica cerrada por nodo y `source_ip`:
- Ventana deslizante de `128` nonces recientes.
- Reglas:
  - El nodo debe comparar/validar el `nonce:u64` completo (epoch+counter).
  - nonce nuevo mayor: aceptar y avanzar ventana.
  - nonce dentro de ventana no visto: aceptar.
  - nonce ya visto: `REPLAY_REJECTED + NONCE_REUSED`.
  - nonce mas antiguo que ventana: `REPLAY_REJECTED + NONCE_OUT_OF_WINDOW`.

Tras reboot del nodo:
- El estado anti-replay se reinicia (sin persistencia en v1).
- La app debe re-sincronizar con `PING` unicast por nodo antes de comandos sensibles.
- Este riesgo residual se acepta en F3 por simplicidad operativa ESP32.

### 12.4 rate-limit

Politica cerrada (por nodo y `source_ip`):
- Token bucket:
  - capacidad: `10` tokens
  - refill: `1 token/segundo`
- Equivalente: `60 comandos/minuto` sostenidos, con rafaga maxima `10`.
- Al exceder:
  - `ack_stage=REJECTED`
  - `status_code=RATE_LIMITED`
  - `err_detail=RATE_LIMIT_EXCEEDED`
  - `retry_after_ms` debe informar espera minima estimada.

### 12.5 alcance de seguridad

- F3 asume operacion en LAN/VPN de confianza.
- Queda prohibido exponer `CMD_PORT`/`ACK_PORT` directamente a Internet.
- El panel de control debe estar protegido operacionalmente.
- Auth de usuarios, cifrado de canal y IAM quedan fuera de este ticket.

## 13. Reglas de broadcast

Reglas cerradas:
- Broadcast se representa exclusivamente con `node_id_target=0`.
- Comandos con broadcast permitido en v1: solo `PING` y `REQUEST_STAT_NOW`.
- Cualquier otro `cmd_id` recibido en broadcast debe responder `ack_stage=REJECTED`, `status_code=INVALID_ARG`, `err_detail=BROADCAST_NOT_ALLOWED`.
- En broadcast, cada nodo elegible debe responder ACK unicast con `broadcast_response=1`.
- La app debe tratar broadcast como operacion fan-out (0..N ACK), no como transaccion all-or-nothing.
- `broadcast_collect_window_ms=1000` debe iniciar al enviar el broadcast.
- Si llega al menos un ACK, la app puede cerrar anticipadamente por `200ms` de silencio sin nuevos ACKs.
- Si no llega ningun ACK, la app debe cerrar al vencer `1000ms`.
- No debe haber retry automatico de broadcast en v1.

## 14. Auditoria en app y logs

La auditoria debe reutilizar el pipeline actual de `session.jsonl` (`schema_version=1`, `session_id`, `event_type`, `ts_rel_ms`, `wall_time_utc`, `payload`).

Eventos minimos obligatorios (nuevos `event_type` para F3):
- `command_sent`
- `command_retry`
- `command_ack`
- `command_timeout`

Politica cerrada de persistencia:
- En `session.jsonl` se debe persistir solo `command_ack` para resultados ACK.
- `command_rejected` no debe persistirse como `event_type` separado.
- `command_rejected` queda como categoria logica derivada cuando `command_ack.ack_stage=REJECTED`.
- El cierre de broadcast debe derivarse logicamente desde `command_sent` + ventana de coleccion + ACKs observados (sin evento terminal adicional dedicado en v1).

### 14.1 Payload minimo comun recomendado

Campos minimos por evento:
- `ts_utc` (ISO8601 UTC; espejo de `wall_time_utc` para consumo externo)
- `session_id`
- `correlation_id` (UUID o equivalente, estable por comando logico)
- `operator_identity` (usuario/perfil/fuente)
- `action_source` (`ui`, `automation`, etc.)
- `node_id_target`
- `cmd_id`
- `cmd_seq`
- `nonce`
- `arg0`
- `arg1`
- `retry_index` (0 en envio inicial)
- `transport` (meta minima de red)

### 14.2 Campos minimos por tipo

- `command_sent`:
  - comunes + `dest_ip`, `dest_port=5007`
  - en broadcast debe incluir `broadcast_collect_window_ms=1000`
- `command_retry`:
  - comunes + `reason` (`timeout`, `busy`, `rate_limited`)
- `command_ack`:
  - comunes + `node_id_responder`, `ack_stage`, `status_code`, `err_detail`, `ack_flags`, `retry_after_ms`, `ack_valid_auth`
- `command_timeout`:
  - comunes + `max_retries`, `deadline_ms`, `attempts_total`
  - aplica a unicast cuando no llega ACK valido tras retries

### 14.3 Distincion de estados operativos

La app debe distinguir explicitamente:
- `sent`: existe `command_sent`.
- `retry`: existe uno o mas `command_retry`.
- `timeout`: cierre por `command_timeout` sin ACK valido.
- `accepted`: `command_ack` con `ack_stage=ACCEPTED` y `status_code=OK`.
- `executed`: `command_ack` con `ack_stage=EXECUTED` y `status_code=OK`.
- `rejected`: categoria derivada cuando `command_ack` tiene `ack_stage=REJECTED`.
- `broadcast_closed`: categoria derivada al cerrar ventana de coleccion (por `window_expired` o `idle_early_close`).

### 14.4 Correlacion comando-ACK

Correlacion obligatoria por clave:
- `(correlation_id, cmd_seq, nonce, cmd_id)`

Refuerzo en recepcion ACK:
- Debe validar tambien `node_id_responder` y `nonce_echo`.
- En broadcast, un mismo `correlation_id` puede tener multiples ACK (uno por nodo).

## 15. Ejemplos minimos de intercambio

Nota de nonce en ejemplos:
- `N1=(control_epoch_s<<32)|0`
- `N2=(control_epoch_s<<32)|1`
- `N3=(control_epoch_s<<32)|2`

### 15.1 PING -> ACK OK

- CMD: `type=3 node_id=12 cmd_seq=100 cmd_id=0x01 nonce=N1 arg0=0 arg1=0`
- ACK: `type=4 node_id=12 cmd_seq=100 cmd_id=0x01 ack_stage=EXECUTED status=OK err=NONE nonce=N1`

### 15.2 REQUEST_STAT_NOW -> ACK OK

- CMD: `type=3 node_id=12 cmd_seq=101 cmd_id=0x07 nonce=N2`
- ACK: `type=4 node_id=12 cmd_seq=101 cmd_id=0x07 ack_stage=ACCEPTED status=OK ack_flags.execution_deferred=1 nonce=N2`
- Nota: luego debe observarse al menos un `STAT` en canal de datos.

### 15.3 REBOOT_SOFT -> ACK OK + nota semantica

- CMD: `type=3 node_id=12 cmd_seq=102 cmd_id=0x02 arg0=200 nonce=N3`
- ACK: `type=4 node_id=12 cmd_seq=102 cmd_id=0x02 ack_stage=ACCEPTED status=OK execution_deferred=1 nonce=N3`
- Semantica: reboot programado; no se espera ACK posterior al reinicio.

### 15.4 Comando rechazado por auth

- CMD con `auth_tag32` invalido.
- ACK: `ack_stage=REJECTED status=INVALID_AUTH err=AUTH_TAG_MISMATCH retry_after_ms=0`.

### 15.5 Comando rechazado por replay

- CMD con `nonce` repetido fuera de regla idempotente.
- ACK: `ack_stage=REJECTED status=REPLAY_REJECTED err=NONCE_REUSED`.

### 15.6 Comando rechazado por rate-limit

- CMD excede bucket del nodo.
- ACK: `ack_stage=REJECTED status=RATE_LIMITED err=RATE_LIMIT_EXCEEDED retry_after_ms=900`.

## 16. Reglas de compatibilidad futura / extensibilidad

- Campos reservados (`rsv0`, bits reservados) deben enviarse en cero y deben ignorarse en v1.
- `cmd_id` nuevos pueden agregarse sin romper v1, manteniendo layout y semantica de seguridad.
- `status_code` y `err_detail` desconocidos deben tratarse como rechazo generico, preservando valor bruto en logs.
- Cambios estructurales de payload o semantica incompatibles deben usar version de protocolo nueva (no reinterpretar v1).
- Queda prohibido reutilizar IDs ya asignados con semantica distinta.

## 17. Decisiones cerradas

1. `CMD/ACK` reutilizan `OkuaHdr` de 8 bytes sin cambios.
2. `cmd_seq` es unicamente `hdr.seq` (sin duplicacion en payload).
3. `CMD` y `ACK` quedan en 28 bytes exactos cada uno.
4. Endianness oficial: little-endian en todos los campos.
5. `status=OK` no implica siempre ejecucion completa; depende de `ack_stage`.
6. `status_code=REJECTED` se elimina en v1; el rechazo lo indica `ack_stage=REJECTED` y la causa la da `status_code` especifico.
7. `REBOOT_SOFT` responde ACK antes del reinicio y solo en modo `ACCEPTED`.
8. Broadcast en v1 solo para `PING` y `REQUEST_STAT_NOW`, con ACK fan-out por nodo y cierre temporal (`1000ms`, cierre temprano por `200ms` de silencio con al menos un ACK).
9. `auth_tag32` queda definido como truncamiento de `HMAC-SHA256` sobre bytes `0..23`.
10. `nonce` queda fijado en `u64` con formato `control_epoch_s(32b) + cmd_counter(32b)`, monotonia entre reinicios de app y ventana anti-replay de 128.
11. Rate-limit cerrado: token bucket `10` de burst y `1 token/s` por nodo/source_ip.
12. Auditoria se integra en `session.jsonl`; se persiste `command_ack` y `command_rejected` queda solo como categoria derivada.

## 18. Pendientes explicitamente dejados para tickets posteriores

- Implementacion firmware de parser/handler `CMD/ACK`.
- Implementacion app de emision de comandos, cola, retries y matching ACK.
- Alta de `event_type` F3 en modelo de recording y reportes (`command_sent`, `command_retry`, `command_ack`, `command_timeout`).
- UI operativa para comandos y visualizacion de estado de control-plane.
- Rotacion de secretos, key management y auth de usuarios.
- Hardening criptografico adicional (canal cifrado, mutual auth, anti-replay persistente entre reboots).
- Expansion de catalogo de comandos (OTA, Wi-Fi, admin extendida).
