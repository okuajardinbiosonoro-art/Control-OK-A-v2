from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from control_okua.app_qt.widgets.midi_outputs_widget import MidiOutputsWidget


class AdvancedToolsDialog(QDialog):
    def __init__(
        self,
        on_open_folder: Callable[[], None],
        on_view_config: Callable[[], None],
        on_reload_config: Callable[[], None],
        on_notify: Callable[..., None] | None,
        state_provider: Callable[[], tuple[dict[str, Any], Path, list[str]]],
        remote_status_provider: Callable[[], Any | None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("advancedToolsDialog")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("Centro técnico")
        self.resize(920, 580)

        self._on_open_folder = on_open_folder
        self._on_view_config = on_view_config
        self._on_reload_config = on_reload_config
        self._on_notify = on_notify
        self._state_provider = state_provider
        self._remote_status_provider = remote_status_provider

        self._build_ui()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)

        intro_label = QLabel(
            "Herramientas de soporte para configuración, remoto y firmware."
        )
        intro_label.setObjectName("sectionHintLabel")
        intro_label.setWordWrap(True)
        root_layout.addWidget(intro_label)

        config_group = QGroupBox("Configuración")
        config_group.setProperty("sectionRole", "summary")
        config_layout = QVBoxLayout(config_group)

        config_form = QFormLayout()
        self.config_path_label = QLabel("-")
        self.config_path_label.setWordWrap(True)
        config_form.addRow("Archivo de configuración:", self.config_path_label)
        config_layout.addLayout(config_form)

        actions_layout = QHBoxLayout()

        self.open_folder_button = QPushButton("Abrir carpeta")
        self.open_folder_button.setProperty("role", "contextual")
        self.open_folder_button.clicked.connect(self._on_open_folder)
        actions_layout.addWidget(self.open_folder_button)

        self.view_config_button = QPushButton("Ver configuración")
        self.view_config_button.setProperty("role", "secondary")
        self.view_config_button.clicked.connect(self._on_view_config)
        actions_layout.addWidget(self.view_config_button)

        self.reload_button = QPushButton("Recargar configuración")
        self.reload_button.setProperty("role", "secondary")
        self.reload_button.clicked.connect(self._handle_reload_clicked)
        actions_layout.addWidget(self.reload_button)
        actions_layout.addStretch(1)

        config_layout.addLayout(actions_layout)

        self.warnings_label = QLabel("Advertencias de configuración: -")
        self.warnings_label.setWordWrap(True)
        config_layout.addWidget(self.warnings_label)

        root_layout.addWidget(config_group)

        remote_group = QGroupBox("Servicio remoto")
        remote_group.setProperty("sectionRole", "summary")
        remote_layout = QVBoxLayout(remote_group)
        remote_form = QFormLayout()
        self.remote_status_label = QLabel("-")
        self.remote_status_label.setWordWrap(True)
        remote_form.addRow("Estado:", self.remote_status_label)
        self.remote_exposure_mode_label = QLabel("-")
        self.remote_exposure_mode_label.setWordWrap(True)
        remote_form.addRow("Exposición:", self.remote_exposure_mode_label)
        self.remote_bind_label = QLabel("-")
        self.remote_bind_label.setWordWrap(True)
        remote_form.addRow("Bind efectivo:", self.remote_bind_label)
        self.remote_port_label = QLabel("-")
        self.remote_port_label.setWordWrap(True)
        remote_form.addRow("Puerto:", self.remote_port_label)
        self.remote_local_url_label = QLabel("-")
        self.remote_local_url_label.setWordWrap(True)
        remote_form.addRow("URL local:", self.remote_local_url_label)
        self.remote_remote_url_label = QLabel("-")
        self.remote_remote_url_label.setWordWrap(True)
        remote_form.addRow("URL remota:", self.remote_remote_url_label)
        self.remote_store_label = QLabel("-")
        self.remote_store_label.setWordWrap(True)
        remote_form.addRow("Base de usuarios:", self.remote_store_label)
        self.remote_failure_label = QLabel("-")
        self.remote_failure_label.setWordWrap(True)
        remote_form.addRow("Último error:", self.remote_failure_label)
        remote_layout.addLayout(remote_form)

        remote_hint = QLabel("Para cambiar el modo o activar el servicio, usa la pestaña Remoto.")
        remote_hint.setObjectName("sectionHintLabel")
        remote_hint.setWordWrap(True)
        remote_layout.addWidget(remote_hint)
        root_layout.addWidget(remote_group)

        midi_group = QGroupBox("Salidas MIDI")
        midi_group.setProperty("sectionRole", "summary")
        midi_layout = QVBoxLayout(midi_group)
        self.midi_outputs_widget = MidiOutputsWidget(self)
        midi_layout.addWidget(self.midi_outputs_widget)
        root_layout.addWidget(midi_group, 1)

    def set_state(
        self,
        cfg: dict[str, Any],
        config_path: Path,
        warnings: list[str] | None = None,
    ) -> None:
        warning_count = len(warnings or [])
        self.config_path_label.setText(str(config_path))
        self.warnings_label.setText(f"Advertencias de configuración: {warning_count}")
        self.midi_outputs_widget.refresh_from_config(cfg)
        remote_status = self._remote_status_provider()
        if remote_status is None:
            self.remote_status_label.setText("-")
            self.remote_exposure_mode_label.setText("-")
            self.remote_bind_label.setText("-")
            self.remote_port_label.setText("-")
            self.remote_local_url_label.setText("-")
            self.remote_remote_url_label.setText("-")
            self.remote_store_label.setText("-")
            self.remote_failure_label.setText("-")
            return

        self.remote_status_label.setText(str(getattr(remote_status, "service_state", "-")))
        self.remote_exposure_mode_label.setText(str(getattr(remote_status, "exposure_mode", "-")))
        bind_text = getattr(remote_status, "effective_bind_host", None) or "-"
        self.remote_bind_label.setText(str(bind_text))
        self.remote_port_label.setText(str(getattr(remote_status, "port", "-")))
        self.remote_local_url_label.setText(
            str(getattr(remote_status, "local_access_url", None) or "No disponible")
        )
        self.remote_remote_url_label.setText(
            str(getattr(remote_status, "remote_access_url", None) or "No disponible")
        )
        self.remote_store_label.setText(
            str(getattr(remote_status, "user_store_path", None) or "No configurado")
        )
        self.remote_failure_label.setText(
            str(getattr(remote_status, "failure_message", None) or "Sin errores")
        )

    def _handle_reload_clicked(self) -> None:
        self._on_reload_config()
        cfg, config_path, warnings = self._state_provider()
        self.set_state(cfg, config_path, warnings)
