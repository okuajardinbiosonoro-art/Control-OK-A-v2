from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from control_okua.app_qt.advanced_tools_dialog import AdvancedToolsDialog
from control_okua.app_qt.profile_selector_dialog import ProfileSelectorDialog
from control_okua.app_qt.widgets import ConfigViewDialog
from control_okua.app_qt.viewmodels import (
    PreflightDiagnosticRow,
    build_general_status_summary,
    build_logging_summary,
    build_midi_summary,
    build_mode_summary,
    build_operation_summary,
    build_preflight_counts,
    build_preflight_diagnostic_rows,
    build_preflight_primary_message,
    build_preflight_runtime_note,
    build_preflight_status_label,
    build_preflight_summary_text,
    build_profile_mode_summary,
    build_profile_summary,
    build_session_action_state,
    build_session_backend_summary,
    build_session_capabilities_summary,
    build_session_message_summary,
    build_session_status_summary,
    build_transport_summary,
)
from control_okua.core.preflight import PreflightReport
from control_okua.core.config.config_schema import load_config, save_config
from control_okua.core.profiles.profile_service import (
    infer_profile_from_config,
    is_known_profile_id,
    set_active_profile,
)
from control_okua.core.session import SessionSnapshot, SessionState
from control_okua.services.session_controller import SessionController


class MainWindow(QMainWindow):
    def __init__(
        self,
        cfg: dict[str, Any],
        config_path: Path,
        warnings: list[str] | None = None,
        session_controller: SessionController | None = None,
    ) -> None:
        super().__init__()
        self.cfg = cfg
        self.config_path = config_path
        self.warnings = list(warnings or [])

        self.setWindowTitle("Control OKÚA v2")
        self.resize(1100, 700)

        self._operation_summary_labels: dict[str, QLabel] = {}
        self._operation_readiness_labels: dict[str, QLabel] = {}
        self._diagnostic_summary_labels: dict[str, QLabel] = {}
        self._advanced_dialog: AdvancedToolsDialog | None = None
        self.session_controller = session_controller or SessionController(
            self._session_cfg_provider,
            parent=self,
        )
        self._session_snapshot: SessionSnapshot = self.session_controller.get_snapshot()
        self._preflight_report: PreflightReport | None = self.session_controller.get_last_preflight_report()
        self._connect_session_signals()

        self._build_ui()
        self.refresh_ui()

    def _connect_session_signals(self) -> None:
        self.session_controller.session_state_changed.connect(self._on_session_state_changed)
        self.session_controller.session_snapshot_changed.connect(self._on_session_snapshot_changed)
        self.session_controller.session_error.connect(self._on_session_error)
        self.session_controller.session_message.connect(self._on_session_message)
        self.session_controller.preflight_report_changed.connect(self._on_preflight_report_changed)

    def _build_ui(self) -> None:
        central = QWidget(self)
        root_layout = QVBoxLayout(central)
        self.setCentralWidget(central)

        self.tabs = QTabWidget(self)
        self.tabs.addTab(self._build_operation_tab(), "Operación")
        self.tabs.addTab(self._build_nodes_tab(), "Nodos")
        self.tabs.addTab(self._build_diagnostics_tab(), "Diagnóstico")
        self.tabs.setCurrentIndex(0)
        root_layout.addWidget(self.tabs)

    def _build_operation_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        self.title_label = QLabel("Control OKÚA v2")
        title_font = self.title_label.font()
        title_font.setPointSize(title_font.pointSize() + 8)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        layout.addWidget(self.title_label)

        self.operation_subtitle_label = QLabel(
            "Aplicación lista para operación. La sesión aún no está iniciada."
        )
        self.operation_subtitle_label.setWordWrap(True)
        layout.addWidget(self.operation_subtitle_label)

        quick_actions_group = QGroupBox("Acciones rápidas")
        quick_actions_layout = QHBoxLayout(quick_actions_group)

        self.change_profile_button = QPushButton("Cambiar perfil")
        self.change_profile_button.clicked.connect(self.change_profile)
        quick_actions_layout.addWidget(self.change_profile_button)

        self.reload_button = QPushButton("Recargar configuración")
        self.reload_button.clicked.connect(self.reload_config)
        quick_actions_layout.addWidget(self.reload_button)

        self.advanced_tools_button = QPushButton("Herramientas avanzadas")
        self.advanced_tools_button.clicked.connect(self.open_advanced_tools)
        quick_actions_layout.addWidget(self.advanced_tools_button)
        quick_actions_layout.addStretch(1)

        layout.addWidget(quick_actions_group)

        session_actions_group = QGroupBox("Control de sesión")
        session_actions_layout = QHBoxLayout(session_actions_group)

        self.start_session_button = QPushButton("Iniciar sesión")
        self.start_session_button.clicked.connect(self.start_session)
        session_actions_layout.addWidget(self.start_session_button)

        self.stop_session_button = QPushButton("Detener sesión")
        self.stop_session_button.clicked.connect(self.stop_session)
        session_actions_layout.addWidget(self.stop_session_button)

        self.reset_session_error_button = QPushButton("Reiniciar error")
        self.reset_session_error_button.clicked.connect(self.reset_session_error)
        session_actions_layout.addWidget(self.reset_session_error_button)
        session_actions_layout.addStretch(1)

        layout.addWidget(session_actions_group)

        readiness_group = QGroupBox("Preparación de sesión")
        readiness_layout = QFormLayout(readiness_group)
        readiness_fields = [
            ("status", "Estado"),
            ("summary", "Resumen"),
            ("counts", "Conteos"),
            ("primary", "Mensaje principal"),
            ("runtime_note", "Nota runtime"),
        ]
        for key, field_name in readiness_fields:
            label = QLabel("-")
            label.setWordWrap(True)
            readiness_layout.addRow(field_name, label)
            self._operation_readiness_labels[key] = label
        layout.addWidget(readiness_group)

        cards_group = QGroupBox("Estado actual")
        cards_layout = QGridLayout(cards_group)

        cards = [
            ("profile", "Perfil activo"),
            ("profile_mode", "Modo asociado"),
            ("session_backend", "Backend esperado"),
            ("session_state", "Estado de sesión"),
            ("session_message", "Mensaje de sesión"),
            ("session_capabilities", "Capacidades de sesión"),
            ("operation", "Resumen operativo"),
            ("mode", "Modo técnico"),
            ("general", "Estado general"),
            ("transport", "Transporte configurado"),
            ("midi", "MIDI"),
            ("logging", "Logging"),
        ]
        for index, (key, title_text) in enumerate(cards):
            row = index // 2
            col = index % 2
            card_group = QGroupBox(title_text)
            card_layout = QVBoxLayout(card_group)
            value_label = QLabel("-")
            value_label.setWordWrap(True)
            card_layout.addWidget(value_label)
            cards_layout.addWidget(card_group, row, col)
            self._operation_summary_labels[key] = value_label

        layout.addWidget(cards_group, 1)

        return tab

    def _build_nodes_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        title_label = QLabel("Monitoreo de nodos")
        title_font = title_label.font()
        title_font.setPointSize(title_font.pointSize() + 2)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        empty_state_label = QLabel("Aún no hay datos en vivo.")
        empty_state_label.setWordWrap(True)
        layout.addWidget(empty_state_label)

        hint_label = QLabel("Los nodos aparecerán cuando la sesión esté en ejecución.")
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)

        self.nodes_table = QTableWidget(0, 9, self)
        self.nodes_table.setHorizontalHeaderLabels(
            [
                "node_id",
                "label",
                "tipo",
                "estado",
                "último visto",
                "pps",
                "pérdida",
                "RSSI",
                "último note/vel",
            ]
        )
        self.nodes_table.horizontalHeader().setStretchLastSection(True)
        self.nodes_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.nodes_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.nodes_table.verticalHeader().setVisible(False)
        layout.addWidget(self.nodes_table, 1)

        return tab

    def _build_diagnostics_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        summary_group = QGroupBox("Resumen técnico")
        summary_layout = QFormLayout(summary_group)

        fields = [
            ("profile", "Perfil"),
            ("config_path", "Archivo config"),
            ("mode", "Modo"),
            ("transport", "Transporte"),
            ("midi", "MIDI"),
            ("logging", "Logging"),
            ("general", "Estado"),
        ]
        for key, field_name in fields:
            label = QLabel("-")
            label.setWordWrap(True)
            summary_layout.addRow(field_name, label)
            self._diagnostic_summary_labels[key] = label

        layout.addWidget(summary_group)

        preflight_group = QGroupBox("Readiness / preflight")
        preflight_layout = QVBoxLayout(preflight_group)

        preflight_summary_form = QFormLayout()
        self.preflight_diag_status_label = QLabel("-")
        self.preflight_diag_status_label.setWordWrap(True)
        preflight_summary_form.addRow("Readiness", self.preflight_diag_status_label)

        self.preflight_diag_summary_label = QLabel("-")
        self.preflight_diag_summary_label.setWordWrap(True)
        preflight_summary_form.addRow("Resumen", self.preflight_diag_summary_label)

        self.preflight_diag_counts_label = QLabel("-")
        self.preflight_diag_counts_label.setWordWrap(True)
        preflight_summary_form.addRow("Conteos", self.preflight_diag_counts_label)
        preflight_layout.addLayout(preflight_summary_form)

        self.preflight_findings_table = QTableWidget(0, 4, self)
        self.preflight_findings_table.setHorizontalHeaderLabels(
            ["Severidad", "Código", "Mensaje", "Detalle"]
        )
        self.preflight_findings_table.horizontalHeader().setStretchLastSection(True)
        self.preflight_findings_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.preflight_findings_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.preflight_findings_table.verticalHeader().setVisible(False)
        preflight_layout.addWidget(self.preflight_findings_table)
        layout.addWidget(preflight_group)

        warnings_group = QGroupBox("Advertencias de configuración")
        warnings_layout = QVBoxLayout(warnings_group)
        self.warnings_view = QTextEdit(self)
        self.warnings_view.setReadOnly(True)
        warnings_layout.addWidget(self.warnings_view)
        layout.addWidget(warnings_group, 1)

        return tab

    def refresh_ui(self) -> None:
        profile_summary = build_profile_summary(self.cfg)
        profile_mode_summary = build_profile_mode_summary(self.cfg)
        operation_summary = build_operation_summary(self.cfg)
        mode_summary = build_mode_summary(self.cfg)
        transport_summary = build_transport_summary(self.cfg)
        midi_summary = build_midi_summary(self.cfg)
        logging_summary = build_logging_summary(self.cfg)
        general_summary = build_general_status_summary(self.cfg, self.warnings)
        session_status_summary = build_session_status_summary(self._session_snapshot)
        session_backend_summary = build_session_backend_summary(self._session_snapshot)
        session_message_summary = build_session_message_summary(self._session_snapshot)
        session_capabilities_summary = build_session_capabilities_summary(self._session_snapshot)
        session_action_state = build_session_action_state(self._session_snapshot)
        preflight_status = build_preflight_status_label(self._preflight_report)
        preflight_summary = build_preflight_summary_text(self._preflight_report)
        preflight_counts = build_preflight_counts(self._preflight_report)
        preflight_primary = build_preflight_primary_message(self._preflight_report)
        preflight_runtime_note = build_preflight_runtime_note(
            self._preflight_report,
            self._session_snapshot,
        )
        preflight_rows = build_preflight_diagnostic_rows(self._preflight_report)

        self._operation_summary_labels["profile"].setText(profile_summary)
        self._operation_summary_labels["profile_mode"].setText(profile_mode_summary)
        self._operation_summary_labels["session_backend"].setText(session_backend_summary)
        self._operation_summary_labels["session_state"].setText(session_status_summary)
        self._operation_summary_labels["session_message"].setText(session_message_summary)
        self._operation_summary_labels["session_capabilities"].setText(
            session_capabilities_summary
        )
        self._operation_summary_labels["operation"].setText(operation_summary)
        self._operation_summary_labels["mode"].setText(mode_summary)
        self._operation_summary_labels["general"].setText(general_summary)
        self._operation_summary_labels["transport"].setText(transport_summary)
        self._operation_summary_labels["midi"].setText(midi_summary)
        self._operation_summary_labels["logging"].setText(logging_summary)
        self._operation_readiness_labels["status"].setText(preflight_status)
        self._operation_readiness_labels["summary"].setText(preflight_summary)
        self._operation_readiness_labels["counts"].setText(preflight_counts)
        self._operation_readiness_labels["primary"].setText(preflight_primary)
        self._operation_readiness_labels["runtime_note"].setText(preflight_runtime_note)

        if self._session_snapshot.state is SessionState.STARTING:
            self.operation_subtitle_label.setText(
                "La sesión se está iniciando. Espere antes de cambiar configuración."
            )
        elif self._session_snapshot.state is SessionState.RUNNING:
            self.operation_subtitle_label.setText(
                "Sesión en ejecución. Detenga la sesión antes de cambiar perfil o configuración."
            )
        elif self._session_snapshot.state is SessionState.STOPPING:
            self.operation_subtitle_label.setText(
                "La sesión se está deteniendo. Espere antes de cambiar configuración."
            )
        elif self._session_snapshot.state is SessionState.ERROR:
            self.operation_subtitle_label.setText(
                "Sesión en error. Revise el mensaje de sesión y use 'Reiniciar error'."
            )
        elif self.warnings:
            self.operation_subtitle_label.setText(
                "Aplicación cargada con advertencias. Revise Diagnóstico. "
                "La sesión aún no está iniciada."
            )
        elif "perfil pendiente" in general_summary or "perfil incompleto" in general_summary:
            self.operation_subtitle_label.setText(
                "Seleccione un perfil operativo para continuar. "
                "La sesión aún no está iniciada."
            )
        elif self.cfg.get("mode") in {"serial", "udp"}:
            self.operation_subtitle_label.setText(
                "Aplicación lista para operación. La sesión aún no está iniciada."
            )
        else:
            self.operation_subtitle_label.setText(
                "Seleccione un perfil operativo para continuar. La sesión aún no está iniciada."
            )

        self.start_session_button.setEnabled(session_action_state.can_start_session)
        self.stop_session_button.setEnabled(session_action_state.can_stop_session)
        self.reset_session_error_button.setEnabled(session_action_state.can_reset_error)

        self.change_profile_button.setEnabled(session_action_state.can_edit_configuration)
        self.reload_button.setEnabled(session_action_state.can_edit_configuration)

        if self.warnings:
            self.warnings_view.setPlainText("\n".join(self.warnings))
        else:
            self.warnings_view.setPlainText("Sin advertencias actuales.")

        profile_diag_text = f"{profile_summary} | {profile_mode_summary}"
        self._diagnostic_summary_labels["profile"].setText(profile_diag_text)
        self._diagnostic_summary_labels["config_path"].setText(str(self.config_path))
        self._diagnostic_summary_labels["mode"].setText(mode_summary)
        self._diagnostic_summary_labels["transport"].setText(transport_summary)
        self._diagnostic_summary_labels["midi"].setText(midi_summary)
        self._diagnostic_summary_labels["logging"].setText(logging_summary)
        self._diagnostic_summary_labels["general"].setText(
            f"{general_summary} | {session_status_summary}"
        )
        self.preflight_diag_status_label.setText(preflight_status)
        self.preflight_diag_summary_label.setText(preflight_summary)
        self.preflight_diag_counts_label.setText(preflight_counts)
        self._refresh_preflight_findings_table(preflight_rows)

        self.statusBar().showMessage(
            f"{preflight_status} | {session_status_summary} | {self._session_snapshot.message}"
        )

        if self._advanced_dialog is not None and self._advanced_dialog.isVisible():
            self._advanced_dialog.set_state(self.cfg, self.config_path, self.warnings)
            self._advanced_dialog.reload_button.setEnabled(
                session_action_state.can_edit_configuration
            )

    def change_profile(self) -> None:
        if not self._ensure_configuration_change_allowed():
            return

        current_profile = self._active_profile_id()
        selected_profile = ProfileSelectorDialog.choose_profile(
            current_profile_id=current_profile,
            parent=self,
        )
        if not isinstance(selected_profile, str):
            return
        if selected_profile == current_profile:
            return

        self.cfg = set_active_profile(self.cfg, selected_profile)
        save_config(self.cfg, self.config_path)
        self.warnings = [f"Perfil actualizado desde UI a '{selected_profile}'."]
        self.session_controller.reload_config(self._session_cfg_provider)

    def reload_config(self) -> None:
        if not self._ensure_configuration_change_allowed():
            return

        cfg, warnings, config_path = load_config()
        self.cfg = cfg
        self.warnings = warnings
        self.config_path = config_path
        self.session_controller.reload_config(self._session_cfg_provider)

    def start_session(self) -> None:
        self.session_controller.start_session()

    def stop_session(self) -> None:
        self.session_controller.stop_session()

    def reset_session_error(self) -> None:
        self.session_controller.reset_error()

    def open_advanced_tools(self) -> None:
        if self._advanced_dialog is None:
            self._advanced_dialog = AdvancedToolsDialog(
                on_open_folder=self.open_config_folder,
                on_view_config=self.view_config,
                on_reload_config=self.reload_config,
                state_provider=self._advanced_state,
                parent=self,
            )

        self._advanced_dialog.set_state(self.cfg, self.config_path, self.warnings)
        self._advanced_dialog.reload_button.setEnabled(
            build_session_action_state(self._session_snapshot).can_edit_configuration
        )
        self._advanced_dialog.exec()

    def _advanced_state(self) -> tuple[dict[str, Any], Path, list[str]]:
        return self.cfg, self.config_path, self.warnings

    def open_config_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.config_path.parent)))

    def view_config(self) -> None:
        dialog = ConfigViewDialog(self._config_pretty_text(), parent=self)
        dialog.exec()

    def _config_pretty_text(self) -> str:
        return json.dumps(self.cfg, indent=2, ensure_ascii=False)

    def _active_profile_id(self) -> str | None:
        profile_cfg = self.cfg.get("profile")
        if not isinstance(profile_cfg, dict):
            return infer_profile_from_config(self.cfg)

        active_profile = profile_cfg.get("active")
        if isinstance(active_profile, str) and is_known_profile_id(active_profile):
            return active_profile

        return infer_profile_from_config(self.cfg)

    def _session_cfg_provider(self) -> dict[str, Any]:
        return self.cfg

    def _ensure_configuration_change_allowed(self) -> bool:
        action_state = build_session_action_state(self._session_snapshot)
        if action_state.can_edit_configuration:
            return True

        message = "Detenga la sesión antes de cambiar perfil o recargar configuración."
        self.operation_subtitle_label.setText(message)
        self.statusBar().showMessage(message)
        return False

    def _on_session_state_changed(self, _state_value: str) -> None:
        self.refresh_ui()

    def _on_session_snapshot_changed(self, snapshot: object) -> None:
        if isinstance(snapshot, SessionSnapshot):
            self._session_snapshot = snapshot
        self._preflight_report = self.session_controller.get_last_preflight_report()
        self.refresh_ui()

    def _on_session_error(self, message: str) -> None:
        self.operation_subtitle_label.setText(
            "Sesión en error. Revise el mensaje de sesión y use 'Reiniciar error'."
        )
        self.statusBar().showMessage(f"Error de sesión: {message}")

    def _on_session_message(self, message: str) -> None:
        if message.strip():
            self.statusBar().showMessage(message)

    def _on_preflight_report_changed(self, report: object) -> None:
        if isinstance(report, PreflightReport):
            self._preflight_report = report
        self.refresh_ui()

    def _refresh_preflight_findings_table(self, rows: list[PreflightDiagnosticRow]) -> None:
        self.preflight_findings_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self.preflight_findings_table.setItem(
                row_index, 0, QTableWidgetItem(str(row.severity))
            )
            self.preflight_findings_table.setItem(
                row_index, 1, QTableWidgetItem(str(row.code))
            )
            self.preflight_findings_table.setItem(
                row_index, 2, QTableWidgetItem(str(row.message))
            )
            self.preflight_findings_table.setItem(
                row_index, 3, QTableWidgetItem(str(row.details))
            )
