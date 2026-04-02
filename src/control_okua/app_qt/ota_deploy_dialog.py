from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
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

from control_okua.app_qt.viewmodels.ota_deploy_vm import (
    OtaDeployArtifactOption,
    OtaDeployNodeOption,
    build_ota_artifact_options,
    build_ota_deploy_result_details,
    build_ota_deploy_result_summary,
    build_ota_node_options,
    build_ota_node_result_rows,
    build_recommended_rollout_channel,
)
from control_okua.core.firmware import (
    FirmwareCatalogStore,
    OtaDeployRequest,
    OtaDeployResult,
    OtaDeployValidationError,
    OtaManifestService,
    OtaManifestValidationError,
    build_default_rollout_token,
)
from control_okua.services.ota_orchestrator_service import (
    OtaOrchestratorService,
    OtaOrchestratorServiceError,
)

if TYPE_CHECKING:
    from control_okua.services.session_controller import SessionController


class OtaDeployDialog(QDialog):
    _REFRESH_INTERVAL_MS = 2000
    _TERMINAL_PHASES = {"confirmed", "failed", "timeout"}

    def __init__(
        self,
        *,
        session_controller: "SessionController",
        catalog_store: FirmwareCatalogStore | None = None,
        orchestrator_service: OtaOrchestratorService | None = None,
        preselected_artifact_id: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("OTA Deploy")
        self.resize(1120, 760)

        self._session_controller = session_controller
        self._catalog_store = catalog_store or FirmwareCatalogStore()
        self._orchestrator = orchestrator_service or OtaOrchestratorService(
            runtime_client=session_controller,
            manifest_service=OtaManifestService(self._catalog_store),
        )
        self._artifact_options: list[OtaDeployArtifactOption] = []
        self._node_options: list[OtaDeployNodeOption] = []
        self._last_result: OtaDeployResult | None = None
        self._preselected_artifact_id = preselected_artifact_id

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(self._REFRESH_INTERVAL_MS)
        self._refresh_timer.timeout.connect(self._on_refresh_status_clicked)

        self._build_ui()
        self.reload_artifacts()
        self.reload_nodes()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._refresh_timer.stop()
        super().closeEvent(event)

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)

        intro = QLabel(
            "Herramienta OTA técnica para publicar un rollout local y disparar "
            "OTA_CHECK_NOW sobre nodos seleccionados explícitamente."
        )
        intro.setWordWrap(True)
        root_layout.addWidget(intro)

        config_grid = QGridLayout()
        config_grid.addWidget(self._build_artifact_group(), 0, 0)
        config_grid.addWidget(self._build_nodes_group(), 0, 1)
        config_grid.addWidget(self._build_rollout_group(), 1, 0, 1, 2)
        root_layout.addLayout(config_grid)

        actions_layout = QHBoxLayout()
        self.deploy_button = QPushButton("Publicar y disparar OTA", self)
        self.deploy_button.clicked.connect(self._on_deploy_clicked)
        actions_layout.addWidget(self.deploy_button)

        self.refresh_status_button = QPushButton("Refrescar estados OTA", self)
        self.refresh_status_button.clicked.connect(self._on_refresh_status_clicked)
        self.refresh_status_button.setEnabled(False)
        actions_layout.addWidget(self.refresh_status_button)

        self.open_rollout_button = QPushButton("Abrir carpeta rollout", self)
        self.open_rollout_button.clicked.connect(self._open_rollout_folder)
        self.open_rollout_button.setEnabled(False)
        actions_layout.addWidget(self.open_rollout_button)
        actions_layout.addStretch(1)
        root_layout.addLayout(actions_layout)

        result_group = QGroupBox("Resultado por nodo", self)
        result_layout = QVBoxLayout(result_group)
        self.summary_label = QLabel("Aún no hay despliegue OTA en curso.", self)
        self.summary_label.setWordWrap(True)
        result_layout.addWidget(self.summary_label)

        self.results_table = QTableWidget(0, 6, self)
        self.results_table.setHorizontalHeaderLabels(
            [
                "Nodo",
                "Fase",
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
        self.details_edit.setMinimumHeight(180)
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

    def _build_nodes_group(self) -> QWidget:
        group = QGroupBox("Nodos", self)
        layout = QVBoxLayout(group)

        self.nodes_list = QListWidget(self)
        self.nodes_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.nodes_list.itemSelectionChanged.connect(self._update_action_state)
        layout.addWidget(self.nodes_list, 1)

        actions = QHBoxLayout()
        self.reload_nodes_button = QPushButton("Recargar nodos", self)
        self.reload_nodes_button.clicked.connect(self.reload_nodes)
        actions.addWidget(self.reload_nodes_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.nodes_hint_label = QLabel("Seleccione uno o más nodos explícitamente.", self)
        self.nodes_hint_label.setWordWrap(True)
        layout.addWidget(self.nodes_hint_label)
        return group

    def _build_rollout_group(self) -> QWidget:
        group = QGroupBox("Parámetros rollout", self)
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

        self.allow_downgrade_check = QCheckBox(
            "Permitir downgrade / reinstalar versión no más nueva", self
        )
        self.allow_downgrade_check.setToolTip(
            "Publica el rollout con una advertencia explícita para permitir "
            "instalar una versión más vieja o no más nueva."
        )
        layout.addRow("Downgrade:", self.allow_downgrade_check)
        return group

    def reload_artifacts(self) -> None:
        catalog = self._catalog_store.load()
        self._artifact_options = build_ota_artifact_options(catalog.artifacts)
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
        self._node_options = build_ota_node_options(snapshots)

        selected_ids = set(self.selected_node_ids())
        self.nodes_list.clear()
        for option in self._node_options:
            item = QListWidgetItem(option.label, self.nodes_list)
            item.setData(Qt.UserRole, option.node_id)
            item.setToolTip(option.summary)
            if option.node_id in selected_ids:
                item.setSelected(True)

        if self._node_options:
            self.nodes_hint_label.setText(
                f"Nodos visibles para OTA: {len(self._node_options)}. "
                "Selecciona uno o más y revisa que el host OTA sea alcanzable."
            )
        else:
            self.nodes_hint_label.setText(
                "No hay nodos visibles en runtime/control-plane. "
                "Inicia sesión UDP antes de disparar OTA."
            )
        self._update_action_state()

    def selected_node_ids(self) -> tuple[int, ...]:
        node_ids: list[int] = []
        for item in self.nodes_list.selectedItems():
            raw_node_id = item.data(Qt.UserRole)
            try:
                node_ids.append(int(raw_node_id))
            except (TypeError, ValueError):
                continue
        return tuple(node_ids)

    def _selected_artifact_option(self) -> OtaDeployArtifactOption | None:
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
        if option.recommended_host:
            self.advertise_host_edit.setText(option.recommended_host)
        recommended_channel = build_recommended_rollout_channel(option.artifact)
        index = self.rollout_channel_combo.findData(recommended_channel)
        if index >= 0:
            self.rollout_channel_combo.setCurrentIndex(index)
        self._update_action_state()

    def _update_action_state(self) -> None:
        option = self._selected_artifact_option()
        has_nodes = bool(self.selected_node_ids())
        can_deploy = (
            option is not None
            and option.is_eligible
            and has_nodes
            and self._session_controller is not None
        )
        self.deploy_button.setEnabled(can_deploy)
        self.refresh_status_button.setEnabled(self._last_result is not None)
        self.open_rollout_button.setEnabled(
            self._last_result is not None and bool(self._last_result.published_dir)
        )

    def _on_deploy_clicked(self) -> None:
        option = self._selected_artifact_option()
        if option is None:
            QMessageBox.warning(self, "OTA Deploy", "Selecciona un artifact firmware.")
            return
        if not option.is_eligible:
            QMessageBox.warning(
                self,
                "Artifact no elegible",
                f"El artifact seleccionado no es elegible para OTA: {option.ineligibility_reason}",
            )
            return
        node_ids = self.selected_node_ids()
        if not node_ids:
            QMessageBox.warning(
                self,
                "Nodos no seleccionados",
                "Selecciona al menos un nodo explícitamente antes de disparar OTA.",
            )
            return

        try:
            request = OtaDeployRequest(
                artifact_id=option.artifact_id,
                node_ids=node_ids,
                advertise_host=self.advertise_host_edit.text(),
                bind_host=self.bind_host_edit.text(),
                port=int(self.port_spin.value()),
                rollout_token=self.rollout_token_edit.text(),
                rollout_channel=str(self.rollout_channel_combo.currentData() or "stable"),
                ack_timeout_ms=int(self.ack_timeout_spin.value()),
                max_retries=int(self.max_retries_spin.value()),
                allow_downgrade=self.allow_downgrade_check.isChecked(),
            )
        except OtaDeployValidationError as exc:
            QMessageBox.warning(self, "Request OTA inválido", str(exc))
            return

        if request.allow_downgrade:
            answer = QMessageBox.warning(
                self,
                "Downgrade OTA permitido",
                "Estás autorizando una OTA con versión no más nueva. "
                "Esto puede reinstalar una versión antigua y es riesgoso si el "
                "build tiene regresiones. ¿Quieres continuar?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        try:
            result = self._orchestrator.deploy(request)
        except (OtaOrchestratorServiceError, OtaManifestValidationError, OtaDeployValidationError) as exc:
            QMessageBox.critical(self, "Deploy OTA fallido", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive UI guard
            QMessageBox.critical(
                self,
                "Deploy OTA inesperado",
                f"Ocurrió un error inesperado durante el deploy OTA: {exc}",
            )
            return

        self._last_result = result
        self._render_result(result)
        self._refresh_timer.start()

        if result.success:
            QMessageBox.information(
                self,
                "Deploy OTA disparado",
                "El rollout OTA fue publicado y se enviaron los triggers a los nodos seleccionados.",
            )
        else:
            QMessageBox.warning(
                self,
                "Deploy OTA con fallos",
                result.message or "El deploy OTA terminó con errores.",
            )

    def _on_refresh_status_clicked(self) -> None:
        if self._last_result is None:
            return
        try:
            self._last_result = self._orchestrator.refresh_deploy_statuses(self._last_result)
        except Exception as exc:  # pragma: no cover - defensive UI guard
            QMessageBox.warning(
                self,
                "Refresco OTA fallido",
                f"No se pudieron refrescar los estados OTA: {exc}",
            )
            self._refresh_timer.stop()
            return

        self._render_result(self._last_result)
        if all(
            status.phase.value in self._TERMINAL_PHASES
            for status in self._last_result.node_statuses
        ):
            self._refresh_timer.stop()

    def _render_result(self, result: OtaDeployResult) -> None:
        rows = build_ota_node_result_rows(result.node_statuses)
        self.summary_label.setText(build_ota_deploy_result_summary(result))
        self.details_edit.setPlainText(build_ota_deploy_result_details(result))
        self.results_table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            values = (
                row.node_label,
                row.phase_label,
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

    def _open_rollout_folder(self) -> None:
        if self._last_result is None or not self._last_result.published_dir:
            return
        rollout_dir = Path(self._last_result.published_dir).resolve()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(rollout_dir)))
