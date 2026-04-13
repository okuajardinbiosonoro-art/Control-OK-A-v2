from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from control_okua.app_qt.design_system import (
    APP_BRAND_LABEL,
    APP_EDITION_LABEL,
    BRAND_ACCENT,
    BRAND_DEEP,
    BRAND_EARTH,
    BRAND_SAND,
)


@dataclass(frozen=True)
class ShellNavItem:
    key: str
    label: str
    subtitle: str


def build_primary_shell_items(*, include_remote: bool = True) -> tuple[ShellNavItem, ...]:
    items = [
        ShellNavItem(
            key="home",
            label="Inicio",
            subtitle="Centro de operación con mapa en tiempo real.",
        ),
        ShellNavItem(
            key="nodes",
            label="Nodos",
            subtitle="Listado en vivo por caja y estado.",
        ),
        ShellNavItem(
            key="diagnostics",
            label="Diagnóstico",
            subtitle="Salud del sistema, preflight y runtime.",
        ),
        ShellNavItem(
            key="firmware",
            label="Firmware",
            subtitle="Catálogo de firmware y despliegue OTA.",
        ),
        ShellNavItem(
            key="technical",
            label="Técnico",
            subtitle="Control F3 y utilidades avanzadas.",
        ),
    ]
    if include_remote:
        items.append(
            ShellNavItem(
                key="remote",
                label="Remoto",
                subtitle="Estado del acceso remoto de CKv2.",
            )
        )
    return tuple(items)


class NavigationPanel(QWidget):
    section_requested = Signal(str)

    def __init__(self, items: tuple[ShellNavItem, ...], parent=None) -> None:
        super().__init__(parent)
        self._items = items
        self._buttons_by_key: dict[str, QPushButton] = {}
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._build_ui()

    @property
    def items(self) -> tuple[ShellNavItem, ...]:
        return self._items

    def set_current_key(self, key: str) -> None:
        button = self._buttons_by_key.get(str(key))
        if button is not None:
            button.setChecked(True)

    def button_for_key(self, key: str) -> QPushButton | None:
        return self._buttons_by_key.get(str(key))

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        self.setObjectName("navigationPanel")

        brand_label = QLabel(APP_BRAND_LABEL)
        brand_label.setObjectName("navigationBrandLabel")
        brand_font = brand_label.font()
        brand_font.setBold(True)
        brand_font.setPointSize(brand_font.pointSize() + 6)
        brand_label.setFont(brand_font)
        layout.addWidget(brand_label)

        edition_label = QLabel(APP_EDITION_LABEL)
        edition_label.setObjectName("navigationEditionLabel")
        layout.addWidget(edition_label)

        for item in self._items:
            button = QPushButton(item.label, self)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, page_key=item.key: self.section_requested.emit(page_key))
            button.setMinimumHeight(42)
            self._button_group.addButton(button)
            self._buttons_by_key[item.key] = button
            layout.addWidget(button)

        layout.addStretch(1)
