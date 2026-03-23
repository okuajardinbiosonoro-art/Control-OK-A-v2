# Control Plane F3 App-Side Minimal (Cierre Ticket 14)

Estado de cierre: **marzo 23, 2026**.

## 1) Alcance implementado en CKv2 (app-side)

- Construcción y envío de `OKUA_CMD` válidos para:
  - `PING`
  - `REQUEST_STAT_NOW`
  - `REBOOT_SOFT`
- `auth_tag32` real (sobre bytes `0..23`) según contrato F3.
- `nonce` persistente/monotónico y `cmd_seq` monotónico para comandos lógicos nuevos.
- Listener UDP de `OKUA_ACK` en `ACK_PORT=5008`.
- Parser estricto de ACK (`28 bytes`, `magic`, `ver`, `type`) y correlación por:
  - `cmd_seq`
  - `cmd_id_echo`
  - `nonce_echo`
- `ControlTransactionService` con:
  - timeout por intento configurable
  - retry controlado
  - reutilización exacta de `cmd_seq` y `nonce` en retries
  - auditoría básica en memoria

## 2) Exposición UI técnica actual

- Existe panel técnico en `Diagnóstico` (ubicación secundaria, operator-first preservado).
- Comandos expuestos en UI:
  - `PING`
  - `REQUEST_STAT_NOW`
  - `REBOOT_SOFT`
- `REBOOT_SOFT` requiere confirmación explícita antes de enviar.
- La UI muestra resultado legible de transacción (estado final, `cmd_seq`, `nonce`, intentos y detalles ACK).
- Durante ejecución se deshabilitan controles del panel y se mantiene ventana responsive.

## 3) Flujo transaccional implementado

1. Construir CMD y enviar por UDP.
2. Registrar pendiente.
3. Esperar ACK correlacionado.
4. Si aplica, retry controlado del mismo comando lógico.
5. Cerrar con resultado final.

Resultados finales soportados:

- `ACK_MATCHED`
- `TIMEOUT`
- `INVALID_ACK_SEEN`
- `UNMATCHED_ACK_SEEN`
- `LISTENER_NOT_RUNNING`
- `SEND_ERROR`

## 4) Validación por niveles (cierre 14.5)

Nivel 1 (obligatorio, ejecutado):

- Smoke local/fake de panel técnico:
  - `PING`
  - `REQUEST_STAT_NOW`
  - `REBOOT_SOFT` con confirmación
- Verificación de no congelamiento de UI del panel durante transacción.
- Verificación de que `Operación` no muestra controles F3 crudos.
- Verificación de que `Diagnóstico` sí contiene el panel técnico.
- Verificación de ausencia de `SET_*` en UI.

Nivel 2 (recomendado, ejecutado):

- Validación integrada app-side por UDP loopback local (sin hardware), con:
  - `PING` -> ACK correlacionado
  - `REQUEST_STAT_NOW` -> ACK correlacionado
  - `REBOOT_SOFT` -> ACK correlacionado
  - escenario de retry con confirmación de reutilización exacta de `cmd_seq` y `nonce` (mismos bytes CMD en reenvío)

Nivel 3 (hardware real):

- No ejecutado en este cierre por no contar con nodo ESP32 conectado en este entorno de validación.
- Pendiente recomendado cuando haya banco real disponible:
  - `PING -> ACK`
  - `REQUEST_STAT_NOW -> ACK + STAT inmediato`
  - `REBOOT_SOFT -> ACK previo + reinicio diferido`

## 5) Fuera de alcance (aún no implementado)

- `SET_PROFILE`, `SET_THROTTLE`, `SET_STAT_RATE`, `SET_DEBUG`
- Auditoría persistente final de control-plane
- Historial avanzado en UI técnica
- Broadcast como caso principal
- Integraciones OTA/servidor/móvil

## 6) Habilitación del siguiente bloque

El bloque app-side F3 mínimo queda consolidado y listo para extenderse en la siguiente fase sobre:

- comandos `SET_*`
- capa de evidencias/auditoría persistente
- validación de hardware real continua en banco
