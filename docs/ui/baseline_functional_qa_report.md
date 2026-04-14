# QA Funcional de Campo — Control OKÚA CKv2 — Baseline

Rama: `desarrollo-fase-2`  
Fecha QA: 2026-04-13 (Ticket 34.4)  
Tipo de QA: funcional operativa + runbook de campo  
Ejecutado por: José David / Claude Code (agente)

---

## Declaración de entorno

| Ítem | Valor |
|------|-------|
| Plataforma | Windows 11 Home Single Language 10.0.26200 |
| Python | 3.11 |
| PySide6 | instalada (sin display disponible en agente) |
| Hardware serial | **NO DISPONIBLE** — sin Maestro ni nodo físico conectado |
| Red UDP / nodos | **NO DISPONIBLE** — sin nodos OKÚA accesibles en red |
| Display gráfico | **NO DISPONIBLE** — entorno de agente headless |

---

## Criterio de clasificación

- **[A] EJECUTADO** — prueba corrida de verdad, resultado observado directamente.  
- **[B] DOCUMENTADO** — prueba definida con precisión pero no corrida por falta de hardware/red/display.

No se afirma ninguna validación que no pertenezca al grupo **[A]**.

---

## Matriz de escenarios funcionales

| # | Escenario | Tipo | Resultado | Evidencia |
|---|-----------|------|-----------|-----------|
| 1 | Arranque de app (`python main.py`) | [B] | NO EJECUTADO — sin display | ver runbook §1 |
| 2 | Inicio/Home visible y estable | [B] | NO EJECUTADO — sin display | ver runbook §2 |
| 3 | Navegación a Nodos | [B] | NO EJECUTADO — sin display | ver runbook §3 |
| 4 | Navegación a Diagnóstico | [B] | NO EJECUTADO — sin display | ver runbook §3 |
| 5 | Navegación a Técnico | [B] | NO EJECUTADO — sin display | ver runbook §3 |
| 6 | Navegación a Firmware | [B] | NO EJECUTADO — sin display | ver runbook §3 |
| 7 | Navegación a Remoto | [B] | NO EJECUTADO — sin display | ver runbook §3 |
| 8 | Sesión serial real | [B] | NO EJECUTADO — sin hardware | ver runbook §4 |
| 9 | Sesión UDP real | [B] | NO EJECUTADO — sin red/nodos | ver runbook §5 |
| 10 | Mapa ↔ Nodos (CTA "Ver nodos") | [B] | NO EJECUTADO — sin display | ver runbook §6 |
| 11 | Toasts / avisos no críticos | [A] | PASS — lógica validada por suite pytest (test_toast_manager) | 467 passed |
| 12 | Estado de sesión (lógica) | [A] | PASS — state machine validada (test_session_state_machine, test_session_models) | 467 passed |
| 13 | Cambio de perfil (lógica) | [A] | PASS — profile service + selector validados (test_profile_service, test_profile_mode_consistency) | 467 passed |
| 14 | Estado actual / detalles de sesión (lógica) | [A] | PASS — viewmodels validados (test_main_window_vm, test_home_map_state_vm) | 467 passed |
| 15 | Aplicar servicio remoto (lógica) | [A] | PASS — remote API validada (test_remote_api_service, test_remote_session_service) | 467 passed |
| 16 | Gestor de firmware abre y responde (lógica) | [A] | PASS — firmware VM validada (test_firmware_manager_vm) | 467 passed |
| 17 | Herramientas avanzadas (lógica) | [A] | PASS — control plane panel validado (test_control_plane_panel) | 467 passed |

### Resumen de la matriz

| Grupo | Escenarios | Ejecutados [A] | Documentados [B] |
|-------|-----------|----------------|------------------|
| Arranque y navegación | 1–7 | 0 | 7 |
| Sesiones hardware | 8–9 | 0 | 2 |
| Flujos UI | 10 | 0 | 1 |
| Lógica de negocio validada por suite | 11–17 | 7 | 0 |
| **Total** | **17** | **7** | **10** |

---

## Pruebas automáticas ejecutadas [A]

### 1. Compilación (`compileall`)

```
python -m compileall src main.py
```

**Resultado: PASA** — 0 errores de compilación en todos los módulos de `src/` y `main.py`.

### 2. Suite completa de tests (`pytest`)

```
PYTHONPATH=src python -m pytest tests/ -q --tb=short
```

**Resultado: PASA** — 467 passed, 0 failed, 0 errors (98.84 s)

Cobertura de la suite por dominio:

| Dominio | Archivos de test | Estado |
|---------|-----------------|--------|
| Control plane | 13 | PASS |
| Firmware / OTA | 11 | PASS |
| Sesión y backends | 10 | PASS |
| UI / ViewModels | 15 | PASS |
| Registro / Nodos | 6 | PASS |
| Remote API | 7 | PASS |
| Transports / Protocol | 8 | PASS |
| Preflight / Perfiles | 4 | PASS |
| Utilidades | 5 | PASS |
| **Total** | **79** | **467/467 PASS** |

---

## Bugs encontrados durante este ticket

**Ninguno.** No se realizaron cambios de código en este ticket. Las pruebas automáticas no revelan regresiones. La validación visual y de hardware queda pendiente por falta de entorno.

---

## Runbook de QA funcional de campo

Para ejecutar la QA funcional completa en el entorno operativo real, seguir este runbook sin ambigüedades.

### Prerrequisitos

- Python 3.11+ con dependencias instaladas: `pip install -r requirements.txt`
- `config.json` con al menos un perfil configurado (ver `config.example.json`)
- Para sesión serial: Maestro OKÚA conectado por USB/serial
- Para sesión UDP: nodos OKÚA en la red local, Maestro encendido

---

### §1 — Arranque de app

```bash
python main.py
```

**Criterio PASS:**
- Ventana principal abre sin error en consola.
- Barra lateral visible con secciones: Inicio / Nodos / Diagnóstico / Técnico / Firmware / Remoto.
- Título de ventana: `"Control OKÚA · CKv2"`.
- Status chip inicial: `"Sesión inactiva"`.
- Sin crash, sin traceback.

**Criterio FAIL:** Cualquier excepción en consola, ventana negra, crash inmediato.

---

### §2 — Inicio / Home

1. Verificar que `HomeMapPanel` es visible con altura ≥ 480 px.
2. Verificar mapa con 5 cajas representadas.
3. Verificar botón "Iniciar sesión" activo.
4. Verificar que no hay scrollbar vertical no deseado en Home.
5. Verificar `home_status_chip` con texto "Sesión inactiva".

**Criterio PASS:** Todo visible, sin scroll indeseado, sin errores en consola.

---

### §3 — Navegación a superficies principales

Para cada sección (Nodos, Diagnóstico, Técnico, Firmware, Remoto):

1. Clic en la sección en barra lateral.
2. Verificar que el contenido de la sección se muestra.
3. Verificar que el título y subtítulo corresponden a la sección.
4. Verificar que no hay traceback en consola.

**Verificaciones específicas por sección:**

| Sección | Verificar |
|---------|-----------|
| Nodos | `QTreeWidget` visible, 7 columnas (Nodo, Estado, Último visto, PPS, Pérdida, RSSI, Última nota/vel) |
| Diagnóstico | 7 campos de resumen, sección "Chequeos previos" plegable |
| Técnico | 2 tabs: "Resumen" y "Control F3"; botón "Solicitar STAT" en Control F3 |
| Firmware | Hint visible, botón "Abrir gestor de firmware" |
| Remoto | 7 campos de estado, dropdown "Solo este equipo" / "Solo red Tailscale" |

**Criterio PASS:** Todas las secciones cargan sin error; contenidos corresponden a lo esperado.

---

### §4 — Sesión serial real

**Prerequisito:** Maestro OKÚA conectado por USB, puerto COM visible en sistema.

1. En Diagnóstico, verificar que el puerto serial aparece en "Detalle serial".
2. Seleccionar perfil serial en "Cambiar perfil" (menú Aplicación → Cambiar perfil).
3. Clic "Iniciar sesión" en Home.
4. Esperar handshake; verificar que `home_status_chip` cambia a estado activo.
5. Navegar a Nodos — verificar que aparecen nodos registrados.
6. Navegar a Diagnóstico — verificar campos de runtime actualizados.
7. En Técnico → Control F3 → clic "Solicitar STAT".
8. Verificar que se recibe respuesta (sin timeout ni error visible).
9. Clic "Detener sesión" — verificar que el estado regresa a "Sesión inactiva".

**Criterio PASS:** Sesión inicia, runtime responde, sesión detiene limpiamente.  
**Criterio FAIL:** Timeout en handshake, crash, sesión no detiene, traceback.

---

### §5 — Sesión UDP real

**Prerequisito:** Maestro encendido, nodos OKÚA en red local, perfil UDP configurado.

1. Seleccionar perfil UDP en "Cambiar perfil".
2. Clic "Iniciar sesión" en Home.
3. Esperar sincronización; verificar `home_status_chip` en estado activo.
4. En Home: verificar mapa con estado agregado por caja (colores de caja reflejan nodos).
5. Clic sobre una caja en el mapa.
6. Verificar que aparece CTA "Ver nodos".
7. Clic "Ver nodos" — verificar navegación a Nodos con filtro de caja activo.
8. Verificar barra de contexto visible ("Caja: X — N nodos").
9. Verificar columnas PPS, Pérdida, RSSI con datos reales.
10. Clic "Ver caja en inicio" — verificar retorno a Home con caja seleccionada.
11. Navegar a Diagnóstico — verificar campos de "Detalle UDP" actualizados.
12. Clic "Detener sesión".

**Criterio PASS:** Sincronización ocurre, nodos visibles, flujo mapa↔Nodos funciona.  
**Criterio FAIL:** Sin nodos en árbol, mapa sin estado, crash, timeout.

---

### §6 — Flujo mapa ↔ Nodos (sin sesión real)

**Aplica también si no hay hardware pero sí config con cajas definidas:**

1. En Home, clic sobre caja en mapa.
2. Verificar que aparece CTA "Ver nodos" (aunque no haya datos de runtime).
3. Clic "Ver nodos" — verificar que Nodos abre con barra de contexto de caja.
4. Clic "Ver caja en inicio" — verificar retorno a Home.

**Criterio PASS:** Señales `boxSelectionChanged` y `viewNodesRequested` funcionales.

---

### §7 — Diálogos principales

| Diálogo | Cómo abrir | Verificar |
|---------|-----------|-----------|
| Cambiar perfil | Aplicación → Cambiar perfil | QDialog modal, radiobuttons de perfiles, OK cancela/aplica |
| Estado de sesión | Técnico → Resumen → "Estado de sesión" | QDialog modeless, 7+ campos |
| Gestor de firmware | Firmware → "Abrir gestor de firmware" | Catálogo, filtros, detalle de artifact |
| Herramientas avanzadas | Técnico → Resumen → "Herramientas avanzadas" | Centro técnico con 3 tabs |
| About | Ayuda → Acerca de | Identidad de marca, sin texto genérico |

**Criterio PASS:** Todos abren, muestran contenido correcto, cierran sin error.

---

### §8 — Toast notifications

1. Disparar una acción que produzca toast (ej: iniciar sesión con perfil inválido).
2. Verificar que el toast aparece en bottom-right.
3. Verificar que se descarta automáticamente (auto-dismiss).

**Criterio PASS:** Toast visible, animación slide+fade, desaparece solo.

---

### §9 — Aplicar servicio remoto

**Solo si Remote API está configurada en config.json.**

1. Navegar a Remoto.
2. Seleccionar exposición en dropdown.
3. Clic "Aplicar servicio remoto".
4. Verificar que el campo "Estado" se actualiza.

**Criterio PASS:** Estado cambia sin error, sin traceback.  
**Nota:** No ejecutar si no hay credenciales o si el entorno no es de prueba.

---

## Qué se validó realmente [A]

1. `python -m compileall src main.py` — **PASA** (0 errores)
2. `PYTHONPATH=src python -m pytest tests/ -q` — **PASA** (467/467)
3. Revisión de código de lógica de negocio, state machine, viewmodels, transports (heredada de tickets anteriores 34.0–34.3)

## Qué NO se pudo validar y por qué [B]

| Escenario | Razón |
|-----------|-------|
| Arranque visual de app | Entorno de agente headless, sin display |
| Navegación GUI entre secciones | Sin display/GUI |
| Sesión serial | Sin hardware Maestro conectado |
| Sesión UDP | Sin nodos OKÚA en red |
| Flujo mapa ↔ Nodos (visual) | Sin display |
| Diálogos secundarios (visual) | Sin display |
| Toast notifications (visual) | Sin display |

**La validación de estos escenarios requiere el entorno operativo real (máquina con display + hardware/red según aplique).**

---

## Bugs encontrados y corregidos en este ticket

**Ninguno.** No se encontraron bugs nuevos durante la ejecución de las pruebas automáticas. La suite de 467 tests pasó íntegra.

Los bugs conocidos de tickets anteriores (ya resueltos o documentados como fuera de alcance) se mantienen en el registro de `baseline_gui_qa_report.md`.

---

## Decisión final: candidatura a release

### Criterio técnico-operativo

| Dimensión | Estado |
|-----------|--------|
| Suite automática (467 tests) | PASA |
| Compilación limpia | PASA |
| Código de lógica de negocio auditado | PASA (34.3) |
| Branding y microcopy | PASA (34.1) |
| Higiene técnica | PASA (34.2) |
| Packaging (PyInstaller) | PASA (34.3) |
| Validación visual GUI real | **PENDIENTE** |
| Sesión serial en hardware | **PENDIENTE** |
| Sesión UDP en red real | **PENDIENTE** |

### Veredicto

**La baseline NO es candidata a release funcional todavía.**

Razón: los escenarios de validación visual y de sesiones con hardware (escenarios 1–10 de la matriz) no han sido ejecutados en condiciones reales. Un release funcional requiere al menos:

1. Smoke visual de arranque y navegación en máquina con display.
2. Una sesión serial o UDP confirmada como funcional de extremo a extremo.
3. Confirmación de que los diálogos principales abren sin error en runtime real.

Una vez que esos tres puntos estén verificados, la baseline puede considerarse candidata a release funcional. El runbook completo de §1–§9 queda disponible para esa validación.

---

## Historial de tickets de baseline

| Ticket | Descripción | Estado |
|--------|-------------|--------|
| 34.0 | Consolidación design system | CERRADO |
| 34.1 | Branding, microcopy y chrome | CERRADO |
| 34.2 | Higiene técnica | CERRADO |
| 34.3 | QA baseline GUI + smoke packaging | CERRADO |
| 34.4 | QA funcional de campo + acta de validación | CERRADO (automáticas PASAN; campo pendiente de hardware) |
| 34.5 | Ejecución real de validación funcional | CERRADO PARCIALMENTE — smoke launch sin crash; validación visual y sesión real pendientes de ejecución humana — ver `docs/ui/baseline_functional_qa_execution.md` |
