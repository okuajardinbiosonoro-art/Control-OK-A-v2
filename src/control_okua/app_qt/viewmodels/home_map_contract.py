from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from control_okua.core.registry import NodeStatus


HOME_MAP_STATUS_PRIORITY: tuple[NodeStatus, ...] = (
    NodeStatus.OFFLINE,
    NodeStatus.DEGRADED,
    NodeStatus.CALIBRATING,
    NodeStatus.ONLINE,
)


@dataclass(frozen=True)
class HomeMapNodeSnapshot:
    node_id: int
    label: str
    status: NodeStatus
    status_reason: str = ""


@dataclass(frozen=True)
class HomeMapBoxSnapshot:
    box_id: int
    label: str
    expected_node_ids: tuple[int, ...]
    nodes: tuple[HomeMapNodeSnapshot, ...]
    aggregate_status: NodeStatus | None
    connected_nodes: int
    expected_nodes: int


def build_home_map_box_snapshot(
    *,
    box_id: int,
    label: str,
    expected_node_ids: Iterable[int],
    nodes: Iterable[HomeMapNodeSnapshot],
    has_runtime_snapshot: bool,
) -> HomeMapBoxSnapshot:
    normalized_expected = _unique_ids(expected_node_ids)
    normalized_nodes = tuple(
        node for node in nodes if not normalized_expected or node.node_id in normalized_expected
    )
    connected_nodes = sum(1 for node in normalized_nodes if node.status is not NodeStatus.OFFLINE)
    aggregate_status = resolve_box_aggregate_status(
        expected_node_ids=normalized_expected,
        nodes=normalized_nodes,
        has_runtime_snapshot=has_runtime_snapshot,
    )
    return HomeMapBoxSnapshot(
        box_id=box_id,
        label=label,
        expected_node_ids=normalized_expected,
        nodes=normalized_nodes,
        aggregate_status=aggregate_status,
        connected_nodes=connected_nodes,
        expected_nodes=len(normalized_expected),
    )


def resolve_box_aggregate_status(
    *,
    expected_node_ids: Iterable[int],
    nodes: Iterable[HomeMapNodeSnapshot],
    has_runtime_snapshot: bool,
) -> NodeStatus | None:
    if not has_runtime_snapshot:
        return None

    expected_ids = _unique_ids(expected_node_ids)
    filtered_nodes = tuple(
        node for node in nodes if not expected_ids or node.node_id in expected_ids
    )
    if not filtered_nodes:
        return NodeStatus.OFFLINE

    connected_nodes = [node for node in filtered_nodes if node.status is not NodeStatus.OFFLINE]
    if not connected_nodes:
        return NodeStatus.OFFLINE

    expected_count = len(expected_ids) if expected_ids else len(filtered_nodes)
    if len(filtered_nodes) < expected_count:
        return NodeStatus.DEGRADED

    statuses = {node.status for node in filtered_nodes}
    if NodeStatus.DEGRADED in statuses:
        return NodeStatus.DEGRADED
    if NodeStatus.OFFLINE in statuses:
        return NodeStatus.DEGRADED
    if NodeStatus.CALIBRATING in statuses:
        return NodeStatus.CALIBRATING
    return NodeStatus.ONLINE


def _unique_ids(node_ids: Iterable[int]) -> tuple[int, ...]:
    seen: set[int] = set()
    ordered: list[int] = []
    for node_id in node_ids:
        normalized = int(node_id)
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return tuple(ordered)
