from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.viewmodels.control_plane_vm import (  # noqa: E402
    REBOOT_SOFT_CONFIRMATION_TITLE,
    build_control_plane_node_options,
    build_reboot_soft_confirmation_text,
    format_control_transaction_event_lines,
    format_control_transaction_result,
    resolve_control_command_policy,
)
from control_okua.core.control_plane.audit import build_control_audit_event  # noqa: E402
from control_okua.core.control_plane.protocol import ParsedOkuaAck  # noqa: E402
from control_okua.services.control_transaction_service import (  # noqa: E402
    ControlTransactionFinalStatus,
    ControlTransactionResult,
)


def _build_result(
    *,
    final_status: ControlTransactionFinalStatus,
    ack: ParsedOkuaAck | None,
    last_error: str | None = None,
) -> ControlTransactionResult:
    return ControlTransactionResult(
        command_name="PING",
        cmd_id=0x01,
        node_ip="192.168.1.40",
        node_id=12,
        cmd_seq=77,
        nonce=0x1122334400000001,
        attempt_count=2,
        final_status=final_status,
        ack=ack,
        matched_sent_command=None,
        elapsed_ms=123.4,
        last_error=last_error,
        events=tuple(),
    )


def test_format_control_transaction_result_ack_matched() -> None:
    ack = ParsedOkuaAck(
        node_id_source=12,
        cmd_seq=77,
        cmd_id_echo=0x01,
        nonce_echo=0x1122334400000001,
        ack_stage=1,
        status_code=0,
        ack_flags=0,
        err_detail=0,
        retry_after_ms=0,
        auth_tag32=0x12345678,
    )
    result = _build_result(
        final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ack=ack,
    )

    view = format_control_transaction_result(result)

    assert "ACK recibido" in view.headline
    assert "final_status: ack_matched" in view.details_text
    assert "cmd_seq: 77" in view.details_text
    assert "nonce: 0x1122334400000001" in view.details_text


def test_format_control_transaction_result_timeout() -> None:
    result = _build_result(
        final_status=ControlTransactionFinalStatus.TIMEOUT,
        ack=None,
        last_error="Timeout esperando ACK.",
    )

    view = format_control_transaction_result(result)

    assert "timeout" in view.headline.lower()
    assert "final_status: timeout" in view.details_text
    assert "ack_stage: -" in view.details_text
    assert "last_error: Timeout esperando ACK." in view.details_text


def test_format_control_transaction_result_includes_ack_details_when_present() -> None:
    ack = ParsedOkuaAck(
        node_id_source=12,
        cmd_seq=77,
        cmd_id_echo=0x01,
        nonce_echo=0x1122334400000001,
        ack_stage=2,
        status_code=9,
        ack_flags=0,
        err_detail=44,
        retry_after_ms=0,
        auth_tag32=0xAABBCCDD,
    )
    result = _build_result(
        final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ack=ack,
    )

    view = format_control_transaction_result(result)

    assert "ACK recibido (rechazado)" in view.headline
    assert "ack_stage: 2" in view.details_text
    assert "status_code: 9" in view.details_text
    assert "err_detail: 44" in view.details_text


def test_reboot_soft_confirmation_text_is_explicit() -> None:
    text = build_reboot_soft_confirmation_text(
        node_ip="10.0.0.8",
        node_id=35,
    )

    assert REBOOT_SOFT_CONFIRMATION_TITLE == "Confirmar reinicio suave"
    assert "REBOOT_SOFT" in text
    assert "10.0.0.8" in text
    assert "35" in text
    assert "perder conectividad temporalmente" in text


def test_resolve_control_command_policy_returns_auto_values() -> None:
    ping = resolve_control_command_policy("PING")
    stat = resolve_control_command_policy("REQUEST_STAT_NOW")
    throttle = resolve_control_command_policy("SET_THROTTLE")
    stat_rate = resolve_control_command_policy("SET_STAT_RATE")
    reboot = resolve_control_command_policy("REBOOT_SOFT")
    unknown = resolve_control_command_policy("X_UNKNOWN")

    assert (ping.ack_timeout_ms, ping.max_retries) == (600, 2)
    assert (stat.ack_timeout_ms, stat.max_retries) == (900, 2)
    assert (throttle.ack_timeout_ms, throttle.max_retries) == (900, 1)
    assert (stat_rate.ack_timeout_ms, stat_rate.max_retries) == (900, 1)
    assert (reboot.ack_timeout_ms, reboot.max_retries) == (1200, 0)
    assert (unknown.ack_timeout_ms, unknown.max_retries) == (600, 1)


def test_build_control_plane_node_options_includes_mapping_and_detected_flags() -> None:
    options = build_control_plane_node_options([1, 3, 10], max_boxes=5)

    by_id = {item.node_id: item for item in options}
    assert by_id[1].node_label == "EB1"
    assert by_id[2].node_label == "EC1"
    assert by_id[3].node_label == "ED1"
    assert by_id[10].node_label == "EF2"
    assert by_id[1].is_available is True
    assert by_id[2].is_available is False
    assert "detectado" in by_id[1].display_text
    assert "no detectado" in by_id[2].display_text


def test_format_control_transaction_event_lines_keeps_retries_visible() -> None:
    result = ControlTransactionResult(
        command_name="PING",
        cmd_id=0x01,
        node_ip="192.168.88.252",
        node_id=1,
        cmd_seq=100,
        nonce=0xAABBCCDD00000001,
        attempt_count=2,
        final_status=ControlTransactionFinalStatus.TIMEOUT,
        ack=None,
        matched_sent_command=None,
        elapsed_ms=1200.0,
        last_error="Timeout final",
        events=(
            build_control_audit_event(
                event_type="command_sent",
                command_name="PING",
                cmd_id=0x01,
                node_ip="192.168.88.252",
                node_id=1,
                cmd_seq=100,
                nonce=0xAABBCCDD00000001,
                attempt_index=1,
            ),
            build_control_audit_event(
                event_type="command_retry",
                command_name="PING",
                cmd_id=0x01,
                node_ip="192.168.88.252",
                node_id=1,
                cmd_seq=100,
                nonce=0xAABBCCDD00000001,
                attempt_index=2,
            ),
        ),
    )

    lines = format_control_transaction_event_lines(result)
    assert len(lines) == 2
    assert "command_sent" in lines[0]
    assert "attempt=1" in lines[0]
    assert "command_retry" in lines[1]
    assert "attempt=2" in lines[1]
