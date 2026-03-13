from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QPushButton


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.main_window import MainWindow  # noqa: E402
from control_okua.core.config.config_schema import validate_and_fix  # noqa: E402
from control_okua.core.profiles.profile_service import (  # noqa: E402
    normalize_profile_mode_consistency,
    set_active_profile,
)


def _ensure_qapp() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_udp_profile_forces_udp_mode() -> None:
    cfg = {"mode": "serial", "profile": {"active": "udp_jardin"}}
    normalized_cfg, warnings = normalize_profile_mode_consistency(cfg)

    assert normalized_cfg["mode"] == "udp"
    assert any("udp_jardin" in warning for warning in warnings)


def test_serial_profile_forces_serial_mode() -> None:
    cfg = {"mode": "udp", "profile": {"active": "serial_local"}}
    normalized_cfg, warnings = normalize_profile_mode_consistency(cfg)

    assert normalized_cfg["mode"] == "serial"
    assert any("serial_local" in warning for warning in warnings)


def test_validate_and_fix_normalizes_inconsistent_profile_mode() -> None:
    cfg = {"version": 2, "mode": "serial", "profile": {"active": "udp_jardin"}}
    fixed_cfg, warnings = validate_and_fix(cfg)

    assert fixed_cfg["mode"] == "udp"
    assert any("se normalizó mode='serial' a mode='udp'" in warning.lower() for warning in warnings)


def test_legacy_config_without_profile_keeps_compatibility() -> None:
    cfg = {"version": 2, "mode": "serial"}
    fixed_cfg, _warnings = validate_and_fix(cfg)

    assert fixed_cfg["profile"]["active"] is None
    assert fixed_cfg["mode"] == "serial"


def test_set_active_profile_syncs_mode() -> None:
    cfg = {"version": 2, "mode": "udp", "profile": {"active": None}}
    updated_cfg = set_active_profile(cfg, "serial_local")

    assert updated_cfg["profile"]["active"] == "serial_local"
    assert updated_cfg["mode"] == "serial"


def test_main_window_primary_actions_no_longer_expose_change_mode() -> None:
    _ensure_qapp()
    cfg = {"version": 2, "mode": "serial", "profile": {"active": "serial_local"}}
    window = MainWindow(cfg=cfg, config_path=Path("config.json"), warnings=[])
    button_texts = {button.text() for button in window.findChildren(QPushButton)}
    window.close()

    assert "Cambiar perfil" in button_texts
    assert "Cambiar modo" not in button_texts
