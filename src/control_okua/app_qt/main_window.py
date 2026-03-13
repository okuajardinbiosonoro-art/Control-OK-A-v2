from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from control_okua.app_qt.mode_selector_dialog import ModeSelectorDialog
from control_okua.app_qt.widgets import ConfigViewDialog, MidiOutputsWidget
from control_okua.core.config.config_schema import load_config, save_config


class MainWindow(QMainWindow):
    def __init__(
        self,
        cfg: dict[str, Any],
        config_path: Path,
        warnings: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.cfg = cfg
        self.config_path = config_path
        self.warnings = list(warnings or [])

        self.setWindowTitle("Control OKÚA v2")
        self.resize(1100, 700)

        self._summary_labels: dict[str, QLabel] = {}
        self._build_ui()
        self.refresh_ui()

    def _build_ui(self) -> None:
        central = QWidget(self)
        root_layout = QVBoxLayout(central)
        self.setCentralWidget(central)

        header_layout = QHBoxLayout()
        self.title_label = QLabel("Control OKÚA v2")
        title_font = self.title_label.font()
        title_font.setPointSize(title_font.pointSize() + 6)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        header_layout.addWidget(self.title_label)

        self.mode_label = QLabel("Modo: (sin seleccionar)")
        header_layout.addWidget(self.mode_label)
        header_layout.addStretch(1)

        self.change_mode_button = QPushButton("Cambiar modo...")
        self.change_mode_button.clicked.connect(self.change_mode)
        header_layout.addWidget(self.change_mode_button)

        self.reload_button = QPushButton("Recargar config")
        self.reload_button.clicked.connect(self.reload_config)
        header_layout.addWidget(self.reload_button)

        self.open_folder_button = QPushButton("Abrir carpeta")
        self.open_folder_button.clicked.connect(self.open_config_folder)
        header_layout.addWidget(self.open_folder_button)

        self.view_config_button = QPushButton("Ver config")
        self.view_config_button.clicked.connect(self.view_config)
        header_layout.addWidget(self.view_config_button)

        root_layout.addLayout(header_layout)

        self.config_path_label = QLabel()
        self.config_path_label.setWordWrap(True)
        root_layout.addWidget(self.config_path_label)

        warnings_group = QGroupBox("Warnings")
        warnings_layout = QVBoxLayout(warnings_group)
        self.warnings_view = QTextEdit(self)
        self.warnings_view.setReadOnly(True)
        warnings_layout.addWidget(self.warnings_view)
        root_layout.addWidget(warnings_group)

        content_layout = QHBoxLayout()
        root_layout.addLayout(content_layout, 1)

        summary_group = QGroupBox("Resumen de Config")
        summary_layout = QFormLayout(summary_group)
        summary_fields = [
            ("version", "Version"),
            ("mode", "Mode"),
            ("serial.baudrate", "Serial baudrate"),
            ("serial.flush_ms", "Serial flush_ms"),
            ("serial.max_silence_s", "Serial max_silence_s"),
            ("udp.bind_ip", "UDP bind_ip"),
            ("udp.evt_port", "UDP evt_port"),
            ("udp.stat_port", "UDP stat_port"),
            ("udp.cmd_port", "UDP cmd_port"),
            ("logging.enabled", "Logging enabled"),
            ("logging.format", "Logging format"),
            ("logging.folder", "Logging folder"),
        ]
        for key, label_text in summary_fields:
            value_label = QLabel("-")
            value_label.setWordWrap(True)
            summary_layout.addRow(label_text, value_label)
            self._summary_labels[key] = value_label

        content_layout.addWidget(summary_group, 1)

        midi_group = QGroupBox("MIDI Outputs")
        midi_layout = QVBoxLayout(midi_group)
        self.midi_outputs_widget = MidiOutputsWidget(self)
        midi_layout.addWidget(self.midi_outputs_widget)
        content_layout.addWidget(midi_group, 1)

    def refresh_ui(self) -> None:
        mode_text = self._mode_text(self.cfg.get("mode"))
        self.mode_label.setText(f"Modo: {mode_text}")
        self.config_path_label.setText(f"Config path: {self.config_path}")
        self.statusBar().showMessage(f"Config: {self.config_path} | Mode: {mode_text}")

        if self.warnings:
            self.warnings_view.setPlainText("\n".join(self.warnings))
        else:
            self.warnings_view.setPlainText("Sin advertencias.")

        serial_cfg = self.cfg.get("serial") if isinstance(self.cfg.get("serial"), dict) else {}
        udp_cfg = self.cfg.get("udp") if isinstance(self.cfg.get("udp"), dict) else {}
        logging_cfg = self.cfg.get("logging") if isinstance(self.cfg.get("logging"), dict) else {}

        values = {
            "version": str(self.cfg.get("version", "-")),
            "mode": mode_text,
            "serial.baudrate": str(serial_cfg.get("baudrate", "-")),
            "serial.flush_ms": str(serial_cfg.get("flush_ms", "-")),
            "serial.max_silence_s": str(serial_cfg.get("max_silence_s", "-")),
            "udp.bind_ip": str(udp_cfg.get("bind_ip", "-")),
            "udp.evt_port": str(udp_cfg.get("evt_port", "-")),
            "udp.stat_port": str(udp_cfg.get("stat_port", "-")),
            "udp.cmd_port": str(udp_cfg.get("cmd_port", "-")),
            "logging.enabled": self._bool_text(logging_cfg.get("enabled")),
            "logging.format": str(logging_cfg.get("format", "-")),
            "logging.folder": str(logging_cfg.get("folder", "-")),
        }
        for key, label in self._summary_labels.items():
            label.setText(values.get(key, "-"))

        self.midi_outputs_widget.refresh_from_config(self.cfg)

    def change_mode(self) -> None:
        current_mode = self.cfg.get("mode")
        selected_mode = ModeSelectorDialog.choose_mode(self)
        if selected_mode == current_mode:
            return

        self.cfg["mode"] = selected_mode
        save_config(self.cfg, self.config_path)
        self.warnings = [f"Modo actualizado desde UI a '{selected_mode}'."]
        self.refresh_ui()

    def reload_config(self) -> None:
        cfg, warnings, config_path = load_config()
        self.cfg = cfg
        self.warnings = warnings
        self.config_path = config_path
        self.refresh_ui()

    def open_config_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.config_path.parent)))

    def view_config(self) -> None:
        dialog = ConfigViewDialog(self._config_pretty_text(), parent=self)
        dialog.exec()

    def _config_pretty_text(self) -> str:
        return json.dumps(self.cfg, indent=2, ensure_ascii=False)

    @staticmethod
    def _mode_text(value: object) -> str:
        if isinstance(value, str) and value in {"serial", "udp"}:
            return value
        return "(sin seleccionar)"

    @staticmethod
    def _bool_text(value: object) -> str:
        if isinstance(value, bool):
            return "Si" if value else "No"
        return "-"
