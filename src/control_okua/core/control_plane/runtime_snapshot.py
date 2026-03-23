from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from control_okua.core.node_identity_policy import resolve_node_identity

DEFAULT_CONTROL_PLANE_RESOLUTION_STALE_S = 8.0


class ControlPlaneNodeResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    STALE = "stale"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class ControlPlaneResolvedIp:
    node_id: int
    ip: str
    observed_at_monotonic: float | None = None


@dataclass(frozen=True)
class ControlPlaneRebootVerificationState:
    status: str
    summary: str
    updated_at_utc: str | None = None


@dataclass(frozen=True)
class ControlPlaneNodeSnapshotInput:
    node_id: int
    label: str | None = None
    resolved_ip: str | None = None
    resolution_observed_at_monotonic: float | None = None
    last_seen_pc_ts: float | None = None
    transaction_active: bool = False
    last_command_name: str | None = None
    last_cmd_seq: int | None = None
    last_nonce: int | None = None
    last_final_status: str | None = None
    last_ack_stage: int | None = None
    last_status_code: int | None = None
    last_err_detail: int | None = None
    last_error_message: str | None = None
    last_tx_started_at: str | None = None
    last_tx_finished_at: str | None = None
    last_reboot_verification_status: str | None = None
    last_reboot_verification_summary: str | None = None
    last_uptime_s: int | None = None
    last_reset_reason: int | None = None
    last_boot_marker: int | None = None
    message: str | None = None


@dataclass(frozen=True)
class ControlPlaneNodeSnapshot:
    node_id: int
    label: str
    resolved_ip: str | None
    resolution_status: ControlPlaneNodeResolutionStatus
    resolution_age_s: float | None
    last_seen_pc_ts: float | None
    transaction_active: bool
    last_command_name: str | None
    last_cmd_seq: int | None
    last_nonce: int | None
    last_final_status: str | None
    last_ack_stage: int | None
    last_status_code: int | None
    last_err_detail: int | None
    last_error_message: str | None
    last_tx_started_at: str | None
    last_tx_finished_at: str | None
    last_reboot_verification_status: str | None
    last_reboot_verification_summary: str | None
    last_uptime_s: int | None
    last_reset_reason: int | None
    last_boot_marker: int | None
    message: str


def build_control_plane_node_snapshot(
    source: ControlPlaneNodeSnapshotInput,
    *,
    now_monotonic: float,
    resolution_stale_after_s: float = DEFAULT_CONTROL_PLANE_RESOLUTION_STALE_S,
) -> ControlPlaneNodeSnapshot:
    node_id = _normalize_node_id(source.node_id)
    label = _normalize_label(source.label, node_id=node_id)
    resolved_ip = _normalize_text(source.resolved_ip)
    resolution_age_s = _compute_resolution_age_s(
        now_monotonic=now_monotonic,
        observed_at_monotonic=source.resolution_observed_at_monotonic,
        resolved_ip=resolved_ip,
    )
    resolution_status = _resolve_resolution_status(
        resolved_ip=resolved_ip,
        resolution_age_s=resolution_age_s,
        resolution_stale_after_s=resolution_stale_after_s,
    )
    message = _resolve_message(
        explicit_message=source.message,
        resolution_status=resolution_status,
        resolution_age_s=resolution_age_s,
        transaction_active=source.transaction_active,
        last_error_message=source.last_error_message,
        reboot_summary=source.last_reboot_verification_summary,
        final_status=source.last_final_status,
    )
    return ControlPlaneNodeSnapshot(
        node_id=node_id,
        label=label,
        resolved_ip=resolved_ip,
        resolution_status=resolution_status,
        resolution_age_s=resolution_age_s,
        last_seen_pc_ts=_coerce_float(source.last_seen_pc_ts),
        transaction_active=bool(source.transaction_active),
        last_command_name=_normalize_text(source.last_command_name),
        last_cmd_seq=_coerce_int(source.last_cmd_seq),
        last_nonce=_coerce_int(source.last_nonce),
        last_final_status=_normalize_text(source.last_final_status),
        last_ack_stage=_coerce_int(source.last_ack_stage),
        last_status_code=_coerce_int(source.last_status_code),
        last_err_detail=_coerce_int(source.last_err_detail),
        last_error_message=_normalize_text(source.last_error_message),
        last_tx_started_at=_normalize_text(source.last_tx_started_at),
        last_tx_finished_at=_normalize_text(source.last_tx_finished_at),
        last_reboot_verification_status=_normalize_text(source.last_reboot_verification_status),
        last_reboot_verification_summary=_normalize_text(source.last_reboot_verification_summary),
        last_uptime_s=_coerce_int(source.last_uptime_s),
        last_reset_reason=_coerce_int(source.last_reset_reason),
        last_boot_marker=_coerce_int(source.last_boot_marker),
        message=message,
    )


def build_control_plane_node_snapshots(
    sources: Iterable[ControlPlaneNodeSnapshotInput],
    *,
    now_monotonic: float,
    resolution_stale_after_s: float = DEFAULT_CONTROL_PLANE_RESOLUTION_STALE_S,
) -> tuple[ControlPlaneNodeSnapshot, ...]:
    snapshots = [
        build_control_plane_node_snapshot(
            source,
            now_monotonic=now_monotonic,
            resolution_stale_after_s=resolution_stale_after_s,
        )
        for source in sources
    ]
    snapshots.sort(key=lambda item: item.node_id)
    return tuple(snapshots)


def _normalize_node_id(raw_value: int) -> int:
    value = int(raw_value)
    if value <= 0:
        raise ValueError(f"node_id invalido para snapshot canonico: {raw_value!r}")
    return value


def _normalize_label(label: str | None, *, node_id: int) -> str:
    text = _normalize_text(label)
    if text:
        return text
    return resolve_node_identity(node_id).node_label


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _coerce_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compute_resolution_age_s(
    *,
    now_monotonic: float,
    observed_at_monotonic: float | None,
    resolved_ip: str | None,
) -> float | None:
    if resolved_ip is None:
        return None
    observed = _coerce_float(observed_at_monotonic)
    if observed is None:
        return None
    return max(0.0, float(now_monotonic) - observed)


def _resolve_resolution_status(
    *,
    resolved_ip: str | None,
    resolution_age_s: float | None,
    resolution_stale_after_s: float,
) -> ControlPlaneNodeResolutionStatus:
    if resolved_ip is None:
        return ControlPlaneNodeResolutionStatus.UNRESOLVED
    stale_after = float(resolution_stale_after_s)
    if stale_after <= 0:
        stale_after = DEFAULT_CONTROL_PLANE_RESOLUTION_STALE_S
    if resolution_age_s is not None and resolution_age_s > stale_after:
        return ControlPlaneNodeResolutionStatus.STALE
    return ControlPlaneNodeResolutionStatus.RESOLVED


def _resolve_message(
    *,
    explicit_message: str | None,
    resolution_status: ControlPlaneNodeResolutionStatus,
    resolution_age_s: float | None,
    transaction_active: bool,
    last_error_message: str | None,
    reboot_summary: str | None,
    final_status: str | None,
) -> str:
    explicit = _normalize_text(explicit_message)
    if explicit:
        return explicit
    if transaction_active:
        return "Transaccion de control-plane en progreso."
    if last_error_message:
        return last_error_message
    if reboot_summary:
        return reboot_summary
    if resolution_status is ControlPlaneNodeResolutionStatus.UNRESOLVED:
        return "Sin IP resuelta en runtime."
    if resolution_status is ControlPlaneNodeResolutionStatus.STALE:
        if resolution_age_s is None:
            return "IP resuelta en runtime, pero stale."
        return f"IP resuelta en runtime, pero stale (edad={resolution_age_s:.1f}s)."
    if final_status:
        return f"Ultimo resultado de control-plane: {final_status}."
    return "Nodo listo para control-plane."
