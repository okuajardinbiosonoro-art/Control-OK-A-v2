from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QGroupBox, QSizePolicy, QSplitter, QWidget


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.ota_campaign_dialog import OtaCampaignDialog  # noqa: E402
from control_okua.app_qt.ota_defaults import DEFAULT_APP_OTA_HTTP_PORT  # noqa: E402
from control_okua.core.firmware import (  # noqa: E402
    FirmwareCatalogStore,
    OtaCampaignHealthGate,
    OtaCampaignNodeStatus,
    OtaCampaignResult,
    OtaCampaignStatus,
    OtaCampaignWave,
    OtaCampaignWaveResult,
    build_default_campaign_id,
    build_default_rollout_token,
)


class _SessionControllerStub:
    def __init__(self, snapshots: list[dict] | None = None) -> None:
        self._snapshots = snapshots or []

    def get_node_snapshots(self, now=None):  # pragma: no cover - Qt callback signature
        return self._snapshots


def _ensure_qapp() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_dialog(tmp_path: Path, snapshots: list[dict] | None = None) -> OtaCampaignDialog:
    return OtaCampaignDialog(
        session_controller=_SessionControllerStub(snapshots=snapshots),
        catalog_store=FirmwareCatalogStore(catalog_path=tmp_path / "firmware_catalog.json"),
    )


def _find_group_by_title(dialog: QWidget, title: str) -> QGroupBox | None:
    for group in dialog.findChildren(QGroupBox):
        if group.title() == title:
            return group
    return None


def _rect_in_dialog(widget: QWidget, dialog: QWidget) -> QRect:
    top_left = widget.mapTo(dialog, widget.rect().topLeft())
    return QRect(top_left, widget.size())


def _sample_campaign_result() -> OtaCampaignResult:
    wave = OtaCampaignWave(wave_index=1, label="wave_1", node_ids=(1,), is_canary=False)
    node_status = OtaCampaignNodeStatus(
        node_id=1,
        node_label="Nodo 1",
        wave_index=1,
        wave_label="wave_1",
    )
    return OtaCampaignResult(
        success=True,
        campaign_id=build_default_campaign_id(),
        artifact_id="artifact_demo",
        rollout_token=build_default_rollout_token(),
        rollout_id="rollout_demo",
        rollout_channel="stable",
        node_ids=(1,),
        canary_nodes=(),
        waves=(wave,),
        wave_results=(OtaCampaignWaveResult(wave=wave),),
        node_statuses=(node_status,),
        current_phase="wave_running",
        campaign_status=OtaCampaignStatus.WAVE_RUNNING,
        health_gate=OtaCampaignHealthGate.PENDING,
        continue_allowed=False,
    )


def test_ota_campaign_dialog_builds_expected_sections(tmp_path: Path) -> None:
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))
    dialog = _make_dialog(tmp_path)
    try:
        assert dialog.findChild(QSplitter, "otaCampaignMainSplitter") is not None
        assert dialog.findChild(QWidget, "otaCampaignActionsBar") is not None
        assert dialog.findChild(QGroupBox, "otaCampaignNodesGroup") is not None
        assert dialog.findChild(QGroupBox, "otaCampaignCanaryGroup") is not None
        assert dialog.findChild(QGroupBox, "otaCampaignRolloutGroup") is not None
        assert dialog.findChild(QGroupBox, "otaCampaignResultGroup") is not None
        assert dialog.findChild(QSplitter, "otaCampaignResultSplitter") is not None
        assert _find_group_by_title(dialog, "Firmware") is not None
        assert _find_group_by_title(dialog, "Nodos de campaña") is not None
        assert _find_group_by_title(dialog, "Estrategia de olas") is not None
        assert _find_group_by_title(dialog, "Configuración de red") is not None
        assert _find_group_by_title(dialog, "Estado de campaña") is not None
    finally:
        dialog.close()


def test_ota_campaign_rollout_controls_are_legible_at_base_size(tmp_path: Path) -> None:
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))
    dialog = _make_dialog(tmp_path)
    try:
        dialog.show()
        app.processEvents()
        dialog.resize(1240, 840)
        app.processEvents()

        rollout_group = dialog.findChild(QGroupBox, "otaCampaignRolloutGroup")
        assert rollout_group is not None
        assert rollout_group.height() >= 320

        controls = (
            dialog.advertise_host_edit,
            dialog.bind_host_edit,
            dialog.port_spin,
            dialog.rollout_token_edit,
            dialog.rollout_channel_combo,
            dialog.ack_timeout_spin,
            dialog.max_retries_spin,
        )
        for widget in controls:
            assert widget.width() >= 200, (
                f"{type(widget).__name__} width too small: {widget.width()}px"
            )
            assert widget.height() >= 30, (
                f"{type(widget).__name__} height too small: {widget.height()}px"
            )
            assert (
                widget.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
            )
            rect_in_rollout = QRect(
                widget.mapTo(rollout_group, widget.rect().topLeft()),
                widget.size(),
            )
            assert rollout_group.rect().contains(rect_in_rollout)

        assert dialog.rollout_channel_combo.width() >= 200
        assert dialog.port_spin.width() >= 200
        assert dialog.port_spin.isReadOnly()
        assert dialog.port_spin.minimum() == DEFAULT_APP_OTA_HTTP_PORT
        assert dialog.port_spin.maximum() == DEFAULT_APP_OTA_HTTP_PORT
        assert dialog.port_spin.value() == DEFAULT_APP_OTA_HTTP_PORT
        assert dialog.ack_timeout_spin.width() >= 200
        assert dialog.max_retries_spin.width() >= 200
    finally:
        dialog.close()


def test_ota_campaign_wave_strategy_layout_is_clean_and_usable(tmp_path: Path) -> None:
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))
    dialog = _make_dialog(tmp_path)
    try:
        dialog.show()
        app.processEvents()
        dialog.resize(1240, 840)
        app.processEvents()

        canary_group = dialog.findChild(QGroupBox, "otaCampaignCanaryGroup")
        assert canary_group is not None
        assert dialog.canary_list.height() >= 120
        assert dialog.wave_size_spin.width() >= 110
        assert dialog.wave_size_spin.height() >= 30

        canary_list_rect = dialog.canary_list.geometry()
        wave_spin_rect = dialog.wave_size_spin.geometry()
        assert canary_list_rect.height() > wave_spin_rect.height() * 2
        assert (
            dialog.require_canary_checkbox.sizePolicy().horizontalPolicy()
            == QSizePolicy.Policy.Preferred
        )

        controls = (
            dialog.require_canary_checkbox,
            dialog.canary_list,
            dialog.wave_size_spin,
        )
        for widget in controls:
            rect_in_canary = QRect(
                widget.mapTo(canary_group, widget.rect().topLeft()),
                widget.size(),
            )
            assert canary_group.rect().contains(rect_in_canary)
    finally:
        dialog.close()


def test_ota_campaign_middle_and_bottom_sections_do_not_overlap(tmp_path: Path) -> None:
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))
    dialog = _make_dialog(tmp_path)
    try:
        dialog.show()
        app.processEvents()
        dialog.resize(1600, 900)
        app.processEvents()

        canary_group = dialog.findChild(QGroupBox, "otaCampaignCanaryGroup")
        rollout_group = dialog.findChild(QGroupBox, "otaCampaignRolloutGroup")
        actions_bar = dialog.findChild(QWidget, "otaCampaignActionsBar")
        result_group = dialog.findChild(QGroupBox, "otaCampaignResultGroup")
        assert canary_group is not None
        assert rollout_group is not None
        assert actions_bar is not None
        assert result_group is not None

        canary_rect = _rect_in_dialog(canary_group, dialog)
        rollout_rect = _rect_in_dialog(rollout_group, dialog)
        actions_rect = _rect_in_dialog(actions_bar, dialog)
        result_rect = _rect_in_dialog(result_group, dialog)

        assert not canary_rect.intersects(rollout_rect)
        assert not canary_rect.intersects(actions_rect)
        assert not rollout_rect.intersects(actions_rect)
        assert not actions_rect.intersects(result_rect)
        assert not canary_rect.intersects(result_rect)
        assert not rollout_rect.intersects(result_rect)
    finally:
        dialog.close()


def test_ota_campaign_result_area_prioritizes_table_and_hides_blank_details_initially(
    tmp_path: Path,
) -> None:
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))
    dialog = _make_dialog(tmp_path)
    try:
        dialog.show()
        app.processEvents()
        dialog.resize(1240, 840)
        app.processEvents()

        result_group = dialog.findChild(QGroupBox, "otaCampaignResultGroup")
        result_splitter = dialog.findChild(QSplitter, "otaCampaignResultSplitter")
        assert result_group is not None
        assert result_splitter is not None
        assert result_splitter.count() == 2
        assert result_splitter.widget(0) is dialog.results_table
        assert result_splitter.widget(1) is dialog.details_edit
        assert not dialog.details_edit.isVisible()
        assert dialog.results_table.height() >= 60
        assert result_group.height() >= 160
    finally:
        dialog.close()


def test_ota_campaign_result_splitter_remains_table_dominant_when_details_present(
    tmp_path: Path,
) -> None:
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))
    dialog = _make_dialog(tmp_path)
    try:
        dialog.show()
        app.processEvents()
        dialog.resize(1600, 900)
        app.processEvents()

        dialog._render_result(_sample_campaign_result())
        app.processEvents()

        splitter = dialog.findChild(QSplitter, "otaCampaignResultSplitter")
        assert splitter is not None
        assert dialog.details_edit.isVisible()
        sizes = splitter.sizes()
        assert sizes[0] >= sizes[1], (
            f"Table panel must remain dominant: table={sizes[0]} details={sizes[1]}"
        )
    finally:
        dialog.close()


def test_ota_campaign_layout_stays_balanced_on_wide_window(tmp_path: Path) -> None:
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))
    dialog = _make_dialog(tmp_path)
    try:
        dialog.show()
        app.processEvents()
        dialog.resize(1240, 840)
        app.processEvents()
        base_rollout_width = dialog.rollout_token_edit.width()
        base_canary_list_width = dialog.canary_list.width()

        dialog.resize(1920, 1080)
        app.processEvents()
        assert dialog.rollout_token_edit.width() > base_rollout_width
        assert dialog.canary_list.width() > base_canary_list_width

        canary_group = dialog.findChild(QGroupBox, "otaCampaignCanaryGroup")
        rollout_group = dialog.findChild(QGroupBox, "otaCampaignRolloutGroup")
        firmware_group = _find_group_by_title(dialog, "Firmware")
        assert canary_group is not None
        assert rollout_group is not None
        assert firmware_group is not None
        assert abs(canary_group.width() - rollout_group.width()) <= 24
        assert firmware_group.width() > rollout_group.width() * 0.8
    finally:
        dialog.close()


def test_ota_campaign_layout_remains_usable_on_lower_height_window(tmp_path: Path) -> None:
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))
    dialog = _make_dialog(tmp_path)
    try:
        dialog.show()
        app.processEvents()
        dialog.resize(1300, 720)
        app.processEvents()

        assert dialog.height() >= dialog.minimumHeight()
        assert dialog.canary_list.height() >= 120
        assert dialog.rollout_token_edit.width() >= 200
        assert dialog.rollout_channel_combo.width() >= 200
        assert dialog.results_table.height() >= 60
    finally:
        dialog.close()


def test_ota_campaign_canary_list_supports_few_and_many_nodes(tmp_path: Path) -> None:
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))
    dialog = _make_dialog(tmp_path)
    try:
        dialog.show()
        app.processEvents()
        dialog.resize(1240, 840)
        app.processEvents()

        dialog.canary_list.clear()
        dialog.canary_list.addItem("Nodo 1")
        dialog.canary_list.addItem("Nodo 2")
        app.processEvents()
        assert dialog.canary_list.count() == 2
        assert dialog.canary_list.verticalScrollBar().maximum() == 0
        assert dialog.canary_list.height() >= 120

        dialog.canary_list.clear()
        for index in range(25):
            dialog.canary_list.addItem(f"Nodo {index + 1}")
        app.processEvents()
        assert dialog.canary_list.verticalScrollBar().maximum() > 0
    finally:
        dialog.close()
