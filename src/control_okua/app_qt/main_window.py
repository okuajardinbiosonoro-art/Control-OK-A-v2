from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow


class MainWindow(QMainWindow):
    def __init__(self, cfg: dict[str, Any], config_path: Path) -> None:
        super().__init__()
        self.setWindowTitle("Control OKÚA v2")
        self.resize(1100, 700)

        mode = str(cfg.get("mode", "serial"))
        label = QLabel(f"CKv2 - Ticket 1 OK\nMode: {mode}")
        label.setAlignment(Qt.AlignCenter)
        self.setCentralWidget(label)

        self.statusBar().showMessage(f"Config: {config_path}")
