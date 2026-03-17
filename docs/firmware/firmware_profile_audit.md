# Firmware Profile Audit (Ticket 12)

## 1. Proposito

Normalizar el firmware actual de nodo para separar con precision:

- firmware base,
- target formal,
- perfil desplegado,
- parametros operativos,
- metadatos/versionado.

El objetivo es habilitar implementaciones posteriores (control-plane F3, OTA, firmware manager) sin depender de macros dispersas ni decisiones implicitas.

## 2. Alcance y fuera de alcance

Alcance:

- Auditoria tecnica del sketch operativo compartido (`NODO - FPP`).
- Inventario real de macros/switches, perfiles y variantes.
- Definicion de targets y perfiles formales.
- Contrato minimo de metadatos de firmware.
- Clasificacion: compile-time vs runtime-configurable futuro vs no exponer remoto.

Fuera de alcance:

- Implementar CMD/ACK en firmware.
- OTA o firmware manager productivo.
- Refactor profundo del sketch.
- Cambios runtime en app CKv2.
- Cambios al contrato F3 ya congelado en `spec_control_f3.md`.

## 3. Insumos revisados

1. `NODO - FPP` (texto entregado por el usuario el 2026-03-17; sketch operativo unificado).
2. `spec_control_f3.md`.
3. `README.md`.
4. `docs/protocol/udp_bench_vs_okua_v1.md`.
5. Bundle bench v0 (como referencia historica, no como base principal de decision).

Nota de trazabilidad:

- Este documento prioriza `NODO - FPP` como fuente de verdad para el estado de firmware actual.
- Los artefactos bench se consideran antecedentes de laboratorio.

## 4. Resumen del sketch actual

El sketch `NODO - FPP` ya es una base unificada UDP OKUA v1 para ESP32 con:

- `MODE_TEST` y `MODE_FIELD`.
- `SENSOR_PLANT` y `SENSOR_FRUIT`.
- LED opcional (`LED_DISABLED` / `LED_SIMPLE`).
- Variante de deteccion de fruta (`FRUIT_VARIANT_V1` / `FRUIT_VARIANT_V2`).
- Paquetes OKUA v1 nativos:
  - `OkuaHdr` 8 bytes
  - `OkuaEvtPacket` 20 bytes
  - `OkuaStatPacket` 28 bytes
- Puertos:
  - EVT 5005
  - STAT 5006
  - CMD 5007 reservado
  - local 5008

Estado funcional relevante:

- No hay receptor de `CMD/ACK` aun (solo emision EVT/STAT).
- Existe logica de campo real para planta y fruta.
- Existe fanout de fruta mediante tabla `FRUIT_ROUTES`.
- Hay fuerte dependencia compile-time en macros de seleccion.

## 5. Inventario de macros y switches funcionales

### 5.1 Seleccion de modo/perfil global (alto impacto)

- `ACTIVE_MODE` (`MODE_TEST` / `MODE_FIELD`).
- `ACTIVE_SENSOR` (`SENSOR_PLANT` / `SENSOR_FRUIT`).
- `LED_PROFILE` (`LED_DISABLED` / `LED_SIMPLE`).
- `ACTIVE_FRUIT_VARIANT` (`FRUIT_VARIANT_V1` / `FRUIT_VARIANT_V2`).

Estas macros cambian rutas de ejecucion completas en `loop()`.

### 5.2 Identidad/red/protocolo (alto impacto)

- `NODE_LABEL`, `NODE_ID`.
- `WIFI_SSID`, `WIFI_PASS`, `WIFI_CHANNEL`, `PC_IP`.
- `EVT_PORT`, `STAT_PORT`, `CMD_PORT`, `UDP_LOCAL_PORT`.
- `FW_MAJOR`, `FW_MINOR`.
- `OKUA_MAGIC`, `OKUA_TYPE_*`, `EVT_FLAG_*`, `STATF_*`.

### 5.3 Hardware y mapeo MIDI (alto impacto)

- `PIN_SIGNAL`.
- LED compile-time: `DATA_PIN`, `LEDS_FISICOS`, `LEDS_POR_PIXEL`, `LED_BRIGHT`.
- Planta:
  - `PLANT_MIDI_BUS`, `PLANT_MIDI_CHANNEL_1B`, `PLANT_NOTE_LOW`, `PLANT_NOTE_HIGH`.
- Fruta:
  - tabla `FRUIT_ROUTES[]` + `FRUIT_ROUTE_COUNT`.
  - `FRUIT_KEEPALIVE_ENABLE`, `FRUIT_KEEPALIVE_MS`.

### 5.4 Temporizacion y calibracion (alto impacto)

- Red/estado: `WIFI_CONNECT_TIMEOUT_MS`, `WIFI_RETRY_DELAY_MS`, `STAT_INTERVAL_MS`.
- Prueba: `TEST_PLANT_EVENT_MS`, `TEST_FRUIT_TOUCH_EVERY_MS`, `TEST_FRUIT_TOUCH_LEN_MS`.
- Planta campo: `PLANT_THROTTLE_MS`, `PLANT_AUTOCAL_MS`, `PLANT_NOISE_FLOOR`, `PLANT_SMOOTH_A`, `PLANT_BASE_A`, `PLANT_TOUCH_GAIN`, `PLANT_MAX_JUMP_ST`.
- Fruta campo: `FRUIT_FILTER_ALPHA`, `FRUIT_VAR_ALPHA`, `FRUIT_BASE_A`, `FRUIT_BASE_CLAMP_MIN`, `FRUIT_AUTOCAL_FAST_MS`, `FRUIT_AUTOCAL_REFINE_MS`, `FRUIT_HARD_TIMEOUT_MS`, `FRUIT_RECOVERY_MS`, mas parametros `FruitDetectParams`.

## 6. Inventario de perfiles/variants/modos detectados

Modos reales en el sketch:

1. `MODE_TEST`
2. `MODE_FIELD`

Sensores/perfiles base:

1. `SENSOR_PLANT`
2. `SENSOR_FRUIT`

Variantes reales de deteccion fruta:

1. `FRUIT_VARIANT_V1`
2. `FRUIT_VARIANT_V2`

Variantes operativas por ruteo fruta:

- `FRUIT_ROUTES` permite fanout multi-canal/multi-nota.
- Ejemplo en comentario: EB1 multi-canal; EC1 un solo canal.

## 7. Analisis especifico de variantes de fruta

### EB1

En el sketch, EB1 aparece como **preset de ruteo** (fanout de varias rutas), no como algoritmo separado.

### EC1

No aparece literal `EC1` en macros, pero el comportamiento equivalente "simple/dedicado" se modela naturalmente como preset de ruteo de 1 sola ruta.

### Otras variantes reales

- Existen dos variantes de deteccion reales (`V1`, `V2`) que afectan umbrales/histeresis/tiempos de deteccion (estructura `FruitDetectParams`).

### Decision formal EB1/EC1

`EB1` y `EC1` deben modelarse como **perfiles desplegados distintos** del mismo target de firmware, diferenciados por `route_preset` (y opcionalmente por variante de deteccion), no como binarios diferentes en esta fase.

Justificacion:

- La diferencia funcional observada entre EB1 y un caso simple proviene del ruteo (`FRUIT_ROUTES`), no de un core de firmware distinto.
- Separarlos como targets binarios ahora duplicaria mantenimiento sin necesidad tecnica inmediata.

## 8. Targets formales propuestos

### 8.1 Target de firmware (nivel binario)

- `okua_node_udp_v1`:
  - ESP32,
  - WiFi + UDP,
  - emision EVT/STAT OKUA v1,
  - soporte plant/fruit + test/field + fruit variants.

### 8.2 Targets/perfiles operativos (nivel despliegue)

| deploy_target | mode | sensor | fruta | objetivo |
|---|---|---|---|---|
| `plant` | `field` | `plant` | n/a | operacion planta |
| `fruit_eb1` | `field` | `fruit` | `v1` o `v2` | fruta con fanout multi-ruta |
| `fruit_ec1` | `field` | `fruit` | `v1` o `v2` | fruta simple (ruta unica) |
| `lab_test` | `test` | `plant` o `fruit` | segun prueba | validacion controlada |
| `diagnostics` | `field` | segun caso | segun caso | soporte tecnico/diagnostico |

### 8.3 `mac_debug` / `id_debug`

No deben crearse como target binario nuevo por defecto. Deben modelarse como `build_profile` o preset de diagnostico dentro de `diagnostics`.

## 9. Separacion conceptual recomendada

### Firmware base

- Protocolo OKUA v1, adquisicion ADC, logica plant/fruit, transporte UDP, estado/calibracion.

### Target

- Define plataforma/stack fijo (`okua_node_udp_v1`).

### Perfil desplegado

- Define intencion operacional (`plant`, `fruit_eb1`, `fruit_ec1`, `lab_test`, `diagnostics`).

### Parametros operativos

- Subset curado de parametros ajustables (no libres) para control remoto futuro.

Regla de gobernanza:

- El binario no debe codificar por defecto decisiones de sitio (SSID/pass/IP/rutas finales) sin capa de perfil/metadatos.

## 10. Metadatos minimos de firmware

Campos obligatorios recomendados:

- `firmware_family`
- `target`
- `variant`
- `version`
- `protocol_version`
- `build_profile`
- `changelog_short`
- `compatible_hw`
- `notes`
- `status` (`current`, `beta`, `obsolete`, `situational`)

Campos de trazabilidad recomendados:

- `deploy_target`
- `sensor_profile`
- `fruit_variant`
- `route_preset`
- `source_ref`
- `git_commit`
- `build_time_utc`

Ejemplo de manifest:

```json
{
  "firmware_family": "okua_node",
  "target": "okua_node_udp_v1",
  "deploy_target": "fruit_eb1",
  "variant": "fruit_v2",
  "version": "1.0.0",
  "protocol_version": "okua_v1",
  "build_profile": "field",
  "status": "current",
  "compatible_hw": ["esp32"],
  "sensor_profile": "fruit",
  "fruit_variant": "v2",
  "route_preset": "eb1_fanout_4ch",
  "changelog_short": "UDP OKUA v1 unified node baseline",
  "notes": "CMD_PORT reservado; sin receptor CMD/ACK aun",
  "source_ref": "NODO - FPP (2026-03-17)",
  "git_commit": "<to-fill>",
  "build_time_utc": "<to-fill>"
}
```

## 11. Clasificacion compile-time vs runtime-configurable vs no exponer

### A. Debe seguir compile-time

1. Estructuras binarias OKUA (`OkuaHdr`, `OkuaEvtPacket`, `OkuaStatPacket`) y tipos.
2. Invariantes de protocolo (`magic`, `ver`, layout, endianness).
3. Pines/hardware base (`PIN_SIGNAL`, wiring LED cuando aplique).
4. Limites de seguridad de algoritmo (rangos maximos/minimos hard cap).
5. Feature-gates estructurales de compilacion (inclusion de NeoPixel, etc.).

### B. Conviene volver runtime-configurable (futuro, con guardrails)

1. `set_profile`: seleccion de `deploy_target` permitido.
2. `set_stat_rate`: sobre `STAT_INTERVAL_MS` dentro de rango seguro.
3. `set_throttle`: sobre ritmo de emision dentro de rango seguro.
4. `set_debug`: nivel de telemetria acotado.
5. `request_stat_now`.
6. `reboot`.
7. `reset_calibration` (limpiar estado de auto-calibracion).
8. `set_route_preset` (solo presets whitelisteados: ej. `eb1_fanout_4ch`, `ec1_single`).

### C. No conviene exponer remotamente

1. `WIFI_SSID`, `WIFI_PASS`, `PC_IP`, `WIFI_CHANNEL`.
2. `NODE_ID`/identidad base sin proceso de provisionamiento controlado.
3. Edicion libre de tablas `FRUIT_ROUTES` por comando crudo.
4. Edicion libre de parametros analogicos internos (`FruitDetectParams`, ruido/base/sigma) en campo.
5. Cualquier constante que pueda degradar seguridad/estabilidad sin validacion fuerte.

## 12. Set curado recomendado para control remoto futuro

Set curado recomendado:

1. `reboot`
2. `reset_calibration`
3. `request_stat_now`
4. `set_profile`
5. `set_throttle`
6. `set_stat_rate`
7. `set_debug`
8. `set_route_preset` (opcional, whitelisteado)

Reglas obligatorias:

- Sin escritura arbitraria de constantes internas.
- Sin mutacion libre de tablas complejas.
- Validacion por rango, estado y perfil antes de aplicar.
- Registro de auditoria por comando/resultado segun contrato F3.

## 13. Riesgos si no se normaliza esto ahora

1. Binarios no trazables por mezclar modo/sensor/variant/rutas en macros sueltas.
2. Contaminacion de `MODE_TEST` en despliegue de campo.
3. Exposicion futura excesiva de parametros peligrosos.
4. Confusion operacional EB1/EC1 por ausencia de nomenclatura formal.
5. Friccion para OTA/manager por falta de metadatos consistentes.

## 14. Decisiones cerradas

1. El firmware base vigente a normalizar es `OKUA Node WiFi + UDP v1` (sketch unificado `NODO - FPP`).
2. Se adopta un unico target binario principal: `okua_node_udp_v1`.
3. `EB1` y `EC1` se formalizan como perfiles desplegados distintos (`fruit_eb1`, `fruit_ec1`) sobre el mismo target.
4. La diferencia EB1/EC1 se resuelve por `route_preset` (fanout vs simple), no por binario distinto en esta fase.
5. `fruit_variant` (`v1`/`v2`) es una dimension formal de perfil/metadato y no debe quedar implicita.
6. Se adopta politica conservadora de control remoto: solo set curado; no edicion arbitraria de constantes.
7. Se requiere metadato minimo obligatorio por build/artefacto para trazabilidad.

### 14.1 Respuestas explicitas a preguntas obligatorias

1. Modos reales: `MODE_TEST` y `MODE_FIELD`; sensores `PLANT` y `FRUIT`; LED `DISABLED/SIMPLE`; fruta `V1/V2`.
2. Macros de mayor impacto: `ACTIVE_MODE`, `ACTIVE_SENSOR`, `ACTIVE_FRUIT_VARIANT`, identidad/red, `FRUIT_ROUTES`, temporizaciones/calibracion.
3. Variantes de fruta reales: `FRUIT_VARIANT_V1` y `FRUIT_VARIANT_V2`, mas variantes de ruteo por `FRUIT_ROUTES`.
4. EB1/EC1: perfiles del mismo target (no targets binarios distintos en esta fase).
5. Quemado compile-time que conviene mover luego: perfil activo, stat rate, throttle, debug, route preset, reset calibration.
6. No exponer remoto: credenciales/red, identidad base sin provisionamiento, parametros internos crudos y tablas libres.
7. Metadatos minimos: seccion 10.
8. Naming formal:
   - target binario: `okua_node_udp_v1`
   - deploy targets: `plant`, `fruit_eb1`, `fruit_ec1`, `lab_test`, `diagnostics`
9. Fijo en binario: protocolo, estructuras, hardware base y limites de seguridad. Variable por despliegue: perfil/preset curado.
10. Evitar contaminacion test: separar `build_profile=field|test`, etiquetar `status`, y prohibir promotion a `current` si build es test.

## 15. Pendientes para tickets siguientes

1. Definir mecanismo de seleccion de perfil sin recompilar (persistencia local con whitelist).
2. Diseñar `route_preset` formal (IDs, tabla, validaciones, fallback seguro).
3. Definir contrato de `reset_calibration` por sensor.
4. Integrar metadatos en pipeline de build/artefacto.
5. Alinear Ticket 13 de control-plane con este modelo (sin abrir escritura arbitraria).
