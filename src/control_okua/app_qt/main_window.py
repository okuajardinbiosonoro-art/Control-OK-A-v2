from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QBrush, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from control_okua.app_qt.advanced_tools_dialog import AdvancedToolsDialog
from control_okua.app_qt.control_plane_panel import ControlPlanePanel
from control_okua.app_qt.firmware_manager_dialog import FirmwareManagerDialog
from control_okua.app_qt.profile_selector_dialog import ProfileSelectorDialog
from control_okua.app_qt.widgets import ConfigViewDialog
from control_okua.app_qt.viewmodels import (
    build_nodes_tab_view_state,
    NodesTabViewState,
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
    format_node_last_note_velocity,
    format_node_last_seen,
    format_node_loss,
    format_node_pps,
    format_node_rssi,
    format_node_status,
    resolve_node_identity,
    sort_node_snapshots_by_id,
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
    build_node_runtime_tooltip,
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
from control_okua.services.control_transaction_service import ControlTransactionResult
from control_okua.services.session_controller import SessionController


class MainWindow(QMainWindow):
    _NODES_COLUMN_MIN_WIDTHS: tuple[int, ...] = (130, 120, 170, 125, 135, 95, 170)
    _NODES_COLUMN_WEIGHTS: tuple[int, ...] = (0, 0, 3, 2, 2, 1, 3)

    def __init__(
        self,
        cfg: dict[str, Any],
        config_path: Path,
        warnings: list[str] | None = None,
        session_controller: SessionController | None = None,
        on_apply_remote_settings: Callable[[bool, str], tuple[Any, str]] | None = None,
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
        self._firmware_manager_dialog: FirmwareManagerDialog | None = None
        self._details_dialog: QDialog | None = None
        self._node_box_expanded: dict[int, bool] = {}
        self._preflight_panel_visible = False
        self._remote_api_status: Any | None = None
        self._on_apply_remote_settings = on_apply_remote_settings
        self.session_controller = session_controller or SessionController(
            self._session_cfg_provider,
            parent=self,
        )
        self._session_snapshot: SessionSnapshot = self.session_controller.get_snapshot()
        self._preflight_report: PreflightReport | None = self.session_controller.get_last_preflight_report()
        self._connect_session_signals()
        self._serial_runtime_refresh_timer = QTimer(self)
        self._serial_runtime_refresh_timer.setInterval(1500)
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
        self._build_menu_bar()

        self.tabs = QTabWidget(self)
        self.operation_tab = self._build_operation_tab()
        self.nodes_tab = self._build_nodes_tab()
        self.diagnostics_tab = self._build_diagnostics_tab()
        self.control_plane_tab = self._build_control_plane_tab()
        self.tabs.addTab(self.operation_tab, "Sesión")
        self.tabs.addTab(self.nodes_tab, "Nodos en vivo")
        self.tabs.addTab(self.diagnostics_tab, "Estado técnico")
        self.tabs.addTab(self.control_plane_tab, "Control F3")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs.setCurrentIndex(0)
        root_layout.addWidget(self.tabs)
        self._create_session_details_dialog()

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("Archivo")
        self.reload_action = QAction("Recargar configuración", self)
        self.reload_action.triggered.connect(self.reload_config)
        file_menu.addAction(self.reload_action)
        file_menu.addSeparator()
        self.exit_action = QAction("Salir", self)
        self.exit_action.triggered.connect(self.close)
        file_menu.addAction(self.exit_action)

        view_menu = menu_bar.addMenu("Ver")
        self.view_state_action = QAction("Estado actual", self)
        self.view_state_action.triggered.connect(self.show_session_details_dialog)
        view_menu.addAction(self.view_state_action)

        self.view_diagnostics_action = QAction("Estado técnico", self)
        self.view_diagnostics_action.triggered.connect(self.show_diagnostics_tab)
        view_menu.addAction(self.view_diagnostics_action)

        self.view_control_plane_action = QAction("Control F3", self)
        self.view_control_plane_action.triggered.connect(self.show_control_plane_tab)
        view_menu.addAction(self.view_control_plane_action)

        self.toggle_preflight_action = QAction("Chequeos previos", self)
        self.toggle_preflight_action.setCheckable(True)
        self.toggle_preflight_action.toggled.connect(self._on_preflight_toggle_action)
        view_menu.addAction(self.toggle_preflight_action)

        tools_menu = menu_bar.addMenu("Herramientas")
        self.advanced_tools_action = QAction("Herramientas avanzadas", self)
        self.advanced_tools_action.triggered.connect(self.open_advanced_tools)
        tools_menu.addAction(self.advanced_tools_action)

        help_menu = menu_bar.addMenu("Ayuda")
        self.about_action = QAction("Acerca de", self)
        self.about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(self.about_action)

    def _create_session_details_dialog(self) -> None:
        self._details_dialog = QDialog(self)
        self._details_dialog.setWindowTitle("Estado actual")
        self._details_dialog.resize(900, 640)
        layout = QVBoxLayout(self._details_dialog)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self._build_session_details_tab())

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

        quick_actions_group = QGroupBox("Inicio rápido")
        quick_actions_layout = QHBoxLayout(quick_actions_group)

        self.change_profile_button = QPushButton("Cambiar perfil")
        self.change_profile_button.clicked.connect(self.change_profile)
        quick_actions_layout.addWidget(self.change_profile_button)
        quick_actions_layout.addStretch(1)
        layout.addWidget(quick_actions_group)

        session_actions_group = QGroupBox("Sesión")
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

        compact_group = QGroupBox("Estado de sesión")
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

        readiness_group = QGroupBox("Chequeos previos")
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

        serial_group = QGroupBox("Canal serial")
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

        udp_group = QGroupBox("Canal UDP")
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
                "MIDI y registro",
                [
                    ("midi", "MIDI"),
                    ("logging", "Registro"),
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
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title_label = QLabel("Nodos en vivo")
        title_font = title_label.font()
        title_font.setPointSize(title_font.pointSize() + 2)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        self.nodes_empty_state_group = QGroupBox("Estado general")
        self.nodes_empty_state_group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        empty_layout = QVBoxLayout(self.nodes_empty_state_group)
        empty_layout.setContentsMargins(10, 8, 10, 8)
        empty_layout.setSpacing(6)

        self.nodes_state_label = QLabel("La vista de nodos está disponible para sesiones UDP.")
        self._set_compact_wordwrap_label(self.nodes_state_label)
        self.nodes_state_label.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self.nodes_state_label)

        self.nodes_hint_label = QLabel("Inicia una sesión UDP para ver nodos en vivo.")
        self._set_compact_wordwrap_label(self.nodes_hint_label)
        self.nodes_hint_label.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self.nodes_hint_label)

        self.nodes_summary_label = QLabel("Resumen de nodos: no disponible.")
        self._set_compact_wordwrap_label(self.nodes_summary_label)
        self.nodes_summary_label.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self.nodes_summary_label)
        layout.addWidget(self.nodes_empty_state_group, 0)

        self.nodes_tree = QTreeWidget(self)
        self.nodes_tree.setColumnCount(7)
        self.nodes_tree.setHeaderLabels(
            [
                "Nodo",
                "Estado",
                "Último visto",
                "PPS",
                "Pérdida",
                "RSSI",
                "Última nota/vel",
            ]
        )
        self.nodes_tree.setAlternatingRowColors(True)
        self.nodes_tree.setRootIsDecorated(True)
        self.nodes_tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.nodes_tree.setSelectionMode(QAbstractItemView.NoSelection)
        self.nodes_tree.itemExpanded.connect(self._on_node_box_expanded)
        self.nodes_tree.itemCollapsed.connect(self._on_node_box_collapsed)
        self._configure_nodes_tree_columns()
        layout.addWidget(self.nodes_tree, 1)

        return tab

    def _build_diagnostics_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        summary_group = QGroupBox("Resumen de sistema")
        summary_layout = QFormLayout(summary_group)

        fields = [
            ("profile", "Perfil"),
            ("config_path", "Archivo de config"),
            ("mode", "Modo"),
            ("transport", "Transporte"),
            ("midi", "MIDI"),
            ("logging", "Registro"),
            ("general", "Estado"),
        ]
        for key, field_name in fields:
            label = QLabel("-")
            label.setWordWrap(True)
            summary_layout.addRow(field_name, label)
            self._diagnostic_summary_labels[key] = label

        layout.addWidget(summary_group)
        self.preflight_toggle_button = QPushButton("Ver chequeos previos")
        self.preflight_toggle_button.setCheckable(True)
        self.preflight_toggle_button.toggled.connect(self._on_preflight_toggle_button)
        layout.addWidget(self.preflight_toggle_button)

        self.preflight_group = QGroupBox("Chequeos previos")
        preflight_layout = QVBoxLayout(self.preflight_group)

        preflight_summary_form = QFormLayout()
        self.preflight_diag_status_label = QLabel("-")
        self.preflight_diag_status_label.setWordWrap(True)
        preflight_summary_form.addRow("Resultado", self.preflight_diag_status_label)

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
        layout.addWidget(self.preflight_group)
        self.preflight_group.setVisible(False)

        self.serial_runtime_group = QGroupBox("Detalle serial")
        serial_runtime_layout = QVBoxLayout(self.serial_runtime_group)
        self.serial_runtime_table = QTableWidget(0, 2, self)
        self.serial_runtime_table.setHorizontalHeaderLabels(["Campo", "Valor"])
        self.serial_runtime_table.horizontalHeader().setStretchLastSection(True)
        self.serial_runtime_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.serial_runtime_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.serial_runtime_table.verticalHeader().setVisible(False)
        serial_runtime_layout.addWidget(self.serial_runtime_table)
        layout.addWidget(self.serial_runtime_group)

        self.udp_runtime_group = QGroupBox("Detalle UDP")
        udp_runtime_layout = QVBoxLayout(self.udp_runtime_group)
        self.udp_runtime_table = QTableWidget(0, 2, self)
        self.udp_runtime_table.setHorizontalHeaderLabels(["Campo", "Valor"])
        self.udp_runtime_table.horizontalHeader().setStretchLastSection(True)
        self.udp_runtime_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.udp_runtime_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.udp_runtime_table.verticalHeader().setVisible(False)
        udp_runtime_layout.addWidget(self.udp_runtime_table)
        layout.addWidget(self.udp_runtime_group)

        warnings_group = QGroupBox("Alertas de configuración")
        warnings_layout = QVBoxLayout(warnings_group)
        self.warnings_view = QTextEdit(self)
        self.warnings_view.setReadOnly(True)
        warnings_layout.addWidget(self.warnings_view)
        layout.addWidget(warnings_group, 1)

        return tab

    def _build_control_plane_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        self.control_plane_panel = ControlPlanePanel(
            send_ping=self._send_control_ping_from_ui,
            send_request_stat_now=self._send_control_request_stat_now_from_ui,
            send_reboot_soft=self._send_control_reboot_soft_from_ui,
            send_set_stat_rate=self._send_control_set_stat_rate_from_ui,
            send_set_throttle=self._send_control_set_throttle_from_ui,
            available_node_ids_provider=self._available_control_node_ids_from_runtime,
            node_snapshot_provider=self._control_node_snapshot_from_runtime,
            reboot_verification_reporter=self._record_control_reboot_verification_from_ui,
            default_node_id=1,
            parent=self,
        )
        layout.addWidget(self.control_plane_panel, 1)
        return tab

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._reflow_details_cards()
        self._adjust_nodes_tree_columns()

    def _reflow_details_cards(self, *, force: bool = False) -> None:
        layout = self._details_cards_layout
        if layout is None:
            return

        viewport_width = 0
        if self._details_scroll_area is not None:
            viewport_width = self._details_scroll_area.viewport().width()
        if viewport_width <= 0 and hasattr(self, "tabs"):
            viewport_width = self.tabs.width()
        if viewport_width <= 0:
            viewport_width = self.width()
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
                "Aplicación cargada con advertencias. Revise Estado técnico. "
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
        self.reload_action.setEnabled(session_action_state.can_edit_configuration)
        self.advanced_tools_action.setEnabled(True)

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
        self._update_preflight_toggle_caption(len(preflight_rows))
        runtime_snapshot = self.session_controller.get_backend_runtime_snapshot()
        self._refresh_runtime_views(runtime_snapshot, force=True)
        if self._is_nodes_view_visible() or self._session_snapshot.state is not SessionState.RUNNING:
            self._refresh_nodes_views()

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
                on_apply_remote_settings=self.apply_remote_settings,
                on_open_firmware_manager=self.open_firmware_manager,
                state_provider=self._advanced_state,
                remote_status_provider=self._remote_api_status_provider,
                parent=self,
            )

        self._advanced_dialog.set_state(self.cfg, self.config_path, self.warnings)
        self._advanced_dialog.reload_button.setEnabled(
            build_session_action_state(self._session_snapshot).can_edit_configuration
        )
        self._advanced_dialog.remote_apply_button.setEnabled(
            build_session_action_state(self._session_snapshot).can_edit_configuration
        )
        self._advanced_dialog.exec()

    def open_firmware_manager(self) -> None:
        if self._firmware_manager_dialog is None:
            self._firmware_manager_dialog = FirmwareManagerDialog(
                session_controller=self.session_controller,
                parent=self,
            )

        self._firmware_manager_dialog.refresh_catalog()
        self._firmware_manager_dialog.show()
        self._firmware_manager_dialog.raise_()
        self._firmware_manager_dialog.activateWindow()

    def _advanced_state(self) -> tuple[dict[str, Any], Path, list[str]]:
        return self.cfg, self.config_path, self.warnings

    def _remote_api_status_provider(self) -> Any | None:
        return self._remote_api_status

    def set_remote_api_status(self, status: Any | None) -> None:
        self._remote_api_status = status
        if self._advanced_dialog is not None and self._advanced_dialog.isVisible():
            self._advanced_dialog.set_state(self.cfg, self.config_path, self.warnings)

    def apply_remote_settings(self, enabled: bool, exposure_mode: str) -> tuple[Any, str]:
        if not self._ensure_configuration_change_allowed():
            raise RuntimeError(
                "Detenga la sesión antes de cambiar la exposición del servicio remoto."
            )
        if self._on_apply_remote_settings is None:
            raise RuntimeError("La aplicación no expuso un handler para reconfigurar el servicio remoto.")

        status, message = self._on_apply_remote_settings(enabled, exposure_mode)
        self.set_remote_api_status(status)
        return status, message

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

    def _send_control_ping_from_ui(
        self,
        node_id: int,
        ack_timeout_ms: int,
        max_retries: int,
    ) -> ControlTransactionResult:
        return self.session_controller.send_control_ping(
            node_id=node_id,
            ack_timeout_ms=ack_timeout_ms,
            max_retries=max_retries,
            source="ui_manual",
        )

    def _send_control_request_stat_now_from_ui(
        self,
        node_id: int,
        ack_timeout_ms: int,
        max_retries: int,
    ) -> ControlTransactionResult:
        return self.session_controller.send_control_request_stat_now(
            node_id=node_id,
            ack_timeout_ms=ack_timeout_ms,
            max_retries=max_retries,
            source="ui_manual",
        )

    def _send_control_reboot_soft_from_ui(
        self,
        node_id: int,
        ack_timeout_ms: int,
        max_retries: int,
    ) -> ControlTransactionResult:
        return self.session_controller.send_control_reboot_soft(
            node_id=node_id,
            ack_timeout_ms=ack_timeout_ms,
            max_retries=max_retries,
            source="ui_manual",
        )

    def _send_control_set_stat_rate_from_ui(
        self,
        node_id: int,
        stat_rate_ms: int,
        ack_timeout_ms: int,
        max_retries: int,
    ) -> ControlTransactionResult:
        return self.session_controller.send_control_set_stat_rate(
            node_id=node_id,
            stat_rate_ms=stat_rate_ms,
            ack_timeout_ms=ack_timeout_ms,
            max_retries=max_retries,
            source="ui_manual",
        )

    def _send_control_set_throttle_from_ui(
        self,
        node_id: int,
        throttle_percent: int,
        ack_timeout_ms: int,
        max_retries: int,
    ) -> ControlTransactionResult:
        return self.session_controller.send_control_set_throttle(
            node_id=node_id,
            throttle_percent=throttle_percent,
            ack_timeout_ms=ack_timeout_ms,
            max_retries=max_retries,
            source="ui_manual",
        )

    def _available_control_node_ids_from_runtime(self) -> list[int]:
        snapshots = self.session_controller.get_control_plane_node_snapshots(now=time.monotonic())
        node_ids: list[int] = []
        seen: set[int] = set()
        for snapshot in snapshots:
            raw = getattr(snapshot, "node_id", None)
            try:
                node_id = int(raw)
            except (TypeError, ValueError):
                continue
            if node_id <= 0:
                continue
            if node_id in seen:
                continue
            resolution_status = str(getattr(snapshot, "resolution_status", "")).lower()
            has_runtime_presence = getattr(snapshot, "last_seen_pc_ts", None) is not None
            if resolution_status.endswith("unresolved") and not has_runtime_presence:
                continue
            seen.add(node_id)
            node_ids.append(node_id)
        node_ids.sort()
        return node_ids

    def _control_node_snapshot_from_runtime(self, node_id: int) -> object | None:
        try:
            resolved_node_id = int(node_id)
        except (TypeError, ValueError):
            return None
        if resolved_node_id <= 0:
            return None
        return self.session_controller.get_control_plane_node_snapshot(
            node_id=resolved_node_id,
            now=time.monotonic(),
        )

    def _record_control_reboot_verification_from_ui(
        self,
        node_id: int,
        status: str,
        summary: str,
    ) -> None:
        self.session_controller.record_control_plane_reboot_verification(
            node_id=node_id,
            status=status,
            summary=summary,
        )

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
        self._refresh_runtime_views(runtime_snapshot)
        if self._is_nodes_view_visible():
            self._refresh_nodes_views()

    def _on_tab_changed(self, _index: int) -> None:
        if self._is_control_plane_view_visible():
            self.control_plane_panel.on_section_activated()
            return
        if self._is_nodes_view_visible():
            self._refresh_nodes_views()
            return
        if self._is_runtime_view_visible():
            runtime_snapshot = self.session_controller.get_backend_runtime_snapshot()
            self._refresh_runtime_views(runtime_snapshot, force=True)

    def show_session_details_dialog(self) -> None:
        if self._details_dialog is None:
            self._create_session_details_dialog()
        if self._details_dialog is None:
            return
        self._details_dialog.show()
        self._details_dialog.raise_()
        self._details_dialog.activateWindow()
        self._reflow_details_cards(force=True)

    def show_diagnostics_tab(self) -> None:
        self.tabs.setCurrentWidget(self.diagnostics_tab)

    def show_control_plane_tab(self) -> None:
        self.tabs.setCurrentWidget(self.control_plane_tab)
        self.control_plane_panel.on_section_activated()

    def show_about_dialog(self) -> None:
        version = self.cfg.get("version")
        version_text = str(version) if version is not None else "No disponible"
        QMessageBox.about(
            self,
            "Acerca de",
            (
                "Control OKÚA v2\n"
                f"Versión de configuración: {version_text}\n\n"
                "Aplicación de operación para monitoreo de nodos OKÚA,\n"
                "control de sesión serial/UDP y ruteo MIDI por caja."
            ),
        )

    def _on_preflight_toggle_button(self, checked: bool) -> None:
        self._set_preflight_panel_visible(checked)

    def _on_preflight_toggle_action(self, checked: bool) -> None:
        if checked:
            self.show_diagnostics_tab()
        self._set_preflight_panel_visible(checked)

    def _set_preflight_panel_visible(self, visible: bool) -> None:
        self._preflight_panel_visible = bool(visible)
        self.preflight_group.setVisible(self._preflight_panel_visible)
        if self.preflight_toggle_button.isChecked() != self._preflight_panel_visible:
            self.preflight_toggle_button.setChecked(self._preflight_panel_visible)
        if self.toggle_preflight_action.isChecked() != self._preflight_panel_visible:
            self.toggle_preflight_action.setChecked(self._preflight_panel_visible)

    def _update_preflight_toggle_caption(self, findings_count: int) -> None:
        if findings_count > 0:
            base = f"Chequeos previos ({findings_count})"
        else:
            base = "Chequeos previos"
        if self._preflight_panel_visible:
            button_text = f"Ocultar {base.lower()}"
        else:
            button_text = f"Ver {base.lower()}"
        self.preflight_toggle_button.setText(button_text)
        self.toggle_preflight_action.setText(base)

    def _is_runtime_view_visible(self) -> bool:
        current_widget = self.tabs.currentWidget()
        return current_widget in {self.operation_tab, self.diagnostics_tab}

    def _is_nodes_view_visible(self) -> bool:
        return self.tabs.currentWidget() is self.nodes_tab

    def _is_control_plane_view_visible(self) -> bool:
        return self.tabs.currentWidget() is self.control_plane_tab

    def _refresh_runtime_views(self, runtime_snapshot: object | None, *, force: bool = False) -> None:
        if not force and not self._is_runtime_view_visible():
            return

        mode = self._session_snapshot.mode
        backend = self._session_snapshot.backend
        is_serial_backend = backend is not None and backend.value == "serial"
        is_udp_runtime = mode == "udp" or (backend is not None and backend.value in {"udp", "lab"})

        self.serial_runtime_group.setVisible(is_serial_backend)
        self.udp_runtime_group.setVisible(is_udp_runtime)

        if is_serial_backend:
            self._refresh_serial_runtime_views(runtime_snapshot)
        if is_udp_runtime:
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

    def _refresh_nodes_views(self) -> None:
        now_monotonic = time.monotonic()
        raw_snapshots = self.session_controller.get_node_snapshots(now=now_monotonic)
        snapshots = sort_node_snapshots_by_id(raw_snapshots)
        summary = self.session_controller.get_node_registry_summary(now=now_monotonic)
        view_state = build_nodes_tab_view_state(
            self._session_snapshot,
            summary,
            shown_nodes=len(snapshots),
        )

        self._refresh_nodes_tree(snapshots, now_monotonic=now_monotonic)
        self._apply_nodes_view_state(view_state)

    def _refresh_nodes_tree(self, snapshots: list[object], *, now_monotonic: float) -> None:
        box_expanded_state = self._capture_node_box_expanded_state()
        self.nodes_tree.clear()

        grouped: dict[int, list[object]] = {}
        max_box = 0
        for snapshot in snapshots:
            identity = resolve_node_identity(getattr(snapshot, "node_id", None))
            box_index = identity.box_index
            if box_index is None:
                continue
            grouped.setdefault(box_index, []).append(snapshot)
            max_box = max(max_box, box_index)

        total_boxes = max(5, max_box)
        for box_index in range(1, total_boxes + 1):
            children = grouped.get(box_index, [])
            parent_text = f"Caja {box_index} ({len(children)})"
            parent_item = QTreeWidgetItem([parent_text])
            parent_item.setData(0, Qt.UserRole, box_index)
            parent_item.setFirstColumnSpanned(True)
            self.nodes_tree.addTopLevelItem(parent_item)

            for snapshot in children:
                identity = resolve_node_identity(getattr(snapshot, "node_id", None))
                child_item = QTreeWidgetItem(
                    [
                        identity.node_label,
                        format_node_status(snapshot),
                        format_node_last_seen(snapshot, now_monotonic=now_monotonic),
                        format_node_pps(snapshot),
                        format_node_loss(snapshot),
                        format_node_rssi(snapshot),
                        format_node_last_note_velocity(snapshot),
                    ]
                )
                node_id = getattr(snapshot, "node_id", None)
                if node_id is not None:
                    runtime_tooltip = build_node_runtime_tooltip(
                        snapshot,
                        now_monotonic=now_monotonic,
                    )
                    child_item.setToolTip(
                        0,
                        (
                            f"node_id={node_id} | {identity.box_label} | "
                            f"bus MIDI={identity.midi_bus}\n{runtime_tooltip}"
                        ),
                    )
                else:
                    runtime_tooltip = build_node_runtime_tooltip(
                        snapshot,
                        now_monotonic=now_monotonic,
                    )
                child_item.setToolTip(1, runtime_tooltip)
                status_key = str(getattr(getattr(snapshot, "status", None), "value", "")).lower()
                if status_key == "online":
                    child_item.setForeground(1, QBrush(QColor("#2F9E44")))
                elif status_key == "calibrating":
                    child_item.setForeground(1, QBrush(QColor("#1C7ED6")))
                elif status_key == "degraded":
                    child_item.setForeground(1, QBrush(QColor("#E67700")))
                else:
                    child_item.setForeground(1, QBrush(QColor("#C92A2A")))
                parent_item.addChild(child_item)

            previous_expanded = box_expanded_state.get(box_index)
            if previous_expanded is None:
                parent_item.setExpanded(len(children) > 0)
            else:
                parent_item.setExpanded(previous_expanded)

        self._adjust_nodes_tree_columns()

    def _capture_node_box_expanded_state(self) -> dict[int, bool]:
        state: dict[int, bool] = self._node_box_expanded.copy()
        for index in range(self.nodes_tree.topLevelItemCount()):
            item = self.nodes_tree.topLevelItem(index)
            raw_box_index = item.data(0, Qt.UserRole)
            if isinstance(raw_box_index, int):
                state[raw_box_index] = item.isExpanded()
        self._node_box_expanded = state.copy()
        return state

    def _on_node_box_expanded(self, item: QTreeWidgetItem) -> None:
        raw_box_index = item.data(0, Qt.UserRole)
        if isinstance(raw_box_index, int):
            self._node_box_expanded[raw_box_index] = True

    def _on_node_box_collapsed(self, item: QTreeWidgetItem) -> None:
        raw_box_index = item.data(0, Qt.UserRole)
        if isinstance(raw_box_index, int):
            self._node_box_expanded[raw_box_index] = False

    @staticmethod
    def _set_compact_wordwrap_label(label: QLabel) -> None:
        label.setWordWrap(True)
        label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

    def _apply_nodes_view_state(self, view_state: NodesTabViewState) -> None:
        self.nodes_state_label.setText(view_state.title)
        self.nodes_hint_label.setText(view_state.hint)
        self.nodes_summary_label.setText(view_state.summary)
        show_table = bool(view_state.show_table)
        self.nodes_tree.setVisible(show_table)
        self.nodes_empty_state_group.setVisible(not show_table)
        if show_table:
            self._adjust_nodes_tree_columns()

    def _configure_nodes_tree_columns(self) -> None:
        header = self.nodes_tree.header()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(72)
        for col in range(self.nodes_tree.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.Interactive)
            min_width = self._NODES_COLUMN_MIN_WIDTHS[col]
            self.nodes_tree.setColumnWidth(col, min_width)

    def _adjust_nodes_tree_columns(self) -> None:
        if not hasattr(self, "nodes_tree"):
            return
        if self.nodes_tree.columnCount() <= 0:
            return
        available_width = self.nodes_tree.viewport().width()
        if available_width <= 0:
            return

        column_count = self.nodes_tree.columnCount()
        min_widths = list(self._NODES_COLUMN_MIN_WIDTHS[:column_count])
        weights = list(self._NODES_COLUMN_WEIGHTS[:column_count])

        # Respect content width for key identity/status columns before distributing.
        self.nodes_tree.resizeColumnToContents(0)
        self.nodes_tree.resizeColumnToContents(1)
        min_widths[0] = max(min_widths[0], self.nodes_tree.columnWidth(0))
        min_widths[1] = max(min_widths[1], self.nodes_tree.columnWidth(1))

        target_widths = list(min_widths)
        min_total = sum(min_widths)
        if available_width > min_total:
            extra = available_width - min_total
            weighted_columns = [idx for idx, weight in enumerate(weights) if weight > 0]
            total_weight = sum(weights[idx] for idx in weighted_columns)
            if total_weight > 0:
                for idx in weighted_columns:
                    target_widths[idx] += (extra * weights[idx]) // total_weight
            remainder = max(0, available_width - sum(target_widths))
            if remainder > 0:
                target_widths[-1] += remainder

        for col, width in enumerate(target_widths):
            self.nodes_tree.setColumnWidth(col, int(width))

    def closeEvent(self, event) -> None:  # type: ignore[override]
        super().closeEvent(event)
