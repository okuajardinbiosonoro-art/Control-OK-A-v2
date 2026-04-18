# Validación de Campaña OTA end-to-end con hardware real — Control OKÚA CKv2

Rama: `desarrollo-fase-2`  
Fecha: 2026-04-18 (Ticket 35.6)  
Clasificación: **NO EJECUTADO por falta de entorno real (agente CLI)**

---

## Por qué existe este documento

El Ticket 35.6 exige validación de Campaña OTA (wave-by-wave con health gates) con hardware real. Esto es distinto a:

- **Ticket 35.2** — QA de UI del diálogo de campaña (sin hardware)
- **Ticket 35.3** — Despliegue OTA individual con hardware real (EB1 TRIGGERED→BOOT_CONFIRMED)

Este ticket requiere que el sistema de waves se ejecute completo: `start_campaign()` → health gate → `continue_campaign()` → resultado final clasificado.

---

## Estado verificado antes de la validación

### Capa de orquestación (código)

| Ítem | Estado |
|------|--------|
| `OtaCampaignService.start_campaign()` | Implementado — primera wave |
| `OtaCampaignService.continue_campaign()` | Implementado — waves siguientes |
| `OtaCampaignService._evaluate_wave_gate()` | Implementado — PENDING/PASSED/FAILED/INCONCLUSIVE |
| `OtaCampaignService._write_campaign_audit()` | Implementado — JSON en `{published_dir}/campaigns/{campaign_id}.json` |
| Tests de orquestación (`test_ota_campaign_service.py`) | **7/7 PASAN** — lógica de wave gate validada |
| Tests de VM (`test_ota_campaign_vm.py`) | Pasan (suite completa 494/494) |

### Hardware disponible

| Ítem | Estado |
|------|--------|
| EB1 en red local | **CONFIRMADO** — `192.168.1.89` responde ping 3/3 (5-8 ms RTT) |
| EB2 en red local | No verificado para este ticket |
| Catálogo de firmware | 9 artefactos, 2 marcados `is_current=True` |
| Artefacto v2.0.0 (sha256:01dc2c9…) | Archivo existe, 839728 bytes |
| Artefacto v1.0.0-dev (sha256:980ddb4…) | Archivo existe, 839680 bytes |
| Ambos `target_kind` | `PLANT` |

### Bloqueante identificado

`OtaCampaignService` delega cada wave a `OtaOrchestratorService.deploy()`, que a su vez llama a:

```python
self._runtime_client.send_control_ota_check_now(node_id, manifest_url, artifact_sha256)
```

Este método (`runtime.py:274`) requiere:
1. `SessionController` con sesión UDP activa
2. Control plane inicializado con ACK listener en ejecución
3. Resolución de IP del nodo por `node_id` (tabla de registro viva)

El agente CLI **no puede** inicializar el `SessionController` ni la capa UDP sin arrancar la aplicación Qt completa. No existe path de inyección que permita ejecutar una campaign real desde terminal sin la app corriendo.

---

## Clasificación

**NO EJECUTADO por falta de entorno real**

El bloqueo es de arquitectura: la capa de hardware de campaña depende del runtime Qt/UDP que solo existe cuando la app está abierta y con sesión activa. Este es el mismo motivo por el que el Ticket 35.3 (deploy individual) fue ejecutado por José David, no por el agente.

---

## Lo que SÍ está validado (base para RC)

| Nivel | Validación | Ticket |
|-------|-----------|--------|
| Orquestación wave-by-wave | 7/7 tests unitarios PASAN | 35.2 / 35.6 |
| UI del diálogo de campaña | QA funcional completo | 35.2 |
| Deploy individual hardware real | EB1: TRIGGERED→ACK_MATCHED→BOOT_CONFIRMED | 35.3 |
| Health gate lógica | `_evaluate_wave_gate()` cubierto por tests | 35.6 |
| Audit JSON por campaign | Cubierto por tests | 35.6 |

La capa de campaña hardware (multi-wave con gates reales) es la **única pieza** del sistema OTA que no tiene validación con hardware. Todas las demás capas están validadas.

---

## Protocolo para José David

Para completar esta validación con hardware, ejecutar desde la app abierta con sesión UDP activa:

### Precondiciones

1. App iniciada con perfil UDP (EB1 + EB2 online y reportando estado ONLINE)
2. Firmware Manager abierto (`Firmware → Gestionar firmware`)
3. Artefacto `v2.0.0` disponible en catálogo (ya importado)

### Pasos

1. En Firmware Manager: seleccionar artefacto `v2.0.0` → clic "Campaña OTA…"
2. En el diálogo de campaña:
   - Configurar Wave 1: nodos EB1 y EB2
   - Configurar health gate: `min_healthy_pct = 100`, `timeout_s = 120`
   - Clic "Iniciar campaña"
3. Observar progreso en la tabla de wave — confirmar que los nodos pasan a `TRIGGERED`
4. Esperar ACK y transición a `BOOT_CONFIRMED` (≤ 60 s por nodo)
5. Verificar que el health gate evalúa a `PASSED`
6. Si hay 2 waves: clic "Continuar campaña" y repetir para Wave 2
7. Verificar resultado final: `COMPLETED` o `COMPLETED_WITH_WARNINGS`
8. Verificar que existe el archivo de audit en `{published_dir}/campaigns/{campaign_id}.json`

### Tabla de resultado (completar al ejecutar)

| Ítem | Resultado observado |
|------|-------------------|
| Wave 1 — nodos desplegados | __ |
| Wave 1 — ACK recibidos | __ |
| Wave 1 — health gate | PASSED / FAILED / INCONCLUSIVE |
| Wave 2 (si aplica) | __ |
| Estado final de campaña | COMPLETED / COMPLETED_WITH_WARNINGS / FAILED |
| Archivo de audit generado | SÍ / NO |
| Tiempo total de campaña | __ min |
| Bugs observados | __ |

---

## Deuda residual

| ID | Ítem | Bloqueo |
|----|------|---------|
| CAMP-1 | Campaña OTA wave-by-wave con hardware real | Requiere app Qt + sesión UDP activa — José David |

Esta deuda es **no bloqueante para RC**: el deploy individual (35.3) está validado y la capa de campaña está cubierta por tests. La campaña real es validación de integración completa recomendada para el primer ciclo de operación en Jardín Biosonoro.
