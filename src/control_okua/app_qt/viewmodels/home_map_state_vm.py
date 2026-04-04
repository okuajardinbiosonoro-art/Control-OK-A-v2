from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from control_okua.app_qt.contracts.home_map_layout_contract import (
    DEFAULT_HOME_MAP_BOXES,
    HomeMapBoxSpec,
)
from control_okua.core.registry import NodeStatus

_STATUS_LABELS = {
    NodeStatus.ONLINE: "En línea",
    NodeStatus.CALIBRATING: "En calibración",
    NodeStatus.DEGRADED: "Degradado",
    NodeStatus.OFFLINE: "Fuera de línea",
}

_STATUS_BADGES = {
    NodeStatus.ONLINE: "OK",
    NodeStatus.CALIBRATING: "CAL",
    NodeStatus.DEGRADED: "DEG",
    NodeStatus.OFFLINE: "OFF",
}


@dataclass(frozen=True)
class HomeMapBoxState:
    box_key: str
    box_index: int
    label: str
    aggregated_status: NodeStatus
    status_label: str
    badge_text: str
    expected_node_count: int
    observed_node_count: int
    active_node_count: int
    missing_node_count: int
    observed_node_ids: tuple[int, ...]
    missing_node_ids: tuple[int, ...]
    counts_text: str
    summary_text: str


def build_home_map_box_states(
    node_snapshots: list[object] | None,
    *,
    box_specs: Iterable[HomeMapBoxSpec] = DEFAULT_HOME_MAP_BOXES,
) -> tuple[HomeMapBoxState, ...]:
    snapshots_by_id = _node_snapshots_by_id(node_snapshots)
    return tuple(
        build_home_map_box_state(spec, snapshots_by_id=snapshots_by_id)
        for spec in box_specs
    )


def build_home_map_box_state(
    spec: HomeMapBoxSpec,
    *,
    snapshots_by_id: Mapping[int, object],
) -> HomeMapBoxState:
    observed_node_ids: list[int] = []
    missing_node_ids: list[int] = []
    observed_statuses: list[NodeStatus] = []

    for node_id in spec.expected_node_ids:
        snapshot = snapshots_by_id.get(int(node_id))
        if snapshot is None:
            missing_node_ids.append(int(node_id))
            continue
        observed_node_ids.append(int(node_id))
        observed_statuses.append(_snapshot_status(snapshot))

    aggregated_status = aggregate_home_map_box_status(
        expected_node_ids=spec.expected_node_ids,
        snapshots_by_id=snapshots_by_id,
    )
    observed_node_count = len(observed_node_ids)
    active_node_count = sum(
        1 for status in observed_statuses if status is not NodeStatus.OFFLINE
    )
    missing_node_count = len(missing_node_ids)

    return HomeMapBoxState(
        box_key=spec.box_key,
        box_index=spec.box_index,
        label=spec.label,
        aggregated_status=aggregated_status,
        status_label=format_home_map_box_status(aggregated_status),
        badge_text=_STATUS_BADGES[aggregated_status],
        expected_node_count=spec.expected_node_count,
        observed_node_count=observed_node_count,
        active_node_count=active_node_count,
        missing_node_count=missing_node_count,
        observed_node_ids=tuple(observed_node_ids),
        missing_node_ids=tuple(missing_node_ids),
        counts_text=(
            f"Observados {observed_node_count}/{spec.expected_node_count}"
            f" · Activos {active_node_count}"
        ),
        summary_text=_build_box_summary_text(
            aggregated_status=aggregated_status,
            observed_node_count=observed_node_count,
            missing_node_count=missing_node_count,
            observed_statuses=tuple(observed_statuses),
        ),
    )


def aggregate_home_map_box_status(
    *,
    expected_node_ids: Iterable[int],
    snapshots_by_id: Mapping[int, object],
) -> NodeStatus:
    observed_statuses: list[NodeStatus] = []
    missing_count = 0

    for node_id in expected_node_ids:
        snapshot = snapshots_by_id.get(int(node_id))
        if snapshot is None:
            missing_count += 1
            continue
        observed_statuses.append(_snapshot_status(snapshot))

    if not observed_statuses:
        return NodeStatus.OFFLINE
    if any(status is NodeStatus.OFFLINE for status in observed_statuses):
        return NodeStatus.OFFLINE
    if any(status is NodeStatus.DEGRADED for status in observed_statuses):
        return NodeStatus.DEGRADED
    if missing_count > 0:
        # Ausencia parcial de nodos esperados se refleja como cobertura degradada.
        return NodeStatus.DEGRADED
    if any(status is NodeStatus.CALIBRATING for status in observed_statuses):
        return NodeStatus.CALIBRATING
    return NodeStatus.ONLINE


def format_home_map_box_status(status: NodeStatus | str) -> str:
    resolved_status = _coerce_status(status)
    return _STATUS_LABELS[resolved_status]


def _build_box_summary_text(
    *,
    aggregated_status: NodeStatus,
    observed_node_count: int,
    missing_node_count: int,
    observed_statuses: tuple[NodeStatus, ...],
) -> str:
    if aggregated_status is NodeStatus.ONLINE:
        return "Todos los nodos esperados están en línea."
    if aggregated_status is NodeStatus.CALIBRATING:
        return "Hay nodos en calibración; se espera estabilización."
    if aggregated_status is NodeStatus.DEGRADED:
        if missing_node_count > 0 and observed_node_count > 0:
            return "Cobertura parcial del runtime en esta caja."
        return "Se detectó degradación en al menos un nodo."
    if observed_node_count == 0:
        return "Sin nodos observados en el runtime actual."
    if any(status is NodeStatus.OFFLINE for status in observed_statuses):
        return "Hay al menos un nodo fuera de línea."
    return "Sin evidencia reciente suficiente para esta caja."


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


def _snapshot_status(snapshot: object) -> NodeStatus:
    raw_status = getattr(snapshot, "status", None)
    return _coerce_status(raw_status)


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
