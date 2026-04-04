from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.contracts.home_map_layout_contract import (  # noqa: E402
    DEFAULT_HOME_MAP_BOXES,
    resolve_home_map_box,
)


def test_home_map_layout_contract_defines_five_boxes_with_expected_node_ranges() -> None:
    assert [spec.label for spec in DEFAULT_HOME_MAP_BOXES] == [
        "Caja 1",
        "Caja 2",
        "Caja 3",
        "Caja 4",
        "Caja 5",
    ]
    assert DEFAULT_HOME_MAP_BOXES[0].expected_node_ids == (1, 2, 3, 4, 5)
    assert DEFAULT_HOME_MAP_BOXES[-1].expected_node_ids == (21, 22, 23, 24, 25)
    assert all(spec.expected_node_count == 5 for spec in DEFAULT_HOME_MAP_BOXES)


def test_home_map_layout_contract_resolves_known_box_keys() -> None:
    resolved = resolve_home_map_box("caja_3")
    assert resolved is not None
    assert resolved.box_index == 3
    assert resolve_home_map_box("missing") is None
