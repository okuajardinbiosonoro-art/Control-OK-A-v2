# Ensayo de entrega empaquetada (.exe) — Control OKÚA CKv2 — RC1

Rama: `desarrollo-fase-2`
Fecha: 2026-04-19 (Ticket 36.2 — actualizado post-correcciones)
Clasificación: **PASA — confirmado visualmente por José David (2026-04-19)**

---

## Entorno usado

| Ítem | Valor |
|------|-------|
| Máquina | <DEV_PC> (Windows 11 Home, 10.0.26200) |
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

### Comprobaciones visuales — CONFIRMADAS por José David (2026-04-19)

| # | Comprobación | Resultado |
|---|-------------|-----------|
| V1 | Nombre en barra de título | **PASA** — `Control OKÚA · CKv2` visible |
| V2 | Icono en barra de título y taskbar | **PASA** — ícono OKÚA branding original, visible en barra de título y taskbar |
| V3 | Home abre correctamente | **PASA** — mapa de 5 cajas visible, chip `Sesión inactiva` |
| V4 | Navegación a Nodos | **PASA** — árbol de nodos visible sin traceback |
| V5 | Navegación a Diagnóstico | **PASA** — resumen runtime sin crash |
| V6 | Navegación a Técnico | **PASA** — sección Comandos visible |
| V7 | Cierre limpio | **PASA** — ventana cierra, proceso termina |

Validación ejecutada directamente por José David en `<DEV_PC>` (Windows 11 Home, 10.0.26200) mediante doble clic en `dist/Control OKÚA CKv2/Control OKÚA CKv2.exe`.

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

## Bloque 4 — Correcciones realizadas (post validación visual de José David)

Tras la validación visual, José David reportó:

1. **El mapa no estaba disponible** en la app empaquetada.
2. **El ícono en la barra de tareas era genérico** (no el de OKÚA).

### BUG-1 corregido — Mapa no disponible en exe (path frozen incorrecto)

**Causa raíz:** `resolve_home_map_asset_path()` en `home_map_panel.py` usaba `Path(sys.executable).resolve().parent` en modo frozen. En one-file, esto apunta al directorio `dist/` (donde está el `.exe`), pero el asset del mapa está en `sys._MEIPASS` (directorio de extracción temporal). En one-dir, el problema persistía porque `_internal/` no es el directorio del exe.

**Corrección:** Reemplazado por `resource_path("assets/maps/okua_home_base.png")` de `control_okua.app_qt.resources`, que usa correctamente `sys._MEIPASS` tanto en one-file como en one-dir.

**Archivo:** `src/control_okua/app_qt/widgets/home_map_panel.py`
**Tests:** 8/8 tests de mapa pasan post-corrección.

### Decisión de formato — one-dir en lugar de one-file

**Motivo:** En PyInstaller one-file, el exe extrae todo a un dir temporal en cada arranque (`%TEMP%/_MEIxxxxx/`), lo que causa:

- Tiempo de arranque mayor (extracción en cada ejecución)
- Rutas temporales que cambian en cada run — puede interferir con el ícono en taskbar de Windows
- Más difícil de depurar assets faltantes

**Decisión: one-dir** (`COLLECT` en spec). La carpeta de distribución queda:

```text
Control OKÚA CKv2/
  Control OKÚA CKv2.exe   ← 2.6 MB (solo bootstrap)
  config.json              ← copiado manualmente desde config.dist.json
  _internal/               ← runtime PyInstaller (DLLs, pyc, assets)
    assets/
      maps/okua_home_base.png
      branding/okua_app_icon.ico
      theme.qss
    ...
```

**Ventajas:** arranque inmediato, assets inspeccionables, ícono resuelto desde ruta estable, fácil de actualizar parcialmente, sin extracción temporal.

**Spec actualizada:** `ControlOkuaV2.spec` — reemplazado one-file `EXE(a.binaries, a.datas)` por `EXE(exclude_binaries=True)` + `COLLECT()`.

### Config de distribución limpia — `config.dist.json`

**Problema:** `dist/config.json` contenía la config personal de José David (ports MIDI `"loopMIDI Port 1 1"`, remote_api `tailscale_only` en puerto 8802).

**Corrección:** Creado `config.dist.json` en la raíz del repo como plantilla de distribución limpia:

- `midi.outputs`: `"loopMIDI Port 1"` y `"loopMIDI Port 2"` (nombres estándar)
- `remote_api.enabled`: `false`
- `remote_api.exposure_mode`: `"local_only"`
- `remote_api.port`: `8788`
- Perfil: `udp_jardin`, modo `udp`

**Uso:** Copiar `config.dist.json` como `config.json` junto al exe antes de distribuir.

---

## Resumen de escenarios

| Escenario | Estado |
|-----------|--------|
| S1 — Build con spec oficial | **PASA** |
| S2 — Nombre del exe | **PASA** — `Control OKÚA CKv2.exe` |
| S3 — Icono embebido en spec | **PASA** — `assets/branding/okua_app_icon.ico` referenciado correctamente |
| S4 — Arranque sin crash (proceso vivo 7 s) | **PASA (programático)** |
| S5 — Verificación visual icono/título | **PASA — confirmado por José David (2026-04-19)** |
| S6 — Home y navegación mínima | **PASA — confirmado por José David (2026-04-19)** |
| S7 — Cierre limpio | **PASA — confirmado por José David (2026-04-19)** |

---

## Decisión final

**La ruta empaquetada `.exe` es VIABLE como alternativa de distribución — validación visual completa confirmada por José David (2026-04-19).**

Condiciones confirmadas:
1. El build es exitoso y reproducible con `pyinstaller ControlOkuaV2.spec --noconfirm`.
2. El exe arranca sin crash (confirmado programáticamente y visualmente).
3. La spec está correctamente configurada: nombre, icono, assets incluidos.
4. Para distribución limpia, copiar `config.dist.json` como `config.json` junto al exe.
5. Ícono OKÚA branding visible en barra de título y barra de tareas — confirmado visualmente.
6. Mapa Home, navegación a Nodos/Diagnóstico/Técnico y cierre limpio — todos confirmados.

**Esta ruta sigue siendo secundaria respecto a `python main.py`.** La ruta desde fuente es la principal para uso operativo. El exe es la alternativa validada para distribución sin entorno Python.
