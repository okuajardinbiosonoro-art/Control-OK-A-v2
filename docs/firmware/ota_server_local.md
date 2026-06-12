# Servidor OTA local y publicación de rollouts (Ticket 26)

## Objetivo

Documentar el backend OTA app-side que ahora existe en CKv2 para:

- construir `manifest.json` OTA desde un `FirmwareArtifact`,
- publicar un rollout local autocontenido,
- servir el manifest y el bin por HTTP desde el PC del sitio,
- mantener compatibilidad exacta con el cliente OTA mínimo del Ticket 25.

Este documento complementa:

- `docs/firmware/ota_gate.md`
- `docs/firmware/ota_firmware_runtime.md`

## Estructura local publicada

El backend publica rollouts bajo un root HTTP local aislado:

```text
artifacts/ota_publish/
  ota/
    rollouts/
      <rollout_token_hex>/
        manifest.json
        firmware.bin
```

Ejemplo:

```text
artifacts/ota_publish/ota/rollouts/20260328/manifest.json
artifacts/ota_publish/ota/rollouts/20260328/firmware.bin
```

Razón de esta forma:

- el árbol publicado queda autocontenido por rollout,
- es fácil de inspeccionar y auditar,
- y coincide exactamente con la convención de URL que ya espera el firmware.

## Relación entre rollout_token y rollout_id

Se congeló esta separación:

- `rollout_token`: identificador corto de 32 bits que viaja por F3 y que el firmware convierte a hex de 8 caracteres para resolver la URL.
- `rollout_id`: identificador humano/auditable que vive dentro del manifest y sirve para trazabilidad operativa.

Ejemplo:

- `rollout_token = 0x20260328`
- directorio publicado: `.../ota/rollouts/20260328/`
- `rollout_id = plant-eb1-2026-03-28-r1`

El firmware consulta:

```text
http://<PC_IP>:<puerto_ota>/ota/rollouts/20260328/manifest.json
```

pero dentro del manifest recibe además:

```json
{
  "rollout_id": "plant-eb1-2026-03-28-r1"
}
```

## Contrato del manifest publicado

El backend publica exactamente los campos que valida el firmware OTA del Ticket 25:

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
- `rollout_channel`
- `changelog_short`
- `published_at_utc`
- `flags.reboot_required`
- `flags.allow_auto_rollback`

## Fuente de verdad y validaciones previas

El manifest se construye desde el catálogo actual, no desde JSON manual.

Antes de publicar un rollout, CKv2 valida:

- que el `artifact_id` exista en el catálogo,
- que `target_kind` no sea `unknown`,
- que el artifact no esté en `obsolete`,
- que el bin exista realmente,
- que el bin venga del managed store,
- que el archivo sea `.bin`,
- que `sha256` y `file_size` del archivo real coincidan con el catálogo,
- que la `version` pueda derivar un `version_code` semver (`MAJOR.MINOR.PATCH`),
- que `download_url` y `manifest_url` sean coherentes con `host`, `port` y `rollout_token`.

## version_code

Como el catálogo actual no persiste `version_code` explícito, el backend OTA lo deriva desde `artifact.version` con la convención congelada en el gate:

```text
major * 10000 + minor * 100 + patch
```

Ejemplo:

- `1.2.3 -> 10203`
- `3.4.5 -> 30405`

Si `artifact.version` no cumple semver básico, el rollout se rechaza.

## URLs publicadas

Con `host=192.0.2.10`, `port=18080` y `rollout_token=0x20260328`:

- manifest:

```text
http://192.0.2.10:<puerto_ota>/ota/rollouts/20260328/manifest.json
```

- bin:

```text
http://192.0.2.10:<puerto_ota>/ota/rollouts/20260328/firmware.bin
```

Estas URLs son exactamente compatibles con la resolución actual del firmware.

## Publicación e idempotencia

`OtaManifestService.publish_rollout()`:

1. carga y valida el artifact del catálogo,
2. verifica integridad del bin real en managed store,
3. construye el manifest OTA,
4. publica `firmware.bin` y `manifest.json` de forma atómica,
5. devuelve rutas locales y URLs resueltas.

Si el mismo `rollout_token` ya está publicado con el mismo contenido:

- el backend reutiliza el rollout existente,
- no duplica archivos,
- y devuelve una advertencia explícita.

Si el `rollout_token` ya existe con otro contenido:

- la publicación se rechaza.

## Servidor OTA local

Nota operativa de esta rama:

- CKv2 fija `18080` como puerto OTA local para las campañas desde la app.
- `OtaServerService` sigue siendo configurable si se usa de forma manual fuera de la app.
- El firmware del nodo debe compilarse con el mismo puerto OTA (`OKUA_OTA_PORT` o `OKUA_OTA_BASE_URL`).

`OtaServerService` usa un servidor HTTP mínimo basado en la librería estándar:

- `ThreadingHTTPServer`
- `SimpleHTTPRequestHandler`

Características:

- `root_dir` configurable,
- `bind_host` configurable,
- `port` configurable,
- logs básicos por request,
- sin UI web, sin framework web pesado y sin lógica de negocio mezclada.

## Flujo manual mínimo

1. Importar un `.bin` al catálogo con `FirmwareIngestService`.
2. Publicar un rollout con `OtaManifestService`.
3. Iniciar `OtaServerService`.
4. Verificar:
   - `GET /ota/rollouts/<token>/manifest.json`
   - `GET /ota/rollouts/<token>/firmware.bin`
5. Disparar luego el `OTA_CHECK_NOW` por F3 en el ticket siguiente de orquestación.

## Fuera de alcance intencional

Este backend todavía no implementa:

- UI OTA grande,
- selección de nodos o lotes,
- campañas canary,
- publicación automática desde Firmware Manager,
- permisos remotos,
- TLS fuerte o firma digital del manifest/bin,
- despliegue end-to-end desde la app.

## Siguiente paso natural

Sobre esta base, el siguiente ticket OTA puede enfocarse ya en:

- disparo operator-driven desde CKv2 hacia nodos concretos,
- seguimiento de rollout,
- confirmación observada post-reboot,
- y superficie técnica mínima para lanzar/monitorear el despliegue.
