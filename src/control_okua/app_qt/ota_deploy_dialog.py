from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QAbstractItemView,
    QCheckBox,
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
from control_okua.app_qt.ota_defaults import DEFAULT_APP_OTA_HTTP_PORT
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
        self.setObjectName("otaDeployDialog")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("Despliegue OTA")
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

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(8)

        intro = QLabel(
            "Publica una actualización de firmware y notifica a los nodos seleccionados "
            "para que la descarguen e instalen."
        )
        intro.setWordWrap(True)
        root_layout.addWidget(intro)

        # A single vertical splitter is the only primitive in Qt that guarantees
        # strict sequential (non-overlapping) placement of its children regardless
        # of how much content is in each pane. Using a plain QVBoxLayout for the
        # config + result stack was the root cause of the overlap: Qt's VBoxLayout
        # distributes space based on sizeHints for stretch=0 items, but when the
        # total sizeHint exceeds the dialog height the config grid was receiving less
        # than its real minimum, causing the rollout group to overflow its allocated
        # slot and visually overlap the section below.
        #
        # With setChildrenCollapsible(False) the splitter honors each child's
        # minimumSizeHint, so the config pane always gets at least enough room for
        # all eight form rows plus the action bar.
        self._main_splitter = QSplitter(Qt.Orientation.Vertical, self)
        self._main_splitter.setObjectName("otaMainSplitter")
        self._main_splitter.setChildrenCollapsible(False)

        # Top pane: configuration groups + action bar.
        config_pane = QWidget()
        config_pane.setObjectName("otaConfigPane")
        config_pane_layout = QVBoxLayout(config_pane)
        config_pane_layout.setContentsMargins(0, 0, 0, 0)
        config_pane_layout.setSpacing(10)

        config_grid = QGridLayout()
        config_grid.setHorizontalSpacing(14)
        config_grid.setVerticalSpacing(14)
        # Keep Firmware visually dominant but give Nodes enough width so the
        # list + hint stay readable and do not feel cramped.
        config_grid.setColumnStretch(0, 2)
        config_grid.setColumnStretch(1, 1)
        artifact_group = self._build_artifact_group()
        nodes_group = self._build_nodes_group()
        # Cap row-0 groups so Nodes remains comfortable without letting the
        # right list's large sizeHint consume excessive height from the rollout form.
        # QGridLayout.setRowMaximumHeight is not exposed in PySide6, so we
        # constrain both row-0 widgets directly.
        _TOP_ROW_MAX_HEIGHT = 220
        artifact_group.setMaximumHeight(_TOP_ROW_MAX_HEIGHT)
        nodes_group.setMaximumHeight(_TOP_ROW_MAX_HEIGHT)
        config_grid.addWidget(artifact_group, 0, 0)
        config_grid.addWidget(nodes_group, 0, 1)
        config_grid.addWidget(self._build_rollout_group(), 1, 0, 1, 2)
        config_pane_layout.addLayout(config_grid)
        config_pane_layout.addLayout(self._build_actions_bar())

        # Bottom pane: results (elastic — takes all remaining space).
        self._main_splitter.addWidget(config_pane)
        self._main_splitter.addWidget(self._build_result_group())

        # Config pane does not grow beyond its natural preferred size; the result
        # pane absorbs all extra vertical space.
        self._main_splitter.setStretchFactor(0, 0)
        self._main_splitter.setStretchFactor(1, 1)

        root_layout.addWidget(self._main_splitter, 1)
        self._update_action_state()

    def _build_actions_bar(self) -> QHBoxLayout:
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)

        self.deploy_button = QPushButton("Publicar actualización", self)
        self.deploy_button.clicked.connect(self._on_deploy_clicked)
        actions_layout.addWidget(self.deploy_button)

        self.refresh_status_button = QPushButton("Actualizar estados", self)
        self.refresh_status_button.clicked.connect(self._on_refresh_status_clicked)
        self.refresh_status_button.setEnabled(False)
        actions_layout.addWidget(self.refresh_status_button)

        self.open_rollout_button = QPushButton("Abrir carpeta", self)
        self.open_rollout_button.clicked.connect(self._open_rollout_folder)
        self.open_rollout_button.setEnabled(False)
        actions_layout.addWidget(self.open_rollout_button)

        actions_layout.addStretch(1)
        return actions_layout

    def _build_result_group(self) -> QGroupBox:
        result_group = QGroupBox("Resultado por nodo", self)
        result_group.setObjectName("otaDeployResultGroup")
        result_layout = QVBoxLayout(result_group)
        result_layout.setSpacing(8)

        self.summary_label = QLabel("Aún no hay despliegue OTA en curso.", self)
        self.summary_label.setWordWrap(True)
        result_layout.addWidget(self.summary_label)

        # Inner splitter gives the user control over the table vs. details split.
        # The table gets ~75 % on first deployment; before any deployment the details
        # panel is hidden so the table fills the entire result area without
        # leaving a permanent "white pit."
        self._result_splitter = QSplitter(Qt.Orientation.Vertical, result_group)
        self._result_splitter.setObjectName("otaResultSplitter")
        self._result_splitter.setChildrenCollapsible(False)

        self.results_table = QTableWidget(0, 6, self)
        self.results_table.setHorizontalHeaderLabels(
            ["Nodo", "Fase", "Respuesta", "Estado OTA", "Mensaje", "Observado UTC"]
        )
        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._result_splitter.addWidget(self.results_table)

        self.details_edit = QTextEdit(self)
        self.details_edit.setReadOnly(True)
        self.details_edit.setObjectName("otaDeployDetails")
        self.details_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.details_edit.setVisible(False)
        self._result_splitter.addWidget(self.details_edit)

        self._result_splitter.setStretchFactor(0, 4)
        self._result_splitter.setStretchFactor(1, 1)

        result_layout.addWidget(self._result_splitter, 1)
        return result_group

    def _set_responsive_field(
        self,
        widget: QWidget,
        *,
        min_width: int,
    ) -> None:
        widget.setMinimumWidth(min_width)
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

    def _build_nodes_group(self) -> QWidget:
        group = QGroupBox("Nodos", self)
        group.setObjectName("otaDeployNodesGroup")
        group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(group)
        # QGroupBox already gets internal padding from QSS. Keep layout margins at
        # zero to avoid double padding and recover useful space for the node list.
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.nodes_list = QListWidget(self)
        self.nodes_list.setObjectName("otaDeployNodesList")
        self.nodes_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.nodes_list.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        min_row_height = max(self.fontMetrics().lineSpacing() + 6, 20)
        self.nodes_list.setMinimumHeight(min_row_height * 3)
        self.nodes_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.nodes_list.itemSelectionChanged.connect(self._update_action_state)
        layout.addWidget(self.nodes_list, 1)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        self.reload_nodes_button = QPushButton("Recargar nodos", self)
        self.reload_nodes_button.setObjectName("otaDeployReloadNodesButton")
        self.reload_nodes_button.clicked.connect(self.reload_nodes)
        actions.addWidget(self.reload_nodes_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.nodes_hint_label = QLabel("Seleccione uno o más nodos explícitamente.", self)
        self.nodes_hint_label.setObjectName("otaDeployNodesHintLabel")
        self.nodes_hint_label.setWordWrap(True)
        self.nodes_hint_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self.nodes_hint_label)
        return group

    def _build_rollout_group(self) -> QWidget:
        group = QGroupBox("Configuración de red", self)
        group.setObjectName("otaDeployRolloutGroup")
        # MinimumExpanding: Qt allocates at least minimumSizeHint (computed after QSS)
        # and grows the widget when extra space is available.
        group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)

        group_layout = QGridLayout(group)
        # Do NOT call setContentsMargins: QSS `padding` on QGroupBox overrides any
        # programmatic margins set before QSS application, causing a mismatch
        # between the pre-QSS sizeHint measurement and the post-QSS visual geometry.
        group_layout.setHorizontalSpacing(14)
        group_layout.setVerticalSpacing(10)
        group_layout.setColumnStretch(0, 0)
        group_layout.setColumnStretch(1, 1)

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

        self.allow_downgrade_check = QCheckBox(
            "Permitir instalar una versión anterior o igual a la actual", group
        )
        self.allow_downgrade_check.setToolTip(
            "Activa esta opción solo si necesitas reinstalar una versión anterior. "
            "Instalar una versión más vieja puede reintroducir errores corregidos."
        )
        self.allow_downgrade_check.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.allow_downgrade_check.setMinimumHeight(
            max(self.allow_downgrade_check.sizeHint().height(), 24)
        )

        row_specs = [
            ("IP accesible por el nodo:", self.advertise_host_edit),
            ("Dirección local:", self.bind_host_edit),
            ("Puerto OTA fijo:", self.port_spin),
            ("Token de actualización:", self.rollout_token_edit),
            ("Canal:", self.rollout_channel_combo),
            ("Tiempo de respuesta:", self.ack_timeout_spin),
            ("Reintentos:", self.max_retries_spin),
            ("Versión anterior:", self.allow_downgrade_check),
        ]
        label_width = (
            max(self.fontMetrics().horizontalAdvance(text) for text, _ in row_specs) + 12
        )
        label_row_min = max(self.fontMetrics().height() + 6, 24)
        row_min_heights: list[int] = []
        for row_index, (text, field_widget) in enumerate(row_specs):
            label = QLabel(text, group)
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            label.setMinimumWidth(label_width)
            label.setMinimumHeight(label_row_min)
            group_layout.addWidget(
                label,
                row_index,
                0,
                1,
                1,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            )
            group_layout.addWidget(field_widget, row_index, 1, 1, 1)
            row_h = max(field_widget.minimumHeight(), label_row_min)
            group_layout.setRowMinimumHeight(row_index, row_h)
            row_min_heights.append(row_h)

        # Set a stable minimum height computed from first principles.
        # DO NOT use group.sizeHint() here: that measurement happens at construction
        # time before the QSS stylesheet is applied, so it underestimates by roughly
        # the QSS-added padding (margin-top:18 + padding-top:18 + padding-bottom:14 on
        # the CKv2 theme ≈ 50 px).  A group allocated too-few pixels causes its bottom
        # rows to overflow into the next section — which was the original visual bug.
        # Computing from the known row heights and spacings is stable across platforms,
        # DPI settings, and QSS timing.
        num_rows = len(row_min_heights)
        content_min_h = (
            sum(row_min_heights) + (num_rows - 1) * group_layout.verticalSpacing()
        )
        # Conservative QGroupBox header overhead for the CKv2 theme:
        # margin-top (18) + title height (~18) + padding-top (18) + padding-bottom (14)
        # = 68 px. Add a small buffer for cross-platform font rendering differences.
        _HEADER_V = 72
        group.setMinimumHeight(content_min_h + _HEADER_V)
        return group

    # ------------------------------------------------------------------ #
    # Data loading                                                         #
    # ------------------------------------------------------------------ #

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
                f"Nodos disponibles: {len(self._node_options)}. "
                "Selecciona los que recibirán la actualización."
            )
        else:
            self.nodes_hint_label.setText(
                "No hay nodos conectados. "
                "Inicia una sesión UDP antes de continuar."
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

    # ------------------------------------------------------------------ #
    # State management                                                     #
    # ------------------------------------------------------------------ #

    def _selected_artifact_option(self) -> OtaDeployArtifactOption | None:
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

    # ------------------------------------------------------------------ #
    # Actions                                                              #
    # ------------------------------------------------------------------ #

    def _on_deploy_clicked(self) -> None:
        option = self._selected_artifact_option()
        if option is None:
            QMessageBox.warning(self, "Actualización OTA", "Selecciona un firmware para continuar.")
            return
        if not option.is_eligible:
            QMessageBox.warning(
                self,
                "Firmware no disponible",
                f"El firmware seleccionado no está disponible para actualización: {option.ineligibility_reason}",
            )
            return
        node_ids = self.selected_node_ids()
        if not node_ids:
            QMessageBox.warning(
                self,
                "Sin nodos seleccionados",
                "Selecciona al menos un nodo antes de publicar la actualización.",
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
            QMessageBox.warning(self, "Configuración inválida", str(exc))
            return

        if request.allow_downgrade:
            answer = QMessageBox.warning(
                self,
                "Versión anterior a la actual",
                "Estás autorizando una actualización con una versión anterior o igual a la instalada. "
                "Esto puede reintroducir errores ya corregidos. ¿Quieres continuar?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        try:
            result = self._orchestrator.deploy(request)
        except (OtaOrchestratorServiceError, OtaManifestValidationError, OtaDeployValidationError) as exc:
            QMessageBox.critical(self, "Error al publicar actualización", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive UI guard
            QMessageBox.critical(
                self,
                "Error inesperado",
                f"Ocurrió un error inesperado al publicar la actualización: {exc}",
            )
            return

        self._last_result = result
        self._render_result(result)
        self._refresh_timer.start()

        if result.success:
            QMessageBox.information(
                self,
                "Actualización iniciada",
                "La actualización fue publicada y se notificó a los nodos seleccionados.",
            )
        else:
            QMessageBox.warning(
                self,
                "Actualización con errores",
                result.message or "La actualización terminó con errores.",
            )

    def _on_refresh_status_clicked(self) -> None:
        if self._last_result is None:
            return
        try:
            self._last_result = self._orchestrator.refresh_deploy_statuses(self._last_result)
        except Exception as exc:  # pragma: no cover - defensive UI guard
            QMessageBox.warning(
                self,
                "Error al actualizar estados",
                f"No se pudo actualizar el estado de los nodos: {exc}",
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

        # Reveal the details panel on the first deployment and set a sensible initial
        # split: table 75 %, details 25 %.  The user can drag the handle to adjust.
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
