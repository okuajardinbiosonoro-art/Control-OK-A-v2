# OTA Firmware Runtime Minimum (Ticket 25)

## Objetivo

Documentar la base mínima OTA que ahora existe dentro del firmware del nodo:

- identidad exacta del build en runtime,
- trigger OTA autenticado por F3,
- fetch/validación de manifest,
- descarga e instalación conservadora al slot OTA inactivo,
- health-check local,
- rollback local alineado con el bootloader OTA del ESP32.

Este documento complementa a `docs/firmware/ota_gate.md`.

## Identidad embebida del build

El firmware ahora configura y expone en runtime:

- `FW_VERSION_STR`
- `FW_VERSION_CODE`
- `FW_TARGET_KIND`
- `FW_TARGET_VARIANT`
- `FW_BUILD_PROFILE`
- `FW_PROTOCOL_VERSION`
- `FW_FIRMWARE_FAMILY`
- `FW_COMPATIBLE_HW`
- `FW_ARTIFACT_ID`
- `FW_ARTIFACT_SHA256`

Decisión importante:

- `FW_ARTIFACT_SHA256` y `FW_ARTIFACT_ID` no se resuelven como pseudo-constantes compile-time.
- Se obtienen del SHA-256 real de la partición en ejecución usando `esp_partition_get_sha256()`.
- Esto evita el problema autorreferencial de intentar incrustar el hash final del mismo bin antes de que exista.

Exposición actual:

- banner de arranque por `Serial`,
- getters runtime consumidos por la capa OTA,
- `fw_major/fw_minor` siguen viajando por `OKUA_STAT`,
- el `OKUA_STAT` v1 conserva su tamaño de 28 bytes, por lo que la identidad larga no viaja completa en cada STAT.

## Trigger OTA por control-plane

Se añadió el comando:

- `OKUA_CMD_OTA_CHECK_NOW = 0x08`

Semántica:

- es **solo unicast**,
- usa `arg0 + arg1` como `rollout_token` de 32 bits,
- no transporta URL completa,
- respeta el modelo autenticado actual de F3.

Codificación:

- `arg0 = rollout_token & 0xFFFF`
- `arg1 = rollout_token >> 16`

Si el token es cero:

- el firmware rechaza el comando con `INVALID_ARG`.

Si ya hay verificación OTA en curso:

- el firmware rechaza el comando con `BUSY`.

## Base URL y resolución del manifest

El nodo deriva la URL del manifest desde:

- `OKUA_OTA_BASE_URL`
- `rollout_token`

Formato actual:

```text
{base_url}/ota/rollouts/{rollout_token_hex_8}/manifest.json
```

Default actual:

```text
http://<PC_IP>:18080
```

donde `<PC_IP>` sale de los macros ya existentes del sketch.

## Manifest mínimo que valida el nodo

El firmware espera estos campos obligatorios:

- `schema_version`
- `rollout_id`
- `firmware_family`
- `target_kind`
- `target_variant`
- `compatible_hw`
- `build_profile`
- `protocol_version`
- `version`
- `version_code`
- `artifact_id`
- `sha256`
- `file_size`
- `download_url`
- `changelog_short`
- `rollout_channel`
- `published_at_utc`

También acepta `flags` opcionales:

- `reboot_required`
- `allow_auto_rollback`

## Validación de compatibilidad

Antes de descargar o instalar, el firmware rechaza si no coincide:

- `firmware_family`
- `target_kind`
- `target_variant`
- `compatible_hw`
- `build_profile`
- `protocol_version`

También rechaza si:

- `sha256` no tiene 64 hex,
- `artifact_id` no coincide con `sha256:<sha256>`,
- `file_size` es cero,
- `version_code` es menor al actual,
- `version_code` es igual al actual,
- el artifact del manifest ya es exactamente el que está corriendo.

El criterio de versión es estrictamente por `version_code`.

## Descarga e instalación OTA

La instalación mínima usa:

- `HTTPClient`
- `esp_ota_begin`
- `esp_ota_write`
- `esp_ota_end`
- `esp_ota_set_boot_partition`

Flujo:

1. descarga manifest,
2. parsea y valida,
3. descarga bin por HTTP,
4. calcula SHA-256 del stream descargado,
5. compara `sha256` y `file_size`,
6. escribe la imagen al slot OTA inactivo,
7. persiste en NVS la identidad esperada del nuevo build,
8. prepara reboot al slot nuevo.

Persistencia NVS actual:

- namespace: `okua_ota`
- claves:
  - `rollout`
  - `artifact`
  - `sha256`
  - `vercode`

## Health-check local

Cuando el bootloader deja la app en `PENDING_VERIFY`, el firmware entra en:

- `boot_validating`

Ventana actual:

- `45 s`

Para confirmar la nueva app como válida exige:

- Wi-Fi operativo,
- loop principal corriendo,
- al menos un `OKUA_STAT` emitido,
- identidad exacta del build coincidente con lo persistido en NVS.

Si todo pasa:

- llama `esp_ota_mark_app_valid_cancel_rollback()`,
- limpia la expectativa OTA persistida,
- marca estado `boot_confirmed`.

## Rollback local conservador

Si la nueva app no supera la validación local:

- timeout de Wi-Fi,
- timeout sin `STAT`,
- mismatch de identidad,
- fallo al marcar la app como válida,

el firmware ejecuta:

- `esp_ota_mark_app_invalid_rollback_and_reboot()`

Si esa llamada no es posible:

- cae al reinicio local como último recurso.

## Exposición runtime mínima

Los 3 bytes `rsv` de `OKUA_STAT` ahora se usan así:

- `rsv[0] = ota_state_code`
- `rsv[1] = ota_error_code`
- `rsv[2] = ota_flags`

Estados runtime actuales:

- `idle`
- `triggered`
- `fetching_manifest`
- `validating_manifest`
- `downloading`
- `ready_reboot`
- `boot_validating`
- `boot_confirmed`
- `error`

Errores runtime actuales:

- `manifest_http`
- `manifest_parse`
- `manifest_incompatible`
- `version_rejected`
- `already_current`
- `download_http`
- `download_size`
- `download_hash`
- `ota_begin`
- `ota_write`
- `ota_finalize`
- `boot_wifi_timeout`
- `boot_stat_timeout`
- `boot_identity_mismatch`
- `boot_validate`
- `nvs_error`

Flags actuales:

- `check_pending`
- `pending_reboot`
- `pending_verify`
- `health_confirmed`

La app CKv2 ya decodifica estos bytes para no quedar ciega ante el proceso OTA.

## Limitaciones explícitas de este corte

Este ticket **no** implementa todavía:

- publicación automática de manifest desde la app,
- servidor OTA funcional del PC,
- UI de campañas OTA,
- rollback remoto arbitrario,
- firma digital fuerte del manifest o del bin,
- exposición completa de la identidad larga en `OKUA_STAT` v1.

La limitación de identidad larga en STAT es intencional:

- el paquete `OKUA_STAT` sigue congelado en 28 bytes,
- por eso el detalle completo del artifact queda en runtime firmware/serial y en la lógica OTA,
- mientras que por STAT sólo viaja la telemetría compacta del estado OTA.
