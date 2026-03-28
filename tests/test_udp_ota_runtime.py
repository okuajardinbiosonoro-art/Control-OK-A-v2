from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.udp import (  # noqa: E402
    OTA_FLAG_CHECK_PENDING,
    OTA_FLAG_HEALTH_CONFIRMED,
    OTA_FLAG_PENDING_REBOOT,
    OTA_FLAG_PENDING_VERIFY,
    decode_okua_ota_runtime,
)


def test_decode_okua_ota_runtime_maps_state_error_and_flags() -> None:
    info = decode_okua_ota_runtime((5, 9, OTA_FLAG_PENDING_REBOOT | OTA_FLAG_PENDING_VERIFY))

    assert info.state_code == 5
    assert info.error_code == 9
    assert info.flags == OTA_FLAG_PENDING_REBOOT | OTA_FLAG_PENDING_VERIFY
    assert info.state_key == "ready_reboot"
    assert info.error_key == "download_hash"
    assert info.check_pending is False
    assert info.pending_reboot is True
    assert info.pending_verify is True
    assert info.health_confirmed is False


def test_decode_okua_ota_runtime_handles_idle_and_confirmation_bits() -> None:
    info = decode_okua_ota_runtime((0, 0, OTA_FLAG_CHECK_PENDING | OTA_FLAG_HEALTH_CONFIRMED))

    assert info.state_key == "idle"
    assert info.error_key == "none"
    assert info.check_pending is True
    assert info.pending_reboot is False
    assert info.pending_verify is False
    assert info.health_confirmed is True
