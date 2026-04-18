# Runbook operativo — Control OKÚA CKv2 — RC Funcional

Rama: `desarrollo-fase-2`  
Fecha: 2026-04-16 (Ticket 35.0 — actualizado en 35.0-correctivo)  
Audiencia: José David — uso controlado en instalación OKÚA

> Este documento es la guía de operación de campo. Para contexto de validación, deuda residual y decisión RC ver [`release_candidate_handoff.md`](release_candidate_handoff.md).

---

## 1 — Checklist de pre-operación

Ejecutar antes de cada sesión. Son 7 verificaciones; si alguna falla, ver §4 (Contingencia).

| # | Verificación | Cómo confirmar |
|---|-------------|----------------|
| P1 | Python 3.11+ disponible | `python --version` → `3.11.x` o superior |
| P2 | Dependencias instaladas | `pip show PySide6 rtmidi` sin error |
| P3 | `config.json` presente en raíz del repo | `ls config.json` — debe existir |
| P4 | Perfil activo correcto en `config.json` | Abrir `config.json` → `"profile": {"active": "udp_jardin"}` (o el perfil deseado) |
| P5 | loopMIDI activo con Port 1 y Port 2 visibles | Bandeja del sistema: ícono loopMIDI activo; dos puertos abiertos |
| P6 | Red local accesible (para UDP) | `ping 192.168.1.89` responde, o nodos confirmados activos |
| P7 | Sin proceso previo de la app colgado | Verificar en el Administrador de tareas que no haya `python main.py` corriendo |

---

## 2 — Arranque

### Artefacto principal de esta RC

**Ruta principal recomendada: `python main.py` desde el repositorio en `desarrollo-fase-2`.**

Esta RC fue validada íntegramente desde fuente. No se requiere el ejecutable empaquetado para uso controlado. El `.exe` generado por PyInstaller (`ControlOkuaV2.spec`) es una alternativa secundaria para distribución futura; no es la ruta operativa validada de esta RC.

```bash
# Desde la raíz del repositorio (rama desarrollo-fase-2)
python main.py
```

### Qué esperar al abrir

| Elemento | Estado esperado |
|----------|----------------|
| Título de ventana | `Control OKÚA · CKv2` |
| Barra lateral | Inicio / Nodos / Diagnóstico / Técnico / Firmware / Remoto |
| Chip de estado (Home) | `Sesión inactiva` |
| Mapa Home | 5 cajas visibles, sin color activo (sin sesión) |
| Consola | Sin traceback, sin `ERROR` en las primeras líneas |

Si la ventana abre y cumple lo anterior: **arranque correcto**. Continuar a §3.

---

## 3 — Operación normal

### 3.1 — Iniciar sesión UDP (perfil `udp_jardin`)

1. Verificar en Home que el chip dice `Sesión inactiva`.
2. Si el perfil visible no es `UDP Jardín`: `Aplicación → Cambiar perfil → UDP Jardín → Aceptar`.
3. Clic **"Iniciar sesión"** en Home.
4. Esperar sincronización (típico: 2–5 s con nodos activos).
5. Confirmación visual:
   - Chip de estado cambia a estado activo.
   - Cajas con nodos online se colorean en el mapa.
   - `Nodos` muestra árbol con EB1 / EB2 (u otros nodos activos).

### 3.2 — Verificar nodos en sesión

1. Navegar a **Nodos** en la barra lateral.
2. Confirmar columnas: Nodo, Estado, Último visto, PPS, Pérdida, RSSI, Última nota/vel.
3. Nodos esperados: `EB1` (192.168.1.89, Caja 1) y `EB2` (192.168.1.90, Caja 2) en estado ONLINE.

### 3.3 — Flujo mapa ↔ Nodos

1. En Home, clic sobre una caja con nodos.
2. Aparece CTA **"Ver nodos"**.
3. Clic "Ver nodos" → Nodos abre con barra de contexto de caja (`Caja: X — N nodos`).
4. Clic **"Ver caja en inicio"** → retorno a Home con caja seleccionada.

> Esta interacción visual queda como confirmación final por José David — es el único escenario no observado por el agente durante la RC.

### 3.4 — Diagnóstico de runtime

- Navegar a **Diagnóstico**: 7 campos de resumen, sección "Chequeos previos" plegable.
- Navegar a **Técnico → Comandos**: botón "Solicitar STAT" para solicitar estado a nodos.

### 3.5 — Detener sesión

1. Clic **"Detener sesión"** en Home (o sección Diagnóstico).
2. Chip regresa a `Sesión inactiva`.
3. Verificar consola — sin `ERROR` ni traceback al detener.

### 3.6 — Salida segura

1. Detener la sesión antes de cerrar (§3.5).
2. Cerrar la ventana o `Aplicación → Salir`.
3. Verificar que el proceso Python termina (Administrador de tareas).

---

## 4 — Contingencia y rollback

### La app no abre (crash inmediato)

| Síntoma | Acción |
|---------|--------|
| `ModuleNotFoundError` en consola | `pip install -r requirements.txt` y reintentar |
| `KeyError` o `ValueError` al leer config | Verificar `config.json` contra `config.example.json`; corregir clave faltante |
| Traceback en `main.py` línea de QApplication | Verificar que `PySide6` está instalado: `pip show PySide6` |
| Ventana negra o freeze en arranque | Verificar que loopMIDI está activo con puertos abiertos antes de iniciar |

### No inicia sesión / sin nodos visibles

| Síntoma | Acción |
|---------|--------|
| Chip nunca sale de `Sesión inactiva` | Verificar `config.json` → perfil activo = `udp_jardin` y modo = `udp` |
| Árbol Nodos vacío | `ping 192.168.1.89` y `.90` — si no responden, los nodos están apagados o fuera de red |
| Puertos UDP bloqueados | Verificar firewall de Windows: puertos 5005 y 5006 UDP deben estar abiertos |
| Error MIDI en consola | Verificar loopMIDI: `Port 1` y `Port 2` visibles; reiniciar loopMIDI si es necesario |

### El mapa no muestra estado de cajas con sesión activa

| Síntoma | Acción |
|---------|--------|
| Cajas grises aunque hay nodos en árbol | Esperar 5–10 s extra (primer ciclo de STAT puede tardar) |
| Cajas grises tras 30 s | Navegar a Diagnóstico → "Detalle UDP" — verificar paquetes recibidos |

### La sesión no detiene limpiamente

| Síntoma | Acción |
|---------|--------|
| App no responde tras "Detener sesión" | Esperar 10 s; si sigue colgada, cerrar la ventana con Alt+F4 |
| Proceso Python sigue en Task Manager | Finalizar proceso manualmente en Task Manager |

### Rollback al último estado estable

Si la app se corrompe o hay regresión inesperada:

```bash
git fetch origin
git checkout desarrollo-fase-2
git reset --hard origin/desarrollo-fase-2
python -m pytest tests/ -q
python main.py
```

> El último commit verificado de la RC es `75943c3` (Ticket 35.0 — runbook operativo). `491/491` tests pasan.

---

## 5 — Alcance de esta RC

### Qué está validado y listo para uso controlado

| Ítem | Estado |
|------|--------|
| Sesión UDP con nodos OKÚA en red local | VALIDADO — 320 EVT + 16 STAT, 0 errores (34.7) |
| MIDI enrutado via loopMIDI Port 1 + Port 2 | VALIDADO — 320 mensajes sin error (34.7) |
| Mapa Home — capa de datos (estado por caja) | VALIDADO — 5 cajas con estados coherentes (34.7) |
| Flujo mapa ↔ Nodos — capa de datos | VALIDADO — filtrado y resolución inversa correctos (34.7) |
| QA pantalla Firmware / OTA UI | VALIDADO — catálogo, despliegue y campaign dialog (35.2) |
| Campaña OTA end-to-end con hardware real | VALIDADO — EB1 canary COMPLETED, health gate PASSED (35.6) |
| Suite completa de tests (491/491) | PASA |
| Arranque visual y navegación básica | CONFIRMADO por José David (34.5, commit a27d2b5) |

### Qué queda pendiente antes del release final

| Ítem | Bloqueante para RC | Pendiente de |
|------|-------------------|--------------|
| Validación visual interactiva del mapa (click cajas, CTA "Ver nodos") | No | José David — sesión interactiva |
| Sesión serial con Maestro USB | No | Cuando haya Maestro disponible |
| Tag de release en `main` | No | Después de confirmación visual del mapa |

### Qué NO cubre esta RC (fuera de alcance)

- Uso multiusuario o en máquinas distintas a la de José David.
- Deploy o distribución del `.exe` a terceros.
- Operación con más de 2 nodos activos simultáneos (validado con EB1 + EB2 únicamente).
- Perfil `lab_sim` en entorno productivo (es perfil de laboratorio).

---

## 6 — Referencias rápidas

| Documento | Contenido |
|-----------|-----------|
| [`release_candidate_handoff.md`](release_candidate_handoff.md) | Qué es la RC, evidencia de validación, deuda residual clasificada |
| [`baseline_release_checklist.md`](baseline_release_checklist.md) | Checklist técnico de cierre (suite, icono, packaging, branding) |
| [`baseline_functional_qa_execution.md`](baseline_functional_qa_execution.md) | Acta completa de validación operativa — evidencia sesión UDP real (34.7) |
| `config.example.json` | Plantilla de configuración con todos los campos documentados |
| `README.md` | Arquitectura técnica, flujos, protocolo UDP, identidad de nodos |
