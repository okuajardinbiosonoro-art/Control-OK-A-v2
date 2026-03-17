from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.viewmodels import (  # noqa: E402
    resolve_node_box_label,
    resolve_node_identity,
    resolve_node_label,
    resolve_node_sort_key,
)


def test_node_label_mapping_follows_expected_box_pattern() -> None:
    assert resolve_node_label(1) == "EB1"
    assert resolve_node_label(2) == "EC1"
    assert resolve_node_label(5) == "EF1"
    assert resolve_node_label(6) == "EB2"
    assert resolve_node_label(10) == "EF2"
    assert resolve_node_label(15) == "EF3"


def test_node_box_label_mapping_is_consistent() -> None:
    assert resolve_node_box_label(1) == "Caja 1"
    assert resolve_node_box_label(7) == "Caja 2"
    assert resolve_node_box_label(13) == "Caja 3"
    assert resolve_node_box_label(21) == "Caja 5"


def test_node_identity_exposes_sort_key_by_box_and_slot() -> None:
    node_6 = resolve_node_identity(6)
    node_7 = resolve_node_identity(7)
    node_11 = resolve_node_identity(11)
    assert node_6.sort_key < node_7.sort_key
    assert node_7.sort_key < node_11.sort_key
    assert resolve_node_sort_key(6) == node_6.sort_key
    assert node_6.midi_bus == 0
    assert resolve_node_identity(21).midi_bus == 1


def test_node_identity_handles_invalid_node_id_without_crashing() -> None:
    unknown = resolve_node_identity(None)
    assert unknown.node_label == "Nodo desconocido"
    assert unknown.box_label == "Caja desconocida"
