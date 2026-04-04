from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
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
        on_apply_remote_settings: Callable[[bool, str], tuple[Any, str]],
        on_open_firmware_manager: Callable[[], None],
        on_notify: Callable[..., None] | None,
        state_provider: Callable[[], tuple[dict[str, Any], Path, list[str]]],
        remote_status_provider: Callable[[], Any | None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("advancedToolsDialog")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("QDialog#advancedToolsDialog { background-color: #F7F4EC; }")
        self.setWindowTitle("Herramientas avanzadas")
        self.resize(980, 680)

        self._on_open_folder = on_open_folder
        self._on_view_config = on_view_config
        self._on_reload_config = on_reload_config
        self._on_apply_remote_settings = on_apply_remote_settings
        self._on_open_firmware_manager = on_open_firmware_manager
        self._on_notify = on_notify
        self._state_provider = state_provider
        self._remote_status_provider = remote_status_provider

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

        remote_group = QGroupBox("Servicio remoto")
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
        remote_form.addRow("Store usuarios:", self.remote_store_label)
        self.remote_failure_label = QLabel("-")
        self.remote_failure_label.setWordWrap(True)
        remote_form.addRow("Último fallo:", self.remote_failure_label)
        remote_layout.addLayout(remote_form)

        remote_apply_hint = QLabel(
            "Cambie aquí el modo operativo del gateway remoto sin editar config.json. "
            "El servicio se guarda y se intenta reaplicar de inmediato."
        )
        remote_apply_hint.setWordWrap(True)
        remote_layout.addWidget(remote_apply_hint)

        remote_apply_form = QFormLayout()
        self.remote_enabled_checkbox = QCheckBox("Servicio remoto habilitado")
        remote_apply_form.addRow("Habilitado:", self.remote_enabled_checkbox)
        self.remote_exposure_mode_combo = QComboBox(self)
        self.remote_exposure_mode_combo.addItem("Solo este PC (local_only)", "local_only")
        self.remote_exposure_mode_combo.addItem("Solo Tailscale (tailscale_only)", "tailscale_only")
        remote_apply_form.addRow("Modo rápido:", self.remote_exposure_mode_combo)
        remote_layout.addLayout(remote_apply_form)

        remote_actions_layout = QHBoxLayout()
        self.remote_apply_button = QPushButton("Aplicar servicio remoto")
        self.remote_apply_button.clicked.connect(self._handle_apply_remote_settings_clicked)
        remote_actions_layout.addWidget(self.remote_apply_button)
        remote_actions_layout.addStretch(1)
        remote_layout.addLayout(remote_actions_layout)
        root_layout.addWidget(remote_group)

        firmware_group = QGroupBox("Firmware")
        firmware_layout = QVBoxLayout(firmware_group)
        firmware_hint = QLabel(
            "Abra el Firmware Manager para revisar el catálogo técnico, "
            "importar bins y marcar current por target."
        )
        firmware_hint.setWordWrap(True)
        firmware_layout.addWidget(firmware_hint)

        firmware_actions_layout = QHBoxLayout()
        self.open_firmware_manager_button = QPushButton("Firmware Manager")
        self.open_firmware_manager_button.clicked.connect(
            self._handle_open_firmware_manager_clicked
        )
        firmware_actions_layout.addWidget(self.open_firmware_manager_button)
        firmware_actions_layout.addStretch(1)
        firmware_layout.addLayout(firmware_actions_layout)

        root_layout.addWidget(firmware_group)

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
        remote_cfg = cfg.get("remote_api")
        remote_enabled = False
        configured_exposure_mode = "local_only"
        if isinstance(remote_cfg, dict):
            remote_enabled = remote_cfg.get("enabled") is True
            raw_exposure_mode = remote_cfg.get("exposure_mode")
            if raw_exposure_mode in {"local_only", "tailscale_only"}:
                configured_exposure_mode = str(raw_exposure_mode)
        self.remote_enabled_checkbox.setChecked(remote_enabled)
        exposure_index = self.remote_exposure_mode_combo.findData(configured_exposure_mode)
        if exposure_index >= 0:
            self.remote_exposure_mode_combo.setCurrentIndex(exposure_index)
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
            str(getattr(remote_status, "local_access_url", None) or "No sugerida")
        )
        self.remote_remote_url_label.setText(
            str(getattr(remote_status, "remote_access_url", None) or "No sugerida")
        )
        self.remote_store_label.setText(
            str(getattr(remote_status, "user_store_path", None) or "No disponible")
        )
        self.remote_failure_label.setText(
            str(getattr(remote_status, "failure_message", None) or "Ninguno")
        )

    def _handle_reload_clicked(self) -> None:
        self._on_reload_config()
        cfg, config_path, warnings = self._state_provider()
        self.set_state(cfg, config_path, warnings)

    def _handle_apply_remote_settings_clicked(self) -> None:
        exposure_mode = str(self.remote_exposure_mode_combo.currentData() or "local_only")
        enabled = self.remote_enabled_checkbox.isChecked()
        try:
            _status, message = self._on_apply_remote_settings(enabled, exposure_mode)
        except Exception as exc:
            cfg, config_path, warnings = self._state_provider()
            self.set_state(cfg, config_path, warnings)
            QMessageBox.warning(
                self,
                "Servicio remoto",
                f"No se pudo actualizar el servicio remoto: {exc}",
            )
            return

        cfg, config_path, warnings = self._state_provider()
        self.set_state(cfg, config_path, warnings)
        if callable(self._on_notify):
            self._on_notify(title="Servicio remoto", message=message, level="success")

    def _handle_open_firmware_manager_clicked(self) -> None:
        self._on_open_firmware_manager()
