from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.viewmodels.control_plane_vm import (  # noqa: E402
    REBOOT_SOFT_CONFIRMATION_TITLE,
    build_reboot_soft_confirmation_text,
    format_control_transaction_result,
)
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
