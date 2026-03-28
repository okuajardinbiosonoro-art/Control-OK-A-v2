from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from control_okua.app_qt.firmware_import_dialog import FirmwareImportDialog
from control_okua.app_qt.ota_campaign_dialog import OtaCampaignDialog
from control_okua.app_qt.ota_deploy_dialog import OtaDeployDialog
from control_okua.app_qt.models.firmware_catalog_table_model import FirmwareCatalogTableModel
from control_okua.app_qt.viewmodels.firmware_manager_vm import (
    FirmwareCatalogRow,
    build_current_summary,
    build_empty_catalog_state,
    build_firmware_catalog_rows,
    build_firmware_detail,
    build_import_feedback,
    build_mark_current_confirmation_text,
    build_status_filter_options,
    build_target_filter_options,
    filter_firmware_catalog_rows,
)
from control_okua.core.firmware import (
    FirmwareCatalogStore,
    FirmwareIngestService,
)

if TYPE_CHECKING:
    from control_okua.services.session_controller import SessionController


class FirmwareManagerDialog(QDialog):
    def __init__(
        self,
        *,
        catalog_store: FirmwareCatalogStore | None = None,
        ingest_service: FirmwareIngestService | None = None,
        session_controller: "SessionController" | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Firmware Manager")
        self.resize(1240, 760)

        self._catalog_store = catalog_store or FirmwareCatalogStore()
        self._ingest_service = ingest_service or FirmwareIngestService(self._catalog_store)
        self._session_controller = session_controller
        self._all_rows: list[FirmwareCatalogRow] = []
        self._current_selection_artifact_id: str | None = None
        self._detail_labels: dict[str, QLabel] = {}

        self._build_ui()
        self.refresh_catalog()

    def refresh_catalog(self, *, select_artifact_id: str | None = None) -> None:
        catalog = self._catalog_store.load()
        self._all_rows = build_firmware_catalog_rows(catalog.artifacts)
        self._apply_filters(select_artifact_id=select_artifact_id)

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)

        intro = QLabel(
            "Gestione el catálogo técnico de firmware importado. "
            "Desde aquí puede revisar artifacts, importarlos y abrir el deploy OTA técnico "
            "para nodos seleccionados manualmente."
        )
        intro.setWordWrap(True)
        root_layout.addWidget(intro)

        actions_layout = QHBoxLayout()
        self.import_button = QPushButton("Importar firmware…", self)
        self.import_button.clicked.connect(self._on_import_clicked)
        actions_layout.addWidget(self.import_button)

        self.mark_current_button = QPushButton("Marcar current", self)
        self.mark_current_button.clicked.connect(self._on_mark_current_clicked)
        self.mark_current_button.setEnabled(False)
        actions_layout.addWidget(self.mark_current_button)

        self.refresh_button = QPushButton("Recargar catálogo", self)
        self.refresh_button.clicked.connect(self.refresh_catalog)
        actions_layout.addWidget(self.refresh_button)

        self.ota_deploy_button = QPushButton("OTA Deploy…", self)
        self.ota_deploy_button.clicked.connect(self._on_ota_deploy_clicked)
        self.ota_deploy_button.setEnabled(self._session_controller is not None)
        actions_layout.addWidget(self.ota_deploy_button)

        self.ota_campaign_button = QPushButton("OTA Campaign…", self)
        self.ota_campaign_button.clicked.connect(self._on_ota_campaign_clicked)
        self.ota_campaign_button.setEnabled(self._session_controller is not None)
        actions_layout.addWidget(self.ota_campaign_button)

        self.open_store_button = QPushButton("Abrir carpeta firmware", self)
        self.open_store_button.clicked.connect(self._open_managed_store_folder)
        actions_layout.addWidget(self.open_store_button)
        actions_layout.addStretch(1)
        root_layout.addLayout(actions_layout)

        filters_group = QGroupBox("Filtros", self)
        filters_layout = QHBoxLayout(filters_group)

        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Buscar por nombre, versión, archivo, target o SHA-256")
        self.search_edit.textChanged.connect(self._on_filters_changed)
        filters_layout.addWidget(self.search_edit, 2)

        self.target_filter_combo = QComboBox(self)
        for value, label in build_target_filter_options():
            self.target_filter_combo.addItem(label, value)
        self.target_filter_combo.currentIndexChanged.connect(self._on_filters_changed)
        filters_layout.addWidget(self.target_filter_combo, 1)

        self.status_filter_combo = QComboBox(self)
        for value, label in build_status_filter_options():
            self.status_filter_combo.addItem(label, value)
        self.status_filter_combo.currentIndexChanged.connect(self._on_filters_changed)
        filters_layout.addWidget(self.status_filter_combo, 1)

        self.current_only_checkbox = QCheckBox("Sólo current", self)
        self.current_only_checkbox.toggled.connect(self._on_filters_changed)
        filters_layout.addWidget(self.current_only_checkbox)

        root_layout.addWidget(filters_group)

        self.summary_label = QLabel("-", self)
        self.summary_label.setWordWrap(True)
        root_layout.addWidget(self.summary_label)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(self._build_catalog_pane())
        splitter.addWidget(self._build_detail_pane())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root_layout.addWidget(splitter, 1)

    def _build_catalog_pane(self) -> QWidget:
        pane = QWidget(self)
        layout = QVBoxLayout(pane)

        self.catalog_stack = QStackedWidget(self)

        empty_page = QWidget(self)
        empty_layout = QVBoxLayout(empty_page)
        self.empty_title_label = QLabel("", empty_page)
        self.empty_title_label.setWordWrap(True)
        font = self.empty_title_label.font()
        font.setBold(True)
        self.empty_title_label.setFont(font)
        empty_layout.addWidget(self.empty_title_label)
        self.empty_hint_label = QLabel("", empty_page)
        self.empty_hint_label.setWordWrap(True)
        empty_layout.addWidget(self.empty_hint_label)
        empty_layout.addStretch(1)
        self.catalog_stack.addWidget(empty_page)

        table_page = QWidget(self)
        table_layout = QVBoxLayout(table_page)
        self.catalog_table = QTableView(self)
        self.catalog_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.catalog_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.catalog_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.catalog_table.setAlternatingRowColors(True)
        self.catalog_table.setSortingEnabled(True)
        self.catalog_table.verticalHeader().setVisible(False)
        self.catalog_table.horizontalHeader().setStretchLastSection(True)
        self.catalog_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.catalog_table_model = FirmwareCatalogTableModel(self.catalog_table)
        self.catalog_table.setModel(self.catalog_table_model)
        self.catalog_table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self.catalog_table.horizontalHeader().setSortIndicator(9, Qt.DescendingOrder)
        table_layout.addWidget(self.catalog_table, 1)
        self.catalog_stack.addWidget(table_page)

        layout.addWidget(self.catalog_stack, 1)
        return pane

    def _build_detail_pane(self) -> QWidget:
        pane = QWidget(self)
        layout = QVBoxLayout(pane)

        current_group = QGroupBox("Resumen de selección", self)
        current_layout = QVBoxLayout(current_group)
        self.current_summary_label = QLabel("Sin selección.", self)
        self.current_summary_label.setWordWrap(True)
        current_layout.addWidget(self.current_summary_label)
        layout.addWidget(current_group)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        detail_content = QWidget(self)
        detail_layout = QVBoxLayout(detail_content)

        scalar_group = QGroupBox("Detalle", detail_content)
        scalar_layout = QFormLayout(scalar_group)
        for key in (
            "Artifact ID",
            "SHA-256",
            "Ruta gestionada",
            "Tamaño",
            "Target",
            "Variante",
            "Status",
            "Current",
            "Nombre",
            "Versión",
            "Etiqueta",
            "Origen",
            "Notas origen",
            "Compatibilidad",
            "Tags",
            "Importado UTC",
            "Creado UTC",
        ):
            label = QLabel("-", scalar_group)
            label.setWordWrap(True)
            scalar_layout.addRow(key + ":", label)
            self._detail_labels[key] = label
        detail_layout.addWidget(scalar_group)

        changelog_group = QGroupBox("Changelog", detail_content)
        changelog_layout = QVBoxLayout(changelog_group)
        self.changelog_edit = QTextEdit(changelog_group)
        self.changelog_edit.setReadOnly(True)
        self.changelog_edit.setMinimumHeight(120)
        changelog_layout.addWidget(self.changelog_edit)
        detail_layout.addWidget(changelog_group)

        notes_group = QGroupBox("Notas", detail_content)
        notes_layout = QVBoxLayout(notes_group)
        self.notes_edit = QTextEdit(notes_group)
        self.notes_edit.setReadOnly(True)
        self.notes_edit.setMinimumHeight(120)
        notes_layout.addWidget(self.notes_edit)
        detail_layout.addWidget(notes_group)
        detail_layout.addStretch(1)

        scroll.setWidget(detail_content)
        layout.addWidget(scroll, 1)
        return pane

    def _on_filters_changed(self) -> None:
        self._apply_filters(select_artifact_id=self._current_selection_artifact_id)

    def _apply_filters(self, *, select_artifact_id: str | None = None) -> None:
        filtered_rows = filter_firmware_catalog_rows(
            self._all_rows,
            search_text=self.search_edit.text(),
            target_filter=str(self.target_filter_combo.currentData() or ""),
            status_filter=str(self.status_filter_combo.currentData() or ""),
            current_only=self.current_only_checkbox.isChecked(),
        )
        self.catalog_table_model.set_rows(filtered_rows)
        header = self.catalog_table.horizontalHeader()
        self.catalog_table_model.sort(
            header.sortIndicatorSection(),
            header.sortIndicatorOrder(),
        )

        self._update_empty_state(total_artifacts=len(self._all_rows), filtered_artifacts=len(filtered_rows))

        target_artifact_id = select_artifact_id or self._current_selection_artifact_id
        if target_artifact_id and self._select_artifact_by_id(target_artifact_id):
            return
        if filtered_rows:
            self.catalog_table.selectRow(0)
            self._sync_selection_from_row(0)
        else:
            self._render_detail(None)

    def _update_empty_state(self, *, total_artifacts: int, filtered_artifacts: int) -> None:
        title, hint = build_empty_catalog_state(
            total_artifacts=total_artifacts,
            filtered_artifacts=filtered_artifacts,
        )
        has_rows = filtered_artifacts > 0
        self.catalog_stack.setCurrentIndex(1 if has_rows else 0)
        self.empty_title_label.setText(title)
        self.empty_hint_label.setText(hint)
        self.summary_label.setText(
            f"Artefactos totales: {total_artifacts} | visibles: {filtered_artifacts}"
        )

    def _on_selection_changed(self) -> None:
        indexes = self.catalog_table.selectionModel().selectedRows() if self.catalog_table.selectionModel() else []
        if not indexes:
            self._render_detail(None)
            return
        self._sync_selection_from_row(indexes[0].row())

    def _sync_selection_from_row(self, row_index: int) -> None:
        row = self.catalog_table_model.row_at(row_index)
        artifact = None if row is None else row.artifact
        self._render_detail(artifact)

    def _render_detail(self, artifact) -> None:
        detail = build_firmware_detail(artifact)
        for key, value in detail.scalar_fields:
            label = self._detail_labels.get(key)
            if label is not None:
                label.setText(value)
        self.changelog_edit.setPlainText(detail.changelog)
        self.notes_edit.setPlainText(detail.notes)
        self.current_summary_label.setText(build_current_summary(artifact))
        self._current_selection_artifact_id = None if artifact is None else artifact.artifact_id
        self.mark_current_button.setEnabled(artifact is not None)

    def _select_artifact_by_id(self, artifact_id: str) -> bool:
        for row_index in range(self.catalog_table_model.rowCount()):
            row = self.catalog_table_model.row_at(row_index)
            if row is None:
                continue
            if row.artifact_id == artifact_id:
                self.catalog_table.selectRow(row_index)
                self._sync_selection_from_row(row_index)
                return True
        return False

    def _on_import_clicked(self) -> None:
        dialog = FirmwareImportDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        request = dialog.selected_request()
        if request is None:
            QMessageBox.warning(
                self,
                "Importación inválida",
                "No se pudo construir una solicitud de importación válida.",
            )
            return

        result = self._ingest_service.import_artifact(request)
        self.refresh_catalog(select_artifact_id=result.artifact_id)

        feedback = build_import_feedback(result)
        text = feedback.summary
        if feedback.details and feedback.details != "Sin advertencias.":
            text = f"{text}\n\n{feedback.details}"

        if feedback.severity == "error":
            QMessageBox.critical(self, feedback.title, text)
        elif feedback.severity == "warning":
            QMessageBox.warning(self, feedback.title, text)
        else:
            QMessageBox.information(self, feedback.title, text)

    def _on_mark_current_clicked(self) -> None:
        artifact = self._selected_artifact()
        if artifact is None:
            return
        if artifact.is_current:
            QMessageBox.information(
                self,
                "Firmware current",
                "El artefacto seleccionado ya es current para su target.",
            )
            return

        answer = QMessageBox.question(
            self,
            "Confirmar current",
            build_mark_current_confirmation_text(artifact),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        updated_artifact = self._catalog_store.set_current(artifact.artifact_id)
        self._catalog_store.save()
        self.refresh_catalog(select_artifact_id=updated_artifact.artifact_id)
        QMessageBox.information(
            self,
            "Current actualizado",
            "El firmware seleccionado ahora es current para su target.",
        )

    def _selected_artifact(self):
        if not self._current_selection_artifact_id:
            return None
        return self._catalog_store.get_by_id(self._current_selection_artifact_id)

    def _on_ota_deploy_clicked(self) -> None:
        if self._session_controller is None:
            QMessageBox.warning(
                self,
                "OTA Deploy no disponible",
                "Esta instancia de Firmware Manager no tiene SessionController asociado.",
            )
            return

        dialog = OtaDeployDialog(
            session_controller=self._session_controller,
            catalog_store=self._catalog_store,
            preselected_artifact_id=self._current_selection_artifact_id,
            parent=self,
        )
        dialog.exec()

    def _on_ota_campaign_clicked(self) -> None:
        if self._session_controller is None:
            QMessageBox.warning(
                self,
                "OTA Campaign no disponible",
                "Esta instancia de Firmware Manager no tiene SessionController asociado.",
            )
            return

        dialog = OtaCampaignDialog(
            session_controller=self._session_controller,
            catalog_store=self._catalog_store,
            preselected_artifact_id=self._current_selection_artifact_id,
            parent=self,
        )
        dialog.exec()

    def _open_managed_store_folder(self) -> None:
        managed_dir = self._ingest_service.managed_store_dir
        managed_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(managed_dir).resolve())))
