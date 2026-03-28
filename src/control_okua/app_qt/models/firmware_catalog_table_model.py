from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

from control_okua.app_qt.viewmodels.firmware_manager_vm import (
    FirmwareCatalogRow,
    build_version_sort_key,
)


class FirmwareCatalogTableModel(QAbstractTableModel):
    _HEADERS = (
        "Nombre",
        "Versión",
        "Etiqueta",
        "Target",
        "Variante",
        "Status",
        "Current",
        "Archivo",
        "SHA-256",
        "Importado UTC",
    )

    def __init__(self, parent: Any | None = None) -> None:
        super().__init__(parent)
        self._rows: list[FirmwareCatalogRow] = []

    def set_rows(self, rows: list[FirmwareCatalogRow]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._HEADERS)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.DisplayRole,
    ) -> Any:
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and 0 <= section < len(self._HEADERS):
            return self._HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:  # noqa: N802
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        if row < 0 or row >= len(self._rows):
            return None

        entry = self._rows[row]
        if role == Qt.DisplayRole:
            return self._display_value(entry, col)
        if role == Qt.TextAlignmentRole and col in {5, 6, 8, 9}:
            return int(Qt.AlignCenter)
        if role == Qt.ForegroundRole:
            if col == 5:
                if entry.status == "current":
                    return QColor("#2F9E44")
                if entry.status == "beta":
                    return QColor("#B35C00")
                if entry.status == "obsolete":
                    return QColor("#6C757D")
                return QColor("#1C7ED6")
            if col == 6 and entry.current_label == "Sí":
                return QColor("#2F9E44")
        if role == Qt.UserRole:
            return entry.artifact_id
        return None

    def row_at(self, row: int) -> FirmwareCatalogRow | None:
        if row < 0 or row >= len(self._rows):
            return None
        return self._rows[row]

    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder) -> None:  # noqa: N802
        reverse = order == Qt.DescendingOrder
        self.layoutAboutToBeChanged.emit()
        self._rows.sort(key=lambda row: self._sort_key(row, column), reverse=reverse)
        self.layoutChanged.emit()

    def _display_value(self, row: FirmwareCatalogRow, col: int) -> str:
        if col == 0:
            return row.display_name
        if col == 1:
            return row.version
        if col == 2:
            return row.version_label
        if col == 3:
            return row.target_kind
        if col == 4:
            return row.target_variant
        if col == 5:
            return row.status
        if col == 6:
            return row.current_label
        if col == 7:
            return row.file_name
        if col == 8:
            return row.sha256_short
        if col == 9:
            return row.imported_at_utc
        return ""

    def _sort_key(self, row: FirmwareCatalogRow, column: int) -> tuple[object, ...]:
        if column == 0:
            return (row.display_name.casefold(), row.imported_at_utc, row.artifact_id)
        if column == 1:
            return (build_version_sort_key(row.version), row.imported_at_utc, row.artifact_id)
        if column == 2:
            return (row.version_label.casefold(), row.imported_at_utc, row.artifact_id)
        if column == 3:
            return (row.target_kind.casefold(), row.target_variant.casefold(), row.artifact_id)
        if column == 4:
            return (row.target_variant.casefold(), row.target_kind.casefold(), row.artifact_id)
        if column == 5:
            return (row.status_sort_order, row.target_kind.casefold(), row.artifact_id)
        if column == 6:
            return (row.current_sort_order, row.target_kind.casefold(), row.artifact_id)
        if column == 7:
            return (row.file_name.casefold(), row.imported_at_utc, row.artifact_id)
        if column == 8:
            return (row.sha256, row.imported_at_utc, row.artifact_id)
        if column == 9:
            return (row.imported_at_utc, row.artifact_id)
        return (row.imported_at_utc, row.artifact_id)
