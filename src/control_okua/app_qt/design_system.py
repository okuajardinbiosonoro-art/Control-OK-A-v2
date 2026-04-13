from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor

from control_okua.core.registry import NodeStatus

APP_BRAND_LABEL = "OKÚA"
APP_EDITION_LABEL = "Control CKv2"
APP_DISPLAY_NAME = "Control OKÚA · CKv2"
APP_ABOUT_NAME = "Control OKÚA CKv2"

BRAND_ACCENT = "#2FAC66"
BRAND_DEEP = "#0B3B27"
BRAND_EARTH = "#432918"
BRAND_SAND = "#CBBBA0"


@dataclass(frozen=True)
class NodeStatusVisual:
    accent_hex: str
    table_text_hex: str
    map_halo_rgba: tuple[int, int, int, int]
    map_fill_rgba: tuple[int, int, int, int]
    map_badge_rgba: tuple[int, int, int, int]


@dataclass(frozen=True)
class ToastLevelVisual:
    background_hex: str
    border_hex: str
    title_hex: str
    message_hex: str
    accent_hex: str


_NODE_STATUS_VISUALS: dict[NodeStatus, NodeStatusVisual] = {
    NodeStatus.ONLINE: NodeStatusVisual(
        accent_hex="#2FAC66",
        table_text_hex="#248B52",
        map_halo_rgba=(47, 172, 102, 42),
        map_fill_rgba=(246, 253, 249, 242),
        map_badge_rgba=(238, 250, 243, 244),
    ),
    NodeStatus.CALIBRATING: NodeStatusVisual(
        accent_hex="#2F7ED8",
        table_text_hex="#1D67B8",
        map_halo_rgba=(47, 126, 216, 40),
        map_fill_rgba=(246, 250, 255, 242),
        map_badge_rgba=(239, 246, 255, 244),
    ),
    NodeStatus.DEGRADED: NodeStatusVisual(
        accent_hex="#DD8A12",
        table_text_hex="#B06A07",
        map_halo_rgba=(221, 138, 18, 42),
        map_fill_rgba=(255, 250, 244, 242),
        map_badge_rgba=(255, 246, 235, 244),
    ),
    NodeStatus.OFFLINE: NodeStatusVisual(
        accent_hex="#C45245",
        table_text_hex="#A33E35",
        map_halo_rgba=(196, 82, 69, 42),
        map_fill_rgba=(255, 248, 247, 242),
        map_badge_rgba=(255, 239, 237, 244),
    ),
}

_TOAST_LEVEL_VISUALS: dict[str, ToastLevelVisual] = {
    "info": ToastLevelVisual("#FFFDF9", "#DCCFB8", "#0B3B27", "#4F6259", "#DCCFB8"),
    "success": ToastLevelVisual("#EFF8F1", "#ACD8BA", "#0B3B27", "#3F5E51", "#79C195"),
    "warning": ToastLevelVisual("#FFF6EA", "#E0C187", "#432918", "#6A5139", "#D8A64D"),
    "error": ToastLevelVisual("#FFF1EF", "#D9978B", "#7B2C20", "#7B2C20", "#CD6A5D"),
}


def coerce_node_status(raw_status: object) -> NodeStatus:
    if isinstance(raw_status, NodeStatus):
        return raw_status
    raw_value = getattr(raw_status, "value", raw_status)
    try:
        normalized = str(raw_value).strip().lower()
    except Exception:
        normalized = ""
    for candidate in NodeStatus:
        if candidate.value == normalized:
            return candidate
    return NodeStatus.OFFLINE


def node_status_visual(raw_status: object) -> NodeStatusVisual:
    return _NODE_STATUS_VISUALS[coerce_node_status(raw_status)]


def node_status_table_color(raw_status: object) -> QColor:
    return QColor(node_status_visual(raw_status).table_text_hex)


def node_status_map_style(raw_status: object) -> dict[str, QColor]:
    visual = node_status_visual(raw_status)
    return {
        "accent": QColor(visual.accent_hex),
        "halo": QColor(*visual.map_halo_rgba),
        "fill": QColor(*visual.map_fill_rgba),
        "badge_fill": QColor(*visual.map_badge_rgba),
    }


def normalize_toast_level(level: str | None) -> str:
    normalized = str(level or "").strip().lower()
    return normalized if normalized in _TOAST_LEVEL_VISUALS else "info"


def toast_level_visual(level: str | None) -> ToastLevelVisual:
    return _TOAST_LEVEL_VISUALS[normalize_toast_level(level)]
