# CKV2 Live State - 2026-06-11

## Proposito

Este documento reconcilia, en forma sanitizada, el estado vivo de Control OKÚA CKv2 observado en las auditorias pasivas `CKV2_FIELD_AUDIT_2026-06-11` y `CKV2_DEV_AUDIT_2026-06-11`.

No es una copia cruda de las auditorias. Omite rutas personales completas, credenciales, hashes de usuarios, tokens, IPs privadas innecesarias y configuraciones reales sensibles.

## Estado general

CKv2 esta operando como produccion liviana: es el sistema actualmente usado para operar la instalacion de campo, pero todavia conserva deuda de trazabilidad entre repo, build, configuracion y cambios locales.

La prioridad inmediata es preservar el estado vivo, documentar el baseline real y posponer limpieza, rebuilds o incorporacion de herramientas hasta tener una linea documental verificable.

## Entornos reconciliados

| Entorno | Estado | Observacion |
| --- | --- | --- |
| Repo remoto/local | Rama de trabajo `desarrollo-fase-2`, HEAD `26a92eff4ace836eb7a26ba5d97845412affb484` | El estado versionado no explica por completo todo lo que existe localmente. |
| PC de desarrollo | Working tree principal sucio | Contiene cambios no commiteados, archivos no versionados, artefactos, posibles secretos y worktrees auxiliares. |
| PC de campo | CKv2 corriendo | No debe tocarse como laboratorio; es el entorno operativo vivo. |

## Baseline de campo

El ejecutable real desplegado en campo coincide exactamente con el build one-dir existente en el PC de desarrollo.

| Campo | Valor |
| --- | --- |
| Nombre del ejecutable | `Control OKÚA CKv2.exe` |
| Tipo de build | PyInstaller one-dir |
| SHA256 baseline | `91F441B6163097E6B960FCAA253C30852B5C31DB4979063BF46E4BE9BB279021` |
| Tamano | `2,703,646` bytes |
| Fecha observada en campo | `2026-04-20 10:16:10` |
| Ruta relativa equivalente en desarrollo | `dist/Control OKÚA CKv2/Control OKÚA CKv2.exe` |
| Fecha observada en desarrollo | `2026-04-19 12:39:41` |

Existe ademas un artefacto alternativo/anterior en desarrollo:

| Artefacto | SHA256 | Tamano | Interpretacion |
| --- | --- | --- | --- |
| `dist/Control OKÚA CKv2.exe` | `90727C4E743B38739117367E84110C969A7E6EC3C9289FFB65A72BF19C7588D3` | `53,807,257` bytes | Build alternativo/anterior; no es el baseline de campo. |

## Estado vivo de campo

La auditoria de campo reporto:

- CKv2 corriendo.
- Ableton Live 11 activo.
- loopMIDI activo con `loopMIDI Port 1` y `loopMIDI Port 2`.
- Remote API habilitada con exposicion limitada por Tailscale, bind local y puerto `8788`.
- Autenticacion remota en modo `human_session_only`.
- Usuarios reales y hashes presentes en `remote_api_users.json`; todos los valores deben permanecer redactados.
- Existencia de `CKV2_CONTROL_SECRET` en un archivo `.bat`; documentado solo como riesgo.
- Tareas programadas y scripts de arranque/recovery.
- Logs de Remote API.
- Log operacional grande `tools/relay.out.txt`, aproximadamente `711 MB`.
- Instalacion ubicada bajo una carpeta sincronizada por OneDrive, lo cual es un riesgo operativo.
- Eventos recientes de drivers UMC/X-AIR y advertencias/reinicios de Windows.

## Estado vivo de desarrollo

La auditoria de desarrollo reporto:

- Rama `desarrollo-fase-2`.
- HEAD `26a92eff4ace836eb7a26ba5d97845412affb484`.
- Working tree principal sucio.
- 6 archivos modificados.
- 400 archivos no versionados.
- Cambios locales en:
  - `.vscode/c_cpp_properties.json`
  - `.vscode/launch.json`
  - `ControlOkuaV2.spec`
  - `firmware/README.md`
  - `firmware/okua_node_udp_v1/okua_node_secrets.example.h`
  - `firmware/okua_node_udp_v1/okua_node_udp_v1.ino`
- `ControlOkuaV2.spec` cambia `upx=True` a `upx=False`.
- Hay cambios grandes en firmware fruit y herramientas nuevas de diagnostico live fruit.
- Hay backups de `okua_node_secrets.h` con secretos o valores realistas.
- Hay un worktree `.claude/worktrees/cranky-elion/**` dentro del repo principal.
- `dist/` contiene configuraciones/logs reales o sensibles y no debe versionarse.
- `pytest` no quedo verde durante la auditoria pasiva.
- `.venv` y Python global difieren.
- `matplotlib` aparece como dependencia usada por diagnostico live, pero no esta en `requirements.txt`.

## Diferencias no reconciliadas

- No esta demostrado todavia que el baseline one-dir pueda reconstruirse desde un repo limpio en HEAD actual.
- El build de campo coincide con el one-dir existente, pero el repo limpio no contiene todo el estado local vivo.
- El working tree principal contiene cambios de firmware fruit que podrian corresponder a la operacion de campo o a experimentacion posterior.
- Las herramientas live fruit y el panel de diagnostico existen fuera del ultimo commit aceptado.
- El segundo ejecutable de `dist/` no debe confundirse con el baseline real de campo.
- La configuracion de campo contiene usuarios reales, secretos y estado local que deben mantenerse fuera del repositorio.

## Fixes no commiteados conocidos

- Ajuste de PyInstaller para desactivar UPX.
- Ajustes locales de rutas/PlatformIO en `.vscode`.
- Cambios extensos de firmware fruit: variantes, release/rearm, diagnostico UDP y armonia.
- Herramientas de captura/visualizacion live fruit.
- Documentos y binarios OTA de iteraciones EB1/EC1.
- Posible configuracion de campo preservada en archivos ignorados o backups.

## Riesgos principales

- Filtracion de secretos si se commitean backups, configs reales, `.bat` operativos o archivos de Remote API.
- Rebuild no reproducible si se confunde el estado local sucio con el HEAD versionado.
- Interrupcion de campo si se trata el PC operativo como entorno de pruebas.
- Sincronizacion OneDrive sobre archivos runtime, logs o ejecutables.
- Logs grandes que pueden bloquear copias, backups o sync.
- Dependencias no declaradas para herramientas auxiliares.
- Worktrees y artefactos auxiliares dentro del repo principal que elevan el riesgo de commits accidentales.

## Decisiones pendientes

- Definir si `upx=False` entra como cambio de packaging oficial.
- Separar cambios de firmware fruit por linea EB1/EC1 y por evidencia de campo.
- Decidir si las herramientas live fruit se incorporan al repo, se documentan como operacion externa o se migran a paquete separado.
- Declarar o retirar `matplotlib` segun la decision sobre el panel live.
- Preparar una estrategia para rotar secretos si algun backup fue expuesto fuera del equipo local.
- Definir el proceso de build reproducible desde worktree limpio.

## Que no debe tocarse todavia

- PC de campo.
- Ejecutable de campo.
- Scripts de arranque/recovery de campo.
- `remote_api_users.json`, tokens, secretos o hashes.
- Firmware operativo hasta separar evidencia de experimento.
- `dist/`, `logs/`, `artifacts/`, `ota_binaries/` y configuraciones reales.
- `.claude/worktrees` dentro del repo principal.
- Caches, venvs o herramientas instaladas en campo.
