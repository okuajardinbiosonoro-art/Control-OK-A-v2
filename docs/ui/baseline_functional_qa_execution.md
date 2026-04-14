# Acta de Ejecución — QA Funcional Real — Control OKÚA CKv2 — Ticket 34.5

Rama: `desarrollo-fase-2`  
Fecha ejecución: 2026-04-13 (Ticket 34.5)  
Tipo: validación funcional real — ejecución de runbook de campo  
Ejecutado por: José David / Claude Code (agente)

---

## Declaración de entorno real — 34.5

| Ítem | Valor confirmado |
|------|-----------------|
| Plataforma | Windows 11 Home Single Language 10.0.26200 |
| Python | 3.11.0 |
| Entorno de agente | Claude Code dentro de extensión VSCode — mismo host físico del usuario |
| Display gráfico | **DISPONIBLE** en la máquina del usuario (Windows 11 con sesión activa) |
| Observación visual del agente | **NO POSIBLE** — el agente no puede observar el contenido de la pantalla |
| Puerto serial COM3 | Detectado — Serie estándar sobre vínculo Bluetooth (Bluetooth, no Maestro) |
| Puerto serial COM18 | Detectado — Serie estándar sobre vínculo Bluetooth (Bluetooth, no Maestro) |
| Hardware Maestro/serial USB | **NO DETECTADO** — sin puerto USB-serial físico conectado |
| Red UDP / nodos OKÚA | **NO VERIFICADO** — socket UDP puede bindear; disponibilidad de nodos desconocida |
| Perfil activo en config.json | `udp_jardin` (UDP, modo instalación) |
| Perfiles disponibles | `serial_local`, `udp_jardin`, `lab_sim` |

---

## Criterio de clasificación

- **[A] EJECUTADO POR AGENTE** — acción corrida directamente por el agente con resultado observable programáticamente.
- **[C] EJECUTADO PARCIALMENTE** — acción corrida por el agente, con resultado parcial (sin observación visual posible).
- **[B] DOCUMENTADO / PENDIENTE HUMANO** — escenario definido, no ejecutable por el agente; requiere validación por José David.

No se afirma ninguna validación visual sin haberla observado.

---

## Pruebas automáticas ejecutadas [A]

### 1. Compilación (`compileall`)

```
python -m compileall src main.py -q
```

**Resultado: PASA** — 0 errores de compilación. Idéntico a 34.4, confirmado en 34.5.

### 2. Suite completa de tests (`pytest`)

```
PYTHONPATH=src python -m pytest tests/ -q --tb=short
```

**Resultado: PASA** — 467 passed, 0 failed, 0 errors (93.88 s)

Sin regresiones desde 34.4. La suite está íntegra.

### 3. Verificación de importaciones

```python
import control_okua.app_qt.app
import control_okua.app_qt.main_window
import control_okua.core.session.session_state_machine
import control_okua.core.profiles.profile_service
```

**Resultado: PASA** — todos los módulos principales importan sin error.  
`run_app` es callable: confirmado.

---

## Smoke launch — arranque real en máquina con display [C]

### Procedimiento

Se lanzó el proceso real de la aplicación como subproceso desde el agente:

```python
subprocess.Popen([sys.executable, 'main.py'], stdout=PIPE, stderr=PIPE)
# espera 5 segundos → poll() → verifica si sigue vivo
```

### Resultado

| Métrica | Valor |
|---------|-------|
| PID asignado | 32192 |
| Estado a los 5 segundos | **VIVO** — sin crash de arranque |
| Salida por stderr | **VACÍA** — ningún error impreso |
| Salida por stdout | Vacía (normal en PySide6) |
| Código de salida antes del timeout | N/A (proceso terminado por agente tras 5s) |

**Conclusión del smoke launch:**  
La aplicación arrancó sin excepción, sin traceback y sin error de importación. El proceso estuvo vivo 5+ segundos con stderr limpio. La ventana SE ABRIÓ en el display de la máquina del usuario (Windows 11, sesión activa), pero el agente no tiene capacidad de observar qué se renderizó en pantalla.

**Esto es un avance real respecto a 34.4**, donde el lanzamiento no fue intentado. Sin embargo, **no sustituye la validación visual**.

---

## Estado de hardware detectado [A]

### Puertos seriales

| Puerto | Descripción | ¿Maestro OKÚA? |
|--------|-------------|----------------|
| COM3 | Serie estándar sobre vínculo Bluetooth | NO — Bluetooth |
| COM18 | Serie estándar sobre vínculo Bluetooth | NO — Bluetooth |

**Sin puerto USB-serial detectado** compatible con Maestro OKÚA. Sesión serial NO ejecutable.

### UDP / Red

- Socket UDP pudo bindear en `0.0.0.0:0` → stack de red operativo.
- Disponibilidad de nodos OKÚA en la red: **desconocida**. No se intentó sondeo de nodos.
- Perfil activo `udp_jardin` está configurado con puertos: evt=5005, stat=5006, cmd=5007.

**Sin confirmación de nodos disponibles.** Sesión UDP real: estado desconocido.

---

## Matriz de escenarios — ejecución real 34.5

| # | Escenario | Tipo | Resultado | Evidencia / Motivo |
|---|-----------|------|-----------|-------------------|
| 1 | Arranque de app (`python main.py`) | [C] | SMOKE PASS — proceso vivo 5s, stderr vacío | PID 32192, stderr vacío |
| 2 | Inicio/Home visible y estable | [B] | PENDIENTE HUMANO — agente no puede observar pantalla | ventana abrió en display; sin confirmación visual |
| 3 | Navegación a Nodos | [B] | PENDIENTE HUMANO | sin interacción GUI posible |
| 4 | Navegación a Diagnóstico | [B] | PENDIENTE HUMANO | sin interacción GUI posible |
| 5 | Navegación a Técnico | [B] | PENDIENTE HUMANO | sin interacción GUI posible |
| 6 | Navegación a Firmware | [B] | PENDIENTE HUMANO | sin interacción GUI posible |
| 7 | Navegación a Remoto | [B] | PENDIENTE HUMANO | sin interacción GUI posible |
| 8 | Estado actual / cambiar perfil | [B] | PENDIENTE HUMANO | sin interacción GUI posible |
| 9 | Mapa ↔ Nodos (CTA "Ver nodos") | [B] | PENDIENTE HUMANO | sin interacción GUI posible |
| 10 | Toasts / mensajes no críticos | [A] | PASS por suite (test_toast_manager) | 467 passed |
| 11 | Sesión serial real | [B] | NO EJECUTADO — sin Maestro USB detectado | COM3/COM18 son Bluetooth |
| 12 | Sesión UDP real | [B] | NO EJECUTADO — nodos desconocidos | socket OK; nodos no verificados |

### Resumen de la matriz 34.5

| Grupo | Escenarios | [A] Agente | [C] Parcial | [B] Pendiente humano |
|-------|-----------|-----------|-------------|----------------------|
| Arranque | 1 | 0 | 1 | 0 |
| Navegación GUI | 2–9 | 0 | 0 | 8 |
| Lógica (suite) | 10 | 1 | 0 | 0 |
| Sesiones hardware | 11–12 | 0 | 0 | 2 |
| **Total** | **12** | **1** | **1** | **10** |

---

## Bugs encontrados durante este ticket

**Ninguno.** No se realizaron cambios de código en este ticket. Los tests automatizados no revelan regresiones. El smoke launch no expuso errores de arranque.

---

## Qué se avanzó respecto a 34.4

| Ítem | 34.4 | 34.5 |
|------|------|------|
| Smoke launch intentado | NO | SÍ — proceso vivo 5s, stderr limpio |
| Puertos seriales verificados | NO | SÍ — COM3/COM18 detectados (ambos Bluetooth) |
| UDP socket verificado | NO | SÍ — puede bindear |
| Perfiles verificados | NO | SÍ — 3 perfiles (`serial_local`, `udp_jardin`, `lab_sim`) |
| Validación visual | NO (sin display en agente) | NO (display disponible pero agente no puede observar) |
| Sesión serial real | NO | NO — sin Maestro USB |
| Sesión UDP real | NO | NO — nodos no verificados |

---

## Decisión final: candidatura a release funcional — 34.5

### Criterio mínimo del ticket

| Criterio | Estado |
|---------|--------|
| 1. App funciona en máquina con display real | PARCIAL — smoke lanzado sin crash; validación visual pendiente |
| 2. Navegación principal sana | PENDIENTE — no verificable por agente |
| 3. Diálogos principales sin romper flujo | PENDIENTE — no verificable por agente |
| 4. Mapa ↔ Nodos funciona en runtime real | PENDIENTE — no verificable por agente |
| 5. Al menos una sesión real (serial o UDP) | NO CUMPLIDO — sin Maestro USB; nodos UDP desconocidos |
| 6. Sin bug bloqueante de operación | CUMPLIDO — suite 467/467, smoke sin crash |

### Veredicto

**La baseline TODAVÍA NO es candidata a release funcional.**

**Razón técnica directa:**

El agente no puede sustituir la validación visual. El smoke launch confirma que la app arranca sin excepción (avance real sobre 34.4), pero no sustituye la confirmación humana de:

1. Que la Home se muestra correctamente con mapa visible y chip de estado.
2. Que la navegación entre las 5 secciones responde sin error.
3. Que los diálogos (cambiar perfil, estado de sesión, gestor de firmware, herramientas avanzadas) abren sin crash.
4. Que el flujo mapa ↔ Nodos funciona en runtime real.
5. Que al menos una sesión real (serial con Maestro conectado por USB, o UDP con nodos en red) se ejecuta de extremo a extremo.

Ninguno de estos cinco puntos puede ser confirmado por el agente. Solo José David puede cerrarlos ejecutando el runbook manualmente en su estación con display.

### Lo que falta para declarar la baseline candidata

1. **José David ejecuta `python main.py` y confirma visualmente:**
   - Home abre correctamente
   - Mapa visible con 5 cajas
   - Navegación a las 5 secciones responde
   - Al menos un diálogo principal abre sin error
2. **José David conecta Maestro por USB o confirma nodos UDP en red** y ejecuta al menos una sesión real.
3. **Sin bug bloqueante** encontrado durante esa sesión.

Si esos tres puntos se cumplen, la baseline puede declararse candidata. El runbook de 34.4 (§1–§9) está listo para ejecutarlo.

---

## Historial acumulado de tickets de baseline

| Ticket | Descripción | Estado |
|--------|-------------|--------|
| 34.0 | Consolidación design system | CERRADO |
| 34.1 | Branding, microcopy y chrome | CERRADO |
| 34.2 | Higiene técnica | CERRADO |
| 34.3 | QA baseline GUI + smoke de packaging | CERRADO |
| 34.4 | QA funcional de campo + runbook | CERRADO — automáticas PASAN; ejecución real pendiente |
| 34.5 | Ejecución real de validación funcional | **CERRADO PARCIALMENTE** — smoke launch sin crash; validación visual y sesión real pendientes de ejecución humana |
