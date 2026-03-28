from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

from control_okua.app_qt.viewmodels import (
    format_node_label,
    format_node_last_note_velocity,
    format_node_last_seen,
    format_node_loss,
    format_node_pps,
    format_node_rssi,
    format_node_status_detail,
    format_node_status,
    format_node_type,
    node_status_key,
)


class NodeTableModel(QAbstractTableModel):
    _HEADERS = (
        "node_id",
        "label",
        "tipo",
        "estado",
        "último visto",
        "pps",
        "pérdida",
        "RSSI",
        "último note/vel",
    )

    def __init__(self, parent: Any | None = None) -> None:
        super().__init__(parent)
        self._snapshots: list[object] = []
        self._now_monotonic: float | None = None

    def set_snapshots(self, snapshots: list[object], *, now_monotonic: float | None = None) -> None:
        self.beginResetModel()
        self._snapshots = list(snapshots)
        self._now_monotonic = now_monotonic
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._snapshots)

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
        if row < 0 or row >= len(self._snapshots):
            return None
        snapshot = self._snapshots[row]

        if role == Qt.DisplayRole:
            return self._display_value(snapshot, col)

        if role == Qt.ToolTipRole and col == 3:
            return format_node_status_detail(snapshot)

        if role == Qt.ForegroundRole and col == 3:
            status = node_status_key(snapshot)
            if status == "online":
                return QColor("#2F9E44")
            if status == "calibrating":
                return QColor("#1C7ED6")
            if status == "degraded":
                return QColor("#E67700")
            return QColor("#C92A2A")

        if role == Qt.TextAlignmentRole and col in {0, 3, 4, 5, 6, 7, 8}:
            return int(Qt.AlignCenter)

        return None

    def _display_value(self, snapshot: object, col: int) -> str:
        node_id = getattr(snapshot, "node_id", None)
        if col == 0:
            return "—" if node_id is None else str(node_id)
        if col == 1:
            return format_node_label(snapshot)
        if col == 2:
            return format_node_type(snapshot)
        if col == 3:
            return format_node_status(snapshot)
        if col == 4:
            return format_node_last_seen(snapshot, now_monotonic=self._now_monotonic)
        if col == 5:
            return format_node_pps(snapshot)
        if col == 6:
            return format_node_loss(snapshot)
        if col == 7:
            return format_node_rssi(snapshot)
        if col == 8:
            return format_node_last_note_velocity(snapshot)
        return ""
