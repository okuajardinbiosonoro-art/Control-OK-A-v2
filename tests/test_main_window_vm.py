from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.viewmodels.main_window_vm import (  # noqa: E402
    build_general_status_summary,
    build_logging_summary,
    build_mode_summary,
    build_transport_summary,
)


def test_serial_mode_and_transport_summary() -> None:
    cfg = {
        "mode": "serial",
        "serial": {
            "baudrate": 115200,
            "port": "COM5",
        },
    }

    mode_summary = build_mode_summary(cfg)
    transport_summary = build_transport_summary(cfg)

    assert mode_summary == "Modo actual: Serial"
    assert "Transporte configurado: Serial" in transport_summary
    assert "COM5" in transport_summary


def test_udp_mode_and_transport_summary() -> None:
    cfg = {
        "mode": "udp",
        "udp": {
            "bind_ip": "0.0.0.0",
            "evt_port": 5005,
            "stat_port": 5006,
            "cmd_port": 5007,
        },
    }

    mode_summary = build_mode_summary(cfg)
    transport_summary = build_transport_summary(cfg)

    assert mode_summary == "Modo actual: Ethernet/UDP"
    assert "Transporte configurado: UDP" in transport_summary
    assert "evt:5005" in transport_summary


def test_logging_summary_enabled_and_disabled() -> None:
    enabled_cfg = {"logging": {"enabled": True}}
    disabled_cfg = {"logging": {"enabled": False}}

    assert build_logging_summary(enabled_cfg) == "Logging: habilitado"
    assert build_logging_summary(disabled_cfg) == "Logging: deshabilitado"


def test_general_status_with_and_without_warnings() -> None:
    cfg = {"mode": "serial"}

    no_warnings_status = build_general_status_summary(cfg, [])
    with_warnings_status = build_general_status_summary(cfg, ["warning 1"])

    assert no_warnings_status == "Estado general: aplicación lista / sesión no iniciada"
    assert "advertencias (1)" in with_warnings_status
