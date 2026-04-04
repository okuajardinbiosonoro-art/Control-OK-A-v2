from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from control_okua.app_qt.contracts import HomeMapBoxLayout, HomeMapLayout
from control_okua.app_qt.viewmodels.home_map_contract import (
    HomeMapNodeSnapshot,
    build_home_map_box_snapshot,
)
from control_okua.core.registry import NodeStatus
from control_okua.core.session import SessionSnapshot, SessionState


@dataclass(frozen=True)
class HomeMapStatusVisual:
    fill_hex: str
    border_hex: str
    badge_text: str
    label: str


@dataclass(frozen=True)
class HomeMapLegendItem:
    status: NodeStatus
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
    expected_nodes: int
    observed_nodes: int
    connected_nodes: int
    expected_node_labels: tuple[str, ...]
    fill_hex: str
    border_hex: str
    badge_text: str


HOME_MAP_LEGEND_ITEMS: tuple[HomeMapLegendItem, ...] = (
    HomeMapLegendItem(
        status=NodeStatus.ONLINE,
        label="En línea",
        fill_hex="#DDEFD8",
        border_hex="#2F9E44",
    ),
    HomeMapLegendItem(
        status=NodeStatus.CALIBRATING,
        label="En calibración",
        fill_hex="#DCECF9",
        border_hex="#1C7ED6",
    ),
    HomeMapLegendItem(
        status=NodeStatus.DEGRADED,
        label="Degradado",
        fill_hex="#FFF1CC",
        border_hex="#E67700",
    ),
    HomeMapLegendItem(
        status=NodeStatus.OFFLINE,
        label="Fuera de línea",
        fill_hex="#FDE2E1",
        border_hex="#C92A2A",
    ),
)


def build_home_map_box_view_models(
    layout_contract: HomeMapLayout,
    node_snapshots: Iterable[object],
    session_snapshot: SessionSnapshot,
) -> tuple[HomeMapBoxViewModel, ...]:
    runtime_active = _home_map_runtime_active(session_snapshot)
    mapped_nodes = _map_runtime_nodes(node_snapshots)
    view_models: list[HomeMapBoxViewModel] = []
    for box in layout_contract.boxes:
        visible_nodes = [
            mapped_nodes[node_id]
            for node_id in box.expected_node_ids
            if node_id in mapped_nodes
        ]
        box_snapshot = build_home_map_box_snapshot(
            box_id=box.box_id,
            label=box.label,
            expected_node_ids=box.expected_node_ids,
            nodes=visible_nodes,
            has_runtime_snapshot=runtime_active,
        )
        visual = resolve_home_map_status_visual(box_snapshot.aggregate_status)
        view_models.append(
            HomeMapBoxViewModel(
                box_id=box.box_id,
                label=box.label,
                aggregate_status=box_snapshot.aggregate_status,
                status_label=visual.label,
                status_summary=build_home_map_box_status_summary(box, box_snapshot.aggregate_status, observed_nodes=len(box_snapshot.nodes), connected_nodes=box_snapshot.connected_nodes, expected_nodes=box_snapshot.expected_nodes),
                expected_nodes=box_snapshot.expected_nodes,
                observed_nodes=len(box_snapshot.nodes),
                connected_nodes=box_snapshot.connected_nodes,
                expected_node_labels=box.expected_node_labels,
                fill_hex=visual.fill_hex,
                border_hex=visual.border_hex,
                badge_text=visual.badge_text,
            )
        )
    return tuple(view_models)


def resolve_home_map_status_visual(status: NodeStatus | None) -> HomeMapStatusVisual:
    if status is NodeStatus.ONLINE:
        return HomeMapStatusVisual(
            fill_hex="#DDEFD8",
            border_hex="#2F9E44",
            badge_text="En línea",
            label="En línea",
        )
    if status is NodeStatus.CALIBRATING:
        return HomeMapStatusVisual(
            fill_hex="#DCECF9",
            border_hex="#1C7ED6",
            badge_text="Calibrando",
            label="En calibración",
        )
    if status is NodeStatus.DEGRADED:
        return HomeMapStatusVisual(
            fill_hex="#FFF1CC",
            border_hex="#E67700",
            badge_text="Degradado",
            label="Degradado",
        )
    if status is NodeStatus.OFFLINE:
        return HomeMapStatusVisual(
            fill_hex="#FDE2E1",
            border_hex="#C92A2A",
            badge_text="Fuera de línea",
            label="Fuera de línea",
        )
    return HomeMapStatusVisual(
        fill_hex="#ECEFE8",
        border_hex="#7D8A82",
        badge_text="Sin datos",
        label="Sin estado en vivo",
    )


def build_home_map_box_status_summary(
    box_layout: HomeMapBoxLayout,
    aggregate_status: NodeStatus | None,
    *,
    observed_nodes: int,
    connected_nodes: int,
    expected_nodes: int,
) -> str:
    if aggregate_status is None:
        return "Sin estado en vivo todavía. La caja mostrará estado agregado cuando exista evidencia del runtime."
    if aggregate_status is NodeStatus.ONLINE:
        return (
            f"{box_layout.label}: {connected_nodes}/{expected_nodes} nodos esperados en línea."
        )
    if aggregate_status is NodeStatus.CALIBRATING:
        return (
            f"{box_layout.label}: se observan nodos calibrando tras reboot o recuperación reciente."
        )
    if aggregate_status is NodeStatus.DEGRADED:
        missing_nodes = max(0, expected_nodes - observed_nodes)
        if missing_nodes > 0:
            return (
                f"{box_layout.label}: hay {missing_nodes} nodo(s) esperado(s) sin evidencia reciente "
                "o con estado no saludable."
            )
        return (
            f"{box_layout.label}: mezcla de estados no saludables o actividad parcial útil."
        )
    return f"{box_layout.label}: sin evidencia reciente de nodos esperados en el runtime."


def _home_map_runtime_active(session_snapshot: SessionSnapshot) -> bool:
    if session_snapshot.state is not SessionState.RUNNING:
        return False
    if session_snapshot.mode == "udp":
        return True
    backend = getattr(session_snapshot, "backend", None)
    return backend is not None and getattr(backend, "value", "") in {"udp", "lab"}


def _map_runtime_nodes(node_snapshots: Iterable[object]) -> dict[int, HomeMapNodeSnapshot]:
    mapped: dict[int, HomeMapNodeSnapshot] = {}
    for snapshot in node_snapshots:
        raw_node_id = getattr(snapshot, "node_id", None)
        try:
            node_id = int(raw_node_id)
        except (TypeError, ValueError):
            continue
        status = _coerce_node_status(getattr(snapshot, "status", None))
        if status is None:
            continue
        raw_label = getattr(snapshot, "label", None)
        label = str(raw_label).strip() if isinstance(raw_label, str) and raw_label.strip() else f"N{node_id}"
        status_reason = str(getattr(snapshot, "status_reason", "") or "")
        mapped[node_id] = HomeMapNodeSnapshot(
            node_id=node_id,
            label=label,
            status=status,
            status_reason=status_reason,
        )
    return mapped


def _coerce_node_status(value: object) -> NodeStatus | None:
    if isinstance(value, NodeStatus):
        return value
    if isinstance(value, str):
        raw = value.strip().lower()
        for candidate in NodeStatus:
            if candidate.value == raw:
                return candidate
    return None
