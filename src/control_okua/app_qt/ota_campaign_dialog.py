from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
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

        intro = QLabel(
            "Campaña OTA técnica con canary, health gate y olas manuales. "
            "Publica el rollout una vez y permite continuar o abortar de forma explícita."
        )
        intro.setWordWrap(True)
        root_layout.addWidget(intro)

        config_grid = QGridLayout()
        config_grid.addWidget(self._build_artifact_group(), 0, 0)
        config_grid.addWidget(self._build_campaign_nodes_group(), 0, 1)
        config_grid.addWidget(self._build_canary_group(), 1, 0)
        config_grid.addWidget(self._build_rollout_group(), 1, 1)
        root_layout.addLayout(config_grid)

        self.wave_preview_label = QLabel("Sin campaña configurada todavía.", self)
        self.wave_preview_label.setWordWrap(True)
        root_layout.addWidget(self.wave_preview_label)

        actions_layout = QHBoxLayout()
        self.start_canary_button = QPushButton("Iniciar canary", self)
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

        self.refresh_button = QPushButton("Refrescar campaña", self)
        self.refresh_button.clicked.connect(self._on_refresh_clicked)
        self.refresh_button.setEnabled(False)
        actions_layout.addWidget(self.refresh_button)

        self.open_rollout_button = QPushButton("Abrir carpeta rollout", self)
        self.open_rollout_button.clicked.connect(self._open_rollout_folder)
        self.open_rollout_button.setEnabled(False)
        actions_layout.addWidget(self.open_rollout_button)
        actions_layout.addStretch(1)
        root_layout.addLayout(actions_layout)

        result_group = QGroupBox("Estado de campaña", self)
        result_layout = QVBoxLayout(result_group)
        self.summary_label = QLabel("Aún no hay campaña OTA en curso.", self)
        self.summary_label.setWordWrap(True)
        result_layout.addWidget(self.summary_label)

        self.continue_hint_label = QLabel(
            "Configura una campaña OTA para iniciar el canary.",
            self,
        )
        self.continue_hint_label.setWordWrap(True)
        result_layout.addWidget(self.continue_hint_label)

        self.results_table = QTableWidget(0, 8, self)
        self.results_table.setHorizontalHeaderLabels(
            [
                "Nodo",
                "Ola",
                "Fase OTA",
                "Resultado",
                "ACK",
                "OTA runtime",
                "Mensaje",
                "Observado UTC",
            ]
        )
        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.horizontalHeader().setStretchLastSection(True)
        result_layout.addWidget(self.results_table, 1)

        self.details_edit = QTextEdit(self)
        self.details_edit.setReadOnly(True)
        self.details_edit.setMinimumHeight(200)
        result_layout.addWidget(self.details_edit)
        root_layout.addWidget(result_group, 1)

        self._update_action_state()

    def _build_artifact_group(self) -> QWidget:
        group = QGroupBox("Artifact", self)
        layout = QVBoxLayout(group)

        combo_row = QHBoxLayout()
        self.artifact_combo = QComboBox(self)
        self.artifact_combo.currentIndexChanged.connect(self._on_artifact_changed)
        combo_row.addWidget(self.artifact_combo, 1)

        self.reload_artifacts_button = QPushButton("Recargar firmware", self)
        self.reload_artifacts_button.clicked.connect(self.reload_artifacts)
        combo_row.addWidget(self.reload_artifacts_button)
        layout.addLayout(combo_row)

        self.artifact_summary_label = QLabel("Sin artifact seleccionado.", self)
        self.artifact_summary_label.setWordWrap(True)
        layout.addWidget(self.artifact_summary_label)
        return group

    def _build_campaign_nodes_group(self) -> QWidget:
        group = QGroupBox("Nodos de campaña", self)
        layout = QVBoxLayout(group)

        self.nodes_list = QListWidget(self)
        self.nodes_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.nodes_list.itemSelectionChanged.connect(self._on_nodes_selection_changed)
        layout.addWidget(self.nodes_list, 1)

        self.nodes_hint_label = QLabel("Selecciona los nodos que participarán en la campaña.", self)
        self.nodes_hint_label.setWordWrap(True)
        layout.addWidget(self.nodes_hint_label)

        actions = QHBoxLayout()
        self.reload_nodes_button = QPushButton("Recargar nodos", self)
        self.reload_nodes_button.clicked.connect(self.reload_nodes)
        actions.addWidget(self.reload_nodes_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        return group

    def _build_canary_group(self) -> QWidget:
        group = QGroupBox("Canary y olas", self)
        layout = QFormLayout(group)

        self.require_canary_checkbox = QPushButton("Canary obligatorio: Sí", self)
        self.require_canary_checkbox.setCheckable(True)
        self.require_canary_checkbox.setChecked(True)
        self.require_canary_checkbox.toggled.connect(self._on_require_canary_toggled)
        layout.addRow("Modo canary:", self.require_canary_checkbox)

        self.canary_list = QListWidget(self)
        self.canary_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.canary_list.itemSelectionChanged.connect(self._update_wave_preview)
        self.canary_list.setMinimumHeight(180)
        layout.addRow("Nodos canary:", self.canary_list)

        self.wave_size_spin = QSpinBox(self)
        self.wave_size_spin.setRange(1, 64)
        self.wave_size_spin.setValue(1)
        self.wave_size_spin.valueChanged.connect(self._update_wave_preview)
        layout.addRow("Tamaño de ola:", self.wave_size_spin)
        return group

    def _build_rollout_group(self) -> QWidget:
        group = QGroupBox("Parámetros OTA", self)
        layout = QFormLayout(group)

        self.advertise_host_edit = QLineEdit("127.0.0.1", self)
        layout.addRow("Host visible al nodo:", self.advertise_host_edit)

        self.bind_host_edit = QLineEdit("0.0.0.0", self)
        layout.addRow("Bind host local:", self.bind_host_edit)

        self.port_spin = QSpinBox(self)
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(8080)
        layout.addRow("Puerto OTA:", self.port_spin)

        self.rollout_token_edit = QLineEdit(build_default_rollout_token(), self)
        layout.addRow("Rollout token (hex):", self.rollout_token_edit)

        self.rollout_channel_combo = QComboBox(self)
        for value in ("stable", "beta", "situational"):
            self.rollout_channel_combo.addItem(value, value)
        layout.addRow("Rollout channel:", self.rollout_channel_combo)

        self.ack_timeout_spin = QSpinBox(self)
        self.ack_timeout_spin.setRange(100, 10000)
        self.ack_timeout_spin.setValue(600)
        self.ack_timeout_spin.setSuffix(" ms")
        layout.addRow("Timeout ACK:", self.ack_timeout_spin)

        self.max_retries_spin = QSpinBox(self)
        self.max_retries_spin.setRange(0, 3)
        self.max_retries_spin.setValue(0)
        layout.addRow("Retries trigger:", self.max_retries_spin)
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
                f"Nodos visibles para campaña OTA: {len(self._node_options)}. "
                "Selecciona el conjunto total y luego el subconjunto canary."
            )
        else:
            self.nodes_hint_label.setText(
                "No hay nodos visibles en runtime/control-plane. "
                "Inicia sesión UDP antes de lanzar una campaña OTA."
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
            self.artifact_summary_label.setText("Sin artifact seleccionado.")
            self._update_action_state()
            return
        self.artifact_summary_label.setText(option.summary)
        self._update_action_state()

    def _on_require_canary_toggled(self, checked: bool) -> None:
        self.require_canary_checkbox.setText(
            "Canary obligatorio: Sí" if checked else "Canary obligatorio: No"
        )
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
            raise OtaCampaignValidationError("Selecciona un artifact firmware.")
        if not option.is_eligible:
            raise OtaCampaignValidationError(
                f"El artifact seleccionado no es elegible para OTA: {option.ineligibility_reason}"
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
            preview = f"Preview inválido: {exc}"
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
            QMessageBox.warning(self, "Plan OTA inválido", str(exc))
            return

        try:
            result = self._campaign_service.start_campaign(plan)
        except (OtaCampaignServiceError, OtaCampaignValidationError) as exc:
            QMessageBox.critical(self, "Campaña OTA fallida", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive UI guard
            QMessageBox.critical(
                self,
                "Campaña OTA inesperada",
                f"Ocurrió un error inesperado durante la campaña OTA: {exc}",
            )
            return

        self._last_result = result
        self._render_result(result)
        self._set_refresh_running_for(result)
        QMessageBox.information(
            self,
            "Canary disparado",
            "La campaña OTA publicó el rollout y disparó la ola canary.",
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
            "Abortar campaña OTA",
            "Esto bloqueará nuevas olas en la campaña actual. ¿Continuar?",
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
                "Refresco OTA fallido",
                f"No se pudo refrescar el estado de la campaña OTA: {exc}",
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
