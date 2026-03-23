from __future__ import annotations

from dataclasses import dataclass

from control_okua.core.control_plane.runtime_snapshot import (
    DEFAULT_CONTROL_PLANE_RESOLUTION_STALE_S,
)


@dataclass(frozen=True)
class ControlPlaneSnapshotView:
    node_id_text: str
    label_text: str
    resolved_ip_text: str
    resolution_status_text: str
    resolution_age_text: str
    resolution_message_text: str
    transaction_active_text: str
    last_command_text: str
    last_cmd_seq_text: str
    last_nonce_text: str
    last_final_status_text: str
    last_error_text: str
    last_tx_started_text: str
    last_tx_finished_text: str
    ack_stage_text: str
    ack_status_code_text: str
    ack_err_detail_text: str
    ack_message_text: str
    reboot_status_text: str
    reboot_summary_text: str
    uptime_text: str
    reset_reason_text: str
    boot_marker_text: str
    backend_message_text: str
    is_unresolved: bool
    is_stale: bool


@dataclass(frozen=True)
class _AtomicTransactionState:
    command_name: str | None = None
    cmd_seq: int | None = None
    nonce: int | None = None
    final_status: str | None = None
    error_message: str | None = None
    ack_stage: int | None = None
    ack_status_code: int | None = None
    ack_err_detail: int | None = None
    tx_started_at: str | None = None
    tx_finished_at: str | None = None


def build_control_plane_snapshot_view(
    *,
    node_id: int,
    snapshot: object | None,
    fallback_label: str | None = None,
    local_result: object | None = None,
    local_result_age_s: float | None = None,
) -> ControlPlaneSnapshotView:
    resolved_node_id = _safe_int(node_id)
    if resolved_node_id is None or resolved_node_id <= 0:
        resolved_node_id = 1

    label_text = (
        _text_or_dash(_read_attr(snapshot, "label"))
        if snapshot is not None
        else _text_or_dash(fallback_label)
    )
    if label_text == "-" and fallback_label is not None:
        label_text = _text_or_dash(fallback_label)

    resolved_ip = _text_or_none(_read_attr(snapshot, "resolved_ip"))
    resolved_ip_text = _text_or_dash(resolved_ip)
    resolution_age_raw = _safe_float(_read_attr(snapshot, "resolution_age_s"))
    resolution_status_raw = _normalize_resolution_status(
        _read_attr(snapshot, "resolution_status"),
        resolved_ip=resolved_ip,
        resolution_age_s=resolution_age_raw,
    )
    resolution_age_text = "-" if resolution_age_raw is None else f"{resolution_age_raw:.1f} s"
    is_unresolved = resolution_status_raw == "UNRESOLVED"
    is_stale = resolution_status_raw == "STALE"

    resolution_message_text = _build_resolution_message(
        node_id=resolved_node_id,
        status=resolution_status_raw,
        resolved_ip=resolved_ip,
    )
    backend_message_text = _text_or_dash(_read_attr(snapshot, "message"))

    snapshot_tx = _build_snapshot_tx_state(snapshot)
    local_tx = _build_local_tx_state(local_result)
    effective_tx = _select_effective_transaction_state(
        snapshot_tx=snapshot_tx,
        local_tx=local_tx,
        local_result_age_s=local_result_age_s,
    )
    effective_final_status = effective_tx.final_status

    last_command_text = effective_tx.command_name
    last_cmd_seq = effective_tx.cmd_seq
    last_nonce = effective_tx.nonce
    last_error_text = effective_tx.error_message
    ack_stage = effective_tx.ack_stage
    ack_status_code = effective_tx.ack_status_code
    ack_err_detail = effective_tx.ack_err_detail
    ack_message_text = _build_ack_message(
        ack_stage=ack_stage,
        status_code=ack_status_code,
        err_detail=ack_err_detail,
        final_status=effective_final_status,
    )

    reboot_summary = _text_or_none(_read_attr(snapshot, "last_reboot_verification_summary"))
    reboot_message = (
        reboot_summary
        if reboot_summary is not None
        else "Sin verificación de reinicio registrada."
    )

    return ControlPlaneSnapshotView(
        node_id_text=str(resolved_node_id),
        label_text=label_text,
        resolved_ip_text=resolved_ip_text,
        resolution_status_text=resolution_status_raw,
        resolution_age_text=resolution_age_text,
        resolution_message_text=resolution_message_text,
        transaction_active_text=_format_yes_no(_read_attr(snapshot, "transaction_active")),
        last_command_text=_text_or_dash(last_command_text),
        last_cmd_seq_text=_format_optional_int(last_cmd_seq),
        last_nonce_text=_format_optional_nonce(last_nonce),
        last_final_status_text=_text_or_dash(effective_final_status),
        last_error_text=_text_or_dash(last_error_text),
        last_tx_started_text=_text_or_dash(effective_tx.tx_started_at),
        last_tx_finished_text=_text_or_dash(effective_tx.tx_finished_at),
        ack_stage_text=_format_optional_int(ack_stage),
        ack_status_code_text=_format_optional_int(ack_status_code),
        ack_err_detail_text=_format_optional_int(ack_err_detail),
        ack_message_text=ack_message_text,
        reboot_status_text=_text_or_dash(_read_attr(snapshot, "last_reboot_verification_status")),
        reboot_summary_text=reboot_message,
        uptime_text=_format_optional_int(_read_attr(snapshot, "last_uptime_s")),
        reset_reason_text=_format_optional_int(_read_attr(snapshot, "last_reset_reason")),
        boot_marker_text=_format_optional_int(_read_attr(snapshot, "last_boot_marker")),
        backend_message_text=backend_message_text,
        is_unresolved=is_unresolved,
        is_stale=is_stale,
    )


def _read_attr(snapshot: object | None, attr_name: str) -> object:
    if snapshot is None:
        return None
    return getattr(snapshot, attr_name, None)


def _normalize_resolution_status(
    raw_value: object,
    *,
    resolved_ip: str | None,
    resolution_age_s: float | None,
) -> str:
    text = _enum_or_text(raw_value)
    if text is None:
        return _infer_resolution_status_from_ip(
            resolved_ip=resolved_ip,
            resolution_age_s=resolution_age_s,
        )
    normalized = text.strip().upper()
    if "." in normalized:
        normalized = normalized.rsplit(".", 1)[-1]
    if normalized in {"RESOLVED", "STALE", "UNRESOLVED"}:
        return normalized
    return _infer_resolution_status_from_ip(
        resolved_ip=resolved_ip,
        resolution_age_s=resolution_age_s,
    )


def _infer_resolution_status_from_ip(
    *,
    resolved_ip: str | None,
    resolution_age_s: float | None,
) -> str:
    if resolved_ip is None:
        return "UNRESOLVED"
    if (
        resolution_age_s is not None
        and resolution_age_s > float(DEFAULT_CONTROL_PLANE_RESOLUTION_STALE_S)
    ):
        return "STALE"
    return "RESOLVED"


def _build_snapshot_tx_state(snapshot: object | None) -> _AtomicTransactionState:
    return _AtomicTransactionState(
        command_name=_text_or_none(_read_attr(snapshot, "last_command_name")),
        cmd_seq=_safe_int(_read_attr(snapshot, "last_cmd_seq")),
        nonce=_safe_int(_read_attr(snapshot, "last_nonce")),
        final_status=_normalize_final_status(_read_attr(snapshot, "last_final_status")),
        error_message=_text_or_none(_read_attr(snapshot, "last_error_message")),
        ack_stage=_safe_int(_read_attr(snapshot, "last_ack_stage")),
        ack_status_code=_safe_int(_read_attr(snapshot, "last_status_code")),
        ack_err_detail=_safe_int(_read_attr(snapshot, "last_err_detail")),
        tx_started_at=_text_or_none(_read_attr(snapshot, "last_tx_started_at")),
        tx_finished_at=_text_or_none(_read_attr(snapshot, "last_tx_finished_at")),
    )


def _build_local_tx_state(local_result: object | None) -> _AtomicTransactionState:
    local_ack = _read_attr(local_result, "ack")
    return _AtomicTransactionState(
        command_name=_text_or_none(_read_attr(local_result, "command_name")),
        cmd_seq=_safe_int(_read_attr(local_result, "cmd_seq")),
        nonce=_safe_int(_read_attr(local_result, "nonce")),
        final_status=_normalize_final_status(_read_local_final_status(local_result)),
        error_message=_text_or_none(_read_attr(local_result, "last_error")),
        ack_stage=_safe_int(_read_attr(local_ack, "ack_stage")),
        ack_status_code=_safe_int(_read_attr(local_ack, "status_code")),
        ack_err_detail=_safe_int(_read_attr(local_ack, "err_detail")),
        tx_started_at=None,
        tx_finished_at=None,
    )


def _select_effective_transaction_state(
    *,
    snapshot_tx: _AtomicTransactionState,
    local_tx: _AtomicTransactionState,
    local_result_age_s: float | None,
) -> _AtomicTransactionState:
    normalized_snapshot = _normalize_transaction_state(snapshot_tx)
    normalized_local = _normalize_transaction_state(local_tx)

    if normalized_local.final_status is None:
        return normalized_snapshot

    local_age = _safe_float(local_result_age_s)
    if local_age is not None and local_age > 3.0:
        return normalized_snapshot

    if normalized_snapshot.final_status is None:
        return normalized_local

    snapshot_seq = normalized_snapshot.cmd_seq
    local_seq = normalized_local.cmd_seq
    if snapshot_seq is not None and local_seq is not None:
        if snapshot_seq != local_seq:
            if _is_cmd_seq_newer(local_seq, snapshot_seq):
                return normalized_local
            return normalized_snapshot
        if _state_completeness_score(normalized_local) > _state_completeness_score(normalized_snapshot):
            return normalized_local
        return normalized_snapshot

    if snapshot_seq is None and local_seq is not None:
        if _state_completeness_score(normalized_local) > _state_completeness_score(normalized_snapshot):
            return normalized_local
        return normalized_snapshot

    if snapshot_seq is not None and local_seq is None:
        return normalized_snapshot

    if local_age is not None and local_age <= 3.0:
        if normalized_snapshot.final_status != normalized_local.final_status:
            return normalized_local

    return normalized_snapshot


def _normalize_transaction_state(state: _AtomicTransactionState) -> _AtomicTransactionState:
    final_status = _normalize_final_status(state.final_status)
    error = _text_or_none(state.error_message)
    ack_stage = state.ack_stage
    ack_status_code = state.ack_status_code
    ack_err_detail = state.ack_err_detail

    if final_status == "ack_matched":
        if _looks_like_timeout_error(error):
            error = None
    elif final_status == "timeout":
        ack_stage = None
        ack_status_code = None
        ack_err_detail = None
        if error is None:
            error = "Timeout esperando ACK."

    return _AtomicTransactionState(
        command_name=state.command_name,
        cmd_seq=state.cmd_seq,
        nonce=state.nonce,
        final_status=final_status,
        error_message=error,
        ack_stage=ack_stage,
        ack_status_code=ack_status_code,
        ack_err_detail=ack_err_detail,
        tx_started_at=state.tx_started_at,
        tx_finished_at=state.tx_finished_at,
    )


def _state_completeness_score(state: _AtomicTransactionState) -> int:
    score = 0
    if state.command_name is not None:
        score += 1
    if state.cmd_seq is not None:
        score += 1
    if state.nonce is not None:
        score += 1
    if state.final_status is not None:
        score += 2
    if state.error_message is not None:
        score += 1
    if _tx_has_ack(state):
        score += 3
    if state.tx_finished_at is not None:
        score += 1
    return score


def _tx_has_ack(state: _AtomicTransactionState) -> bool:
    return (
        state.ack_stage is not None
        or state.ack_status_code is not None
        or state.ack_err_detail is not None
    )


def _is_cmd_seq_newer(candidate: int, reference: int) -> bool:
    left = int(candidate) & 0xFFFF
    right = int(reference) & 0xFFFF
    diff = (left - right) & 0xFFFF
    return 0 < diff < 0x8000


def _looks_like_timeout_error(raw_error: str | None) -> bool:
    text = _text_or_none(raw_error)
    if text is None:
        return False
    lowered = text.lower()
    return "timeout" in lowered


def _build_resolution_message(
    *,
    node_id: int,
    status: str,
    resolved_ip: str | None,
) -> str:
    if status == "RESOLVED":
        if resolved_ip is not None:
            return f"Nodo {node_id} resuelto a {resolved_ip}."
        return f"Nodo {node_id} resuelto en runtime."
    if status == "STALE":
        return f"Nodo {node_id} resuelto, pero sin actividad reciente."
    return f"Nodo {node_id} no resoluble todavía; primero debe emitir EVT/STAT."


def _build_ack_message(
    *,
    ack_stage: int | None,
    status_code: int | None,
    err_detail: int | None,
    final_status: str | None,
) -> str:
    if ack_stage is None and status_code is None and err_detail is None:
        normalized_final = _normalize_final_status(final_status)
        if normalized_final == "ack_matched":
            return "ACK correlacionado (sin detalle stage/status_code/err_detail)."
        return "Sin ACK registrado."
    return (
        "ACK registrado: "
        f"stage={_format_optional_int(ack_stage)}, "
        f"status_code={_format_optional_int(status_code)}, "
        f"err_detail={_format_optional_int(err_detail)}"
    )


def _format_yes_no(raw_value: object) -> str:
    if bool(raw_value):
        return "sí"
    return "no"


def _format_optional_int(raw_value: object) -> str:
    parsed = _safe_int(raw_value)
    if parsed is None:
        return "-"
    return str(parsed)


def _format_optional_nonce(raw_value: int | None) -> str:
    if raw_value is None:
        return "-"
    return f"0x{int(raw_value) & 0xFFFFFFFFFFFFFFFF:016X}"


def _safe_int(raw_value: object) -> int | None:
    if raw_value is None:
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _safe_float(raw_value: object) -> float | None:
    if raw_value is None:
        return None
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return None


def _enum_or_text(raw_value: object) -> str | None:
    if raw_value is None:
        return None
    enum_value = getattr(raw_value, "value", None)
    text = _text_or_none(enum_value)
    if text is not None:
        return text
    return _text_or_none(raw_value)


def _normalize_final_status(raw_value: object) -> str | None:
    text = _enum_or_text(raw_value)
    if text is None:
        return None
    return text.strip().lower()


def _read_local_final_status(local_result: object | None) -> object:
    if local_result is None:
        return None
    final_status = _read_attr(local_result, "final_status")
    if final_status is None:
        return None
    enum_value = getattr(final_status, "value", None)
    if enum_value is not None:
        return enum_value
    return final_status


def _text_or_none(raw_value: object) -> str | None:
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    if not text:
        return None
    return text


def _text_or_dash(raw_value: object) -> str:
    text = _text_or_none(raw_value)
    if text is None:
        return "-"
    return text
