from __future__ import annotations

from dataclasses import dataclass

from control_okua.services.control_transaction_service import (
    ControlTransactionFinalStatus,
    ControlTransactionResult,
)

REBOOT_SOFT_CONFIRMATION_TITLE = "Confirmar reinicio suave"


@dataclass(frozen=True)
class ControlPlaneResultView:
    headline: str
    details_text: str


def format_control_transaction_result(result: ControlTransactionResult) -> ControlPlaneResultView:
    status_label = _status_label(result)
    headline = f"{result.command_name}: {status_label}"

    details: list[str] = [
        f"final_status: {result.final_status.value}",
        f"node_ip: {result.node_ip}",
        f"node_id: {result.node_id}",
        f"cmd_seq: {_format_optional_int(result.cmd_seq)}",
        f"nonce: {_format_optional_nonce(result.nonce)}",
        f"attempt_count: {result.attempt_count}",
        f"elapsed_ms: {result.elapsed_ms:.1f}",
    ]

    if result.ack is None:
        details.extend(
            [
                "ack_stage: -",
                "status_code: -",
                "err_detail: -",
            ]
        )
    else:
        details.extend(
            [
                f"ack_stage: {result.ack.ack_stage}",
                f"status_code: {result.ack.status_code}",
                f"err_detail: {result.ack.err_detail}",
            ]
        )

    if result.last_error:
        details.append(f"last_error: {result.last_error}")

    return ControlPlaneResultView(
        headline=headline,
        details_text="\n".join(details),
    )


def build_reboot_soft_confirmation_text(*, node_ip: str, node_id: int) -> str:
    return (
        "Vas a enviar REBOOT_SOFT al nodo "
        f"{int(node_id)} ({str(node_ip).strip()}).\n\n"
        "El nodo puede reiniciarse y perder conectividad temporalmente.\n"
        "Ejecuta esta acción solo si es intencional.\n\n"
        "¿Deseas continuar?"
    )


def _status_label(result: ControlTransactionResult) -> str:
    status = result.final_status
    if status is ControlTransactionFinalStatus.ACK_MATCHED:
        if result.ack is not None and result.ack.status_code != 0:
            return "ACK recibido (rechazado)"
        return "ACK recibido"

    if status is ControlTransactionFinalStatus.TIMEOUT:
        return "timeout"
    if status is ControlTransactionFinalStatus.INVALID_ACK_SEEN:
        return "ACK inválido observado"
    if status is ControlTransactionFinalStatus.UNMATCHED_ACK_SEEN:
        return "ACK huérfano observado"
    if status is ControlTransactionFinalStatus.LISTENER_NOT_RUNNING:
        return "listener ACK no disponible"
    if status is ControlTransactionFinalStatus.SEND_ERROR:
        return "error de envío"
    return status.value


def _format_optional_int(value: int | None) -> str:
    if value is None:
        return "-"
    return str(int(value))


def _format_optional_nonce(value: int | None) -> str:
    if value is None:
        return "-"
    return f"0x{int(value) & 0xFFFFFFFFFFFFFFFF:016X}"
