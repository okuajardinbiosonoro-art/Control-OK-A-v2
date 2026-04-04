from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.contracts.home_map_layout_contract import resolve_home_map_box  # noqa: E402
from control_okua.app_qt.viewmodels.home_map_state_vm import (  # noqa: E402
    aggregate_home_map_box_status,
    build_home_map_box_states,
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


def test_aggregate_home_map_box_status_uses_expected_priority() -> None:
    spec = resolve_home_map_box("caja_1")
    assert spec is not None

    assert (
        aggregate_home_map_box_status(
            expected_node_ids=spec.expected_node_ids,
            snapshots_by_id={node_id: _node_snapshot(node_id=node_id, status=NodeStatus.ONLINE) for node_id in spec.expected_node_ids},
        )
        is NodeStatus.ONLINE
    )
    assert (
        aggregate_home_map_box_status(
            expected_node_ids=spec.expected_node_ids,
            snapshots_by_id={
                node_id: _node_snapshot(
                    node_id=node_id,
                    status=NodeStatus.CALIBRATING if node_id == spec.expected_node_ids[-1] else NodeStatus.ONLINE,
                )
                for node_id in spec.expected_node_ids
            },
        )
        is NodeStatus.CALIBRATING
    )
    assert (
        aggregate_home_map_box_status(
            expected_node_ids=spec.expected_node_ids,
            snapshots_by_id={
                node_id: _node_snapshot(
                    node_id=node_id,
                    status=NodeStatus.DEGRADED if node_id == spec.expected_node_ids[-1] else NodeStatus.ONLINE,
                )
                for node_id in spec.expected_node_ids
            },
        )
        is NodeStatus.DEGRADED
    )
    assert (
        aggregate_home_map_box_status(
            expected_node_ids=spec.expected_node_ids,
            snapshots_by_id={
                node_id: _node_snapshot(
                    node_id=node_id,
                    status=NodeStatus.OFFLINE if node_id == spec.expected_node_ids[-1] else NodeStatus.ONLINE,
                )
                for node_id in spec.expected_node_ids
            },
        )
        is NodeStatus.OFFLINE
    )


def test_aggregate_home_map_box_status_marks_partial_coverage_as_degraded() -> None:
    spec = resolve_home_map_box("caja_2")
    assert spec is not None

    partial = {
        node_id: _node_snapshot(node_id=node_id, status=NodeStatus.ONLINE)
        for node_id in spec.expected_node_ids[:-1]
    }

    assert (
        aggregate_home_map_box_status(
            expected_node_ids=spec.expected_node_ids,
            snapshots_by_id=partial,
        )
        is NodeStatus.DEGRADED
    )


def test_build_home_map_box_states_exposes_counts_and_summary() -> None:
    states = build_home_map_box_states(
        [
            _node_snapshot(node_id=1, status=NodeStatus.ONLINE),
            _node_snapshot(node_id=2, status=NodeStatus.ONLINE),
            _node_snapshot(node_id=3, status=NodeStatus.ONLINE),
            _node_snapshot(node_id=4, status=NodeStatus.ONLINE),
            _node_snapshot(node_id=6, status=NodeStatus.CALIBRATING),
            _node_snapshot(node_id=7, status=NodeStatus.ONLINE),
            _node_snapshot(node_id=8, status=NodeStatus.ONLINE),
            _node_snapshot(node_id=9, status=NodeStatus.ONLINE),
            _node_snapshot(node_id=10, status=NodeStatus.ONLINE),
        ]
    )

    by_key = {state.box_key: state for state in states}
    caja_1 = by_key["caja_1"]
    caja_2 = by_key["caja_2"]
    caja_3 = by_key["caja_3"]

    assert caja_1.aggregated_status is NodeStatus.DEGRADED
    assert caja_1.observed_node_count == 4
    assert caja_1.missing_node_count == 1
    assert "Cobertura parcial" in caja_1.summary_text

    assert caja_2.aggregated_status is NodeStatus.CALIBRATING
    assert caja_2.observed_node_count == 5
    assert caja_2.active_node_count == 5
    assert caja_2.status_label == "En calibración"

    assert caja_3.aggregated_status is NodeStatus.OFFLINE
    assert caja_3.observed_node_count == 0
    assert caja_3.summary_text == "Sin nodos observados en el runtime actual."
