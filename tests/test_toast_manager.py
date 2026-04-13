from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.widgets.toast_manager import ToastManager  # noqa: E402


def _ensure_qapp() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_toast_manager_creates_visible_toast_without_breaking_parent() -> None:
    app = _ensure_qapp()
    parent = QWidget()
    parent.resize(900, 640)
    manager = ToastManager(parent)
    try:
        parent.show()
        app.processEvents()
        manager.show_toast(title="Servicio remoto", message="Configuración aplicada.", level="success")
        app.processEvents()
        assert len(manager._toasts) == 1
        toast = manager._toasts[0]
        assert toast.title_label.text() == "Servicio remoto"
        assert toast.message_label.text() == "Configuración aplicada."
        assert toast.property("level") == "success"
        assert toast.styleSheet() == ""
        assert toast.pos().x() >= parent.width() - toast.width() - 24
        assert toast.pos().y() >= 0
    finally:
        parent.close()
