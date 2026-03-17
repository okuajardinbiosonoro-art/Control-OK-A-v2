# Firmware CMD/ACK minimal closure (Ticket 13)

## Scope implemented
- Real `OKUA_CMD` RX on node bind port `5007`.
- Real `OKUA_ACK` TX to `source_ip:5008`.
- Structural parser + classification.
- Security minimum in RX path:
  - `auth_tag32` validation (HMAC-SHA256 truncated to `u32` LE)
  - `nonce:u64` validation
  - anti-replay window
  - rate-limit (token bucket)
- Retry/idempotency baseline:
  - dedup cache by `(source_ip, cmd_seq, nonce, cmd_id, arg0, arg1)`
  - duplicate ACK replay with duplicate flag

## Implemented commands today
- `PING`
  - ACK: `ACCEPTED + OK`
  - no extra side effect
- `REQUEST_STAT_NOW`
  - ACK: `ACCEPTED + OK`
  - forces immediate `OKUA_STAT`
- `REBOOT_SOFT`
  - ACK: `ACCEPTED + OK`
  - deferred reboot scheduled in loop (ACK-first behavior)

## Known but not implemented commands
- `SET_PROFILE` -> `REJECTED + UNSUPPORTED_CMD`
- `SET_THROTTLE` -> `REJECTED + UNSUPPORTED_CMD`
- `SET_STAT_RATE` -> `REJECTED + UNSUPPORTED_CMD`
- `SET_DEBUG` -> `REJECTED + UNSUPPORTED_CMD`

## Current ACK policy
- Structural garbage or not-for-me target:
  - silence (no ACK)
- Valid targeted command + implemented handler:
  - `ACCEPTED + OK`
- Valid targeted command + known but not implemented:
  - `REJECTED + UNSUPPORTED_CMD`
- Security failure:
  - `REJECTED` with specific status/detail (`INVALID_AUTH`, `REPLAY_REJECTED`, `RATE_LIMITED`, etc.)

## Broadcast policy
- Broadcast allowed only for:
  - `PING`
  - `REQUEST_STAT_NOW`
- Broadcast blocked for:
  - `REBOOT_SOFT`
  - all `SET_*`

## Notes for next stage
- Pending handler implementation for `SET_PROFILE`, `SET_THROTTLE`, `SET_STAT_RATE`, `SET_DEBUG`.
- In this environment, firmware toolchain compile checks were not available (`arduino-cli` / `platformio` not installed).
- End-to-end app+firmware validation should be executed in the next stage with the real toolchain and network path.
