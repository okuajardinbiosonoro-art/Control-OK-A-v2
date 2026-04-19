# Ensayo de entrega empaquetada (.exe) — Control OKÚA CKv2 — RC1

Rama: `desarrollo-fase-2`  
Fecha: 2026-04-19 (Ticket 36.2)  
Clasificación: **PASA con observaciones menores**

---

## Entorno usado

| Ítem | Valor |
|------|-------|
| Máquina | josecillo (Windows 11 Home, 10.0.26200) |
| Python | 3.11.0 |
| PyInstaller | 6.19.0 |
| Spec usada | `ControlOkuaV2.spec` (en raíz del repo) |
| Commit HEAD al momento del build | `0f08c2f` (rama `desarrollo-fase-2`) |
| Working tree | Limpio respecto a HEAD (solo `.vscode/c_cpp_properties.json` con CRLF) |

---

## Bloque 1 — Build empaquetada

### Verificación previa de la spec

| Ítem | Estado |
|------|--------|
| `assets/branding/okua_app_icon.ico` | EXISTE |
| `assets/branding/okua_icon_256.png` | EXISTE (fallback en spec) |
| `src/control_okua/services/remote_console_assets/` | EXISTE — `app.js`, `index.html`, `styles.css` |
| `pathex` → `src/` | CORRECTO |
| `name` en EXE | `"Control OKÚA CKv2"` |
| `console=False` | CORRECTO (windowed) |
| `icon` | `assets/branding/okua_app_icon.ico` |

### Resultado del build

```
pyinstaller ControlOkuaV2.spec --noconfirm
```

| Ítem | Valor |
|------|-------|
| Resultado | **EXITOSO** — `Build complete!` sin errores |
| Artefacto generado | `dist/Control OKÚA CKv2.exe` |
| Tamaño | 53.8 MB |
| Fecha de build | 2026-04-19 09:41 |
| UPX compresión | Activa (`upx=True` en spec) |

El artefacto anterior (`dist/Control OKÚA CKv2.exe`, 51.2 MB, del 2026-04-15) fue sobreescrito. La diferencia de tamaño (+2.6 MB) refleja el código añadido en los tickets 35.x–36.1 desde el último build.

---

## Bloque 2 — Arranque del exe

### Estado del `dist/config.json` al momento del arranque

El exe busca `config.json` en el mismo directorio donde reside el exe. El archivo presente en `dist/` tiene:

| Clave | Valor en `dist/config.json` | Valor en `config.example.json` |
|-------|---------------------------|-------------------------------|
| `profile.active` | `"udp_jardin"` | `null` (requiere configuración) |
| `mode` | `"udp"` | `null` |
| `midi.outputs["0"]` | `"loopMIDI Port 1 1"` | `"loopMIDI Port 1"` |
| `midi.outputs["1"]` | `"loopMIDI Port 2 2"` | `"loopMIDI Port 2"` |
| `remote_api.enabled` | `true` | `false` |
| `remote_api.exposure_mode` | `"tailscale_only"` | `"local_only"` |
| `remote_api.port` | `8802` | `8788` |

> El `dist/config.json` es la configuración personal de José David, no un config genérico de distribución. Los nombres de puerto MIDI con sufijo duplicado (`"loopMIDI Port 1 1"`) corresponden al sistema de José David. En una distribución limpia, se debe copiar `config.example.json` como base.

### Resultado del arranque

El agente no puede observar la GUI directamente, pero lanzó el proceso y verificó que seguía activo tras 7 segundos:

| Comprobación | Resultado |
|-------------|-----------|
| Proceso arranca | **CONFIRMADO** — proceso vivo a los 7 s, memoria ~15 MB RSS |
| Crash inmediato | **NO** — ningún exit code de error |
| Proceso terminado limpiamente | Sí — `Stop-Process` ejecutado manualmente |

### Comprobaciones visuales — PENDIENTE DE JOSÉ DAVID

Las siguientes comprobaciones requieren observación directa del exe en pantalla:

| # | Comprobación | Qué observar |
|---|-------------|--------------|
| V1 | Nombre en barra de título | `Control OKÚA · CKv2` |
| V2 | Icono en barra de título y taskbar | Icono OKÚA branding (no el icono Python genérico) |
| V3 | Home abre correctamente | 5 cajas del mapa visibles, chip `Sesión inactiva` |
| V4 | Navegación a Nodos | Árbol de nodos visible sin traceback |
| V5 | Navegación a Diagnóstico | Resumen runtime sin crash |
| V6 | Navegación a Técnico | Sección Comandos visible |
| V7 | Cierre limpio | Ventana cierra, proceso termina |

Para ejecutar: doble clic en `dist/Control OKÚA CKv2.exe`. Asegurarse de que loopMIDI está activo antes. Si el `config.json` de `dist/` tiene ports MIDI incorrectos para el sistema actual, la app puede mostrar un aviso de MIDI pero abrirá igualmente.

---

## Bloque 3 — Hallazgos y observaciones

### Hallazgo H1 — `dist/config.json` tiene config personal, no genérica

**Descripción:** El archivo `dist/config.json` (fecha: 2026-04-02) contiene valores específicos del sistema de José David:
- Ports MIDI: `"loopMIDI Port 1 1"` / `"loopMIDI Port 2 2"` (no el nombre estándar del example)
- Remote API: habilitada en modo `tailscale_only` con puerto 8802

**Impacto:** En la máquina de José David, el arranque es correcto. En una distribución a otro entorno, los ports MIDI no coincidirían y la app arrancaría con aviso MIDI (no bloqueante).

**Acción:** Documentado como observación de distribución. Para preparar una distribución limpia, copiar `config.example.json` como `config.json` en `dist/` antes de entregar.

**Clasificación:** No es un bug de código. Es una nota operativa de distribución.

### Hallazgo H2 — El exe no bundlea `config.json`

**Descripción:** La spec no incluye `config.json` en `datas`. El exe busca `config.json` en su directorio de ejecución. Si no existe, la app crea uno con defaults v2 y abre el selector de perfil.

**Impacto:** Comportamiento correcto para distribución — cada máquina destino debe proveer su propio `config.json`.

**Acción:** Documentado. El runbook de distribución debe indicar que se requiere copiar `config.example.json` y configurar el perfil antes del primer uso.

---

## Bloque 4 — Correcciones realizadas

No se requirieron correcciones de código o spec. Los hallazgos son notas operativas de distribución, no bugs.

---

## Protocolo de validación visual para José David

Para completar la validación del exe en esta máquina:

1. Abrir `dist/Control OKÚA CKv2.exe` (doble clic o desde Explorer)
2. Confirmar que:
   - El ícono en la taskbar es el ícono OKÚA (no el Python genérico)
   - La barra de título muestra `Control OKÚA · CKv2`
   - Home carga con el mapa de 5 cajas y chip `Sesión inactiva`
3. Navegar a Nodos, Diagnóstico, Técnico brevemente (10 segundos cada uno)
4. Cerrar la app con `Aplicación → Salir` o con la X
5. Confirmar que el proceso termina (no queda colgado en Task Manager)

Completar la tabla del Bloque 2 §Comprobaciones visuales al ejecutar este protocolo.

---

## Resumen de escenarios

| Escenario | Estado |
|-----------|--------|
| S1 — Build con spec oficial | **PASA** |
| S2 — Nombre del exe | **PASA** — `Control OKÚA CKv2.exe` |
| S3 — Icono embebido en spec | **PASA** — `assets/branding/okua_app_icon.ico` referenciado correctamente |
| S4 — Arranque sin crash (proceso vivo 7 s) | **PASA (programático)** |
| S5 — Verificación visual icono/título | **PENDIENTE — José David** |
| S6 — Home y navegación mínima | **PENDIENTE — José David** |
| S7 — Cierre limpio | **PENDIENTE — José David** |

---

## Decisión final

**La ruta empaquetada `.exe` es VIABLE como alternativa de distribución.**

Condiciones confirmadas:
1. El build es exitoso y reproducible con `pyinstaller ControlOkuaV2.spec --noconfirm`.
2. El exe arranca sin crash (confirmado programáticamente).
3. La spec está correctamente configurada: nombre, icono, assets incluidos.
4. Para distribución limpia, se debe proveer un `config.json` basado en `config.example.json` junto al exe — el `dist/config.json` actual es la config personal de José David.
5. La verificación visual del icono, título y navegación queda pendiente de confirmación por José David (protocolo en Bloque 4).

**Esta ruta sigue siendo secundaria respecto a `python main.py`.** La ruta desde fuente es la validada para uso operativo. El exe es la alternativa para distribución sin entorno Python.
