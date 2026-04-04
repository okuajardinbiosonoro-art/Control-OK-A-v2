from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QPlainTextEdit, QVBoxLayout


class ConfigViewDialog(QDialog):
    def __init__(self, config_text: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("configViewDialog")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("QDialog#configViewDialog { background-color: #F7F4EC; }")
        self.setWindowTitle("Ver config")
        self.resize(760, 560)

        layout = QVBoxLayout(self)

        editor = QPlainTextEdit(self)
        editor.setReadOnly(True)
        editor.setPlainText(config_text)
        layout.addWidget(editor)
