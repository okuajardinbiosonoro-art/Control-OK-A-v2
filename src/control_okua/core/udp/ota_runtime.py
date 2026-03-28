from __future__ import annotations

from dataclasses import dataclass


OTA_FLAG_CHECK_PENDING = 0x01
OTA_FLAG_PENDING_REBOOT = 0x02
OTA_FLAG_PENDING_VERIFY = 0x04
OTA_FLAG_HEALTH_CONFIRMED = 0x08


@dataclass(frozen=True)
class OkuaOtaRuntimeInfo:
    state_code: int
    error_code: int
    flags: int
    state_key: str
    error_key: str
    check_pending: bool
    pending_reboot: bool
    pending_verify: bool
    health_confirmed: bool


def decode_okua_ota_runtime(rsv: tuple[int, int, int] | list[int]) -> OkuaOtaRuntimeInfo:
    if len(rsv) != 3:
        raise ValueError("OTA runtime rsv debe tener exactamente 3 bytes.")
    state_code = int(rsv[0]) & 0xFF
    error_code = int(rsv[1]) & 0xFF
    flags = int(rsv[2]) & 0xFF
    return OkuaOtaRuntimeInfo(
        state_code=state_code,
        error_code=error_code,
        flags=flags,
        state_key=_state_key_for_code(state_code),
        error_key=_error_key_for_code(error_code),
        check_pending=bool(flags & OTA_FLAG_CHECK_PENDING),
        pending_reboot=bool(flags & OTA_FLAG_PENDING_REBOOT),
        pending_verify=bool(flags & OTA_FLAG_PENDING_VERIFY),
        health_confirmed=bool(flags & OTA_FLAG_HEALTH_CONFIRMED),
    )


def _state_key_for_code(state_code: int) -> str:
    mapping = {
        0: "idle",
        1: "triggered",
        2: "fetching_manifest",
        3: "validating_manifest",
        4: "downloading",
        5: "ready_reboot",
        6: "boot_validating",
        7: "boot_confirmed",
        255: "error",
    }
    return mapping.get(int(state_code) & 0xFF, "unknown")


def _error_key_for_code(error_code: int) -> str:
    mapping = {
        0: "none",
        1: "invalid_trigger",
        2: "manifest_http",
        3: "manifest_parse",
        4: "manifest_incompatible",
        5: "version_rejected",
        6: "already_current",
        7: "download_http",
        8: "download_size",
        9: "download_hash",
        10: "ota_begin",
        11: "ota_write",
        12: "ota_finalize",
        13: "boot_wifi_timeout",
        14: "boot_stat_timeout",
        15: "boot_identity_mismatch",
        16: "boot_validate",
        17: "nvs_error",
    }
    return mapping.get(int(error_code) & 0xFF, "unknown_error")
