from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
)

from control_okua.core.profiles.profile_schema import ProfileDefinition
from control_okua.core.profiles.profile_service import (
    is_known_profile_id,
    list_available_profiles,
)


def build_profile_selection_copy(definition: ProfileDefinition) -> str:
    return (
        f"{definition.description}\n"
        f"Modo asociado: {definition.mode.upper()}\n"
        f"Cuándo usarlo: {definition.usage_level}"
    )


class ProfileSelectorDialog(QDialog):
    def __init__(self, current_profile_id: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("profileSelectorDialog")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("Perfil de operación")
        self.setModal(True)
        self.resize(620, 460)

        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._profile_buttons: dict[str, QRadioButton] = {}

        self._build_ui(current_profile_id)

    def _build_ui(self, current_profile_id: str | None) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title = QLabel(
            "Selecciona cómo deseas operar Control OKÚA."
        )
        title.setObjectName("dialogHeadlineLabel")
        title.setWordWrap(True)
        layout.addWidget(title)

        hint = QLabel("Puedes cambiar este perfil más adelante desde Aplicación.")
        hint.setObjectName("dialogSubtleLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        first_radio: QRadioButton | None = None
        for definition in list_available_profiles():
            group_box = QGroupBox(definition.short_name, self)
            group_box.setProperty("sectionRole", "summary")
            group_layout = QVBoxLayout(group_box)

            radio = QRadioButton("Elegir este perfil", group_box)
            group_layout.addWidget(radio)
            self._button_group.addButton(radio)
            self._profile_buttons[definition.profile_id] = radio

            details = QLabel(build_profile_selection_copy(definition), group_box)
            details.setWordWrap(True)
            group_layout.addWidget(details)

            layout.addWidget(group_box)

            if first_radio is None:
                first_radio = radio

        if isinstance(current_profile_id, str) and current_profile_id in self._profile_buttons:
            self._profile_buttons[current_profile_id].setChecked(True)
        elif first_radio is not None:
            first_radio.setChecked(True)

        buttons = QDialogButtonBox(self)
        self.confirm_button = buttons.addButton(
            "Continuar", QDialogButtonBox.AcceptRole
        )
        self.cancel_button = buttons.addButton("Cancelar", QDialogButtonBox.RejectRole)
        self.confirm_button.setProperty("role", "primary")
        self.cancel_button.setProperty("role", "secondary")
        self.confirm_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def selected_profile_id(self) -> str | None:
        for profile_id, radio in self._profile_buttons.items():
            if radio.isChecked():
                return profile_id
        return None

    @staticmethod
    def choose_profile(
        current_profile_id: str | None = None,
        parent=None,
    ) -> str | None:
        auto_profile = os.getenv("CKV2_AUTOPROFILE", "").strip().lower()
        if is_known_profile_id(auto_profile):
            return auto_profile

        dialog = ProfileSelectorDialog(
            current_profile_id=current_profile_id,
            parent=parent,
        )
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.selected_profile_id()
