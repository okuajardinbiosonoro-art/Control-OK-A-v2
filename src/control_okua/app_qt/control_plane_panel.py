from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from control_okua.app_qt.viewmodels.control_plane_vm import (
    REBOOT_SOFT_CONFIRMATION_TITLE,
    build_reboot_soft_confirmation_text,
    format_control_transaction_result,
)
from control_okua.services.control_transaction_service import (
    ControlTransactionResult,
    ControlTransactionService,
)


class _TransactionWorker(QObject):
    finished = Signal(object, object)

    def __init__(self, execute: Callable[[], ControlTransactionResult]) -> None:
        super().__init__()
        self._execute = execute

    @Slot()
    def run(self) -> None:
        try:
            result = self._execute()
        except Exception as exc:
            self.finished.emit(None, str(exc))
            return
        self.finished.emit(result, None)


class ControlPlanePanel(QWidget):
    def __init__(
        self,
        *,
        transaction_service_provider: Callable[[], ControlTransactionService],
        default_node_ip: str = "",
        default_node_id: int = 1,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._transaction_service_provider = transaction_service_provider
        self._active_thread: QThread | None = None
        self._active_worker: _TransactionWorker | None = None
        self._active_command_name: str = ""

        root = QVBoxLayout(self)

        self.group = QGroupBox("Control Plane F3 (técnico)", self)
        group_layout = QVBoxLayout(self.group)

        self.status_label = QLabel(
            "Panel técnico listo. Define target y ejecuta una acción manual."
        )
        self.status_label.setWordWrap(True)
        group_layout.addWidget(self.status_label)

        target_layout = QFormLayout()
        self.node_ip_edit = QLineEdit(self)
        self.node_ip_edit.setPlaceholderText("192.168.1.40")
        self.node_ip_edit.setText(str(default_node_ip).strip())
        target_layout.addRow("IP nodo", self.node_ip_edit)

        self.node_id_spin = QSpinBox(self)
        self.node_id_spin.setRange(1, 0xFFFF)
        self.node_id_spin.setValue(max(1, int(default_node_id)))
        target_layout.addRow("node_id", self.node_id_spin)
        group_layout.addLayout(target_layout)

        policy_layout = QFormLayout()
        self.ack_timeout_spin = QSpinBox(self)
        self.ack_timeout_spin.setRange(50, 15000)
        self.ack_timeout_spin.setValue(350)
        self.ack_timeout_spin.setSuffix(" ms")
        policy_layout.addRow("ack_timeout_ms", self.ack_timeout_spin)

        self.max_retries_spin = QSpinBox(self)
        self.max_retries_spin.setRange(0, 10)
        self.max_retries_spin.setValue(1)
        policy_layout.addRow("max_retries", self.max_retries_spin)
        group_layout.addLayout(policy_layout)

        actions_layout = QHBoxLayout()
        self.ping_button = QPushButton("PING", self)
        self.ping_button.clicked.connect(self._on_ping_clicked)
        actions_layout.addWidget(self.ping_button)

        self.request_stat_button = QPushButton("Solicitar STAT ahora", self)
        self.request_stat_button.clicked.connect(self._on_request_stat_now_clicked)
        actions_layout.addWidget(self.request_stat_button)

        self.reboot_soft_button = QPushButton("Reinicio suave", self)
        self.reboot_soft_button.clicked.connect(self._on_reboot_soft_clicked)
        actions_layout.addWidget(self.reboot_soft_button)
        group_layout.addLayout(actions_layout)

        self.result_view = QTextEdit(self)
        self.result_view.setReadOnly(True)
        self.result_view.setPlaceholderText(
            "Aquí aparece el último resultado de transacción F3."
        )
        group_layout.addWidget(self.result_view)

        root.addWidget(self.group)

        self._waiting_hint_timer = QTimer(self)
        self._waiting_hint_timer.setSingleShot(True)
        self._waiting_hint_timer.timeout.connect(self._on_waiting_hint_timeout)

    def _on_ping_clicked(self) -> None:
        self._run_transaction(
            command_name="PING",
            execute=lambda service, node_ip, node_id, ack_timeout_ms, max_retries: service.send_ping_and_wait_ack(
                node_ip,
                node_id,
                ack_timeout_ms=ack_timeout_ms,
                max_retries=max_retries,
            ),
        )

    def _on_request_stat_now_clicked(self) -> None:
        self._run_transaction(
            command_name="REQUEST_STAT_NOW",
            execute=lambda service, node_ip, node_id, ack_timeout_ms, max_retries: service.send_request_stat_now_and_wait_ack(
                node_ip,
                node_id,
                ack_timeout_ms=ack_timeout_ms,
                max_retries=max_retries,
            ),
        )

    def _on_reboot_soft_clicked(self) -> None:
        if not self._confirm_reboot_soft():
            return
        self._run_transaction(
            command_name="REBOOT_SOFT",
            execute=lambda service, node_ip, node_id, ack_timeout_ms, max_retries: service.send_reboot_soft_and_wait_ack(
                node_ip,
                node_id,
                ack_timeout_ms=ack_timeout_ms,
                max_retries=max_retries,
            ),
        )

    def _confirm_reboot_soft(self) -> bool:
        node_ip = self.node_ip_edit.text().strip()
        node_id = int(self.node_id_spin.value())
        message = build_reboot_soft_confirmation_text(
            node_ip=node_ip,
            node_id=node_id,
        )
        answer = QMessageBox.warning(
            self,
            REBOOT_SOFT_CONFIRMATION_TITLE,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer is QMessageBox.StandardButton.Yes

    def _run_transaction(
        self,
        *,
        command_name: str,
        execute: Callable[
            [ControlTransactionService, str, int, int, int],
            ControlTransactionResult,
        ],
    ) -> None:
        if self._active_thread is not None:
            return

        node_ip = self.node_ip_edit.text().strip()
        if not node_ip:
            self.status_label.setText("Error: IP de nodo requerida.")
            self.result_view.setPlainText("Ingresa una IP de target antes de enviar comando.")
            return

        node_id = int(self.node_id_spin.value())
        ack_timeout_ms = int(self.ack_timeout_spin.value())
        max_retries = int(self.max_retries_spin.value())

        try:
            service = self._transaction_service_provider()
        except Exception as exc:
            self.status_label.setText("Error: no se pudo preparar el control-plane.")
            self.result_view.setPlainText(str(exc))
            return

        self._active_command_name = command_name
        self._set_busy(True, status_text=f"{command_name}: enviando comando...")
        self.result_view.setPlainText(
            "Transacción en progreso.\nEstado: enviando..."
        )
        self._waiting_hint_timer.start(120)

        worker = _TransactionWorker(
            lambda: execute(
                service,
                node_ip,
                node_id,
                ack_timeout_ms,
                max_retries,
            )
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
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
        self.node_ip_edit.setEnabled(enabled)
        self.node_id_spin.setEnabled(enabled)
        self.ack_timeout_spin.setEnabled(enabled)
        self.max_retries_spin.setEnabled(enabled)
        self.ping_button.setEnabled(enabled)
        self.request_stat_button.setEnabled(enabled)
        self.reboot_soft_button.setEnabled(enabled)
        if status_text:
            self.status_label.setText(status_text)

    @Slot()
    def _on_waiting_hint_timeout(self) -> None:
        if self._active_thread is None:
            return
        self.status_label.setText(f"{self._active_command_name}: esperando ACK...")

    @Slot(object, object)
    def _on_transaction_finished(self, result_obj: object, error_obj: object) -> None:
        self._waiting_hint_timer.stop()
        self._set_busy(False)

        if error_obj is not None:
            self.status_label.setText(
                f"{self._active_command_name}: error durante transacción."
            )
            self.result_view.setPlainText(str(error_obj))
            return

        if not isinstance(result_obj, ControlTransactionResult):
            self.status_label.setText(
                f"{self._active_command_name}: error de integración (resultado inválido)."
            )
            self.result_view.setPlainText("El worker no devolvió ControlTransactionResult.")
            return

        result_view = format_control_transaction_result(result_obj)
        self.status_label.setText(result_view.headline)
        self.result_view.setPlainText(result_view.details_text)

    @Slot()
    def _on_thread_finished(self) -> None:
        self._active_thread = None
        self._active_worker = None
        self._active_command_name = ""
