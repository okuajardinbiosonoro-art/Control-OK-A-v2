# Ensayo post-promoción desde `rc1-interna` — Control OKÚA CKv2

Rama/tag fuente: `rc1-interna` → commit `6a16c33`  
Fecha: 2026-04-19 (Ticket 39.1)  
Clasificación: **PASA completamente**

---

## Bloque 1 — Preparación del ensayo

| Ítem | Valor |
|------|-------|
| Fuente del ensayo | Tag `rc1-interna` (commit `6a16c33`) |
| Método de checkout | `git worktree add --detach C:/Temp/okua_rc1_39_1 rc1-interna` |
| Máquina | <DEV_PC> (Windows 11 Home, 10.0.26200) |
| Python | 3.11.0 (entorno existente — venv ya instalado) |
| Directorio del ensayo | `C:/Temp/okua_rc1_39_1` (worktree limpio, sin `config.json` previo) |
| Diferencias respecto a `desarrollo-fase-2` | Ninguna en código — `rc1-interna` y `desarrollo-fase-2` HEAD coincidían en `6a16c33` |

---

## Bloque 2 — Verificaciones automáticas desde el tag

### Compilación

```
python -m compileall src main.py -q
```

**Resultado:** Sin errores — `COMPILEALL_OK`

### Suite de tests

```
PYTHONPATH=src python -m pytest --tb=short -q
```

**Resultado: 498 passed in 142.57s** — 0 fallos

---

## Bloque 3 — Arranque desde estado limpio (primer arranque real)

Comando ejecutado:
```
CKV2_AUTOPROFILE=udp_jardin PYTHONPATH=src python main.py
```

Mensajes de arranque observados:
```
[config] config no existia; se creo v2 en 'C:\Temp\okua_rc1_39_1\config.json'.
[config] profile.active actualizado a 'udp_jardin' desde selector guiado.
[remote_api] deshabilitado: remote_api.enabled=false en config.
```

**Evaluación:**

| Mensaje | Evaluación |
|---------|-----------|
| `config no existia; se creo v2` | **Correcto** — primer arranque en directorio limpio sin `config.json` previo |
| `profile.active actualizado a 'udp_jardin' desde selector guiado` | **Correcto** — `CKV2_AUTOPROFILE` resuelve el perfil de forma no interactiva |
| `remote_api deshabilitado` | **Correcto y mejor que en dev** — config nueva crea `remote_api.enabled: false` por defecto; sin warnings de Tailscale |

> El arranque desde cero es **más limpio que desde el entorno de desarrollo**: no aparecen los avisos de `tailscale_only` porque el `config.json` generado desde cero tiene `remote_api.enabled: false`.

### Estabilidad del proceso

| Comprobación | Resultado |
|-------------|-----------|
| Proceso vivo a los 12 s | **CONFIRMADO** |
| Proceso vivo a los 30 s | **CONFIRMADO** |
| Crash inmediato | NO |
| Terminación limpia | **CONFIRMADO** — exit code 143 (SIGTERM normal) |

---

## Bloque 4 — Bug encontrado y corregido (README desactualizado)

### Discrepancia en README — ruta del exe

**Hallazgo:** `README.md` documentaba la ruta del ejecutable empaquetado como `dist/Control OKUA CKv2.exe` (formato one-file, sin tilde, sin directorio). Desde el ticket 36.2 el spec usa one-dir y el artefacto real es `dist/Control OKÚA CKv2/Control OKÚA CKv2.exe`.

**Impacto:** Un usuario nuevo leyendo el README buscaría el exe en la ruta incorrecta.

**Corrección:** Actualizada la sección "Build con PyInstaller" del `README.md`:
```
El ejecutable queda en `dist/Control OKÚA CKv2/Control OKÚA CKv2.exe` (formato one-dir).
Copiar `config.dist.json` como `config.json` junto al exe antes de distribuir.
```

**Archivo:** `README.md`  
**Sin cambios de código** — solo documentación.

---

## Bloque 5 — Decisión de consumibilidad

**`main` / `rc1-interna` son consumibles desde cero.**

Evidencias:
1. Worktree limpio desde tag `rc1-interna` — sin `config.json` previo.
2. `compileall` limpio — sin errores de compilación.
3. **498/498 tests PASAN** desde el estado del tag.
4. Primer arranque real: `config.json` creado automáticamente, perfil resuelto vía `CKV2_AUTOPROFILE`, remote_api silencioso por defecto.
5. Proceso estable 30 s sin crash.
6. Terminación limpia.

El único ajuste necesario fue la corrección menor del README (ruta del exe).

---

## Bloque 6 — Cierre de la familia 39.x

**La familia 39.x queda cerrada.**

| Ticket | Resultado |
|--------|-----------|
| 39.0 | Promoción fast-forward a `main` ejecutada; tag `rc1-interna` publicado |
| 39.1 | Ensayo desde tag confirmado consumible; README corregido |

`main` y el tag `rc1-interna` representan el estado definitivo, consumible y documentado de la Release Interna Controlada RC1 de Control OKÚA CKv2.

---

## Rollback de la promoción (si fuera necesario)

```bash
# Revertir main al commit anterior a 39.0
git push origin 7fe065d:main --force-with-lease

# Eliminar el tag si también debe revertirse
git push origin :rc1-interna
git tag -d rc1-interna
```

`desarrollo-fase-2` no se ve afectada por ninguna de estas operaciones.
