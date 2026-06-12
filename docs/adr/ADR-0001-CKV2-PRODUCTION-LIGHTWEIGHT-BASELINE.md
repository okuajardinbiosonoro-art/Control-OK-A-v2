# ADR-0001: CKv2 Production Lightweight Baseline

## Estado

Aceptada para documentacion base.

## Fecha

2026-06-11

## Contexto

CKv2 ya opera en campo como produccion liviana. Las auditorias pasivas de campo y desarrollo mostraron que:

- el PC de campo esta ejecutando CKv2;
- el PC de campo no debe usarse como laboratorio;
- el repo de desarrollo tiene un working tree principal sucio;
- hay cambios locales no reconciliados;
- hay posibles secretos, configs reales, logs y artefactos dentro del entorno de desarrollo;
- el ejecutable real de campo coincide por SHA256 con el build one-dir existente en desarrollo;
- todavia no esta demostrada la reproducibilidad desde repo limpio.

## Decision

Se declara CKv2 como produccion liviana.

El PC de campo queda fuera de alcance para experimentos, instalaciones, pruebas de agentes, rebuilds y limpieza general.

El servidor queda fuera de alcance por ahora.

El baseline de campo sera el ejecutable:

- `Control OKÚA CKv2.exe`
- SHA256 `91F441B6163097E6B960FCAA253C30852B5C31DB4979063BF46E4BE9BB279021`
- PyInstaller one-dir

El ejecutable baseline de campo coincide exactamente con el build one-dir observado en el PC de desarrollo.

La limpieza del repo, secretos, worktrees, artefactos y firmware se hara despues de esta reconciliacion documental.

Las herramientas de agentes se incorporaran gradualmente, en clones o worktrees limpios, con politica de seguridad previa.

Ninguna herramienta nueva se instalara sin aprobacion humana y sin politica de seguridad aplicable.

## Consecuencias

- La documentacion de estado vivo tiene prioridad sobre refactors o limpieza.
- El baseline se protege por hash antes que por rebuild.
- El repo principal sucio no se usara como base de cambios directos.
- Los proximos tickets deberan separar docs, seguridad, firmware, build y tools.
- El PC de campo se tocara solo con plan, ventana de intervencion y rollback.

## No decisiones

Esta ADR no decide:

- promover cambios de firmware fruit;
- cambiar el ejecutable de campo;
- instalar herramientas nuevas;
- limpiar `dist/`, logs o artefactos;
- rotar secretos;
- publicar una release masiva;
- incorporar servidor o infraestructura externa.

## Reglas derivadas

- Todo trabajo de reconciliacion debe usar worktree limpio.
- No commitear configs reales, usuarios, tokens, hashes ni secretos.
- No versionar binarios de campo.
- No ejecutar build o tests de hardware como parte de tareas documentales.
- No hacer push sin aprobacion humana.
