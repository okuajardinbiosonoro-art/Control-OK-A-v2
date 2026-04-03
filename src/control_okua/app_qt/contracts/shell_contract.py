from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ShellSectionId(str, Enum):
    HOME_MAP = "home_map"
    NODES = "nodes"
    DIAGNOSTICS = "diagnostics"
    FIRMWARE_OTA = "firmware_ota"
    ADVANCED_TOOLS = "advanced_tools"


@dataclass(frozen=True)
class ShellSectionContract:
    section_id: ShellSectionId
    title: str
    purpose: str
    includes: tuple[str, ...]
    excludes: tuple[str, ...]


@dataclass(frozen=True)
class ShellContract:
    primary_sections: tuple[ShellSectionContract, ...]
    desktop_role: str
    web_console_role: str
    control_plane_owner: ShellSectionId
    firmware_owner: ShellSectionId
    diagnostics_owner: ShellSectionId
    current_shell_status: str


DESKTOP_OPERATOR_FIRST_SHELL = ShellContract(
    primary_sections=(
        ShellSectionContract(
            section_id=ShellSectionId.HOME_MAP,
            title="Home / Mapa",
            purpose="Operator-first spatial overview and rapid orientation.",
            includes=(
                "map-guided system overview",
                "box-level status summary",
                "compact operational summary",
                "contextual jump to node detail",
            ),
            excludes=(
                "full technical node table",
                "firmware workflows",
                "advanced maintenance controls",
                "deep diagnostics",
            ),
        ),
        ShellSectionContract(
            section_id=ShellSectionId.NODES,
            title="Nodos",
            purpose="Canonical technical-operational node inspection surface.",
            includes=(
                "node table",
                "per-node metrics",
                "status reasons",
                "detailed inspection by box and node",
            ),
            excludes=(
                "spatial map overview",
                "firmware workflows",
                "advanced maintenance controls",
            ),
        ),
        ShellSectionContract(
            section_id=ShellSectionId.DIAGNOSTICS,
            title="Diagnostico",
            purpose="Events, observability and support-focused troubleshooting.",
            includes=(
                "events and problems",
                "readiness findings",
                "backend/runtime observability",
                "support diagnostics",
            ),
            excludes=(
                "canonical node table",
                "firmware workflows",
                "primary operator home",
            ),
        ),
        ShellSectionContract(
            section_id=ShellSectionId.FIRMWARE_OTA,
            title="Firmware / OTA",
            purpose="Separated technical workspace for artifact and deployment workflows.",
            includes=(
                "firmware catalog",
                "artifact import",
                "ota deployment",
                "campaign tracking",
            ),
            excludes=(
                "primary operator home",
                "deep diagnostics",
                "control-plane maintenance actions",
            ),
        ),
        ShellSectionContract(
            section_id=ShellSectionId.ADVANCED_TOOLS,
            title="Herramientas avanzadas",
            purpose="Protected surface for delicate control and maintenance actions.",
            includes=(
                "control-plane F3",
                "remote service administration",
                "advanced configuration",
                "maintenance panels",
            ),
            excludes=(
                "primary operator home",
                "firmware campaign workspace",
                "canonical node detail table",
            ),
        ),
    ),
    desktop_role="primary_local_operator_surface",
    web_console_role="complementary_remote_surface",
    control_plane_owner=ShellSectionId.ADVANCED_TOOLS,
    firmware_owner=ShellSectionId.FIRMWARE_OTA,
    diagnostics_owner=ShellSectionId.DIAGNOSTICS,
    current_shell_status="transitional_until_ticket_32_1",
)


def shell_section_ids() -> tuple[ShellSectionId, ...]:
    return tuple(section.section_id for section in DESKTOP_OPERATOR_FIRST_SHELL.primary_sections)


def get_shell_section_contract(section_id: ShellSectionId) -> ShellSectionContract:
    for section in DESKTOP_OPERATOR_FIRST_SHELL.primary_sections:
        if section.section_id is section_id:
            return section
    raise KeyError(f"Unknown shell section: {section_id!r}")
