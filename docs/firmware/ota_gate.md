# OTA Technical Gate for CKv2 (Ticket 24)

## 1. Objetivo

Congelar la arquitectura OTA de CKv2 antes de implementar:

- cliente OTA en firmware,
- orquestación OTA en la app,
- publicación de manifests,
- despliegues reales a nodos.

Este documento es el gate técnico para Ticket 25+.

Resultado del gate:

- **GO condicionado** para una primera OTA conservadora basada en `HTTP pull + manifest + dual-slot OTA`.
- La viabilidad de partición y tamaño es **positiva** con el firmware actual.
- La implementación OTA queda **bloqueada** hasta agregar identidad embebida exacta del build y el cliente OTA mínimo en firmware.

## 2. Estado actual auditado

### 2.1 Fuente auditada

Se revisó el estado real del repo en `2026-03-28` a partir de:

- `platformio.ini`
- `firmware/okua_node_udp_v1/okua_node_udp_v1.cpp`
- `firmware/okua_node_udp_v1/okua_control_plane.h`
- `docs/firmware/firmware_profile_audit.md`
- artefactos ya presentes en `.pio/build/okua_node_esp32dev/`
- `idedata.json` del build previo

Nota operativa:

- En este shell no está disponible `pio`, por lo que la auditoría de firmware se basó en artefactos de build ya generados y en metadatos persistidos por PlatformIO.

### 2.2 Build y plataforma observados

- Entorno PlatformIO: `okua_node_esp32dev`
- Board: `esp32dev`
- Framework: Arduino sobre ESP32
- Define observada: `ARDUINO_PARTITION_default`
- `application_offset`: `0x10000`

### 2.3 Particionado observado

La tabla `default.csv` del framework activo define:

- `nvs`: `0x5000`
- `otadata`: `0x2000`
- `app0`: `0x140000`
- `app1`: `0x140000`
- `spiffs`: `0x160000`
- `coredump`: `0x10000`

Conclusión:

- El build actual ya está montado sobre un esquema **dual-slot OTA**.
- No hace falta inventar una estrategia sin rollback físico; la base de particiones ya permite `ota_0` / `ota_1`.

### 2.4 Tamaño del bin observado

Artefacto observado:

- `.pio/build/okua_node_esp32dev/firmware.bin`
- tamaño: `756688` bytes

Capacidad por slot OTA (`0x140000`):

- `1310720` bytes

Margen libre observado por slot:

- `554032` bytes

Conclusión:

- El firmware actual **sí cabe** en el slot OTA actual.
- El margen actual es razonable para un primer corte OTA conservador, pero no tan amplio como para permitir crecimiento descontrolado del sketch.

### 2.5 Metadatos y señales ya existentes en firmware

El firmware actual ya expone o infiere:

- `FW_MAJOR`
- `FW_MINOR`
- `uptime_s`
- `reset_reason`
- `boot_marker4`
- `STATF_CALIBRATING`
- `state_flags`
- conectividad Wi-Fi y envío periódico de `STAT`

La app CKv2 ya sabe observar:

- reboot reciente,
- cambio de `boot_marker`,
- `reset_reason`,
- transición a `calibrating`,
- transición a `online / degraded / offline`,
- estado runtime por nodo con reasons y eventos recientes.

### 2.6 Brechas actuales para OTA real

El firmware actual **no** tiene todavía:

- cliente OTA,
- consumidor de manifest,
- identidad embebida exacta del artefacto,
- validación OTA por target/variant,
- health-check local del nuevo build,
- confirmación/rollback del boot OTA,
- comando de control-plane dedicado a iniciar la comprobación OTA.

## 3. Supuestos y restricciones congelados

### 3.1 Supuestos

- Los nodos seguirán siendo ESP32 compatibles con el entorno `esp32dev`.
- El flujo operativo seguirá siendo site-local y operator-driven.
- CKv2 seguirá siendo la fuente de verdad del catálogo de firmware y del rollout.
- La red del sitio seguirá siendo una LAN controlada donde el PC del sitio puede servir HTTP local.

### 3.2 Restricciones

- El router MikroTik **no** será servidor OTA.
- El primer corte OTA no intentará resolver firma digital completa, canary complejo, fleet management remoto ni UI masiva.
- No se hará downgrade automático genérico por versión; el primer corte será conservador y sólo instalará upgrades compatibles o rollback al slot previo.
- `target_kind=unknown` queda excluido de OTA.

## 4. Decisiones congeladas

### 4.1 Estrategia OTA elegida

**Decisión congelada**

- La estrategia OTA de CKv2 será **HTTP pull OTA**.
- El bin será servido por **HTTP desde el PC del sitio**.
- El nodo descargará un **manifest JSON** y, si aplica a su target y versión, descargará el bin.
- La descarga ocurrirá sobre el **slot OTA inactivo** y no sobre la partición activa.

### 4.2 Modelo operativo del primer corte

**Decisión congelada**

- El primer corte OTA será **operator-triggered**, no un autopolling permanente.
- CKv2 seleccionará nodos o lote y disparará una acción futura de control-plane para que el nodo haga `OTA check now`.
- El nodo hará `pull` de manifest y bin solo después de ese trigger autenticado.

Justificación:

- preserva control operativo,
- reduce ruido de red,
- evita que todos los nodos de un target se autoactualicen por accidente,
- encaja con el control-plane F3 ya existente.

### 4.3 Identificador de rollout

**Decisión congelada**

- El trigger OTA no transportará una URL completa dentro de F3.
- El trigger futuro transportará un `rollout_id` corto o identificador equivalente.
- La URL final del manifest se derivará a partir de una base URL local del sitio.

Motivo:

- los frames F3 actuales son compactos,
- una URL completa no cabe limpia ni robustamente en ese canal,
- un `rollout_id` es suficiente y más seguro.

## 5. Versionado e identidad embebida

## 5.1 Problema del estado actual

Hoy el firmware sólo expone `FW_MAJOR` y `FW_MINOR`.

Eso no alcanza para OTA seria porque no permite:

- distinguir dos builds distintos con mismo `major.minor`,
- confirmar exactamente qué artefacto del catálogo está corriendo,
- correlacionar despliegue, health-check y rollback con un artifact concreto.

## 5.2 Contrato mínimo congelado para firmware OTA

Antes de desplegar OTA real, el firmware deberá embebir como constantes o metadatos de build:

- `FW_VERSION_STR`
- `FW_VERSION_CODE`
- `FW_TARGET_KIND`
- `FW_TARGET_VARIANT`
- `FW_BUILD_PROFILE`
- `FW_PROTOCOL_VERSION`
- `FW_ARTIFACT_ID`
- `FW_ARTIFACT_SHA256`

Semántica congelada:

- `FW_VERSION_STR`: string legible estilo `MAJOR.MINOR.PATCH[-prerelease]`
- `FW_VERSION_CODE`: entero monotónico para comparación en firmware
- `FW_TARGET_KIND`: por ejemplo `plant`, `fruit`, `lab_test`, `diagnostics`
- `FW_TARGET_VARIANT`: por ejemplo `eb1`, `ec1`, `generic`
- `FW_BUILD_PROFILE`: `field`, `test`, `diagnostics`
- `FW_PROTOCOL_VERSION`: `okua_v1`
- `FW_ARTIFACT_ID`: identidad del artefacto del catálogo
- `FW_ARTIFACT_SHA256`: hash completo del bin esperado

## 5.3 Regla de comparación de versión

**Decisión congelada**

- El firmware comparará versiones por `FW_VERSION_CODE`, no por string.
- `FW_VERSION_STR` y `version_label` seguirán siendo display/humano.
- El primer corte OTA no instalará versiones con `version_code` menor al actual salvo flujo explícito de rollback.

Formato recomendado:

- `major.minor.patch`
- `version_code = major * 10000 + minor * 100 + patch`

## 5.4 Compatibilidad con CKv2 actual

**Decisión congelada**

- El campo `version` del catálogo de CKv2 seguirá siendo obligatorio y se mapeará al `FW_VERSION_STR`.
- `version_label` seguirá siendo opcional y puramente humano.
- `artifact_id` y `sha256` del catálogo serán la base de la identidad OTA.

## 6. Manifest OTA congelado

## 6.1 Contrato mínimo

**Decisión congelada**

El manifest OTA mínimo del primer corte tendrá este contrato conceptual:

```json
{
  "schema_version": 1,
  "rollout_id": "plant-eb1-2026-03-28-r1",
  "firmware_family": "okua_node_udp_v1",
  "target_kind": "plant",
  "target_variant": "eb1",
  "compatible_hw": ["esp32dev"],
  "build_profile": "field",
  "protocol_version": "okua_v1",
  "version": "1.1.0",
  "version_code": 10100,
  "artifact_id": "sha256:0123456789abcdef...",
  "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "file_size": 756688,
  "download_url": "http://192.168.88.254:8080/ota/artifacts/0123456789abcdef.bin",
  "changelog_short": "Ajuste de runtime y observabilidad",
  "rollout_channel": "stable",
  "published_at_utc": "2026-03-28T21:30:00Z",
  "flags": {
    "reboot_required": true,
    "allow_auto_rollback": true
  }
}
```

## 6.2 Campos obligatorios

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

## 6.3 Reglas del manifest

**Decisiones congeladas**

- El manifest es **inmutable** una vez publicado.
- Un `rollout_id` apunta a un solo artefacto.
- No se reaprovecha el mismo `rollout_id` para otro bin.
- `target_kind`, `target_variant`, `compatible_hw` y `build_profile` deben coincidir con el firmware que pretende instalarse.
- `download_url` debe apuntar a un bin que coincide exactamente con `sha256` y `file_size`.
- `rollout_channel` del primer corte será uno de:
  - `stable`
  - `beta`
  - `situational`

Regla:

- `obsolete` no se publica como rollout OTA.

## 6.4 Relación con el catálogo de firmware

**Decisión congelada**

El manifest se genera a partir de un artefacto existente del catálogo CKv2 y de metadata de rollout.

Campos que vienen del catálogo actual:

- `artifact_id`
- `sha256`
- `file_size`
- `version`
- `version_label`
- `target_kind`
- `target_variant`
- `changelog`
- `status`

Campos de rollout que se agregan al publicar:

- `rollout_id`
- `download_url`
- `rollout_channel`
- `published_at_utc`

## 7. Integridad, autenticidad mínima y seguridad

## 7.1 Integridad obligatoria

**Decisión congelada**

La integridad mínima del primer corte OTA se basa en:

- `sha256` completo del bin,
- `file_size` exacto,
- coincidencia exacta entre manifest y bin descargado.

El nodo debe:

1. descargar el manifest,
2. validar `target_kind`, `target_variant`, `compatible_hw`, `build_profile`, `version_code`,
3. descargar el bin,
4. calcular `sha256`,
5. comparar `sha256` y `file_size`,
6. rechazar la instalación si cualquiera de esas validaciones falla.

## 7.2 Prevención de target incorrecto

**Decisión congelada**

Para impedir que un firmware de planta termine en fruta o viceversa, el nodo debe requerir coincidencia exacta de:

- `firmware_family`
- `target_kind`
- `target_variant`
- `compatible_hw`
- `protocol_version`

Además:

- CKv2 no publicará rollout OTA para artefactos con target `unknown`.
- El Firmware Manager/catalog store sigue siendo la fuente de verdad del target del artefacto.

## 7.3 Autenticidad mínima del primer corte

**Decisión congelada**

El primer corte OTA tendrá autenticidad operativa mínima basada en:

- trigger OTA vía control-plane autenticado con secreto compartido F3,
- servidor OTA local en el PC del sitio,
- LAN controlada del sitio,
- manifest inmutable por rollout,
- validación estricta de target + hash.

Lo que **no** queda resuelto en este ticket:

- firma digital de manifest,
- firma digital del bin,
- TLS mutuo o pinning de certificado,
- autorización remota multiusuario.

Esto queda congelado como hardening posterior.

## 8. Servidor OTA congelado

## 8.1 Ubicación

**Decisión congelada**

El servidor OTA del primer corte vivirá en el **PC del sitio**.

No vivirá en:

- router MikroTik,
- nube,
- servidor remoto externo,
- móvil.

## 8.2 Razones para no usar el router

- El router no es el lugar correcto para custodiar artifacts y manifests del catálogo.
- No queremos mezclar funciones de red con lógica de publicación OTA.
- El router complica trazabilidad, versionado y depuración.
- CKv2 ya vive en el PC del sitio y ahí está el catálogo y el managed firmware store.
- El PC del sitio permite logs, validación, publicación controlada y evolución futura sin depender de firmware del router.

## 8.3 Forma del servidor OTA

**Decisión congelada**

El primer corte usará un servidor HTTP local sobrio y read-only servido por el PC del sitio.

Ubicación lógica recomendada:

- artifacts fuente: managed store actual de CKv2
- publicación OTA: carpeta derivada o vista publicada, por ejemplo:
  - `artifacts/ota_publish/<rollout_id>/manifest.json`
  - `artifacts/ota_publish/artifacts/<sha256>.bin`

Puerto por defecto congelado:

- `8080`

Debe poder cambiarse por configuración luego, pero el valor por defecto queda congelado en `8080`.

## 9. Health-check congelado

## 9.1 Health-check local en el nodo

**Decisión congelada**

El health-check del primer corte será de dos capas.

La capa 1 es local al nodo y define si el nuevo firmware se considera “boot válido”.

Señales mínimas requeridas:

- arranque del nuevo slot sin crash loop,
- asociación Wi-Fi exitosa,
- inicialización del loop principal,
- al menos un `STAT` emitido exitosamente,
- metadatos embebidos coherentes con el manifest aplicado.

Ventana local de gracia congelada:

- `45 segundos`

Regla:

- El nuevo firmware no debe marcarse como definitivamente válido hasta superar esta ventana local.

## 9.2 Health-check observado por CKv2

La capa 2 es observada por la app y define si el despliegue quedó operativo.

Señales mínimas que CKv2 debe poder observar:

- cambio de `boot_marker` o evidencia equivalente de reboot,
- `uptime` fresco compatible con reinicio,
- versión/reportes coherentes con el artifact esperado,
- estado `calibrating` u `online` rápidamente,
- retorno a `online` dentro de la ventana esperada cuando aplique.

Ventana de gracia operativa recomendada:

- `90 segundos`

Resultado:

- Si la app observa reboot pero no recuperación operativa suficiente, el despliegue queda marcado como **failed operationally**, aunque el nodo haya quedado ejecutando el nuevo slot.

## 9.3 Uso de señales ya existentes

**Decisión congelada**

CKv2 reutilizará las señales ya disponibles en runtime:

- `boot_marker`
- `reset_reason`
- `uptime`
- `calibrating`
- `online / degraded / offline`
- `status_reason`
- eventos recientes por nodo

Esto reduce deuda y mantiene coherencia entre OTA y observabilidad runtime.

## 10. Rollback congelado

## 10.1 Qué sí habrá en el primer corte

**Decisión congelada**

Sí habrá rollback automático, pero sólo en el alcance conservador del primer corte:

- rollback de bootloader/slot ante imagen nueva que no supera validación local del boot,
- rollback automático si la nueva app no llega a estado válido dentro de la ventana local,
- rollback si el nuevo boot entra en reinicio fallido antes de ser confirmado.

## 10.2 Qué no habrá en el primer corte

No habrá todavía:

- rollback remoto arbitrario a cualquier versión del catálogo,
- cambio de manifest “en caliente” como rollback masivo,
- orquestación automática multietapa basada en KPIs de campaña,
- downgrade OTA genérico fuera del slot previo.

## 10.3 Evidencia que dispara rollback local

El rollback local queda congelado para estas condiciones:

- no logra conectar Wi-Fi dentro de la ventana local,
- no logra emitir al menos un `STAT` válido,
- reinicio repetido antes de marcar la app como válida,
- inconsistencia crítica de identidad/manifest detectada antes de confirmar la app.

## 10.4 Limitación explícita

**Decisión congelada**

Si el firmware nuevo ya fue marcado como válido localmente pero la app no observa recuperación operacional suficiente dentro de la ventana de `90 s`, el primer corte **no** garantiza rollback remoto automático.

Esa limitación queda aceptada para el primer corte y deberá endurecerse luego.

## 11. Flujo operativo congelado

Runbook resumido del flujo OTA futuro:

1. El operador importa y cataloga el firmware en CKv2.
2. El artifact queda validado, con `sha256`, `artifact_id`, target y managed store.
3. CKv2 publica un rollout OTA para un target y lote concretos.
4. CKv2 genera `manifest.json` inmutable para ese `rollout_id`.
5. CKv2 expone `manifest + bin` desde el PC del sitio por HTTP local.
6. El operador selecciona nodos/lote y dispara `OTA check now` por control-plane autenticado.
7. Cada nodo consulta el manifest de su rollout y valida compatibilidad.
8. Si aplica, descarga el bin y verifica `sha256` y `file_size`.
9. El nodo escribe en el slot OTA inactivo y reinicia al nuevo slot.
10. El nodo entra a health-check local.
11. CKv2 observa reboot, versión esperada y recuperación operativa.
12. Si el health-check local falla, el nodo revierte al slot previo.
13. Si el health-check local pasa pero la recuperación observada por app falla, el rollout queda marcado como fallo operacional y se trata como incidente.

## 12. Congelación de diseño para Ticket 25+

## 12.1 Requisitos mínimos que Ticket 25 debe implementar

Antes de cualquier despliegue OTA real, Ticket 25 deberá cubrir como mínimo:

- cliente OTA pull en firmware,
- metadata embebida exacta de build,
- comprobación de manifest,
- comprobación de target/hardware/version,
- descarga HTTP del bin,
- verificación `sha256`,
- uso correcto del slot OTA inactivo,
- confirmación local de app válida,
- rollback local,
- trigger OTA vía control-plane autenticado,
- publicación local de manifest/bin desde el PC del sitio.

## 12.2 Lo que queda explícitamente fuera del primer corte OTA

- canary automático complejo,
- UI masiva de campañas,
- firma criptográfica end-to-end,
- OTA vía internet pública,
- servidor OTA en MikroTik,
- asociación completa firmware -> nodo en histórico productivo,
- rollback remoto multi-versión,
- despliegue por grupos dinámicos complejos.

## 13. Riesgos y vigilancia

Riesgos técnicos que deben vigilarse:

- crecimiento del bin por encima del margen cómodo del slot actual,
- falta de disciplina en el versionado embebido,
- publicar manifests con target incompleto o incorrecto,
- marcar una app como válida demasiado pronto,
- depender sólo de observación app-side para rollback,
- intentar meter URL completas o payloads complejos por F3 en vez de usar `rollout_id`.

Mitigaciones congeladas:

- `version_code` monotónico obligatorio,
- `artifact_id + sha256` obligatorios,
- manifest inmutable,
- target/variant/hardware exactos,
- servidor OTA en PC local,
- health-check local antes de confirmar imagen,
- OTA sólo sobre artefactos ya catalogados por CKv2.

## 14. Decisión final del gate

Decisión final:

- **La arquitectura OTA queda congelada** en modo `HTTP pull + manifest + dual-slot OTA + PC local como servidor + health-check local + rollback conservador`.
- **No hay bloqueo de particiones o tamaño** con el build actual observado.
- **Sí hay bloqueo funcional** hasta añadir identidad embebida exacta y cliente OTA mínimo en firmware.

En otras palabras:

- el proyecto está listo para implementar Ticket 25,
- pero no está listo para hacer despliegue OTA real con el firmware actual sin esas piezas mínimas.
