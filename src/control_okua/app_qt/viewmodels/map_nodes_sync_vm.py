from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from control_okua.app_qt.contracts.home_map_layout_contract import (
    DEFAULT_HOME_MAP_BOXES,
    HomeMapBoxSpec,
    resolve_home_map_box,
)
from control_okua.core.node_identity_policy import resolve_node_identity


@dataclass(frozen=True)
class MapNodesSyncContext:
    box_key: str
    box_index: int
    box_label: str
    expected_node_ids: tuple[int, ...]
    selected_node_id: int | None
    origin: str

    @property
    def summary_text(self) -> str:
        return f"{self.box_label} · {len(self.expected_node_ids)} nodos esperados"

    @property
    def selected_node_label(self) -> str | None:
        if self.selected_node_id is None:
            return None
        return resolve_node_identity(self.selected_node_id).node_label

    def contains_node(self, node_id: int | None) -> bool:
        if node_id is None:
            return False
        return int(node_id) in self.expected_node_ids


def build_map_nodes_sync_context_for_box(
    box_key: str,
    *,
    selected_node_id: int | None = None,
    origin: str = "map",
    box_specs: Iterable[HomeMapBoxSpec] = DEFAULT_HOME_MAP_BOXES,
) -> MapNodesSyncContext | None:
    spec = _resolve_box_spec(box_key, box_specs=box_specs)
    if spec is None:
        return None
    try:
        normalized_selected_node_id = int(selected_node_id) if selected_node_id is not None else None
    except (TypeError, ValueError):
        normalized_selected_node_id = None
    resolved_selected_node_id = (
        normalized_selected_node_id if normalized_selected_node_id in spec.expected_node_ids else None
    )
    return MapNodesSyncContext(
        box_key=spec.box_key,
        box_index=spec.box_index,
        box_label=spec.label,
        expected_node_ids=spec.expected_node_ids,
        selected_node_id=resolved_selected_node_id,
        origin=str(origin).strip().lower() or "map",
    )


def build_map_nodes_sync_context_for_node(
    node_id: int | None,
    *,
    origin: str = "nodes",
    box_specs: Iterable[HomeMapBoxSpec] = DEFAULT_HOME_MAP_BOXES,
) -> MapNodesSyncContext | None:
    identity = resolve_node_identity(node_id)
    if identity.box_index is None:
        return None
    return build_map_nodes_sync_context_for_box(
        f"caja_{identity.box_index}",
        selected_node_id=identity.node_id,
        origin=origin,
        box_specs=box_specs,
    )


def filter_snapshots_for_context(
    node_snapshots: Iterable[object] | None,
    context: MapNodesSyncContext | None,
) -> list[object]:
    if context is None:
        return list(node_snapshots or ())

    filtered: list[object] = []
    for snapshot in node_snapshots or ():
        raw_node_id = getattr(snapshot, "node_id", None)
        try:
            node_id = int(raw_node_id)
        except (TypeError, ValueError):
            continue
        if context.contains_node(node_id):
            filtered.append(snapshot)
    return filtered


def _resolve_box_spec(
    box_key: str,
    *,
    box_specs: Iterable[HomeMapBoxSpec],
) -> HomeMapBoxSpec | None:
    resolved_specs = tuple(box_specs)
    spec = resolve_home_map_box(box_key)
    if spec is not None and spec in resolved_specs:
        return spec
    canonical_key = str(box_key).strip().lower()
    for candidate in resolved_specs:
        if candidate.box_key == canonical_key:
            return candidate
    return None
