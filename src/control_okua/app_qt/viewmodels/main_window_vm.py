from __future__ import annotations

import json
from dataclasses import dataclass
import time
from typing import Any

from control_okua.core.preflight import PreflightReport, ReadinessLevel
from control_okua.core.profiles.profile_service import (
    build_profile_ui_summary,
    infer_profile_from_config,
)
from control_okua.core.node_identity_policy import (
    resolve_node_identity,
    resolve_node_label,
)
from control_okua.core.registry import NodeRuntimeEvent, NodeRuntimeEventType, NodeStatus
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
        backend_text = "LAB (sobre runtime UDP)"
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
class PreflightDiagnosticRow:
    severity: str
    code: str
    message: str
    details: str


def build_preflight_status_label(report: PreflightReport | None) -> str:
    if report is None:
        return "Preparación de sesión: Sin evaluación"
    if report.readiness is ReadinessLevel.READY:
        return "Preparación de sesión: Lista"
    if report.readiness is ReadinessLevel.READY_WITH_WARNINGS:
        return "Preparación de sesión: Lista con advertencias"
    return "Preparación de sesión: No lista"


def build_preflight_summary_text(report: PreflightReport | None) -> str:
    if report is None:
        return "Resumen: autodiagnóstico aún no ejecutado."
    summary = report.summary.strip()
    if not summary:
        return "Resumen: sin datos de readiness."
    return f"Resumen: {summary}"


def build_preflight_counts(report: PreflightReport | None) -> str:
    if report is None:
        return "Bloqueos: - | Advertencias: - | Info: -"
    return (
        f"Bloqueos: {report.blocking_count} | "
        f"Advertencias: {report.warning_count} | "
        f"Info: {report.info_count}"
    )


def _first_finding_message(report: PreflightReport, *, prefer_blocking: bool) -> str | None:
    for finding in report.findings:
        if prefer_blocking and finding.is_blocking:
            return finding.message
        if not prefer_blocking and finding.severity.value == "warning":
            return finding.message
    for finding in report.findings:
        if finding.severity.value == "error":
            return finding.message
    if report.findings:
        return report.findings[0].message
    return None


def build_preflight_primary_message(report: PreflightReport | None) -> str:
    if report is None:
        return "Autodiagnóstico aún no ejecutado."

    if report.readiness is ReadinessLevel.BLOCKED:
        message = _first_finding_message(report, prefer_blocking=True)
        if message:
            return f"Motivo principal: {message}"
        return "Motivo principal: la sesión no está lista por configuración."

    if report.readiness is ReadinessLevel.READY_WITH_WARNINGS:
        message = _first_finding_message(report, prefer_blocking=False)
        if message:
            return f"Advertencia principal: {message}"
        return "Advertencia principal: hay observaciones no bloqueantes."

    return "Motivo principal: configuración válida para intentar iniciar sesión."


def build_preflight_runtime_note(
    report: PreflightReport | None,
    snapshot: SessionSnapshot,
) -> str:
    if report is None:
        return "Sin evaluación de readiness."

    if report.readiness is ReadinessLevel.BLOCKED:
        return "Inicio bloqueado por readiness/configuración."

    if snapshot.state is SessionState.ERROR:
        message = snapshot.message.casefold()
        if "backend" in message:
            return "Readiness OK; el error actual es de backend/runtime."
        return "Readiness OK; el error actual es del ciclo de sesión."

    return "Readiness evaluado; sin bloqueo declarativo."


def _format_finding_details(details: dict[str, Any] | None) -> str:
    if not isinstance(details, dict) or not details:
        return "-"
    parts: list[str] = []
    for key in sorted(details):
        raw_value = details[key]
        if isinstance(raw_value, (dict, list, tuple)):
            value_text = json.dumps(raw_value, ensure_ascii=False)
        else:
            value_text = str(raw_value)
        parts.append(f"{key}={value_text}")
    return " | ".join(parts)


def build_preflight_diagnostic_rows(report: PreflightReport | None) -> list[PreflightDiagnosticRow]:
    if report is None:
        return []

    rows: list[PreflightDiagnosticRow] = []
    for finding in report.findings:
        rows.append(
            PreflightDiagnosticRow(
                severity=finding.severity.value.upper(),
                code=finding.code.value,
                message=finding.message,
                details=_format_finding_details(finding.details),
            )
        )
    return rows


@dataclass(frozen=True)
class SerialRuntimeOperationBlock:
    status_label: str
    summary: str
    port: str
    messages_processed: str
    last_error: str
    recent_activity: str


@dataclass(frozen=True)
class SerialRuntimeDiagnosticRow:
    field: str
    value: str


def _is_serial_session(snapshot: SessionSnapshot) -> bool:
    backend = snapshot.backend
    return backend is not None and backend.value == "serial"


def _runtime_attr(runtime_snapshot: object | None, name: str) -> Any:
    if runtime_snapshot is None:
        return None
    return getattr(runtime_snapshot, name, None)


def _transport_attr(runtime_snapshot: object | None, name: str) -> Any:
    transport_snapshot = _runtime_attr(runtime_snapshot, "transport")
    if transport_snapshot is None:
        return None
    return getattr(transport_snapshot, name, None)


def _safe_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_recent_activity(
    runtime_snapshot: object | None,
    *,
    now_monotonic: float | None,
    recent_window_s: float,
) -> bool:
    if runtime_snapshot is None:
        return False

    last_activity = _safe_float(_runtime_attr(runtime_snapshot, "last_activity_ts"))
    if last_activity is None:
        last_activity = _safe_float(_transport_attr(runtime_snapshot, "last_activity_ts"))
    if last_activity is None:
        return False

    now_value = now_monotonic if now_monotonic is not None else time.monotonic()
    return max(0.0, now_value - last_activity) <= recent_window_s


def _serial_runtime_status_text(
    runtime_snapshot: object | None,
    session_snapshot: SessionSnapshot,
    *,
    now_monotonic: float | None = None,
    recent_window_s: float = 3.0,
) -> str:
    if not _is_serial_session(session_snapshot):
        return "No disponible"

    if runtime_snapshot is None:
        return "No disponible"

    last_error = str(_runtime_attr(runtime_snapshot, "last_error") or "").strip()
    if last_error:
        return "Con error"

    is_running = bool(_runtime_attr(runtime_snapshot, "is_running"))
    if not is_running:
        return "No disponible"

    if _has_recent_activity(
        runtime_snapshot,
        now_monotonic=now_monotonic,
        recent_window_s=recent_window_s,
    ):
        return "Activo"
    return "Sin actividad reciente"


def build_operation_serial_block(
    runtime_snapshot: object | None,
    session_snapshot: SessionSnapshot,
    *,
    now_monotonic: float | None = None,
    recent_window_s: float = 3.0,
) -> SerialRuntimeOperationBlock:
    status_text = _serial_runtime_status_text(
        runtime_snapshot,
        session_snapshot,
        now_monotonic=now_monotonic,
        recent_window_s=recent_window_s,
    )
    status_label = f"Estado serial: {status_text}"

    if not _is_serial_session(session_snapshot):
        return SerialRuntimeOperationBlock(
            status_label=status_label,
            summary="Actividad serial no aplica para la sesión actual.",
            port="Puerto: -",
            messages_processed="Mensajes procesados: -",
            last_error="Último error: -",
            recent_activity="Actividad reciente: -",
        )

    if runtime_snapshot is None:
        return SerialRuntimeOperationBlock(
            status_label=status_label,
            summary="Runtime serial no disponible para la sesión actual.",
            port="Puerto: -",
            messages_processed="Mensajes procesados: -",
            last_error="Último error: -",
            recent_activity="Actividad reciente: -",
        )

    port_value = _runtime_attr(runtime_snapshot, "port")
    port_text = str(port_value).strip() if isinstance(port_value, str) and port_value.strip() else "-"
    messages_routed = _safe_int(_runtime_attr(runtime_snapshot, "messages_routed"), default=0)
    last_error_raw = str(_runtime_attr(runtime_snapshot, "last_error") or "").strip()
    last_error_text = last_error_raw if last_error_raw else "Sin errores"
    recent_text = (
        "Sí"
        if _has_recent_activity(
            runtime_snapshot,
            now_monotonic=now_monotonic,
            recent_window_s=recent_window_s,
        )
        else "No"
    )

    if status_text == "Activo":
        summary = "Flujo serial activo con tráfico reciente."
    elif status_text == "Sin actividad reciente":
        summary = "Backend serial corriendo sin tráfico reciente."
    elif status_text == "Con error":
        summary = "Backend serial con error runtime; revisar detalle técnico."
    else:
        summary = "Runtime serial no disponible para la sesión actual."

    return SerialRuntimeOperationBlock(
        status_label=status_label,
        summary=summary,
        port=f"Puerto: {port_text}",
        messages_processed=f"Mensajes procesados: {messages_routed}",
        last_error=f"Último error: {last_error_text}",
        recent_activity=f"Actividad reciente: {recent_text}",
    )


def _format_last_activity(runtime_snapshot: object | None, *, now_monotonic: float | None = None) -> str:
    if runtime_snapshot is None:
        return "-"

    last_activity = _safe_float(_runtime_attr(runtime_snapshot, "last_activity_ts"))
    if last_activity is None:
        last_activity = _safe_float(_transport_attr(runtime_snapshot, "last_activity_ts"))
    if last_activity is None:
        return "-"

    now_value = now_monotonic if now_monotonic is not None else time.monotonic()
    delta_s = max(0.0, now_value - last_activity)
    return f"hace {delta_s:.1f} s"


def build_diagnostic_serial_rows(
    runtime_snapshot: object | None,
    session_snapshot: SessionSnapshot,
    *,
    now_monotonic: float | None = None,
    recent_window_s: float = 3.0,
) -> list[SerialRuntimeDiagnosticRow]:
    status_text = _serial_runtime_status_text(
        runtime_snapshot,
        session_snapshot,
        now_monotonic=now_monotonic,
        recent_window_s=recent_window_s,
    )

    if not _is_serial_session(session_snapshot):
        return [
            SerialRuntimeDiagnosticRow("Estado serial", status_text),
            SerialRuntimeDiagnosticRow("Runtime", "No aplica para la sesión actual."),
        ]

    if runtime_snapshot is None:
        return [
            SerialRuntimeDiagnosticRow("Estado serial", status_text),
            SerialRuntimeDiagnosticRow("Runtime", "No disponible."),
        ]

    bytes_received = _safe_int(_transport_attr(runtime_snapshot, "bytes_received"), default=0)
    messages_parsed = _safe_int(_transport_attr(runtime_snapshot, "messages_parsed"), default=0)
    parse_errors = _safe_int(_transport_attr(runtime_snapshot, "parse_errors"), default=0)
    read_errors = _safe_int(_transport_attr(runtime_snapshot, "read_errors"), default=0)
    messages_routed = _safe_int(_runtime_attr(runtime_snapshot, "messages_routed"), default=0)

    port_value = _runtime_attr(runtime_snapshot, "port")
    port_text = str(port_value).strip() if isinstance(port_value, str) and port_value.strip() else "-"
    is_running = "Sí" if bool(_runtime_attr(runtime_snapshot, "is_running")) else "No"
    default_bus = _runtime_attr(runtime_snapshot, "default_bus")
    bus_text = "-" if default_bus is None else str(default_bus)
    last_error = str(_runtime_attr(runtime_snapshot, "last_error") or "").strip() or "Sin errores"
    last_event = str(_runtime_attr(runtime_snapshot, "last_event") or "").strip() or "-"

    return [
        SerialRuntimeDiagnosticRow("Estado serial", status_text),
        SerialRuntimeDiagnosticRow("Puerto", port_text),
        SerialRuntimeDiagnosticRow("Corriendo", is_running),
        SerialRuntimeDiagnosticRow("Bus por defecto", bus_text),
        SerialRuntimeDiagnosticRow("Bytes recibidos", str(bytes_received)),
        SerialRuntimeDiagnosticRow("Mensajes parseados", str(messages_parsed)),
        SerialRuntimeDiagnosticRow("Mensajes procesados", str(messages_routed)),
        SerialRuntimeDiagnosticRow("Errores de parseo", str(parse_errors)),
        SerialRuntimeDiagnosticRow("Errores de lectura", str(read_errors)),
        SerialRuntimeDiagnosticRow(
            "Última actividad",
            _format_last_activity(runtime_snapshot, now_monotonic=now_monotonic),
        ),
        SerialRuntimeDiagnosticRow("Último evento", last_event),
        SerialRuntimeDiagnosticRow("Último error", last_error),
    ]


@dataclass(frozen=True)
class UdpRuntimeOperationBlock:
    status_label: str
    summary: str
    bind: str
    ports: str
    evt_packets: str
    stat_packets: str
    last_error: str
    recent_activity: str


@dataclass(frozen=True)
class UdpRuntimeDiagnosticRow:
    field: str
    value: str


def _is_udp_session(snapshot: SessionSnapshot) -> bool:
    backend = snapshot.backend
    if snapshot.mode == "udp":
        return True
    if backend is None:
        return False
    return backend.value in {"udp", "lab"}


def _udp_runtime_status_text(
    runtime_snapshot: object | None,
    session_snapshot: SessionSnapshot,
    *,
    now_monotonic: float | None = None,
    recent_window_s: float = 5.0,
) -> str:
    if not _is_udp_session(session_snapshot):
        return "No disponible"

    if runtime_snapshot is None:
        return "No disponible"

    last_error = str(_runtime_attr(runtime_snapshot, "last_error") or "").strip()
    if not last_error:
        last_error = str(_transport_attr(runtime_snapshot, "last_error") or "").strip()
    if last_error:
        return "Con error"

    is_running = bool(_runtime_attr(runtime_snapshot, "is_running"))
    if not is_running:
        return "No disponible"

    if _has_recent_activity(
        runtime_snapshot,
        now_monotonic=now_monotonic,
        recent_window_s=recent_window_s,
    ):
        return "Activo"
    return "Sin actividad reciente"


def build_operation_udp_block(
    runtime_snapshot: object | None,
    session_snapshot: SessionSnapshot,
    *,
    now_monotonic: float | None = None,
    recent_window_s: float = 5.0,
) -> UdpRuntimeOperationBlock:
    status_text = _udp_runtime_status_text(
        runtime_snapshot,
        session_snapshot,
        now_monotonic=now_monotonic,
        recent_window_s=recent_window_s,
    )
    status_label = f"Estado UDP: {status_text}"

    if not _is_udp_session(session_snapshot):
        return UdpRuntimeOperationBlock(
            status_label=status_label,
            summary="Actividad UDP no aplica para la sesión actual.",
            bind="Bind: -",
            ports="Puertos: -",
            evt_packets="EVT recibidos: -",
            stat_packets="STAT recibidos: -",
            last_error="Último error: -",
            recent_activity="Actividad reciente: -",
        )

    if runtime_snapshot is None:
        return UdpRuntimeOperationBlock(
            status_label=status_label,
            summary="Runtime UDP no disponible para la sesión actual.",
            bind="Bind: -",
            ports="Puertos: -",
            evt_packets="EVT recibidos: -",
            stat_packets="STAT recibidos: -",
            last_error="Último error: -",
            recent_activity="Actividad reciente: -",
        )

    bind_ip = str(_transport_attr(runtime_snapshot, "bind_ip") or "-")
    evt_port = _transport_attr(runtime_snapshot, "evt_port")
    stat_port = _transport_attr(runtime_snapshot, "stat_port")
    evt_port_text = str(evt_port) if evt_port is not None else "-"
    stat_port_text = str(stat_port) if stat_port is not None else "-"
    total_evt = _safe_int(
        _runtime_attr(runtime_snapshot, "total_evt_packets"),
        default=_safe_int(_transport_attr(runtime_snapshot, "total_evt_packets"), default=0),
    )
    total_stat = _safe_int(
        _runtime_attr(runtime_snapshot, "total_stat_packets"),
        default=_safe_int(_transport_attr(runtime_snapshot, "total_stat_packets"), default=0),
    )
    last_error = str(_runtime_attr(runtime_snapshot, "last_error") or "").strip()
    if not last_error:
        last_error = str(_transport_attr(runtime_snapshot, "last_error") or "").strip()
    last_error_text = last_error or "Sin errores"
    recent_text = (
        "Sí"
        if _has_recent_activity(
            runtime_snapshot,
            now_monotonic=now_monotonic,
            recent_window_s=recent_window_s,
        )
        else "No"
    )

    if status_text == "Activo":
        summary = "Flujo UDP activo con tráfico reciente."
    elif status_text == "Sin actividad reciente":
        summary = "Backend UDP corriendo sin tráfico reciente."
    elif status_text == "Con error":
        summary = "Backend UDP con error runtime; revisar detalle técnico."
    else:
        summary = "Runtime UDP no disponible para la sesión actual."

    return UdpRuntimeOperationBlock(
        status_label=status_label,
        summary=summary,
        bind=f"Bind: {bind_ip}",
        ports=f"Puertos: EVT {evt_port_text} / STAT {stat_port_text}",
        evt_packets=f"EVT recibidos: {total_evt}",
        stat_packets=f"STAT recibidos: {total_stat}",
        last_error=f"Último error: {last_error_text}",
        recent_activity=f"Actividad reciente: {recent_text}",
    )


def _format_udp_evt_summary(runtime_snapshot: object | None) -> str:
    summary = _runtime_attr(runtime_snapshot, "last_evt")
    if summary is None:
        return "-"

    node_id = _runtime_attr(summary, "node_id")
    identity = resolve_node_identity(node_id)
    seq = _runtime_attr(summary, "seq")
    midi_bus = _runtime_attr(summary, "midi_bus")
    midi_ch = _runtime_attr(summary, "midi_ch")
    note = _runtime_attr(summary, "note")
    vel = _runtime_attr(summary, "vel")
    source_ip = _runtime_attr(summary, "source_ip")
    source_port = _runtime_attr(summary, "source_port")
    return (
        f"node={identity.node_label} (id={node_id}, caja={identity.box_label}) "
        f"seq={seq} bus={midi_bus} ch={midi_ch} "
        f"note={note} vel={vel} src={source_ip}:{source_port}"
    )


def _format_udp_stat_summary(runtime_snapshot: object | None) -> str:
    summary = _runtime_attr(runtime_snapshot, "last_stat")
    if summary is None:
        return "-"

    node_id = _runtime_attr(summary, "node_id")
    seq = _runtime_attr(summary, "seq")
    uptime_s = _runtime_attr(summary, "uptime_s")
    rssi_dbm = _runtime_attr(summary, "rssi_dbm")
    pps_x10 = _runtime_attr(summary, "pps_x10")
    vbat_mv = _runtime_attr(summary, "vbat_mv")
    source_ip = _runtime_attr(summary, "source_ip")
    source_port = _runtime_attr(summary, "source_port")
    return (
        f"node={node_id} seq={seq} uptime={uptime_s}s rssi={rssi_dbm}dBm "
        f"pps_x10={pps_x10} vbat={vbat_mv}mV src={source_ip}:{source_port}"
    )


def build_diagnostic_udp_rows(
    runtime_snapshot: object | None,
    session_snapshot: SessionSnapshot,
    *,
    now_monotonic: float | None = None,
    recent_window_s: float = 5.0,
) -> list[UdpRuntimeDiagnosticRow]:
    status_text = _udp_runtime_status_text(
        runtime_snapshot,
        session_snapshot,
        now_monotonic=now_monotonic,
        recent_window_s=recent_window_s,
    )

    if not _is_udp_session(session_snapshot):
        return [
            UdpRuntimeDiagnosticRow("Estado UDP", status_text),
            UdpRuntimeDiagnosticRow("Runtime", "No aplica para la sesión actual."),
        ]

    if runtime_snapshot is None:
        return [
            UdpRuntimeDiagnosticRow("Estado UDP", status_text),
            UdpRuntimeDiagnosticRow("Runtime", "No disponible."),
        ]

    bind_ip = str(_transport_attr(runtime_snapshot, "bind_ip") or "-")
    evt_port = str(_transport_attr(runtime_snapshot, "evt_port") or "-")
    stat_port = str(_transport_attr(runtime_snapshot, "stat_port") or "-")
    is_running = "Sí" if bool(_runtime_attr(runtime_snapshot, "is_running")) else "No"
    total_evt = _safe_int(
        _runtime_attr(runtime_snapshot, "total_evt_packets"),
        default=_safe_int(_transport_attr(runtime_snapshot, "total_evt_packets"), default=0),
    )
    total_stat = _safe_int(
        _runtime_attr(runtime_snapshot, "total_stat_packets"),
        default=_safe_int(_transport_attr(runtime_snapshot, "total_stat_packets"), default=0),
    )
    total_bytes = _safe_int(
        _runtime_attr(runtime_snapshot, "total_bytes_received"),
        default=_safe_int(_transport_attr(runtime_snapshot, "total_bytes_received"), default=0),
    )
    parse_errors = _safe_int(
        _runtime_attr(runtime_snapshot, "parse_errors"),
        default=_safe_int(_transport_attr(runtime_snapshot, "parse_errors"), default=0),
    )
    socket_errors = _safe_int(
        _runtime_attr(runtime_snapshot, "socket_errors"),
        default=_safe_int(_transport_attr(runtime_snapshot, "socket_errors"), default=0),
    )
    messages_routed = _safe_int(_runtime_attr(runtime_snapshot, "messages_routed"), default=0)
    last_packet_summary = str(_runtime_attr(runtime_snapshot, "last_packet_summary") or "").strip()
    if not last_packet_summary:
        last_packet_summary = str(_transport_attr(runtime_snapshot, "last_packet_summary") or "").strip()
    if not last_packet_summary:
        last_packet_summary = "-"
    last_error = str(_runtime_attr(runtime_snapshot, "last_error") or "").strip()
    if not last_error:
        last_error = str(_transport_attr(runtime_snapshot, "last_error") or "").strip()
    if not last_error:
        last_error = "Sin errores"

    rows = [
        UdpRuntimeDiagnosticRow("Estado UDP", status_text),
        UdpRuntimeDiagnosticRow("Bind IP", bind_ip),
        UdpRuntimeDiagnosticRow("Puerto EVT", evt_port),
        UdpRuntimeDiagnosticRow("Puerto STAT", stat_port),
        UdpRuntimeDiagnosticRow("Corriendo", is_running),
        UdpRuntimeDiagnosticRow("EVT totales", str(total_evt)),
        UdpRuntimeDiagnosticRow("STAT totales", str(total_stat)),
        UdpRuntimeDiagnosticRow("Bytes recibidos", str(total_bytes)),
        UdpRuntimeDiagnosticRow("Mensajes MIDI ruteados", str(messages_routed)),
        UdpRuntimeDiagnosticRow("Errores de parseo", str(parse_errors)),
        UdpRuntimeDiagnosticRow("Errores de socket", str(socket_errors)),
        UdpRuntimeDiagnosticRow(
            "Última actividad",
            _format_last_activity(runtime_snapshot, now_monotonic=now_monotonic),
        ),
        UdpRuntimeDiagnosticRow("Último paquete", last_packet_summary),
        UdpRuntimeDiagnosticRow("Último EVT", _format_udp_evt_summary(runtime_snapshot)),
        UdpRuntimeDiagnosticRow("Último STAT", _format_udp_stat_summary(runtime_snapshot)),
        UdpRuntimeDiagnosticRow("Último error", last_error),
    ]
    return rows


@dataclass(frozen=True)
class NodesTabViewState:
    title: str
    hint: str
    summary: str
    show_table: bool


def _node_attr(snapshot: object, name: str) -> Any:
    return getattr(snapshot, name, None)


def node_status_key(snapshot: object) -> str:
    raw_status = _node_attr(snapshot, "status")
    if raw_status is None:
        return "offline"
    if hasattr(raw_status, "value"):
        return str(raw_status.value).strip().lower()
    return str(raw_status).strip().lower()


def node_status_reason_key(snapshot: object) -> str:
    raw_reason = _node_attr(snapshot, "status_reason")
    if raw_reason is None:
        return ""
    return str(raw_reason).strip().lower()


def node_health_summary_key(snapshot: object) -> str:
    raw_summary = _node_attr(snapshot, "health_summary")
    if raw_summary is None:
        return node_status_reason_key(snapshot)
    text = str(raw_summary).strip().lower()
    if not text:
        return node_status_reason_key(snapshot)
    return text


def node_ota_state_key(snapshot: object) -> str:
    raw_state = _node_attr(snapshot, "ota_state_key")
    if raw_state is None:
        return "idle"
    text = str(raw_state).strip().lower()
    return text or "idle"


def node_ota_error_key(snapshot: object) -> str:
    raw_error = _node_attr(snapshot, "ota_error_key")
    if raw_error is None:
        return "none"
    text = str(raw_error).strip().lower()
    return text or "none"


def format_node_status(snapshot: object) -> str:
    status_key = node_status_key(snapshot)
    if status_key == NodeStatus.ONLINE.value:
        return "En línea"
    if status_key == NodeStatus.CALIBRATING.value:
        return "En calibración"
    if status_key == NodeStatus.DEGRADED.value:
        return "Degradado"
    return "Fuera de línea"


def format_node_status_reason(snapshot: object) -> str:
    reason_key = node_status_reason_key(snapshot)
    if not reason_key:
        return "—"
    if reason_key == "healthy traffic":
        return "tráfico saludable"
    if reason_key == "partial traffic":
        return "tráfico parcial"
    if reason_key == "elevated loss":
        return "pérdida elevada"
    if reason_key == "recovering":
        return "recuperándose"
    if reason_key == "calibrating":
        return "en calibración"
    if reason_key == "no recent packets":
        return "sin tráfico reciente"
    return reason_key


def format_node_health_summary(snapshot: object) -> str:
    summary_key = node_health_summary_key(snapshot)
    if not summary_key:
        return format_node_status_reason(snapshot)
    if summary_key == "healthy traffic":
        return "tráfico saludable"
    if summary_key == "reboot recent":
        return "reboot reciente"
    if summary_key == "recovering":
        return "recuperándose"
    if summary_key == "elevated loss":
        return "pérdida elevada"
    if summary_key == "activity partial":
        return "actividad parcial"
    if summary_key == "no recent packets":
        return "sin tráfico reciente"
    return summary_key


def format_node_ota_state(snapshot: object) -> str:
    state_key = node_ota_state_key(snapshot)
    if state_key == "idle":
        return "inactiva"
    if state_key == "triggered":
        return "trigger OTA recibido"
    if state_key == "fetching_manifest":
        return "consultando manifest"
    if state_key == "validating_manifest":
        return "validando manifest"
    if state_key == "downloading":
        return "descargando firmware"
    if state_key == "ready_reboot":
        return "instalado, reinicio pendiente"
    if state_key == "boot_validating":
        return "validando arranque nuevo"
    if state_key == "boot_confirmed":
        return "arranque OTA confirmado"
    if state_key == "error":
        return "error OTA"
    return state_key


def format_node_ota_error(snapshot: object) -> str:
    error_key = node_ota_error_key(snapshot)
    if error_key == "none":
        return "sin error"
    if error_key == "invalid_trigger":
        return "trigger inválido"
    if error_key == "manifest_http":
        return "error HTTP de manifest"
    if error_key == "manifest_parse":
        return "manifest inválido"
    if error_key == "manifest_incompatible":
        return "manifest incompatible"
    if error_key == "version_rejected":
        return "versión rechazada"
    if error_key == "already_current":
        return "artifact ya instalado"
    if error_key == "download_http":
        return "error HTTP de descarga"
    if error_key == "download_size":
        return "tamaño OTA inválido"
    if error_key == "download_hash":
        return "hash OTA inválido"
    if error_key == "ota_begin":
        return "falló inicio OTA"
    if error_key == "ota_write":
        return "falló escritura OTA"
    if error_key == "ota_finalize":
        return "falló cierre OTA"
    if error_key == "boot_wifi_timeout":
        return "timeout Wi-Fi tras OTA"
    if error_key == "boot_stat_timeout":
        return "STAT no emitido tras OTA"
    if error_key == "boot_identity_mismatch":
        return "identidad OTA inconsistente"
    if error_key == "boot_validate":
        return "falló validación de arranque"
    if error_key == "nvs_error":
        return "persistencia OTA falló"
    return error_key


def format_node_ota_flags(snapshot: object) -> str:
    flags: list[str] = []
    if bool(_node_attr(snapshot, "ota_check_pending")):
        flags.append("check pendiente")
    if bool(_node_attr(snapshot, "ota_pending_reboot")):
        flags.append("reinicio pendiente")
    if bool(_node_attr(snapshot, "ota_pending_verify")):
        flags.append("boot pendiente verify")
    if bool(_node_attr(snapshot, "ota_health_confirmed")):
        flags.append("boot confirmado")
    return ", ".join(flags) if flags else "sin flags"


def format_node_status_detail(snapshot: object) -> str:
    status_text = format_node_status(snapshot)
    reason_text = format_node_health_summary(snapshot)
    if reason_text == "—":
        return status_text
    return f"{status_text} | motivo: {reason_text}"


def format_node_status_since(snapshot: object) -> str:
    status_age_s = _safe_float(_node_attr(snapshot, "status_age_s"))
    return _format_age_value(status_age_s)


def format_node_last_stat_seen(snapshot: object) -> str:
    last_stat_age_s = _safe_float(_node_attr(snapshot, "last_stat_age_s"))
    return _format_age_value(last_stat_age_s)


def format_node_reboot_recency(snapshot: object) -> str:
    reboot_recent = bool(_node_attr(snapshot, "reboot_recent"))
    reboot_age_s = _safe_float(_node_attr(snapshot, "reboot_age_s"))
    if not reboot_recent or reboot_age_s is None:
        return "No"
    return f"Sí, hace {reboot_age_s:.1f} s"


def format_node_recent_events(
    snapshot: object,
    *,
    now_monotonic: float | None = None,
    limit: int = 3,
) -> tuple[str, ...]:
    raw_events = _node_attr(snapshot, "recent_events")
    if not isinstance(raw_events, tuple):
        return ()
    now_value = now_monotonic if now_monotonic is not None else time.monotonic()
    lines: list[str] = []
    for event in raw_events[: max(0, int(limit))]:
        if not isinstance(event, NodeRuntimeEvent):
            continue
        lines.append(_format_runtime_event(event, now_monotonic=now_value))
    return tuple(lines)


def build_node_runtime_tooltip(
    snapshot: object,
    *,
    now_monotonic: float | None = None,
    event_limit: int = 3,
) -> str:
    lines = [
        f"Estado: {format_node_status(snapshot)}",
        f"Resumen: {format_node_health_summary(snapshot)}",
        f"Motivo: {format_node_status_reason(snapshot)}",
        f"Último paquete: {format_node_last_seen(snapshot, now_monotonic=now_monotonic)}",
        f"Último STAT: {format_node_last_stat_seen(snapshot)}",
        f"Tiempo en estado: {format_node_status_since(snapshot)}",
        f"Reboot reciente: {format_node_reboot_recency(snapshot)}",
        f"PPS: {format_node_pps(snapshot)}",
        f"Pérdida: {format_node_loss(snapshot)}",
    ]
    uptime = _node_attr(snapshot, "last_uptime_s")
    if uptime is not None:
        lines.append(f"Uptime conocido: {uptime} s")
    reset_reason = _node_attr(snapshot, "reset_reason")
    if reset_reason is not None:
        lines.append(f"Reset reason: {reset_reason}")
    ota_state = node_ota_state_key(snapshot)
    ota_error = node_ota_error_key(snapshot)
    ota_flags = format_node_ota_flags(snapshot)
    if ota_state != "idle" or ota_error != "none" or ota_flags != "sin flags":
        lines.append(f"OTA: {format_node_ota_state(snapshot)}")
        if ota_error != "none":
            lines.append(f"OTA error: {format_node_ota_error(snapshot)}")
        lines.append(f"OTA flags: {ota_flags}")

    recent_events = format_node_recent_events(
        snapshot,
        now_monotonic=now_monotonic,
        limit=event_limit,
    )
    if recent_events:
        lines.append("Eventos recientes:")
        lines.extend(f"- {item}" for item in recent_events)
    return "\n".join(lines)


def format_node_last_seen(
    snapshot: object,
    now_monotonic: float | None = None,
    *,
    freeze_after_s: float = 600.0,
) -> str:
    last_seen = _safe_float(_node_attr(snapshot, "last_seen_pc_ts"))
    if last_seen is None:
        return "—"
    now_value = now_monotonic if now_monotonic is not None else time.monotonic()
    delta_s = max(0.0, now_value - last_seen)
    if delta_s >= freeze_after_s:
        return "hace más de 10 min"
    return f"hace {delta_s:.1f} s"


def format_node_pps(snapshot: object) -> str:
    pps_evt = _safe_float(_node_attr(snapshot, "pps_evt"))
    pps_stat = _safe_float(_node_attr(snapshot, "pps_stat"))
    if pps_evt is None and pps_stat is None:
        return "—"
    evt_value = 0.0 if pps_evt is None else pps_evt
    stat_value = 0.0 if pps_stat is None else pps_stat
    return f"EVT {evt_value:.1f} | STAT {stat_value:.1f}"


def format_node_loss(snapshot: object) -> str:
    loss_evt = _safe_float(_node_attr(snapshot, "loss_evt_pct"))
    loss_stat = _safe_float(_node_attr(snapshot, "loss_stat_pct"))
    if loss_evt is None and loss_stat is None:
        return "—"
    evt_value = 0.0 if loss_evt is None else loss_evt
    stat_value = 0.0 if loss_stat is None else loss_stat
    return f"EVT {evt_value:.1f}% | STAT {stat_value:.1f}%"


def format_node_rssi(snapshot: object) -> str:
    rssi = _node_attr(snapshot, "rssi_dbm")
    if rssi is None:
        return "—"
    return f"{rssi} dBm"


def format_node_last_note_velocity(snapshot: object) -> str:
    note = _node_attr(snapshot, "last_note")
    velocity = _node_attr(snapshot, "last_velocity")
    if note is None or velocity is None:
        return "—"
    return f"{note} / {velocity}"


def format_node_label(snapshot: object) -> str:
    node_id = _safe_int(_node_attr(snapshot, "node_id"), default=-1)
    if node_id > 0:
        return resolve_node_label(node_id)

    label = _node_attr(snapshot, "label")
    if not isinstance(label, str):
        return "—"
    stripped = label.strip()
    return stripped if stripped else "—"


def format_node_type(snapshot: object) -> str:
    node_type = _node_attr(snapshot, "node_type")
    if not isinstance(node_type, str):
        return "—"
    stripped = node_type.strip()
    return stripped if stripped else "—"


def sort_node_snapshots_by_id(snapshots: list[object] | None) -> list[object]:
    if not isinstance(snapshots, list):
        return []
    return sorted(
        snapshots,
        key=lambda snapshot: _safe_int(_node_attr(snapshot, "node_id"), default=2147483647),
    )


def build_nodes_summary_text(summary: object | None) -> str:
    if summary is None:
        return "Resumen de nodos: no disponible."

    total_nodes = _safe_int(_node_attr(summary, "total_nodes"), default=0)
    online_count = _safe_int(_node_attr(summary, "online_count"), default=0)
    calibrating_count = _safe_int(_node_attr(summary, "calibrating_count"), default=0)
    degraded_count = _safe_int(_node_attr(summary, "degraded_count"), default=0)
    offline_count = _safe_int(_node_attr(summary, "offline_count"), default=0)
    total_pps_evt = _safe_float(_node_attr(summary, "total_pps_evt"))
    total_pps_stat = _safe_float(_node_attr(summary, "total_pps_stat"))

    evt_text = "0.0" if total_pps_evt is None else f"{total_pps_evt:.1f}"
    stat_text = "0.0" if total_pps_stat is None else f"{total_pps_stat:.1f}"
    return (
        f"Nodos: {total_nodes} | En línea: {online_count} | En calibración: {calibrating_count} | "
        f"Degradado: {degraded_count} | "
        f"Fuera de línea: {offline_count} | PPS EVT: {evt_text} | PPS STAT: {stat_text}"
    )


def _format_age_value(age_s: float | None) -> str:
    if age_s is None:
        return "—"
    return f"hace {age_s:.1f} s"


def _format_runtime_event(
    event: NodeRuntimeEvent,
    *,
    now_monotonic: float,
) -> str:
    age_s = max(0.0, float(now_monotonic) - float(event.occurred_at_pc_ts))
    base = _event_type_label(event.event_type)
    detail_parts: list[str] = []
    status_text = _status_key_to_text(event.status_key)
    if status_text:
        detail_parts.append(status_text)
    reason_text = _reason_key_to_text(event.reason)
    if reason_text:
        detail_parts.append(reason_text)
    details_text = _details_key_to_text(event.details)
    if details_text and details_text not in detail_parts:
        detail_parts.append(details_text)
    if detail_parts:
        return f"{base}: {' | '.join(detail_parts)} | hace {age_s:.1f} s"
    return f"{base} | hace {age_s:.1f} s"


def _event_type_label(event_type: NodeRuntimeEventType) -> str:
    if event_type is NodeRuntimeEventType.REBOOT_DETECTED:
        return "reboot detectado"
    if event_type is NodeRuntimeEventType.CALIBRATING_ENTERED:
        return "entró en calibración"
    if event_type is NodeRuntimeEventType.RECOVERED_ONLINE:
        return "volvió a en línea"
    if event_type is NodeRuntimeEventType.MOVED_DEGRADED:
        return "pasó a degradado"
    if event_type is NodeRuntimeEventType.MOVED_OFFLINE:
        return "pasó a fuera de línea"
    return "estado actualizado"


def _status_key_to_text(status_key: str) -> str:
    raw = str(status_key or "").strip().lower()
    if raw == NodeStatus.ONLINE.value:
        return "En línea"
    if raw == NodeStatus.CALIBRATING.value:
        return "En calibración"
    if raw == NodeStatus.DEGRADED.value:
        return "Degradado"
    if raw == NodeStatus.OFFLINE.value:
        return "Fuera de línea"
    return ""


def _reason_key_to_text(reason_key: str) -> str:
    raw = str(reason_key or "").strip().lower()
    if not raw:
        return ""
    if raw == "healthy traffic":
        return "tráfico saludable"
    if raw == "partial traffic":
        return "tráfico parcial"
    if raw == "elevated loss":
        return "pérdida elevada"
    if raw == "recovering":
        return "recuperándose"
    if raw == "calibrating":
        return "en calibración"
    if raw == "no recent packets":
        return "sin tráfico reciente"
    return raw


def _details_key_to_text(details_key: str) -> str:
    raw = str(details_key or "").strip().lower()
    if not raw:
        return ""
    if raw == "healthy traffic":
        return "tráfico saludable"
    if raw == "reboot recent":
        return "reboot reciente"
    if raw == "recovering":
        return "recuperándose"
    if raw == "elevated loss":
        return "pérdida elevada"
    if raw == "activity partial":
        return "actividad parcial"
    if raw == "no recent packets":
        return "sin tráfico reciente"
    if raw == "startup low uptime":
        return "arranque con uptime bajo"
    if raw == "uptime reset":
        return "reset de uptime"
    if raw == "reset reason changed":
        return "cambio de reset reason"
    if raw == "boot marker changed":
        return "cambio de boot marker"
    return raw


def build_nodes_tab_view_state(
    session_snapshot: SessionSnapshot,
    summary: object | None,
    *,
    shown_nodes: int,
) -> NodesTabViewState:
    if not _is_udp_session(session_snapshot) or session_snapshot.state is not SessionState.RUNNING:
        return NodesTabViewState(
            title="La vista de nodos está disponible para sesiones UDP.",
            hint="Inicia una sesión UDP para ver nodos en vivo.",
            summary="Resumen de nodos: no disponible.",
            show_table=False,
        )

    total_nodes = _safe_int(_node_attr(summary, "total_nodes"), default=shown_nodes)
    if total_nodes <= 0:
        return NodesTabViewState(
            title="Aún no hay nodos en vivo.",
            hint="Los nodos aparecerán cuando se reciba tráfico EVT/STAT.",
            summary=build_nodes_summary_text(summary),
            show_table=False,
        )

    return NodesTabViewState(
        title="Nodos en vivo detectados.",
        hint="Actualización automática periódica mientras la sesión UDP esté corriendo.",
        summary=build_nodes_summary_text(summary),
        show_table=True,
    )


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
