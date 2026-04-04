from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HomeMapBoxLayout:
    box_id: int
    label: str
    position_slot: str
    normalized_rect: tuple[float, float, float, float]
    description: str
    expected_node_ids: tuple[int, ...]
    expected_node_labels: tuple[str, ...]
    future_status_hint: str = "Estado agregado disponible en el siguiente ticket."


@dataclass(frozen=True)
class HomeMapLayout:
    layout_id: str
    display_name: str
    aspect_ratio: float
    background_asset: str | None
    fallback_note: str
    boxes: tuple[HomeMapBoxLayout, ...]


DEFAULT_HOME_MAP_LAYOUT = HomeMapLayout(
    layout_id="okua_jardin_base_v1",
    display_name="Plano base estático de jardín",
    aspect_ratio=1.60,
    background_asset="assets/maps/okua_home_base.png",
    fallback_note=(
        "Plano base estático sin asset final. La geometría de cajas ya prepara la Home "
        "para estado agregado y overlays posteriores."
    ),
    boxes=(
        HomeMapBoxLayout(
            box_id=4,
            label="Caja 4",
            position_slot="top",
            normalized_rect=(0.47, 0.07, 0.08, 0.10),
            description="Caja superior del recorrido. Referencia de entrada al eje alto del jardín.",
            expected_node_ids=(16, 17, 18, 19, 20),
            expected_node_labels=("EB4", "EC4", "ED4", "EE4", "EF4"),
        ),
        HomeMapBoxLayout(
            box_id=2,
            label="Caja 2",
            position_slot="left_upper",
            normalized_rect=(0.24, 0.42, 0.08, 0.10),
            description="Caja lateral izquierda alta. Cubre el arco superior izquierdo del sistema.",
            expected_node_ids=(6, 7, 8, 9, 10),
            expected_node_labels=("EB2", "EC2", "ED2", "EE2", "EF2"),
        ),
        HomeMapBoxLayout(
            box_id=3,
            label="Caja 3",
            position_slot="left_lower",
            normalized_rect=(0.25, 0.63, 0.08, 0.10),
            description="Caja lateral izquierda baja. Extiende la cobertura del borde inferior izquierdo.",
            expected_node_ids=(11, 12, 13, 14, 15),
            expected_node_labels=("EB3", "EC3", "ED3", "EE3", "EF3"),
        ),
        HomeMapBoxLayout(
            box_id=1,
            label="Caja 1",
            position_slot="center",
            normalized_rect=(0.53, 0.53, 0.08, 0.10),
            description="Caja central del sistema. Punto de referencia principal para lectura espacial.",
            expected_node_ids=(1, 2),
            expected_node_labels=("EB1", "EC1"),
        ),
        HomeMapBoxLayout(
            box_id=5,
            label="Caja 5",
            position_slot="right",
            normalized_rect=(0.79, 0.66, 0.08, 0.10),
            description="Caja lateral derecha. Cubre el flanco derecho y salida baja del recorrido.",
            expected_node_ids=(21, 22, 23, 24, 25),
            expected_node_labels=("EB5", "EC5", "ED5", "EE5", "EF5"),
        ),
    ),
)


def get_default_home_map_layout() -> HomeMapLayout:
    return DEFAULT_HOME_MAP_LAYOUT


def get_home_map_box(box_id: int, layout: HomeMapLayout = DEFAULT_HOME_MAP_LAYOUT) -> HomeMapBoxLayout:
    for box in layout.boxes:
        if box.box_id == int(box_id):
            return box
    raise KeyError(f"Unknown map box: {box_id!r}")
