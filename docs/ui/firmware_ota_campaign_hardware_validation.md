# Validación de Campaña OTA end-to-end con hardware real — Control OKÚA CKv2

Rama: `desarrollo-fase-2`
Fecha: 2026-04-18 (Ticket 35.6)
Clasificación: **PASA con observaciones menores**

---

## Resumen ejecutivo

Se ejecutó una campaña OTA real sobre EB1 con sesión UDP viva, artifact compatible por variante y observación de reboot por serial y por snapshots de control-plane.

La campaña completó con:

- `campaign_status = COMPLETED`
- `health_gate = PASSED`
- `node phase = CONFIRMED`
- reboot confirmado
- firmware levantado en `1.0.1-dev`

El único incidente fue operativo: el primer intento usó un `rollout_token` ya publicado y fue rechazado antes de publicar el manifest. Se corrigió repitiendo la campaña con un token único. No hubo bug de código.

---

## Entorno real

| Ítem | Valor |
|------|-------|
| Rama | `desarrollo-fase-2` |
| Perfil activo | `udp_jardin` |
| IP del PC | `192.0.2.10` |
| Sesión | UDP viva con `SessionController` y control-plane disponible |
| Nodo observado | EB1 (`node_id = 1`) |
| Nodos en red | EB1 y EB2 visibles, pero la campaña se ejecutó sólo sobre EB1 |
| Serial observado | `COM4` (USB-SERIAL CH340) |
| Serial alterno | `COM6` presente, no usado |
| Evidencia de red | EB1 resolvió `192.0.2.10` |
| Evidencia de red | EB2 resolvió `192.0.2.10` |

---

## Escenario ejecutado

| Ítem | Valor |
|------|-------|
| Nodos objetivo | `1` |
| Canary | Sí |
| Waves manuales | Ninguna |
| Artifact/bin usado | `sha256:085f8e3e78a6ce83aa9052791ba721709eef0971a9a21aa21107d33883b1ec5b` |
| Archivo del bin | `artifacts/firmware_store/085f8e3e78a6ce83aa9052791ba721709eef0971a9a21aa21107d33883b1ec5b.bin` |
| Versión | `1.0.1-dev` |
| Target | `plant/eb1` |
| Canal | `situational` |
| Advertise host | `192.0.2.10` |
| Bind host | `0.0.0.0` |
| Puerto OTA | `18080` |
| Ack timeout | `600 ms` |
| Reintentos | `0` |
| Rollout token final | `69e3bb72` |
| Rollout id | `plant-eb1-1_0_1-dev-69e3bb72` |

Nota: EB2 quedó fuera del alcance de esta campaña porque el flujo OTA valida `target_variant` de forma estricta y este artifact es específico de `eb1`.

---

## Ejecución real

1. Se inició `SessionController` en modo UDP.
2. Se confirmó que EB1 y EB2 aparecían online en el control-plane.
3. Se seleccionó el artifact compatible de EB1 (`1.0.1-dev`).
4. Primer intento con `rollout_token = 20260418` falló porque ese token ya estaba publicado con otro manifest.
5. Se repitió la campaña con token único `69e3bb72`.
6. `start_campaign()` devolvió `success = True` y el nodo entró en `TRIGGERED`.
7. El nodo pasó por reboot y reapareció online.
8. La campaña cerró en `CONFIRMED` con health gate `PASSED`.
9. Se capturó banner serial del reinicio y del boot final.

---

## Resultado real observado

| Ítem | Observado |
|------|-----------|
| `start_campaign()` | `success = True` |
| Estado inicial OTA | `TRIGGERED` |
| ACK del control-plane | `ACK_MATCHED` |
| Observación de reboot | Sí, por serial y snapshots UDP |
| Estado posterior | `CONFIRMED` |
| Estado final de campaña | `COMPLETED` |
| Health gate | `PASSED` |
| Audit de deploy | `artifacts/ota_publish/ota/rollouts/69e3bb72/deploy_status.json` |
| Audit de campaña | `artifacts/ota_publish/ota/rollouts/69e3bb72/campaigns/campaign-20260418171218.json` |
| Tiempo total aproximado | 31 s |

### Evidencia clave de serial

- `NODE_LABEL    : EB1`
- `NODE_ID       : 1`
- `FW_VERSION    : 1.0.1-dev`
- `FW_VERSION_CD : 10001`
- `FW_TARGET     : plant/eb1`
- `FW_PROFILE    : test`
- `OTA_BASE_URL  : http://192.0.2.10:18080`

El banner también reporta `FW_ARTIFACT` / `FW_SHA256` del runtime, que en este firmware corresponde al SHA de la partición en ejecución. Eso no coincide con el SHA del bin del catálogo y es esperado por diseño. Ver `docs/firmware/ota_firmware_runtime.md`.

---

## Bugs encontrados y correcciones

| Hallazgo | Estado |
|----------|--------|
| `rollout_token` reutilizado en el primer intento | Corregido operativamente con un token único (`69e3bb72`) |
| Diferencia entre SHA del bin publicado y SHA de la partición en ejecución | No es bug; está documentado en runtime OTA |
| Fallo de código | No encontrado |

No fue necesario modificar código.

---

## Decisión final

**PASA con observaciones menores**

La campaña OTA real quedó validada para uso controlado interno sobre EB1. El flujo de campaña funciona end-to-end con hardware real: publicación del manifest, trigger OTA, reboot, reaparición online y confirmación final.

La validación queda cerrada como evidencia suficiente para la RC, con la salvedad operativa de que el `rollout_token` debe ser único por campaña.
