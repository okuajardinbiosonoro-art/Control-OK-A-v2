from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.resources import app_icon_path, resource_path  # noqa: E402


def test_app_icon_path_prefers_new_branding_icon_set() -> None:
    resolved = app_icon_path()
    expected = resource_path("assets/branding/okua_app_icon.ico")

    assert resolved == expected
    assert resolved.exists()


def test_pyinstaller_spec_points_to_branding_icon_assets() -> None:
    spec_text = (ROOT_DIR / "ControlOkuaV2.spec").read_text(encoding="utf-8")

    assert 'PROJECT_DIR / "assets" / "branding" / "okua_app_icon.ico"' in spec_text
    assert 'PROJECT_DIR / "assets" / "branding" / "okua_icon_256.png"' in spec_text
    assert 'PROJECT_DIR / "assets" / "icons" / "app_icon.ico"' not in spec_text
    assert 'PROJECT_DIR / "assets" / "icons" / "app_icon.png"' not in spec_text
