# Agent Workflow CKv2

## Principios

- Observar antes de modificar.
- Documentar antes de limpiar.
- Proponer antes de tocar runtime.
- Commit solo con alcance cerrado.
- PC de campo fuera de experimentacion.
- No usar `.claude/worktrees` dentro del repo principal como zona de trabajo.

## Flujo para Codex

1. Confirmar cwd, rama y estado Git.
2. Si el repo principal esta sucio, crear worktree limpio separado.
3. Leer solo los archivos necesarios.
4. Mantener secreto cualquier valor sensible.
5. Editar solo archivos permitidos por el ticket.
6. Validar `git status --short --untracked-files=all`.
7. Validar `git diff --check`.
8. Revisar `git diff --name-only`.
9. Buscar patrones de secretos en el diff staged antes de commit.
10. Commit solo si el alcance coincide.
11. No hacer push sin aprobacion humana.

## Flujo para Claude Code

Claude Code puede colaborar en lectura, planificacion o generacion de borradores, pero debe seguir las mismas reglas:

- worktree limpio fuera del repo principal;
- no ejecutar scripts no inspeccionados;
- no instalar herramientas;
- no tocar campo;
- no commitear secretos;
- no mezclar codigo, firmware, docs y build en el mismo commit.

## Separacion de fases

| Fase | Puede hacer el agente | Requiere aprobacion |
| --- | --- | --- |
| Observar | `git status`, inventario, lectura de archivos permitidos | Acceder a secretos o PC de campo |
| Documentar | Crear docs sanitizados | Incluir rutas privadas, hashes de usuarios o tokens |
| Proponer | Plan de commits, riesgos, rollback | Cambiar runtime |
| Modificar | Solo archivos permitidos por ticket | Firmware, build, scripts, configs reales |
| Commit | Commit local de alcance aprobado | Push |

## Que puede hacer un agente sin aprobacion

- Crear worktree limpio si el ticket lo pide.
- Leer documentacion y archivos no sensibles.
- Crear documentos sanitizados.
- Ejecutar validaciones Git de solo lectura.
- Revisar diffs.
- Preparar commit local si el ticket lo autoriza explicitamente.

## Que requiere aprobacion humana

- Tocar PC de campo.
- Ejecutar la app en campo.
- Instalar paquetes.
- Rebuild de exe.
- Cambios de firmware.
- Cambios de herramientas reales de campo.
- Edicion de configs reales.
- Limpieza de logs o artefactos.
- Push a remoto.

## Division de commits

Separar por tipo:

- documentacion de estado vivo;
- packaging/build;
- firmware;
- herramientas de diagnostico;
- tests;
- seguridad/configuracion.

No mezclar secretos, bins ni configs reales con docs.

## Pre-cierre

Antes de entregar:

1. Mostrar rama y commit.
2. Listar archivos creados/modificados.
3. Confirmar validaciones.
4. Confirmar que no hubo push.
5. Confirmar que no se toco campo/runtime.
6. Confirmar que no hay secretos en staged diff.

## Reporte de riesgos

Todo riesgo debe reportarse sin exponer datos sensibles:

- archivo o area;
- tipo de riesgo;
- impacto;
- accion recomendada;
- si requiere rotacion o limpieza.

## Prevencion de commits accidentales

Antes de `git add`:

- revisar `git diff --name-only`;
- verificar que no aparezcan `dist/`, `build/`, `.venv/`, `.claude/`, `logs/`, `config.json`, `remote_api_*`, `ota_binaries/` ni backups de secrets;
- buscar palabras como `TOKEN`, `PASSWORD`, `SECRET`, `CKV2_CONTROL_SECRET`, `WIFI_PASS`, `hash`, `bearer`;
- si aparece un valor real, detenerse.
