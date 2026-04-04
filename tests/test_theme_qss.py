from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
THEME_PATH = ROOT_DIR / "assets" / "theme.qss"


def test_theme_qss_uses_new_light_palette_and_removes_legacy_dark_colors() -> None:
    qss = THEME_PATH.read_text(encoding="utf-8")

    assert "#F7F4EC" in qss
    assert "#2FAC66" in qss
    assert "QPushButton#primarySessionButton" in qss
    assert "QToolButton#secondaryMenuButton" in qss
    assert "QWidget#navigationPanel QPushButton:checked" in qss
    assert "QLabel#dialogHeadlineLabel" in qss
    assert "QPlainTextEdit" in qss
    assert "QTabWidget::pane" in qss
    assert "QGroupBox::title" in qss

    assert "#252525" not in qss
    assert "#2D2D2D" not in qss
    assert "#2FACC6" not in qss
