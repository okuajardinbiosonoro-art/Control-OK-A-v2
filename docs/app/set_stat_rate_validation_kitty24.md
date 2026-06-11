# TICKET 17.3 - Validacion real multi-nodo `SET_STAT_RATE` en `Kitty_2.4`

## 1) Objetivo

Validar end-to-end en hardware real el primer `SET_*` curado (`SET_STAT_RATE`) con banco local:

- `EB2` (`node_id=6`)
- `EC2` (`node_id=7`)
- `ED2` (`node_id=8`)

Ejecutado sobre repo local (no `.exe`) con referencias de operacion de `python main.py`.

## 2) Precondiciones del run

1. PC y nodos en LAN `192.168.1.x` (nodos en SSID `Kitty_2.4`).
2. IP destino configurada en firmware: `192.0.2.10`.
3. Secret de control disponible en:
   - `firmware/okua_node_udp_v1/okua_node_secrets.h`
4. Allowlist curada vigente:
   - `1000 ms`
   - `2000 ms`
   - `5000 ms`

## 3) Verificacion de precondicion de red (2026-03-27)

- `ipconfig`: interfaz activa con IPv4 `192.0.2.10`.
- `netsh wlan show interfaces`: adaptador Wi-Fi reportado como desconectado.
- La validacion se ejecuto con conectividad real en la misma LAN de los nodos (tramas EVT/STAT y ACK recibidas en esta maquina).

## 4) Nodos detectados y resueltos

Discovery inicial de corrida principal (STAT/5006):

- `node_id=6` -> `192.0.2.10`
- `node_id=7` -> `192.0.2.10`
- `node_id=8` -> `192.0.2.10`

Artefacto de evidencia:

- `artifacts/ticket17_3_set_stat_rate_kitty24_20260327.json`

## 5) Secuencia aplicada por nodo

Por cada nodo validado:

1. Medir baseline de cadencia STAT.
2. Enviar `SET_STAT_RATE=1000`.
3. Verificar ACK y medir cadencia.
4. Enviar `SET_STAT_RATE=5000`.
5. Verificar ACK y medir cadencia.
6. Enviar `SET_STAT_RATE=2000` (cierre operativo).
7. Verificar ACK y medir cadencia.

## 6) Resultado por nodo (ACK + cadencia)

### 6.1 EB2 (`node_id=6`, `ip=192.0.2.10`)

Corrida de seguimiento para estabilizar evidencia de ACK:

- `SET_STAT_RATE=1000`:
  - `final_status=ack_matched`, `ack_stage=1`, `status_code=0`, `err_detail=0`
  - cadencia observada: mediana `1.000 s`
- `SET_STAT_RATE=5000`:
  - `final_status=ack_matched`, `ack_stage=1`, `status_code=0`, `err_detail=0`
  - cadencia observada: mediana `5.032 s`
- `SET_STAT_RATE=2000`:
  - `final_status=ack_matched`, `ack_stage=1`, `status_code=0`, `err_detail=0`
  - cadencia observada: mediana `2.016 s`

Nota de campo: hubo jitter/picos esporadicos de red (intervalos largos aislados), pero la mediana siguio la cadencia objetivo.

### 6.2 EC2 (`node_id=7`, `ip=192.0.2.10`)

- `SET_STAT_RATE=1000`:
  - `final_status=ack_matched`, `ack_stage=1`, `status_code=0`, `err_detail=0`
  - cadencia observada: mediana `1.000 s`
- `SET_STAT_RATE=5000`:
  - `final_status=ack_matched`, `ack_stage=1`, `status_code=0`, `err_detail=0`
  - cadencia observada: mediana `5.000 s`
- `SET_STAT_RATE=2000`:
  - `final_status=ack_matched`, `ack_stage=1`, `status_code=0`, `err_detail=0`
  - cadencia observada: mediana `2.000 s`

### 6.3 ED2 (`node_id=8`, `ip=192.0.2.10`)

- `SET_STAT_RATE=1000`:
  - `final_status=ack_matched`, `ack_stage=1`, `status_code=0`, `err_detail=0`
  - cadencia observada: mediana `1.000 s`
- `SET_STAT_RATE=5000`:
  - `final_status=ack_matched`, `ack_stage=1`, `status_code=0`, `err_detail=0`
  - cadencia observada: mediana `4.992 s` (aprox. `5 s`)
- `SET_STAT_RATE=2000`:
  - `final_status=ack_matched`, `ack_stage=1`, `status_code=0`, `err_detail=0`
  - cadencia observada: mediana `2.000 s`

## 7) Aislamiento multi-nodo (verificado)

Se observo aislamiento correcto por nodo durante la secuencia:

- Al cambiar `node_id=7` entre `1000/5000/2000`, `node_id=6` y `node_id=8` se mantuvieron en su cadencia previa.
- Al cambiar `node_id=8`, `node_id=6` y `node_id=7` no fueron contaminados.
- Al cambiar `node_id=6`, `node_id=7` y `node_id=8` conservaron su cadencia esperada.

## 8) Semantica runtime-only / reboot

No cerrada en esta corrida:

- La comprobacion formal `SET_STAT_RATE -> REBOOT_SOFT -> default` queda pendiente para corrida dedicada.
- Se priorizo no interferir con una instancia activa de `main.py`/puertos en paralelo durante esta validacion.

## 9) Criterio de cierre del primer `SET_*`

Estado final de 17.3 en banco `Kitty_2.4`: **cumplido**.

Checklist:

- `SET_STAT_RATE` validado en hardware real multi-nodo.
- ACK correcto (`ACCEPTED + OK`) en valores permitidos.
- Cambio de cadencia real demostrado (`1000`, `5000`, `2000`).
- Aislamiento multi-nodo verificado.
- Sin abrir otros `SET_*`.
