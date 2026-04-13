from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.viewmodels.map_nodes_sync_vm import (  # noqa: E402
    build_map_nodes_sync_context_for_box,
    build_map_nodes_sync_context_for_node,
    filter_snapshots_for_context,
)
from control_okua.core.registry import NodeSnapshot, NodeStatus  # noqa: E402


def _node_snapshot(node_id: int) -> NodeSnapshot:
    return NodeSnapshot(
        node_id=node_id,
        label=None,
        node_type=None,
        last_seen_pc_ts=100.0,
        last_seq_evt=1,
        last_seq_stat=1,
        pps_evt=1.0,
        pps_stat=2.0,
        loss_evt_pct=0.0,
        loss_stat_pct=0.0,
        rssi_dbm=-55,
        last_note=64,
        last_velocity=90,
        last_evt_ts_ms=1,
        last_evt_flags=1,
        last_state_flags=1,
        last_uptime_s=20,
        reported_pps_x10=10,
        status=NodeStatus.ONLINE,
    )


def test_build_map_nodes_sync_context_for_box_normalizes_selected_node_to_box_identity() -> None:
    context = build_map_nodes_sync_context_for_box("CAJA_3", selected_node_id=12, origin="MAP")

    assert context is not None
    assert context.box_key == "caja_3"
    assert context.box_index == 3
    assert context.expected_node_ids == (11, 12, 13, 14, 15)
    assert context.selected_node_id == 12
    assert context.selected_node_label == "EC3"
    assert context.origin == "map"


def test_build_map_nodes_sync_context_for_box_discards_node_outside_expected_group() -> None:
    context = build_map_nodes_sync_context_for_box("caja_2", selected_node_id=17)

    assert context is not None
    assert context.selected_node_id is None


def test_build_map_nodes_sync_context_for_node_uses_shared_identity_mapping() -> None:
    context = build_map_nodes_sync_context_for_node(24)

    assert context is not None
    assert context.box_key == "caja_5"
    assert context.box_index == 5
    assert context.selected_node_id == 24
    assert context.selected_node_label == "EE5"


def test_filter_snapshots_for_context_returns_only_nodes_in_selected_box() -> None:
    context = build_map_nodes_sync_context_for_box("caja_3")

    filtered = filter_snapshots_for_context(
        [
            _node_snapshot(3),
            _node_snapshot(11),
            _node_snapshot(13),
            _node_snapshot(21),
        ],
        context,
    )

    assert [snapshot.node_id for snapshot in filtered] == [11, 13]
