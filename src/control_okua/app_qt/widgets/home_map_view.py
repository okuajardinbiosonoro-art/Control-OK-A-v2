from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from control_okua.app_qt.contracts import HomeMapBoxLayout, HomeMapLayout
from control_okua.app_qt.viewmodels import HomeMapBoxViewModel


class HomeMapView(QWidget):
    box_selected = Signal(int)

    def __init__(self, layout_contract: HomeMapLayout, parent=None) -> None:
        super().__init__(parent)
        self._layout_contract = layout_contract
        self._selected_box_id = layout_contract.boxes[0].box_id if layout_contract.boxes else None
        self._background_pixmap = self._load_background_pixmap(layout_contract.background_asset)
        self._box_view_models: dict[int, HomeMapBoxViewModel] = {}
        self.setMinimumHeight(360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

    @property
    def layout_contract(self) -> HomeMapLayout:
        return self._layout_contract

    @property
    def selected_box_id(self) -> int | None:
        return self._selected_box_id

    def selected_box(self) -> HomeMapBoxLayout | None:
        if self._selected_box_id is None:
            return None
        for box in self._layout_contract.boxes:
            if box.box_id == self._selected_box_id:
                return box
        return None

    def has_background_asset(self) -> bool:
        return not self._background_pixmap.isNull()

    def set_box_view_models(self, view_models: dict[int, HomeMapBoxViewModel]) -> None:
        self._box_view_models = dict(view_models)
        self.update()

    def box_view_model(self, box_id: int) -> HomeMapBoxViewModel | None:
        return self._box_view_models.get(int(box_id))

    def set_selected_box(self, box_id: int) -> None:
        normalized = int(box_id)
        if self._selected_box_id == normalized:
            return
        for box in self._layout_contract.boxes:
            if box.box_id == normalized:
                self._selected_box_id = normalized
                self.box_selected.emit(normalized)
                self.update()
                return
        raise KeyError(f"Unknown map box: {box_id!r}")

    def box_at_position(self, point: QPointF) -> HomeMapBoxLayout | None:
        for box in reversed(self._layout_contract.boxes):
            if self.box_rect(box.box_id).contains(point):
                return box
        return None

    def box_rect(self, box_id: int) -> QRectF:
        map_rect = self._map_rect(QRectF(self.rect()))
        for box in self._layout_contract.boxes:
            if box.box_id == int(box_id):
                x, y, width, height = box.normalized_rect
                return QRectF(
                    map_rect.left() + x * map_rect.width(),
                    map_rect.top() + y * map_rect.height(),
                    width * map_rect.width(),
                    height * map_rect.height(),
                )
        raise KeyError(f"Unknown map box: {box_id!r}")

    def sizeHint(self) -> QSize:
        return QSize(920, 540)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        box = self.box_at_position(event.position())
        if box is None:
            super().mousePressEvent(event)
            return
        self.set_selected_box(box.box_id)
        event.accept()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        outer_rect = QRectF(self.rect()).adjusted(8.0, 8.0, -8.0, -8.0)
        painter.fillRect(outer_rect, QColor("#F6F8F6"))

        map_rect = self._map_rect(outer_rect)
        self._paint_background(painter, map_rect)

        for box in self._layout_contract.boxes:
            box_rect = self.box_rect(box.box_id)
            is_selected = box.box_id == self._selected_box_id
            box_view_model = self._box_view_models.get(box.box_id)
            fill_color = QColor(
                box_view_model.fill_hex if box_view_model is not None else ("#F8FBFF" if is_selected else "#FBFBF8")
            )
            border_color = QColor(
                "#184E91" if is_selected else (
                    box_view_model.border_hex if box_view_model is not None else "#5F6B66"
                )
            )
            painter.setPen(QPen(border_color, 3 if is_selected else 2))
            painter.setBrush(fill_color)
            painter.drawRoundedRect(box_rect, 8, 8)

            inner_rect = box_rect.adjusted(6.0, 6.0, -6.0, -6.0)
            painter.setPen(QPen(QColor("#8A8F85"), 1))
            painter.drawRoundedRect(inner_rect, 5, 5)

            text_rect = box_rect.adjusted(4.0, 4.0, -4.0, -22.0)
            painter.setPen(QColor("#23312B"))
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                box.label,
            )

            badge_rect = QRectF(
                box_rect.left() + 4.0,
                box_rect.bottom() - 20.0,
                box_rect.width() - 8.0,
                16.0,
            )
            badge_color = QColor(box_view_model.badge_hex if box_view_model is not None else "#5F6B66")
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(badge_color)
            painter.drawRoundedRect(badge_rect, 6, 6)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(
                badge_rect,
                Qt.AlignmentFlag.AlignCenter,
                box_view_model.badge_text if box_view_model is not None else "Sin datos",
            )

        super().paintEvent(event)

    def _paint_background(self, painter: QPainter, map_rect: QRectF) -> None:
        painter.save()
        painter.setClipRect(map_rect)
        if not self._background_pixmap.isNull():
            scaled = self._background_pixmap.scaled(
                map_rect.size().toSize(),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawPixmap(map_rect.topLeft(), scaled)
            painter.restore()
            return

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#F2F7D8"))
        painter.drawRoundedRect(map_rect, 24, 24)

        island_path = QPainterPath()
        island_path.moveTo(map_rect.left() + map_rect.width() * 0.42, map_rect.top() + map_rect.height() * 0.03)
        island_path.cubicTo(
            map_rect.left() + map_rect.width() * 0.24,
            map_rect.top() + map_rect.height() * 0.20,
            map_rect.left() + map_rect.width() * 0.18,
            map_rect.top() + map_rect.height() * 0.46,
            map_rect.left() + map_rect.width() * 0.26,
            map_rect.top() + map_rect.height() * 0.82,
        )
        island_path.cubicTo(
            map_rect.left() + map_rect.width() * 0.38,
            map_rect.top() + map_rect.height() * 0.98,
            map_rect.left() + map_rect.width() * 0.70,
            map_rect.top() + map_rect.height() * 0.96,
            map_rect.left() + map_rect.width() * 0.86,
            map_rect.top() + map_rect.height() * 0.60,
        )
        island_path.cubicTo(
            map_rect.left() + map_rect.width() * 0.94,
            map_rect.top() + map_rect.height() * 0.41,
            map_rect.left() + map_rect.width() * 0.74,
            map_rect.top() + map_rect.height() * 0.29,
            map_rect.left() + map_rect.width() * 0.61,
            map_rect.top() + map_rect.height() * 0.17,
        )
        island_path.cubicTo(
            map_rect.left() + map_rect.width() * 0.54,
            map_rect.top() + map_rect.height() * 0.11,
            map_rect.left() + map_rect.width() * 0.51,
            map_rect.top() + map_rect.height() * 0.03,
            map_rect.left() + map_rect.width() * 0.42,
            map_rect.top() + map_rect.height() * 0.03,
        )
        painter.setBrush(QColor("#F6F9E8"))
        painter.drawPath(island_path)
        painter.setPen(QPen(QColor("#A4B57D"), 1.5))
        painter.drawPath(island_path)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(170, 197, 107, 70))
        center_island = QRectF(
            map_rect.left() + map_rect.width() * 0.44,
            map_rect.top() + map_rect.height() * 0.42,
            map_rect.width() * 0.22,
            map_rect.height() * 0.22,
        )
        painter.drawEllipse(center_island)
        painter.restore()

    def _map_rect(self, available_rect: QRectF) -> QRectF:
        padded = available_rect.adjusted(16.0, 16.0, -16.0, -16.0)
        if padded.width() <= 0 or padded.height() <= 0:
            return padded
        desired_ratio = float(self._layout_contract.aspect_ratio)
        available_ratio = padded.width() / padded.height()
        if available_ratio > desired_ratio:
            width = padded.height() * desired_ratio
            x = padded.left() + (padded.width() - width) / 2.0
            return QRectF(x, padded.top(), width, padded.height())
        height = padded.width() / desired_ratio
        y = padded.top() + (padded.height() - height) / 2.0
        return QRectF(padded.left(), y, padded.width(), height)

    @staticmethod
    def _load_background_pixmap(asset_path: str | None) -> QPixmap:
        if not isinstance(asset_path, str) or not asset_path.strip():
            return QPixmap()
        repo_root = Path(__file__).resolve().parents[4]
        resolved = repo_root / asset_path
        if not resolved.exists():
            return QPixmap()
        pixmap = QPixmap(str(resolved))
        return pixmap if not pixmap.isNull() else QPixmap()
