from __future__ import annotations

import os
import sys
from pathlib import Path

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
    finally:
        panel.close()
