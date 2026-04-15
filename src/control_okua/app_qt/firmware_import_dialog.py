from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from control_okua.app_qt.viewmodels.firmware_manager_vm import (
    build_display_name_suggestion,
    build_status_filter_options,
    build_target_filter_options,
)
from control_okua.core.firmware import (
    FirmwareImportRequest,
    FirmwareImportValidationError,
)


class FirmwareImportDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("firmwareImportDialog")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("Importar firmware")
        self.setModal(True)
        self.resize(720, 620)

        self._display_name_autofill = True
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Registre un artefacto firmware desde un .bin real. "
            "La identidad técnica se calculará automáticamente desde el contenido."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        source_group = QGroupBox("Archivo fuente", self)
        source_layout = QFormLayout(source_group)

        source_row = QHBoxLayout()
        self.source_path_edit = QLineEdit(self)
        self.source_path_edit.setPlaceholderText("Seleccione un archivo .bin")
        self.source_path_edit.textChanged.connect(self._on_source_path_changed)
        source_row.addWidget(self.source_path_edit, 1)

        self.browse_button = QPushButton("Seleccionar…", self)
        self.browse_button.clicked.connect(self._browse_source_file)
        source_row.addWidget(self.browse_button)
        source_layout.addRow("Archivo .bin:", source_row)

        layout.addWidget(source_group)

        metadata_group = QGroupBox("Metadata", self)
        metadata_layout = QFormLayout(metadata_group)

        self.version_edit = QLineEdit(self)
        self.version_edit.setPlaceholderText("Ej. 1.2.3")
        metadata_layout.addRow("Versión *", self.version_edit)

        self.version_label_edit = QLineEdit(self)
        self.version_label_edit.setPlaceholderText("Ej. v1.2.3")
        metadata_layout.addRow("Etiqueta versión", self.version_label_edit)

        self.target_kind_combo = QComboBox(self)
        target_options = build_target_filter_options()[1:]
        for value, label in target_options:
            self.target_kind_combo.addItem(label, value)
        metadata_layout.addRow("Target *", self.target_kind_combo)

        self.target_variant_edit = QLineEdit(self)
        self.target_variant_edit.setText("generic")
        metadata_layout.addRow("Variante", self.target_variant_edit)

        self.status_combo = QComboBox(self)
        status_options = [
            item
            for item in build_status_filter_options()[1:]
            if item[0] != "current"
        ]
        for value, label in status_options:
            self.status_combo.addItem(label, value)
        beta_index = self.status_combo.findData("beta")
        if beta_index >= 0:
            self.status_combo.setCurrentIndex(beta_index)
        metadata_layout.addRow("Status inicial", self.status_combo)

        self.display_name_edit = QLineEdit(self)
        self.display_name_edit.setPlaceholderText("Opcional; se genera desde el nombre del archivo")
        self.display_name_edit.textEdited.connect(self._on_display_name_edited)
        metadata_layout.addRow("Nombre visible", self.display_name_edit)

        self.mark_current_checkbox = QCheckBox("Marcar como current para este target", self)
        metadata_layout.addRow("", self.mark_current_checkbox)

        layout.addWidget(metadata_group)

        extra_group = QGroupBox("Notas técnicas", self)
        extra_layout = QFormLayout(extra_group)

        self.source_notes_edit = QLineEdit(self)
        self.source_notes_edit.setPlaceholderText("Opcional")
        extra_layout.addRow("Notas origen", self.source_notes_edit)

        self.tags_edit = QLineEdit(self)
        self.tags_edit.setPlaceholderText("tag1, tag2")
        extra_layout.addRow("Tags", self.tags_edit)

        self.compatibility_edit = QLineEdit(self)
        self.compatibility_edit.setPlaceholderText("eb1, f3")
        extra_layout.addRow("Compatibilidad", self.compatibility_edit)

        self.changelog_edit = QTextEdit(self)
        self.changelog_edit.setMinimumHeight(90)
        extra_layout.addRow("Changelog", self.changelog_edit)

        self.notes_edit = QTextEdit(self)
        self.notes_edit.setMinimumHeight(90)
        extra_layout.addRow("Notas", self.notes_edit)

        layout.addWidget(extra_group, 1)

        buttons = QDialogButtonBox(self)
        self.import_button = buttons.addButton("Importar", QDialogButtonBox.AcceptRole)
        self.cancel_button = buttons.addButton("Cancelar", QDialogButtonBox.RejectRole)
        self.import_button.clicked.connect(self._accept_if_valid)
        self.cancel_button.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def build_request(self) -> FirmwareImportRequest:
        return FirmwareImportRequest(
            source_file_path=self.source_path_edit.text().strip(),
            target_kind=self.target_kind_combo.currentData(),
            target_variant=self.target_variant_edit.text().strip() or "generic",
            version=self.version_edit.text().strip(),
            version_label=self.version_label_edit.text().strip(),
            status=self.status_combo.currentData(),
            display_name=self.display_name_edit.text().strip(),
            changelog=self.changelog_edit.toPlainText().strip(),
            notes=self.notes_edit.toPlainText().strip(),
            source_kind="manual_import",
            source_notes=self.source_notes_edit.text().strip(),
            tags=_split_csv_values(self.tags_edit.text()),
            compatibility=_split_csv_values(self.compatibility_edit.text()),
            mark_as_current=self.mark_current_checkbox.isChecked(),
            copy_to_managed_store=True,
        )

    def selected_request(self) -> FirmwareImportRequest | None:
        try:
            return self.build_request()
        except (FirmwareImportValidationError, ValueError):
            return None

    def _browse_source_file(self) -> None:
        file_path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Seleccionar firmware",
            "",
            "Firmware (*.bin)",
        )
        if file_path:
            self.source_path_edit.setText(file_path)

    def _on_source_path_changed(self, value: str) -> None:
        path = Path(value.strip()) if value.strip() else None
        if path is None:
            return
        if self._display_name_autofill or not self.display_name_edit.text().strip():
            self.display_name_edit.setText(build_display_name_suggestion(path))

    def _on_display_name_edited(self, _value: str) -> None:
        self._display_name_autofill = False

    def _accept_if_valid(self) -> None:
        try:
            self.build_request()
        except (FirmwareImportValidationError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Importación inválida",
                str(exc),
            )
            return
        self.accept()


def _split_csv_values(text: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]
