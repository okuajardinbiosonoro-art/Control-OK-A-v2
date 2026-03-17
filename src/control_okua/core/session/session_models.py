from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from control_okua.core.profiles.profile_service import (
    infer_profile_from_config,
    is_known_profile_id,
    resolve_profile_to_mode,
)


class SessionState(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class BackendKind(str, Enum):
    SERIAL = "serial"
    UDP = "udp"
    LAB = "lab"


@dataclass(frozen=True)
class SessionErrorInfo:
    code: str
    message: str
    detail: str | None = None


@dataclass(frozen=True)
class SessionSpec:
    profile_id: str | None
    mode: str | None
    backend: BackendKind | None
    is_valid: bool
    reason: str


@dataclass(frozen=True)
class SessionSnapshot:
    state: SessionState
    active_profile: str | None
    mode: str | None
    backend: BackendKind | None
    message: str
    error: SessionErrorInfo | None
    can_start: bool
    can_stop: bool


_PROFILE_BACKEND_MAP: dict[str, BackendKind] = {
    "serial_local": BackendKind.SERIAL,
    "udp_jardin": BackendKind.UDP,
    "lab_sim": BackendKind.LAB,
}


def _resolve_backend_kind(profile_id: str | None, mode: str | None) -> BackendKind | None:
    if isinstance(profile_id, str) and profile_id in _PROFILE_BACKEND_MAP:
        return _PROFILE_BACKEND_MAP[profile_id]
    if mode == "serial":
        return BackendKind.SERIAL
    if mode == "udp":
        return BackendKind.UDP
    return None


def _invalid_session_spec(reason: str) -> SessionSpec:
    return SessionSpec(
        profile_id=None,
        mode=None,
        backend=None,
        is_valid=False,
        reason=reason,
    )


def build_session_request_from_profile(cfg: dict[str, Any]) -> SessionSpec:
    if not isinstance(cfg, dict):
        return _invalid_session_spec("Config invalido: se esperaba un dict.")

    explicit_profile: str | None = None
    profile_cfg = cfg.get("profile")
    if isinstance(profile_cfg, dict):
        active_profile = profile_cfg.get("active")
        if isinstance(active_profile, str):
            explicit_profile = active_profile

    profile_id: str | None = None
    profile_source = "none"
    if is_known_profile_id(explicit_profile):
        profile_id = explicit_profile
        profile_source = "explicit"
    else:
        inferred_profile = infer_profile_from_config(cfg)
        if inferred_profile is not None:
            profile_id = inferred_profile
            profile_source = "inferred"

    if profile_id is None:
        return _invalid_session_spec(
            "No hay perfil activo valido y no se pudo inferir uno desde config.mode."
        )

    mode = resolve_profile_to_mode(profile_id)
    if mode not in {"serial", "udp"}:
        return _invalid_session_spec(
            f"No se pudo resolver modo operativo para profile_id='{profile_id}'."
        )

    backend = _resolve_backend_kind(profile_id, mode)
    if backend is None:
        return _invalid_session_spec(
            f"No se pudo resolver backend esperado para profile_id='{profile_id}'."
        )

    if profile_id == "lab_sim":
        reason = "Perfil lab_sim resuelto con backend 'lab' sobre runtime UDP."
    elif profile_source == "inferred":
        reason = "Perfil inferido desde config.mode."
    else:
        reason = "Perfil activo resuelto correctamente."

    return SessionSpec(
        profile_id=profile_id,
        mode=mode,
        backend=backend,
        is_valid=True,
        reason=reason,
    )


def _default_snapshot_message(state: SessionState) -> str:
    if state is SessionState.IDLE:
        return "Sesion inactiva."
    if state is SessionState.STARTING:
        return "Iniciando sesion."
    if state is SessionState.RUNNING:
        return "Sesion en ejecucion."
    if state is SessionState.STOPPING:
        return "Deteniendo sesion."
    return "Sesion en error."


def build_session_snapshot(
    state: SessionState,
    spec: SessionSpec,
    *,
    message: str | None = None,
    error: SessionErrorInfo | None = None,
) -> SessionSnapshot:
    return SessionSnapshot(
        state=state,
        active_profile=spec.profile_id,
        mode=spec.mode,
        backend=spec.backend,
        message=message or _default_snapshot_message(state),
        error=error,
        can_start=spec.is_valid and state is SessionState.IDLE,
        can_stop=state is SessionState.RUNNING,
    )
