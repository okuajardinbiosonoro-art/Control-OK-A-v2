# Ticket 13 validation runbook (firmware F3 minimal)

## 1) Prerequisites
- ESP32 board compatible with Arduino-ESP32.
- USB cable + serial access to flash the board.
- Python 3.10+ on host PC.
- PlatformIO CLI (`pio`) available in shell.
- Host and ESP32 on same LAN.

## 2) Local secrets configuration

### Firmware side
1. Copy:
   - `firmware/okua_node_udp_v1/okua_node_secrets.example.h`
   - to `firmware/okua_node_udp_v1/okua_node_secrets.h`
2. Set local values:
   - `WIFI_SSID`
   - `WIFI_PASS`
   - `OKUA_CONTROL_SECRET`
3. Ensure host IP is configured in firmware (`PC_IP`) so STAT/ACK visibility is possible from test PC.

### Host-side validator
- Prefer environment variable:
  - `OKUA_CONTROL_SECRET=<same secret used in firmware>`
- Alternative:
  - `--secret <value>`
  - `--secret-file <path>`

## 3) Build firmware
From repo root:

```powershell
pio run -e okua_node_esp32dev
```

If your user profile has restricted permissions for default PlatformIO cache,
use a local core dir:

```powershell
$env:PLATFORMIO_CORE_DIR = "$PWD\.pio-home"
pio run -e okua_node_esp32dev
```

Expected result:
- successful compile with no missing includes/symbols.

## 4) Flash firmware to ESP32
Identify serial port (example `COM5`) and run:

```powershell
pio run -e okua_node_esp32dev -t upload --upload-port COM5
```

Optional serial monitor:

```powershell
pio device monitor -b 115200 -p COM5
```

## 5) Verify Wi-Fi and boot state
Check serial output:
- node prints local IP
- node prints protocol ports (`5005/5006/5007/5008`)
- node enters normal loop without continuous reconnect failures

## 6) Validate `PING -> ACK`
Unicast:

```powershell
python tools/firmware_f3_validator.py ping `
  --target-ip 192.168.88.120 `
  --node-id 16
```

Success criteria:
- ACK received
- `stage=ACCEPTED`
- `status=OK`
- `auth_valid=True`

## 7) Validate `REQUEST_STAT_NOW -> ACK + STAT`
Unicast:

```powershell
python tools/firmware_f3_validator.py request_stat_now `
  --target-ip 192.168.88.120 `
  --node-id 16
```

Success criteria:
- ACK `ACCEPTED + OK`
- STAT frame received within timeout

## 8) Validate `REBOOT_SOFT` safely
`REBOOT_SOFT` is blocked unless explicit opt-in.

```powershell
python tools/firmware_f3_validator.py reboot_soft `
  --target-ip 192.168.88.120 `
  --node-id 16 `
  --allow-reboot `
  --reboot-delay-ms 200
```

Success criteria:
- ACK `ACCEPTED + OK` received first
- node reboots shortly after
- node reconnects to Wi-Fi and resumes UDP loop

## 9) Observe ACK/STAT behavior
- ACK target is host `ACK_PORT=5008`.
- STAT uses `STAT_PORT=5006`.
- Validator prints correlated `seq/cmd_id/nonce`, status, err_detail and RTT.

## 10) Failure criteria and triage
- No ACK:
  - verify firewall, host bind IP, target IP, ports, shared secret.
- `INVALID_AUTH`:
  - mismatch in `OKUA_CONTROL_SECRET`.
- `REPLAY_REJECTED`:
  - repeated stale nonce/seq usage outside retry expectations.
- `RATE_LIMITED`:
  - reduce command cadence, respect `retry_after_ms`.

## 11) Evidence to retain
- Build command output.
- Upload command output.
- Validator outputs for:
  - `PING`
  - `REQUEST_STAT_NOW`
  - `REBOOT_SOFT` (if executed)
- Serial logs showing reboot/reconnect for reboot test.

## 12) Known limitations
- This runbook validates the minimal Ticket 13 block only.
- `SET_PROFILE`, `SET_THROTTLE`, `SET_STAT_RATE`, `SET_DEBUG` are still intentionally rejected (`UNSUPPORTED_CMD`).
- Full app-side orchestration and broader production checks are out of scope for this runbook.
