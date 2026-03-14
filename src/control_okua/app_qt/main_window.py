from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, QUrl
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
    QScrollArea,
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
    SerialRuntimeDiagnosticRow,
    UdpRuntimeDiagnosticRow,
    build_general_status_summary,
    build_diagnostic_serial_rows,
    build_diagnostic_udp_rows,
    build_logging_summary,
    build_midi_summary,
    build_mode_summary,
    build_operation_serial_block,
    build_operation_udp_block,
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

        self._operation_compact_labels: dict[str, QLabel] = {}
        self._details_summary_labels: dict[str, QLabel] = {}
        self._operation_readiness_labels: dict[str, QLabel] = {}
        self._operation_serial_labels: dict[str, QLabel] = {}
        self._operation_udp_labels: dict[str, QLabel] = {}
        self._diagnostic_summary_labels: dict[str, QLabel] = {}
        self._details_cards: list[QGroupBox] = []
        self._details_cards_layout: QGridLayout | None = None
        self._details_scroll_area: QScrollArea | None = None
        self._details_columns = 0
        self._advanced_dialog: AdvancedToolsDialog | None = None
        self.session_controller = session_controller or SessionController(
            self._session_cfg_provider,
            parent=self,
        )
        self._session_snapshot: SessionSnapshot = self.session_controller.get_snapshot()
        self._preflight_report: PreflightReport | None = self.session_controller.get_last_preflight_report()
        self._connect_session_signals()
        self._serial_runtime_refresh_timer = QTimer(self)
        self._serial_runtime_refresh_timer.setInterval(1000)
        self._serial_runtime_refresh_timer.timeout.connect(
            self._on_runtime_refresh_tick
        )
        self._serial_runtime_refresh_timer.start()

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
        self.tabs.addTab(self._build_session_details_tab(), "Estado actual")
        self.tabs.addTab(self._build_nodes_tab(), "Nodos")
        self.tabs.addTab(self._build_diagnostics_tab(), "Diagnóstico")
        self.tabs.setCurrentIndex(0)
        root_layout.addWidget(self.tabs)

    def _build_operation_tab(self) -> QWidget:
        tab = QWidget(self)
        tab_layout = QVBoxLayout(tab)
        operation_scroll = QScrollArea(self)
        operation_scroll.setWidgetResizable(True)

        operation_content = QWidget(self)
        layout = QVBoxLayout(operation_content)

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

        compact_group = QGroupBox("Resumen operativo")
        compact_layout = QFormLayout(compact_group)
        compact_fields = [
            ("profile", "Perfil activo"),
            ("profile_mode", "Modo asociado"),
            ("session_state", "Estado de sesión"),
            ("session_backend", "Backend esperado"),
            ("session_message", "Mensaje de sesión"),
            ("general", "Estado general"),
        ]
        for key, field_name in compact_fields:
            label = QLabel("-")
            label.setWordWrap(True)
            compact_layout.addRow(field_name, label)
            self._operation_compact_labels[key] = label
        layout.addWidget(compact_group)

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

        serial_group = QGroupBox("Actividad serial")
        serial_layout = QFormLayout(serial_group)
        serial_fields = [
            ("status", "Estado"),
            ("summary", "Resumen"),
            ("port", "Puerto"),
            ("messages", "Mensajes"),
            ("error", "Último error"),
            ("recent", "Actividad reciente"),
        ]
        for key, field_name in serial_fields:
            label = QLabel("-")
            label.setWordWrap(True)
            serial_layout.addRow(field_name, label)
            self._operation_serial_labels[key] = label
        layout.addWidget(serial_group)

        udp_group = QGroupBox("Actividad UDP")
        udp_layout = QFormLayout(udp_group)
        udp_fields = [
            ("status", "Estado"),
            ("summary", "Resumen"),
            ("bind", "Bind"),
            ("ports", "Puertos"),
            ("evt", "EVT"),
            ("stat", "STAT"),
            ("error", "Último error"),
            ("recent", "Actividad reciente"),
        ]
        for key, field_name in udp_fields:
            label = QLabel("-")
            label.setWordWrap(True)
            udp_layout.addRow(field_name, label)
            self._operation_udp_labels[key] = label
        layout.addWidget(udp_group)
        layout.addStretch(1)

        operation_scroll.setWidget(operation_content)
        tab_layout.addWidget(operation_scroll)
        return tab

    def _build_session_details_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        title_label = QLabel("Detalles de sesión")
        title_font = title_label.font()
        title_font.setPointSize(title_font.pointSize() + 2)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        hint_label = QLabel(
            "Resumen técnico completo del estado actual. "
            "Esta vista se adapta automáticamente y mantiene scroll interno."
        )
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)

        self._details_scroll_area = QScrollArea(self)
        self._details_scroll_area.setWidgetResizable(True)
        details_content = QWidget(self)
        self._details_cards_layout = QGridLayout(details_content)
        self._details_cards_layout.setContentsMargins(0, 0, 0, 0)
        self._details_cards_layout.setHorizontalSpacing(12)
        self._details_cards_layout.setVerticalSpacing(12)

        card_specs = [
            (
                "Sesión",
                [
                    ("profile", "Perfil activo"),
                    ("profile_mode", "Modo asociado"),
                    ("session_state", "Estado de sesión"),
                    ("session_message", "Mensaje de sesión"),
                ],
            ),
            (
                "Backend",
                [
                    ("session_backend", "Backend esperado"),
                    ("transport", "Transporte"),
                    ("mode", "Modo técnico"),
                ],
            ),
            (
                "Capacidades",
                [
                    ("session_capabilities", "Capacidades"),
                    ("operation", "Uso esperado"),
                ],
            ),
            (
                "MIDI y Logging",
                [
                    ("midi", "MIDI"),
                    ("logging", "Logging"),
                ],
            ),
            (
                "Estado general",
                [
                    ("general", "Estado general"),
                ],
            ),
        ]

        self._details_cards = []
        for title, fields in card_specs:
            card = QGroupBox(title)
            card_layout = QFormLayout(card)
            for key, field_name in fields:
                label = QLabel("-")
                label.setWordWrap(True)
                card_layout.addRow(field_name, label)
                self._details_summary_labels[key] = label
            self._details_cards.append(card)

        self._details_scroll_area.setWidget(details_content)
        layout.addWidget(self._details_scroll_area, 1)
        self._reflow_details_cards(force=True)
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

        serial_runtime_group = QGroupBox("Runtime serial")
        serial_runtime_layout = QVBoxLayout(serial_runtime_group)
        self.serial_runtime_table = QTableWidget(0, 2, self)
        self.serial_runtime_table.setHorizontalHeaderLabels(["Campo", "Valor"])
        self.serial_runtime_table.horizontalHeader().setStretchLastSection(True)
        self.serial_runtime_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.serial_runtime_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.serial_runtime_table.verticalHeader().setVisible(False)
        serial_runtime_layout.addWidget(self.serial_runtime_table)
        layout.addWidget(serial_runtime_group)

        udp_runtime_group = QGroupBox("Runtime UDP")
        udp_runtime_layout = QVBoxLayout(udp_runtime_group)
        self.udp_runtime_table = QTableWidget(0, 2, self)
        self.udp_runtime_table.setHorizontalHeaderLabels(["Campo", "Valor"])
        self.udp_runtime_table.horizontalHeader().setStretchLastSection(True)
        self.udp_runtime_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.udp_runtime_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.udp_runtime_table.verticalHeader().setVisible(False)
        udp_runtime_layout.addWidget(self.udp_runtime_table)
        layout.addWidget(udp_runtime_group)

        warnings_group = QGroupBox("Advertencias de configuración")
        warnings_layout = QVBoxLayout(warnings_group)
        self.warnings_view = QTextEdit(self)
        self.warnings_view.setReadOnly(True)
        warnings_layout.addWidget(self.warnings_view)
        layout.addWidget(warnings_group, 1)

        return tab

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._reflow_details_cards()

    def _reflow_details_cards(self, *, force: bool = False) -> None:
        layout = self._details_cards_layout
        if layout is None:
            return

        tabs_width = self.tabs.width() if hasattr(self, "tabs") else self.width()
        viewport_width = tabs_width if tabs_width > 0 else self.width()
        columns = 2 if viewport_width >= 900 else 1
        if not force and columns == self._details_columns:
            return

        while layout.count() > 0:
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                layout.removeWidget(widget)

        for index, card in enumerate(self._details_cards):
            row = index // columns
            col = index % columns
            layout.addWidget(card, row, col)

        for col in range(columns):
            layout.setColumnStretch(col, 1)
        self._details_columns = columns

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

        summary_values = {
            "profile": profile_summary,
            "profile_mode": profile_mode_summary,
            "session_backend": session_backend_summary,
            "session_state": session_status_summary,
            "session_message": session_message_summary,
            "session_capabilities": session_capabilities_summary,
            "operation": operation_summary,
            "mode": mode_summary,
            "general": general_summary,
            "transport": transport_summary,
            "midi": midi_summary,
            "logging": logging_summary,
        }
        self._apply_summary_values(summary_values)
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
        runtime_snapshot = self.session_controller.get_backend_runtime_snapshot()
        self._refresh_serial_runtime_views(runtime_snapshot)
        self._refresh_udp_runtime_views(runtime_snapshot)

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

    def _apply_summary_values(self, values: dict[str, str]) -> None:
        for key, text in values.items():
            self._set_summary_label_value(key, text)

    def _set_summary_label_value(self, key: str, text: str) -> None:
        compact_label = self._operation_compact_labels.get(key)
        if compact_label is not None:
            compact_label.setText(text)
        details_label = self._details_summary_labels.get(key)
        if details_label is not None:
            details_label.setText(text)

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

    def _on_runtime_refresh_tick(self) -> None:
        if self._session_snapshot.state is not SessionState.RUNNING:
            return

        runtime_snapshot = self.session_controller.get_backend_runtime_snapshot()
        backend = self._session_snapshot.backend
        is_serial_backend = backend is not None and backend.value == "serial"
        is_udp_mode = self._session_snapshot.mode == "udp"

        if is_serial_backend:
            self._refresh_serial_runtime_views(runtime_snapshot)
        if is_udp_mode:
            self._refresh_udp_runtime_views(runtime_snapshot)

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

    def _refresh_serial_runtime_views(self, runtime_snapshot: object | None = None) -> None:
        if runtime_snapshot is None:
            runtime_snapshot = self.session_controller.get_backend_runtime_snapshot()
        operation_serial = build_operation_serial_block(
            runtime_snapshot,
            self._session_snapshot,
        )
        diagnostic_serial_rows = build_diagnostic_serial_rows(
            runtime_snapshot,
            self._session_snapshot,
        )

        self._operation_serial_labels["status"].setText(operation_serial.status_label)
        self._operation_serial_labels["summary"].setText(operation_serial.summary)
        self._operation_serial_labels["port"].setText(operation_serial.port)
        self._operation_serial_labels["messages"].setText(
            operation_serial.messages_processed
        )
        self._operation_serial_labels["error"].setText(operation_serial.last_error)
        self._operation_serial_labels["recent"].setText(operation_serial.recent_activity)
        self._refresh_serial_runtime_table(diagnostic_serial_rows)

    def _refresh_udp_runtime_views(self, runtime_snapshot: object | None = None) -> None:
        if runtime_snapshot is None:
            runtime_snapshot = self.session_controller.get_backend_runtime_snapshot()
        operation_udp = build_operation_udp_block(
            runtime_snapshot,
            self._session_snapshot,
        )
        diagnostic_udp_rows = build_diagnostic_udp_rows(
            runtime_snapshot,
            self._session_snapshot,
        )

        self._operation_udp_labels["status"].setText(operation_udp.status_label)
        self._operation_udp_labels["summary"].setText(operation_udp.summary)
        self._operation_udp_labels["bind"].setText(operation_udp.bind)
        self._operation_udp_labels["ports"].setText(operation_udp.ports)
        self._operation_udp_labels["evt"].setText(operation_udp.evt_packets)
        self._operation_udp_labels["stat"].setText(operation_udp.stat_packets)
        self._operation_udp_labels["error"].setText(operation_udp.last_error)
        self._operation_udp_labels["recent"].setText(operation_udp.recent_activity)
        self._refresh_udp_runtime_table(diagnostic_udp_rows)

    def _refresh_serial_runtime_table(
        self,
        rows: list[SerialRuntimeDiagnosticRow],
    ) -> None:
        self.serial_runtime_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self.serial_runtime_table.setItem(
                row_index,
                0,
                QTableWidgetItem(str(row.field)),
            )
            self.serial_runtime_table.setItem(
                row_index,
                1,
                QTableWidgetItem(str(row.value)),
            )

    def _refresh_udp_runtime_table(
        self,
        rows: list[UdpRuntimeDiagnosticRow],
    ) -> None:
        self.udp_runtime_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self.udp_runtime_table.setItem(
                row_index,
                0,
                QTableWidgetItem(str(row.field)),
            )
            self.udp_runtime_table.setItem(
                row_index,
                1,
                QTableWidgetItem(str(row.value)),
            )
