from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QSizePolicy


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.main_window import MainWindow  # noqa: E402
from control_okua.app_qt.viewmodels import NodesTabViewState  # noqa: E402


def _ensure_qapp() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _build_cfg() -> dict[str, object]:
    return {
        "version": 2,
        "mode": "serial",
        "profile": {"active": "serial_local"},
    }


def test_nodes_empty_state_uses_compact_non_expanding_labels() -> None:
    _ensure_qapp()
    window = MainWindow(cfg=_build_cfg(), config_path=Path("config.json"), warnings=[])
    try:
        state_policy = window.nodes_state_label.sizePolicy().verticalPolicy()
        hint_policy = window.nodes_hint_label.sizePolicy().verticalPolicy()
        summary_policy = window.nodes_summary_label.sizePolicy().verticalPolicy()
        empty_group_policy = window.nodes_empty_state_group.sizePolicy().verticalPolicy()

        assert state_policy == QSizePolicy.Policy.Fixed
        assert hint_policy == QSizePolicy.Policy.Fixed
        assert summary_policy == QSizePolicy.Policy.Fixed
        assert empty_group_policy == QSizePolicy.Policy.Maximum
    finally:
        window.close()


def test_nodes_view_state_toggles_table_and_empty_group_cleanly() -> None:
    _ensure_qapp()
    window = MainWindow(cfg=_build_cfg(), config_path=Path("config.json"), warnings=[])
    try:
        window._apply_nodes_view_state(
            NodesTabViewState(
                title="Sin nodos",
                hint="Esperando trafico",
                summary="Resumen vacio",
                show_table=False,
            )
        )
        assert window.nodes_table.isHidden() is True
        assert window.nodes_empty_state_group.isHidden() is False

        window._apply_nodes_view_state(
            NodesTabViewState(
                title="Con nodos",
                hint="Actualizando",
                summary="Resumen activo",
                show_table=True,
            )
        )
        assert window.nodes_table.isHidden() is False
        assert window.nodes_empty_state_group.isHidden() is True
    finally:
        window.close()
