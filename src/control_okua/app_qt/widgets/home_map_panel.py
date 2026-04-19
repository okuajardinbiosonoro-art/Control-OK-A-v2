from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from control_okua.app_qt.contracts.home_map_layout_contract import (
    DEFAULT_HOME_MAP_BOXES,
    HomeMapBoxSpec,
    resolve_home_map_box,
)
from control_okua.app_qt.navigation_shell import BRAND_ACCENT, BRAND_DEEP, BRAND_SAND
from control_okua.app_qt.design_system import node_status_map_style
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
    from control_okua.app_qt.resources import resource_path
    return resource_path("assets/maps/okua_home_base.png")


class HomeMapPanel(QWidget):
    boxSelectionChanged = Signal(object)
    viewNodesRequested = Signal(str)
    _MAP_FRAME_INSET = 3.0
    _MAP_CONTENT_GAP = 4.0
    _ANIMATION_TICK_MS = 33
    _STATUS_TRANSITION_DURATION_S = 0.28
    _SELECTION_TRANSITION_DURATION_S = 0.18
    _STATUS_STYLE = {status: node_status_map_style(status) for status in NodeStatus}

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
        self._context_action_rect: QRectF | None = None
        self._context_action_hovered = False
        self._status_transition_by_box_key: dict[str, tuple[NodeStatus, float]] = {}
        self._selection_transition: tuple[str | None, str | None, float] | None = None
        self._animation_timer = QTimer(self)
        self._animation_timer.setInterval(self._ANIMATION_TICK_MS)
        self._animation_timer.timeout.connect(self._on_animation_tick)
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
        previous_key = self._selected_box_key
        self._selection_transition = (previous_key, canonical_key, time.monotonic())
        self._selected_box_key = canonical_key
        self.boxSelectionChanged.emit(self.selected_box())
        self._ensure_animation_running()
        self.update()

    def request_view_nodes_for_selected_box(self) -> None:
        if self._selected_box_key is None:
            return
        self.viewNodesRequested.emit(self._selected_box_key)

    def set_box_states(self, box_states: tuple[HomeMapBoxState, ...] | list[HomeMapBoxState] | None) -> None:
        resolved_states = tuple(box_states or ())
        if resolved_states == self._box_states:
            return
        previous_status_by_key = {
            state.box_key: state.aggregated_status
            for state in self._box_states
        }
        self._box_states = resolved_states
        self._box_states_by_key = {state.box_key: state for state in resolved_states}
        now_monotonic = time.monotonic()
        has_status_transition = False
        for state in resolved_states:
            previous_status = previous_status_by_key.get(state.box_key)
            if previous_status is None or previous_status is state.aggregated_status:
                continue
            self._status_transition_by_box_key[state.box_key] = (previous_status, now_monotonic)
            has_status_transition = True
        if has_status_transition:
            self._ensure_animation_running()
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

        frame_rect = self._map_frame_rect()
        content_rect = self._map_content_rect()
        target_rect = self._resolved_map_target_rect()

        frame_path = QPainterPath()
        frame_path.addRoundedRect(frame_rect, 22.0, 22.0)
        painter.fillPath(frame_path, QColor("#F4F7F0"))

        painter.save()
        clip_path = QPainterPath()
        clip_path.addRoundedRect(content_rect, 20.0, 20.0)
        painter.setClipPath(clip_path)
        painter.fillRect(content_rect, QColor("#F4F7F0"))

        if not self._map_pixmap.isNull():
            source_rect = self._map_source_rect if self._map_source_rect is not None else QRectF(self._map_pixmap.rect())
            if target_rect is not None and source_rect.width() > 0 and source_rect.height() > 0:
                painter.drawPixmap(target_rect, self._map_pixmap, source_rect)
        else:
            painter.fillRect(content_rect, QColor("#F4F0E6"))
            painter.setPen(QColor(BRAND_DEEP))
            painter.drawText(
                content_rect,
                Qt.AlignmentFlag.AlignCenter,
                "Mapa no disponible",
            )

        painter.restore()
        painter.setPen(QPen(QColor(BRAND_ACCENT), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(frame_rect, 22.0, 22.0)
        if target_rect is not None:
            self._draw_box_overlays(painter, target_rect)
        self._draw_context_card(painter, frame_rect)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            if self._context_action_rect is not None and self._context_action_rect.contains(event.position()):
                self.request_view_nodes_for_selected_box()
                event.accept()
                return
            hovered_spec = self._spec_at_position(event.position())
            if hovered_spec is not None:
                self.select_box(hovered_spec.box_key)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        hovered_action = bool(
            self._context_action_rect is not None and self._context_action_rect.contains(event.position())
        )
        hovered_spec = self._spec_at_position(event.position())
        hovered_key = hovered_spec.box_key if hovered_spec is not None else None
        if hovered_key != self._hovered_box_key or hovered_action != self._context_action_hovered:
            self._hovered_box_key = hovered_key
            self._context_action_hovered = hovered_action
            self.setCursor(
                Qt.CursorShape.PointingHandCursor
                if hovered_key is not None or hovered_action
                else Qt.CursorShape.ArrowCursor
            )
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self._hovered_box_key = None
        self._context_action_hovered = False
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
        map_rect = self._map_content_rect()
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

    def _map_frame_rect(self) -> QRectF:
        outer_rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        return outer_rect.adjusted(
            self._MAP_FRAME_INSET,
            self._MAP_FRAME_INSET,
            -self._MAP_FRAME_INSET,
            -self._MAP_FRAME_INSET,
        )

    def _map_content_rect(self) -> QRectF:
        return self._map_frame_rect().adjusted(
            self._MAP_CONTENT_GAP,
            self._MAP_CONTENT_GAP,
            -self._MAP_CONTENT_GAP,
            -self._MAP_CONTENT_GAP,
        )

    def _marker_rect_for_spec(self, spec: HomeMapBoxSpec, map_rect: QRectF) -> QRectF:
        width = max(42.0, map_rect.width() * spec.normalized_size[0] * 1.1)
        height = max(36.0, map_rect.height() * spec.normalized_size[1] * 1.12)
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
            style = self._resolved_style_for_box(spec.box_key, status)
            is_selected = spec.box_key == self._selected_box_key
            is_hovered = spec.box_key == self._hovered_box_key
            selection_strength = self._selection_strength_for_box(
                spec.box_key,
                is_selected=is_selected,
                is_hovered=is_hovered,
            )
            base_font = painter.font()
            body_rect = marker_rect.adjusted(4.0, 4.0, -4.0, -4.0)
            dot_diameter = 8.0 + selection_strength
            dot_rect = QRectF(
                body_rect.right() - dot_diameter - 5.0,
                body_rect.top() + 5.0,
                dot_diameter,
                dot_diameter,
            )
            accent_rail_rect = QRectF(
                body_rect.left() + 5.0,
                body_rect.top() + 5.0,
                3.5,
                body_rect.height() - 10.0,
            )
            number_rect = QRectF(
                body_rect.left() + 10.0,
                body_rect.top() + 4.0,
                body_rect.width() - 20.0,
                body_rect.height() - 8.0,
            )

            if selection_strength > 0.0 or is_hovered:
                glow_rect = body_rect.adjusted(-5.0, -5.0, 5.0, 5.0)
                glow_fill = QColor(style["halo"])
                glow_alpha = 34 + int(52.0 * selection_strength) + (10 if is_hovered else 0)
                glow_fill.setAlpha(max(24, min(98, glow_alpha)))
                glow_border = QColor(style["accent"])
                glow_border.setAlpha(48 + int(70.0 * selection_strength))
                painter.setPen(QPen(glow_border, 0.9 + (0.7 * selection_strength)))
                painter.setBrush(glow_fill)
                painter.drawRoundedRect(glow_rect, 14.0, 14.0)

            shadow_rect = body_rect.translated(1.5, 2.0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(26, 37, 31, 18))
            painter.drawRoundedRect(shadow_rect, 12.0, 12.0)

            marker_fill = QColor(style["fill"])
            marker_fill.setAlpha(max(236, min(255, 242 + int(13.0 * selection_strength) + (4 if is_hovered else 0))))
            painter.setBrush(marker_fill)
            painter.setPen(QPen(QColor(style["accent"]), 1.1 + (0.7 * selection_strength)))
            painter.drawRoundedRect(body_rect, 12.0, 12.0)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(style["accent"]))
            painter.drawRoundedRect(accent_rail_rect, 2.0, 2.0)

            painter.setBrush(QColor(style["accent"]))
            painter.drawEllipse(dot_rect)
            painter.setPen(QPen(QColor(255, 255, 255, 228), 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(dot_rect.adjusted(0.8, 0.8, -0.8, -0.8))

            number_font = painter.font()
            number_font.setBold(True)
            number_font.setPointSize(max(9, number_font.pointSize() + 2))
            painter.setFont(number_font)
            painter.setPen(QColor(BRAND_DEEP))
            painter.drawText(
                number_rect,
                Qt.AlignmentFlag.AlignCenter,
                str(spec.box_index),
            )
            painter.setFont(base_font)

    def _draw_context_card(self, painter: QPainter, map_rect: QRectF) -> None:
        self._context_action_rect = None
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
            state_style = self._resolved_style_for_box(selected_box.box_key, selected_state.aggregated_status)
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

        action_rect = QRectF(card_rect.right() - 112.0, card_rect.bottom() - 34.0, 94.0, 20.0)
        self._context_action_rect = action_rect
        action_fill = QColor("#F5EDDD" if not self._context_action_hovered else "#EDE0C8")
        action_border = QColor("#D8C3A0" if not self._context_action_hovered else "#BB9C6C")
        painter.setPen(QPen(action_border, 1.0))
        painter.setBrush(action_fill)
        painter.drawRoundedRect(action_rect, 10.0, 10.0)
        action_font = painter.font()
        action_font.setBold(True)
        action_font.setPointSize(max(8, action_font.pointSize() - 1))
        painter.setFont(action_font)
        painter.setPen(QColor(BRAND_DEEP))
        painter.drawText(
            action_rect.adjusted(0.0, 0.0, -8.0, 0.0),
            Qt.AlignmentFlag.AlignCenter,
            "Ver nodos",
        )
        painter.drawText(
            QRectF(action_rect.right() - 16.0, action_rect.top(), 10.0, action_rect.height()),
            Qt.AlignmentFlag.AlignCenter,
            "›",
        )

    def _on_animation_tick(self) -> None:
        now_monotonic = time.monotonic()
        self._cleanup_finished_transitions(now_monotonic)
        if not self._has_active_visual_transition():
            self._animation_timer.stop()
            return
        self.update()

    def _ensure_animation_running(self) -> None:
        if not self._animation_timer.isActive():
            self._animation_timer.start()

    def _cleanup_finished_transitions(self, now_monotonic: float) -> None:
        completed_status_keys = [
            box_key
            for box_key, (_, started_at) in self._status_transition_by_box_key.items()
            if (now_monotonic - started_at) >= self._STATUS_TRANSITION_DURATION_S
        ]
        for box_key in completed_status_keys:
            self._status_transition_by_box_key.pop(box_key, None)

        if self._selection_transition is not None:
            _, _, started_at = self._selection_transition
            if (now_monotonic - started_at) >= self._SELECTION_TRANSITION_DURATION_S:
                self._selection_transition = None

    def _selection_strength_for_box(
        self,
        box_key: str,
        *,
        is_selected: bool,
        is_hovered: bool,
    ) -> float:
        strength = 1.0 if is_selected else 0.0
        if is_hovered and not is_selected:
            strength = max(strength, 0.35)
        if self._selection_transition is None:
            return strength

        from_key, to_key, started_at = self._selection_transition
        progress = self._transition_progress(
            now_monotonic=time.monotonic(),
            started_at=started_at,
            duration_s=self._SELECTION_TRANSITION_DURATION_S,
        )
        eased = self._smooth_step(progress)
        if box_key == from_key:
            strength = max(strength, 1.0 - eased)
        if box_key == to_key:
            strength = max(strength, eased)
        return strength

    def _resolved_style_for_box(self, box_key: str, status: NodeStatus) -> dict[str, QColor]:
        target_style = self._STATUS_STYLE[status]
        transition = self._status_transition_by_box_key.get(box_key)
        if transition is None:
            return target_style

        source_status, started_at = transition
        source_style = self._STATUS_STYLE[source_status]
        progress = self._transition_progress(
            now_monotonic=time.monotonic(),
            started_at=started_at,
            duration_s=self._STATUS_TRANSITION_DURATION_S,
        )
        eased = self._smooth_step(progress)
        return {
            key: self._blend_color(source_style[key], target_style[key], eased)
            for key in target_style.keys()
        }

    def _has_active_visual_transition(self) -> bool:
        return bool(self._status_transition_by_box_key) or self._selection_transition is not None

    @staticmethod
    def _transition_progress(*, now_monotonic: float, started_at: float, duration_s: float) -> float:
        if duration_s <= 0.0:
            return 1.0
        elapsed = max(0.0, now_monotonic - started_at)
        return min(1.0, elapsed / duration_s)

    @staticmethod
    def _smooth_step(progress: float) -> float:
        clamped = max(0.0, min(1.0, float(progress)))
        return clamped * clamped * (3.0 - (2.0 * clamped))

    @staticmethod
    def _blend_color(source: QColor, target: QColor, weight: float) -> QColor:
        ratio = max(0.0, min(1.0, float(weight)))
        inverse = 1.0 - ratio
        return QColor(
            int((source.red() * inverse) + (target.red() * ratio)),
            int((source.green() * inverse) + (target.green() * ratio)),
            int((source.blue() * inverse) + (target.blue() * ratio)),
            int((source.alpha() * inverse) + (target.alpha() * ratio)),
        )
