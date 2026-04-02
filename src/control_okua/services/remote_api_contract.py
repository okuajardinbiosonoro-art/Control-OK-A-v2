from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from control_okua.core.control_plane.runtime import ControlPlaneRuntimeSnapshot
from control_okua.core.control_plane.runtime_snapshot import ControlPlaneNodeSnapshot
from control_okua.core.node_identity_policy import resolve_node_identity
from control_okua.core.registry.node_models import NodeRegistrySummary, NodeSnapshot
from control_okua.core.session import SessionSnapshot
from control_okua.services.control_transaction_service import ControlTransactionResult


@dataclass(frozen=True)
class RemoteApiTokenInventoryEntry:
    env_var: str
    role: str
    label: str | None = None


@dataclass(frozen=True)
class RemoteApiConfig:
    enabled: bool = False
    exposure_mode: str = "local_only"
    bind_host: str = "127.0.0.1"
    port: int = 8788
    auth_mode: str = "human_session_only"
    token_env_var: str = "CKV2_REMOTE_API_TOKEN"
    tokens: tuple[RemoteApiTokenInventoryEntry, ...] = ()
    audit_enabled: bool = True
    audit_folder: str = "logs/remote_api"
    user_store_filename: str = "remote_api_users.json"
    session_ttl_s: int = 43200


class RemoteApiError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int,
        action: str,
        node_id: int | None = None,
        result: str | None = None,
        correlation_cmd_seq: int | None = None,
        correlation_nonce: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = int(status_code)
        self.action = action
        self.node_id = node_id
        self.result = result or code
        self.correlation_cmd_seq = correlation_cmd_seq
        self.correlation_nonce = correlation_nonce


def resolve_remote_api_config(cfg: dict[str, Any]) -> RemoteApiConfig:
    raw = cfg.get("remote_api")
    if not isinstance(raw, dict):
        return RemoteApiConfig()
    bind_host = raw.get("bind_host")
    exposure_mode = raw.get("exposure_mode")
    auth_mode = raw.get("auth_mode")
    token_env_var = raw.get("token_env_var")
    audit_folder = raw.get("audit_folder")
    user_store_filename = raw.get("user_store_filename")
    tokens = _coerce_token_inventory(raw.get("tokens"))
    return RemoteApiConfig(
        enabled=bool(raw.get("enabled") is True),
        exposure_mode=_coerce_exposure_mode(exposure_mode, bind_host),
        bind_host=bind_host.strip() if isinstance(bind_host, str) and bind_host.strip() else "127.0.0.1",
        port=_coerce_port(raw.get("port"), fallback=8788),
        auth_mode=_coerce_auth_mode(auth_mode),
        token_env_var=(
            token_env_var.strip()
            if isinstance(token_env_var, str) and token_env_var.strip()
            else "CKV2_REMOTE_API_TOKEN"
        ),
        tokens=tokens,
        audit_enabled=bool(raw.get("audit_enabled", True) is True),
        audit_folder=(
            audit_folder.strip()
            if isinstance(audit_folder, str) and audit_folder.strip()
            else "logs/remote_api"
        ),
        user_store_filename=(
            user_store_filename.strip()
            if isinstance(user_store_filename, str) and user_store_filename.strip()
            else "remote_api_users.json"
        ),
        session_ttl_s=_coerce_positive_int(raw.get("session_ttl_s"), fallback=43200),
    )


def build_success_response(*, data: Any, request_id: str) -> dict[str, Any]:
    return {
        "ok": True,
        "data": data,
        "meta": {
            "request_id": str(request_id),
            "api_version": "v1",
        },
    }


def build_error_response(*, code: str, message: str, request_id: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": str(code),
            "message": str(message),
        },
        "meta": {
            "request_id": str(request_id),
            "api_version": "v1",
        },
    }


def serialize_session_snapshot(snapshot: SessionSnapshot) -> dict[str, Any]:
    return {
        "state": _enum_value(getattr(snapshot, "state", None)),
        "profile_id": getattr(snapshot, "active_profile", None),
        "mode": getattr(snapshot, "mode", None),
        "backend_kind": _enum_value(getattr(snapshot, "backend", None)),
        "message": getattr(snapshot, "message", ""),
    }


def serialize_control_plane_summary(snapshot: ControlPlaneRuntimeSnapshot) -> dict[str, Any]:
    return {
        "available": bool(getattr(snapshot, "is_available", False)),
        "listener_active": bool(getattr(snapshot, "listener_active", False)),
        "ack_port": _coerce_int(getattr(snapshot, "ack_port", None)),
        "pending_count": _coerce_int(getattr(snapshot, "pending_count", None), default=0),
        "commands_sent_total": _coerce_int(getattr(snapshot, "commands_sent_total", None), default=0),
        "command_retry_total": _coerce_int(getattr(snapshot, "command_retry_total", None), default=0),
        "command_ack_total": _coerce_int(getattr(snapshot, "command_ack_total", None), default=0),
        "command_timeout_total": _coerce_int(getattr(snapshot, "command_timeout_total", None), default=0),
        "invalid_ack_total": _coerce_int(getattr(snapshot, "invalid_ack_total", None), default=0),
        "unmatched_ack_total": _coerce_int(getattr(snapshot, "unmatched_ack_total", None), default=0),
    }


def serialize_node_registry_summary(summary: NodeRegistrySummary | None) -> dict[str, Any] | None:
    if summary is None:
        return None
    return {
        "total_nodes": int(summary.total_nodes),
        "online_count": int(summary.online_count),
        "degraded_count": int(summary.degraded_count),
        "offline_count": int(summary.offline_count),
        "calibrating_count": int(summary.calibrating_count),
        "total_pps_evt": float(summary.total_pps_evt),
        "total_pps_stat": float(summary.total_pps_stat),
    }


def serialize_node_summary(
    snapshot: NodeSnapshot,
    *,
    control_plane_snapshot: ControlPlaneNodeSnapshot | None,
) -> dict[str, Any]:
    identity = resolve_node_identity(getattr(snapshot, "node_id", None))
    return {
        "node_id": int(snapshot.node_id),
        "label": identity.node_label,
        "box_label": identity.box_label,
        "status": _enum_value(getattr(snapshot, "status", None)),
        "health_summary": getattr(snapshot, "health_summary", ""),
        "last_seen_age_s": _coerce_float(getattr(snapshot, "last_seen_age_s", None)),
        "last_stat_age_s": _coerce_float(getattr(snapshot, "last_stat_age_s", None)),
        "pps_evt": float(snapshot.pps_evt),
        "pps_stat": float(snapshot.pps_stat),
        "loss_evt_pct": float(snapshot.loss_evt_pct),
        "loss_stat_pct": float(snapshot.loss_stat_pct),
        "rssi_dbm": _coerce_int(getattr(snapshot, "rssi_dbm", None)),
        "last_uptime_s": _coerce_int(getattr(snapshot, "last_uptime_s", None)),
        "fw_version": _format_fw_version(snapshot),
        "ota": {
            "state_key": getattr(snapshot, "ota_state_key", "idle"),
            "error_key": getattr(snapshot, "ota_error_key", "none"),
            "pending_reboot": bool(getattr(snapshot, "ota_pending_reboot", False)),
            "pending_verify": bool(getattr(snapshot, "ota_pending_verify", False)),
            "health_confirmed": bool(getattr(snapshot, "ota_health_confirmed", False)),
        },
        "control_plane": serialize_control_plane_node_brief(control_plane_snapshot),
    }


def serialize_node_detail(
    snapshot: NodeSnapshot,
    *,
    control_plane_snapshot: ControlPlaneNodeSnapshot | None,
) -> dict[str, Any]:
    identity = resolve_node_identity(getattr(snapshot, "node_id", None))
    return {
        "node_id": int(snapshot.node_id),
        "label": identity.node_label,
        "box_label": identity.box_label,
        "runtime": {
            "status": _enum_value(getattr(snapshot, "status", None)),
            "health_summary": getattr(snapshot, "health_summary", ""),
            "status_reason": getattr(snapshot, "status_reason", ""),
            "last_seen_age_s": _coerce_float(getattr(snapshot, "last_seen_age_s", None)),
            "last_stat_age_s": _coerce_float(getattr(snapshot, "last_stat_age_s", None)),
            "status_age_s": _coerce_float(getattr(snapshot, "status_age_s", None)),
            "pps_evt": float(snapshot.pps_evt),
            "pps_stat": float(snapshot.pps_stat),
            "loss_evt_pct": float(snapshot.loss_evt_pct),
            "loss_stat_pct": float(snapshot.loss_stat_pct),
            "rssi_dbm": _coerce_int(getattr(snapshot, "rssi_dbm", None)),
            "vbat_mv": _coerce_int(getattr(snapshot, "vbat_mv", None)),
            "free_heap": _coerce_int(getattr(snapshot, "free_heap", None)),
            "last_uptime_s": _coerce_int(getattr(snapshot, "last_uptime_s", None)),
            "reset_reason": _coerce_int(getattr(snapshot, "reset_reason", None)),
            "fw_major": _coerce_int(getattr(snapshot, "fw_major", None)),
            "fw_minor": _coerce_int(getattr(snapshot, "fw_minor", None)),
        },
        "ota": {
            "state_key": getattr(snapshot, "ota_state_key", "idle"),
            "error_key": getattr(snapshot, "ota_error_key", "none"),
            "check_pending": bool(getattr(snapshot, "ota_check_pending", False)),
            "pending_reboot": bool(getattr(snapshot, "ota_pending_reboot", False)),
            "pending_verify": bool(getattr(snapshot, "ota_pending_verify", False)),
            "health_confirmed": bool(getattr(snapshot, "ota_health_confirmed", False)),
        },
        "control_plane": serialize_control_plane_node_detail(control_plane_snapshot),
    }


def serialize_control_transaction_result(result: ControlTransactionResult) -> dict[str, Any]:
    ack = getattr(result, "ack", None)
    return {
        "command_name": str(result.command_name),
        "final_status": _enum_value(getattr(result, "final_status", None)),
        "attempt_count": int(result.attempt_count),
        "cmd_seq": _coerce_int(getattr(result, "cmd_seq", None)),
        "nonce": _coerce_int(getattr(result, "nonce", None)),
        "ack_stage": _coerce_int(None if ack is None else getattr(ack, "ack_stage", None)),
        "status_code": _coerce_int(None if ack is None else getattr(ack, "status_code", None)),
        "err_detail": _coerce_int(None if ack is None else getattr(ack, "err_detail", None)),
        "elapsed_ms": float(result.elapsed_ms),
    }


def serialize_control_plane_node_brief(
    snapshot: ControlPlaneNodeSnapshot | None,
) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    return {
        "resolved_ip": getattr(snapshot, "resolved_ip", None),
        "resolution_status": _enum_value(getattr(snapshot, "resolution_status", None)),
        "transaction_active": bool(getattr(snapshot, "transaction_active", False)),
        "last_command_name": getattr(snapshot, "last_command_name", None),
        "last_final_status": getattr(snapshot, "last_final_status", None),
        "last_tx_finished_at": getattr(snapshot, "last_tx_finished_at", None),
        "message": getattr(snapshot, "message", ""),
    }


def serialize_control_plane_node_detail(
    snapshot: ControlPlaneNodeSnapshot | None,
) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    return {
        "resolved_ip": getattr(snapshot, "resolved_ip", None),
        "resolution_status": _enum_value(getattr(snapshot, "resolution_status", None)),
        "resolution_age_s": _coerce_float(getattr(snapshot, "resolution_age_s", None)),
        "transaction_active": bool(getattr(snapshot, "transaction_active", False)),
        "last_command_name": getattr(snapshot, "last_command_name", None),
        "last_cmd_seq": _coerce_int(getattr(snapshot, "last_cmd_seq", None)),
        "last_nonce": _coerce_int(getattr(snapshot, "last_nonce", None)),
        "last_final_status": getattr(snapshot, "last_final_status", None),
        "last_ack_stage": _coerce_int(getattr(snapshot, "last_ack_stage", None)),
        "last_status_code": _coerce_int(getattr(snapshot, "last_status_code", None)),
        "last_err_detail": _coerce_int(getattr(snapshot, "last_err_detail", None)),
        "last_error_message": getattr(snapshot, "last_error_message", None),
        "last_tx_started_at": getattr(snapshot, "last_tx_started_at", None),
        "last_tx_finished_at": getattr(snapshot, "last_tx_finished_at", None),
        "last_reboot_verification_status": getattr(snapshot, "last_reboot_verification_status", None),
        "last_reboot_verification_summary": getattr(snapshot, "last_reboot_verification_summary", None),
        "message": getattr(snapshot, "message", ""),
    }


def _enum_value(value: object) -> object:
    raw = getattr(value, "value", value)
    return raw


def _coerce_port(value: object, *, fallback: int) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return fallback
    if port < 0 or port > 65535:
        return fallback
    return port


def _coerce_positive_int(value: object, *, fallback: int) -> int:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return fallback
    if resolved <= 0:
        return fallback
    return resolved


def _coerce_exposure_mode(raw_mode: object, bind_host: object) -> str:
    if isinstance(raw_mode, str):
        normalized = raw_mode.strip()
        if normalized in {"local_only", "tailscale_only", "custom_bind"}:
            return normalized
    if isinstance(bind_host, str):
        normalized_bind_host = bind_host.strip()
        if normalized_bind_host and normalized_bind_host not in {"127.0.0.1", "::1"}:
            return "custom_bind"
    return "local_only"


def _coerce_auth_mode(raw_mode: object) -> str:
    if isinstance(raw_mode, str):
        normalized = raw_mode.strip()
        if normalized in {"human_session_only", "bearer_token", "bearer_token_inventory"}:
            return normalized
    return "human_session_only"


def _coerce_token_inventory(value: object) -> tuple[RemoteApiTokenInventoryEntry, ...]:
    if not isinstance(value, list):
        return ()
    entries: list[RemoteApiTokenInventoryEntry] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        env_var = item.get("env_var")
        role = item.get("role")
        label = item.get("label")
        if not isinstance(env_var, str) or not env_var.strip():
            continue
        if not isinstance(role, str) or not role.strip():
            continue
        normalized_label = None
        if isinstance(label, str) and label.strip():
            normalized_label = label.strip()
        entries.append(
            RemoteApiTokenInventoryEntry(
                env_var=env_var.strip(),
                role=role.strip(),
                label=normalized_label,
            )
        )
    return tuple(entries)


def _coerce_int(value: object, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_fw_version(snapshot: NodeSnapshot) -> str | None:
    major = _coerce_int(getattr(snapshot, "fw_major", None))
    minor = _coerce_int(getattr(snapshot, "fw_minor", None))
    if major is None or minor is None:
        return None
    return f"{major}.{minor}"
