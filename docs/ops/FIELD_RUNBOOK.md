# Field Runbook CKv2

## Principio operativo

El PC de campo ejecuta produccion liviana. No es laboratorio. Toda accion debe privilegiar continuidad, observacion pasiva y rollback.

## Verificar si CKv2 esta corriendo sin detenerlo

Acciones permitidas en modo observacion:

- Revisar procesos por nombre de ejecutable o ventana.
- Verificar que Ableton Live 11 sigue activo.
- Verificar que loopMIDI esta activo.
- Confirmar presencia de `loopMIDI Port 1` y `loopMIDI Port 2`.
- Revisar timestamps/tamano de logs sin abrir secretos.
- Revisar tareas programadas solo en modo lectura.
- Confirmar conectividad Tailscale sin cambiar configuracion.

No cerrar procesos, reiniciar servicios ni ejecutar scripts de recovery salvo incidente declarado y aprobacion humana.

## Dependencias externas

- CKv2 empaquetado one-dir.
- Ableton Live 11.
- loopMIDI.
- Puertos `loopMIDI Port 1` y `loopMIDI Port 2`.
- Drivers UMC/X-AIR.
- Servicios MIDI/audio de Windows.
- Tailscale para acceso remoto restringido.
- Tareas programadas de arranque/recovery.
- Configuracion local de Remote API y usuarios.

## loopMIDI

Verificar:

- loopMIDI abierto o servicio activo.
- `loopMIDI Port 1` visible.
- `loopMIDI Port 2` visible.
- No renombrar puertos durante operacion.
- No crear nuevos puertos en campo sin ticket.

## Ableton

Verificar:

- Ableton Live 11 activo.
- Proyecto esperado cargado.
- Entradas MIDI asociadas a loopMIDI disponibles.
- Audio device estable.

No cambiar ruteo, proyecto, driver o buffer durante operacion salvo plan aprobado.

## Tailscale y Remote API

Estado esperado observado:

- `remote_api.enabled=true`.
- Exposicion limitada por Tailscale.
- `bind_host=127.0.0.1`.
- `port=8788`.
- `auth_mode=human_session_only`.

No publicar tokens, usuarios, hashes ni IPs Tailscale. No cambiar modo de exposicion en campo sin revision de seguridad.

## Tareas programadas y scripts de arranque

El campo tiene tareas y scripts de arranque/recovery. Deben tratarse como parte del runtime vivo.

Permitido:

- Inventariar nombre, estado y hora de ultima ejecucion.
- Leer comandos solo si se redactan secretos.

Prohibido sin aprobacion:

- Editar tareas.
- Reprogramar triggers.
- Cambiar rutas.
- Ejecutar scripts manualmente.
- Copiar scripts a otro equipo con secretos incluidos.

## Problemas de MIDI o Windows

Ante perdida de audio/MIDI:

1. Documentar hora y sintoma.
2. Confirmar CKv2, Ableton y loopMIDI sin detenerlos.
3. Revisar si hubo eventos recientes de driver UMC/X-AIR o advertencias de Windows.
4. Verificar que los puertos loopMIDI siguen presentes.
5. Escalar antes de reiniciar servicios.

Advertencia: reiniciar `midisrv` puede afectar Ableton, loopMIDI y el runtime. Solo hacerlo con ventana de intervencion y aprobacion humana.

## OneDrive

La instalacion de campo esta bajo una ruta sincronizada por OneDrive. Riesgos:

- Locks durante escritura.
- Sync de logs grandes.
- Cambios parciales o conflictos.
- Latencia o corrupcion al actualizar binarios/configs.

No mover la instalacion durante operacion. Si se decide retirar OneDrive del runtime, hacerlo en ticket separado con rollback.

## Logs grandes

Existe un log grande `tools/relay.out.txt` de aproximadamente `711 MB`.

Riesgos:

- Consumo de disco.
- Sync lento o fallido.
- Dificultad para abrir editores.
- Posible exposicion de datos operativos.

No truncar, borrar ni comprimir sin ticket de mantenimiento. Primero confirmar si CKv2 o algun script lo mantiene abierto.

## Que no hacer en campo

- No instalar paquetes.
- No ejecutar herramientas nuevas.
- No reconstruir exe.
- No cambiar firmware.
- No editar configuraciones reales.
- No mostrar secretos.
- No detener CKv2 si esta corriendo.
- No reiniciar Windows por conveniencia.
- No usar el PC de campo para probar Graphify, Gstack, Claude Council, Spec-kit, SkillCheck u otras herramientas de agente.
