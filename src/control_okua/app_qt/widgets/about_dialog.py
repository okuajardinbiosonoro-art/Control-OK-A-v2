from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from control_okua.app_qt.design_system import (
    APP_ABOUT_NAME,
    APP_BRAND_LABEL,
    APP_EDITION_LABEL,
)


class AboutDialog(QDialog):
    def __init__(
        self,
        *,
        version: str | None = None,
        active_profile: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("aboutDialog")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("Acerca de")
        self.setModal(True)
        self.setFixedSize(520, 400)
        self._version = version
        self._active_profile = active_profile
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(0)

        # — Encabezado de marca —
        header = QWidget(self)
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        header.setObjectName("aboutHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 16)
        header_layout.setSpacing(4)

        brand = QLabel(APP_BRAND_LABEL, header)
        brand.setObjectName("aboutBrandLabel")
        brand_font = brand.font()
        brand_font.setPointSize(brand_font.pointSize() + 10)
        brand_font.setBold(True)
        brand.setFont(brand_font)
        header_layout.addWidget(brand)

        edition = QLabel(APP_EDITION_LABEL, header)
        edition.setObjectName("aboutEditionLabel")
        header_layout.addWidget(edition)

        root.addWidget(header)

        # — Descripción —
        desc = QLabel(
            "Sistema de monitoreo y control en tiempo real para instalaciones OKÚA.\n"
            "Gestión de sesiones, nodos, firmware OTA y acceso remoto desde\n"
            "una interfaz operativa unificada.",
            self,
        )
        desc.setObjectName("aboutDescLabel")
        desc.setWordWrap(True)
        root.addWidget(desc)
        root.addSpacing(20)

        # — Línea de detalles técnicos —
        details_layout = QVBoxLayout()
        details_layout.setSpacing(6)

        profile_text = self._active_profile or "sin perfil"
        version_text = self._version or "—"

        for label_text, value_text in (
            ("Versión de configuración", version_text),
            ("Perfil activo", profile_text),
            ("Plataforma", "PySide6 · Python 3.11+"),
            ("Transporte soportado", "Serial USB · UDP"),
        ):
            row = QHBoxLayout()
            lbl = QLabel(f"{label_text}:", self)
            lbl.setObjectName("aboutFieldLabel")
            val = QLabel(value_text, self)
            val.setObjectName("aboutFieldValue")
            row.addWidget(lbl)
            row.addWidget(val, 1)
            details_layout.addLayout(row)

        root.addLayout(details_layout)
        root.addSpacing(20)

        # — Nota de construcción —
        build_note = QLabel(
            "Desarrollado con atención al detalle para el equipo OKÚA.\n"
            "Cada sección fue pensada para el técnico que opera en campo.",
            self,
        )
        build_note.setObjectName("aboutBuildNoteLabel")
        build_note.setWordWrap(True)
        root.addWidget(build_note)

        root.addStretch(1)

        # — Botón de cierre —
        buttons = QDialogButtonBox(self)
        close_btn = buttons.addButton("Cerrar", QDialogButtonBox.AcceptRole)
        close_btn.setProperty("role", "secondary")
        close_btn.clicked.connect(self.accept)
        root.addWidget(buttons)
