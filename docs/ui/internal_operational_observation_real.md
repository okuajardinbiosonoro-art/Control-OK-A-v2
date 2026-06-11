# Observación operativa prolongada real — Control OKÚA CKv2 — RC1

Rama: `desarrollo-fase-2`  
Fecha: 2026-04-19 (Ticket 37.2)  
Clasificación: **PASA completamente**

---

## Bloque 1 — Preparación del ensayo

| Ítem | Valor |
|------|-------|
| Máquina | <DEV_PC> (Windows 11 Home Single Language, 10.0.26200) |
| Python | 3.11.0 |
| Rama | `desarrollo-fase-2` |
| Ruta de operación | Ruta oficial de la app (`python main.py` / `run_app`) automatizada temporalmente sobre el mismo stack Qt para sostener una sesión viva sin intervención manual |
| Perfil | `udp_jardin` |
| Config usada | `config.json` local, modo `udp`, loopMIDI Port 1 y Port 2 activos |
| Tipo de sesión | Sesión UDP real y viva con nodos físicos activos durante toda la ventana |
| Duración observada | **690 s (~11m30s)** |
| Muestras de proceso | 15 muestras |
| Operador | Agente |

---

## Bloque 2 — Observación prolongada real

### Nodos y tráfico reales

| Ítem | Valor |
|------|-------|
| Nodos reales activos | EB1 (`node_id=1`, `192.0.2.10`) y EB2 (`node_id=6`, `192.0.2.10`) |
| Estado de nodos durante la ventana | 2 online, 0 degraded, 0 offline |
| Tráfico observado | EVT + STAT continuos durante toda la sesión |
| Tráfico acumulado al cierre | 27,320 EVT / 1,369 STAT |
| Bytes recibidos al cierre | 584,732 bytes |
| PPS observado | EVT ~39.8-40.0 / STAT ~1.8-2.0 |

### Home, Nodos y Diagnóstico

| Superficie | Comportamiento observado |
|-----------|---------------------------|
| Home | `Estado de sesión: en ejecución` durante toda la ventana |
| Nodos | `Nodos en vivo detectados.` con EB1 y EB2 resolviendo en vivo |
| Diagnóstico | Accesible durante la sesión, con transporte UDP y sesión activa |
| Técnico / Control | Disponible durante la sesión; panel con nodos resolvibles y estado de control-plane sano |

### Pulsos de control reales

| Tiempo aprox. | Acción | Nodo | Resultado |
|---------------|--------|------|-----------|
| ~90 s | `REQUEST_STAT_NOW` | EB1 | `ack_matched`, `ack_stage=1`, `status_code=0`, `err_detail=0`, ~16 ms |
| ~360 s | `REQUEST_STAT_NOW` | EB1 | `ack_matched`, `ack_stage=1`, `status_code=0`, `err_detail=0`, ~15 ms |
| ~540 s | `REQUEST_STAT_NOW` | EB1 | `ack_matched`, `ack_stage=1`, `status_code=0`, `err_detail=0`, ~16 ms |

### Estabilidad observada

| Aspecto | Resultado |
|--------|-----------|
| Crash durante la ventana | NO |
| Freeze perceptible | NO |
| Runaway CPU | NO |
| Crecimiento de memoria preocupante | NO |
| Desincronización mapa ↔ nodos | NO observable |
| Cierre de sesión | Limpio |
| Cierre de app | Limpio |

### Métricas de proceso

| Métrica | Valor |
|--------|-------|
| RSS mínimo | 78.4 MB |
| RSS máximo | 105.3 MB |
| CPU máxima | 5.5 % |
| Muestras | 15 |

### Advertencias / fricciones

| Tipo | Observación |
|------|-------------|
| `remote_api` | Warnings esperados por `tailscale_only` sin Tailscale activo en este host |
| `remote_api` | Warnings esperados por tokens de inventario no definidos en variables de entorno |
| Preflight | `logging_disabled` aparece como info no bloqueante |

---

## Bloque 3 — Clasificación del resultado

**PASA completamente**

La sesión sostuvo nodos reales activos durante toda la ventana, con tráfico EVT/STAT real, control-plane disponible y tres pulsos `REQUEST_STAT_NOW` confirmados por ACK. No hubo crash, freeze, runaway ni degradación progresiva apreciable.

---

## Bloque 4 — Bugfixes pequeños

**Ninguno.**

No aparecieron bugs pequeños atribuibles a la app que justificaran cambio de código.  
La observación mostró comportamiento estable y consistente.

---

## Bloque 5 — Documentación y estado

Documentos alineados con esta observación:

- [`internal_release_checklist.md`](internal_release_checklist.md)
- [`internal_release_notes_rc1.md`](internal_release_notes_rc1.md)
- [`release_candidate_handoff.md`](release_candidate_handoff.md)

No hubo cambios de código, así que no se ejecutaron `compileall` ni `pytest` adicionales para este ticket.

---

## Bloque 6 — Decisión final

La RC1 queda reforzada para operación interna continuada con nodos reales activos y sesión viva sostenida.

Evidencia principal:

1. **690 s** de sesión real viva.
2. **2 nodos reales activos** durante toda la ventana.
3. **3 `REQUEST_STAT_NOW` reales** con ACK confirmado.
4. **CPU y memoria estables** sin deriva preocupante.
5. **Cierre limpio** de sesión y aplicación.

Para contexto previo, ver [`internal_operational_observation.md`](internal_operational_observation.md).
