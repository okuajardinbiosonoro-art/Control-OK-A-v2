from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
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
            subtitle="Entrada operator-first y operación principal.",
        ),
        ShellNavItem(
            key="nodes",
            label="Nodos",
            subtitle="Vista detallada de nodos en vivo.",
        ),
        ShellNavItem(
            key="diagnostics",
            label="Diagnóstico",
            subtitle="Estado técnico, runtime y evidencia.",
        ),
        ShellNavItem(
            key="firmware",
            label="Firmware",
            subtitle="Catálogo técnico y OTA local.",
        ),
        ShellNavItem(
            key="technical",
            label="Técnico",
            subtitle="Control F3 y herramientas avanzadas.",
        ),
    ]
    if include_remote:
        items.append(
            ShellNavItem(
                key="remote",
                label="Remoto",
                subtitle="Estado y exposición de la consola remota.",
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

        brand_label = QLabel("CKv2")
        brand_font = brand_label.font()
        brand_font.setBold(True)
        brand_font.setPointSize(brand_font.pointSize() + 6)
        brand_label.setFont(brand_font)
        layout.addWidget(brand_label)

        hint_label = QLabel("Shell principal")
        hint_label.setObjectName("shellHintLabel")
        layout.addWidget(hint_label)

        for item in self._items:
            button = QPushButton(item.label, self)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, page_key=item.key: self.section_requested.emit(page_key))
            button.setMinimumHeight(42)
            self._button_group.addButton(button)
            self._buttons_by_key[item.key] = button
            layout.addWidget(button)

        layout.addStretch(1)
