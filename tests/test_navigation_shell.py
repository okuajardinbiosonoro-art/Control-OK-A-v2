from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.navigation_shell import NavigationPanel, build_primary_shell_items  # noqa: E402


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_build_primary_shell_items_uses_operator_first_order() -> None:
    items = build_primary_shell_items(include_remote=True)
    assert [item.key for item in items] == [
        "home",
        "nodes",
        "diagnostics",
        "firmware",
        "technical",
        "remote",
    ]
    assert items[0].label == "Inicio"
    assert items[-1].label == "Remoto"


def test_build_primary_shell_items_can_hide_remote_surface() -> None:
    items = build_primary_shell_items(include_remote=False)
    assert [item.key for item in items] == [
        "home",
        "nodes",
        "diagnostics",
        "firmware",
        "technical",
    ]


def test_navigation_panel_tracks_checked_section() -> None:
    _ensure_qapp()
    panel = NavigationPanel(build_primary_shell_items(include_remote=True))
    try:
        panel.set_current_key("firmware")
        assert panel.button_for_key("firmware").isChecked() is True
        assert panel.button_for_key("home").isChecked() is False
    finally:
        panel.close()
