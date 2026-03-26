from __future__ import annotations

import os
import sys

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from control_okua.app_qt.main_window import MainWindow
from control_okua.app_qt.profile_selector_dialog import ProfileSelectorDialog
from control_okua.app_qt.resources import app_icon_path, load_qss, resource_path
from control_okua.core.config.config_schema import load_config, save_config
from control_okua.core.profiles.profile_service import (
    infer_profile_from_config,
    is_known_profile_id,
    set_active_profile,
)


def _get_active_profile_id(cfg: dict[str, object]) -> str | None:
    profile_cfg = cfg.get("profile")
    if not isinstance(profile_cfg, dict):
        return None
    active_profile = profile_cfg.get("active")
    if isinstance(active_profile, str) and is_known_profile_id(active_profile):
        return active_profile
    return None


def run_app() -> int:
    cfg, warnings, config_path = load_config()
    for warning in warnings:
        print(f"[config] {warning}")

    # Ayuda a evitar clipping visual cuando el factor DPI es fraccional
    # (caso frecuente en equipos de campo con escalado 125%/150%).
    if hasattr(QApplication, "setHighDpiScaleFactorRoundingPolicy") and hasattr(
        Qt, "HighDpiScaleFactorRoundingPolicy"
    ):
        try:
            QApplication.setHighDpiScaleFactorRoundingPolicy(
                Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
            )
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    qss_path = resource_path("assets/theme.qss")
    if qss_path.exists():
        app.setStyleSheet(load_qss(qss_path))

    icon_path = app_icon_path()
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    active_profile = _get_active_profile_id(cfg)
    if active_profile is None:
        inferred_profile = infer_profile_from_config(cfg)
        selected_profile = ProfileSelectorDialog.choose_profile(
            current_profile_id=inferred_profile,
        )

        if isinstance(selected_profile, str):
            cfg = set_active_profile(cfg, selected_profile)
            save_config(cfg, config_path)
            profile_warning = (
                f"profile.active actualizado a '{selected_profile}' desde selector guiado."
            )
            warnings.append(profile_warning)
            print(f"[config] {profile_warning}")
            active_profile = selected_profile

    window = MainWindow(cfg=cfg, config_path=config_path, warnings=warnings)
    window.show()

    # Permite validaciones automáticas sin afectar ejecución normal.
    auto_close_ms = os.getenv("CKV2_AUTOCLOSE_MS", "").strip()
    if auto_close_ms.isdigit():
        QTimer.singleShot(int(auto_close_ms), app.quit)

    return app.exec()
