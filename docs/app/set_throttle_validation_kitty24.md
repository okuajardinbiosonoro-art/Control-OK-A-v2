# TICKET 18.3 - Validacion real multi-nodo de `SET_THROTTLE` en `Kitty_2.4`

## 1) Objetivo

Validar end-to-end en hardware real el segundo `SET_*` curado (`SET_THROTTLE`) desde CKv2 ejecutado con:

- `python main.py`
- panel `Control F3`
- nodos de prueba: `EB2 (node_id=6)`, `EC2 (node_id=7)`, `ED2 (node_id=8)`

## 2) Prerequisitos

1. Red Wi-Fi activa: `Kitty_2.4`.
2. Host CKv2 alcanzable por los nodos con la IP cargada en firmware (`192.0.2.10`).
3. Nodos de prueba encendidos y emitiendo EVT/STAT en modo `TEST + PLANT`.
4. App ejecutada desde repo local (`python main.py`), no `.exe`.
5. Sesion UDP/LAB en `RUNNING`.

Si la red o IP del host no coincide con la configuracion de nodos, detener validacion y reportar bloqueo operativo.

## 3) Valores permitidos (curados)

`SET_THROTTLE` solo permite:

- `25`
- `50`
- `100`

No hay input libre.

## 4) Secuencia minima por nodo

Aplicar por nodo (`6`, `7`, `8`):

1. Confirmar nodo resoluble (IP en `Control F3`).
2. Medir referencia inicial del ritmo de EVT/notas automaticas.
3. Enviar `SET_THROTTLE = 25`.
4. Registrar ACK/resultado.
5. Medir de nuevo ritmo EVT/notas.
6. Enviar `SET_THROTTLE = 100`.
7. Registrar ACK/resultado.
8. Medir de nuevo ritmo EVT/notas.
9. (Opcional de cierre) enviar `SET_THROTTLE = 50`.

## 5) Observables esperados de exito

Para cada valor permitido:

- transaccion con `final_status=ack_matched`
- `ack_stage=1 (ACCEPTED)`
- `status_code=0 (OK)`
- `err_detail=0`

Evidencia de efecto real:

- `25%` debe mostrar menor ritmo de EVT/notas que `100%`
- `100%` debe mostrar mayor ritmo de EVT/notas que `25%`
- diferencia visible por timestamps/intervalos en bitacora o snapshot

## 6) Aislamiento multi-nodo

Confirmar explicitamente:

- cambiar `EB2` no altera ritmo de `EC2/ED2`
- cambiar `EC2` no altera ritmo de `EB2/ED2`
- cambiar `ED2` no altera ritmo de `EB2/EC2`

## 7) Persistencia (runtime-only)

Opcional en esta corrida, si el entorno lo permite:

1. aplicar `SET_THROTTLE` a un nodo
2. ejecutar `REBOOT_SOFT`
3. observar si vuelve al default del firmware

Si no se ejecuta, dejarlo consignado.

## 8) Plantilla de evidencia por envio

- `node_id`:
- `label`:
- `ip_resuelta`:
- `throttle_enviado`:
- `ack_stage`:
- `status_code`:
- `err_detail`:
- `final_status`:
- `ritmo_evt_observado` (antes/despues):
- `nota`:

## 9) Corridas ejecutadas en este entorno (2026-03-27)

### 9.1 Corrida inicial (fallida por red)

Resultado: **bloqueada por precondicion de red/IP**.

- SSID: `Integra f(x) = ln(x)`
- IPv4 Wi-Fi: `172.20.10.3`
- Sondeo UDP (`5005/5006`, 12 s): `{5005: 0, 5006: 0}`

### 9.2 Reintento operativo (precondicion cumplida, bloqueo funcional)

Precondicion de red: **cumplida**.

- Host en `192.0.2.10` (Ethernet), coincidente con `PC_IP` cargada en nodos.
- Sondeo UDP (`5005/5006`, 12 s): trafico activo.

Descubrimiento real de nodos:

- `EC2` (`node_id=7`) -> `192.0.2.10`
- `ED2` (`node_id=8`) -> `192.0.2.10`
- `EB2` (`node_id=6`) no aparecio en trafico durante la ventana de validacion.

Comprobacion de canal F3 base (control positivo):

- `PING` en nodos `7` y `8`: `ACK (1,0,0)` (`ACCEPTED + OK`)
- `REQUEST_STAT_NOW` en nodos `7` y `8`: `ACK (1,0,0)`
- `SET_STAT_RATE=1000` en nodos `7` y `8`: `ACK (1,0,0)`

Validacion `SET_THROTTLE` ejecutada (nodos 7 y 8):

- `SET_THROTTLE=25` y `SET_THROTTLE=100` correlacionaron ACK (`final_status=ack_matched`)
- Pero los ACK fueron `ack_stage=3`, `status_code=4`, `err_detail=0`
- Segun `okua_control_plane.h`: `3=REJECTED`, `4=UNSUPPORTED_CMD`

Interpretacion:

- El pipeline app-side funciona y el nodo responde.
- El firmware activo en los nodos probados **aun no tiene habilitado `SET_THROTTLE`** (o no es la build esperada de 18.1).

Evidencia de ritmo EVT (Hz, ventana 8 s) en reintento:

- `baseline`: node7=`9.00`, node8=`9.25`
- `post node7 thr25`: node7=`9.00`, node8=`8.50`
- `post node7 thr100`: node7=`9.00`, node8=`9.25`
- `post node8 thr25`: node7=`9.00`, node8=`9.25`
- `post node8 thr100`: node7=`9.00`, node8=`9.25`

Como el comando fue rechazado por `UNSUPPORTED_CMD`, no se observan cambios consistentes atribuibles a throttle.

Artefacto de evidencia:

- `artifacts/validation/ticket18_3_set_throttle_20260327_100639.json`

Conclusiones de la corrida:

- La precondicion de red ya no bloquea.
- El bloqueo actual es de version de firmware en nodos (`SET_THROTTLE` rechazado como `UNSUPPORTED_CMD`).
- **No se puede declarar cerrado formalmente el TICKET 18.3** hasta cargar firmware con soporte real de `SET_THROTTLE` en al menos dos nodos activos.

### 9.3 Rerun posterior a reflasheo EB2/EC2/ED2 (precondicion cumplida)

Precondicion de red: **cumplida**.

- Host CKv2: `192.0.2.10` (Ethernet).
- Nodos detectados en trafico UDP:
  - `EB2` (`node_id=6`) -> `192.0.2.10`
  - `EC2` (`node_id=7`) -> `192.0.2.10`
  - `ED2` (`node_id=8`) -> `192.0.2.10`

Control positivo del canal F3:

- `PING` en `6/7/8`: `ACK (1,0,0)`.

Validacion `SET_THROTTLE` (corrida principal):

- `node 6`: `25` -> `ACK (1,0,0)`, `100` -> `ACK (1,0,0)`.
- `node 8`: `25` -> `ACK (1,0,0)`, `100` -> `ACK (1,0,0)`.
- `node 7`: `25` -> `ACK (1,0,0)`, `100` -> `timeout` en esta ventana.
- Restore de cierre:
  - `SET_THROTTLE=50` en `6/7/8` -> `ACK (1,0,0)`.

Persistencia/runtime-only (opcional ejecutada):

- `node 6`: `SET_THROTTLE=25` -> `ACK (1,0,0)`.
- `REBOOT_SOFT` -> `ACK (1,0,0)`.
- Nodo vuelve a emitir EVT/STAT tras reinicio (comando runtime-only aceptado; no persistencia demostrable por cadencia en este modo).

Evidencia de ritmo EVT (Hz, ventana 6 s, corrida principal):

- `baseline`: node6=`9.00`, node7=`8.667`, node8=`9.167`
- `post node6 thr25`: node6=`9.333`, node7=`0.167`, node8=`9.00`
- `post node6 thr100`: node6=`9.00`, node7=`0.00`, node8=`9.00`
- `post node7 thr25`: node6=`9.00`, node7=`8.50`, node8=`8.667`
- `post node7 thr100`: node6=`9.00`, node7=`0.00`, node8=`9.00`
- `post node8 thr25`: node6=`9.00`, node7=`0.00`, node8=`9.333`
- `post node8 thr100`: node6=`9.333`, node7=`9.167`, node8=`9.00`

Interpretacion tecnica del rerun:

- El comando `SET_THROTTLE` ya no cae en `UNSUPPORTED_CMD` para nodos activos (6 y 8, y parcialmente 7).
- Hay confirmacion real de pipeline transaccional+ACK por nodo en hardware.
- Sin embargo, **no hay diferencia de cadencia EVT consistente entre 25% y 100%** en este banco de prueba.
- Revisando firmware actual:
  - `SET_THROTTLE` actualiza `g_plantThrottleMs` (runtime).
  - En `MODE_TEST + SENSOR_PLANT`, `servicePlantTest()` emite con `TEST_PLANT_EVENT_MS` fijo y no usa `g_plantThrottleMs`.
- Por lo tanto, en este modo de banco no se puede demostrar el efecto fisico de throttle por frecuencia de EVT.

Artefacto de evidencia de esta corrida:

- `artifacts/validation/ticket18_3_set_throttle_rerun_20260327_103402.json`

## 10) Siguiente paso operativo

1. Resolver la observabilidad de efecto throttle en banco:
   - opcion A: validar en `MODE_FIELD` con estimulo real de planta;
   - opcion B: micro-fix firmware para que `servicePlantTest()` respete `g_plantThrottleMs`.
2. Repetir secuencia `25 -> 100` por nodo con metrica EVT/pps y evidenciar diferencia real.
3. Confirmar estabilidad de `EC2` (`node_id=7`) para reducir timeouts intermitentes durante ventana de prueba.
4. Con esa evidencia, cerrar formalmente `TICKET 18.3`.
