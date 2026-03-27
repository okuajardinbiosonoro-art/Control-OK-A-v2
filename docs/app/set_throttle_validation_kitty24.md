# TICKET 18.3 - Validacion real multi-nodo de `SET_THROTTLE` en `Kitty_2.4`

## 1) Objetivo

Validar end-to-end en hardware real el segundo `SET_*` curado (`SET_THROTTLE`) desde CKv2 ejecutado con:

- `python main.py`
- panel `Control F3`
- nodos de prueba: `EB2 (node_id=6)`, `EC2 (node_id=7)`, `ED2 (node_id=8)`

## 2) Prerequisitos

1. Red Wi-Fi activa: `Kitty_2.4`.
2. Host CKv2 alcanzable por los nodos con la IP cargada en firmware (`192.168.1.57`).
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

## 9) Corrida ejecutada en este entorno (2026-03-27)

Resultado: **bloqueada por precondicion de red/IP**.

Evidencia recolectada:

1. `netsh wlan show interfaces`:
   - SSID actual: `Integra f(x) = ln(x)`
2. `ipconfig`:
   - IPv4 Wi-Fi actual: `172.20.10.3`
3. Sondeo UDP directo (`0.0.0.0:5005/5006`, 12 s):
   - paquetes recibidos: `{5005: 0, 5006: 0}`
4. App local:
   - `python main.py` abre/cierra correctamente en este host, pero no hay base de red para validar nodos `Kitty_2.4`.

Conclusiones de la corrida:

- No se cumple la precondicion de red para validar `EB2/EC2/ED2`.
- No hay evidencia valida de ACK real ni de cambio de throttle en hardware en este estado de red.
- **No se puede declarar cerrado formalmente el TICKET 18.3** hasta repetir esta secuencia en `Kitty_2.4` con host alineado a la IP configurada en nodos.

## 10) Siguiente paso operativo

1. Conectar la PC a `Kitty_2.4`.
2. Confirmar IP del host igual a la cargada en nodos (actualmente `192.168.1.57`).
3. Repetir la secuencia del punto 4 para `EB2`, `EC2` y `ED2`.
4. Consolidar evidencia final de ACK + cambio de ritmo + aislamiento por nodo.
