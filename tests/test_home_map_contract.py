from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.viewmodels.home_map_contract import (  # noqa: E402
    HOME_MAP_STATUS_PRIORITY,
    HomeMapNodeSnapshot,
    build_home_map_box_snapshot,
    resolve_box_aggregate_status,
)
from control_okua.core.registry import NodeStatus  # noqa: E402


def _node(node_id: int, status: NodeStatus) -> HomeMapNodeSnapshot:
    return HomeMapNodeSnapshot(node_id=node_id, label=f"N{node_id}", status=status)


def test_home_map_priority_matches_frozen_contract() -> None:
    assert HOME_MAP_STATUS_PRIORITY == (
        NodeStatus.OFFLINE,
        NodeStatus.DEGRADED,
        NodeStatus.CALIBRATING,
        NodeStatus.ONLINE,
    )


def test_box_without_runtime_snapshot_has_no_operational_state() -> None:
    aggregate = resolve_box_aggregate_status(
        expected_node_ids=(1, 2),
        nodes=(_node(1, NodeStatus.ONLINE), _node(2, NodeStatus.ONLINE)),
        has_runtime_snapshot=False,
    )
    assert aggregate is None


def test_box_is_online_only_when_complete_and_healthy() -> None:
    snapshot = build_home_map_box_snapshot(
        box_id=1,
        label="Caja 1",
        expected_node_ids=(1, 2),
        nodes=(_node(1, NodeStatus.ONLINE), _node(2, NodeStatus.ONLINE)),
        has_runtime_snapshot=True,
    )
    assert snapshot.aggregate_status is NodeStatus.ONLINE
    assert snapshot.connected_nodes == 2
    assert snapshot.expected_nodes == 2


def test_box_prefers_degraded_over_calibrating_when_mixed() -> None:
    aggregate = resolve_box_aggregate_status(
        expected_node_ids=(1, 2),
        nodes=(_node(1, NodeStatus.CALIBRATING), _node(2, NodeStatus.DEGRADED)),
        has_runtime_snapshot=True,
    )
    assert aggregate is NodeStatus.DEGRADED


def test_box_with_missing_expected_nodes_is_degraded() -> None:
    aggregate = resolve_box_aggregate_status(
        expected_node_ids=(1, 2, 3),
        nodes=(_node(1, NodeStatus.ONLINE), _node(2, NodeStatus.ONLINE)),
        has_runtime_snapshot=True,
    )
    assert aggregate is NodeStatus.DEGRADED


def test_box_is_offline_when_all_visible_nodes_are_offline() -> None:
    aggregate = resolve_box_aggregate_status(
        expected_node_ids=(1, 2),
        nodes=(_node(1, NodeStatus.OFFLINE), _node(2, NodeStatus.OFFLINE)),
        has_runtime_snapshot=True,
    )
    assert aggregate is NodeStatus.OFFLINE
