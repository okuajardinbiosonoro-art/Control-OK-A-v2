from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from control_okua.app_qt.contracts.home_map_layout_contract import (
    DEFAULT_HOME_MAP_BOXES,
    HomeMapBoxSpec,
)
from control_okua.app_qt.viewmodels.home_map_state_vm import (
    HomeMapBoxState,
    build_home_map_box_states,
    format_home_map_box_status,
)
from control_okua.app_qt.viewmodels.main_window_vm import format_node_status
from control_okua.core.node_identity_policy import resolve_node_identity
from control_okua.core.registry import NodeStatus

_NODE_STATUS_BADGES = {
    NodeStatus.ONLINE: "OK",
    NodeStatus.CALIBRATING: "CAL",
    NodeStatus.DEGRADED: "DEG",
    NodeStatus.OFFLINE: "OFF",
}


@dataclass(frozen=True)
class HomeMapNodeDetailItem:
    node_id: int
    node_label: str
    display_label: str
    status: NodeStatus
    status_label: str
    badge_text: str
    status_summary: str
    is_observed: bool


@dataclass(frozen=True)
class HomeMapBoxDetailState:
    box_key: str
    box_index: int
    label: str
    aggregated_status: NodeStatus
    aggregated_status_label: str
    counts_text: str
    summary_text: str
    nodes: tuple[HomeMapNodeDetailItem, ...]


def build_home_map_box_detail_states(
    node_snapshots: list[object] | None,
    *,
    box_specs: Iterable[HomeMapBoxSpec] = DEFAULT_HOME_MAP_BOXES,
    box_states: tuple[HomeMapBoxState, ...] | None = None,
) -> tuple[HomeMapBoxDetailState, ...]:
    resolved_specs = tuple(box_specs)
    resolved_box_states = (
        build_home_map_box_states(node_snapshots, box_specs=resolved_specs)
        if box_states is None
        else tuple(box_states)
    )
    snapshots_by_id = _node_snapshots_by_id(node_snapshots)
    return tuple(
        build_home_map_box_detail_state(
            spec,
            box_state=box_state,
            snapshots_by_id=snapshots_by_id,
        )
        for spec, box_state in zip(resolved_specs, resolved_box_states, strict=False)
    )


def build_home_map_box_detail_state(
    spec: HomeMapBoxSpec,
    *,
    box_state: HomeMapBoxState,
    snapshots_by_id: Mapping[int, object],
) -> HomeMapBoxDetailState:
    nodes = tuple(
        _build_node_detail_item(node_id=node_id, snapshots_by_id=snapshots_by_id)
        for node_id in spec.expected_node_ids
    )
    return HomeMapBoxDetailState(
        box_key=spec.box_key,
        box_index=spec.box_index,
        label=spec.label,
        aggregated_status=box_state.aggregated_status,
        aggregated_status_label=box_state.status_label,
        counts_text=box_state.counts_text,
        summary_text=box_state.summary_text,
        nodes=nodes,
    )


def _build_node_detail_item(
    *,
    node_id: int,
    snapshots_by_id: Mapping[int, object],
) -> HomeMapNodeDetailItem:
    identity = resolve_node_identity(node_id)
    snapshot = snapshots_by_id.get(int(node_id))
    if snapshot is None:
        status = NodeStatus.OFFLINE
        status_label = format_home_map_box_status(status)
        return HomeMapNodeDetailItem(
            node_id=int(node_id),
            node_label=identity.node_label,
            display_label=f"{identity.node_label} · ID {int(node_id)}",
            status=status,
            status_label=status_label,
            badge_text=_NODE_STATUS_BADGES[status],
            status_summary="Sin observación reciente",
            is_observed=False,
        )

    status = _coerce_status(getattr(snapshot, "status", None))
    return HomeMapNodeDetailItem(
        node_id=int(node_id),
        node_label=identity.node_label,
        display_label=f"{identity.node_label} · ID {int(node_id)}",
        status=status,
        status_label=format_node_status(snapshot),
        badge_text=_NODE_STATUS_BADGES[status],
        status_summary="Observado en runtime",
        is_observed=True,
    )


def _node_snapshots_by_id(node_snapshots: list[object] | None) -> dict[int, object]:
    if not isinstance(node_snapshots, list):
        return {}

    snapshots_by_id: dict[int, object] = {}
    for snapshot in node_snapshots:
        raw_node_id = getattr(snapshot, "node_id", None)
        try:
            node_id = int(raw_node_id)
        except (TypeError, ValueError):
            continue
        if node_id <= 0:
            continue
        snapshots_by_id[node_id] = snapshot
    return snapshots_by_id


def _coerce_status(raw_status: object) -> NodeStatus:
    if isinstance(raw_status, NodeStatus):
        return raw_status
    raw_value = getattr(raw_status, "value", raw_status)
    text = str(raw_value).strip().lower()
    if text == NodeStatus.ONLINE.value:
        return NodeStatus.ONLINE
    if text == NodeStatus.CALIBRATING.value:
        return NodeStatus.CALIBRATING
    if text == NodeStatus.DEGRADED.value:
        return NodeStatus.DEGRADED
    return NodeStatus.OFFLINE
