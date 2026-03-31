# PARÉNTESIS OPERATIVO OTA-A — Protocolo de creación de artifacts OTA

## 1. Propósito

Este documento fija el protocolo operativo para crear artifacts OTA de forma consistente en CKv2 durante el paréntesis `OTA-A`.

Objetivos:

- evitar bins improvisados,
- evitar nombres/versiones ambiguas,
- congelar la regla de `situational` para firmwares de prueba,
- y dejar una base reusable por repo y por la app exportada.

## 2. Regla obligatoria de status

Durante `OTA-A`, todo firmware generado con intención de:

- prueba,
- comparación,
- experimento,
- validación puntual,
- clon del baseline actual,

debe clasificarse como `situational`.

Esto incluye:

- el artifact de `planta prueba actual`,
- el artifact `fruta prueba` comparativo,
- cualquier clon intermedio usado para validar el pipeline OTA.

No se debe usar `current`, `beta` u `obsolete` para estos bins de prueba salvo que exista una decisión operacional explícita posterior fuera de este paréntesis.

## 3. Auditoría cerrada del repo actual

### 3.1 Cómo se construye hoy el firmware

- Entorno por defecto: `okua_node_esp32dev`
- Fuente principal: `firmware/okua_node_udp_v1/okua_node_udp_v1.ino`
- Identidad embebida:
  - `FW_VERSION_STR`
  - `FW_VERSION_CODE`
  - `FW_TARGET_KIND`
  - `FW_TARGET_VARIANT`
  - `FW_BUILD_PROFILE`
  - `FW_PROTOCOL_VERSION`
  - `FW_ARTIFACT_ID`
  - `FW_ARTIFACT_SHA256`

### 3.2 Qué representa “planta prueba actual”

En el repo actual, `planta prueba actual` no es un único bin compartido.

Razón:

- `kOkuaBuildInfoConfig` usa `NODE_LABEL` como `target_variant`.
- `NODE_LABEL` y `NODE_ID` forman parte de la identidad compile-time.

Consecuencia:

- `EB1`, `EC1` y `ED1` requieren artifacts distintos.
- Aunque el perfil funcional sea el mismo (`MODE_TEST + SENSOR_PLANT`), la identidad OTA queda separada por nodo.

### 3.3 Qué representa “fruta prueba”

En el repo actual, un build de fruta:

- cambia `ACTIVE_SENSOR` a `SENSOR_FRUIT`,
- cambia `target_kind` a `fruit`,
- y por lo tanto queda como artifact distinto y comparativo.

Advertencia importante:

- un artifact `fruit` no es OTA-compatible sobre un baseline actual `plant`,
- porque el firmware valida `target_kind` y `target_variant` del manifest contra el build que está corriendo.

Por eso, el artifact `fruta prueba` de `OTA-A` es útil para:

- comparación de comportamiento,
- validación visible de cambio,
- y preparación de artifacts futuros,

pero no debe asumirse como desplegable por OTA sobre los nodos baseline `plant` actuales sin una estrategia adicional.

## 4. Política de decisión por artifact

### 4.1 Clon del actual

Úsalo cuando quieras:

- representar formalmente lo que ya está cargado en el nodo,
- catalogarlo sin cambiar intención funcional,
- o validar pipeline OTA sin introducir un cambio funcional deliberado.

Reglas:

- `intent = current_clone`
- `status = situational`
- `version =` la misma del baseline auditado
- `target_kind =` el mismo del baseline
- `target_variant =` el `NODE_LABEL` del nodo

### 4.2 Artifact comparativo

Úsalo cuando quieras:

- notar un cambio real,
- comparar comportamiento,
- o validar que la subida cambió efectivamente el binario.

Reglas:

- `intent = comparative`
- `status = situational`
- `version =` mayor al baseline cuando el objetivo sea compararlo como build nuevo
- `target_kind =` el del comportamiento comparativo real
- `target_variant =` concreto y no ambiguo

## 5. Reglas de naming y metadata

### 5.1 display_name

Debe dejar claro:

- familia de firmware,
- nodo o variante,
- intención,
- y si es baseline o comparativo.

Ejemplos:

- `OKUA Node UDP v1 - EB1 planta prueba actual (1.0.0-dev)`
- `OKUA Node UDP v1 - ED1 fruta prueba comparativa (1.0.1-dev)`

### 5.2 version

Debe mantenerse en semver compatible con OTA:

- `MAJOR.MINOR.PATCH`
- o `MAJOR.MINOR.PATCH-sufijo`

Ejemplos válidos:

- `1.0.0-dev`
- `1.0.1-dev`

### 5.3 version_label

Etiqueta humana corta y legible.

Ejemplos:

- `v1.0.0 baseline situational`
- `v1.0.1 comparativo situational`

### 5.4 target_kind

Debe reflejar el comportamiento real del build:

- `plant`
- `fruit`

### 5.5 target_variant

Debe ser explícito y estable.

En el repo actual, para `OTA-A`:

- `eb1`
- `ec1`
- `ed1`

No usar `generic` cuando el build es realmente node-specific.

### 5.6 changelog_short y notes

`changelog_short`:

- una línea que explique por qué existe el artifact.

`notes`:

- contexto operativo, limitaciones o advertencias de despliegue.

## 6. Agente reutilizable

La lógica reusable quedó en:

- `src/control_okua/core/firmware/artifact_agent_service.py`

Responsabilidades:

- auditar el baseline actual del repo,
- decidir defaults para `display_name`, `version`, `version_label`,
- forzar `situational` para tests/comparativos,
- construir planes reproducibles,
- generar headers de override para build,
- compilar/exportar bins,
- y dejar metadata lista para importación.

El entrypoint operativo quedó en:

- `tools/firmware_artifact_agent.py`

## 7. Uso operativo recomendado

### 7.1 Auditar el baseline actual

```powershell
python tools/firmware_artifact_agent.py audit --pretty
```

### 7.2 Generar el set situational estándar

```powershell
python tools/firmware_artifact_agent.py build-situational --pretty
```

Eso genera por defecto:

- `EB1` planta prueba actual
- `EC1` planta prueba actual
- `ED1` planta prueba actual
- `ED1` fruta prueba comparativa

### 7.3 Generar e importar localmente

```powershell
python tools/firmware_artifact_agent.py build-situational --import-generated --pretty
```

Esto:

- exporta los `.bin`,
- escribe sidecars `artifact_plan.json`,
- e importa localmente los artifacts al catálogo/managed store.

## 8. Layout de salida esperado

Por defecto los outputs quedan en:

- `artifacts/ota_artifact_agent/<lote>/...`

Cada artifact exportado deja:

- `*.bin`
- `artifact_build_overrides.h`
- `artifact_plan.json`

## 9. Qué no hacer

- No etiquetar como `current` un build de prueba.
- No usar `generic` si el build es por nodo.
- No publicar un artifact `fruit` como si fuera compatible OTA con baseline `plant`.
- No reutilizar el mismo `display_name` para bins distintos.
- No usar `version` no semver.
- No depender de `.pio/build/.../firmware.bin` como biblioteca histórica; ese archivo se sobreescribe.

## 10. Resultado operativo esperado de OTA-A

Al terminar este paréntesis deben existir:

- un protocolo formal,
- un servicio reusable,
- un CLI operativo,
- y los primeros artifacts situational exportados con metadata consistente.
