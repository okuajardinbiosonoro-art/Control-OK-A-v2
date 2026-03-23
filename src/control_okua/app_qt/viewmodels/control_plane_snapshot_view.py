from __future__ import annotations

from dataclasses import dataclass


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


def build_control_plane_snapshot_view(
    *,
    node_id: int,
    snapshot: object | None,
    fallback_label: str | None = None,
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

    resolved_ip_text = _text_or_dash(_read_attr(snapshot, "resolved_ip"))
    resolution_status_raw = _normalize_resolution_status(_read_attr(snapshot, "resolution_status"))
    resolution_age_raw = _safe_float(_read_attr(snapshot, "resolution_age_s"))
    resolution_age_text = "-" if resolution_age_raw is None else f"{resolution_age_raw:.1f} s"
    is_unresolved = resolution_status_raw == "UNRESOLVED"
    is_stale = resolution_status_raw == "STALE"

    resolution_message_text = _build_resolution_message(
        node_id=resolved_node_id,
        status=resolution_status_raw,
        resolved_ip=None if resolved_ip_text == "-" else resolved_ip_text,
    )
    backend_message_text = _text_or_dash(_read_attr(snapshot, "message"))

    last_nonce = _safe_int(_read_attr(snapshot, "last_nonce"))
    ack_stage = _safe_int(_read_attr(snapshot, "last_ack_stage"))
    ack_status_code = _safe_int(_read_attr(snapshot, "last_status_code"))
    ack_err_detail = _safe_int(_read_attr(snapshot, "last_err_detail"))
    ack_message_text = _build_ack_message(
        ack_stage=ack_stage,
        status_code=ack_status_code,
        err_detail=ack_err_detail,
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
        last_command_text=_text_or_dash(_read_attr(snapshot, "last_command_name")),
        last_cmd_seq_text=_format_optional_int(_read_attr(snapshot, "last_cmd_seq")),
        last_nonce_text=_format_optional_nonce(last_nonce),
        last_final_status_text=_text_or_dash(_read_attr(snapshot, "last_final_status")),
        last_error_text=_text_or_dash(_read_attr(snapshot, "last_error_message")),
        last_tx_started_text=_text_or_dash(_read_attr(snapshot, "last_tx_started_at")),
        last_tx_finished_text=_text_or_dash(_read_attr(snapshot, "last_tx_finished_at")),
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


def _normalize_resolution_status(raw_value: object) -> str:
    text = _text_or_none(raw_value)
    if text is None:
        return "UNRESOLVED"
    normalized = text.upper()
    if normalized in {"RESOLVED", "STALE", "UNRESOLVED"}:
        return normalized
    return "UNRESOLVED"


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
) -> str:
    if ack_stage is None and status_code is None and err_detail is None:
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
