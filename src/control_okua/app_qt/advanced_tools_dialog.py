from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from control_okua.app_qt.widgets import MidiOutputsWidget


class AdvancedToolsDialog(QDialog):
    def __init__(
        self,
        on_open_folder: Callable[[], None],
        on_view_config: Callable[[], None],
        on_reload_config: Callable[[], None],
        state_provider: Callable[[], tuple[dict[str, Any], Path, list[str]]],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Herramientas avanzadas")
        self.resize(980, 680)

        self._on_open_folder = on_open_folder
        self._on_view_config = on_view_config
        self._on_reload_config = on_reload_config
        self._state_provider = state_provider

        self._build_ui()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)

        intro_label = QLabel(
            "Use estas herramientas para diagnóstico técnico y revisión de configuración."
        )
        intro_label.setWordWrap(True)
        root_layout.addWidget(intro_label)

        config_group = QGroupBox("Configuración")
        config_layout = QVBoxLayout(config_group)

        config_form = QFormLayout()
        self.config_path_label = QLabel("-")
        self.config_path_label.setWordWrap(True)
        config_form.addRow("Archivo config:", self.config_path_label)
        config_layout.addLayout(config_form)

        actions_layout = QHBoxLayout()

        self.open_folder_button = QPushButton("Abrir carpeta")
        self.open_folder_button.clicked.connect(self._on_open_folder)
        actions_layout.addWidget(self.open_folder_button)

        self.view_config_button = QPushButton("Ver config")
        self.view_config_button.clicked.connect(self._on_view_config)
        actions_layout.addWidget(self.view_config_button)

        self.reload_button = QPushButton("Recargar config")
        self.reload_button.clicked.connect(self._handle_reload_clicked)
        actions_layout.addWidget(self.reload_button)
        actions_layout.addStretch(1)

        config_layout.addLayout(actions_layout)

        self.warnings_label = QLabel("Advertencias de config: -")
        self.warnings_label.setWordWrap(True)
        config_layout.addWidget(self.warnings_label)

        root_layout.addWidget(config_group)

        midi_group = QGroupBox("Salidas MIDI")
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
        self.warnings_label.setText(f"Advertencias de config: {warning_count}")
        self.midi_outputs_widget.refresh_from_config(cfg)

    def _handle_reload_clicked(self) -> None:
        self._on_reload_config()
        cfg, config_path, warnings = self._state_provider()
        self.set_state(cfg, config_path, warnings)
