# Protocolo de validación OTA con hardware real — Control OKÚA CKv2

Rama: `desarrollo-fase-2`
Fecha de preparación: 2026-04-17 (Ticket 35.3)
Estado: **PENDIENTE DE EJECUCIÓN POR JOSÉ DAVID**

> Este documento es un protocolo de validación, no un acta. El agente no puede interactuar con la GUI ni observar dispositivos físicos. La ejecución real corresponde a José David con acceso físico al hardware y la app abierta en pantalla.

---

## Por qué existe este documento

El Ticket 35.3 exige validación OTA end-to-end con hardware real, con criterios de no aceptación explícitos:

- No puede cerrarse sin hardware real
- La "prueba" no puede ser solo UI (ya cubierta en 35.2)
- Debe quedar claro qué pasó con el dispositivo (ESP32)
- La decisión operativa final sobre OTA no puede quedar ambigua

Este documento define el protocolo exacto, las precondiciones verificadas y las tablas de resultado que José David debe completar al ejecutar la validación.

---

## Estado verificado antes de la validación

### Firmware de PC (servidor OTA)

| Ítem | Estado verificado |
|------|-----------------|
| `OtaOrchestratorService` | Implementado — `deploy()`, `_dispatch_to_node()`, `_ensure_server()` |
| `OtaServerService` | Implementado — `ThreadingHTTPServer` en `0.0.0.0:18080`, daemon thread |
| `OtaManifestService.publish_rollout()` | Implementado — escribe `manifest.json` + copia `.bin` en `publish_root_dir` |
| `send_control_ota_check_now` | Implementado — despacha paquete UDP al nodo con `rollout_token` |
| `_write_deploy_audit()` | Implementado — escribe `deploy_status.json` atómicamente |

### Firmware de nodo (ESP32)

| Ítem | Estado verificado |
|------|-----------------|
| `okua_ota.h` / `okua_ota.cpp` | Presentes en `firmware/okua_node_udp_v1/` |
| Handler `OKUA_CMD_OTA_CHECK_NOW` | Líneas 983, 999, 1071, 1521 de `okua_node_udp_v1.ino` |
| `OKUA_OTA_BASE_URL` | `http://<PC_IP>:18080` — definido desde `OKUA_STR(PC_IP_*)` en secrets |
| Estados OTA (firmware) | `IDLE → TRIGGERED → FETCHING_MANIFEST → VALIDATING_MANIFEST → DOWNLOADING → READY_REBOOT → BOOT_VALIDATING → BOOT_CONFIRMED` |
| Telemetría OTA en STAT | `rsv[0]=state_code`, `rsv[1]=error_code`, `rsv[2]=flags` |

### Artefacto `.bin` disponible

| Ítem | Valor |
|------|-------|
| Ruta | `.pio/build/okua_node_esp32dev/firmware.bin` |
| Tamaño | 839728 bytes |
| Fecha de build | 2026-04-15 07:59 |

### Catálogo de firmware

| Ítem | Valor |
|------|-------|
| Artefactos registrados | 6 |
| Target kind de todos | `plant` |
| Versiones presentes | `1.0.0-dev` (3 artefactos), `1.0.1-dev` (3 artefactos) |
| Ninguno marcado `is_current` | Confirmado — ninguno tiene `is_current: true` |

> **Acción previa requerida:** Antes de ejecutar el despliegue, importar el `.bin` de `.pio/build/` al catálogo (o usar uno ya registrado) y marcarlo como current. Ver §Pasos de validación, etapa P1.

---

## Precondiciones de ejecución

Verificar TODAS antes de iniciar:

| # | Precondición | Cómo verificar |
|---|-------------|----------------|
| PRE-1 | Nodo objetivo encendido y en red | `ping 192.0.2.10` responde |
| PRE-2 | Nodo ejecuta firmware OTA-compatible | Consola serial: debe mostrar `OTA_BASE_URL  :` al arranque |
| PRE-3 | `OKUA_OTA_BASE_URL` apunta al PC correcto | Consola serial: URL debe tener la IP del PC de control |
| PRE-4 | Puerto 18080 libre en el PC | `netstat -an \| findstr 18080` → sin resultado |
| PRE-5 | Firewall permite 18080 TCP entrante | Verificar en Windows Defender o añadir regla si necesario |
| PRE-6 | Sesión UDP activa con el nodo | App abierta, perfil `udp_jardin`, chip de sesión activo |
| PRE-7 | Al menos un artefacto en catálogo con `is_current: true` | Firmware Manager → tabla visible, uno marcado como current |

---

## Pasos de validación

### Etapa P1 — Preparar artefacto en catálogo

1. En la app: **Firmware → Firmware Manager**.
2. Clic **"Importar firmware…"** → navegar a `.pio/build/okua_node_esp32dev/firmware.bin`.
3. Completar metadatos: `target_kind = plant`, version = (la del build, ej. `1.0.1-dev`).
4. Una vez importado, seleccionar el artefacto en la tabla → clic **"Marcar como current"** → confirmar.
5. Verificar que la columna `is_current` muestra ✓ para ese artefacto.

**Resultado esperado:** Artefacto aparece en tabla con `is_current = true`. Ningún otro artefacto del mismo `target_kind` queda como current simultáneamente.

---

### Etapa P2 — Lanzar OTA Deploy (despliegue unitario)

1. En Firmware Manager: seleccionar el artefacto marcado como current.
2. Clic **"Despliegue OTA…"** → abre `OtaDeployDialog`.
3. Verificar configuración de red (grupo "Configuración de red"):
   - IP de bind correcta (la del PC en la red local)
   - Puerto: 18080
   - Token: cualquier valor no-cero
   - Canal: `plant` (o el que corresponda)
   - Timeout y reintentos: valores razonables (ej. 30 s, 3 reintentos)
4. En la lista de nodos: seleccionar EB1 (`192.0.2.10`).
5. Clic **"Publicar actualización"**.

**Resultado esperado inmediato:**
- Botón cambia a estado de progreso (spinner o texto "En curso…")
- Tabla de resultados aparece con EB1 en estado `ENVIADO` o `PENDIENTE`
- Sin `QMessageBox.warning` inmediato (valdación de parámetros OK)

---

### Etapa P3 — Observar progreso en telemetría del nodo

Mientras el deploy corre, observar la consola serial del nodo EB1 o el panel de Diagnóstico UDP.

**Secuencia de estados OTA esperada en el nodo:**

| Paso | `state_code` en STAT (`rsv[0]`) | Descripción |
|------|--------------------------------|-------------|
| 1 | `1` (TRIGGERED) | Nodo recibió `OTA_CHECK_NOW` |
| 2 | `2` (FETCHING_MANIFEST) | Nodo hace GET a `http://<PC>:18080/manifest.json` |
| 3 | `3` (VALIDATING_MANIFEST) | Nodo verifica `target_kind`, `version`, `sha256` |
| 4 | `4` (DOWNLOADING) | Nodo descarga el `.bin` via HTTP GET |
| 5 | `5` (READY_REBOOT) | Flash completo, esperando reboot |
| 6 | Nodo se desconecta brevemente | Reboot para aplicar firmware |
| 7 | `6` (BOOT_VALIDATING) | Primer ciclo de vida del nuevo firmware |
| 8 | `7` (BOOT_CONFIRMED) | Firmware validado, STAT normal reanudado |

**En la app (panel de resultado del OtaDeployDialog):** el estado de EB1 debe progresar de `PENDIENTE` → `ACK` → (si telemetría está disponible) `COMPLETADO`.

---

### Etapa P4 — Confirmar identidad post-OTA

Tras el reboot del nodo:

1. Verificar en panel Nodos que EB1 vuelve a aparecer como ONLINE.
2. Navegar a Diagnóstico → "Detalle UDP": confirmar que los paquetes STAT se reanudan (PPS > 0).
3. Anotar la versión reportada por el nodo si el firmware la expone (campo `fw_version` en STAT).

**Resultado esperado:** EB1 en ONLINE, STAT recibidos, versión coincide con el artefacto desplegado.

---

### Etapa P5 — Verificar `deploy_status.json`

Después del despliegue:

```bash
# Desde la raíz del repositorio
cat artifacts/deploy_status.json
```

Debe contener:
- `artifact_id` del artefacto desplegado
- `node_ids` con EB1
- `status` = `"completed"` o `"partial"` (no `"failed"`)
- `timestamp_utc` del despliegue

---

## Tabla de resultados — completar al ejecutar

| Etapa | Resultado observado | Pass / Fail | Notas |
|-------|--------------------|-----------|----|
| PRE-1 — ping EB1 | | | |
| PRE-2 — firmware OTA en consola | | | |
| PRE-3 — URL apunta a PC correcto | | | |
| PRE-6 — sesión UDP activa | | | |
| PRE-7 — artefacto current en catálogo | | | |
| P1 — importar y marcar current | | | |
| P2 — despliegue lanzado sin error | | | |
| P3 — estado TRIGGERED visto | | | |
| P3 — estado DOWNLOADING visto | | | |
| P3 — nodo rebooteó | | | |
| P4 — EB1 ONLINE post-OTA | | | |
| P4 — STAT reanudados | | | |
| P5 — `deploy_status.json` coherente | | | |

---

## Criterios de cierre del ticket

### El ticket 35.3 se cierra como EJECUTADO si:

- [ ] Al menos un nodo real (EB1 o EB2) completó el ciclo OTA completo: `TRIGGERED → DOWNLOADING → reboot → BOOT_CONFIRMED`
- [ ] EB1 volvió a ONLINE post-reboot con STAT funcionando
- [ ] `deploy_status.json` registra el despliegue correctamente
- [ ] No hay error fatal en la app ni traceback durante el proceso

### El ticket se cierra como PARCIAL si:

- Despliegue llegó hasta `READY_REBOOT` pero no se confirmó `BOOT_CONFIRMED` (ej. nodo tardó más de lo esperado)
- `deploy_status.json` existe pero muestra `"partial"` — documentar el estado exacto

### El ticket se cierra como BLOQUEADO si:

- El firmware de los nodos en producción no acepta `OTA_CHECK_NOW` (versión incompatible)
- `OKUA_OTA_BASE_URL` en el firmware del nodo no apunta al PC correcto
- El puerto 18080 no es accesible desde los nodos

---

## Decisión operativa post-validación (a completar por José David)

Tras ejecutar el protocolo, registrar aquí:

```
Hardware usado: _______________
Artefacto/bin usado (artifact_id): _______________
Perfil/sesión usado: udp_jardin
Ruta OTA ejecutada: Firmware Manager → Despliegue OTA → EB1

Resultado final: [ ] EJECUTADO  [ ] PARCIAL  [ ] BLOQUEADO
Motivo (si no EJECUTADO): _______________
Decisión operativa OTA: _______________
  Opciones: "OTA listo para uso controlado" / "Pendiente de fix en firmware" / "No usar hasta próximo ciclo"
```

---

## Referencias

| Documento | Contenido |
|-----------|-----------|
| [`firmware_ota_ui_qa_report.md`](firmware_ota_ui_qa_report.md) | QA de UI/flujo completado en 35.2 — sin hardware |
| [`baseline_release_checklist.md`](baseline_release_checklist.md) | Checklist técnico de RC |
| `firmware/okua_node_udp_v1/okua_ota.h` | Estados y códigos de error OTA del firmware |
| `src/control_okua/services/ota_orchestrator_service.py` | Flujo de orquestación OTA en PC |
