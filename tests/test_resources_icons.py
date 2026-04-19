from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QColor, QImage


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.resources import app_icon_path, resource_path  # noqa: E402


def test_app_icon_path_prefers_png_over_ico() -> None:
    # app_icon_path() prefiere PNG para que QIcon lo cargue de forma confiable;
    # el ICO permanece en la spec como recurso PE del exe (taskbar anclado).
    resolved = app_icon_path()
    expected = resource_path("assets/branding/okua_icon_256.png")

    assert resolved == expected
    assert resolved.exists()


def test_pyinstaller_spec_points_to_branding_icon_assets() -> None:
    spec_text = (ROOT_DIR / "ControlOkuaV2.spec").read_text(encoding="utf-8")

    assert 'PROJECT_DIR / "assets" / "branding" / "okua_app_icon.ico"' in spec_text
    assert 'PROJECT_DIR / "assets" / "branding" / "okua_icon_256.png"' in spec_text
    assert 'PROJECT_DIR / "assets" / "icons" / "app_icon.ico"' not in spec_text
    assert 'PROJECT_DIR / "assets" / "icons" / "app_icon.png"' not in spec_text


def test_primary_branding_png_uses_canvas_more_aggressively() -> None:
    icon_path = resource_path("assets/branding/okua_icon_256.png")
    image = QImage(str(icon_path))

    left = image.width()
    top = image.height()
    right = -1
    bottom = -1
    for y in range(image.height()):
        for x in range(image.width()):
            if QColor.fromRgba(image.pixel(x, y)).alpha() <= 0:
                continue
            left = min(left, x)
            top = min(top, y)
            right = max(right, x)
            bottom = max(bottom, y)

    assert right > left
    assert bottom > top
    assert (right - left + 1) >= 190
    assert (bottom - top + 1) >= 220
