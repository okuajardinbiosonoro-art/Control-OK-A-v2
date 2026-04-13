from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QColor


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.design_system import (  # noqa: E402
    coerce_node_status,
    node_status_map_style,
    node_status_table_color,
    normalize_toast_level,
    toast_level_visual,
)
from control_okua.core.registry import NodeStatus  # noqa: E402


def test_design_system_coerces_node_status_from_mixed_values() -> None:
    assert coerce_node_status(NodeStatus.ONLINE) is NodeStatus.ONLINE
    assert coerce_node_status("calibrating") is NodeStatus.CALIBRATING
    assert coerce_node_status("degraded") is NodeStatus.DEGRADED
    assert coerce_node_status("unknown") is NodeStatus.OFFLINE


def test_design_system_exposes_map_and_table_colors_for_node_status() -> None:
    style = node_status_map_style(NodeStatus.CALIBRATING)

    assert isinstance(style["accent"], QColor)
    assert isinstance(style["fill"], QColor)
    assert style["accent"].name().lower() == "#2f7ed8"
    assert node_status_table_color(NodeStatus.CALIBRATING).name().lower() == "#1d67b8"


def test_design_system_normalizes_toast_levels() -> None:
    assert normalize_toast_level("warning") == "warning"
    assert normalize_toast_level("invalid-value") == "info"
    assert toast_level_visual("error").border_hex == "#D9978B"
