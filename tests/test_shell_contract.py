from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.contracts import (  # noqa: E402
    DESKTOP_OPERATOR_FIRST_SHELL,
    ShellSectionId,
    get_shell_section_contract,
    shell_section_ids,
)


def test_shell_contract_freezes_primary_sections_in_order() -> None:
    assert shell_section_ids() == (
        ShellSectionId.HOME_MAP,
        ShellSectionId.NODES,
        ShellSectionId.DIAGNOSTICS,
        ShellSectionId.FIRMWARE_OTA,
        ShellSectionId.ADVANCED_TOOLS,
    )


def test_shell_contract_keeps_desktop_primary_and_web_complementary() -> None:
    contract = DESKTOP_OPERATOR_FIRST_SHELL
    assert contract.desktop_role == "primary_local_operator_surface"
    assert contract.web_console_role == "complementary_remote_surface"
    assert contract.current_shell_status == "transitional_until_ticket_32_1"


def test_home_map_contract_excludes_technical_surfaces() -> None:
    home = get_shell_section_contract(ShellSectionId.HOME_MAP)
    assert "map-guided system overview" in home.includes
    assert "full technical node table" in home.excludes
    assert "firmware workflows" in home.excludes
    assert "advanced maintenance controls" in home.excludes


def test_advanced_tools_owns_control_plane() -> None:
    contract = DESKTOP_OPERATOR_FIRST_SHELL
    advanced = get_shell_section_contract(ShellSectionId.ADVANCED_TOOLS)
    assert contract.control_plane_owner is ShellSectionId.ADVANCED_TOOLS
    assert "control-plane F3" in advanced.includes
    assert "remote service administration" in advanced.includes
