from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QPushButton, QSizePolicy


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.main_window import MainWindow  # noqa: E402
from control_okua.app_qt.viewmodels import NodesTabViewState  # noqa: E402
from control_okua.core.registry import NodeSnapshot, NodeStatus  # noqa: E402
from control_okua.core.session import BackendKind, SessionSnapshot, SessionState  # noqa: E402


def _ensure_qapp() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _build_cfg() -> dict[str, object]:
    return {
        "version": 2,
        "mode": "udp",
        "profile": {"active": "udp_jardin"},
    }


def _node_snapshot(*, node_id: int) -> NodeSnapshot:
    return NodeSnapshot(
        node_id=node_id,
        label=None,
        node_type=None,
        last_seen_pc_ts=100.0,
        last_seq_evt=1,
        last_seq_stat=1,
        pps_evt=1.0,
        pps_stat=2.0,
        loss_evt_pct=0.0,
        loss_stat_pct=0.0,
        rssi_dbm=-50,
        last_note=64,
        last_velocity=100,
        last_evt_ts_ms=1,
        last_evt_flags=1,
        last_state_flags=1,
        last_uptime_s=10,
        reported_pps_x10=10,
        status=NodeStatus.ONLINE,
    )


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
        assert window.nodes_tree.isHidden() is True
        assert window.nodes_empty_state_group.isHidden() is False

        window._apply_nodes_view_state(
            NodesTabViewState(
                title="Con nodos",
                hint="Actualizando",
                summary="Resumen activo",
                show_table=True,
            )
        )
        assert window.nodes_tree.isHidden() is False
        assert window.nodes_empty_state_group.isHidden() is True
    finally:
        window.close()


def test_main_tabs_do_not_include_estado_actual_by_default() -> None:
    _ensure_qapp()
    window = MainWindow(cfg=_build_cfg(), config_path=Path("config.json"), warnings=[])
    try:
        tab_titles = [window.tabs.tabText(index) for index in range(window.tabs.count())]
        assert tab_titles == ["Sesión", "Nodos en vivo", "Estado técnico", "Control F3"]
    finally:
        window.close()


def test_control_plane_panel_is_separated_from_diagnostics() -> None:
    _ensure_qapp()
    window = MainWindow(cfg=_build_cfg(), config_path=Path("config.json"), warnings=[])
    try:
        diagnostics_buttons = [btn.text() for btn in window.diagnostics_tab.findChildren(QPushButton)]
        assert "PING" not in diagnostics_buttons
        assert "Pedir STAT" not in diagnostics_buttons
        assert "Reinicio suave" not in diagnostics_buttons

        control_buttons = [btn.text() for btn in window.control_plane_tab.findChildren(QPushButton)]
        assert "PING" in control_buttons
        assert "Pedir STAT" in control_buttons
        assert "Reinicio suave" in control_buttons
        assert "Limpiar bitácora" in control_buttons
        assert not hasattr(window.control_plane_panel, "node_ip_edit")
        assert window.control_plane_panel.node_selector_combo.count() >= 25
        assert "PING:" in window.control_plane_panel.policy_values_label.text()
        detail_tabs = [
            window.control_plane_panel.details_tabs.tabText(i)
            for i in range(window.control_plane_panel.details_tabs.count())
        ]
        assert detail_tabs == ["Resumen", "Diagnóstico", "Bitácora"]
        assert window.control_plane_panel.result_view.minimumHeight() >= 320
    finally:
        window.close()


def test_nodes_tree_uses_available_width_and_keeps_pps_loss_readable() -> None:
    app = _ensure_qapp()
    window = MainWindow(cfg=_build_cfg(), config_path=Path("config.json"), warnings=[])
    try:
        window._session_snapshot = SessionSnapshot(
            state=SessionState.RUNNING,
            active_profile="udp_jardin",
            mode="udp",
            backend=BackendKind.UDP,
            message="running",
            error=None,
            can_start=False,
            can_stop=True,
        )
        window.show()
        app.processEvents()
        window.resize(1400, 800)
        window.tabs.setCurrentWidget(window.nodes_tab)
        window._apply_nodes_view_state(
            NodesTabViewState(
                title="Nodos",
                hint="",
                summary="",
                show_table=True,
            )
        )
        app.processEvents()

        window._refresh_nodes_tree(
            [_node_snapshot(node_id=1), _node_snapshot(node_id=10)],
            now_monotonic=101.0,
        )
        app.processEvents()

        viewport_width = window.nodes_tree.viewport().width()
        widths = [window.nodes_tree.columnWidth(idx) for idx in range(window.nodes_tree.columnCount())]
        assert sum(widths) >= int(viewport_width * 0.9)
        assert widths[3] >= 110
        assert widths[4] >= 120

        window.resize(760, 700)
        app.processEvents()
        window._adjust_nodes_tree_columns()
        app.processEvents()

        narrow_widths = [window.nodes_tree.columnWidth(idx) for idx in range(window.nodes_tree.columnCount())]
        assert narrow_widths[3] >= 95
        assert narrow_widths[4] >= 100
    finally:
        window.close()


def test_help_menu_has_about_action_and_uses_qmessagebox(monkeypatch) -> None:
    _ensure_qapp()
    window = MainWindow(cfg=_build_cfg(), config_path=Path("config.json"), warnings=[])
    called: dict[str, str] = {}

    def _fake_about(_parent, title: str, text: str) -> None:
        called["title"] = title
        called["text"] = text

    monkeypatch.setattr("control_okua.app_qt.main_window.QMessageBox.about", _fake_about)
    try:
        menu_titles = [action.text() for action in window.menuBar().actions()]
        assert "Ayuda" in menu_titles
        assert window.about_action.text() == "Acerca de"

        window.show_about_dialog()
        assert called["title"] == "Acerca de"
        assert "Control OKÚA v2" in called["text"]
    finally:
        window.close()
