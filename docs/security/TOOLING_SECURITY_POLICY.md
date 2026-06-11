# Tooling Security Policy

## Alcance

Esta politica gobierna herramientas de desarrollo, agentes y automatizacion alrededor de CKv2 mientras el sistema vive como produccion liviana.

## PC de campo

No instalar herramientas nuevas en el PC de campo sin aprobacion humana explicita.

Prohibido por defecto:

- instalar paquetes;
- actualizar dependencias;
- ejecutar agentes;
- ejecutar scripts remotos;
- cambiar servicios;
- reconstruir ejecutables;
- tocar configuracion real;
- exponer tokens, usuarios, hashes o secretos.

El PC de campo es runtime, no laboratorio.

## Repo sucio principal

No ejecutar herramientas nuevas sobre el working tree sucio principal.

Antes de usar herramientas de analisis o agentes:

1. Crear clon o worktree limpio fuera de `.claude/worktrees` dentro del repo principal.
2. Verificar `git status --short --untracked-files=all`.
3. Confirmar alcance permitido.
4. Mantener cambios en ramas documentales o experimentales separadas.

## Herramientas nuevas

Graphify, Gstack, Claude Council, Spec-kit, SkillCheck y herramientas similares solo pueden probarse en:

- clon limpio;
- worktree limpio;
- entorno sin secretos;
- datos sinteticos o sanitizados;
- rama experimental.

No usar como entrada configs reales, `dist/`, logs de campo, usuarios, tokens ni backups de secretos.

## Politica de secretos

Redactar siempre como `<REDACTED>`:

- tokens;
- password hashes;
- contrasenas;
- claves API;
- `CKV2_CONTROL_SECRET`;
- secretos de firmware;
- credenciales WiFi;
- IPs Tailscale cuando no sean necesarias;
- rutas personales completas;
- archivos reales de `remote_api_*`.

Si se detecta un secreto en staging o diff:

1. Detener commit.
2. No imprimir el valor.
3. Reportar archivo y tipo de riesgo.
4. Pedir decision humana para rotacion o limpieza.

## Politica de permisos

Todo agente debe operar con minimo alcance:

- lectura primero;
- escritura solo en archivos permitidos por ticket;
- no escalamiento de permisos sin aprobacion;
- no comandos destructivos;
- no mover/borrar archivos runtime;
- no modificar Git history.

## Politica de red

No abrir puertos, tuneles o servicios nuevos sin aprobacion.

No ejecutar comandos que publiquen datos operativos fuera del entorno local.

No usar repositorios, pastebins, dashboards externos o servicios cloud con archivos no sanitizados.

## Scripts remotos

No ejecutar scripts remotos sin inspeccion previa.

Antes de ejecutar cualquier script descargado:

1. Guardarlo en entorno aislado.
2. Revisarlo completo.
3. Confirmar hash/origen si aplica.
4. Ejecutarlo solo sobre datos de prueba.
5. Documentar efectos esperados.

## Aprobacion humana requerida

Requiere aprobacion humana:

- instalaciones;
- upgrades;
- cambios de servicios;
- tocar PC de campo;
- cambios en Remote API;
- cambios de firmware;
- rebuild de exe;
- cambio de rutas de OneDrive/runtime;
- rotacion de secretos;
- limpieza de logs;
- integracion de herramientas nuevas al flujo oficial.

## Regla de cierre

Un commit de tooling o agente solo es aceptable si:

- no contiene secretos;
- no contiene binarios de campo;
- no modifica runtime;
- tiene alcance claro;
- incluye validacion de diff;
- separa documentacion, codigo y configuracion.
