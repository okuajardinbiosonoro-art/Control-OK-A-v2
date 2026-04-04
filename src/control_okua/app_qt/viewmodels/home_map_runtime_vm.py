from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from control_okua.app_qt.contracts import HomeMapBoxLayout, HomeMapLayout
from control_okua.app_qt.viewmodels.home_map_contract import (
    HomeMapNodeSnapshot,
    build_home_map_box_snapshot,
)
from control_okua.core.registry import NodeStatus
from control_okua.core.session import BackendKind, SessionSnapshot, SessionState


@dataclass(frozen=True)
class HomeMapStatusVisual:
    status: NodeStatus | None
    label: str
    fill_hex: str
    border_hex: str
    badge_hex: str


@dataclass(frozen=True)
class HomeMapLegendItem:
    key: str
    label: str
    fill_hex: str
    border_hex: str


@dataclass(frozen=True)
class HomeMapBoxViewModel:
    box_id: int
    label: str
    aggregate_status: NodeStatus | None
    status_label: str
    status_summary: str
    connected_nodes: int
    expected_nodes: int
    observed_nodes: int
    fill_hex: str
    border_hex: str
    badge_hex: str
    badge_text: str


_STATUS_VISUALS: dict[NodeStatus | None, HomeMapStatusVisual] = {
    None: HomeMapStatusVisual(
        status=None,
        label="Sin estado en vivo",
        fill_hex="#F6F7F4",
        border_hex="#7A857C",
        badge_hex="#5F6B66",
    ),
    NodeStatus.ONLINE: HomeMapStatusVisual(
        status=NodeStatus.ONLINE,
        label="En línea",
        fill_hex="#DDEFD8",
        border_hex="#2F9E44",
        badge_hex="#2B8A3E",
    ),
    NodeStatus.CALIBRATING: HomeMapStatusVisual(
        status=NodeStatus.CALIBRATING,
        label="En calibración",
        fill_hex="#DCECF9",
        border_hex="#1C7ED6",
        badge_hex="#1864AB",
    ),
    NodeStatus.DEGRADED: HomeMapStatusVisual(
        status=NodeStatus.DEGRADED,
        label="Degradado",
        fill_hex="#FFF1CC",
        border_hex="#E67700",
        badge_hex="#D9480F",
    ),
    NodeStatus.OFFLINE: HomeMapStatusVisual(
        status=NodeStatus.OFFLINE,
        label="Fuera de línea",
        fill_hex="#FDE2E1",
        border_hex="#C92A2A",
        badge_hex="#A61E1E",
    ),
}

HOME_MAP_LEGEND_ITEMS: tuple[HomeMapLegendItem, ...] = tuple(
    HomeMapLegendItem(
        key=visual.status.value if visual.status is not None else "none",
        label=visual.label,
        fill_hex=visual.fill_hex,
        border_hex=visual.border_hex,
    )
    for visual in (
        _STATUS_VISUALS[NodeStatus.ONLINE],
        _STATUS_VISUALS[NodeStatus.CALIBRATING],
        _STATUS_VISUALS[NodeStatus.DEGRADED],
        _STATUS_VISUALS[NodeStatus.OFFLINE],
    )
)


def build_home_map_box_view_models(
    layout_contract: HomeMapLayout,
    node_snapshots: Iterable[object],
    session_snapshot: SessionSnapshot | None,
) -> dict[int, HomeMapBoxViewModel]:
    has_runtime_snapshot = _home_map_runtime_active(session_snapshot)
    runtime_nodes = _map_runtime_nodes(node_snapshots)

    view_models: dict[int, HomeMapBoxViewModel] = {}
    for box_layout in layout_contract.boxes:
        matched_nodes = ()
        if has_runtime_snapshot:
            matched_nodes = tuple(
                runtime_nodes[node_id]
                for node_id in box_layout.expected_node_ids
                if node_id in runtime_nodes
            )
        snapshot = build_home_map_box_snapshot(
            box_id=box_layout.box_id,
            label=box_layout.label,
            expected_node_ids=box_layout.expected_node_ids,
            nodes=matched_nodes,
            has_runtime_snapshot=has_runtime_snapshot,
        )
        visual = resolve_home_map_status_visual(snapshot.aggregate_status)
        view_models[box_layout.box_id] = HomeMapBoxViewModel(
            box_id=box_layout.box_id,
            label=box_layout.label,
            aggregate_status=snapshot.aggregate_status,
            status_label=visual.label,
            status_summary=build_home_map_box_status_summary(
                box_layout=box_layout,
                aggregate_status=snapshot.aggregate_status,
                observed_nodes=len(snapshot.nodes),
                connected_nodes=snapshot.connected_nodes,
                expected_nodes=snapshot.expected_nodes,
            ),
            connected_nodes=snapshot.connected_nodes,
            expected_nodes=snapshot.expected_nodes,
            observed_nodes=len(snapshot.nodes),
            fill_hex=visual.fill_hex,
            border_hex=visual.border_hex,
            badge_hex=visual.badge_hex,
            badge_text=visual.label if snapshot.aggregate_status is not None else "Sin datos",
        )
    return view_models


def resolve_home_map_status_visual(status: NodeStatus | None) -> HomeMapStatusVisual:
    return _STATUS_VISUALS.get(status, _STATUS_VISUALS[None])


def build_home_map_box_status_summary(
    *,
    box_layout: HomeMapBoxLayout,
    aggregate_status: NodeStatus | None,
    observed_nodes: int,
    connected_nodes: int,
    expected_nodes: int,
) -> str:
    if aggregate_status is None:
        return (
            "Sin estado en vivo todavía. La Home leerá el agregado real cuando la sesión "
            "UDP/LAB esté corriendo."
        )
    if aggregate_status is NodeStatus.ONLINE:
        return (
            f"{box_layout.label}: {connected_nodes}/{expected_nodes} nodos esperados en línea."
        )
    if aggregate_status is NodeStatus.CALIBRATING:
        return (
            f"{box_layout.label}: nodos en calibración tras reboot o recuperación reciente."
        )
    if aggregate_status is NodeStatus.DEGRADED:
        if observed_nodes < expected_nodes:
            return (
                f"{box_layout.label}: faltan nodos esperados en el snapshot "
                f"({observed_nodes}/{expected_nodes} observados)."
            )
        return (
            f"{box_layout.label}: mezcla de estados no saludables detectada en nodos esperados."
        )
    return (
        f"{box_layout.label}: sin evidencia reciente de nodos esperados en el runtime actual."
    )


def _home_map_runtime_active(session_snapshot: SessionSnapshot | None) -> bool:
    if not isinstance(session_snapshot, SessionSnapshot):
        return False
    if session_snapshot.state is not SessionState.RUNNING:
        return False
    return session_snapshot.backend in {BackendKind.UDP, BackendKind.LAB}


def _map_runtime_nodes(node_snapshots: Iterable[object]) -> dict[int, HomeMapNodeSnapshot]:
    runtime_nodes: dict[int, HomeMapNodeSnapshot] = {}
    for snapshot in node_snapshots:
        raw_node_id = getattr(snapshot, "node_id", None)
        try:
            node_id = int(raw_node_id)
        except (TypeError, ValueError):
            continue
        if node_id <= 0:
            continue
        status = _coerce_node_status(getattr(snapshot, "status", None))
        runtime_nodes[node_id] = HomeMapNodeSnapshot(
            node_id=node_id,
            label=str(getattr(snapshot, "label", None) or f"Nodo {node_id}"),
            status=status,
            status_reason=str(getattr(snapshot, "status_reason", "") or ""),
        )
    return runtime_nodes


def _coerce_node_status(raw_status: object) -> NodeStatus:
    if isinstance(raw_status, NodeStatus):
        return raw_status
    normalized = str(raw_status or "").strip().lower()
    for candidate in NodeStatus:
        if candidate.value == normalized:
            return candidate
    return NodeStatus.OFFLINE
