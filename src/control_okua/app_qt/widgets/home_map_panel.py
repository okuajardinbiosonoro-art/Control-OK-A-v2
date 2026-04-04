from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
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
        self.setMinimumHeight(600)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    @property
    def asset_path(self) -> Path:
        return self._asset_path

    def has_map_asset(self) -> bool:
        return not self._map_pixmap.isNull()

    def sizeHint(self) -> QSize:
        return QSize(1600, 980)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        outer_rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        painter.fillRect(outer_rect, QColor("#F7F4EC"))

        panel_path = QPainterPath()
        panel_path.addRoundedRect(outer_rect, 22.0, 22.0)
        painter.fillPath(panel_path, QColor("#FFFEFB"))
        painter.setPen(QPen(QColor(BRAND_SAND), 0.7))
        painter.drawPath(panel_path)

        map_rect = outer_rect.adjusted(4.0, 4.0, -4.0, -4.0)
        painter.save()
        clip_path = QPainterPath()
        clip_path.addRoundedRect(map_rect, 18.0, 18.0)
        painter.setClipPath(clip_path)
        painter.fillRect(map_rect, QColor("#F4F7F0"))

        if not self._map_pixmap.isNull():
            scaled = self._map_pixmap.scaled(
                map_rect.size().toSize(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            draw_x = map_rect.left() + (map_rect.width() - scaled.width()) / 2.0
            draw_y = map_rect.top() + (map_rect.height() - scaled.height()) / 2.0
            painter.drawPixmap(int(draw_x), int(draw_y), scaled)
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
        painter.drawRoundedRect(map_rect, 18.0, 18.0)

    @staticmethod
    def _load_pixmap(asset_path: Path) -> QPixmap:
        if not asset_path.exists():
            return QPixmap()
        pixmap = QPixmap(str(asset_path))
        return pixmap if not pixmap.isNull() else QPixmap()
