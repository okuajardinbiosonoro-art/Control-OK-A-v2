# UDP BenchPktV0 vs OKUA v1 (CKv2)

## Objetivo

Documentar por que el emisor bench antiguo no es compatible con el runtime UDP real de CKv2 y definir la base correcta para pruebas de laboratorio.

## Contrato que CKv2 consume hoy (OKUA v1)

- Endianness: little-endian.
- Header comun: `<HBBHH` (8 bytes)
  - `magic` = `0x4B4F`
  - `ver` = `1`
  - `type` = `1` (EVT) o `2` (STAT)
  - `node_id` = `uint16`
  - `seq` = `uint16`
- `OKUA_EVT`: 20 bytes totales (`header=8` + payload=12).
- `OKUA_STAT`: 28 bytes totales (`header=8` + payload=20).
- Canales:
  - `EVT` entra por `udp.evt_port` (default `5005`)
  - `STAT` entra por `udp.stat_port` (default `5006`)

## Wire format bench legado detectado (BenchPktV0)

- `ver = 0`
- Longitud fija = 32 bytes
- Tipos legacy (`MSG_EVT`, `MSG_STAT`, `MSG_PING`, `MSG_PONG`)
- Tramas enviadas al mismo puerto (`5005`)
- Campos auxiliares de laboratorio (RTT/aux/PONG) fuera del contrato OKUA v1

## Diagnostico de incompatibilidad

1. CKv2 valida version antes de parsear payload. `ver=0` dispara `unsupported_version`.
2. CKv2 separa EVT y STAT por puertos distintos (`5005` / `5006`), pero bench antiguo mezcla todo en `5005`.
3. CKv2 espera longitudes exactas por tipo (20/28), bench usa 32 bytes fijos.

Conclusión: BenchPktV0 no es compatible como wire format final para CKv2.

## Estrategia adoptada (obligatoria)

- El parser productivo de CKv2 se mantiene estricto para OKUA v1.
- El emisor de pruebas se alinea al wire format real (OKUA v1).
- Si se requiere compatibilidad bench, debe ser explicita y separada en tooling de laboratorio, nunca mezclada de forma opaca en el camino productivo.

## Artefacto de prueba incluido

Se agrega `tools/udp_okua_v1_sender.py`:

- Construye `EVT` validos de 20 bytes.
- Construye `STAT` validos de 28 bytes.
- Envia por puertos separados:
  - EVT -> `--evt-port` (default `5005`)
  - STAT -> `--stat-port` (default `5006`)
- Modo reproducible:
  - `--dry-run` imprime hex/longitudes.
  - `--ts-ms-start` fija timestamp base para pruebas deterministas.

Ejemplos:

```powershell
# Ver vectores sin enviar trafico
python tools/udp_okua_v1_sender.py --dry-run

# Enviar 50 iteraciones EVT+STAT a CKv2 local
python tools/udp_okua_v1_sender.py --host 127.0.0.1 --evt-port 5005 --stat-port 5006 --count 50 --interval-ms 20
```

## Mejora menor de diagnostico (runtime/parser)

Cuando llega `ver=0` y `len=32`, CKv2 conserva el error `unsupported_version` pero anade un hint tecnico:

- posible patron `BenchPktV0`
- recordatorio del contrato esperado:
  - `EVT=20` por `5005`
  - `STAT=28` por `5006`

Esto mejora troubleshooting sin relajar el parser productivo.
