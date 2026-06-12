# CKV2 Security Hardening 000I - 2026-06-11

## Scope

- Rama: `chore/000d-repo-guardrails`
- Commit inicial: `e1161d6`
- Ejecucion local: 2026-06-12
- PC de campo tocado: no
- Runtime ejecutado: no
- Build ejecutado: no
- Upload firmware ejecutado: no
- Push realizado: no
- Reportes crudos locales: `.security-reports/000I_20260612_091920/` (ignorado por Git)

## Raw scan exports

- `pip-audit.json`, `pip-audit.txt`: salida inicial antes de pins dev/security.
- `pip-audit-after.json`, `pip-audit-after.txt`: salida posterior a pins y actualizacion local en `.venv`.
- `bandit.json`, `bandit.txt`: salida detallada de `bandit -r src tools`.
- `pre-commit-all-files.txt`, `pre-commit-changed-files.txt`, `pre-commit-diff-stat.txt`: evidencia de normalizacion masiva rechazada.

## pip-audit triage

Resultado inicial: 14 vulnerabilidades en 7 paquetes. Resultado posterior a cambios seguros: 2 registros restantes, ambos de `starlette`.

| Package | Installed | Vulnerability ID | Fix versions | Runtime impact | Decision | Rationale |
|---|---:|---|---|---|---|---|
| idna | 3.11 | CVE-2026-45409 | 3.15 | Dev/security transitive via requests/anyio | FIX_NOW | Pin agregado en `requirements-security.txt`; `.venv` actualizado a version corregida. |
| pygments | 2.19.2 | CVE-2026-4539 | 2.20.0 | Dev/test/security formatting output | FIX_NOW | Pin agregado en `requirements-security.txt`; `.venv` actualizado. |
| pytest | 9.0.2 | CVE-2025-71176 | 9.0.3 | Dev/test only | DEV_ONLY | Pin agregado en `requirements-dev.txt`; no toca runtime principal. |
| requests | 2.32.5 | CVE-2026-25645 | 2.33.0 | Security tooling and PlatformIO local dependency | FIX_NOW | Pin agregado en `requirements-security.txt`; compatible con `pip check`. |
| setuptools | 65.5.0 | PYSEC-2022-43012 | 65.5.1 | Build/dev environment | FIX_NOW | Pin a version corregida en `requirements-security.txt`; no cambia `requirements.txt`. |
| setuptools | 65.5.0 | PYSEC-2025-49 | 78.1.1 | Build/dev environment | FIX_NOW | Pin a `setuptools>=78.1.1`; `.venv` actualizado. |
| setuptools | 65.5.0 | CVE-2024-6345 | 70.0.0 | Build/dev environment | FIX_NOW | Cubierto por `setuptools>=78.1.1`. |
| starlette | 0.52.1 | PYSEC-2026-161 | 1.0.1 | PlatformIO local dependency | ACCEPT_TEMPORARILY | Fix recomendado rompe `platformio 6.1.19` (`starlette<0.53`). Se revirtio `.venv` a `0.52.1` y `pip check` queda limpio. |
| urllib3 | 2.6.3 | PYSEC-2026-141 | 2.7.0 | Security tooling via requests | FIX_NOW | Pin agregado en `requirements-security.txt`; `.venv` actualizado. |
| urllib3 | 2.6.3 | PYSEC-2026-142 | 2.7.0 | Security tooling via requests | FIX_NOW | Cubierto por `urllib3>=2.7.0`. |

Notas:

- Los duplicados reportados por `pip-audit` para `setuptools`, `starlette` y `urllib3` se triagean por paquete/ID.
- `requirements.txt` no fue modificado.
- Se instalo/actualizo solo en `.venv`; no hubo instalacion global.
- `matplotlib` quedo instalado localmente al sincronizar `requirements-dev.txt`; sigue siendo dependencia de diagnostico, no runtime principal.

## Bandit triage

Resultado: 54 hallazgos, 0 altos, 21 medios, 33 bajos.

| ID | Severity | Confidence | File | Decision | Rationale |
|---|---|---|---|---|---|
| B104 | MEDIUM | MEDIUM | `src/control_okua/app_qt/ota_campaign_dialog.py` | NEEDS_REVIEW | Default UI para bind OTA; cambiarlo puede alterar flujo operacional. |
| B104 | MEDIUM | MEDIUM | `src/control_okua/app_qt/ota_deploy_dialog.py` | NEEDS_REVIEW | Default UI para bind OTA; requiere ticket de hardening OTA. |
| B104 | MEDIUM | MEDIUM | `src/control_okua/app_qt/viewmodels/main_window_vm.py` | ACCEPT_TEMPORARILY | Lectura/default de configuracion visible; no se cambia sin revisar flujo UDP. |
| B104 | MEDIUM | MEDIUM | `src/control_okua/core/config/config_schema.py` | NEEDS_REVIEW | Default UDP `0.0.0.0`; cambiarlo puede afectar nodos en campo. |
| B108 | MEDIUM | MEDIUM | `src/control_okua/core/firmware/artifact_agent_service.py` | NEEDS_REVIEW | Ruta temporal fija en servicio de artefactos; requiere cambio de diseno con pruebas. |
| B104 | MEDIUM | MEDIUM | `src/control_okua/core/firmware/ota_campaign_models.py` | NEEDS_REVIEW | Default de servidor OTA; no cambiar sin validar hardware/red. |
| B104 | MEDIUM | MEDIUM | `src/control_okua/core/firmware/ota_deploy_models.py` | NEEDS_REVIEW | Default de servidor OTA; no cambiar sin validar hardware/red. |
| B104 | MEDIUM | MEDIUM | `src/control_okua/core/firmware/ota_manifest_models.py` | FALSE_POSITIVE | El codigo valida/rechaza host no publicable; no abre socket. |
| B104 | MEDIUM | MEDIUM | `src/control_okua/services/ack_listener.py` | NEEDS_REVIEW | Listener ACK; cambiar bind puede romper operacion UDP. |
| B104 | MEDIUM | MEDIUM | `src/control_okua/services/ack_listener.py` | FALSE_POSITIVE | Fallback de direccion local, no bind real. |
| B104 | MEDIUM | MEDIUM | `src/control_okua/services/ota_campaign_service.py` | NEEDS_REVIEW | Fallback OTA; requiere ticket especifico. |
| B104 | MEDIUM | MEDIUM | `src/control_okua/services/ota_server_service.py` | NEEDS_REVIEW | Bind del servidor OTA; no se cambia sin validacion operacional. |
| B104 | MEDIUM | MEDIUM | `src/control_okua/services/ota_server_service.py` | FALSE_POSITIVE | Rama de mensaje de error; no abre socket por si sola. |
| B104 | MEDIUM | MEDIUM | `src/control_okua/services/remote_api_bootstrap.py` | FALSE_POSITIVE | Construccion de URL local cuando bind es amplio; no cambia bind. |
| B104 | MEDIUM | MEDIUM | `src/control_okua/services/remote_api_bootstrap.py` | NEEDS_REVIEW | Normalizacion de exposicion remota; requiere revision de seguridad remota. |
| B104 | MEDIUM | MEDIUM | `src/control_okua/transports/udp/udp_models.py` | NEEDS_REVIEW | Defaults UDP repetidos; cambio requiere compatibilidad de nodos. |
| B104 | MEDIUM | MEDIUM | `src/control_okua/transports/udp/udp_models.py` | NEEDS_REVIEW | Defaults UDP repetidos; cambio requiere compatibilidad de nodos. |
| B104 | MEDIUM | MEDIUM | `src/control_okua/transports/udp/udp_models.py` | NEEDS_REVIEW | Defaults UDP repetidos; cambio requiere compatibilidad de nodos. |
| B104 | MEDIUM | MEDIUM | `src/control_okua/transports/udp/udp_transport.py` | FALSE_POSITIVE | Fallback para direccion de socket, no configuracion de exposicion. |
| B104 | MEDIUM | MEDIUM | `tools/firmware_f3_validator.py` | ACCEPT_TEMPORARILY | Herramienta de diagnostico; no se ejecuta en este ticket. |
| B104 | MEDIUM | MEDIUM | `tools/fruit_diag_listener.py` | ACCEPT_TEMPORARILY | Herramienta auxiliar live/fruit; default amplio se revisara aparte. |
| B101 | LOW | HIGH | grouped: `src/...recording`, `tools/live_diagnostics_panel.py` | ACCEPT_TEMPORARILY | `assert` en runtime/tools requiere cambio pequeno pero no bloquea push humano; evitar ediciones funcionales en 000I. |
| B105 | LOW | MEDIUM | `src/control_okua/core/config/config_schema.py` | FALSE_POSITIVE | Nombre de variable de entorno, no secreto embebido. |
| B106 | LOW | MEDIUM | `src/control_okua/services/remote_api_auth.py` | FALSE_POSITIVE | Etiqueta `legacy-admin`, no password real. |
| B110 | LOW | HIGH | grouped: runtime transports/services | NEEDS_REVIEW | `try/except/pass` repetido; cambiar manejo de errores puede alterar tolerancia operacional. |
| B404/B603/B607 | LOW | HIGH | grouped: artifact agent and remote API bootstrap | NEEDS_REVIEW | Uso de `subprocess` sin `shell=True`; revisar allowlist/rutas absolutas en ticket dedicado. |

No se agregaron `# nosec` masivos y no se cambio logica de red, autenticacion, MIDI, firmware ni control remoto.

## pre-commit

- `pre-commit run --all-files` exit code: 1.
- Hooks no mutadores relevantes pasaron: `check-yaml`, `check-json`, `check-added-large-files`, `detect-private-key`.
- Hooks mutadores tocaron 30 archivos historicos (`trailing-whitespace`, `end-of-file-fixer`), incluyendo docs, GUI, firmware, runtime y tests.
- Cambios automaticos revertidos por alcance de 000I.
- Decision: postergar a `CKV2-000J - Normalizacion controlada de whitespace/EOL`.

## Changes applied

- `.gitignore`: agrega `.security-reports/` para impedir versionar reportes crudos.
- `requirements-dev.txt`: `pytest>=9.0.3`.
- `requirements-security.txt`: pins minimos para tooling y transitivos corregidos (`idna`, `pygments`, `requests`, `setuptools`, `urllib3`).
- `.venv`: actualizado localmente; `starlette` fue revertido a `0.52.1` por compatibilidad con PlatformIO.

## Accepted temporary risks

- `starlette 0.52.1` conserva `PYSEC-2026-161` porque el fix disponible requiere `>=1.0.1` y rompe la restriccion de PlatformIO 6.1.19.
- Bandit medios asociados a `0.0.0.0` quedan documentados para hardening de red/OTA/UDP.
- Bandit bajos de excepciones silenciosas, asserts y subprocess quedan para revision focalizada.
- `pre-commit --all-files` no es gate verde hasta normalizacion separada.
- `gitleaks` sigue no disponible localmente.

## Validation summary

- `pip check`: sin conflictos tras revertir `starlette` a rango compatible.
- `pip-audit after`: 2 registros restantes en 1 paquete (`starlette`).
- `bandit`: sin hallazgos altos.
- `pre-commit`: no aceptado por normalizacion masiva.
- `git diff --check`: pasa.
- Validacion nativa de patrones sensibles: solo rutas/lineas; hallazgos amplios corresponden a nombres de variables, fixtures, documentacion y politicas de exclusion ya conocidas. No se imprimieron valores.
- Sintaxis Python sin cache: `syntax ok: 207 python files`.

## Push readiness decision

Decision: READY_FOR_HUMAN_REVIEW

### Conditions before push

- Confirmar revision humana del riesgo `starlette`/PlatformIO.
- Aceptar que no hay Bandit alto, pero quedan medios de red/OTA/UDP para ticket posterior.
- Aceptar que `pre-commit --all-files` requiere `CKV2-000J`.
- Ejecutar `gitleaks` externamente o aceptar su ausencia local.
- Confirmar working tree limpio y sin secretos directos antes del push.

Rama lista para push humano: si, condicionada a aprobacion humana explicita de los riesgos aceptados temporalmente.
