from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.viewmodels.home_map_detail_vm import (  # noqa: E402
    build_home_map_box_detail_states,
)
from control_okua.core.registry import NodeSnapshot, NodeStatus  # noqa: E402


def _node_snapshot(*, node_id: int, status: NodeStatus) -> NodeSnapshot:
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
        rssi_dbm=-52,
        last_note=64,
        last_velocity=100,
        last_evt_ts_ms=1,
        last_evt_flags=1,
        last_state_flags=1,
        last_uptime_s=10,
        reported_pps_x10=10,
        status=status,
    )


def test_home_map_box_detail_states_include_expected_nodes_for_selected_box() -> None:
    details = build_home_map_box_detail_states(
        [
            _node_snapshot(node_id=1, status=NodeStatus.ONLINE),
            _node_snapshot(node_id=2, status=NodeStatus.CALIBRATING),
            _node_snapshot(node_id=3, status=NodeStatus.DEGRADED),
            _node_snapshot(node_id=4, status=NodeStatus.ONLINE),
            _node_snapshot(node_id=5, status=NodeStatus.OFFLINE),
        ]
    )
    by_key = {detail.box_key: detail for detail in details}
    caja_1 = by_key["caja_1"]

    assert caja_1.label == "Caja 1"
    assert len(caja_1.nodes) == 5
    assert [node.node_id for node in caja_1.nodes] == [1, 2, 3, 4, 5]
    assert caja_1.nodes[0].display_label == "EB1 · ID 1"
    assert caja_1.nodes[1].status_label == "En calibración"
    assert caja_1.nodes[2].badge_text == "DEG"
    assert caja_1.nodes[4].status is NodeStatus.OFFLINE


def test_home_map_box_detail_states_mark_missing_nodes_as_unobserved() -> None:
    details = build_home_map_box_detail_states(
        [
            _node_snapshot(node_id=6, status=NodeStatus.ONLINE),
            _node_snapshot(node_id=7, status=NodeStatus.ONLINE),
        ]
    )
    by_key = {detail.box_key: detail for detail in details}
    caja_2 = by_key["caja_2"]

    assert caja_2.aggregated_status is NodeStatus.DEGRADED
    assert caja_2.nodes[0].is_observed is True
    assert caja_2.nodes[2].is_observed is False
    assert caja_2.nodes[2].status is NodeStatus.OFFLINE
    assert caja_2.nodes[2].status_summary == "Sin observación reciente"
