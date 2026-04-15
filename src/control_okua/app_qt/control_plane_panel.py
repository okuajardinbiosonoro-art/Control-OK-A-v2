from __future__ import annotations

from datetime import datetime
import time
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from control_okua.app_qt.viewmodels.control_plane_vm import (
    ControlPlaneNodeOption,
    build_control_plane_node_options,
    format_control_transaction_event_lines,
    format_control_transaction_result,
    resolve_control_command_policy,
)
from control_okua.app_qt.viewmodels.control_plane_snapshot_view import (
    ControlPlaneSnapshotView,
    build_control_plane_snapshot_view,
)
from control_okua.services.control_transaction_service import ControlTransactionResult


@dataclass(frozen=True)
class _PanelRunOutcome:
    result: ControlTransactionResult
    post_lines: tuple[str, ...] = tuple()


@dataclass(frozen=True)
class _RebootProbeOutcome:
    feedback_line: str
    attempt_count: int
    observed_interruption: bool
    observed_recovery: bool
    observed_uptime_reset: bool
    observed_reset_reason_change: bool
    observed_boot_marker_change: bool
    baseline_uptime_s: int | None
    final_uptime_s: int | None
    baseline_reset_reason: int | None
    final_reset_reason: int | None
    baseline_boot_marker: int | None
    final_boot_marker: int | None


_SET_STAT_RATE_PRESETS_MS: tuple[int, ...] = (1000, 2000, 5000)
_SET_THROTTLE_PRESETS_PERCENT: tuple[int, ...] = (25, 50, 100)


class _TransactionWorker(QObject):
    finished = Signal(object, object)
    progress = Signal(str)

    def __init__(self, execute: Callable[[Callable[[str], None]], _PanelRunOutcome]) -> None:
        super().__init__()
        self._execute = execute

    def _emit_progress(self, line: str) -> None:
        text = str(line).strip()
        if text:
            self.progress.emit(text)

    @Slot()
    def run(self) -> None:
        try:
            result = self._execute(self._emit_progress)
        except Exception as exc:
            self.finished.emit(None, str(exc))
            return
        self.finished.emit(result, None)


class ControlPlanePanel(QWidget):
    def __init__(
        self,
        *,
        send_ping: Callable[[int, int, int], ControlTransactionResult],
        send_request_stat_now: Callable[[int, int, int], ControlTransactionResult],
        send_reboot_soft: Callable[[int, int, int], ControlTransactionResult],
        send_set_stat_rate: Callable[[int, int, int, int], ControlTransactionResult],
        send_set_throttle: Callable[[int, int, int, int], ControlTransactionResult] | None = None,
        available_node_ids_provider: Callable[[], list[int]] | None = None,
        node_snapshot_provider: Callable[[int], object | None] | None = None,
        reboot_verification_reporter: Callable[[int, str, str], None] | None = None,
        on_notify: Callable[..., None] | None = None,
        default_node_id: int = 1,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._send_ping = send_ping
        self._send_request_stat_now = send_request_stat_now
        self._send_reboot_soft = send_reboot_soft
        self._send_set_stat_rate = send_set_stat_rate
        self._send_set_throttle = send_set_throttle or _missing_set_throttle_handler
        self._available_node_ids_provider = available_node_ids_provider
        self._node_snapshot_provider = node_snapshot_provider
        self._reboot_verification_reporter = reboot_verification_reporter
        self._on_notify = on_notify
        self._default_node_id = max(1, int(default_node_id))
        self._node_options: tuple[ControlPlaneNodeOption, ...] = tuple()
        self._filtered_node_options: tuple[ControlPlaneNodeOption, ...] = tuple()
        self._active_thread: QThread | None = None
        self._active_worker: _TransactionWorker | None = None
        self._active_command_name: str = ""
        self._active_run_index = 0
        self._active_policy_text = ""
        self._last_waiting_hint_run = 0
        self._section_warning_shown = False
        self._last_local_result_by_node: dict[int, ControlTransactionResult] = {}
        self._last_local_result_ts_by_node: dict[int, float] = {}
        self._identity_labels: dict[str, QLabel] = {}
        self._transaction_labels: dict[str, QLabel] = {}
        self._ack_labels: dict[str, QLabel] = {}
        self._reboot_labels: dict[str, QLabel] = {}
        self._runtime_labels: dict[str, QLabel] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        self.group = QGroupBox("Control por nodo (F3)", self)
        self.group.setProperty("sectionRole", "actions")
        group_layout = QVBoxLayout(self.group)
        group_layout.setSpacing(10)

        status_group = QGroupBox("Estado rápido", self)
        status_group.setProperty("sectionRole", "summary")
        status_layout = QVBoxLayout(status_group)
        self.status_label = QLabel(
            "Listo para enviar comandos. Selecciona un nodo."
        )
        self.status_label.setObjectName("controlPlaneStatusLabel")
        self.status_label.setWordWrap(True)
        status_layout.addWidget(self.status_label)
        group_layout.addWidget(status_group)

        target_group = QGroupBox("Nodo seleccionado", self)
        target_group.setProperty("sectionRole", "summary")
        target_layout = QFormLayout(target_group)
        self.node_search_edit = QLineEdit(self)
        self.node_search_edit.setPlaceholderText("Buscar por ID o alias")
        self.node_search_edit.textChanged.connect(self._on_node_filter_changed)
        target_layout.addRow("Buscar", self.node_search_edit)
        target_row = QHBoxLayout()
        self.node_selector_combo = QComboBox(self)
        self.node_selector_combo.currentIndexChanged.connect(self._on_node_selection_changed)
        target_row.addWidget(self.node_selector_combo, 1)
        self.refresh_nodes_button = QPushButton("Actualizar", self)
        self.refresh_nodes_button.setProperty("role", "contextual")
        self.refresh_nodes_button.clicked.connect(self._refresh_node_options)
        target_row.addWidget(self.refresh_nodes_button)
        target_layout.addRow("Nodo", target_row)

        self.node_id_label = QLabel("-", self)
        target_layout.addRow("Identidad", self.node_id_label)

        self.target_help_label = QLabel(
            "Filtra por alias o ID. Los nodos detectados se priorizan automáticamente."
        )
        self.target_help_label.setWordWrap(True)
        target_layout.addRow("Ayuda rápida", self.target_help_label)
        group_layout.addWidget(target_group)

        self._build_snapshot_groups()

        policy_group = QGroupBox("Políticas automáticas", self)
        policy_group.setProperty("sectionRole", "technical")
        policy_layout = QFormLayout(policy_group)
        self.policy_title_label = QLabel("Timeout y reintentos por comando.", self)
        self.policy_title_label.setWordWrap(True)
        policy_layout.addRow("Modo", self.policy_title_label)

        self.policy_values_label = QLabel(self._policy_summary_text(), self)
        self.policy_values_label.setWordWrap(True)
        policy_layout.addRow("Valores", self.policy_values_label)
        group_layout.addWidget(policy_group)

        actions_group = QGroupBox("Comandos", self)
        actions_group.setProperty("sectionRole", "actions")
        actions_layout = QVBoxLayout(actions_group)
        actions_layout.setContentsMargins(8, 8, 8, 8)
        actions_layout.setSpacing(8)

        command_row = QHBoxLayout()
        command_row.setSpacing(8)
        self.ping_button = QPushButton("PING", self)
        self.ping_button.setProperty("role", "secondary")
        self.ping_button.clicked.connect(self._on_ping_clicked)
        command_row.addWidget(self.ping_button)

        self.request_stat_button = QPushButton("Solicitar STAT", self)
        self.request_stat_button.setProperty("role", "secondary")
        self.request_stat_button.clicked.connect(self._on_request_stat_now_clicked)
        command_row.addWidget(self.request_stat_button)

        self.reboot_soft_button = QPushButton("Reinicio suave", self)
        self.reboot_soft_button.setProperty("role", "danger")
        self.reboot_soft_button.clicked.connect(self._on_reboot_soft_clicked)
        command_row.addWidget(self.reboot_soft_button)
        actions_layout.addLayout(command_row)

        self.stat_rate_controls_widget = QWidget(self)
        stat_rate_layout = QHBoxLayout(self.stat_rate_controls_widget)
        stat_rate_layout.setContentsMargins(0, 0, 0, 0)
        stat_rate_layout.setSpacing(8)
        self.stat_rate_label = QLabel("Cadencia STAT", self.stat_rate_controls_widget)
        stat_rate_layout.addWidget(self.stat_rate_label)
        self.stat_rate_combo = QComboBox(self)
        for value_ms in _SET_STAT_RATE_PRESETS_MS:
            self.stat_rate_combo.addItem(f"{value_ms} ms", value_ms)
        stat_rate_layout.addWidget(self.stat_rate_combo, 1)
        self.set_stat_rate_button = QPushButton("Aplicar STAT rate", self)
        self.set_stat_rate_button.setProperty("role", "contextual")
        self.set_stat_rate_button.clicked.connect(self._on_set_stat_rate_clicked)
        stat_rate_layout.addWidget(self.set_stat_rate_button)
        actions_layout.addWidget(self.stat_rate_controls_widget)

        self.throttle_controls_widget = QWidget(self)
        throttle_layout = QHBoxLayout(self.throttle_controls_widget)
        throttle_layout.setContentsMargins(0, 0, 0, 0)
        throttle_layout.setSpacing(8)
        self.throttle_label = QLabel("Throttle planta", self.throttle_controls_widget)
        throttle_layout.addWidget(self.throttle_label)
        self.throttle_combo = QComboBox(self)
        for value_percent in _SET_THROTTLE_PRESETS_PERCENT:
            self.throttle_combo.addItem(f"{value_percent}%", value_percent)
        throttle_layout.addWidget(self.throttle_combo, 1)
        self.set_throttle_button = QPushButton("Aplicar throttle", self)
        self.set_throttle_button.setProperty("role", "contextual")
        self.set_throttle_button.clicked.connect(self._on_set_throttle_clicked)
        throttle_layout.addWidget(self.set_throttle_button)
        actions_layout.addWidget(self.throttle_controls_widget)
        group_layout.addWidget(actions_group)

        self.details_tabs = QTabWidget(self)
        self.details_tabs.setDocumentMode(False)

        self.summary_tab = QWidget(self)
        summary_layout = QVBoxLayout(self.summary_tab)
        summary_layout.setContentsMargins(8, 8, 8, 8)
        summary_layout.setSpacing(8)
        summary_layout.addWidget(self.snapshot_identity_group)
        summary_layout.addWidget(self.snapshot_transaction_group, 1)
        self.details_tabs.addTab(self.summary_tab, "Resumen")

        self.diagnostics_tab = QWidget(self)
        diagnostics_layout = QVBoxLayout(self.diagnostics_tab)
        diagnostics_layout.setContentsMargins(8, 8, 8, 8)
        diagnostics_layout.setSpacing(8)
        diagnostics_layout.addWidget(self.snapshot_ack_group)
        diagnostics_layout.addWidget(self.snapshot_reboot_group)
        diagnostics_layout.addWidget(self.snapshot_runtime_group)
        diagnostics_layout.addWidget(policy_group)
        diagnostics_layout.addStretch(1)
        self.details_tabs.addTab(self.diagnostics_tab, "Diagnóstico")

        self.log_tab = QWidget(self)
        log_layout = QVBoxLayout(self.log_tab)
        log_layout.setContentsMargins(8, 8, 8, 8)
        log_layout.setSpacing(8)
        log_tools_layout = QHBoxLayout()
        self.clear_log_button = QPushButton("Limpiar bitácora", self)
        self.clear_log_button.setProperty("role", "ghost")
        self.clear_log_button.clicked.connect(self._clear_log)
        log_tools_layout.addWidget(self.clear_log_button)
        log_tools_layout.addStretch(1)
        log_layout.addLayout(log_tools_layout)

        self.result_view = QTextEdit(self)
        self.result_view.setObjectName("monoLogView")
        self.result_view.setReadOnly(True)
        self.result_view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.result_view.setMinimumHeight(320)
        self.result_view.setPlaceholderText(
            "Eventos y resultados de transacciones F3."
        )
        log_layout.addWidget(self.result_view, 1)
        self.details_tabs.addTab(self.log_tab, "Bitácora")
        self.details_tabs.setCurrentWidget(self.summary_tab)
        group_layout.addWidget(self.details_tabs, 1)

        root.addWidget(self.group, 1)

        self._waiting_hint_timer = QTimer(self)
        self._waiting_hint_timer.setSingleShot(True)
        self._waiting_hint_timer.timeout.connect(self._on_waiting_hint_timeout)
        self._node_refresh_timer = QTimer(self)
        self._node_refresh_timer.setInterval(2000)
        self._node_refresh_timer.timeout.connect(self._refresh_node_options)
        self._node_refresh_timer.start()
        self._refresh_node_options()

    def _on_ping_clicked(self) -> None:
        self._run_transaction(
            command_name="PING",
            execute=lambda node_id, ack_timeout_ms, max_retries, _progress: _PanelRunOutcome(
                result=self._send_ping(
                    node_id,
                    ack_timeout_ms,
                    max_retries,
                )
            ),
        )

    def _on_request_stat_now_clicked(self) -> None:
        self._run_transaction(
            command_name="REQUEST_STAT_NOW",
            execute=lambda node_id, ack_timeout_ms, max_retries, _progress: _PanelRunOutcome(
                result=self._send_request_stat_now(
                    node_id,
                    ack_timeout_ms,
                    max_retries,
                )
            ),
        )

    def _on_reboot_soft_clicked(self) -> None:
        self._run_transaction(
            command_name="REBOOT_SOFT",
            execute=lambda node_id, ack_timeout_ms, max_retries, progress: self._execute_reboot_with_probe(
                node_id=node_id,
                ack_timeout_ms=ack_timeout_ms,
                max_retries=max_retries,
                progress=progress,
            ),
        )

    def _on_set_stat_rate_clicked(self) -> None:
        stat_rate_ms = self._selected_stat_rate_ms()
        self._run_transaction(
            command_name="SET_STAT_RATE",
            execute=lambda node_id, ack_timeout_ms, max_retries, _progress: _PanelRunOutcome(
                result=self._send_set_stat_rate(
                    node_id,
                    stat_rate_ms,
                    ack_timeout_ms,
                    max_retries,
                )
            ),
        )

    def _on_set_throttle_clicked(self) -> None:
        throttle_percent = self._selected_throttle_percent()
        self._run_transaction(
            command_name="SET_THROTTLE",
            execute=lambda node_id, ack_timeout_ms, max_retries, _progress: _PanelRunOutcome(
                result=self._send_set_throttle(
                    node_id,
                    throttle_percent,
                    ack_timeout_ms,
                    max_retries,
                )
            ),
        )

    def on_section_activated(self) -> None:
        if self._section_warning_shown:
            return
        self._section_warning_shown = True
        self._append_log(
            f"[{self._now_hms()}] Aviso: Control F3 envía comandos reales "
            "(PING/STAT/THROTTLE/STAT_RATE/REBOOT). Reinicio suave puede cortar conectividad temporalmente."
        )
        if callable(self._on_notify):
            self._on_notify(
                title="Control F3 — Comandos reales",
                message=(
                    "Este panel envía comandos reales a nodos del runtime. "
                    "PING y STAT son diagnósticos; reboot puede interrumpir conectividad brevemente."
                ),
                level="warning",
                duration_ms=7000,
            )
            return
        QMessageBox.information(
            self,
            "Control F3",
            (
                "Este panel envía comandos reales a nodos del runtime.\n\n"
                "- PING y Solicitar STAT son diagnósticos.\n"
                "- Throttle planta ajusta el ritmo de emisión en presets curados.\n"
                "- STAT rate ajusta la cadencia de STAT del nodo (presets curados).\n"
                "- Reinicio suave puede interrumpir conectividad por unos segundos.\n\n"
                "Este aviso se muestra una sola vez por apertura de la aplicación."
            ),
            QMessageBox.StandardButton.Ok,
        )

    def _build_snapshot_groups(self) -> None:
        self.snapshot_identity_group = QGroupBox("Identidad y resolución", self)
        self.snapshot_identity_group.setProperty("sectionRole", "technical")
        identity_form = QFormLayout(self.snapshot_identity_group)
        self._identity_labels = self._create_form_labels(
            identity_form,
            (
                ("node_id", "ID"),
                ("label", "Alias"),
                ("resolved_ip", "IP resuelta"),
                ("resolution_status", "Resolución"),
                ("resolution_age", "Antigüedad"),
                ("resolution_message", "Estado"),
                ("backend_message", "Nota backend"),
            ),
        )

        self.snapshot_transaction_group = QGroupBox("Última transacción", self)
        self.snapshot_transaction_group.setProperty("sectionRole", "technical")
        tx_form = QFormLayout(self.snapshot_transaction_group)
        self._transaction_labels = self._create_form_labels(
            tx_form,
            (
                ("transaction_active", "Activa"),
                ("last_command", "Comando"),
                ("last_cmd_seq", "Cmd seq"),
                ("last_nonce", "Nonce"),
                ("last_final_status", "Resultado"),
                ("last_error", "Error"),
                ("last_tx_started", "Inicio"),
                ("last_tx_finished", "Fin"),
            ),
        )

        self.snapshot_ack_group = QGroupBox("Último ACK", self)
        self.snapshot_ack_group.setProperty("sectionRole", "technical")
        ack_form = QFormLayout(self.snapshot_ack_group)
        self._ack_labels = self._create_form_labels(
            ack_form,
            (
                ("ack_stage", "Etapa"),
                ("status_code", "Código"),
                ("err_detail", "Detalle"),
                ("ack_message", "Resumen"),
            ),
        )

        self.snapshot_reboot_group = QGroupBox("Verificación de reinicio", self)
        self.snapshot_reboot_group.setProperty("sectionRole", "technical")
        reboot_form = QFormLayout(self.snapshot_reboot_group)
        self._reboot_labels = self._create_form_labels(
            reboot_form,
            (
                ("reboot_status", "Estado"),
                ("reboot_summary", "Resumen"),
            ),
        )

        self.snapshot_runtime_group = QGroupBox("Señales runtime", self)
        self.snapshot_runtime_group.setProperty("sectionRole", "technical")
        runtime_form = QFormLayout(self.snapshot_runtime_group)
        self._runtime_labels = self._create_form_labels(
            runtime_form,
            (
                ("uptime", "Uptime (s)"),
                ("reset_reason", "Razón de reinicio"),
                ("boot_marker", "Marca de arranque"),
            ),
        )
        resolution_message_label = self._identity_labels.get("resolution_message")
        if resolution_message_label is not None:
            resolution_message_label.setObjectName("controlPlaneResolutionMessage")

    @staticmethod
    def _create_form_labels(
        layout: QFormLayout,
        fields: tuple[tuple[str, str], ...],
    ) -> dict[str, QLabel]:
        labels: dict[str, QLabel] = {}
        for key, title in fields:
            value = QLabel("-")
            value.setWordWrap(True)
            layout.addRow(title, value)
            labels[key] = value
        return labels

    def _refresh_selected_snapshot_view(self) -> None:
        node_id = self._selected_node_id()
        selected = self._selected_node_option()
        snapshot = self._get_node_snapshot(node_id)
        local_result, local_result_age_s = self._recent_local_result_for_node(
            node_id,
            snapshot=snapshot,
        )
        view = build_control_plane_snapshot_view(
            node_id=node_id,
            snapshot=snapshot,
            fallback_label=None if selected is None else selected.node_label,
            local_result=local_result,
            local_result_age_s=local_result_age_s,
        )
        self._apply_snapshot_view(view)

    def _apply_snapshot_view(self, view: ControlPlaneSnapshotView) -> None:
        self._set_label_value(self._identity_labels, "node_id", view.node_id_text)
        self._set_label_value(self._identity_labels, "label", view.label_text)
        self._set_label_value(self._identity_labels, "resolved_ip", view.resolved_ip_text)
        self._set_label_value(
            self._identity_labels,
            "resolution_status",
            view.resolution_status_text,
        )
        self._set_label_value(self._identity_labels, "resolution_age", view.resolution_age_text)
        self._set_label_value(
            self._identity_labels,
            "resolution_message",
            view.resolution_message_text,
        )
        self._set_label_value(
            self._identity_labels,
            "backend_message",
            view.backend_message_text,
        )

        self._set_label_value(
            self._transaction_labels,
            "transaction_active",
            view.transaction_active_text,
        )
        self._set_label_value(self._transaction_labels, "last_command", view.last_command_text)
        self._set_label_value(self._transaction_labels, "last_cmd_seq", view.last_cmd_seq_text)
        self._set_label_value(self._transaction_labels, "last_nonce", view.last_nonce_text)
        self._set_label_value(
            self._transaction_labels,
            "last_final_status",
            view.last_final_status_text,
        )
        self._set_label_value(self._transaction_labels, "last_error", view.last_error_text)
        self._set_label_value(
            self._transaction_labels,
            "last_tx_started",
            view.last_tx_started_text,
        )
        self._set_label_value(
            self._transaction_labels,
            "last_tx_finished",
            view.last_tx_finished_text,
        )

        self._set_label_value(self._ack_labels, "ack_stage", view.ack_stage_text)
        self._set_label_value(self._ack_labels, "status_code", view.ack_status_code_text)
        self._set_label_value(self._ack_labels, "err_detail", view.ack_err_detail_text)
        self._set_label_value(self._ack_labels, "ack_message", view.ack_message_text)

        self._set_label_value(self._reboot_labels, "reboot_status", view.reboot_status_text)
        self._set_label_value(self._reboot_labels, "reboot_summary", view.reboot_summary_text)

        self._set_label_value(self._runtime_labels, "uptime", view.uptime_text)
        self._set_label_value(self._runtime_labels, "reset_reason", view.reset_reason_text)
        self._set_label_value(self._runtime_labels, "boot_marker", view.boot_marker_text)

        self._apply_resolution_hint_visuals(view)

    @staticmethod
    def _set_label_value(labels: dict[str, QLabel], key: str, value: str) -> None:
        label = labels.get(key)
        if label is None:
            return
        label.setText(value)

    def _apply_resolution_hint_visuals(self, view: ControlPlaneSnapshotView) -> None:
        message_label = self._identity_labels.get("resolution_message")
        if message_label is None:
            return
        should_emphasize = bool(view.is_unresolved or view.is_stale)
        if bool(message_label.property("emphasis")) == should_emphasize:
            return
        message_label.setProperty("emphasis", should_emphasize)
        style = message_label.style()
        style.unpolish(message_label)
        style.polish(message_label)
        message_label.update()

    def _run_transaction(
        self,
        *,
        command_name: str,
        execute: Callable[[int, int, int, Callable[[str], None]], _PanelRunOutcome],
    ) -> None:
        if self._active_thread is not None:
            self.status_label.setText(
                f"{command_name}: espera, hay otra transacción en progreso."
            )
            self._append_log(
                f"[{self._now_hms()}] {command_name} ignorado: transacción en progreso."
            )
            return

        node_id = self._selected_node_id()
        policy = resolve_control_command_policy(command_name)
        ack_timeout_ms = int(policy.ack_timeout_ms)
        max_retries = int(policy.max_retries)
        self._active_policy_text = (
            f"ack_timeout_ms={ack_timeout_ms}, max_retries={max_retries} (auto)"
        )
        self._active_run_index += 1
        run_index = self._active_run_index
        selected = self._selected_node_option()
        selected_label = "-" if selected is None else selected.node_label

        self._active_command_name = command_name
        self._set_busy(
            True,
            status_text=f"{command_name}: enviando comando ({self._active_policy_text})...",
        )
        if hasattr(self, "details_tabs"):
            self.details_tabs.setCurrentWidget(self.log_tab)
        self._append_log(
            f"[{self._now_hms()}] RUN {run_index} | {command_name} | "
            f"nodo={selected_label} (id={node_id}) | {self._active_policy_text}"
        )
        self._append_log(f"[{self._now_hms()}] RUN {run_index} | estado=enviando")
        if command_name == "REBOOT_SOFT":
            self._append_log(
                f"[{self._now_hms()}] RUN {run_index} | "
                "verificación_reinicio=activa (puede tardar hasta ~12s)"
            )
        self._waiting_hint_timer.start(120)

        worker = _TransactionWorker(
            lambda progress: execute(
                node_id,
                ack_timeout_ms,
                max_retries,
                progress,
            )
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_worker_progress)
        worker.finished.connect(self._on_transaction_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_finished)

        self._active_worker = worker
        self._active_thread = thread
        thread.start()

    def _set_busy(self, is_busy: bool, *, status_text: str | None = None) -> None:
        enabled = not is_busy
        self.node_selector_combo.setEnabled(enabled)
        self.refresh_nodes_button.setEnabled(enabled)
        self.clear_log_button.setEnabled(enabled)
        self.ping_button.setEnabled(enabled)
        self.request_stat_button.setEnabled(enabled)
        self.reboot_soft_button.setEnabled(enabled)
        self.stat_rate_combo.setEnabled(enabled)
        self.set_stat_rate_button.setEnabled(enabled)
        self.throttle_combo.setEnabled(enabled)
        self.set_throttle_button.setEnabled(enabled)
        if status_text:
            self.status_label.setText(status_text)

    @Slot()
    def _on_waiting_hint_timeout(self) -> None:
        if self._active_thread is None:
            return
        self.status_label.setText(f"{self._active_command_name}: esperando ACK...")
        if self._last_waiting_hint_run != self._active_run_index:
            self._append_log(
                f"[{self._now_hms()}] RUN {self._active_run_index} | estado=esperando_ack"
            )
            self._last_waiting_hint_run = self._active_run_index

    @Slot(str)
    def _on_worker_progress(self, message: str) -> None:
        text = str(message).strip()
        if not text:
            return
        self._append_log(
            f"[{self._now_hms()}] RUN {self._active_run_index} | {text}"
        )

    @Slot(object, object)
    def _on_transaction_finished(self, result_obj: object, error_obj: object) -> None:
        self._waiting_hint_timer.stop()
        self._set_busy(False)

        if error_obj is not None:
            self.status_label.setText(
                f"{self._active_command_name}: error durante transacción."
            )
            error_text = str(error_obj)
            self._append_log(
                f"[{self._now_hms()}] RUN {self._active_run_index} | error={error_text}"
            )
            if "CKV2_CONTROL_SECRET" in error_text:
                self._append_log(
                    f"[{self._now_hms()}] RUN {self._active_run_index} | "
                    "tip: define CKV2_CONTROL_SECRET o configura "
                    "firmware/okua_node_udp_v1/okua_node_secrets.h."
                )
            return

        if not isinstance(result_obj, _PanelRunOutcome):
            self.status_label.setText(
                f"{self._active_command_name}: error de integración (resultado inválido)."
            )
            self._append_log(
                f"[{self._now_hms()}] RUN {self._active_run_index} | "
                "error=resultado inválido del worker"
            )
            return

        result = result_obj.result
        if not isinstance(result, ControlTransactionResult):
            self.status_label.setText(
                f"{self._active_command_name}: error de integración (resultado inválido)."
            )
            self._append_log(
                f"[{self._now_hms()}] RUN {self._active_run_index} | "
                "error=worker devolvió outcome sin ControlTransactionResult"
            )
            return

        result_view = format_control_transaction_result(result)
        self.status_label.setText(result_view.headline)
        self._register_local_result(result)
        self._append_log(
            f"[{self._now_hms()}] RUN {self._active_run_index} | resultado={result_view.headline}"
        )
        for line in result_view.details_text.splitlines():
            self._append_log(f"[{self._now_hms()}] RUN {self._active_run_index} | {line}")
        for line in format_control_transaction_event_lines(result):
            self._append_log(f"[{self._now_hms()}] RUN {self._active_run_index} | event={line}")
        for line in result_obj.post_lines:
            self._append_log(f"[{self._now_hms()}] RUN {self._active_run_index} | {line}")

        reboot_feedback = self._extract_reboot_feedback_line(result_obj.post_lines)
        if self._active_command_name == "REBOOT_SOFT":
            if reboot_feedback is None:
                reboot_feedback = (
                    "reinicio no confirmado automáticamente: "
                    "no se obtuvo evidencia concluyente en la verificación."
                )
                self._append_log(
                    f"[{self._now_hms()}] RUN {self._active_run_index} | {reboot_feedback}"
                )
            self.status_label.setText(f"REBOOT_SOFT: {reboot_feedback}")
        self._refresh_selected_snapshot_view()

    @Slot()
    def _on_thread_finished(self) -> None:
        self._active_thread = None
        self._active_worker = None
        self._active_command_name = ""
        self._active_policy_text = ""

    @Slot()
    def _refresh_node_options(self) -> None:
        available_ids: list[int] = []
        if self._available_node_ids_provider is not None:
            try:
                available_ids = list(self._available_node_ids_provider())
            except Exception:
                available_ids = []
        options = build_control_plane_node_options(available_ids, max_boxes=5)
        current_id = self._selected_node_id()
        self._node_options = options
        self._rebuild_node_selector(current_id=current_id)
        self._refresh_selected_snapshot_view()

    @Slot(str)
    def _on_node_filter_changed(self, _text: str) -> None:
        self._rebuild_node_selector(current_id=self._selected_node_id())
        self._refresh_selected_snapshot_view()

    def _rebuild_node_selector(self, *, current_id: int) -> None:
        options = self._filtered_options()
        self._filtered_node_options = options
        self.node_selector_combo.blockSignals(True)
        self.node_selector_combo.clear()
        selected_index = -1
        first_detected = -1
        for index, option in enumerate(options):
            self.node_selector_combo.addItem(option.display_text, option.node_id)
            if option.is_available and first_detected < 0:
                first_detected = index
            if option.node_id == current_id:
                selected_index = index
            if option.node_id == self._default_node_id and selected_index < 0:
                selected_index = index
        if selected_index < 0:
            selected_index = first_detected
        if selected_index < 0 and self.node_selector_combo.count() > 0:
            selected_index = 0
        if selected_index >= 0:
            self.node_selector_combo.setCurrentIndex(selected_index)
        self.node_selector_combo.blockSignals(False)
        self._update_selected_node_label()

    def _filtered_options(self) -> tuple[ControlPlaneNodeOption, ...]:
        search_text = self.node_search_edit.text().strip().lower()
        if not search_text:
            return self._node_options
        filtered: list[ControlPlaneNodeOption] = []
        for option in self._node_options:
            haystack = f"{option.node_id} {option.node_label} {option.display_text}".lower()
            if search_text in haystack:
                filtered.append(option)
        return tuple(filtered)

    def _selected_node_id(self) -> int:
        if self.node_selector_combo.count() <= 0:
            return self._default_node_id
        raw = self.node_selector_combo.currentData()
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return self._default_node_id
        return max(1, value)

    def _selected_stat_rate_ms(self) -> int:
        raw = self.stat_rate_combo.currentData()
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return _SET_STAT_RATE_PRESETS_MS[0]
        if value in _SET_STAT_RATE_PRESETS_MS:
            return value
        return _SET_STAT_RATE_PRESETS_MS[0]

    def _selected_throttle_percent(self) -> int:
        raw = self.throttle_combo.currentData()
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return _SET_THROTTLE_PRESETS_PERCENT[0]
        if value in _SET_THROTTLE_PRESETS_PERCENT:
            return value
        return _SET_THROTTLE_PRESETS_PERCENT[0]

    def _selected_node_option(self) -> ControlPlaneNodeOption | None:
        if self.node_selector_combo.count() <= 0:
            return None
        node_id = self._selected_node_id()
        for option in self._filtered_node_options or self._node_options:
            if option.node_id == node_id:
                return option
        return None

    def _update_selected_node_label(self) -> None:
        selected = self._selected_node_option()
        if selected is None:
            self.node_id_label.setText("Sin coincidencias" if self.node_selector_combo.count() <= 0 else f"ID {self._selected_node_id()}")
            return
        status = "detectado" if selected.is_available else "no detectado"
        self.node_id_label.setText(f"{selected.node_label} · ID {selected.node_id} · {status}")

    @Slot(int)
    def _on_node_selection_changed(self, _index: int) -> None:
        self._update_selected_node_label()
        self._refresh_selected_snapshot_view()

    def _append_log(self, line: str) -> None:
        current = self.result_view.toPlainText().rstrip()
        if current:
            self.result_view.setPlainText(f"{current}\n{line}")
        else:
            self.result_view.setPlainText(line)
        self.result_view.moveCursor(QTextCursor.MoveOperation.End)

    @Slot()
    def _clear_log(self) -> None:
        self.result_view.clear()
        self._append_log(f"[{self._now_hms()}] Bitácora limpiada.")

    def _execute_reboot_with_probe(
        self,
        *,
        node_id: int,
        ack_timeout_ms: int,
        max_retries: int,
        progress: Callable[[str], None],
    ) -> _PanelRunOutcome:
        trace_lines: list[str] = []

        def _emit(message: str) -> None:
            text = str(message).strip()
            if not text:
                return
            trace_lines.append(text)
            progress(text)

        baseline_uptime_s = self._read_node_uptime_s(node_id)
        baseline_reset_reason = self._read_node_reset_reason(node_id)
        baseline_boot_marker = self._read_node_boot_marker(node_id)
        if baseline_uptime_s is None:
            _emit("verificación_reinicio: uptime previo no disponible.")
        else:
            _emit(f"verificación_reinicio: uptime_previo_s={baseline_uptime_s}")
        if baseline_reset_reason is None:
            _emit("verificación_reinicio: reset_reason previo no disponible.")
        else:
            _emit(f"verificación_reinicio: reset_reason_previo={baseline_reset_reason}")
        if baseline_boot_marker is None:
            _emit("verificación_reinicio: boot_marker previo no disponible.")
        else:
            _emit(f"verificación_reinicio: boot_marker_previo={baseline_boot_marker}")

        result = self._send_reboot_soft(node_id, ack_timeout_ms, max_retries)
        post_lines: list[str] = []
        if result.final_status.value != "ack_matched":
            summary = "reinicio no verificado: no hubo ACK_MATCHED para REBOOT_SOFT."
            post_lines.append(summary)
            self._report_reboot_verification(
                node_id=node_id,
                status="not_verified_no_ack",
                summary=summary,
            )
            return _PanelRunOutcome(result=result, post_lines=tuple(post_lines))

        _emit("ACK REBOOT_SOFT recibido; iniciando verificación de efecto en nodo...")
        post_lines.append("ACK REBOOT_SOFT recibido; verificando efecto de reinicio...")
        probe_outcome = self._probe_reboot_effect(
            node_id,
            baseline_uptime_s=baseline_uptime_s,
            baseline_reset_reason=baseline_reset_reason,
            baseline_boot_marker=baseline_boot_marker,
            progress=_emit,
        )
        post_lines.append(probe_outcome.feedback_line)
        post_lines.append(
            "verificación_reinicio_resumen: "
            f"intentos={probe_outcome.attempt_count} "
            f"corte={int(probe_outcome.observed_interruption)} "
            f"recuperado={int(probe_outcome.observed_recovery)} "
            f"uptime_reset={int(probe_outcome.observed_uptime_reset)} "
            f"reset_reason_change={int(probe_outcome.observed_reset_reason_change)} "
            f"boot_marker_change={int(probe_outcome.observed_boot_marker_change)} "
            f"uptime_previo={_fmt_int_or_dash(probe_outcome.baseline_uptime_s)} "
            f"uptime_final={_fmt_int_or_dash(probe_outcome.final_uptime_s)} "
            f"reset_reason_previo={_fmt_int_or_dash(probe_outcome.baseline_reset_reason)} "
            f"reset_reason_final={_fmt_int_or_dash(probe_outcome.final_reset_reason)} "
            f"boot_marker_previo={_fmt_int_or_dash(probe_outcome.baseline_boot_marker)} "
            f"boot_marker_final={_fmt_int_or_dash(probe_outcome.final_boot_marker)}"
        )
        verification_summary = next(
            (
                line
                for line in post_lines
                if str(line).strip().startswith("verificación_reinicio_resumen:")
            ),
            probe_outcome.feedback_line,
        )
        self._report_reboot_verification(
            node_id=node_id,
            status=self._resolve_reboot_verification_status(probe_outcome.feedback_line),
            summary=verification_summary,
        )
        return _PanelRunOutcome(result=result, post_lines=tuple(post_lines))

    def _probe_reboot_effect(
        self,
        node_id: int,
        *,
        baseline_uptime_s: int | None,
        baseline_reset_reason: int | None,
        baseline_boot_marker: int | None,
        progress: Callable[[str], None],
    ) -> _RebootProbeOutcome:
        observed_interruption = False
        observed_recovery = False
        observed_uptime_reset = False
        observed_reset_reason_change = False
        observed_boot_marker_change = False
        last_uptime_s = baseline_uptime_s
        last_reset_reason = baseline_reset_reason
        last_boot_marker = baseline_boot_marker
        deadline = time.monotonic() + 12.0
        attempt = 0

        # Give deferred reboot scheduling a short head start.
        time.sleep(0.35)
        while time.monotonic() < deadline:
            attempt += 1
            ping_state = "unknown"
            try:
                probe = self._send_ping(node_id, 250, 0)
            except Exception:
                observed_interruption = True
                ping_state = "send_error"
            else:
                ping_state = probe.final_status.value
                if probe.final_status.value == "ack_matched":
                    if observed_interruption:
                        observed_recovery = True
                else:
                    observed_interruption = True

            # Refresh runtime STAT occasionally to update uptime snapshot.
            if attempt % 3 == 0:
                try:
                    self._send_request_stat_now(node_id, 450, 0)
                except Exception:
                    pass

            current_uptime_s = self._read_node_uptime_s(node_id)
            current_reset_reason = self._read_node_reset_reason(node_id)
            current_boot_marker = self._read_node_boot_marker(node_id)
            if current_uptime_s is not None:
                if (
                    last_uptime_s is not None
                    and current_uptime_s + 1 < last_uptime_s
                ):
                    observed_uptime_reset = True
                last_uptime_s = current_uptime_s
            if (
                baseline_reset_reason is not None
                and current_reset_reason is not None
                and current_reset_reason != baseline_reset_reason
            ):
                observed_reset_reason_change = True
            if current_reset_reason is not None:
                last_reset_reason = current_reset_reason
            if (
                baseline_boot_marker is not None
                and current_boot_marker is not None
                and current_boot_marker != baseline_boot_marker
            ):
                observed_boot_marker_change = True
            if current_boot_marker is not None:
                last_boot_marker = current_boot_marker

            uptime_text = "-" if current_uptime_s is None else str(current_uptime_s)
            reason_text = "-" if current_reset_reason is None else str(current_reset_reason)
            boot_text = "-" if current_boot_marker is None else str(current_boot_marker)
            progress(
                "verificación_reinicio "
                f"intento={attempt} ping={ping_state} uptime_s={uptime_text} "
                f"corte={int(observed_interruption)} recuperado={int(observed_recovery)} "
                f"uptime_reset={int(observed_uptime_reset)} "
                f"reset_reason={reason_text} "
                f"reason_change={int(observed_reset_reason_change)} "
                f"boot_marker={boot_text} "
                f"boot_change={int(observed_boot_marker_change)}"
            )

            if observed_uptime_reset:
                return _RebootProbeOutcome(
                    feedback_line="reinicio confirmado: se detectó reinicio de uptime en runtime STAT.",
                    attempt_count=attempt,
                    observed_interruption=observed_interruption,
                    observed_recovery=observed_recovery,
                    observed_uptime_reset=observed_uptime_reset,
                    observed_reset_reason_change=observed_reset_reason_change,
                    observed_boot_marker_change=observed_boot_marker_change,
                    baseline_uptime_s=baseline_uptime_s,
                    final_uptime_s=last_uptime_s,
                    baseline_reset_reason=baseline_reset_reason,
                    final_reset_reason=last_reset_reason,
                    baseline_boot_marker=baseline_boot_marker,
                    final_boot_marker=last_boot_marker,
                )

            if observed_reset_reason_change:
                return _RebootProbeOutcome(
                    feedback_line=(
                        "reinicio confirmado: se detectó cambio de reset_reason "
                        "en runtime STAT."
                    ),
                    attempt_count=attempt,
                    observed_interruption=observed_interruption,
                    observed_recovery=observed_recovery,
                    observed_uptime_reset=observed_uptime_reset,
                    observed_reset_reason_change=observed_reset_reason_change,
                    observed_boot_marker_change=observed_boot_marker_change,
                    baseline_uptime_s=baseline_uptime_s,
                    final_uptime_s=last_uptime_s,
                    baseline_reset_reason=baseline_reset_reason,
                    final_reset_reason=last_reset_reason,
                    baseline_boot_marker=baseline_boot_marker,
                    final_boot_marker=last_boot_marker,
                )

            if observed_boot_marker_change:
                return _RebootProbeOutcome(
                    feedback_line=(
                        "reinicio confirmado: se detectó cambio de boot_marker "
                        "en state_flags del STAT."
                    ),
                    attempt_count=attempt,
                    observed_interruption=observed_interruption,
                    observed_recovery=observed_recovery,
                    observed_uptime_reset=observed_uptime_reset,
                    observed_reset_reason_change=observed_reset_reason_change,
                    observed_boot_marker_change=observed_boot_marker_change,
                    baseline_uptime_s=baseline_uptime_s,
                    final_uptime_s=last_uptime_s,
                    baseline_reset_reason=baseline_reset_reason,
                    final_reset_reason=last_reset_reason,
                    baseline_boot_marker=baseline_boot_marker,
                    final_boot_marker=last_boot_marker,
                )

            if observed_interruption and observed_recovery:
                return _RebootProbeOutcome(
                    feedback_line=(
                        "reinicio confirmado: se observó corte temporal de ACK y recuperación "
                        "posterior de PING."
                    ),
                    attempt_count=attempt,
                    observed_interruption=observed_interruption,
                    observed_recovery=observed_recovery,
                    observed_uptime_reset=observed_uptime_reset,
                    observed_reset_reason_change=observed_reset_reason_change,
                    observed_boot_marker_change=observed_boot_marker_change,
                    baseline_uptime_s=baseline_uptime_s,
                    final_uptime_s=last_uptime_s,
                    baseline_reset_reason=baseline_reset_reason,
                    final_reset_reason=last_reset_reason,
                    baseline_boot_marker=baseline_boot_marker,
                    final_boot_marker=last_boot_marker,
                )
            time.sleep(0.4)

        if observed_interruption:
            return _RebootProbeOutcome(
                feedback_line=(
                    "reinicio probable: hubo interrupción de respuesta, pero no se confirmó "
                    "recuperación completa dentro de la ventana."
                ),
                attempt_count=attempt,
                observed_interruption=observed_interruption,
                observed_recovery=observed_recovery,
                observed_uptime_reset=observed_uptime_reset,
                observed_reset_reason_change=observed_reset_reason_change,
                observed_boot_marker_change=observed_boot_marker_change,
                baseline_uptime_s=baseline_uptime_s,
                final_uptime_s=last_uptime_s,
                baseline_reset_reason=baseline_reset_reason,
                final_reset_reason=last_reset_reason,
                baseline_boot_marker=baseline_boot_marker,
                final_boot_marker=last_boot_marker,
            )
        return _RebootProbeOutcome(
            feedback_line=(
                "reinicio no confirmado automáticamente: el nodo respondió a PING sin interrupción "
                "durante la ventana de verificación."
            ),
            attempt_count=attempt,
            observed_interruption=observed_interruption,
            observed_recovery=observed_recovery,
            observed_uptime_reset=observed_uptime_reset,
            observed_reset_reason_change=observed_reset_reason_change,
            observed_boot_marker_change=observed_boot_marker_change,
            baseline_uptime_s=baseline_uptime_s,
            final_uptime_s=last_uptime_s,
            baseline_reset_reason=baseline_reset_reason,
            final_reset_reason=last_reset_reason,
            baseline_boot_marker=baseline_boot_marker,
            final_boot_marker=last_boot_marker,
        )

    def _read_node_uptime_s(self, node_id: int) -> int | None:
        snapshot = self._get_node_snapshot(node_id)
        if snapshot is None:
            return None
        raw = getattr(snapshot, "last_uptime_s", None)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        if value < 0:
            return None
        return value

    def _read_node_reset_reason(self, node_id: int) -> int | None:
        snapshot = self._get_node_snapshot(node_id)
        if snapshot is None:
            return None
        raw = getattr(snapshot, "last_reset_reason", None)
        if raw is None:
            raw = getattr(snapshot, "reset_reason", None)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        if value < 0:
            return None
        return value

    def _read_node_boot_marker(self, node_id: int) -> int | None:
        snapshot = self._get_node_snapshot(node_id)
        if snapshot is None:
            return None
        direct_marker = getattr(snapshot, "last_boot_marker", None)
        try:
            marker = int(direct_marker)
        except (TypeError, ValueError):
            marker = None
        if marker is not None and 0 <= marker <= 0x0F:
            return marker
        raw = getattr(snapshot, "last_state_flags", None)
        try:
            flags = int(raw)
        except (TypeError, ValueError):
            return None
        if flags < 0 or flags > 0xFF:
            return None
        return (flags >> 4) & 0x0F

    def _get_node_snapshot(self, node_id: int) -> object | None:
        provider = self._node_snapshot_provider
        if provider is None:
            return None
        try:
            resolved_node_id = int(node_id)
        except (TypeError, ValueError):
            return None
        if resolved_node_id <= 0:
            return None
        try:
            return provider(resolved_node_id)
        except Exception:
            return None

    def _recent_local_result_for_node(
        self,
        node_id: int,
        *,
        snapshot: object | None = None,
    ) -> tuple[ControlTransactionResult | None, float | None]:
        try:
            resolved_node_id = int(node_id)
        except (TypeError, ValueError):
            return None, None
        cached = self._last_local_result_by_node.get(resolved_node_id)
        if cached is None:
            return None, None
        ts = self._last_local_result_ts_by_node.get(resolved_node_id)
        if ts is None:
            return None, None
        # Keep fallback only as a brief bridge while canonical backend snapshot absorbs the result.
        age_s = max(0.0, float(time.monotonic()) - float(ts))
        if age_s > 3.0:
            self._last_local_result_by_node.pop(resolved_node_id, None)
            self._last_local_result_ts_by_node.pop(resolved_node_id, None)
            return None, None

        snapshot_cmd_seq = self._as_int_or_none(
            None if snapshot is None else getattr(snapshot, "last_cmd_seq", None)
        )
        local_cmd_seq = self._as_int_or_none(getattr(cached, "cmd_seq", None))
        if (
            snapshot_cmd_seq is not None
            and local_cmd_seq is not None
            and self._is_cmd_seq_newer(snapshot_cmd_seq, local_cmd_seq)
        ):
            self._last_local_result_by_node.pop(resolved_node_id, None)
            self._last_local_result_ts_by_node.pop(resolved_node_id, None)
            return None, None

        return cached, age_s

    def _register_local_result(self, result: ControlTransactionResult) -> None:
        try:
            node_id = int(result.node_id)
        except (TypeError, ValueError):
            return
        if node_id <= 0:
            return
        self._last_local_result_by_node[node_id] = result
        self._last_local_result_ts_by_node[node_id] = float(time.monotonic())

    @staticmethod
    def _is_cmd_seq_newer(candidate: int, reference: int) -> bool:
        left = int(candidate) & 0xFFFF
        right = int(reference) & 0xFFFF
        diff = (left - right) & 0xFFFF
        return 0 < diff < 0x8000

    @staticmethod
    def _as_int_or_none(raw_value: object) -> int | None:
        if raw_value is None:
            return None
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return None

    def _policy_summary_text(self) -> str:
        ping = resolve_control_command_policy("PING")
        stat = resolve_control_command_policy("REQUEST_STAT_NOW")
        throttle = resolve_control_command_policy("SET_THROTTLE")
        stat_rate = resolve_control_command_policy("SET_STAT_RATE")
        reboot = resolve_control_command_policy("REBOOT_SOFT")
        return (
            "PING: "
            f"{ping.ack_timeout_ms} ms/{ping.max_retries} reintentos | "
            "REQUEST_STAT_NOW: "
            f"{stat.ack_timeout_ms} ms/{stat.max_retries} reintentos | "
            "SET_THROTTLE: "
            f"{throttle.ack_timeout_ms} ms/{throttle.max_retries} reintentos | "
            "SET_STAT_RATE: "
            f"{stat_rate.ack_timeout_ms} ms/{stat_rate.max_retries} reintentos | "
            "REBOOT_SOFT: "
            f"{reboot.ack_timeout_ms} ms/{reboot.max_retries} reintentos"
        )

    @staticmethod
    def _now_hms() -> str:
        return datetime.now().strftime("%H:%M:%S")

    @staticmethod
    def _extract_reboot_feedback_line(lines: tuple[str, ...]) -> str | None:
        for line in lines:
            text = str(line).strip()
            if text.startswith("reinicio "):
                return text
        return None

    def _report_reboot_verification(
        self,
        *,
        node_id: int,
        status: str,
        summary: str,
    ) -> None:
        reporter = self._reboot_verification_reporter
        if reporter is None:
            return
        try:
            reporter(int(node_id), str(status), str(summary))
        except Exception:
            return

    @staticmethod
    def _resolve_reboot_verification_status(feedback_line: str) -> str:
        text = str(feedback_line).strip().lower()
        if text.startswith("reinicio confirmado"):
            return "confirmed"
        if text.startswith("reinicio probable"):
            return "probable"
        if text.startswith("reinicio no confirmado"):
            return "not_confirmed"
        return "unknown"


def _fmt_int_or_dash(value: int | None) -> str:
    if value is None:
        return "-"
    return str(int(value))


def _missing_set_throttle_handler(
    _node_id: int,
    _throttle_percent: int,
    _ack_timeout_ms: int,
    _max_retries: int,
) -> ControlTransactionResult:
    raise RuntimeError("send_set_throttle no está configurado en ControlPlanePanel.")
