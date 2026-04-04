from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.widgets.home_map_panel import (  # noqa: E402
    HomeMapPanel,
    resolve_home_map_asset_path,
)


def _ensure_qapp() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_home_map_panel_resolves_expected_asset_path() -> None:
    asset_path = resolve_home_map_asset_path()
    assert asset_path.name == "okua_home_base.png"
    assert asset_path.exists()


def test_home_map_panel_loads_asset_and_has_reasonable_size_hint() -> None:
    _ensure_qapp()
    panel = HomeMapPanel()
    try:
        assert panel.has_map_asset() is True
        assert panel.sizeHint().width() >= 1200
        assert panel.minimumHeight() >= 480
        assert panel._map_source_rect is not None
        assert len(panel.box_specs()) == 5
    finally:
        panel.close()


def test_home_map_panel_supports_selection_and_hit_regions() -> None:
    app = _ensure_qapp()
    panel = HomeMapPanel()
    try:
        panel.resize(1280, 760)
        panel.show()
        app.processEvents()

        caja_1_rect = panel.box_screen_rect("caja_1")
        assert caja_1_rect is not None
        assert caja_1_rect.width() >= 36
        panel.select_box("caja_1")
        assert panel.selected_box() is not None
        assert panel.selected_box().label == "Caja 1"

        hit_spec = panel._spec_at_position(QPointF(caja_1_rect.center()))
        assert hit_spec is not None
        assert hit_spec.box_key == "caja_1"
    finally:
        panel.close()
