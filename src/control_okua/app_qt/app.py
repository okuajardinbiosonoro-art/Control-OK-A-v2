from __future__ import annotations

import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from control_okua.app_qt.main_window import MainWindow
from control_okua.app_qt.mode_selector_dialog import ModeSelectorDialog
from control_okua.app_qt.resources import app_icon_path, load_qss, resource_path
from control_okua.core.config.config_schema import load_config, save_config


def _is_valid_mode(value: object) -> bool:
    return isinstance(value, str) and value in {"serial", "udp"}


def run_app() -> int:
    cfg, warnings, config_path = load_config()
    for warning in warnings:
        print(f"[config] {warning}")

    app = QApplication(sys.argv)

    qss_path = resource_path("assets/theme.qss")
    if qss_path.exists():
        app.setStyleSheet(load_qss(qss_path))

    icon_path = app_icon_path()
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    if not _is_valid_mode(cfg.get("mode")):
        selected_mode = ModeSelectorDialog.choose_mode()
        cfg["mode"] = selected_mode
        save_config(cfg, config_path)
        selection_warning = (
            f"mode no definido/invalid; se selecciono {selected_mode} y se guardo."
        )
        warnings.append(selection_warning)
        print(f"[config] {selection_warning}")

    window = MainWindow(cfg=cfg, config_path=config_path, warnings=warnings)
    window.show()

    # Permite validaciones automáticas sin afectar ejecución normal.
    auto_close_ms = os.getenv("CKV2_AUTOCLOSE_MS", "").strip()
    if auto_close_ms.isdigit():
        QTimer.singleShot(int(auto_close_ms), app.quit)

    return app.exec()
