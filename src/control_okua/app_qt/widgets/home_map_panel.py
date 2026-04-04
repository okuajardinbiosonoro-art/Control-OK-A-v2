from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from control_okua.app_qt.contracts.home_map_layout_contract import (
    DEFAULT_HOME_MAP_BOXES,
    HomeMapBoxSpec,
    resolve_home_map_box,
)
from control_okua.app_qt.navigation_shell import BRAND_ACCENT, BRAND_DEEP, BRAND_SAND
from control_okua.app_qt.viewmodels.home_map_state_vm import (
    HomeMapBoxState,
    build_home_map_box_states,
)
from control_okua.app_qt.viewmodels.home_map_detail_vm import (
    HomeMapBoxDetailState,
    build_home_map_box_detail_states,
)
from control_okua.core.registry import NodeStatus


def resolve_home_map_asset_path() -> Path:
    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).resolve().parent
    else:
        base_dir = Path(__file__).resolve().parents[4]
    return base_dir / "assets" / "maps" / "okua_home_base.png"


class HomeMapPanel(QWidget):
    boxSelectionChanged = Signal(object)
    _STATUS_STYLE = {
        NodeStatus.ONLINE: {
            "accent": QColor("#2FAC66"),
            "halo": QColor(47, 172, 102, 42),
            "fill": QColor(246, 253, 249, 242),
            "badge_fill": QColor(238, 250, 243, 244),
        },
        NodeStatus.CALIBRATING: {
            "accent": QColor("#2F7ED8"),
            "halo": QColor(47, 126, 216, 40),
            "fill": QColor(246, 250, 255, 242),
            "badge_fill": QColor(239, 246, 255, 244),
        },
        NodeStatus.DEGRADED: {
            "accent": QColor("#DD8A12"),
            "halo": QColor(221, 138, 18, 42),
            "fill": QColor(255, 250, 244, 242),
            "badge_fill": QColor(255, 246, 235, 244),
        },
        NodeStatus.OFFLINE: {
            "accent": QColor("#C45245"),
            "halo": QColor(196, 82, 69, 42),
            "fill": QColor(255, 248, 247, 242),
            "badge_fill": QColor(255, 239, 237, 244),
        },
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._asset_path = resolve_home_map_asset_path()
        self._map_pixmap = self._load_pixmap(self._asset_path)
        self._map_source_rect = self._resolve_content_rect(self._map_pixmap.toImage())
        self._box_specs = DEFAULT_HOME_MAP_BOXES
        self._box_states = build_home_map_box_states(node_snapshots=None, box_specs=self._box_specs)
        self._box_states_by_key = {state.box_key: state for state in self._box_states}
        self._box_details = build_home_map_box_detail_states(node_snapshots=None, box_specs=self._box_specs)
        self._box_details_by_key = {detail.box_key: detail for detail in self._box_details}
        self._selected_box_key: str | None = None
        self._hovered_box_key: str | None = None
        self.setMinimumHeight(480)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

    @property
    def asset_path(self) -> Path:
        return self._asset_path

    def box_specs(self) -> tuple[HomeMapBoxSpec, ...]:
        return self._box_specs

    def box_states(self) -> tuple[HomeMapBoxState, ...]:
        return self._box_states

    def box_state(self, box_key: str) -> HomeMapBoxState | None:
        canonical_key = str(box_key).strip().lower()
        return self._box_states_by_key.get(canonical_key)

    def has_map_asset(self) -> bool:
        return not self._map_pixmap.isNull()

    def selected_box(self) -> HomeMapBoxSpec | None:
        if self._selected_box_key is None:
            return None
        return resolve_home_map_box(self._selected_box_key)

    def selected_box_state(self) -> HomeMapBoxState | None:
        if self._selected_box_key is None:
            return None
        return self._box_states_by_key.get(self._selected_box_key)

    def selected_box_detail(self) -> HomeMapBoxDetailState | None:
        if self._selected_box_key is None:
            return None
        return self._box_details_by_key.get(self._selected_box_key)

    def select_box(self, box_key: str | None) -> None:
        canonical_key = str(box_key).strip().lower() if isinstance(box_key, str) else None
        if canonical_key == self._selected_box_key:
            return
        self._selected_box_key = canonical_key
        self.boxSelectionChanged.emit(self.selected_box())
        self.update()

    def set_box_states(self, box_states: tuple[HomeMapBoxState, ...] | list[HomeMapBoxState] | None) -> None:
        resolved_states = tuple(box_states or ())
        if resolved_states == self._box_states:
            return
        self._box_states = resolved_states
        self._box_states_by_key = {state.box_key: state for state in resolved_states}
        self.update()

    def set_box_details(
        self,
        box_details: tuple[HomeMapBoxDetailState, ...] | list[HomeMapBoxDetailState] | None,
    ) -> None:
        resolved_details = tuple(box_details or ())
        if resolved_details == self._box_details:
            return
        self._box_details = resolved_details
        self._box_details_by_key = {detail.box_key: detail for detail in resolved_details}
        self.update()

    def box_screen_rect(self, box_key: str) -> QRectF | None:
        spec = resolve_home_map_box(box_key)
        if spec is None:
            return None
        map_rect = self._resolved_map_target_rect()
        if map_rect is None:
            return None
        return self._marker_rect_for_spec(spec, map_rect)

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
        self._draw_box_overlays(painter, map_rect)
        self._draw_context_card(painter, map_rect)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            hovered_spec = self._spec_at_position(event.position())
            if hovered_spec is not None:
                self.select_box(hovered_spec.box_key)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        hovered_spec = self._spec_at_position(event.position())
        hovered_key = hovered_spec.box_key if hovered_spec is not None else None
        if hovered_key != self._hovered_box_key:
            self._hovered_box_key = hovered_key
            self.setCursor(
                Qt.CursorShape.PointingHandCursor
                if hovered_key is not None
                else Qt.CursorShape.ArrowCursor
            )
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self._hovered_box_key = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()
        super().leaveEvent(event)

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
        left = image.width()
        top = image.height()
        right = -1
        bottom = -1
        for y in range(image.height()):
            for x in range(image.width()):
                pixel = QColor.fromRgba(image.pixel(x, y))
                if pixel.alpha() <= 8:
                    continue
                if pixel.red() >= 250 and pixel.green() >= 250 and pixel.blue() >= 250:
                    continue
                left = min(left, x)
                top = min(top, y)
                right = max(right, x)
                bottom = max(bottom, y)

        if right < left or bottom < top:
            return QRectF(image.rect())
        return QRectF(left, top, right - left + 1, bottom - top + 1)

    def _resolved_map_target_rect(self) -> QRectF | None:
        outer_rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        map_rect = outer_rect.adjusted(2.0, 2.0, -2.0, -2.0)
        if self._map_pixmap.isNull():
            return map_rect

        source_rect = self._map_source_rect if self._map_source_rect is not None else QRectF(self._map_pixmap.rect())
        source_size = source_rect.size()
        if source_size.width() <= 0 or source_size.height() <= 0:
            return map_rect
        scale = min(
            map_rect.width() / source_size.width(),
            map_rect.height() / source_size.height(),
        )
        target_width = source_size.width() * scale
        target_height = source_size.height() * scale
        return QRectF(
            map_rect.left() + (map_rect.width() - target_width) / 2.0,
            map_rect.top() + (map_rect.height() - target_height) / 2.0,
            target_width,
            target_height,
        )

    def _marker_rect_for_spec(self, spec: HomeMapBoxSpec, map_rect: QRectF) -> QRectF:
        width = max(36.0, map_rect.width() * spec.normalized_size[0] * 1.06)
        height = max(34.0, map_rect.height() * spec.normalized_size[1] * 1.08)
        center_x = map_rect.left() + (map_rect.width() * spec.normalized_center[0])
        center_y = map_rect.top() + (map_rect.height() * spec.normalized_center[1])
        return QRectF(center_x - (width / 2.0), center_y - (height / 2.0), width, height)

    def _spec_at_position(self, position: QPointF) -> HomeMapBoxSpec | None:
        map_rect = self._resolved_map_target_rect()
        if map_rect is None:
            return None
        for spec in self._box_specs:
            if self._marker_rect_for_spec(spec, map_rect).adjusted(-10.0, -10.0, 10.0, 10.0).contains(position):
                return spec
        return None

    def _draw_box_overlays(self, painter: QPainter, map_rect: QRectF) -> None:
        for spec in self._box_specs:
            marker_rect = self._marker_rect_for_spec(spec, map_rect)
            state = self._box_states_by_key.get(spec.box_key)
            status = NodeStatus.OFFLINE if state is None else state.aggregated_status
            style = self._STATUS_STYLE[status]
            is_selected = spec.box_key == self._selected_box_key
            is_hovered = spec.box_key == self._hovered_box_key

            halo_rect = marker_rect.adjusted(-7.0, -7.0, 7.0, 7.0)
            halo_fill = QColor(style["halo"])
            if is_selected:
                halo_fill.setAlpha(76)
            elif is_hovered:
                halo_fill.setAlpha(56)
            halo_border = QColor(style["accent"])
            painter.setPen(QPen(halo_border, 1.8 if (is_selected or is_hovered) else 1.2))
            painter.setBrush(halo_fill)
            painter.drawEllipse(halo_rect)

            marker_path = QPainterPath()
            marker_path.addRoundedRect(marker_rect, 10.0, 10.0)
            marker_fill = QColor(style["fill"])
            if is_selected:
                marker_fill.setAlpha(255)
            elif is_hovered:
                marker_fill.setAlpha(248)
            painter.fillPath(marker_path, marker_fill)
            painter.setPen(QPen(QColor(style["accent"]), 1.8 if is_selected else 1.25))
            painter.drawPath(marker_path)

            status_dot_rect = QRectF(marker_rect.right() - 10.0, marker_rect.top() - 2.0, 10.0, 10.0)
            painter.setPen(QPen(QColor("#FFFEFB"), 1.2))
            painter.setBrush(QColor(style["accent"]))
            painter.drawEllipse(status_dot_rect)

            painter.setPen(QColor(BRAND_DEEP))
            painter.drawText(
                marker_rect,
                Qt.AlignmentFlag.AlignCenter,
                str(spec.box_index),
            )

            if state is not None:
                base_font = painter.font()
                badge_rect = QRectF(
                    marker_rect.center().x() - 19.0,
                    marker_rect.bottom() + 5.0,
                    38.0,
                    16.0,
                )
                if badge_rect.bottom() > map_rect.bottom() - 4.0:
                    badge_rect.moveTop(marker_rect.top() - 20.0)
                painter.setPen(QPen(QColor(style["accent"]), 1.0))
                painter.setBrush(QColor(style["badge_fill"]))
                painter.drawRoundedRect(badge_rect, 8.0, 8.0)
                badge_font = painter.font()
                badge_font.setPointSize(max(7, badge_font.pointSize() - 1))
                badge_font.setBold(True)
                painter.setFont(badge_font)
                painter.setPen(QColor(style["accent"]))
                painter.drawText(
                    badge_rect,
                    Qt.AlignmentFlag.AlignCenter,
                    state.badge_text,
                )
                painter.setFont(base_font)

    def _draw_context_card(self, painter: QPainter, map_rect: QRectF) -> None:
        selected_box = self.selected_box()
        selected_state = self.selected_box_state()
        selected_detail = self.selected_box_detail()
        if selected_box is None:
            card_rect = QRectF(
                map_rect.left() + 18.0,
                map_rect.bottom() - 56.0,
                156.0,
                38.0,
            )
            painter.setPen(QPen(QColor("#D6C9B3"), 1.0))
            painter.setBrush(QColor(255, 254, 251, 235))
            painter.drawRoundedRect(card_rect, 14.0, 14.0)
            painter.setPen(QColor("#5B6F66"))
            painter.drawText(card_rect.adjusted(12.0, 0.0, -12.0, 0.0), Qt.AlignmentFlag.AlignVCenter, "Seleccione una caja")
            return

        card_rect = QRectF(
            map_rect.left() + 18.0,
            map_rect.bottom() - 254.0,
            min(348.0, map_rect.width() * 0.38),
            236.0,
        )
        card_path = QPainterPath()
        card_path.addRoundedRect(card_rect, 18.0, 18.0)
        painter.fillPath(card_path, QColor(255, 253, 249, 242))
        painter.setPen(QPen(QColor("#D6C9B3"), 1.0))
        painter.drawPath(card_path)

        painter.setPen(QColor(BRAND_DEEP))
        title_rect = QRectF(card_rect.left() + 14.0, card_rect.top() + 10.0, card_rect.width() - 28.0, 22.0)
        title_font = painter.font()
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, selected_box.label)

        body_font = painter.font()
        body_font.setBold(False)
        painter.setFont(body_font)
        if selected_state is not None:
            state_style = self._STATUS_STYLE[selected_state.aggregated_status]
            status_rect = QRectF(card_rect.left() + 14.0, card_rect.top() + 36.0, 126.0, 22.0)
            painter.setPen(QPen(QColor(state_style["accent"]), 1.0))
            painter.setBrush(QColor(state_style["badge_fill"]))
            painter.drawRoundedRect(status_rect, 11.0, 11.0)
            painter.setPen(QColor(state_style["accent"]))
            painter.drawText(
                status_rect,
                Qt.AlignmentFlag.AlignCenter,
                selected_state.status_label,
            )

        painter.setPen(QColor("#53685E"))
        painter.drawText(
            QRectF(card_rect.left() + 14.0, card_rect.top() + 62.0, card_rect.width() - 28.0, 18.0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            (
                f"Nodos esperados: {selected_box.expected_node_count}"
                if selected_state is None
                else selected_state.counts_text
            ),
        )
        painter.drawText(
            QRectF(card_rect.left() + 14.0, card_rect.top() + 80.0, card_rect.width() - 28.0, 18.0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            selected_box.detail_hint if selected_state is None else selected_state.summary_text,
        )
        if selected_detail is None:
            return

        divider_y = card_rect.top() + 107.0
        painter.setPen(QPen(QColor("#E4D9C5"), 1.0))
        painter.drawLine(
            QPointF(card_rect.left() + 14.0, divider_y),
            QPointF(card_rect.right() - 14.0, divider_y),
        )

        list_title_rect = QRectF(card_rect.left() + 14.0, divider_y + 6.0, card_rect.width() - 28.0, 16.0)
        list_title_font = painter.font()
        list_title_font.setBold(True)
        list_title_font.setPointSize(max(8, list_title_font.pointSize() - 1))
        painter.setFont(list_title_font)
        painter.setPen(QColor("#5B6F66"))
        painter.drawText(
            list_title_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "Nodos de la caja",
        )

        row_top = divider_y + 26.0
        row_height = 19.0
        list_body_font = painter.font()
        list_body_font.setBold(False)
        list_body_font.setPointSize(max(8, list_body_font.pointSize() - 1))
        painter.setFont(list_body_font)
        for index, node in enumerate(selected_detail.nodes[:5]):
            row_rect = QRectF(
                card_rect.left() + 12.0,
                row_top + (index * row_height),
                card_rect.width() - 24.0,
                17.0,
            )
            status_style = self._STATUS_STYLE[node.status]
            dot_rect = QRectF(row_rect.left() + 2.0, row_rect.top() + 4.0, 8.0, 8.0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(status_style["accent"]))
            painter.drawEllipse(dot_rect)

            painter.setPen(QColor(BRAND_DEEP))
            painter.drawText(
                QRectF(row_rect.left() + 16.0, row_rect.top(), row_rect.width() - 98.0, row_rect.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                node.display_label,
            )

            badge_rect = QRectF(row_rect.right() - 56.0, row_rect.top() + 1.0, 54.0, 15.0)
            painter.setPen(QPen(QColor(status_style["accent"]), 1.0))
            painter.setBrush(QColor(status_style["badge_fill"]))
            painter.drawRoundedRect(badge_rect, 7.0, 7.0)
            painter.setPen(QColor(status_style["accent"]))
            painter.drawText(
                badge_rect,
                Qt.AlignmentFlag.AlignCenter,
                node.badge_text,
            )
