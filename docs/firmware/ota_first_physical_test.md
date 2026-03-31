# PARÉNTESIS OPERATIVO OTA-B — Primer ensayo OTA físico real

## 1. Nodo físico recomendado

Para el primer ensayo OTA físico se recomienda usar `ED1`.

Razones:

- el override local de banco quedó apuntando a `ED1`,
- `ED1` ya fue reflasheado y validado como baseline OTA-capable,
- el catálogo local ya contiene el baseline `plant/ed1`,
- y el comparativo `fruit/ed1` previo permite contrastar claramente qué artifact no usar para la primera OTA física.

## 2. Artifact baseline correcto

Usar como baseline de la prueba:

- `display_name`: `OKUA Node UDP v1 - ED1 planta prueba actual (1.0.0-dev)`
- `version`: `1.0.0-dev`
- `target_kind`: `plant`
- `target_variant`: `ed1`
- `status`: `situational`

Artifact local actual:

- `artifact_id`: `sha256:290321bb88c052540871d690c97deb0ff7e051845e33fef1d3079d4655fbc385`
- `file_path`: `artifacts/firmware_store/290321bb88c052540871d690c97deb0ff7e051845e33fef1d3079d4655fbc385.bin`

## 3. Artifact comparativo OTA-compatible correcto

El primer comparativo OTA físico debe mantener:

- `target_kind = plant`
- `target_variant = ed1`
- `build_profile = test`

El cambio observable esperado debe ser seguro y técnico:

- nueva `version`,
- nuevo `artifact_id`,
- nuevo `FW_SHA256`,
- nuevo `FW_ARTIFACT`,
- nuevo `version_code`.

No se necesita cambiar lógica funcional riesgosa para validar el primer circuito OTA físico.

## 4. Artifact fruit comparativo existente

El artifact `fruit/ed1` generado en `OTA-A`:

- sí sirve para comparación de comportamiento y para validar que el agente produce builds deliberadamente distintos,
- no sirve como primera OTA física directa sobre el baseline actual `plant/ed1`,
- porque el firmware valida `target_kind` del manifest y rechazará un rollout `fruit` sobre un baseline `plant`.

## 5. Preparación previa

### 5.1 PC del sitio

- Host en red `Kitty_2.4`
- IP alcanzable por nodos: `192.168.1.70`
- Puerto OTA local: `8080`
- App CKv2 ejecutable con:

```powershell
python main.py
```

### 5.2 Nodo físico

`ED1` debe arrancar mostrando por serial:

- `NODE_LABEL    : ED1`
- `NODE_ID       : 3`
- `FW_TARGET     : plant/ed1`
- `FW_PROFILE    : test`
- `FW_VERSION    : 1.0.0-dev`
- `FW_VERSION_CD : 10000`
- `FW_ARTIFACT   : sha256:...`
- `FW_SHA256     : ...`
- `OTA_BASE_URL  : http://192.168.1.70:8080`

Si no aparece eso, reflashear por cable antes de la OTA.

## 6. Generar el comparativo compatible

Comando recomendado:

```powershell
python tools/firmware_artifact_agent.py build-first-physical-test `
  --platformio-exe "C:\Users\JOSE DAVID\.platformio\penv\Scripts\platformio.exe" `
  --import-generated `
  --pretty
```

Resultado esperado:

- identifica el baseline `plant/ed1` del catálogo,
- genera un nuevo `.bin` `plant/ed1`,
- lo deja en `artifacts/ota_artifact_agent/<lote>/...`,
- lo importa al catálogo local,
- y marca en la salida JSON el artifact `fruit` que no debe usarse en esta primera OTA.

## 7. Verificación del comparativo antes de desplegar

Comprobar en `Firmware Manager`:

- `target_kind = plant`
- `target_variant = ed1`
- `status = situational`
- `version > 1.0.0-dev`
- `display_name` claro
- `sha256` y `file_size` presentes

Comprobar en el sidecar `artifact_plan.json`:

- `build_profile = test`
- `intent = comparative`
- tags con:
  - `build_profile_test`
  - `ota_compatible`

## 8. Publicación OTA local

Abrir:

- `Firmware Manager`
- luego `OTA Deploy`

Seleccionar:

- artifact comparativo `plant/ed1`
- nodo `ED1`
- `Host visible al nodo = 192.168.1.70`
- `Bind host = 0.0.0.0`
- `Puerto OTA = 8080`
- `Rollout channel = situational`
- `Rollout token` explícito y único

Pulsar:

- `Publicar y disparar OTA`

Verificar que existan:

- `artifacts/ota_publish/ota/rollouts/<token>/manifest.json`
- `artifacts/ota_publish/ota/rollouts/<token>/firmware.bin`

Verificar manifest:

```powershell
Invoke-WebRequest http://192.168.1.70:8080/ota/rollouts/<token>/manifest.json | Select-Object -ExpandProperty Content
```

Campos obligatorios:

- `target_kind = "plant"`
- `target_variant = "ed1"`
- `build_profile = "test"`
- `version_code > 10000`
- `artifact_id` del comparativo
- `download_url` apuntando al mismo token publicado

## 9. Observación durante la OTA

En CKv2 mirar:

- ACK del trigger
- cambio de fase OTA
- `fetching_manifest`
- `validating_manifest`
- `downloading`
- `ready_reboot`
- reboot
- `boot_validating`
- `boot_confirmed`

En serial mirar:

- aceptación de `OTA_CHECK_NOW`
- desaparición/reinicio
- nuevo banner post-boot

## 10. Verificación post-reboot

Tras volver el nodo:

- debe reaparecer en CKv2,
- debe volver a emitir `STAT`,
- debe quedar en `boot_confirmed` o equivalente,
- y el banner serial debe mostrar:
  - nueva `FW_VERSION`
  - nuevo `FW_VERSION_CD`
  - nuevo `FW_ARTIFACT`
  - nuevo `FW_SHA256`

Eso confirma que el firmware realmente cambió.

## 11. Evidencia mínima a guardar

- banner serial baseline
- artifact baseline usado
- artifact comparativo usado
- `artifact_id` anterior y nuevo
- `rollout_token`
- `rollout_id`
- captura de `OTA Deploy`
- `manifest.json`
- `deploy_status.json`
- banner serial post-OTA
- resultado final en CKv2

## 12. GO / NO-GO

### GO

- baseline `plant/ed1` visible y sano
- comparativo `plant/ed1` importado
- `version_code` mayor
- manifest publicado con `build_profile=test`
- servidor OTA responde en `192.168.1.70:8080`

### NO-GO

- intentas usar el artifact `fruit/ed1` para la primera OTA física
- comparativo con `target_kind` distinto del baseline
- `build_profile` del manifest sale `field`
- el nodo no está estable por control-plane/runtime antes del despliegue
