from __future__ import annotations

from dataclasses import dataclass


_NODES_PER_BOX = 5


@dataclass(frozen=True)
class HomeMapBoxSpec:
    box_key: str
    box_index: int
    label: str
    normalized_center: tuple[float, float]
    normalized_size: tuple[float, float]
    expected_node_ids: tuple[int, ...]
    detail_hint: str

    @property
    def expected_node_count(self) -> int:
        return len(self.expected_node_ids)


def _build_box_spec(
    *,
    box_index: int,
    center_x: float,
    center_y: float,
    width: float,
    height: float,
) -> HomeMapBoxSpec:
    start_node_id = ((int(box_index) - 1) * _NODES_PER_BOX) + 1
    expected_ids = tuple(range(start_node_id, start_node_id + _NODES_PER_BOX))
    return HomeMapBoxSpec(
        box_key=f"caja_{int(box_index)}",
        box_index=int(box_index),
        label=f"Caja {int(box_index)}",
        normalized_center=(float(center_x), float(center_y)),
        normalized_size=(float(width), float(height)),
        expected_node_ids=expected_ids,
        detail_hint="Detalle vivo disponible desde 33.2+.",
    )


DEFAULT_HOME_MAP_BOXES: tuple[HomeMapBoxSpec, ...] = (
    _build_box_spec(box_index=1, center_x=0.2313, center_y=0.0614, width=0.0688, height=0.0438),
    _build_box_spec(box_index=2, center_x=0.0445, center_y=0.4568, width=0.0672, height=0.0470),
    _build_box_spec(box_index=3, center_x=0.0422, center_y=0.7220, width=0.0625, height=0.0416),
    _build_box_spec(box_index=4, center_x=0.8477, center_y=0.7487, width=0.0672, height=0.0459),
    _build_box_spec(box_index=5, center_x=0.4859, center_y=0.6275, width=0.0531, height=0.0363),
)


def resolve_home_map_box(box_key: str) -> HomeMapBoxSpec | None:
    canonical_key = str(box_key).strip().lower()
    for spec in DEFAULT_HOME_MAP_BOXES:
        if spec.box_key == canonical_key:
            return spec
    return None
