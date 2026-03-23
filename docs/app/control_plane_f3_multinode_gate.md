# Gate Operativo F3 Multi-nodo (EA1 + EA3) - Ticket 16.4

Fecha: 2026-03-23

## 1) Objetivo del gate

Validar en entorno real que el plano de control F3 de CKv2 funciona de forma robusta en dos nodos independientes (EA1 y EA3), con evidencia coherente en:

- runtime/backend (`SessionController` + snapshot canónico por nodo),
- UI técnica (`Plano de control`),
- recording/session JSONL.

Comandos en alcance:

- `PING`
- `REQUEST_STAT_NOW`
- `REBOOT_SOFT`

Fuera de alcance:

- `SET_PROFILE`, `SET_THROTTLE`, `SET_STAT_RATE`, `SET_DEBUG`
- firmware/spec/OTA/rediseño UI.

## 2) Prerrequisitos

1. App CKv2 ejecutable (`python main.py`) y sesión UDP/LAB disponible.
2. Secreto de control-plane válido:
   - `CKV2_CONTROL_SECRET` o
   - `CKV2_CONTROL_SECRET_FILE`.
3. Red operativa entre host y nodos EA1/EA3.
4. EA1 y EA3 identificados con `node_id` y alcanzables por runtime (EVT/STAT recientes).
5. Ventana de operación segura para `REBOOT_SOFT` (impacto permitido).
6. Recording de sesión habilitado para evidencias JSONL (`logging.enabled=true` recomendado).

## 3) Objetivos de validación

1. Confirmar ejecución de `PING`, `REQUEST_STAT_NOW`, `REBOOT_SOFT` en EA1 y EA3.
2. Confirmar aislamiento multi-nodo:
   - evidencia de EA1 no contamina EA3,
   - evidencia de EA3 no contamina EA1.
3. Confirmar consistencia entre snapshot backend-side, panel técnico y recording JSONL.
4. Confirmar robustez de reboot verification por nodo.

## 4) Preparación previa

1. Iniciar CKv2 y arrancar sesión UDP/LAB.
2. Ir a `Plano de control`.
3. Verificar para EA1 y EA3:
   - `node_id` seleccionable,
   - `IP resuelta` visible o estado claro de no resolución,
   - `Estado de resolución` (`RESOLVED`/`STALE`/`UNRESOLVED`),
   - `Transacción activa` coherente (normalmente `no` antes de enviar).
4. Confirmar que el panel sigue mostrando solo:
   - `PING`
   - `REQUEST_STAT_NOW`
   - `REBOOT_SOFT`

## 5) Secuencia operativa por nodo (ejecutar EA1 y luego EA3)

### 5.1 `PING`

1. Seleccionar nodo objetivo.
2. Ejecutar `PING`.
3. Verificar observables esperados:
   - ACK correlacionado (resultado final `ACK_MATCHED` o equivalente de éxito),
   - `last_command_name=PING`,
   - actualización de `last_cmd_seq`, `last_nonce`,
   - bloque ACK con `stage/status_code/err_detail` si aplica.

### 5.2 `REQUEST_STAT_NOW`

1. Mantener nodo objetivo seleccionado.
2. Ejecutar `REQUEST_STAT_NOW`.
3. Verificar observables esperados:
   - ACK correlacionado correcto,
   - evidencia runtime de STAT reciente,
   - snapshot del nodo actualizado sin afectar al otro nodo.

### 5.3 `REBOOT_SOFT` (solo si es seguro en operación)

1. Confirmar impacto operativo y ventana segura.
2. Ejecutar `REBOOT_SOFT` con confirmación explícita.
3. Verificar observables esperados:
   - ACK previo al reinicio,
   - corte/reaparición esperada del nodo,
   - actualización de evidencia runtime,
   - resumen de verificación de reboot en el nodo correcto.

## 6) Observables de reboot verification por nodo

Para el nodo reiniciado, verificar uno o más indicadores consistentes:

- cambio/caída de `uptime`,
- cambio o actualización coherente de `reset_reason`,
- cambio o confirmación de `boot_marker`,
- `last_reboot_verification_status` + `last_reboot_verification_summary` claros.

Validación de aislamiento:

- el nodo no reiniciado no debe heredar resumen ni estado de reboot del otro.

## 7) Matriz de validación EA1 + EA3

| Nodo | Comando | ACK esperado | Evidencia runtime esperada | Evidencia UI esperada | Resultado real | Observaciones |
| --- | --- | --- | --- | --- | --- | --- |
| EA1 | `PING` | ACK válido correlacionado a EA1 | `last_command_name=PING`, estado final éxito | Panel de EA1 muestra último resultado/ACK de EA1 | No ejecutado en esta corrida | Sin acceso operativo a EA1 desde este entorno |
| EA1 | `REQUEST_STAT_NOW` | ACK válido correlacionado a EA1 | ACK + actividad STAT reciente EA1 | Panel EA1 actualiza resultado y no contamina EA3 | No ejecutado en esta corrida | Sin acceso operativo a EA1 desde este entorno |
| EA1 | `REBOOT_SOFT` | ACK previo al reinicio | verificación reboot por EA1 (`uptime/reset_reason/boot_marker`) | Resumen reboot visible solo en EA1 | No ejecutado en esta corrida | No se puede validar reboot real sin hardware |
| EA3 | `PING` | ACK válido correlacionado a EA3 | `last_command_name=PING`, estado final éxito | Panel de EA3 muestra último resultado/ACK de EA3 | No ejecutado en esta corrida | Sin acceso operativo a EA3 desde este entorno |
| EA3 | `REQUEST_STAT_NOW` | ACK válido correlacionado a EA3 | ACK + actividad STAT reciente EA3 | Panel EA3 actualiza resultado y no contamina EA1 | No ejecutado en esta corrida | Sin acceso operativo a EA3 desde este entorno |
| EA3 | `REBOOT_SOFT` | ACK previo al reinicio | verificación reboot por EA3 (`uptime/reset_reason/boot_marker`) | Resumen reboot visible solo en EA3 | No ejecutado en esta corrida | No se puede validar reboot real sin hardware |

## 8) Evidencia a guardar

1. Capturas o registro textual del panel `Plano de control` para EA1 y EA3 antes/durante/después de cada comando.
2. Extractos de snapshot backend-side por nodo:
   - `SessionController.get_control_plane_node_snapshot(node_id)`
   - `SessionController.get_control_plane_node_snapshots()`.
3. Evidencia de recording (`session.jsonl`) con eventos de control-plane correlacionables por nodo/comando.
4. En caso de reboot:
   - evidencia del resumen runtime de verificación y campos de soporte (`uptime/reset_reason/boot_marker`).

## 9) Criterios de éxito/fallo del gate

Éxito del gate:

1. EA1 y EA3 completan `PING`, `REQUEST_STAT_NOW`, `REBOOT_SOFT` (cuando seguro) con evidencia coherente.
2. No hay mezcla de evidencia entre nodos.
3. Snapshot backend-side, panel técnico y JSONL cuentan la misma historia por nodo.
4. Reboot verification es robusto y aislado por nodo.

Fallo del gate:

1. Falta validación real de uno o más comandos críticos por nodo.
2. Hay contaminación cruzada de evidencia entre nodos.
3. Inconsistencia material entre runtime, UI y recording.

## 10) Limitaciones conocidas

1. Este gate no habilita ni implementa comandos `SET_*`.
2. La ejecución de `REBOOT_SOFT` depende de ventana operativa segura.
3. Si no hay acceso real a EA1/EA3 en la corrida actual, no se puede declarar gate superado.

## 11) Ejecución de esta corrida (2026-03-23)

Estado de entorno observado en esta ejecución:

- Sin acceso verificable a hardware EA1/EA3 desde este entorno de trabajo.
- Se preparó runbook operativo y matriz completa, pero la ejecución física de comandos por nodo quedó pendiente.
- La validación automática mínima de integridad de código/documentación sí se ejecutó (`compileall`).

## 12) Conclusión de gate

Gate multi-nodo F3 no superado; debe completarse la validación operativa real EA1/EA3 (PING, REQUEST_STAT_NOW y REBOOT_SOFT con evidencia por nodo) antes de abrir `SET_*`.
