from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QAbstractSpinBox
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QGroupBox,
    QSizePolicy,
    QSplitter,
    QWidget,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.ota_campaign_dialog import OtaCampaignDialog  # noqa: E402
from control_okua.app_qt.ota_deploy_dialog import OtaDeployDialog  # noqa: E402
from control_okua.app_qt.ota_defaults import DEFAULT_APP_OTA_HTTP_PORT  # noqa: E402
from control_okua.core.firmware import FirmwareCatalogStore  # noqa: E402


class _SessionControllerStub:
    def get_node_snapshots(self, now=None):
        return []


def _ensure_qapp() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _assert_no_widget_overlap(widgets: tuple) -> None:
    for index, widget in enumerate(widgets):
        for other in widgets[index + 1 :]:
            assert not widget.geometry().intersects(other.geometry())


def _make_deploy_dialog(tmp_path: Path) -> OtaDeployDialog:
    return OtaDeployDialog(
        session_controller=_SessionControllerStub(),
        catalog_store=FirmwareCatalogStore(catalog_path=tmp_path / "firmware_catalog.json"),
    )


def _find_group_by_title(dialog: QWidget, title: str) -> QGroupBox | None:
    for group in dialog.findChildren(QGroupBox):
        if group.title() == title:
            return group
    return None


# ---------------------------------------------------------------------------
# Original responsive-fields test (preserved)
# ---------------------------------------------------------------------------

def test_ota_deploy_rollout_form_uses_responsive_fields(tmp_path: Path) -> None:
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))
    dialog = _make_deploy_dialog(tmp_path)
    try:
        rollout_group = dialog.findChild(QGroupBox, "otaDeployRolloutGroup")
        assert rollout_group is not None
        rollout_layout = rollout_group.layout()
        assert isinstance(rollout_layout, QGridLayout)
        assert rollout_layout.columnStretch(0) == 0
        assert rollout_layout.columnStretch(1) == 1
        assert rollout_layout.horizontalSpacing() >= 12
        assert rollout_layout.verticalSpacing() >= 8

        responsive_fields = (
            dialog.advertise_host_edit,
            dialog.bind_host_edit,
            dialog.port_spin,
            dialog.rollout_token_edit,
            dialog.rollout_channel_combo,
            dialog.ack_timeout_spin,
            dialog.max_retries_spin,
        )
        for widget in responsive_fields:
            assert widget.maximumWidth() > widget.minimumWidth()
            assert (
                widget.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
            )
            assert (
                widget.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Preferred
            )

        assert dialog.port_spin.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons
        assert dialog.port_spin.isReadOnly()
        assert dialog.port_spin.minimum() == DEFAULT_APP_OTA_HTTP_PORT
        assert dialog.port_spin.maximum() == DEFAULT_APP_OTA_HTTP_PORT
        assert dialog.port_spin.value() == DEFAULT_APP_OTA_HTTP_PORT
        assert dialog.ack_timeout_spin.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons
        assert dialog.max_retries_spin.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons

        geometry_fields = responsive_fields + (dialog.allow_downgrade_check,)
        dialog.show()
        app.processEvents()
        dialog.resize(1040, 760)
        app.processEvents()
        for widget in geometry_fields:
            assert widget.height() >= 22
        narrow_width = dialog.rollout_token_edit.width()
        narrow_group_width = rollout_group.width()
        _assert_no_widget_overlap(geometry_fields)

        dialog.resize(1560, 900)
        app.processEvents()
        wide_width = dialog.rollout_token_edit.width()
        wide_group_width = rollout_group.width()
        _assert_no_widget_overlap(geometry_fields)

        assert wide_width > narrow_width
        assert wide_group_width > narrow_group_width
        assert dialog.rollout_channel_combo.width() >= 200
        assert dialog.allow_downgrade_check.width() >= 200

        group_rect = rollout_group.rect()
        for widget in geometry_fields:
            top_left = widget.mapTo(rollout_group, widget.rect().topLeft())
            rect_in_group = QRect(top_left, widget.size())
            assert group_rect.contains(rect_in_group)
    finally:
        dialog.close()


# ---------------------------------------------------------------------------
# New comprehensive layout tests
# ---------------------------------------------------------------------------

def test_ota_deploy_dialog_sections_present(tmp_path: Path) -> None:
    """Dialog constructs all expected named sections."""
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))
    dialog = _make_deploy_dialog(tmp_path)
    try:
        assert dialog.findChild(QGroupBox, "otaDeployRolloutGroup") is not None
        assert dialog.findChild(QGroupBox, "otaDeployResultGroup") is not None
        assert dialog.findChild(QSplitter, "otaMainSplitter") is not None
        assert dialog.findChild(QSplitter, "otaResultSplitter") is not None
        assert dialog.results_table is not None
        assert dialog.details_edit is not None
        assert dialog.deploy_button is not None
        assert dialog.refresh_status_button is not None
        assert dialog.open_rollout_button is not None
    finally:
        dialog.close()


def test_ota_deploy_nodes_group_layout_is_legible_at_base_size(tmp_path: Path) -> None:
    """Nodes card must keep list/button/hint separated with useful list height."""
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))
    dialog = _make_deploy_dialog(tmp_path)
    try:
        dialog.show()
        app.processEvents()
        dialog.resize(1120, 760)
        app.processEvents()

        nodes_group = dialog.findChild(QGroupBox, "otaDeployNodesGroup")
        firmware_group = _find_group_by_title(dialog, "Firmware")
        assert nodes_group is not None
        assert firmware_group is not None
        assert dialog.nodes_list.objectName() == "otaDeployNodesList"
        assert dialog.reload_nodes_button.objectName() == "otaDeployReloadNodesButton"
        assert dialog.nodes_hint_label.objectName() == "otaDeployNodesHintLabel"

        assert nodes_group.height() >= 200, (
            f"nodes_group should not be collapsed: {nodes_group.height()}px"
        )
        assert dialog.nodes_list.height() >= 60, (
            f"nodes_list should keep useful height: {dialog.nodes_list.height()}px"
        )
        assert (
            dialog.nodes_list.sizePolicy().verticalPolicy()
            == QSizePolicy.Policy.Expanding
        )

        nodes_list_rect = dialog.nodes_list.geometry()
        button_rect = dialog.reload_nodes_button.geometry()
        hint_rect = dialog.nodes_hint_label.geometry()
        gap_list_button = button_rect.top() - nodes_list_rect.bottom()
        gap_button_hint = hint_rect.top() - button_rect.bottom()
        assert gap_list_button >= 4, f"List/button gap too small: {gap_list_button}px"
        assert gap_button_hint >= 4, f"Button/hint gap too small: {gap_button_hint}px"

        group_rect = nodes_group.rect()
        for widget in (dialog.nodes_list, dialog.reload_nodes_button, dialog.nodes_hint_label):
            top_left = widget.mapTo(nodes_group, widget.rect().topLeft())
            rect_in_group = QRect(top_left, widget.size())
            assert group_rect.contains(rect_in_group), (
                f"{type(widget).__name__} overflows nodes_group.\n"
                f"  Widget: {rect_in_group}\n"
                f"  Group:  {group_rect}"
            )

        assert abs(nodes_group.height() - firmware_group.height()) <= 1, (
            "Nodes and Firmware cards must stay visually balanced in row 0 "
            f"({nodes_group.height()}px vs {firmware_group.height()}px)."
        )
    finally:
        dialog.close()


def test_ota_deploy_nodes_group_is_stable_when_dialog_gets_wider(tmp_path: Path) -> None:
    """Nodes card should scale in width while preserving readable internals."""
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))
    dialog = _make_deploy_dialog(tmp_path)
    try:
        dialog.show()
        app.processEvents()
        dialog.resize(1120, 760)
        app.processEvents()

        nodes_group = dialog.findChild(QGroupBox, "otaDeployNodesGroup")
        firmware_group = _find_group_by_title(dialog, "Firmware")
        assert nodes_group is not None
        assert firmware_group is not None

        base_nodes_group_width = nodes_group.width()
        base_nodes_list_width = dialog.nodes_list.width()
        base_nodes_list_height = dialog.nodes_list.height()

        dialog.resize(1920, 1080)
        app.processEvents()

        assert nodes_group.width() > base_nodes_group_width
        assert dialog.nodes_list.width() > base_nodes_list_width
        assert dialog.nodes_list.height() >= base_nodes_list_height

        top_row_width = firmware_group.width() + nodes_group.width()
        assert nodes_group.width() >= int(top_row_width * 0.30), (
            f"Nodes card should not look strangled at wide size. "
            f"nodes={nodes_group.width()} top_row={top_row_width}"
        )
        assert dialog.artifact_combo.width() >= 280, (
            f"Firmware combo became too narrow: {dialog.artifact_combo.width()}px"
        )
    finally:
        dialog.close()


def test_ota_deploy_nodes_list_handles_few_and_many_rows(tmp_path: Path) -> None:
    """Nodes list keeps readability with few rows and uses scrollbar with many rows."""
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))
    dialog = _make_deploy_dialog(tmp_path)
    try:
        dialog.show()
        app.processEvents()
        dialog.resize(1120, 760)
        app.processEvents()

        dialog.nodes_list.clear()
        dialog.nodes_list.addItem("Nodo 1")
        dialog.nodes_list.addItem("Nodo 2")
        app.processEvents()

        assert dialog.nodes_list.count() == 2
        assert dialog.nodes_list.height() >= 60
        assert dialog.nodes_list.verticalScrollBar().maximum() == 0
        row_height = dialog.nodes_list.sizeHintForRow(0)
        if row_height > 0:
            assert dialog.nodes_list.viewport().height() >= row_height * 2

        dialog.nodes_list.clear()
        for index in range(25):
            dialog.nodes_list.addItem(f"Nodo {index + 1}")
        app.processEvents()
        assert dialog.nodes_list.verticalScrollBar().maximum() > 0
    finally:
        dialog.close()


def test_ota_deploy_details_panel_hidden_before_deployment(tmp_path: Path) -> None:
    """Before any deployment the details panel must not occupy visible space."""
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))
    dialog = _make_deploy_dialog(tmp_path)
    try:
        dialog.show()
        app.processEvents()
        dialog.resize(1120, 760)
        app.processEvents()
        assert not dialog.details_edit.isVisible(), (
            "details_edit should be hidden before the first deployment"
        )
    finally:
        dialog.close()


def test_ota_deploy_table_has_dominant_height_before_deployment(tmp_path: Path) -> None:
    """The results table must occupy the vast majority of the results area."""
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))
    dialog = _make_deploy_dialog(tmp_path)
    try:
        dialog.show()
        app.processEvents()
        dialog.resize(1120, 760)
        app.processEvents()

        result_group = dialog.findChild(QGroupBox, "otaDeployResultGroup")
        assert result_group is not None
        assert result_group.height() >= 40, (
            f"result_group is too short: {result_group.height()}px"
        )
        assert dialog.results_table.height() >= 20, (
            f"results_table height too small: {dialog.results_table.height()}px"
        )
    finally:
        dialog.close()


def _splitter_children_non_overlapping(splitter: QSplitter, dialog: QWidget) -> None:
    """Assert that adjacent children of a splitter do not overlap in dialog coords."""
    prev_rect: QRect | None = None
    for i in range(splitter.count()):
        child = splitter.widget(i)
        if not child.isVisible():
            continue
        tl = child.mapTo(dialog, child.rect().topLeft())
        rect = QRect(tl, child.size())
        if prev_rect is not None:
            assert not prev_rect.intersects(rect), (
                f"Splitter child {i-1} overlaps child {i}: {prev_rect} / {rect}"
            )
        prev_rect = rect


def test_ota_deploy_no_section_overlap_base_size(tmp_path: Path) -> None:
    """At 1120x760 the main splitter children must not overlap."""
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))
    dialog = _make_deploy_dialog(tmp_path)
    try:
        dialog.show()
        app.processEvents()
        dialog.resize(1120, 760)
        app.processEvents()

        main_splitter = dialog.findChild(QSplitter, "otaMainSplitter")
        assert main_splitter is not None
        _splitter_children_non_overlapping(main_splitter, dialog)

        # Rollout group must be fully inside the config pane (splitter child 0).
        rollout_group = dialog.findChild(QGroupBox, "otaDeployRolloutGroup")
        config_pane = main_splitter.widget(0)
        rollout_tl = rollout_group.mapTo(dialog, rollout_group.rect().topLeft())
        rollout_rect = QRect(rollout_tl, rollout_group.size())
        config_tl = config_pane.mapTo(dialog, config_pane.rect().topLeft())
        config_rect = QRect(config_tl, config_pane.size())
        assert config_rect.contains(rollout_rect), (
            f"Rollout group overflows config pane at 1120x760.\n"
            f"  Rollout: {rollout_rect}\n"
            f"  Config pane: {config_rect}"
        )
    finally:
        dialog.close()


def test_ota_deploy_no_section_overlap_wide_size(tmp_path: Path) -> None:
    """At 1920x1080 the main splitter children must not overlap."""
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))
    dialog = _make_deploy_dialog(tmp_path)
    try:
        dialog.show()
        app.processEvents()
        dialog.resize(1920, 1080)
        app.processEvents()

        main_splitter = dialog.findChild(QSplitter, "otaMainSplitter")
        assert main_splitter is not None
        _splitter_children_non_overlapping(main_splitter, dialog)
    finally:
        dialog.close()


def test_ota_deploy_no_section_overlap_compact_size(tmp_path: Path) -> None:
    """At 1366x768 the main splitter children must not overlap."""
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))
    dialog = _make_deploy_dialog(tmp_path)
    try:
        dialog.show()
        app.processEvents()
        dialog.resize(1366, 768)
        app.processEvents()

        main_splitter = dialog.findChild(QSplitter, "otaMainSplitter")
        assert main_splitter is not None
        _splitter_children_non_overlapping(main_splitter, dialog)
    finally:
        dialog.close()


def test_ota_deploy_result_splitter_proportions(tmp_path: Path) -> None:
    """The result splitter must exist with the table panel dominant over details."""
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))
    dialog = _make_deploy_dialog(tmp_path)
    try:
        splitter = dialog.findChild(QSplitter, "otaResultSplitter")
        assert splitter is not None
        assert splitter.count() == 2
        assert splitter.widget(0) is dialog.results_table
        assert splitter.widget(1) is dialog.details_edit

        dialog.show()
        app.processEvents()
        dialog.resize(1120, 760)
        app.processEvents()

        # When both panels are visible, table must receive more (or equal) height.
        total = splitter.height()
        if total > 0:
            table_h = max(80, int(total * 0.75))
            details_h = max(60, total - table_h)
            splitter.setSizes([table_h, details_h])
        dialog.details_edit.setVisible(True)
        app.processEvents()

        sizes = splitter.sizes()
        assert sizes[0] >= sizes[1], (
            f"Table panel ({sizes[0]}px) must be >= details panel ({sizes[1]}px)"
        )
    finally:
        dialog.close()


def test_ota_deploy_rollout_group_policy_is_minimum_expanding(tmp_path: Path) -> None:
    """The rollout group must use MinimumExpanding vertical policy."""
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))
    dialog = _make_deploy_dialog(tmp_path)
    try:
        rollout_group = dialog.findChild(QGroupBox, "otaDeployRolloutGroup")
        assert rollout_group is not None
        assert (
            rollout_group.sizePolicy().verticalPolicy()
            == QSizePolicy.Policy.MinimumExpanding
        )
    finally:
        dialog.close()


def test_ota_deploy_rollout_group_all_rows_visible_base_size(tmp_path: Path) -> None:
    """All form rows must be fully contained within the rollout group at 1120x760."""
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))
    dialog = _make_deploy_dialog(tmp_path)
    try:
        dialog.show()
        app.processEvents()
        dialog.resize(1120, 760)
        app.processEvents()

        rollout_group = dialog.findChild(QGroupBox, "otaDeployRolloutGroup")
        assert rollout_group is not None
        group_rect = rollout_group.rect()

        fields = (
            dialog.advertise_host_edit,
            dialog.bind_host_edit,
            dialog.port_spin,
            dialog.rollout_token_edit,
            dialog.rollout_channel_combo,
            dialog.ack_timeout_spin,
            dialog.max_retries_spin,
            dialog.allow_downgrade_check,
        )
        for widget in fields:
            top_left = widget.mapTo(rollout_group, widget.rect().topLeft())
            rect_in_group = QRect(top_left, widget.size())
            assert group_rect.contains(rect_in_group), (
                f"Widget {widget.objectName() or type(widget).__name__} is outside "
                f"the rollout group.\n"
                f"  Widget in group coords: {rect_in_group}\n"
                f"  Group rect:             {group_rect}"
            )
    finally:
        dialog.close()


def test_ota_deploy_main_splitter_structure(tmp_path: Path) -> None:
    """The main splitter must have config pane as child 0 and result group as child 1."""
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))
    dialog = _make_deploy_dialog(tmp_path)
    try:
        main_splitter = dialog.findChild(QSplitter, "otaMainSplitter")
        assert main_splitter is not None
        assert main_splitter.count() == 2
        config_pane = main_splitter.widget(0)
        result_pane = main_splitter.widget(1)
        assert config_pane is not None
        assert result_pane is not None
        # The rollout group must be a descendant of the config pane (child 0).
        rollout_group = dialog.findChild(QGroupBox, "otaDeployRolloutGroup")
        assert rollout_group is not None
        parent = rollout_group.parent()
        found_config_pane = False
        while parent is not None:
            if parent is config_pane:
                found_config_pane = True
                break
            parent = parent.parent()
        assert found_config_pane, "rollout_group must be a descendant of the config pane"
        # The result group must be the second child of the main splitter.
        result_group = dialog.findChild(QGroupBox, "otaDeployResultGroup")
        assert result_group is result_pane, (
            "result group must be the second direct child of the main splitter"
        )
    finally:
        dialog.close()


# ---------------------------------------------------------------------------
# Original campaign dialog test (preserved)
# ---------------------------------------------------------------------------

def test_ota_campaign_rollout_and_canary_forms_scale_with_dialog_width(tmp_path: Path) -> None:
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))
    dialog = OtaCampaignDialog(
        session_controller=_SessionControllerStub(),
        catalog_store=FirmwareCatalogStore(catalog_path=tmp_path / "firmware_catalog.json"),
    )
    try:
        rollout_group = dialog.findChild(QGroupBox, "otaCampaignRolloutGroup")
        canary_group = dialog.findChild(QGroupBox, "otaCampaignCanaryGroup")
        result_group = dialog.findChild(QGroupBox, "otaCampaignResultGroup")
        main_splitter = dialog.findChild(QSplitter, "otaCampaignMainSplitter")
        assert rollout_group is not None
        assert canary_group is not None
        assert result_group is not None
        assert main_splitter is not None
        assert isinstance(rollout_group.layout(), QGridLayout)

        responsive_fields = (
            dialog.require_canary_checkbox,
            dialog.wave_size_spin,
            dialog.advertise_host_edit,
            dialog.bind_host_edit,
            dialog.port_spin,
            dialog.rollout_token_edit,
            dialog.rollout_channel_combo,
            dialog.ack_timeout_spin,
            dialog.max_retries_spin,
        )
        for widget in responsive_fields:
            assert widget.maximumWidth() > widget.minimumWidth()
            assert widget.sizePolicy().horizontalPolicy() in {
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            }

        dialog.show()
        app.processEvents()
        dialog.resize(980, 760)
        app.processEvents()
        narrow_token = dialog.rollout_token_edit.width()
        narrow_canary_list = dialog.canary_list.width()

        dialog.resize(1600, 980)
        app.processEvents()
        wide_token = dialog.rollout_token_edit.width()
        wide_canary_list = dialog.canary_list.width()

        assert wide_token >= dialog.rollout_token_edit.minimumWidth()
        assert narrow_token >= dialog.rollout_token_edit.minimumWidth()
        assert wide_canary_list >= narrow_canary_list
        assert wide_token != narrow_token or wide_canary_list != narrow_canary_list
        assert not dialog.details_edit.isVisible()
        assert dialog.results_table.height() >= 40
    finally:
        dialog.close()
