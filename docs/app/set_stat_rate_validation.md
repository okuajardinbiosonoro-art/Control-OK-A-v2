# TICKET 17.3 - Validacion real multi-nodo de `SET_STAT_RATE`

## 1) Objetivo

Validar end-to-end en hardware real el primer `SET_*` curado (`SET_STAT_RATE`) en CKv2 corriendo desde repo local con:

- `python main.py`
- panel `Control F3`
- nodos minimos: `EB1 (node_id=1)` y `ED1 (node_id=3)`

## 2) Prerequisitos

1. Red UDP operativa de planta (nodos emitiendo EVT/STAT a la PC).
2. App CKv2 ejecutada desde repo local (`python main.py`), no `.exe`.
3. Secreto de control configurado:
   - `CKV2_CONTROL_SECRET` o
   - `CKV2_CONTROL_SECRET_FILE` o
   - archivo local soportado por la app.
4. Sesion en `RUNNING` (modo UDP/LAB).
5. MIDI operativo en el host (si falta, la sesion no inicia).

## 3) Valores permitidos (curados)

Solo se aceptan:

- `1000 ms`
- `2000 ms`
- `5000 ms`

No hay input libre.

## 4) Secuencia de validacion por nodo (minima)

Aplicar esta secuencia por cada nodo (`1` y `3`):

1. Confirmar nodo resoluble (`IP resuelta`) en `Control F3`.
2. Medir referencia inicial de cadencia STAT (intervalo observado).
3. Enviar `SET_STAT_RATE = 1000`.
4. Registrar resultado:
   - `ack_stage`
   - `status_code`
   - `err_detail`
   - `final_status`
5. Medir de nuevo la cadencia STAT.
6. Enviar `SET_STAT_RATE = 5000`.
7. Registrar ACK/resultado.
8. Medir de nuevo la cadencia STAT.
9. (Opcional de cierre operativo) devolver a `2000`.

## 5) Observables esperados de exito

Para cada cambio permitido:

- ACK correlacionado (`final_status=ack_matched`).
- Firmware esperado:
  - exito: `ack_stage=1 (ACCEPTED)`, `status_code=0 (OK)`, `err_detail=0`.
- Evidencia de cadencia:
  - a `1000 ms`: STAT aprox cada 1 s.
  - a `5000 ms`: STAT aprox cada 5 s.
  - debe verse diferencia clara (`1000 != 5000`).

## 6) Aislamiento multi-nodo (obligatorio)

Confirmar explicitamente:

- cambio en `node_id=1` no altera cadencia de `node_id=3`
- cambio en `node_id=3` no altera cadencia de `node_id=1`

Validar alternando cambios en cada nodo y observando snapshot/bitacora por nodo.

## 7) Semantica de persistencia (runtime-only)

`SET_STAT_RATE` es runtime-only (RAM). Si el entorno lo permite:

- aplicar `SET_STAT_RATE` a un nodo,
- ejecutar `REBOOT_SOFT`,
- verificar si vuelve al default operativo del firmware.

Si no se ejecuta este paso, dejarlo consignado explicitamente.

## 8) Plantilla de evidencia por cambio

Completar por cada envio:

- `node_id`:
- `label`:
- `ip_resuelta`:
- `stat_rate_enviado_ms`:
- `ack_stage`:
- `status_code`:
- `err_detail`:
- `final_status`:
- `intervalo_stat_observado_s` (antes/despues):
- `nota`:

## 9) Corrida ejecutada en este entorno (2026-03-26)

Resultado: **bloqueada por falta de hardware/trafico UDP activo** en este host.

Evidencia recolectada:

1. Inicio con config real:
   - `start_session()` fallo por MIDI no disponible (`loopMIDI` ausente en este host).
2. Inicio con ajuste temporal de salida MIDI solo para diagnostico local:
   - sesion `RUNNING` en UDP,
   - pero `node_id=1` y `node_id=3` quedaron sin resolucion/IP en ventana de espera.
3. Sondeo UDP directo (`0.0.0.0:5005/5006`, 12 s):
   - paquetes recibidos: `{5005: 0, 5006: 0}`.
4. Prueba transaccional directa a IP historica de EB1 (`192.0.2.10`):
   - `PING`: timeout (sin ACK)
   - `SET_STAT_RATE=1000`: timeout (sin ACK)

Conclusión de esta corrida:

- No hay evidencia de nodos activos en la red de esta maquina en este momento.
- **No se puede declarar cerrado formalmente el TICKET 17.3** sin ejecutar la secuencia en hardware real activo (minimo EB1 + ED1).

## 10) Decision de avance del bloque `SET_*`

Estado recomendado:

- `SET_STAT_RATE` queda listo tecnicamente (firmware + app/UI + pipeline).
- Cierre formal del primer `SET_*`: **pendiente** hasta completar validacion real multi-nodo de este runbook con ACK+cadencia observada.
- Apertura de otro `SET_*`: **no recomendada todavia** hasta cerrar 17.3 en banco/campo.
