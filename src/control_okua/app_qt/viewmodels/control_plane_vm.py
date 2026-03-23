from __future__ import annotations

from dataclasses import dataclass

from control_okua.core.node_identity_policy import resolve_node_identity
from control_okua.services.control_transaction_service import (
    ControlTransactionFinalStatus,
    ControlTransactionResult,
)

REBOOT_SOFT_CONFIRMATION_TITLE = "Confirmar reinicio suave"


@dataclass(frozen=True)
class ControlPlaneResultView:
    headline: str
    details_text: str


@dataclass(frozen=True)
class ControlCommandPolicy:
    ack_timeout_ms: int
    max_retries: int


@dataclass(frozen=True)
class ControlPlaneNodeOption:
    node_id: int
    node_label: str
    is_available: bool
    display_text: str


_DEFAULT_POLICY = ControlCommandPolicy(ack_timeout_ms=600, max_retries=1)
_AUTO_POLICIES: dict[str, ControlCommandPolicy] = {
    "PING": ControlCommandPolicy(ack_timeout_ms=600, max_retries=2),
    "REQUEST_STAT_NOW": ControlCommandPolicy(ack_timeout_ms=900, max_retries=2),
    "REBOOT_SOFT": ControlCommandPolicy(ack_timeout_ms=1200, max_retries=0),
}


def resolve_control_command_policy(command_name: str) -> ControlCommandPolicy:
    return _AUTO_POLICIES.get(str(command_name).strip().upper(), _DEFAULT_POLICY)


def build_control_plane_node_options(
    available_node_ids: list[int] | tuple[int, ...] | set[int] | None,
    *,
    max_boxes: int = 5,
) -> tuple[ControlPlaneNodeOption, ...]:
    available_ids: set[int] = set()
    if available_node_ids is not None:
        for raw in available_node_ids:
            try:
                value = int(raw)
            except (TypeError, ValueError):
                continue
            if value > 0:
                available_ids.add(value)

    canonical_max = max(1, int(max_boxes)) * 5
    base_ids = set(range(1, canonical_max + 1))
    all_ids = sorted(base_ids | available_ids)

    options: list[ControlPlaneNodeOption] = []
    for node_id in all_ids:
        identity = resolve_node_identity(node_id)
        available = node_id in available_ids
        suffix = "detectado" if available else "no detectado"
        options.append(
            ControlPlaneNodeOption(
                node_id=node_id,
                node_label=identity.node_label,
                is_available=available,
                display_text=f"{identity.node_label} (id={node_id}) - {suffix}",
            )
        )

    return tuple(options)


def format_control_transaction_event_lines(result: ControlTransactionResult) -> tuple[str, ...]:
    lines: list[str] = []
    for event in result.events:
        bits: list[str] = [
            str(event.ts_utc),
            str(event.event_type),
            f"attempt={event.attempt_index}",
        ]
        if event.ack_stage is not None:
            bits.append(f"ack_stage={event.ack_stage}")
        if event.status_code is not None:
            bits.append(f"status_code={event.status_code}")
        if event.err_detail is not None:
            bits.append(f"err_detail={event.err_detail}")
        if event.detail:
            bits.append(f"detail={event.detail}")
        lines.append(" | ".join(bits))
    return tuple(lines)


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
