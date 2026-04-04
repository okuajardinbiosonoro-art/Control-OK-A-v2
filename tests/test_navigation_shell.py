from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.navigation_shell import build_primary_shell_items  # noqa: E402


def test_build_primary_shell_items_uses_operator_first_order() -> None:
    items = build_primary_shell_items(include_remote=True)
    assert [item.key for item in items] == [
        "home",
        "nodes",
        "diagnostics",
        "firmware",
        "technical",
        "remote",
    ]
    assert items[0].label == "Inicio"
    assert items[-1].label == "Remoto"


def test_build_primary_shell_items_can_hide_remote_surface() -> None:
    items = build_primary_shell_items(include_remote=False)
    assert [item.key for item in items] == [
        "home",
        "nodes",
        "diagnostics",
        "firmware",
        "technical",
    ]
