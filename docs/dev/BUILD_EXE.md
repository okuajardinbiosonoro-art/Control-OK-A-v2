# Build del Ejecutable CKv2

## Proceso previsto

El empaquetado de CKv2 para Windows se realiza con PyInstaller usando el spec principal:

```powershell
pyinstaller ControlOkuaV2.spec
```

Tambien existe evidencia historica de uso con:

```powershell
pyinstaller ControlOkuaV2.spec --noconfirm
```

No ejecutar estos comandos como parte de tareas documentales o auditorias pasivas.

## Rol de PyInstaller

PyInstaller agrupa la aplicacion Python, dependencias Qt/PySide6, dependencias MIDI y assets necesarios para ejecutar CKv2 sin invocar `python main.py`.

Dependencias relevantes:

- `PySide6`
- `pyserial`
- `mido`
- `python-rtmidi`
- `pyinstaller`

## Rol de `ControlOkuaV2.spec`

`ControlOkuaV2.spec` define:

- entrypoint `main.py`;
- `pathex` hacia `src`;
- assets empaquetados desde `assets/`;
- portal remoto desde `src/control_okua/services/remote_console_assets`;
- hidden imports para `rtmidi` y `mido.backends.rtmidi`;
- nombre del ejecutable `Control OKÚA CKv2`;
- icono de branding;
- formato one-dir mediante `COLLECT`.

## One-dir vs one-file

| Tipo | Forma | Uso |
| --- | --- | --- |
| one-dir | Carpeta `dist/Control OKÚA CKv2/` con exe pequeno y `_internal/` | Baseline de campo observado. |
| one-file | Un solo `.exe` grande en `dist/` | Artefacto alternativo/anterior; no baseline de campo. |

El baseline de campo coincide con el one-dir, no con el one-file grande.

## UPX

La auditoria de desarrollo encontro un cambio local en `ControlOkuaV2.spec`: `upx=True` a `upx=False`.

Motivo documentado: UPX puede disparar heuristicas antivirus en apps PyInstaller sin firma.

Decision pendiente: formalizar si `upx=False` sera politica oficial de packaging. Hasta entonces, no asumir reproducibilidad exacta entre builds.

## Configuracion real

Nunca empaquetar ni distribuir configuracion real de campo:

- `config.json`
- `remote_api_users.json`
- `remote_api_tokens.json`
- `remote_api_access.txt`
- `control_plane_state.json`
- logs de Remote API
- secretos en `.bat`, `.ps1`, `.cmd` o headers locales
- backups de `okua_node_secrets.h`

Usar plantillas limpias (`config.example.json` o `config.dist.json`) y configurar cada equipo destino de forma controlada.

## Pasos minimos de verificacion

Antes de declarar un build como candidato:

1. Trabajar desde un repo o worktree limpio.
2. Verificar `git status --short --untracked-files=all`.
3. Confirmar Python y PyInstaller usados.
4. Confirmar que `ControlOkuaV2.spec` es el spec principal.
5. Construir sin incluir configs reales.
6. Calcular SHA256 del ejecutable resultante.
7. Inventariar assets empaquetados.
8. Probar arranque en entorno controlado sin hardware real, salvo ticket explicito.
9. Documentar diferencias de hash frente al baseline.
10. Preparar rollback antes de tocar campo.

## Decision pendiente de reproducibilidad

El hash de campo esta identificado y coincide con el one-dir existente en desarrollo. Aun falta demostrar que un worktree limpio, con dependencias declaradas, produce un artefacto equivalente o aceptablemente nuevo.

Hasta cerrar esa brecha, el build de campo es un baseline observado, no una receta reproducible certificada.
