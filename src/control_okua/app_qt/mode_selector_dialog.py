from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
)


class ModeSelectorDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Seleccionar modo de operación")
        self.setModal(True)
        self.resize(460, 220)

        layout = QVBoxLayout(self)

        title = QLabel(
            "Seleccione cómo desea operar Control OKÚA.\n"
            "Serial: usa puertos COM (compatibilidad CKv1).\n"
            "Ethernet/UDP: recibe paquetes UDP desde la red (CKv2)."
        )
        title.setWordWrap(True)
        layout.addWidget(title)

        self.serial_radio = QRadioButton("Serial")
        self.serial_radio.setChecked(True)
        layout.addWidget(self.serial_radio)

        self.udp_radio = QRadioButton("Ethernet/UDP")
        layout.addWidget(self.udp_radio)

        buttons = QDialogButtonBox(self)
        continue_btn = buttons.addButton("Continuar", QDialogButtonBox.AcceptRole)
        cancel_btn = buttons.addButton("Cancelar", QDialogButtonBox.RejectRole)
        continue_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def get_mode(self) -> str:
        if self.udp_radio.isChecked():
            return "udp"
        return "serial"

    @staticmethod
    def choose_mode(parent=None) -> str:
        auto_mode = os.getenv("CKV2_AUTOMODE", "").strip().lower()
        if auto_mode in {"serial", "udp"}:
            return auto_mode

        dialog = ModeSelectorDialog(parent=parent)
        dialog.exec()
        return dialog.get_mode()
