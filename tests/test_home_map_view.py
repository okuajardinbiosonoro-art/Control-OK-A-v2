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

from control_okua.app_qt.contracts import DEFAULT_HOME_MAP_LAYOUT  # noqa: E402
from control_okua.app_qt.widgets.home_map_view import HomeMapView  # noqa: E402


def _ensure_qapp() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_home_map_view_starts_with_first_box_selected() -> None:
    _ensure_qapp()
    widget = HomeMapView(DEFAULT_HOME_MAP_LAYOUT)
    try:
        assert widget.selected_box_id == 4
        assert widget.selected_box() is not None
        assert widget.selected_box().label == "Caja 4"
    finally:
        widget.close()


def test_home_map_view_resolves_box_from_position() -> None:
    app = _ensure_qapp()
    widget = HomeMapView(DEFAULT_HOME_MAP_LAYOUT)
    try:
        widget.resize(960, 640)
        widget.show()
        app.processEvents()
        rect = widget.box_rect(1)
        center = QPointF(rect.center())
        selected = widget.box_at_position(center)
        assert selected is not None
        assert selected.box_id == 1
    finally:
        widget.close()


def test_home_map_view_emits_selection_changes() -> None:
    app = _ensure_qapp()
    widget = HomeMapView(DEFAULT_HOME_MAP_LAYOUT)
    seen: list[int] = []
    widget.box_selected.connect(seen.append)
    try:
        widget.resize(960, 640)
        widget.show()
        app.processEvents()
        widget.set_selected_box(5)
        assert widget.selected_box_id == 5
        assert seen == [5]
    finally:
        widget.close()
