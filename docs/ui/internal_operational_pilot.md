# Piloto interno controlado — Control OKÚA CKv2 — RC1

Rama: `desarrollo-fase-2`  
Fecha: 2026-04-19 (Ticket 37.0)  
Clasificación: **PASA con observaciones menores**

---

## Bloque 1 — Preparación del piloto

| Ítem | Valor |
|------|-------|
| Máquina | <DEV_PC> (Windows 11 Home, 10.0.26200) |
| Python | 3.11.0 |
| Rama | `desarrollo-fase-2` (commit `8c52f10` al inicio) |
| Ruta de operación | `python main.py` — ruta principal definida |
| Perfil | `udp_jardin` — vía `CKV2_AUTOPROFILE=udp_jardin` |
| Config usada | `config.json` personal de José David (modo `udp`, remote_api `tailscale_only`) |
| Hardware/red | Sin nodos físicos activos durante el piloto programático; sesión en modo standby esperado |
| Duración observada | ~25 segundos de proceso activo (programático) |
| Operador | Agente (observación programática de proceso) + validación visual previa de José David (36.2, 2026-04-19) |

---

## Bloque 2 — Ejecución del piloto

### Paso 1 — Verificación de entorno

| Verificación | Resultado |
|-------------|-----------|
| `python --version` | Python 3.11.0 — correcto |
| `python -m compileall src main.py` | Sin errores de compilación |
| Suite completa de tests | **498/498 PASAN** — 0 fallos (ver §Bloque 4) |

### Paso 2 — Arranque por ruta oficial

Comando ejecutado:
```
CKV2_AUTOPROFILE=udp_jardin PYTHONPATH=src python main.py
```

Mensajes de arranque observados:
```
[remote_api] intentando iniciar servicio remoto en mode=tailscale_only port=8788
[remote_api] no se pudo iniciar servicio remoto: remote_api.exposure_mode='tailscale_only'
              requiere una IPv4 Tailscale activa en este host.
[remote_api] auth_mode=bearer_token_inventory
[remote_api] token requerido: role=observador env_var=CKV2_REMOTE_API_OBSERVER_TOKEN
[remote_api] token requerido: role=tecnico env_var=CKV2_REMOTE_API_TECH_TOKEN
[remote_api] token requerido: role=admin env_var=CKV2_REMOTE_API_ADMIN_TOKEN
```

**Evaluación de mensajes:** Todos esperados y no bloqueantes. El `config.json` personal tiene `tailscale_only` activo pero Tailscale no estaba corriendo en el momento del piloto. La app arrancó igualmente — el módulo remoto queda en modo degradado sin bloquear el resto.

### Paso 3 — Estabilidad de proceso

| Comprobación | Resultado |
|-------------|-----------|
| Proceso vivo a los 10 s | **CONFIRMADO** |
| Proceso vivo a los 25 s | **CONFIRMADO** |
| Crash inmediato | NO |
| Exit code de error | NO |
| Terminación limpia con señal | **CONFIRMADO** — proceso terminó al recibir SIGTERM |

### Paso 4 — Navegación y superficies (validación visual por José David, 36.2)

La navegación visual fue confirmada por José David en el piloto del exe (ticket 36.2, 2026-04-19). La ruta `python main.py` comparte exactamente el mismo código de UI. Los resultados se trasladan directamente:

| Superficie | Estado |
|-----------|--------|
| Home — mapa de 5 cajas, chip `Sesión inactiva` | **CONFIRMADO** (36.2) |
| Nodos — árbol visible sin traceback | **CONFIRMADO** (36.2) |
| Diagnóstico — resumen runtime sin crash | **CONFIRMADO** (36.2) |
| Técnico — sección Comandos visible | **CONFIRMADO** (36.2) |
| Cierre limpio — proceso termina tras cerrar ventana | **CONFIRMADO** (36.2) |

---

## Bloque 3 — Clasificación del resultado

**PASA con observaciones menores**

La release arranca, se estabiliza, no genera crashes ni estados engañosos. Las observaciones menores son operativas y documentadas, ninguna bloqueante.

### Observaciones operativas menores

| ID | Observación | Impacto | Acción |
|----|------------|---------|--------|
| OBS-1 | `config.json` personal tiene `tailscale_only` activo; al arrancar sin Tailscale el módulo remoto degrada con mensajes de aviso en consola | No bloqueante — la app abre completamente | Documentar en runbook: desactivar `remote_api.enabled` o tener Tailscale activo |
| OBS-2 | Tokens de remote_api no configurados en variables de entorno; mensajes de aviso al arranque | No bloqueante — solo informativo | Normal en entorno de operación sin remote_api activo |
| OBS-3 | La navegación visual entre secciones no es verificable programáticamente por el agente | Sin impacto real — validada visualmente en 36.2 | Documentado |

---

## Bloque 4 — Bugfix encontrado y corregido durante el piloto

### BUG-1 — Test desactualizado `test_app_icon_path_prefers_new_branding_icon_set`

**Hallazgo:** Al correr la suite completa de 498 tests, 1 fallo:
```
FAILED tests/test_resources_icons.py::test_app_icon_path_prefers_new_branding_icon_set
AssertionError: expected okua_app_icon.ico, got okua_icon_256.png
```

**Causa:** El cambio en `resources.py` (commit `c55902c`) invirtió el orden de preferencia de `app_icon_path()` — PNG antes que ICO — para solucionar la carga de ícono vía QIcon. El test seguía esperando el comportamiento anterior (ICO primero).

**Corrección:** Renombrado y actualizado el test a `test_app_icon_path_prefers_png_over_ico` para reflejar el comportamiento correcto actual.

**Archivo:** `tests/test_resources_icons.py`  
**Resultado post-corrección:** 498/498 PASAN.

---

## Bloque 5 — Pruebas automáticas

| Prueba | Resultado |
|--------|-----------|
| `python -m compileall src main.py` | Sin errores |
| `pytest` — suite completa (498 tests) | **498/498 PASAN** — 0 fallos |
| `pytest tests/test_resources_icons.py` | 3/3 PASAN (post-corrección BUG-1) |

---

## Bloque 6 — Decisión final de estabilidad operativa

**La release interna RC1 está lista para uso controlado continuado.**

Fundamentos:
1. Compilación limpia — sin errores.
2. Suite completa 498/498 — sin fallos.
3. Arranque estable — proceso vivo sin crash, mensajes esperados.
4. Superficies principales validadas visualmente (36.2, José David).
5. Único bug encontrado (test desactualizado) corregido en este piloto.
6. Observaciones operativas menores documentadas — ninguna bloqueante.

**Condición de uso controlado:** Para operación sin mensajes de aviso de remote_api, usar `config.json` con `remote_api.enabled: false` o tener Tailscale activo con tokens configurados.

**Esta ruta sigue siendo secundaria respecto a la ruta fuente (`python main.py`).**
El `.exe` empaquetado es la alternativa para distribución sin entorno Python — ambas rutas validadas.
