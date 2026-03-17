from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.node_identity_policy import (  # noqa: E402
    resolve_node_box_index,
    resolve_node_identity,
    resolve_node_midi_bus,
)


def test_node_id_mapping_to_logical_name_and_box_is_deterministic() -> None:
    node_1 = resolve_node_identity(1)
    node_10 = resolve_node_identity(10)
    node_14 = resolve_node_identity(14)

    assert node_1.node_label == "EB1"
    assert node_1.box_label == "Caja 1"
    assert node_10.node_label == "EF2"
    assert node_10.box_label == "Caja 2"
    assert node_14.node_label == "EE3"
    assert node_14.box_label == "Caja 3"


def test_midi_bus_policy_routes_boxes_1_to_3_to_bus_0_and_4_to_5_to_bus_1() -> None:
    assert resolve_node_box_index(15) == 3
    assert resolve_node_midi_bus(15) == 0

    assert resolve_node_box_index(16) == 4
    assert resolve_node_midi_bus(16) == 1

    assert resolve_node_box_index(25) == 5
    assert resolve_node_midi_bus(25) == 1


def test_invalid_node_ids_keep_policy_safe() -> None:
    unknown = resolve_node_identity(None)
    assert unknown.box_index is None
    assert unknown.node_label == "Nodo desconocido"
    assert resolve_node_midi_bus(None) == 0
