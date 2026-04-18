from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QAbstractItemView,
    QComboBox,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from control_okua.app_qt.viewmodels.ota_campaign_vm import (
    build_ota_campaign_artifact_options,
    build_ota_campaign_continue_hint,
    build_ota_campaign_node_options,
    build_ota_campaign_node_rows,
    build_ota_campaign_result_details,
    build_ota_campaign_result_summary,
    build_ota_campaign_wave_preview,
)
from control_okua.app_qt.ota_defaults import DEFAULT_APP_OTA_HTTP_PORT
from control_okua.core.firmware import (
    FirmwareCatalogStore,
    OtaCampaignStatus,
    OtaCampaignPlan,
    OtaCampaignResult,
    OtaCampaignValidationError,
    OtaManifestService,
    build_campaign_waves,
    build_default_rollout_token,
)
from control_okua.services.ota_campaign_service import (
    OtaCampaignService,
    OtaCampaignServiceError,
)
from control_okua.services.ota_orchestrator_service import OtaOrchestratorService

if TYPE_CHECKING:
    from control_okua.services.session_controller import SessionController


class OtaCampaignDialog(QDialog):
    _REFRESH_INTERVAL_MS = 2000

    def __init__(
        self,
        *,
        session_controller: "SessionController",
        catalog_store: FirmwareCatalogStore | None = None,
        orchestrator_service: OtaOrchestratorService | None = None,
        campaign_service: OtaCampaignService | None = None,
        preselected_artifact_id: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("otaCampaignDialog")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("Campaña OTA")
        self.resize(1240, 840)

        self._session_controller = session_controller
        self._catalog_store = catalog_store or FirmwareCatalogStore()
        self._orchestrator = orchestrator_service or OtaOrchestratorService(
            runtime_client=session_controller,
            manifest_service=OtaManifestService(self._catalog_store),
        )
        self._campaign_service = campaign_service or OtaCampaignService(
            orchestrator_service=self._orchestrator
        )
        self._artifact_options = []
        self._node_options = []
        self._last_result: OtaCampaignResult | None = None
        self._preselected_artifact_id = preselected_artifact_id

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(self._REFRESH_INTERVAL_MS)
        self._refresh_timer.timeout.connect(self._on_refresh_clicked)

        self._build_ui()
        self.reload_artifacts()
        self.reload_nodes()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._refresh_timer.stop()
        super().closeEvent(event)

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(8)

        intro = QLabel(
            "Actualización por olas con validación previa. "
            "Publica el firmware y avanza ola a ola, pausando o cancelando si es necesario."
        )
        intro.setWordWrap(True)
        root_layout.addWidget(intro)

        self._main_splitter = QSplitter(Qt.Orientation.Vertical, self)
        self._main_splitter.setObjectName("otaCampaignMainSplitter")
        self._main_splitter.setChildrenCollapsible(False)

        config_pane = QWidget(self)
        config_pane.setObjectName("otaCampaignConfigPane")
        config_pane_layout = QVBoxLayout(config_pane)
        config_pane_layout.setContentsMargins(0, 0, 0, 0)
        config_pane_layout.setSpacing(10)

        config_grid = QGridLayout()
        config_grid.setHorizontalSpacing(14)
        config_grid.setVerticalSpacing(14)
        config_grid.setColumnStretch(0, 1)
        config_grid.setColumnStretch(1, 1)
        artifact_group = self._build_artifact_group()
        nodes_group = self._build_campaign_nodes_group()
        _TOP_ROW_MAX_HEIGHT = 220
        artifact_group.setMaximumHeight(_TOP_ROW_MAX_HEIGHT)
        nodes_group.setMaximumHeight(_TOP_ROW_MAX_HEIGHT)
        config_grid.addWidget(artifact_group, 0, 0)
        config_grid.addWidget(nodes_group, 0, 1)
        config_grid.addWidget(self._build_canary_group(), 1, 0)
        config_grid.addWidget(self._build_rollout_group(), 1, 1)
        config_pane_layout.addLayout(config_grid)

        self.wave_preview_label = QLabel(
            "Configura los nodos para ver la distribución de olas.",
            self,
        )
        self.wave_preview_label.setWordWrap(True)
        config_pane_layout.addWidget(self.wave_preview_label)
        config_pane_layout.addWidget(self._build_actions_bar())

        self._main_splitter.addWidget(config_pane)
        self._main_splitter.addWidget(self._build_result_group())
        self._main_splitter.setStretchFactor(0, 0)
        self._main_splitter.setStretchFactor(1, 1)

        root_layout.addWidget(self._main_splitter, 1)
        self._update_action_state()

    def _build_actions_bar(self) -> QWidget:
        actions_host = QWidget(self)
        actions_host.setObjectName("otaCampaignActionsBar")
        actions_layout = QHBoxLayout()
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)
        actions_host.setLayout(actions_layout)

        self.start_canary_button = QPushButton("Iniciar primera ola", self)
        self.start_canary_button.clicked.connect(self._on_start_canary_clicked)
        actions_layout.addWidget(self.start_canary_button)

        self.continue_button = QPushButton("Continuar siguiente ola", self)
        self.continue_button.clicked.connect(self._on_continue_clicked)
        self.continue_button.setEnabled(False)
        actions_layout.addWidget(self.continue_button)

        self.pause_button = QPushButton("Pausar", self)
        self.pause_button.clicked.connect(self._on_pause_clicked)
        self.pause_button.setEnabled(False)
        actions_layout.addWidget(self.pause_button)

        self.abort_button = QPushButton("Abortar", self)
        self.abort_button.clicked.connect(self._on_abort_clicked)
        self.abort_button.setEnabled(False)
        actions_layout.addWidget(self.abort_button)

        self.refresh_button = QPushButton("Actualizar estado", self)
        self.refresh_button.clicked.connect(self._on_refresh_clicked)
        self.refresh_button.setEnabled(False)
        actions_layout.addWidget(self.refresh_button)

        self.open_rollout_button = QPushButton("Abrir carpeta", self)
        self.open_rollout_button.clicked.connect(self._open_rollout_folder)
        self.open_rollout_button.setEnabled(False)
        actions_layout.addWidget(self.open_rollout_button)
        actions_layout.addStretch(1)
        return actions_host

    def _build_result_group(self) -> QGroupBox:
        result_group = QGroupBox("Estado de campaña", self)
        result_group.setObjectName("otaCampaignResultGroup")
        result_layout = QVBoxLayout(result_group)
        result_layout.setSpacing(8)

        self.summary_label = QLabel("Aún no hay campaña OTA en curso.", self)
        self.summary_label.setWordWrap(True)
        result_layout.addWidget(self.summary_label)

        self.continue_hint_label = QLabel(
            "Configura la campaña y selecciona nodos para comenzar.",
            self,
        )
        self.continue_hint_label.setWordWrap(True)
        result_layout.addWidget(self.continue_hint_label)

        self._result_splitter = QSplitter(Qt.Orientation.Vertical, result_group)
        self._result_splitter.setObjectName("otaCampaignResultSplitter")
        self._result_splitter.setChildrenCollapsible(False)

        self.results_table = QTableWidget(0, 8, self)
        self.results_table.setHorizontalHeaderLabels(
            [
                "Nodo",
                "Ola",
                "Fase OTA",
                "Resultado",
                "Respuesta",
                "Estado OTA",
                "Mensaje",
                "Observado UTC",
            ]
        )
        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._result_splitter.addWidget(self.results_table)

        self.details_edit = QTextEdit(self)
        self.details_edit.setReadOnly(True)
        self.details_edit.setObjectName("otaCampaignDetails")
        self.details_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.details_edit.setVisible(False)
        self._result_splitter.addWidget(self.details_edit)
        self._result_splitter.setStretchFactor(0, 4)
        self._result_splitter.setStretchFactor(1, 1)
        result_layout.addWidget(self._result_splitter, 1)
        return result_group

    @staticmethod
    def _set_responsive_field(
        widget: QWidget,
        *,
        min_width: int,
        max_width: int | None = None,
    ) -> None:
        widget.setMinimumWidth(min_width)
        if max_width is not None:
            widget.setMaximumWidth(max_width)
        widget.setMinimumHeight(max(widget.sizeHint().height(), 30))
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def _build_artifact_group(self) -> QWidget:
        group = QGroupBox("Firmware", self)
        layout = QVBoxLayout(group)

        combo_row = QHBoxLayout()
        self.artifact_combo = QComboBox(self)
        self.artifact_combo.currentIndexChanged.connect(self._on_artifact_changed)
        combo_row.addWidget(self.artifact_combo, 1)

        self.reload_artifacts_button = QPushButton("Recargar firmware", self)
        self.reload_artifacts_button.clicked.connect(self.reload_artifacts)
        combo_row.addWidget(self.reload_artifacts_button)
        layout.addLayout(combo_row)

        self.artifact_summary_label = QLabel("Sin firmware seleccionado.", self)
        self.artifact_summary_label.setWordWrap(True)
        layout.addWidget(self.artifact_summary_label)
        return group

    def _build_campaign_nodes_group(self) -> QWidget:
        group = QGroupBox("Nodos de campaña", self)
        group.setObjectName("otaCampaignNodesGroup")
        group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.nodes_list = QListWidget(self)
        self.nodes_list.setObjectName("otaCampaignNodesList")
        self.nodes_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.nodes_list.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        min_row_height = max(self.fontMetrics().lineSpacing() + 6, 20)
        self.nodes_list.setMinimumHeight(min_row_height * 3)
        self.nodes_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.nodes_list.itemSelectionChanged.connect(self._on_nodes_selection_changed)
        layout.addWidget(self.nodes_list, 1)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        self.reload_nodes_button = QPushButton("Recargar nodos", self)
        self.reload_nodes_button.setObjectName("otaCampaignReloadNodesButton")
        self.reload_nodes_button.clicked.connect(self.reload_nodes)
        actions.addWidget(self.reload_nodes_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.nodes_hint_label = QLabel(
            "Selecciona los nodos que participarán en la campaña.",
            self,
        )
        self.nodes_hint_label.setObjectName("otaCampaignNodesHint")
        self.nodes_hint_label.setWordWrap(True)
        self.nodes_hint_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self.nodes_hint_label)
        return group

    def _build_canary_group(self) -> QWidget:
        group = QGroupBox("Estrategia de olas", self)
        group.setObjectName("otaCampaignCanaryGroup")
        group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 0, 0, 0)
        toggle_row.setSpacing(10)
        toggle_label = QLabel("Validación previa:", group)
        toggle_label.setMinimumWidth(
            max(self.fontMetrics().horizontalAdvance("Validación previa:"), 120)
        )
        toggle_row.addWidget(toggle_label)

        self.require_canary_checkbox = QPushButton("Validación previa: Activada", self)
        self.require_canary_checkbox.setCheckable(True)
        self.require_canary_checkbox.setChecked(True)
        self.require_canary_checkbox.setMinimumWidth(220)
        self.require_canary_checkbox.setMinimumHeight(
            max(self.require_canary_checkbox.sizeHint().height(), 30)
        )
        self.require_canary_checkbox.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )
        self.require_canary_checkbox.toggled.connect(self._on_require_canary_toggled)
        toggle_row.addWidget(self.require_canary_checkbox)
        toggle_row.addStretch(1)
        layout.addLayout(toggle_row)

        canary_label = QLabel("Nodos de prueba:", group)
        canary_label.setObjectName("otaCampaignCanaryNodesLabel")
        layout.addWidget(canary_label)

        self.canary_list = QListWidget(self)
        self.canary_list.setObjectName("otaCampaignCanaryList")
        self.canary_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.canary_list.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        min_row_height = max(self.fontMetrics().lineSpacing() + 6, 20)
        self.canary_list.setMinimumHeight(min_row_height * 4)
        self.canary_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.canary_list.itemSelectionChanged.connect(self._update_wave_preview)
        layout.addWidget(self.canary_list, 1)

        wave_row = QHBoxLayout()
        wave_row.setContentsMargins(0, 0, 0, 0)
        wave_row.setSpacing(10)
        wave_size_label = QLabel("Nodos por ola:", group)
        wave_size_label.setMinimumWidth(
            max(self.fontMetrics().horizontalAdvance("Nodos por ola:"), 120)
        )
        wave_row.addWidget(wave_size_label)

        self.wave_size_spin = QSpinBox(self)
        self.wave_size_spin.setRange(1, 64)
        self.wave_size_spin.setValue(1)
        self.wave_size_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._set_responsive_field(self.wave_size_spin, min_width=120, max_width=180)
        self.wave_size_spin.valueChanged.connect(self._update_wave_preview)
        wave_row.addWidget(self.wave_size_spin)
        wave_row.addStretch(1)
        layout.addLayout(wave_row)

        self.canary_list.setEnabled(self.require_canary_checkbox.isChecked())
        return group

    def _build_rollout_group(self) -> QWidget:
        group = QGroupBox("Configuración de red", self)
        group.setObjectName("otaCampaignRolloutGroup")
        group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)

        layout = QGridLayout(group)
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(8)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        self.advertise_host_edit = QLineEdit("127.0.0.1", group)
        self._set_responsive_field(self.advertise_host_edit, min_width=200)

        self.bind_host_edit = QLineEdit("0.0.0.0", group)
        self._set_responsive_field(self.bind_host_edit, min_width=200)

        self.port_spin = QSpinBox(group)
        self.port_spin.setRange(
            DEFAULT_APP_OTA_HTTP_PORT,
            DEFAULT_APP_OTA_HTTP_PORT,
        )
        self.port_spin.setValue(DEFAULT_APP_OTA_HTTP_PORT)
        self.port_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.port_spin.setReadOnly(True)
        self.port_spin.setToolTip(
            f"Puerto OTA fijo de la app. Debe coincidir con el firmware del nodo "
            f"({DEFAULT_APP_OTA_HTTP_PORT})."
        )
        self._set_responsive_field(self.port_spin, min_width=200)

        self.rollout_token_edit = QLineEdit(build_default_rollout_token(), group)
        self._set_responsive_field(self.rollout_token_edit, min_width=200)

        self.rollout_channel_combo = QComboBox(group)
        self._set_responsive_field(self.rollout_channel_combo, min_width=200)
        self.rollout_channel_combo.addItem("Estable", "stable")
        self.rollout_channel_combo.addItem("Beta", "beta")
        self.rollout_channel_combo.addItem("Situacional", "situational")

        self.ack_timeout_spin = QSpinBox(group)
        self.ack_timeout_spin.setRange(100, 10000)
        self.ack_timeout_spin.setValue(600)
        self.ack_timeout_spin.setSuffix(" ms")
        self.ack_timeout_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._set_responsive_field(self.ack_timeout_spin, min_width=200)

        self.max_retries_spin = QSpinBox(group)
        self.max_retries_spin.setRange(0, 3)
        self.max_retries_spin.setValue(0)
        self.max_retries_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._set_responsive_field(self.max_retries_spin, min_width=200)

        row_specs = [
            ("IP accesible por el nodo:", self.advertise_host_edit),
            ("Dirección local:", self.bind_host_edit),
            ("Puerto OTA fijo:", self.port_spin),
            ("Token de actualización:", self.rollout_token_edit),
            ("Canal:", self.rollout_channel_combo),
            ("Tiempo de respuesta:", self.ack_timeout_spin),
            ("Reintentos:", self.max_retries_spin),
        ]
        label_width = (
            max(self.fontMetrics().horizontalAdvance(text) for text, _ in row_specs) + 12
        )
        label_row_min = max(self.fontMetrics().height() + 4, 22)
        row_min_heights: list[int] = []
        for row_index, (text, field_widget) in enumerate(row_specs):
            label = QLabel(text, group)
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            label.setMinimumWidth(label_width)
            label.setMinimumHeight(label_row_min)
            layout.addWidget(
                label,
                row_index,
                0,
                1,
                1,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            )
            layout.addWidget(field_widget, row_index, 1, 1, 1)
            row_height = max(field_widget.minimumHeight(), label_row_min)
            layout.setRowMinimumHeight(row_index, row_height)
            row_min_heights.append(row_height)

        num_rows = len(row_min_heights)
        content_min_h = sum(row_min_heights) + (num_rows - 1) * layout.verticalSpacing()
        _HEADER_V = 64
        group.setMinimumHeight(content_min_h + _HEADER_V)
        return group

    def reload_artifacts(self) -> None:
        catalog = self._catalog_store.load()
        self._artifact_options = build_ota_campaign_artifact_options(catalog.artifacts)
        previous_artifact_id = self.artifact_combo.currentData()

        self.artifact_combo.blockSignals(True)
        self.artifact_combo.clear()
        for option in self._artifact_options:
            label = option.label
            if not option.is_eligible:
                label = f"{label} [no elegible]"
            self.artifact_combo.addItem(label, option.artifact_id)
        self.artifact_combo.blockSignals(False)

        selected_artifact_id = (
            self._preselected_artifact_id
            or previous_artifact_id
            or (self._artifact_options[0].artifact_id if self._artifact_options else None)
        )
        self._preselected_artifact_id = None
        if selected_artifact_id is not None:
            index = self.artifact_combo.findData(selected_artifact_id)
            if index >= 0:
                self.artifact_combo.setCurrentIndex(index)
        self._on_artifact_changed()

    def reload_nodes(self) -> None:
        snapshots = self._session_controller.get_node_snapshots(now=time.monotonic())
        self._node_options = build_ota_campaign_node_options(snapshots)
        selected_campaign_ids = set(self.selected_campaign_node_ids())
        selected_canary_ids = set(self.selected_canary_node_ids())

        self.nodes_list.clear()
        self.canary_list.clear()
        for option in self._node_options:
            item = QListWidgetItem(option.label, self.nodes_list)
            item.setData(Qt.UserRole, option.node_id)
            item.setToolTip(option.summary)
            if option.node_id in selected_campaign_ids:
                item.setSelected(True)

            canary_item = QListWidgetItem(option.label, self.canary_list)
            canary_item.setData(Qt.UserRole, option.node_id)
            canary_item.setToolTip(option.summary)
            if option.node_id in selected_canary_ids:
                canary_item.setSelected(True)

        if self._node_options:
            self.nodes_hint_label.setText(
                f"Nodos disponibles: {len(self._node_options)}. "
                "Selecciona el conjunto total y luego los nodos de prueba."
            )
        else:
            self.nodes_hint_label.setText(
                "No hay nodos conectados. "
                "Inicia una sesión UDP antes de continuar."
            )
        self._sync_canary_selection()
        self._update_wave_preview()
        self._update_action_state()

    def selected_campaign_node_ids(self) -> tuple[int, ...]:
        return self._selected_node_ids_from(self.nodes_list)

    def selected_canary_node_ids(self) -> tuple[int, ...]:
        return self._selected_node_ids_from(self.canary_list)

    def _selected_node_ids_from(self, widget: QListWidget) -> tuple[int, ...]:
        node_ids: list[int] = []
        for item in widget.selectedItems():
            raw_node_id = item.data(Qt.UserRole)
            try:
                node_ids.append(int(raw_node_id))
            except (TypeError, ValueError):
                continue
        return tuple(node_ids)

    def _selected_artifact_option(self):
        artifact_id = self.artifact_combo.currentData()
        for option in self._artifact_options:
            if option.artifact_id == artifact_id:
                return option
        return None

    def _on_artifact_changed(self) -> None:
        option = self._selected_artifact_option()
        if option is None:
            self.artifact_summary_label.setText("Sin firmware seleccionado.")
            self._update_action_state()
            return
        self.artifact_summary_label.setText(option.summary)
        self._update_action_state()

    def _on_require_canary_toggled(self, checked: bool) -> None:
        self.require_canary_checkbox.setText(
            "Validación previa: Activada" if checked else "Validación previa: Desactivada"
        )
        self.canary_list.setEnabled(checked)
        self._update_wave_preview()
        self._update_action_state()

    def _on_nodes_selection_changed(self) -> None:
        self._sync_canary_selection()
        self._update_wave_preview()
        self._update_action_state()

    def _sync_canary_selection(self) -> None:
        allowed_node_ids = set(self.selected_campaign_node_ids())
        for index in range(self.canary_list.count()):
            item = self.canary_list.item(index)
            node_id = int(item.data(Qt.UserRole))
            if node_id not in allowed_node_ids and item.isSelected():
                item.setSelected(False)
            item.setHidden(node_id not in allowed_node_ids and bool(allowed_node_ids))

    def _build_plan_from_ui(self) -> OtaCampaignPlan:
        option = self._selected_artifact_option()
        if option is None:
            raise OtaCampaignValidationError("Selecciona un firmware para continuar.")
        if not option.is_eligible:
            raise OtaCampaignValidationError(
                f"El firmware seleccionado no está disponible para actualización: {option.ineligibility_reason}"
            )
        node_ids = self.selected_campaign_node_ids()
        canary_nodes = self.selected_canary_node_ids()
        require_canary = self.require_canary_checkbox.isChecked()
        waves = build_campaign_waves(
            node_ids,
            canary_nodes=canary_nodes,
            wave_size=int(self.wave_size_spin.value()),
        )
        return OtaCampaignPlan(
            campaign_id="",
            artifact_id=option.artifact_id,
            node_ids=node_ids,
            canary_nodes=canary_nodes,
            waves=waves,
            advertise_host=self.advertise_host_edit.text(),
            bind_host=self.bind_host_edit.text(),
            port=int(self.port_spin.value()),
            rollout_token=self.rollout_token_edit.text(),
            rollout_channel=str(self.rollout_channel_combo.currentData() or "stable"),
            ack_timeout_ms=int(self.ack_timeout_spin.value()),
            max_retries=int(self.max_retries_spin.value()),
            require_canary=require_canary,
        )

    def _update_wave_preview(self) -> None:
        try:
            preview = build_ota_campaign_wave_preview(
                node_ids=self.selected_campaign_node_ids(),
                canary_nodes=self.selected_canary_node_ids(),
                wave_size=int(self.wave_size_spin.value()),
            )
        except Exception as exc:
            preview = f"Distribución inválida: {exc}"
        self.wave_preview_label.setText(preview)
        if hasattr(self, "start_canary_button"):
            self._update_action_state()

    def _update_action_state(self) -> None:
        option = self._selected_artifact_option()
        can_start = (
            option is not None
            and option.is_eligible
            and bool(self.selected_campaign_node_ids())
            and (
                not self.require_canary_checkbox.isChecked()
                or bool(self.selected_canary_node_ids())
            )
        )
        self.start_canary_button.setEnabled(can_start)

        result = self._last_result
        has_result = result is not None
        self.continue_button.setEnabled(bool(has_result and result.continue_allowed))
        self.pause_button.setEnabled(
            bool(
                has_result
                and result.campaign_status
                not in {OtaCampaignStatus.COMPLETED, OtaCampaignStatus.ABORTED}
            )
        )
        self.abort_button.setEnabled(
            bool(
                has_result
                and result.campaign_status
                not in {OtaCampaignStatus.COMPLETED, OtaCampaignStatus.ABORTED}
            )
        )
        self.refresh_button.setEnabled(has_result)
        self.open_rollout_button.setEnabled(bool(has_result and result.published_dir))

    def _on_start_canary_clicked(self) -> None:
        try:
            plan = self._build_plan_from_ui()
        except OtaCampaignValidationError as exc:
            QMessageBox.warning(self, "Configuración inválida", str(exc))
            return

        try:
            result = self._campaign_service.start_campaign(plan)
        except (OtaCampaignServiceError, OtaCampaignValidationError) as exc:
            QMessageBox.critical(self, "Error al iniciar campaña", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive UI guard
            QMessageBox.critical(
                self,
                "Error inesperado",
                f"Ocurrió un error inesperado al iniciar la campaña: {exc}",
            )
            return

        self._last_result = result
        self._render_result(result)
        self._set_refresh_running_for(result)
        QMessageBox.information(
            self,
            "Primera ola iniciada",
            "La actualización fue publicada y la primera ola está en curso.",
        )

    def _on_continue_clicked(self) -> None:
        if self._last_result is None:
            return
        try:
            self._last_result = self._campaign_service.continue_campaign(self._last_result)
        except (OtaCampaignServiceError, OtaCampaignValidationError) as exc:
            QMessageBox.warning(self, "No se pudo continuar", str(exc))
            return
        self._render_result(self._last_result)
        self._set_refresh_running_for(self._last_result)

    def _on_pause_clicked(self) -> None:
        if self._last_result is None:
            return
        self._last_result = self._campaign_service.pause_campaign(self._last_result)
        self._render_result(self._last_result)
        self._refresh_timer.stop()

    def _on_abort_clicked(self) -> None:
        if self._last_result is None:
            return
        answer = QMessageBox.question(
            self,
            "Confirmar cancelación",
            "Se cancelarán las actualizaciones pendientes. ¿Confirmar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._last_result = self._campaign_service.abort_campaign(self._last_result)
        self._render_result(self._last_result)
        self._refresh_timer.stop()

    def _on_refresh_clicked(self) -> None:
        if self._last_result is None:
            return
        try:
            self._last_result = self._campaign_service.refresh_campaign(self._last_result)
        except Exception as exc:  # pragma: no cover - defensive UI guard
            QMessageBox.warning(
                self,
                "Error al actualizar estado",
                f"No se pudo actualizar el estado de la campaña: {exc}",
            )
            self._refresh_timer.stop()
            return
        self._render_result(self._last_result)
        self._set_refresh_running_for(self._last_result)

    def _render_result(self, result: OtaCampaignResult) -> None:
        rows = build_ota_campaign_node_rows(result.node_statuses)
        self.summary_label.setText(build_ota_campaign_result_summary(result))
        self.continue_hint_label.setText(build_ota_campaign_continue_hint(result))
        self.details_edit.setPlainText(build_ota_campaign_result_details(result))

        if not self.details_edit.isVisible():
            self.details_edit.setVisible(True)
            total = self._result_splitter.height()
            if total > 0:
                table_h = max(80, int(total * 0.75))
                details_h = max(60, total - table_h)
                self._result_splitter.setSizes([table_h, details_h])

        self.results_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = (
                row.node_label,
                row.wave_label,
                row.phase_label,
                row.outcome_label,
                row.ack_label,
                row.runtime_label,
                row.message,
                row.observed_at_utc,
            )
            for column_index, value in enumerate(values):
                self.results_table.setItem(
                    row_index,
                    column_index,
                    QTableWidgetItem(value),
                )
        self.results_table.resizeColumnsToContents()
        self._update_action_state()

    def _set_refresh_running_for(self, result: OtaCampaignResult) -> None:
        if result.campaign_status.value in {"canary_running", "wave_running"}:
            self._refresh_timer.start()
        else:
            self._refresh_timer.stop()

    def _open_rollout_folder(self) -> None:
        if self._last_result is None or not self._last_result.published_dir:
            return
        rollout_dir = Path(self._last_result.published_dir).resolve()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(rollout_dir)))
