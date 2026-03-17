from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_NODE_PREFIXES: tuple[str, ...] = ("EB", "EC", "ED", "EE", "EF")
_UNKNOWN_SORT_GROUP = 2_147_483_647
_PRIMARY_MIDI_BUS = 0
_SECONDARY_MIDI_BUS = 1
_PRIMARY_BOX_LIMIT = 3


@dataclass(frozen=True)
class NodeIdentityPolicy:
    node_id: int | None
    node_label: str
    box_label: str
    box_index: int | None
    slot_index: int | None
    midi_bus: int
    sort_key: tuple[int, int, int]


def resolve_node_identity(node_id: Any) -> NodeIdentityPolicy:
    resolved_node_id = _normalize_node_id(node_id)
    if resolved_node_id is None:
        return NodeIdentityPolicy(
            node_id=None,
            node_label="Nodo desconocido",
            box_label="Caja desconocida",
            box_index=None,
            slot_index=None,
            midi_bus=_PRIMARY_MIDI_BUS,
            sort_key=(_UNKNOWN_SORT_GROUP, _UNKNOWN_SORT_GROUP, _UNKNOWN_SORT_GROUP),
        )

    zero_based = resolved_node_id - 1
    slots_per_box = len(_NODE_PREFIXES)
    box_index = (zero_based // slots_per_box) + 1
    slot_index = zero_based % slots_per_box
    prefix = _NODE_PREFIXES[slot_index]
    node_label = f"{prefix}{box_index}"
    midi_bus = resolve_midi_bus_from_box(box_index)
    return NodeIdentityPolicy(
        node_id=resolved_node_id,
        node_label=node_label,
        box_label=f"Caja {box_index}",
        box_index=box_index,
        slot_index=slot_index,
        midi_bus=midi_bus,
        sort_key=(box_index, slot_index, resolved_node_id),
    )


def resolve_node_label(node_id: Any) -> str:
    return resolve_node_identity(node_id).node_label


def resolve_node_box_index(node_id: Any) -> int | None:
    return resolve_node_identity(node_id).box_index


def resolve_node_box_label(node_id: Any) -> str:
    return resolve_node_identity(node_id).box_label


def resolve_node_midi_bus(node_id: Any) -> int:
    return resolve_node_identity(node_id).midi_bus


def resolve_midi_bus_from_box(box_index: int | None) -> int:
    if box_index is None:
        return _PRIMARY_MIDI_BUS
    if int(box_index) <= _PRIMARY_BOX_LIMIT:
        return _PRIMARY_MIDI_BUS
    return _SECONDARY_MIDI_BUS


def resolve_node_sort_key(node_id: Any) -> tuple[int, int, int]:
    return resolve_node_identity(node_id).sort_key


def _normalize_node_id(node_id: Any) -> int | None:
    try:
        value = int(node_id)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return value
