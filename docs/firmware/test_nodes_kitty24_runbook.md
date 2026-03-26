# Runbook - Nodos de prueba `Kitty_2.4` (EB2 / EC2 / ED2)

## 1) Objetivo

Preparar 3 ESP32 de banco para validacion local CKv2 en nueva red Wi-Fi:

- `EB2` -> `NODE_ID=6`
- `EC2` -> `NODE_ID=7`
- `ED2` -> `NODE_ID=8`

Red de prueba:

- `SSID=Kitty_2.4`
- `PASSWORD=66661174`

## 2) Notas de seguridad y alcance

- Credenciales y secreto van en `firmware/okua_node_udp_v1/okua_node_secrets.h` (archivo local ignorado por git).
- No se cambiaron defaults productivos del firmware.
- Se usa el target unico vigente: `okua_node_udp_v1` (sin firmware paralelo por nodo).

## 3) Modo de prueba que se usa

En esta rama, el firmware ya arranca por defecto en:

- `ACTIVE_MODE = MODE_TEST`
- `ACTIVE_SENSOR = SENSOR_PLANT`

Eso activa generacion automatica de notas (`servicePlantTest`) sin depender de toques manuales.

## 4) Preparar override local por nodo

Usar helper:

`firmware/okua_node_udp_v1/prepare_test_node_kitty24.ps1`

Ejemplos (PowerShell, desde raiz del repo):

```powershell
# EB2
.\firmware\okua_node_udp_v1\prepare_test_node_kitty24.ps1 `
  -NodeLabel EB2 `
  -WifiSsid "Kitty_2.4" `
  -WifiPass "66661174" `
  -PcIp "192.168.1.57"

# EC2
.\firmware\okua_node_udp_v1\prepare_test_node_kitty24.ps1 `
  -NodeLabel EC2 `
  -WifiSsid "Kitty_2.4" `
  -WifiPass "66661174" `
  -PcIp "192.168.1.57"

# ED2
.\firmware\okua_node_udp_v1\prepare_test_node_kitty24.ps1 `
  -NodeLabel ED2 `
  -WifiSsid "Kitty_2.4" `
  -WifiPass "66661174" `
  -PcIp "192.168.1.57"
```

Notas:

- `-PcIp` debe ser la IP del host donde corre CKv2 en esa red.
- Si no se pasa `-ControlSecret`, el helper intenta resolverlo desde entorno/archivo local.
- El helper genera/actualiza `okua_node_secrets.h` para el nodo elegido.

## 5) Compilar firmware

```powershell
python -m platformio run -e okua_node_esp32dev
```

## 6) Subir firmware por nodo

Conectar el ESP32 correspondiente y subir (ajustar `COMx`):

```powershell
python -m platformio run -e okua_node_esp32dev -t upload --upload-port COMx
```

Repetir el flujo por cada nodo en este orden recomendado:

1. Generar `okua_node_secrets.h` para EB2
2. Upload EB2
3. Generar `okua_node_secrets.h` para EC2
4. Upload EC2
5. Generar `okua_node_secrets.h` para ED2
6. Upload ED2

## 7) Verificacion minima tras carga

En monitor serie:

```powershell
python -m platformio device monitor -b 115200 -p COMx
```

Esperado:

- `NODE_LABEL` correcto (`EB2`/`EC2`/`ED2`)
- `NODE_ID` correcto (`6`/`7`/`8`)
- `MODE : TEST`
- `SENSOR : PLANT`
- `LOCAL_IP` en red `Kitty_2.4`
- `PC_IP` igual al host CKv2 configurado

En CKv2 (`python main.py`):

1. Iniciar sesion UDP.
2. Ver nodos en `Nodos en vivo`.
3. Confirmar trafico automatico (EVT/STAT) sin interaccion manual.

## 8) Checklist rapido por nodo

- EB2 -> `NODE_LABEL=EB2`, `NODE_ID=6`
- EC2 -> `NODE_LABEL=EC2`, `NODE_ID=7`
- ED2 -> `NODE_LABEL=ED2`, `NODE_ID=8`
- Wi-Fi: `Kitty_2.4`
- Password: `66661174`
- Modo: `TEST + PLANT` (auto-notas activas)

Con esto queda listo el banco local para retomar validaciones reales de CKv2.
