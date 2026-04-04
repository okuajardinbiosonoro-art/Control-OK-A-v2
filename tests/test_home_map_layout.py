from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.contracts import (  # noqa: E402
    DEFAULT_HOME_MAP_LAYOUT,
    get_home_map_box,
)


def test_default_home_map_layout_freezes_five_boxes() -> None:
    layout = DEFAULT_HOME_MAP_LAYOUT
    assert layout.layout_id == "okua_jardin_base_v1"
    assert len(layout.boxes) == 5
    assert tuple(box.box_id for box in layout.boxes) == (4, 2, 3, 1, 5)


def test_home_map_boxes_keep_expected_nodes_and_labels() -> None:
    center_box = get_home_map_box(1)
    assert center_box.label == "Caja 1"
    assert center_box.expected_node_ids == (1, 2)
    assert center_box.expected_node_labels == ("EB1", "EC1")

    right_box = get_home_map_box(5)
    assert right_box.position_slot == "right"
    assert len(right_box.expected_node_ids) == 5
    assert right_box.future_status_hint == "Estado agregado disponible en el siguiente ticket."


def test_home_map_normalized_rects_stay_inside_layout_bounds() -> None:
    for box in DEFAULT_HOME_MAP_LAYOUT.boxes:
        x, y, width, height = box.normalized_rect
        assert 0.0 <= x <= 1.0
        assert 0.0 <= y <= 1.0
        assert width > 0.0
        assert height > 0.0
        assert x + width <= 1.0
        assert y + height <= 1.0
