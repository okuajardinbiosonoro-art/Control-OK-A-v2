from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QPushButton, QSizePolicy


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.advanced_tools_dialog import AdvancedToolsDialog  # noqa: E402
from control_okua.app_qt.main_window import MainWindow  # noqa: E402
from control_okua.app_qt.viewmodels import NodesTabViewState  # noqa: E402
from control_okua.core.registry import NodeSnapshot, NodeStatus  # noqa: E402
from control_okua.core.session import BackendKind, SessionSnapshot, SessionState  # noqa: E402
from control_okua.services.remote_api_bootstrap import (  # noqa: E402
    RemoteApiRuntimeStatus,
)


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
        assert tab_titles == ["Inicio", "Nodos", "Diagnóstico", "Firmware", "Técnico", "Remoto"]
        assert window.tabs.currentWidget() is window.home_tab
        assert window.tabs.tabBar().isHidden() is True
        assert window.navigation_panel is not None
        assert window.navigation_panel.button_for_key("home").isChecked() is True
        assert window.shell_title_label.text() == "Inicio"
        assert window.home_map_panel.has_map_asset() is True
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
        technical_buttons = [btn.text() for btn in window.technical_tab.findChildren(QPushButton)]
        assert "Estado actual" in technical_buttons
        assert "Herramientas avanzadas" in technical_buttons
    finally:
        window.close()


def test_firmware_and_remote_surfaces_are_visible_from_primary_shell() -> None:
    _ensure_qapp()
    window = MainWindow(cfg=_build_cfg(), config_path=Path("config.json"), warnings=[])
    try:
        assert window.open_firmware_manager_button.text() == "Abrir Firmware Manager"
        assert "catalog" in window._firmware_summary_labels
        assert "status" in window._remote_summary_labels
        window.show_remote_tab()
        assert window.tabs.currentWidget() is window.remote_tab
        assert window.shell_title_label.text() == "Remoto"
    finally:
        window.close()


def test_navigation_panel_changes_real_view_and_keeps_selection_in_sync() -> None:
    app = _ensure_qapp()
    window = MainWindow(cfg=_build_cfg(), config_path=Path("config.json"), warnings=[])
    try:
        window.show()
        app.processEvents()
        window.navigation_panel.button_for_key("nodes").click()
        app.processEvents()
        assert window.tabs.currentWidget() is window.nodes_tab
        assert window.navigation_panel.button_for_key("nodes").isChecked() is True
        assert window.shell_title_label.text() == "Nodos"

        window.navigation_panel.button_for_key("remote").click()
        app.processEvents()
        assert window.tabs.currentWidget() is window.remote_tab
        assert window.navigation_panel.button_for_key("remote").isChecked() is True
        assert window.shell_title_label.text() == "Remoto"
    finally:
        window.close()


def test_home_surface_keeps_primary_action_and_visual_map_as_main_elements() -> None:
    app = _ensure_qapp()
    window = MainWindow(cfg=_build_cfg(), config_path=Path("config.json"), warnings=[])
    try:
        window.show()
        app.processEvents()
        window.resize(1400, 900)
        app.processEvents()
        assert window.tabs.currentWidget() is window.home_tab
        assert window.start_session_button.text() == "Iniciar sesión"
        assert window.home_map_panel.has_map_asset() is True
        assert window.home_map_panel.width() >= 700
        assert window.home_alerts_label.text().strip()
        assert not hasattr(window, "home_visual_placeholder")
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


def test_advanced_tools_dialog_surfaces_remote_api_runtime_status(monkeypatch) -> None:
    _ensure_qapp()
    window = MainWindow(cfg=_build_cfg(), config_path=Path("config.json"), warnings=[])
    remote_status = RemoteApiRuntimeStatus(
        enabled=True,
        service_state="running",
        exposure_mode="tailscale_only",
        effective_bind_host="100.88.127.119",
        port=8788,
        local_access_url=None,
        remote_access_url="http://100.88.127.119:8788/remote/",
        access_urls=("http://100.88.127.119:8788/remote/",),
        failure_message=None,
        user_store_path=Path("remote_api_users.json"),
    )
    window.set_remote_api_status(remote_status)

    def _fake_exec(self) -> int:
        return 0

    monkeypatch.setattr("control_okua.app_qt.advanced_tools_dialog.AdvancedToolsDialog.exec", _fake_exec)
    try:
        window.open_advanced_tools()
        dialog = window._advanced_dialog
        assert dialog is not None
        assert dialog.remote_status_label.text() == "running"
        assert dialog.remote_exposure_mode_label.text() == "tailscale_only"
        assert dialog.remote_bind_label.text() == "100.88.127.119"
        assert dialog.remote_port_label.text() == "8788"
        assert dialog.remote_local_url_label.text() == "No sugerida"
        assert dialog.remote_remote_url_label.text() == "http://100.88.127.119:8788/remote/"
        assert dialog.remote_store_label.text() == "remote_api_users.json"
        assert dialog.remote_failure_label.text() == "Ninguno"
    finally:
        window.close()


def test_advanced_tools_dialog_applies_remote_settings_from_ui(monkeypatch) -> None:
    _ensure_qapp()
    cfg = _build_cfg()
    cfg["remote_api"] = {
        "enabled": True,
        "exposure_mode": "local_only",
    }
    status_holder = {
        "status": RemoteApiRuntimeStatus(
            enabled=True,
            service_state="running",
            exposure_mode="local_only",
            effective_bind_host="127.0.0.1",
            port=8788,
            local_access_url="http://127.0.0.1:8788/remote/",
            remote_access_url=None,
            access_urls=("http://127.0.0.1:8788/remote/",),
            failure_message=None,
            user_store_path=Path("remote_api_users.json"),
        )
    }
    captured: dict[str, object] = {}
    info_box: dict[str, str] = {}

    def _apply_remote_settings(enabled: bool, exposure_mode: str) -> tuple[object, str]:
        captured["enabled"] = enabled
        captured["exposure_mode"] = exposure_mode
        cfg["remote_api"]["enabled"] = enabled
        cfg["remote_api"]["exposure_mode"] = exposure_mode
        status_holder["status"] = RemoteApiRuntimeStatus(
            enabled=enabled,
            service_state="running",
            exposure_mode=exposure_mode,
            effective_bind_host="100.88.127.119",
            port=8788,
            local_access_url=None,
            remote_access_url="http://100.88.127.119:8788/remote/",
            access_urls=("http://100.88.127.119:8788/remote/",),
            failure_message=None,
            user_store_path=Path("remote_api_users.json"),
        )
        return status_holder["status"], "Servicio remoto actualizado."

    def _fake_info(_parent, title: str, text: str) -> None:
        info_box["title"] = title
        info_box["text"] = text

    monkeypatch.setattr(
        "control_okua.app_qt.advanced_tools_dialog.QMessageBox.information",
        _fake_info,
    )

    dialog = AdvancedToolsDialog(
        on_open_folder=lambda: None,
        on_view_config=lambda: None,
        on_reload_config=lambda: None,
        on_apply_remote_settings=_apply_remote_settings,
        on_open_firmware_manager=lambda: None,
        state_provider=lambda: (cfg, Path("config.json"), []),
        remote_status_provider=lambda: status_holder["status"],
    )
    try:
        dialog.set_state(cfg, Path("config.json"), [])
        dialog.remote_enabled_checkbox.setChecked(True)
        dialog.remote_exposure_mode_combo.setCurrentIndex(1)
        dialog._handle_apply_remote_settings_clicked()

        assert captured == {"enabled": True, "exposure_mode": "tailscale_only"}
        assert dialog.remote_remote_url_label.text() == "http://100.88.127.119:8788/remote/"
        assert info_box["title"] == "Servicio remoto"
        assert "actualizado" in info_box["text"].lower()
    finally:
        dialog.close()
