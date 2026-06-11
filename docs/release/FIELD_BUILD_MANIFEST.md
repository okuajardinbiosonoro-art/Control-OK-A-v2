# Field Build Manifest

## Baseline actual de campo

| Campo | Valor |
| --- | --- |
| Producto | Control OKÚA CKv2 |
| Ejecutable | `Control OKÚA CKv2.exe` |
| Tipo de build | PyInstaller one-dir |
| SHA256 | `91F441B6163097E6B960FCAA253C30852B5C31DB4979063BF46E4BE9BB279021` |
| Tamano | `2,703,646` bytes |
| Fecha observada en campo | `2026-04-20 10:16:10` |
| Equivalente observado en desarrollo | `dist/Control OKÚA CKv2/Control OKÚA CKv2.exe` |
| Fecha observada en desarrollo | `2026-04-19 12:39:41` |

El ejecutable real desplegado en campo coincide exactamente con el build one-dir existente en el PC de desarrollo.

## Relacion con `ControlOkuaV2.spec`

El baseline de campo corresponde al formato one-dir que usa `COLLECT` en `ControlOkuaV2.spec`: un ejecutable pequeno junto a un directorio `_internal` y archivos de soporte.

Este manifiesto no declara aun que el build sea reproducible desde repo limpio. Solo registra que el ejecutable vivo en campo coincide bit a bit con el one-dir observado en desarrollo.

## Artefacto alternativo/anterior

Existe otro artefacto en desarrollo:

| Artefacto | SHA256 | Tamano | Clasificacion |
| --- | --- | --- | --- |
| `dist/Control OKÚA CKv2.exe` | `90727C4E743B38739117367E84110C969A7E6EC3C9289FFB65A72BF19C7588D3` | `53,807,257` bytes | Build alternativo/anterior. No es baseline de campo. |

No usar este segundo ejecutable como referencia operacional sin una decision explicita y nueva evidencia.

## Dependencias externas de operacion

El baseline de campo no es autosuficiente. Depende del entorno operativo:

- loopMIDI con `loopMIDI Port 1` y `loopMIDI Port 2`.
- Ableton Live 11.
- Drivers y servicios de audio/MIDI asociados a UMC/X-AIR.
- Tailscale para acceso remoto limitado.
- Servicios MIDI/audio del sistema operativo.
- Configuracion local de CKv2 y usuarios remotos, no versionada.
- Tareas programadas y scripts de arranque/recovery del PC de campo.

## Advertencias de distribucion

- No distribuir `dist/` completo desde el PC de desarrollo sin inspeccion: puede contener configs reales, usuarios, logs o estado local.
- No empaquetar `remote_api_users.json`, tokens, hashes, logs ni secretos.
- No confundir configuracion de campo con plantilla de distribucion.
- El build no debe considerarse reproducible desde repo limpio hasta reconciliar cambios locales, dependencias y comandos de build.

## Estado de confianza

| Pregunta | Respuesta |
| --- | --- |
| El ejecutable de campo esta identificado? | Si. |
| Su hash coincide con el one-dir de desarrollo? | Si. |
| Es seguro reconstruirlo hoy desde el repo limpio? | No demostrado. |
| Es seguro reemplazarlo en campo? | No sin ticket especifico, plan de rollback y aprobacion humana. |
