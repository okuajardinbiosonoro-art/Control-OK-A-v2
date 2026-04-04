from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.control_plane_panel import (  # noqa: E402
    ControlPlanePanel,
    _PanelRunOutcome,
)
from control_okua.services.control_transaction_service import (  # noqa: E402
    ControlTransactionFinalStatus,
    ControlTransactionResult,
)


def _ensure_qapp() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _tx_result(
    *,
    command_name: str,
    cmd_id: int,
    final_status: ControlTransactionFinalStatus,
    node_id: int = 3,
) -> ControlTransactionResult:
    return ControlTransactionResult(
        command_name=command_name,
        cmd_id=cmd_id,
        node_ip="192.168.88.248",
        node_id=node_id,
        cmd_seq=100,
        nonce=0xAABBCCDD00000003,
        attempt_count=1,
        final_status=final_status,
        ack=None,
        matched_sent_command=None,
        elapsed_ms=100.0,
        last_error=None if final_status is ControlTransactionFinalStatus.ACK_MATCHED else "timeout",
        events=tuple(),
    )


def test_reboot_probe_emits_progress_and_returns_confirmation() -> None:
    _ensure_qapp()

    ping_calls = {"count": 0}
    uptime_values = [120, 120, 18, 19, 20]

    class _Snapshot:
        def __init__(self, uptime_s: int | None) -> None:
            self.last_uptime_s = uptime_s

    def _snapshot_provider(_node_id: int) -> object | None:
        if not uptime_values:
            return _Snapshot(20)
        return _Snapshot(uptime_values.pop(0))

    def _send_ping(_node_id: int, _ack_timeout_ms: int, _max_retries: int) -> ControlTransactionResult:
        ping_calls["count"] += 1
        if ping_calls["count"] == 1:
            return _tx_result(
                command_name="PING",
                cmd_id=0x01,
                final_status=ControlTransactionFinalStatus.TIMEOUT,
            )
        return _tx_result(
            command_name="PING",
            cmd_id=0x01,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        )

    def _send_request_stat(_node_id: int, _ack_timeout_ms: int, _max_retries: int) -> ControlTransactionResult:
        return _tx_result(
            command_name="REQUEST_STAT_NOW",
            cmd_id=0x07,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        )

    def _send_reboot(_node_id: int, _ack_timeout_ms: int, _max_retries: int) -> ControlTransactionResult:
        return _tx_result(
            command_name="REBOOT_SOFT",
            cmd_id=0x02,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        )

    panel = ControlPlanePanel(
        send_ping=_send_ping,
        send_request_stat_now=_send_request_stat,
        send_reboot_soft=_send_reboot,
        send_set_stat_rate=lambda *_: _tx_result(
            command_name="SET_STAT_RATE",
            cmd_id=0x05,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        available_node_ids_provider=lambda: [3],
        node_snapshot_provider=_snapshot_provider,
        default_node_id=3,
    )

    progress_lines: list[str] = []
    try:
        outcome = panel._execute_reboot_with_probe(  # type: ignore[attr-defined]
            node_id=3,
            ack_timeout_ms=1200,
            max_retries=0,
            progress=progress_lines.append,
        )
    finally:
        panel.close()

    assert outcome.result.final_status is ControlTransactionFinalStatus.ACK_MATCHED
    assert any("ACK REBOOT_SOFT recibido" in line for line in progress_lines)
    assert any("verificación_reinicio intento=" in line for line in progress_lines)
    assert any("reinicio confirmado" in line for line in outcome.post_lines)
    assert any("verificación_reinicio_resumen:" in line for line in outcome.post_lines)


def test_reboot_probe_confirms_using_boot_marker_change() -> None:
    _ensure_qapp()

    ping_calls = {"count": 0}
    # Keep uptime stable to force confirmation by boot marker.
    snapshot_calls = {"count": 0}

    class _Snapshot:
        def __init__(self, payload: dict[str, int]) -> None:
            self.last_uptime_s = payload.get("last_uptime_s")
            self.reset_reason = payload.get("reset_reason")
            self.last_state_flags = payload.get("last_state_flags")

    def _snapshot_provider(_node_id: int) -> object | None:
        snapshot_calls["count"] += 1
        marker = 0x10 if snapshot_calls["count"] <= 12 else 0x20
        return _Snapshot({"last_uptime_s": 80, "reset_reason": 1, "last_state_flags": marker})

    def _send_ping(_node_id: int, _ack_timeout_ms: int, _max_retries: int) -> ControlTransactionResult:
        ping_calls["count"] += 1
        return _tx_result(
            command_name="PING",
            cmd_id=0x01,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        )

    def _send_request_stat(_node_id: int, _ack_timeout_ms: int, _max_retries: int) -> ControlTransactionResult:
        return _tx_result(
            command_name="REQUEST_STAT_NOW",
            cmd_id=0x07,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        )

    def _send_reboot(_node_id: int, _ack_timeout_ms: int, _max_retries: int) -> ControlTransactionResult:
        return _tx_result(
            command_name="REBOOT_SOFT",
            cmd_id=0x02,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        )

    panel = ControlPlanePanel(
        send_ping=_send_ping,
        send_request_stat_now=_send_request_stat,
        send_reboot_soft=_send_reboot,
        send_set_stat_rate=lambda *_: _tx_result(
            command_name="SET_STAT_RATE",
            cmd_id=0x05,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        available_node_ids_provider=lambda: [3],
        node_snapshot_provider=_snapshot_provider,
        default_node_id=3,
    )
    progress_lines: list[str] = []
    try:
        outcome = panel._execute_reboot_with_probe(  # type: ignore[attr-defined]
            node_id=3,
            ack_timeout_ms=1200,
            max_retries=0,
            progress=progress_lines.append,
        )
    finally:
        panel.close()

    assert outcome.result.final_status is ControlTransactionFinalStatus.ACK_MATCHED
    assert any("boot_change=1" in line for line in progress_lines)
    assert any("boot_marker_change=1" in line for line in outcome.post_lines)
    assert any("reinicio confirmado" in line for line in outcome.post_lines)


def test_reboot_transaction_writes_fallback_feedback_when_post_lines_are_empty() -> None:
    _ensure_qapp()

    panel = ControlPlanePanel(
        send_ping=lambda *_: _tx_result(
            command_name="PING",
            cmd_id=0x01,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        send_request_stat_now=lambda *_: _tx_result(
            command_name="REQUEST_STAT_NOW",
            cmd_id=0x07,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        send_reboot_soft=lambda *_: _tx_result(
            command_name="REBOOT_SOFT",
            cmd_id=0x02,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        send_set_stat_rate=lambda *_: _tx_result(
            command_name="SET_STAT_RATE",
            cmd_id=0x05,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        available_node_ids_provider=lambda: [3],
        default_node_id=3,
    )
    try:
        panel._active_command_name = "REBOOT_SOFT"
        panel._active_run_index = 9
        panel._on_transaction_finished(
            _PanelRunOutcome(
                result=_tx_result(
                    command_name="REBOOT_SOFT",
                    cmd_id=0x02,
                    final_status=ControlTransactionFinalStatus.ACK_MATCHED,
                ),
                post_lines=tuple(),
            ),
            None,
        )

        text = panel.result_view.toPlainText()
        assert "reinicio no confirmado automáticamente" in text
        assert panel.status_label.text().startswith("REBOOT_SOFT: reinicio no confirmado")
    finally:
        panel.close()


def test_section_warning_is_shown_only_once(monkeypatch) -> None:
    _ensure_qapp()
    dialog_calls = {"count": 0}

    def _fake_information(*_args, **_kwargs):
        dialog_calls["count"] += 1
        return 0

    monkeypatch.setattr(
        "control_okua.app_qt.control_plane_panel.QMessageBox.information",
        _fake_information,
    )
    panel = ControlPlanePanel(
        send_ping=lambda *_: _tx_result(
            command_name="PING",
            cmd_id=0x01,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        send_request_stat_now=lambda *_: _tx_result(
            command_name="REQUEST_STAT_NOW",
            cmd_id=0x07,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        send_reboot_soft=lambda *_: _tx_result(
            command_name="REBOOT_SOFT",
            cmd_id=0x02,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        send_set_stat_rate=lambda *_: _tx_result(
            command_name="SET_STAT_RATE",
            cmd_id=0x05,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        available_node_ids_provider=lambda: [1],
        default_node_id=1,
    )
    try:
        panel.on_section_activated()
        panel.on_section_activated()
        text = panel.result_view.toPlainText()
        assert "Aviso: Control F3 envía comandos reales" in text
        assert dialog_calls["count"] == 1
    finally:
        panel.close()


def test_section_warning_uses_notify_callback_when_available() -> None:
    _ensure_qapp()
    notifications: list[dict[str, object]] = []
    panel = ControlPlanePanel(
        send_ping=lambda *_: _tx_result(
            command_name="PING",
            cmd_id=0x01,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        send_request_stat_now=lambda *_: _tx_result(
            command_name="REQUEST_STAT_NOW",
            cmd_id=0x07,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        send_reboot_soft=lambda *_: _tx_result(
            command_name="REBOOT_SOFT",
            cmd_id=0x02,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        send_set_stat_rate=lambda *_: _tx_result(
            command_name="SET_STAT_RATE",
            cmd_id=0x05,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        available_node_ids_provider=lambda: [1],
        on_notify=lambda **payload: notifications.append(payload),
        default_node_id=1,
    )
    try:
        panel.on_section_activated()
        assert notifications
        assert notifications[-1]["title"] == "Control F3"
        assert notifications[-1]["level"] == "warning"
    finally:
        panel.close()


def test_node_selector_supports_search_filtering() -> None:
    _ensure_qapp()
    panel = ControlPlanePanel(
        send_ping=lambda *_: _tx_result(
            command_name="PING",
            cmd_id=0x01,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        send_request_stat_now=lambda *_: _tx_result(
            command_name="REQUEST_STAT_NOW",
            cmd_id=0x07,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        send_reboot_soft=lambda *_: _tx_result(
            command_name="REBOOT_SOFT",
            cmd_id=0x02,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        send_set_stat_rate=lambda *_: _tx_result(
            command_name="SET_STAT_RATE",
            cmd_id=0x05,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        available_node_ids_provider=lambda: [1, 7, 12],
        default_node_id=1,
    )
    try:
        baseline_count = panel.node_selector_combo.count()
        panel.node_search_edit.setText("12")
        assert panel.node_selector_combo.count() < baseline_count
        assert panel._selected_node_id() == 12
        assert "ID 12" in panel.node_id_label.text()

        panel.node_search_edit.setText("sin-coincidencia")
        assert panel.node_selector_combo.count() == 0
        assert panel.node_id_label.text() == "Sin coincidencias"
    finally:
        panel.close()


def test_run_transaction_logs_when_command_is_ignored() -> None:
    _ensure_qapp()
    panel = ControlPlanePanel(
        send_ping=lambda *_: _tx_result(
            command_name="PING",
            cmd_id=0x01,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        send_request_stat_now=lambda *_: _tx_result(
            command_name="REQUEST_STAT_NOW",
            cmd_id=0x07,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        send_reboot_soft=lambda *_: _tx_result(
            command_name="REBOOT_SOFT",
            cmd_id=0x02,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        send_set_stat_rate=lambda *_: _tx_result(
            command_name="SET_STAT_RATE",
            cmd_id=0x05,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        available_node_ids_provider=lambda: [1],
        default_node_id=1,
    )
    try:
        panel._active_thread = object()  # type: ignore[assignment]
        panel._on_ping_clicked()
        text = panel.result_view.toPlainText()
        assert "PING ignorado: transacción en progreso" in text
    finally:
        panel.close()


def test_reboot_click_runs_transaction_without_confirmation_dialog() -> None:
    _ensure_qapp()
    panel = ControlPlanePanel(
        send_ping=lambda *_: _tx_result(
            command_name="PING",
            cmd_id=0x01,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        send_request_stat_now=lambda *_: _tx_result(
            command_name="REQUEST_STAT_NOW",
            cmd_id=0x07,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        send_reboot_soft=lambda *_: _tx_result(
            command_name="REBOOT_SOFT",
            cmd_id=0x02,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        send_set_stat_rate=lambda *_: _tx_result(
            command_name="SET_STAT_RATE",
            cmd_id=0x05,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        available_node_ids_provider=lambda: [1],
        default_node_id=1,
    )
    captured: dict[str, str] = {}

    def _fake_run_transaction(*, command_name, execute):
        captured["command_name"] = command_name

    try:
        panel._run_transaction = _fake_run_transaction  # type: ignore[method-assign]
        panel._on_reboot_soft_clicked()
        assert captured.get("command_name") == "REBOOT_SOFT"
    finally:
        panel.close()


def test_set_stat_rate_ui_is_curated_and_dispatches_command() -> None:
    app = _ensure_qapp()
    panel = ControlPlanePanel(
        send_ping=lambda *_: _tx_result(
            command_name="PING",
            cmd_id=0x01,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        send_request_stat_now=lambda *_: _tx_result(
            command_name="REQUEST_STAT_NOW",
            cmd_id=0x07,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        send_reboot_soft=lambda *_: _tx_result(
            command_name="REBOOT_SOFT",
            cmd_id=0x02,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        send_set_stat_rate=lambda *_: _tx_result(
            command_name="SET_STAT_RATE",
            cmd_id=0x05,
            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ),
        available_node_ids_provider=lambda: [1],
        default_node_id=1,
    )
    captured: dict[str, object] = {}

    def _fake_run_transaction(*, command_name, execute):
        captured["command_name"] = command_name

    try:
        panel.resize(1200, 760)
        panel.show()
        app.processEvents()

        options = [panel.stat_rate_combo.itemData(i) for i in range(panel.stat_rate_combo.count())]
        assert options == [1000, 2000, 5000]
        throttle_options = [panel.throttle_combo.itemData(i) for i in range(panel.throttle_combo.count())]
        assert throttle_options == [25, 50, 100]
        assert panel.stat_rate_label.text() == "Cadencia STAT"
        assert panel.throttle_label.text() == "Throttle planta"
        assert panel.ping_button.isVisible()
        assert panel.request_stat_button.isVisible()
        assert panel.reboot_soft_button.isVisible()
        assert panel.stat_rate_controls_widget.isVisible()
        assert panel.set_stat_rate_button.isVisible()
        assert panel.throttle_controls_widget.isVisible()
        assert panel.set_throttle_button.isVisible()

        command_row_y = panel.ping_button.mapTo(panel, panel.ping_button.rect().topLeft()).y()
        stat_row_y = panel.stat_rate_controls_widget.mapTo(
            panel,
            panel.stat_rate_controls_widget.rect().topLeft(),
        ).y()
        throttle_row_y = panel.throttle_controls_widget.mapTo(
            panel,
            panel.throttle_controls_widget.rect().topLeft(),
        ).y()
        assert stat_row_y >= command_row_y
        assert throttle_row_y >= stat_row_y

        panel.stat_rate_combo.setCurrentIndex(2)
        panel._run_transaction = _fake_run_transaction  # type: ignore[method-assign]
        panel._on_set_stat_rate_clicked()
        assert captured.get("command_name") == "SET_STAT_RATE"
        panel.throttle_combo.setCurrentIndex(1)
        panel._on_set_throttle_clicked()
        assert captured.get("command_name") == "SET_THROTTLE"
    finally:
        panel.close()
