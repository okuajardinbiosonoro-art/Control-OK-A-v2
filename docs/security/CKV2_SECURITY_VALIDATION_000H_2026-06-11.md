# CKV2 Security Validation 000H - 2026-06-11

## Scope
- Rama: `chore/000d-repo-guardrails`
- Commit inicial: `1640ad1`
- Commit de sanitizacion: `e2fddca`
- PC de campo tocado: no
- Runtime ejecutado: no
- Build ejecutado: no
- Upload firmware ejecutado: no
- Push realizado: no

## Sanitization
- Patrones buscados: rutas Windows de usuario, nombres de equipo, nombres de usuario, IPs Tailscale-like, IPs privadas documentales, `remote_api_*`, `CKV2_CONTROL_SECRET`, `password`, `token`, `secret`, `ssid`, `wifi`, `clave`, `contraseña`.
- Archivos revisados: todos los archivos versionados mediante `git ls-files`.
- Cambios aplicados:
  - Rutas absolutas de `.vscode` reemplazadas por `${workspaceFolder}` y `${env:USERPROFILE}`.
  - Rutas locales historicas de documentacion reemplazadas por `<CKV2_REPO_LOCAL>` y `<USER_HOME>`.
  - Nombres de usuario/equipo historicos reemplazados por placeholders como `<USER_NAME>`, `<DEV_PC>` y `<FIELD_PC>`.
  - IPs Tailscale-like historicas reemplazadas por rangos documentales.
  - IPs privadas documentales en `docs/` reemplazadas por rangos reservados para documentacion.
  - Fixtures de tests con IPs Tailscale-like reemplazadas por rangos documentales.
- Hallazgos dejados como aceptables:
  - Referencias a OneDrive como riesgo operativo documentado.
  - Nombres de archivos `remote_api_users.json`, `remote_api_tokens.json` y `control_plane_state.json` como politica de exclusion, no como datos reales.
  - Identificadores de entorno como `CKV2_CONTROL_SECRET` sin valor asociado.
  - Campos de modelo o tests como `password_hash`, `token`, `secret` y bearer tokens ficticios.
  - IPs privadas que permanecen solo como fixtures de tests.
- Falsos positivos:
  - `pyrightconfig.json` aparecio por patron amplio `config.json`; no es config real de runtime.
  - Bearer tokens en tests son fixtures, no credenciales reales.
  - El reporte 000G contenia un marcador textual de clave privada; fue reformulado para evitar falso positivo de `detect-private-key`.

## Tools
- `bandit`: instalado localmente en `.venv`, version 1.9.4, ejecutado con `python -m bandit -r src tools -q`.
- `pip-audit`: instalado localmente en `.venv`, version 2.10.1; requirio `PYTHONUTF8=1` por ruta local con caracteres no ASCII.
- `pre-commit`: instalado localmente en `.venv`, version 4.6.0; configuracion minima creada.
- `gitleaks`: no disponible localmente; no se instalo globalmente.

## Results
- Secretos directos: no se detectaron en rutas versionadas ni en lineas agregadas del staged diff.
- Rutas privadas: las referencias directas a rutas de perfil Windows quedaron en cero dentro del arbol versionado.
- IPs privadas/Tailscale: las IPs Tailscale-like quedaron en cero; las IPs privadas documentales en `docs/` quedaron en cero; quedan fixtures de tests aceptables.
- Binarios/logs/configs reales: no se detectaron `dist/`, `build/`, `.exe`, `.dll`, `.pyd`, `.bin`, `.elf`, `.map`, logs, configs reales ni secretos de firmware versionados. `pyrightconfig.json` es falso positivo por nombre.
- Python syntax: `syntax ok: 207 python files`.
- Vulnerabilidades de dependencias:
  - `idna` 3.11: `CVE-2026-45409`, fix sugerido 3.15.
  - `pygments` 2.19.2: `CVE-2026-4539`, fix sugerido 2.20.0.
  - `pytest` 9.0.2: `CVE-2025-71176`, fix sugerido 9.0.3.
  - `requests` 2.32.5: `CVE-2026-25645`, fix sugerido 2.33.0.
  - `setuptools` 65.5.0: `PYSEC-2022-43012`, `PYSEC-2025-49`, `CVE-2024-6345`; fixes sugeridos 65.5.1, 70.0.0 o 78.1.1 segun ID.
  - `starlette` 0.52.1: `PYSEC-2026-161`, fix sugerido 1.0.1.
  - `urllib3` 2.6.3: `PYSEC-2026-142`, `PYSEC-2026-141`, fix sugerido 2.7.0.
  - `pip-audit` reporto 14 vulnerabilidades conocidas en 7 paquetes; severidad no fue informada por la salida nativa.
- Hallazgos Bandit:
  - 0 altos, 21 medios, 33 bajos.
  - Principales categorias: bind a `0.0.0.0`, `try/except/pass`, uso de `assert`, uso de `subprocess`, ruta temporal fija y falsos positivos sobre etiquetas/token env vars.
  - No se modifico codigo para silenciar hallazgos en este ticket.
- Hallazgos pre-commit:
  - `check-yaml` y `check-added-large-files` pasaron.
  - `trailing-whitespace` y `end-of-file-fixer` intentaron modificar muchos archivos historicos; los cambios automaticos fueron revertidos y no se commitearon.
  - `check-json` fallo sobre JSONC/archivos `.vscode`; se configuro exclusion para `.vscode/`.
  - `detect-private-key` marco un falso positivo en el reporte 000G; el marcador textual fue reformulado.

## Open Risks
- Riesgos pendientes:
  - `pip-audit` detecto vulnerabilidades en dependencias del entorno local.
  - `bandit` detecto hallazgos medios relacionados con bind a todas las interfaces y otros hallazgos bajos.
  - `pre-commit run --all-files` aun no queda verde por deuda historica de whitespace/EOL si se ejecutan hooks mutadores sobre todo el repo.
  - `gitleaks` sigue pendiente de ejecucion externa o instalacion controlada posterior.
- Acciones recomendadas antes de push:
  - Revision humana del diff 000H.
  - Decidir si el push acepta riesgos documentados o si se abre ticket previo para dependencias y Bandit.
  - Ejecutar gitleaks en entorno controlado si se requiere bloqueo fuerte antes del remoto.
- Acciones recomendadas despues de push:
  - Ticket de hardening para `0.0.0.0`, `subprocess` y manejo de excepciones.
  - Ticket de actualizacion de dependencias con pruebas.
  - Ticket separado para normalizar whitespace/EOL si se desea activar `pre-commit run --all-files` como gate estricto.

## Decision
- Rama lista para revision humana: si.
- Rama lista para push: no como gate automatico estricto; si solo bajo aprobacion humana explicita aceptando los riesgos documentados.
- Condiciones: revisar vulnerabilidades de dependencias, hallazgos Bandit y ausencia de gitleaks antes del push remoto final.
