from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class ProfileDefinition:
    profile_id: str
    short_name: str
    description: str
    mode: str
    usage_level: str
    operation_summary: str


PROFILE_DEFINITIONS: Final[tuple[ProfileDefinition, ...]] = (
    ProfileDefinition(
        profile_id="serial_local",
        short_name="Serial local",
        description="Uso con Maestro conectado por USB/Serial",
        mode="serial",
        usage_level="Operación local",
        operation_summary="Perfil para operación local por puerto serial.",
    ),
    ProfileDefinition(
        profile_id="udp_jardin",
        short_name="UDP Jardín",
        description="Uso en instalación OKÚA por red UDP",
        mode="udp",
        usage_level="Instalación",
        operation_summary="Perfil para operación en instalación con transporte UDP.",
    ),
    ProfileDefinition(
        profile_id="lab_sim",
        short_name="LAB / simulación",
        description="Uso de pruebas reproducibles sin operación final",
        mode="udp",
        usage_level="Laboratorio",
        operation_summary="Perfil de laboratorio; sesión/simulador aún pendientes.",
    ),
)

PROFILE_IDS: Final[set[str]] = {definition.profile_id for definition in PROFILE_DEFINITIONS}
