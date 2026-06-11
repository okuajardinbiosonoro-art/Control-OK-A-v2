# CKV2 Security Validation - 2026-06-11

## Scope

- Rama: `chore/000d-repo-guardrails`
- Commits revisados: `eb77292`, `ba6af50`, `296496d`, `fe87ca5`, `2a49ac2`, `305521b`, `17dc75e`
- PC de campo tocado: no
- Herramientas instaladas: no

## Residuo documental

- Archivo revisado: `docs/process/POLITICA_ARCHIVO_HISTORICO_EVIDENCIA_VISUAL.md`
- Clasificacion: D. Documento accidental o fuera de alcance
- Accion tomada: movido a cuarentena externa `CKV2_QUARANTINE_000G_20260611_173850` y agregado a `.gitignore` con regla especifica

## Versioned tree checks

- Binarios/logs/configs reales: no se detectaron rutas versionadas refinadas para `dist/`, `build/`, ejecutables, DLL, Pyd, binarios firmware, logs, configs reales, tokens remotos o secrets firmware reales.
- Secretos directos: no se detectaron marcadores de claves privadas, `api_key`, asignaciones de `CKV2_CONTROL_SECRET` ni bearer tokens fuera de fixtures de test.
- Firmware secrets: `firmware/**/okua_node_secrets.h` no esta versionado; el example versionado usa placeholders.
- Dist/build: no se detectaron como rutas versionadas.
- Hallazgos: la primera pasada marco `pyrightconfig.json` por el texto `config.json`; clasificado como falso positivo de nombre de archivo.

## Pattern scan

- Patrones revisados: `CKV2_CONTROL_SECRET`, `password_hash`, `remote_api_tokens`, `remote_api_users`, marcador de clave privada, `api_key`, `token`, `password`, `contraseña`, `ssid`, `wifi`, `tailscale`, prefijo `100.` y patron de ruta Windows de usuario.
- Hallazgos sanitizados:
  - Referencias de codigo, docs y tests a nombres de secretos/control remoto sin valores expuestos.
  - Tres referencias versionadas a rutas Windows de usuario en documentacion historica.
  - Diecisiete referencias versionadas con forma de IP Tailscale en documentacion y tests.
  - Fixtures de tests con bearer tokens o secretos de prueba.
  - Helpers de firmware que escriben templates de secrets a partir de parametros o entorno.
- Falsos positivos:
  - Variables y campos llamados `token`.
  - Campos `password_hash` del modelo de usuarios remotos.
  - Referencias a archivos ignorados como `remote_api_users.json` y `remote_api_tokens.json`.
  - Valores numericos `100` que no son IPs.

## Tool availability

- gitleaks: no disponible
- bandit: no disponible
- pip-audit: no disponible
- pre-commit: no disponible

## Python syntax validation

- Resultado: `syntax ok: 207 python files`

## Risks remaining

- Riesgos abiertos:
  - Existen referencias versionadas historicas a rutas Windows de usuario en docs.
  - Existen referencias versionadas con forma de IP Tailscale en docs/tests; los tests parecen fixtures, pero la documentacion debe revisarse antes de push.
  - No se ejecuto `pytest` completo por alcance del ticket.
  - No se ejecutaron scanners externos porque no estan instalados.
- Recomendaciones:
  - Abrir un ticket especifico para sanitizar referencias historicas de rutas e IPs en docs.
  - Ejecutar `gitleaks`, `bandit`, `pip-audit` y `pre-commit` en un entorno controlado antes de publicar.
  - Mantener fuera de Git configs reales, users/tokens remotos, logs, dist, builds y secrets firmware.

## Decision

- Rama lista para revision humana: si
- Rama lista para push: no automatico; requiere revision humana de hallazgos historicos de rutas/IPs o ticket de sanitizacion previo
- Condiciones antes de push:
  - Aceptar o sanitizar las referencias historicas detectadas.
  - Opcionalmente ejecutar scanners externos en entorno preparado.
  - Confirmar que no se agregaron nuevos archivos fuera de la documentacion y guardrails esperados.
