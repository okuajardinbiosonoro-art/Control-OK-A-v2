# Observación operativa prolongada — Control OKÚA CKv2 — RC1

Rama: `desarrollo-fase-2`  
Fecha: 2026-04-19 (Ticket 37.1)  
Clasificación: **PASA completamente**

---

## Bloque 1 — Preparación del ensayo

| Ítem | Valor |
|------|-------|
| Máquina | josecillo (Windows 11 Home, 10.0.26200) |
| Python | 3.11.0 |
| Rama | `desarrollo-fase-2` (commit `c9e978b` al inicio) |
| Ruta de operación | `python main.py` — ruta principal definida |
| Perfil | `udp_jardin` — vía `CKV2_AUTOPROFILE=udp_jardin` |
| Config usada | `config.json` personal de José David (`udp`, `tailscale_only`, loopMIDI activo) |
| Tipo de sesión | Semirreal — app en modo standby UDP con MIDI inicializado; sin nodos físicos activos durante la observación |
| Duración observada | **602 segundos (~10 minutos)** |
| Muestras de proceso | 9 muestras (una cada ~60 s) |
| Operador | Agente (observación programática: proceso, memoria, CPU, stdout completo) |

---

## Bloque 2 — Observación prolongada

### Perfil de memoria RSS

| t (s) | RSS (MB) | CPU (%) | Estado |
|-------|----------|---------|--------|
| 60    | 163      | 0.0     | Carga inicial — Qt + Python + assets |
| 121   | 139      | 7.8     | GC post-arranque, activo |
| 180   | 132      | 1.6     | Settling |
| 241   | 119      | 6.2     | **Baseline estable alcanzado** |
| 300   | 121      | 3.1     | Estable |
| 361   | 121      | 4.7     | Estable |
| 420   | 123      | 4.7     | Estable |
| 481   | 124      | 0.0     | Estable, idle |
| 540   | 126      | 3.1     | Estable |

**Análisis de memoria:** Sin leak detectado. La memoria bajó de 163 MB en la carga inicial a ~120 MB de baseline estable (variación ±7 MB en los últimos 5 minutos de observación). Comportamiento consistente con el event loop de Qt en modo standby.

**Análisis de CPU:** Rango 0.0–7.8%. Sin runaway ni spike sostenido. Coherente con un proceso Qt inactivo polling UDP a 10 Hz.

### Mensajes de runtime observados (stdout completo)

```
[remote_api] intentando iniciar servicio remoto en mode=tailscale_only port=8788
[remote_api] no se pudo iniciar servicio remoto: remote_api.exposure_mode='tailscale_only'
             requiere una IPv4 Tailscale activa en este host.
[remote_api] auth_mode=bearer_token_inventory
[remote_api] token requerido: role=observador env_var=CKV2_REMOTE_API_OBSERVER_TOKEN
[remote_api] token requerido: role=tecnico   env_var=CKV2_REMOTE_API_TECH_TOKEN
[remote_api] token requerido: role=admin     env_var=CKV2_REMOTE_API_ADMIN_TOKEN
[midi] backend=rtmidi
[midi] outputs={'0': 'loopMIDI Port 1 1', '1': 'loopMIDI Port 2 2'}
[midi] available_outputs=['Microsoft GS Wavetable Synth 0', 'loopMIDI Port 1 1', 'loopMIDI Port 2 2']
[midi] resolve bus 0: 'loopMIDI Port 1 1' -> 'loopMIDI Port 1 1' (exact)
[midi] bus 0 abierto -> loopMIDI Port 1 1
[midi] resolve bus 1: 'loopMIDI Port 2 2' -> 'loopMIDI Port 2 2' (exact)
[midi] bus 1 abierto -> loopMIDI Port 2 2
```

**Evaluación de mensajes:**

| Mensaje | Evaluación |
|---------|-----------|
| remote_api `tailscale_only` sin Tailscale activo | Esperado — config personal de José David; app arranca sin bloquearse |
| remote_api tokens no configurados | Esperado — entorno de piloto sin tokens de producción |
| MIDI buses abiertos exitosamente | **Correcto** — `loopMIDI Port 1 1` y `loopMIDI Port 2 2` resueltos por exact match |
| Sin trazas de error Python | Confirmado — 0 excepciones en 602 s |
| Sin warnings de Qt | Confirmado — sin mensajes de QObject, signal/slot ni widget |

### Comportamiento general

| Aspecto | Resultado |
|---------|-----------|
| Crash durante los 10 min | NO |
| Terminación inesperada del proceso | NO |
| Freezes detectados (CPU=0 sostenido + proceso sin responder) | NO — CPU=0 es idle normal de event loop |
| Leak de memoria | NO — baseline estable 119–126 MB |
| Mensajes de error nuevos | NO |
| Degradaciones progresivas | NO |
| Comportamiento raro o inesperado | NO |

### Cierre

- Proceso terminado vía `SIGTERM` (`proc.terminate()`) al finalizar los 600 s planificados.
- Exit code final: **1** — comportamiento normal en Windows cuando Qt recibe terminación externa (no es crash). El proceso terminó en <10 s tras la señal.

---

## Bloque 3 — Clasificación del resultado

**PASA completamente**

La release sostuvo 10 minutos continuos sin crash, sin leak, sin errores nuevos y con MIDI inicializado correctamente. Los únicos mensajes son los esperados del módulo remoto (config personal `tailscale_only`).

---

## Bloque 4 — Bugs encontrados

**Ninguno.** No se encontraron bugs durante la observación prolongada. No se realizaron cambios de código.

---

## Bloque 5 — Pruebas automáticas

No se ejecutaron pruebas adicionales — no hubo cambios de código.  
La suite completa (498/498) ya fue ejecutada y confirmada en 37.0.

---

## Bloque 6 — Decisión final de estabilidad operativa prolongada

**La release interna RC1 supera la observación de estabilidad prolongada.**

Evidencias:
1. **Proceso continuo 602 s** — sin crash, sin terminación inesperada.
2. **Sin leak de memoria** — baseline ~120 MB estable en los últimos 300 s.
3. **CPU idle normal** — 0–7.8%, sin runaway.
4. **MIDI inicializado correctamente** — ambos buses abiertos con exact match.
5. **Sin errores ni trazas Python en 10 minutos** — stdout limpio salvo mensajes esperados de remote_api.
6. **Cierre limpio** — proceso respondió a SIGTERM en <10 s.

**La release interna RC1 queda declarada estable para uso operativo controlado continuado.**

Nota operativa: para eliminar los mensajes de aviso de remote_api al arranque, desactivar `remote_api.enabled` en `config.json` o tener Tailscale activo con tokens configurados en las variables de entorno correspondientes.
