# Firmware workspace

This repository now tracks the node sketch used by CKv2 tickets under:

- `firmware/okua_node_udp_v1/okua_node_udp_v1.ino`
- `firmware/okua_node_udp_v1/okua_control_plane.h`

Ticket 13.1 scope in this folder:

- explicit F3 control-plane ports (`5005/5006/5007/5008`)
- packed `OKUA_CMD` and `OKUA_ACK` models (28 bytes each)
- baseline enums/constants for later command handling

Current minimal functional commands in firmware:

- `PING`
- `REQUEST_STAT_NOW`
- `REBOOT_SOFT`
- `OTA_CHECK_NOW`

Current field fruit reference note:

- [docs/firmware/fruit_field_session_2026-04-21.md](../docs/firmware/fruit_field_session_2026-04-21.md)
- [docs/firmware/fruit_soak_2026-04-22.md](../docs/firmware/fruit_soak_2026-04-22.md)
- [docs/firmware/fruit_hotstart_2026-04-23.md](../docs/firmware/fruit_hotstart_2026-04-23.md)
- [docs/firmware/fruit_soak_2026-04-23.md](../docs/firmware/fruit_soak_2026-04-23.md)
- [docs/firmware/fruit_soak_2026-04-24_runbook.md](../docs/firmware/fruit_soak_2026-04-24_runbook.md)
- [docs/firmware/fruit_morning_bootguard_2026-04-24.md](../docs/firmware/fruit_morning_bootguard_2026-04-24.md)
- [docs/firmware/fruit_v7_morning_adaptive_2026-04-24.md](../docs/firmware/fruit_v7_morning_adaptive_2026-04-24.md)
- [docs/firmware/fruit_v8_morning_resilient_2026-04-24.md](../docs/firmware/fruit_v8_morning_resilient_2026-04-24.md)
- [docs/firmware/fruit_v14_spike_guard_2026-04-25.md](../docs/firmware/fruit_v14_spike_guard_2026-04-25.md)
- [docs/firmware/fruit_v15_rearm_balance_2026-04-25.md](../docs/firmware/fruit_v15_rearm_balance_2026-04-25.md)
- [docs/firmware/fruit_v16_reopen_2026-04-25.md](../docs/firmware/fruit_v16_reopen_2026-04-25.md)
- [docs/firmware/fruit_v17_release_fix_2026-04-25.md](../docs/firmware/fruit_v17_release_fix_2026-04-25.md)
- [docs/firmware/fruit_v18_release_timeout_2026-04-25.md](../docs/firmware/fruit_v18_release_timeout_2026-04-25.md)
- [docs/firmware/fruit_v19_release_deriv_2026-04-25.md](../docs/firmware/fruit_v19_release_deriv_2026-04-25.md)
- [docs/firmware/fruit_soak_daily_runbook.md](../docs/firmware/fruit_soak_daily_runbook.md)
- [docs/firmware/fruit_detector_redesign_review_2026-04-26.md](../docs/firmware/fruit_detector_redesign_review_2026-04-26.md)
- [docs/firmware/fruit_feedback_report_2026-04-26.md](../docs/firmware/fruit_feedback_report_2026-04-26.md)
- [docs/firmware/fruit_v20_fsm_detector_2026-04-26.md](../docs/firmware/fruit_v20_fsm_detector_2026-04-26.md)
- [docs/firmware/fruit_v21_entry_guard_2026-04-26.md](../docs/firmware/fruit_v21_entry_guard_2026-04-26.md)
- [docs/firmware/fruit_morning_status_2026-04-24.md](../docs/firmware/fruit_morning_status_2026-04-24.md)
- [docs/firmware/fruit_soak_2026-04-24.md](../docs/firmware/fruit_soak_2026-04-24.md)

Known but still not implemented (`UNSUPPORTED_CMD`):

- `SET_PROFILE`
- `SET_THROTTLE`
- `SET_STAT_RATE`
- `SET_DEBUG`

Ticket 13.2 adds UDP CMD receive parsing + structural validation/classification
without ACK emission and without command execution.

Ticket 13.5 adds minimal safe command execution for:

- `PING` (control-plane roundtrip, no extra side effects)
- `REQUEST_STAT_NOW` (forces immediate `OKUA_STAT` on accepted fresh commands only;
  exact duplicate retries do not re-trigger side effects)

Ticket 13.6 adds `REBOOT_SOFT` as accepted command with deferred reboot:

- ACK is emitted first by control-plane pipeline
- reboot is scheduled with a short delay and executed in `loop()`
- exact duplicate retries do not re-schedule reboot side effects
- known but not yet implemented `SET_*` commands are rejected as `UNSUPPORTED_CMD`

Final closure summary for Ticket 13:

- `docs/firmware/firmware_cmd_ack_minimal.md`
- `docs/firmware/ticket13_validation_runbook.md`

Build and validation entrypoints:

- PlatformIO build config: `platformio.ini` (env: `okua_node_esp32dev`)
- CI workflow: `.github/workflows/firmware-build.yml`
- Host-side F3 validator: `tools/firmware_f3_validator.py`
- OTA runtime notes: `docs/firmware/ota_firmware_runtime.md`

Local Wi-Fi secrets override:

- defaults in repo: `WIFI_SSID="OKUA_CORE"` and `WIFI_PASS="CHANGE_ME"`
- default control secret in repo: `OKUA_CONTROL_SECRET="CHANGE_ME_CONTROL_SECRET"`
- optional local override: `firmware/okua_node_udp_v1/okua_node_secrets.h`
- template: `firmware/okua_node_udp_v1/okua_node_secrets.example.h`
