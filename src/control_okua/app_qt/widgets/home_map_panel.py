from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from control_okua.app_qt.navigation_shell import BRAND_ACCENT, BRAND_DEEP, BRAND_SAND


def resolve_home_map_asset_path() -> Path:
    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).resolve().parent
    else:
        base_dir = Path(__file__).resolve().parents[4]
    return base_dir / "assets" / "maps" / "okua_home_base.png"


class HomeMapPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._asset_path = resolve_home_map_asset_path()
        self._map_pixmap = self._load_pixmap(self._asset_path)
        self._map_source_rect = self._resolve_content_rect(self._map_pixmap.toImage())
        self.setMinimumHeight(480)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    @property
    def asset_path(self) -> Path:
        return self._asset_path

    def has_map_asset(self) -> bool:
        return not self._map_pixmap.isNull()

    def sizeHint(self) -> QSize:
        return QSize(1560, 920)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        outer_rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        painter.fillRect(outer_rect, QColor("#F7F4EC"))

        panel_path = QPainterPath()
        panel_path.addRoundedRect(outer_rect, 24.0, 24.0)
        painter.fillPath(panel_path, QColor("#FFFEFB"))
        painter.setPen(QPen(QColor(BRAND_SAND), 0.8))
        painter.drawPath(panel_path)

        map_rect = outer_rect.adjusted(2.0, 2.0, -2.0, -2.0)
        painter.save()
        clip_path = QPainterPath()
        clip_path.addRoundedRect(map_rect, 22.0, 22.0)
        painter.setClipPath(clip_path)
        painter.fillRect(map_rect, QColor("#F4F7F0"))

        if not self._map_pixmap.isNull():
            source_rect = self._map_source_rect if self._map_source_rect is not None else QRectF(self._map_pixmap.rect())
            source_size = source_rect.size()
            if source_size.width() > 0 and source_size.height() > 0:
                scale = min(
                    map_rect.width() / source_size.width(),
                    map_rect.height() / source_size.height(),
                )
                target_width = source_size.width() * scale
                target_height = source_size.height() * scale
                target_rect = QRectF(
                    map_rect.left() + (map_rect.width() - target_width) / 2.0,
                    map_rect.top() + (map_rect.height() - target_height) / 2.0,
                    target_width,
                    target_height,
                )
                painter.drawPixmap(target_rect, self._map_pixmap, source_rect)
        else:
            painter.fillRect(map_rect, QColor("#F4F0E6"))
            painter.setPen(QColor(BRAND_DEEP))
            painter.drawText(
                map_rect,
                Qt.AlignmentFlag.AlignCenter,
                "Mapa no disponible",
            )

        painter.restore()
        painter.setPen(QPen(QColor(BRAND_ACCENT), 1.0))
        painter.drawRoundedRect(map_rect, 22.0, 22.0)

    @staticmethod
    def _load_pixmap(asset_path: Path) -> QPixmap:
        if not asset_path.exists():
            return QPixmap()
        pixmap = QPixmap(str(asset_path))
        return pixmap if not pixmap.isNull() else QPixmap()

    @staticmethod
    def _resolve_content_rect(image: QImage) -> QRectF | None:
        if image.isNull():
            return None
        if not image.hasAlphaChannel():
            return QRectF(image.rect())

        left = image.width()
        top = image.height()
        right = -1
        bottom = -1
        for y in range(image.height()):
            for x in range(image.width()):
                if QColor.fromRgba(image.pixel(x, y)).alpha() <= 8:
                    continue
                left = min(left, x)
                top = min(top, y)
                right = max(right, x)
                bottom = max(bottom, y)

        if right < left or bottom < top:
            return QRectF(image.rect())
        return QRectF(left, top, right - left + 1, bottom - top + 1)
