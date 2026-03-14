from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from control_okua.core.profiles.profile_service import (
    build_profile_ui_summary,
    infer_profile_from_config,
)
from control_okua.core.session import SessionSnapshot, SessionState


def _mode_label(cfg: dict[str, Any]) -> str:
    mode_value = cfg.get("mode")
    if mode_value == "serial":
        return "Serial"
    if mode_value == "udp":
        return "Ethernet/UDP"
    return "No seleccionado"


def build_mode_summary(cfg: dict[str, Any]) -> str:
    return f"Modo actual: {_mode_label(cfg)}"


def _active_profile_id(cfg: dict[str, Any]) -> str | None:
    profile_cfg = cfg.get("profile")
    if isinstance(profile_cfg, dict):
        active_profile = profile_cfg.get("active")
        if isinstance(active_profile, str):
            return active_profile
    return infer_profile_from_config(cfg)


def build_profile_summary(cfg: dict[str, Any]) -> str:
    profile_summary = build_profile_ui_summary(_active_profile_id(cfg), cfg)
    return f"Perfil activo: {profile_summary['short_name']}"


def build_profile_mode_summary(cfg: dict[str, Any]) -> str:
    profile_summary = build_profile_ui_summary(_active_profile_id(cfg), cfg)
    mode_value = profile_summary.get("mode", "No disponible aún")
    if mode_value in {"serial", "udp"}:
        return f"Modo asociado: {str(mode_value).upper()}"
    return "Modo asociado: No disponible aún"


def build_operation_summary(cfg: dict[str, Any]) -> str:
    profile_summary = build_profile_ui_summary(_active_profile_id(cfg), cfg)
    operation_text = profile_summary.get("operation_summary", "").strip()
    if operation_text:
        return f"Uso esperado: {operation_text}"
    return "Uso esperado: No disponible aún"


def build_transport_summary(cfg: dict[str, Any]) -> str:
    mode_value = cfg.get("mode")
    if mode_value == "serial":
        raw_serial_cfg = cfg.get("serial")
        serial_cfg: dict[str, Any] = raw_serial_cfg if isinstance(raw_serial_cfg, dict) else {}
        baudrate = serial_cfg.get("baudrate", "-")
        port = serial_cfg.get("port")
        port_text = port if isinstance(port, str) and port.strip() else "sin puerto asignado"
        return f"Transporte configurado: Serial ({port_text}, {baudrate} baudios)"

    if mode_value == "udp":
        raw_udp_cfg = cfg.get("udp")
        udp_cfg: dict[str, Any] = raw_udp_cfg if isinstance(raw_udp_cfg, dict) else {}
        bind_ip = udp_cfg.get("bind_ip", "0.0.0.0")
        evt_port = udp_cfg.get("evt_port", "-")
        stat_port = udp_cfg.get("stat_port", "-")
        cmd_port = udp_cfg.get("cmd_port", "-")
        return (
            "Transporte configurado: "
            f"UDP ({bind_ip} | evt:{evt_port} stat:{stat_port} cmd:{cmd_port})"
        )

    return "Transporte configurado: No disponible aún"


def build_midi_summary(cfg: dict[str, Any]) -> str:
    raw_midi_cfg = cfg.get("midi")
    midi_cfg: dict[str, Any] = raw_midi_cfg if isinstance(raw_midi_cfg, dict) else {}
    outputs = midi_cfg.get("outputs")
    backend = midi_cfg.get("backend")

    buses = 0
    if isinstance(outputs, dict):
        buses = len(outputs)

    backend_text = str(backend) if isinstance(backend, str) and backend.strip() else "desconocido"
    if buses <= 0:
        return f"MIDI configurado: sin buses definidos (backend: {backend_text})"

    bus_word = "bus" if buses == 1 else "buses"
    return f"MIDI configurado: {buses} {bus_word} (backend: {backend_text})"


def build_logging_summary(cfg: dict[str, Any]) -> str:
    raw_logging_cfg = cfg.get("logging")
    logging_cfg: dict[str, Any] = (
        raw_logging_cfg if isinstance(raw_logging_cfg, dict) else {}
    )
    enabled = logging_cfg.get("enabled")

    if isinstance(enabled, bool):
        if enabled:
            return "Logging: habilitado"
        return "Logging: deshabilitado"

    return "Logging: No disponible aún"


def build_general_status_summary(cfg: dict[str, Any], warnings: list[str] | None) -> str:
    profile_summary = build_profile_ui_summary(_active_profile_id(cfg), cfg)
    profile_defined = profile_summary.get("short_name") != "Perfil no definido"
    mode_value = cfg.get("mode")
    warnings_count = len(warnings or [])

    if warnings_count > 0:
        return (
            "Estado general: aplicación lista con advertencias "
            f"({warnings_count}) / sesión no iniciada"
        )

    if not profile_defined:
        if mode_value in {"serial", "udp"}:
            return "Estado general: perfil pendiente / sesión no iniciada"
        return "Estado general: perfil incompleto / sesión no iniciada"

    if mode_value not in {"serial", "udp"}:
        return "Estado general: modo pendiente / sesión no iniciada"

    return "Estado general: aplicación lista / sesión aún no iniciada"


def _session_state_label(state: SessionState) -> str:
    if state is SessionState.IDLE:
        return "inactiva"
    if state is SessionState.STARTING:
        return "iniciando"
    if state is SessionState.RUNNING:
        return "en ejecución"
    if state is SessionState.STOPPING:
        return "deteniendo"
    return "en error"


def build_session_status_summary(snapshot: SessionSnapshot) -> str:
    return f"Estado de sesión: {_session_state_label(snapshot.state)}"


def build_session_backend_summary(snapshot: SessionSnapshot) -> str:
    if snapshot.backend is None:
        return "Backend esperado: No disponible"

    if snapshot.backend.value == "serial":
        backend_text = "Serial"
    elif snapshot.backend.value == "udp":
        backend_text = "UDP"
    elif snapshot.backend.value == "lab":
        backend_text = "LAB (pendiente)"
    else:
        backend_text = snapshot.backend.value.upper()

    return f"Backend esperado: {backend_text}"


def build_session_message_summary(snapshot: SessionSnapshot) -> str:
    message = snapshot.message.strip() if isinstance(snapshot.message, str) else ""
    if not message:
        message = "Sin mensajes de sesión."
    return f"Mensaje actual: {message}"


def build_session_capabilities_summary(snapshot: SessionSnapshot) -> str:
    start_text = "Sí" if snapshot.can_start else "No"
    stop_text = "Sí" if snapshot.can_stop else "No"
    return f"Puede iniciar: {start_text} | Puede detener: {stop_text}"


@dataclass(frozen=True)
class SessionActionState:
    can_start_session: bool
    can_stop_session: bool
    can_reset_error: bool
    can_edit_configuration: bool


def build_session_action_state(snapshot: SessionSnapshot) -> SessionActionState:
    can_edit_configuration = snapshot.state not in {
        SessionState.STARTING,
        SessionState.RUNNING,
        SessionState.STOPPING,
    }
    return SessionActionState(
        can_start_session=snapshot.can_start,
        can_stop_session=snapshot.can_stop,
        can_reset_error=snapshot.state is SessionState.ERROR,
        can_edit_configuration=can_edit_configuration,
    )
