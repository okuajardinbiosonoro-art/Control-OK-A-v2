from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.viewmodels.main_window_vm import (  # noqa: E402
    build_nodes_tab_view_state,
    build_diagnostic_serial_rows,
    build_diagnostic_udp_rows,
    build_general_status_summary,
    build_logging_summary,
    build_mode_summary,
    build_operation_serial_block,
    build_operation_udp_block,
    build_operation_summary,
    build_preflight_counts,
    build_preflight_diagnostic_rows,
    build_preflight_primary_message,
    build_preflight_runtime_note,
    build_preflight_status_label,
    build_preflight_summary_text,
    build_profile_mode_summary,
    build_profile_summary,
    format_node_label,
    format_node_last_note_velocity,
    format_node_last_seen,
    format_node_loss,
    format_node_pps,
    format_node_rssi,
    format_node_status_detail,
    format_node_status_reason,
    format_node_status,
    format_node_type,
    sort_node_snapshots_by_id,
    build_transport_summary,
)
from control_okua.core.registry import NodeSnapshot, NodeStatus  # noqa: E402
from control_okua.core.preflight import (  # noqa: E402
    PreflightCheckCode,
    PreflightFinding,
    PreflightReport,
    PreflightSeverity,
    ReadinessLevel,
)
from control_okua.core.session import (  # noqa: E402
    BackendKind,
    SessionSnapshot,
    SessionState,
)


def test_serial_mode_and_transport_summary() -> None:
    cfg = {
        "mode": "serial",
        "serial": {
            "baudrate": 115200,
            "port": "COM5",
        },
    }

    mode_summary = build_mode_summary(cfg)
    transport_summary = build_transport_summary(cfg)

    assert mode_summary == "Modo actual: Serial"
    assert "Transporte configurado: Serial" in transport_summary
    assert "COM5" in transport_summary


def test_udp_mode_and_transport_summary() -> None:
    cfg = {
        "mode": "udp",
        "udp": {
            "bind_ip": "0.0.0.0",
            "evt_port": 5005,
            "stat_port": 5006,
            "cmd_port": 5007,
        },
    }

    mode_summary = build_mode_summary(cfg)
    transport_summary = build_transport_summary(cfg)

    assert mode_summary == "Modo actual: Ethernet/UDP"
    assert "Transporte configurado: UDP" in transport_summary
    assert "evt:5005" in transport_summary


def test_logging_summary_enabled_and_disabled() -> None:
    enabled_cfg = {"logging": {"enabled": True}}
    disabled_cfg = {"logging": {"enabled": False}}

    assert build_logging_summary(enabled_cfg) == "Logging: habilitado"
    assert build_logging_summary(disabled_cfg) == "Logging: deshabilitado"


def test_general_status_with_and_without_warnings() -> None:
    cfg = {"mode": "serial", "profile": {"active": "serial_local"}}

    no_warnings_status = build_general_status_summary(cfg, [])
    with_warnings_status = build_general_status_summary(cfg, ["warning 1"])

    assert no_warnings_status == "Estado general: aplicación lista / sesión aún no iniciada"
    assert "advertencias (1)" in with_warnings_status


def test_profile_summary_and_mode_for_udp_profile() -> None:
    cfg = {"mode": "udp", "profile": {"active": "udp_jardin"}}

    assert build_profile_summary(cfg) == "Perfil activo: UDP Jardín"
    assert build_profile_mode_summary(cfg) == "Modo asociado: UDP"
    assert "Uso esperado:" in build_operation_summary(cfg)


def test_general_status_for_missing_profile() -> None:
    cfg = {"mode": None, "profile": {"active": None}}
    status = build_general_status_summary(cfg, [])
    assert status == "Estado general: perfil incompleto / sesión no iniciada"


def _build_report(
    readiness: ReadinessLevel,
    findings: Iterable[PreflightFinding] = (),
) -> PreflightReport:
    findings_tuple = tuple(findings)
    blocking_count = sum(1 for finding in findings_tuple if finding.is_blocking)
    warning_count = sum(
        1 for finding in findings_tuple if finding.severity is PreflightSeverity.WARNING
    )
    info_count = sum(
        1 for finding in findings_tuple if finding.severity is PreflightSeverity.INFO
    )
    return PreflightReport(
        readiness=readiness,
        findings=findings_tuple,
        blocking_count=blocking_count,
        warning_count=warning_count,
        info_count=info_count,
        summary=f"Readiness: {readiness.value}",
        can_start=readiness is not ReadinessLevel.BLOCKED,
        profile_id="serial_local",
        derived_mode="serial",
        backend_kind="serial",
        session_spec_valid=True,
    )


def _build_snapshot(state: SessionState, message: str) -> SessionSnapshot:
    return SessionSnapshot(
        state=state,
        active_profile="serial_local",
        mode="serial",
        backend=BackendKind.SERIAL,
        message=message,
        error=None,
        can_start=state is SessionState.IDLE,
        can_stop=state is SessionState.RUNNING,
    )


def _build_udp_snapshot(state: SessionState, message: str) -> SessionSnapshot:
    return SessionSnapshot(
        state=state,
        active_profile="udp_jardin",
        mode="udp",
        backend=BackendKind.UDP,
        message=message,
        error=None,
        can_start=state is SessionState.IDLE,
        can_stop=state is SessionState.RUNNING,
    )


def _build_lab_udp_snapshot(state: SessionState, message: str) -> SessionSnapshot:
    return SessionSnapshot(
        state=state,
        active_profile="lab_sim",
        mode="udp",
        backend=BackendKind.LAB,
        message=message,
        error=None,
        can_start=state is SessionState.IDLE,
        can_stop=state is SessionState.RUNNING,
    )


def _node_snapshot(
    *,
    node_id: int,
    status: NodeStatus,
    last_seen_pc_ts: float | None = 100.0,
    pps_evt: float = 0.0,
    pps_stat: float = 0.0,
    loss_evt_pct: float = 0.0,
    loss_stat_pct: float = 0.0,
    rssi_dbm: int | None = None,
    note: int | None = None,
    vel: int | None = None,
    label: str | None = None,
    node_type: str | None = None,
    status_reason: str = "healthy traffic",
) -> NodeSnapshot:
    return NodeSnapshot(
        node_id=node_id,
        label=label,
        node_type=node_type,
        last_seen_pc_ts=last_seen_pc_ts,
        last_seq_evt=1,
        last_seq_stat=1,
        pps_evt=pps_evt,
        pps_stat=pps_stat,
        loss_evt_pct=loss_evt_pct,
        loss_stat_pct=loss_stat_pct,
        rssi_dbm=rssi_dbm,
        last_note=note,
        last_velocity=vel,
        last_evt_ts_ms=123,
        last_evt_flags=1,
        last_state_flags=1,
        last_uptime_s=100,
        reported_pps_x10=20,
        status=status,
        status_reason=status_reason,
    )


def _runtime_snapshot(
    *,
    is_running: bool = True,
    port: str | None = "COM5",
    messages_routed: int = 128,
    last_activity_ts: float | None = 100.0,
    last_error: str | None = None,
    last_event: str | None = "info: Serial iniciado",
    bytes_received: int = 2048,
    messages_parsed: int = 140,
    parse_errors: int = 0,
    read_errors: int = 0,
):
    transport = SimpleNamespace(
        port=port,
        bytes_received=bytes_received,
        messages_parsed=messages_parsed,
        parse_errors=parse_errors,
        read_errors=read_errors,
        last_activity_ts=last_activity_ts,
    )
    return SimpleNamespace(
        is_running=is_running,
        port=port,
        messages_routed=messages_routed,
        last_activity_ts=last_activity_ts,
        last_error=last_error,
        last_event=last_event,
        default_bus=0,
        transport=transport,
    )


def _udp_runtime_snapshot(
    *,
    is_running: bool = True,
    bind_ip: str = "127.0.0.1",
    evt_port: int = 5005,
    stat_port: int = 5006,
    total_evt_packets: int = 128,
    total_stat_packets: int = 64,
    total_bytes_received: int = 4096,
    parse_errors: int = 0,
    socket_errors: int = 0,
    messages_routed: int = 120,
    last_activity_ts: float | None = 100.0,
    last_packet_summary: str | None = "STAT node=10 seq=30",
    last_error: str | None = None,
):
    transport = SimpleNamespace(
        bind_ip=bind_ip,
        evt_port=evt_port,
        stat_port=stat_port,
        is_running=is_running,
        total_evt_packets=total_evt_packets,
        total_stat_packets=total_stat_packets,
        total_bytes_received=total_bytes_received,
        parse_errors=parse_errors,
        socket_errors=socket_errors,
        last_activity_ts=last_activity_ts,
        last_packet_summary=last_packet_summary,
        last_error=last_error,
    )
    last_evt = SimpleNamespace(
        node_id=10,
        seq=20,
        midi_bus=1,
        midi_ch=0,
        note=60,
        vel=100,
        source_ip="127.0.0.1",
        source_port=5005,
    )
    last_stat = SimpleNamespace(
        node_id=10,
        seq=30,
        uptime_s=111,
        rssi_dbm=-42,
        pps_x10=80,
        vbat_mv=3700,
        source_ip="127.0.0.1",
        source_port=5006,
    )
    return SimpleNamespace(
        is_running=is_running,
        messages_routed=messages_routed,
        last_activity_ts=last_activity_ts,
        last_error=last_error,
        total_evt_packets=total_evt_packets,
        total_stat_packets=total_stat_packets,
        total_bytes_received=total_bytes_received,
        parse_errors=parse_errors,
        socket_errors=socket_errors,
        last_packet_summary=last_packet_summary,
        last_evt=last_evt,
        last_stat=last_stat,
        transport=transport,
    )


def test_preflight_helpers_render_when_report_is_missing() -> None:
    status = build_preflight_status_label(None)
    summary = build_preflight_summary_text(None)
    counts = build_preflight_counts(None)
    primary = build_preflight_primary_message(None)

    assert status == "Preparación de sesión: Sin evaluación"
    assert "autodiagnóstico" in summary.lower()
    assert "bloqueos: -" in counts.lower()
    assert "aún no ejecutado" in primary.lower()


def test_preflight_helpers_render_ready_ready_with_warnings_and_blocked() -> None:
    ready_report = _build_report(ReadinessLevel.READY)
    warn_report = _build_report(
        ReadinessLevel.READY_WITH_WARNINGS,
        findings=(
            PreflightFinding(
                code=PreflightCheckCode.LOGGING_DISABLED,
                severity=PreflightSeverity.WARNING,
                message="Logging deshabilitado por configuracion.",
                is_blocking=False,
            ),
        ),
    )
    blocked_report = _build_report(
        ReadinessLevel.BLOCKED,
        findings=(
            PreflightFinding(
                code=PreflightCheckCode.PROFILE_MISSING,
                severity=PreflightSeverity.ERROR,
                message="profile.active no esta definido.",
                is_blocking=True,
            ),
        ),
    )

    assert build_preflight_status_label(ready_report).endswith("Lista")
    assert "advertencias" in build_preflight_status_label(warn_report).lower()
    assert build_preflight_status_label(blocked_report).endswith("No lista")
    assert "readiness: ready" in build_preflight_summary_text(ready_report).lower()
    assert "advertencia principal" in build_preflight_primary_message(warn_report).lower()
    assert "motivo principal" in build_preflight_primary_message(blocked_report).lower()


def test_preflight_counts_and_diagnostic_rows_are_coherent() -> None:
    report = _build_report(
        ReadinessLevel.BLOCKED,
        findings=(
            PreflightFinding(
                code=PreflightCheckCode.PROFILE_MISSING,
                severity=PreflightSeverity.ERROR,
                message="profile.active no esta definido.",
                details={"path": "profile.active"},
                is_blocking=True,
            ),
            PreflightFinding(
                code=PreflightCheckCode.LOGGING_DISABLED,
                severity=PreflightSeverity.WARNING,
                message="Logging deshabilitado por configuracion.",
                details=None,
                is_blocking=False,
            ),
        ),
    )

    counts = build_preflight_counts(report)
    rows = build_preflight_diagnostic_rows(report)

    assert "Bloqueos: 1" in counts
    assert "Advertencias: 1" in counts
    assert len(rows) == 2
    assert rows[0].severity == "ERROR"
    assert rows[0].code == "profile_missing"
    assert "profile.active" in rows[0].details
    assert rows[1].details == "-"


def test_preflight_runtime_note_separates_readiness_ok_from_backend_error() -> None:
    ready_report = _build_report(ReadinessLevel.READY_WITH_WARNINGS)
    backend_error_snapshot = _build_snapshot(
        SessionState.ERROR,
        "No se pudo iniciar sesion: Backend 'serial' no implementado.",
    )
    blocked_report = _build_report(ReadinessLevel.BLOCKED)
    blocked_snapshot = _build_snapshot(
        SessionState.ERROR,
        "No se puede iniciar la sesion: profile.active no esta definido.",
    )

    backend_note = build_preflight_runtime_note(ready_report, backend_error_snapshot)
    blocked_note = build_preflight_runtime_note(blocked_report, blocked_snapshot)

    assert "readiness ok" in backend_note.lower()
    assert "backend" in backend_note.lower()
    assert "inicio bloqueado" in blocked_note.lower()


def test_operation_serial_block_for_runtime_not_available() -> None:
    block = build_operation_serial_block(None, _build_snapshot(SessionState.IDLE, "ok"))
    assert "No disponible" in block.status_label
    assert "no disponible" in block.summary.lower()


def test_operation_serial_block_for_active_runtime() -> None:
    runtime = _runtime_snapshot(last_activity_ts=100.0)
    block = build_operation_serial_block(
        runtime,
        _build_snapshot(SessionState.RUNNING, "Sesion iniciada"),
        now_monotonic=101.0,
    )

    assert "Activo" in block.status_label
    assert "Puerto: COM5" == block.port
    assert "Mensajes procesados: 128" == block.messages_processed
    assert "Actividad reciente: Sí" == block.recent_activity


def test_operation_serial_block_for_runtime_error() -> None:
    runtime = _runtime_snapshot(last_error="Error de lectura serial: timeout")
    block = build_operation_serial_block(
        runtime,
        _build_snapshot(SessionState.RUNNING, "Sesion iniciada"),
        now_monotonic=120.0,
    )
    assert "Con error" in block.status_label
    assert "timeout" in block.last_error.lower()


def test_operation_serial_block_for_running_without_recent_activity() -> None:
    runtime = _runtime_snapshot(last_activity_ts=100.0, last_error=None)
    block = build_operation_serial_block(
        runtime,
        _build_snapshot(SessionState.RUNNING, "Sesion iniciada"),
        now_monotonic=110.0,
    )
    assert "Sin actividad reciente" in block.status_label
    assert block.recent_activity == "Actividad reciente: No"


def test_operation_serial_block_for_non_serial_session() -> None:
    runtime = _runtime_snapshot()
    block = build_operation_serial_block(
        runtime,
        _build_udp_snapshot(SessionState.RUNNING, "Sesion UDP"),
    )
    assert "No disponible" in block.status_label
    assert "no aplica" in block.summary.lower()


def test_diagnostic_serial_rows_include_technical_fields() -> None:
    runtime = _runtime_snapshot(
        messages_routed=55,
        bytes_received=4096,
        messages_parsed=70,
        parse_errors=2,
        read_errors=1,
        last_activity_ts=100.0,
        last_event="warning: Parseo MIDI serial",
    )
    rows = build_diagnostic_serial_rows(
        runtime,
        _build_snapshot(SessionState.RUNNING, "Sesion iniciada"),
        now_monotonic=102.0,
    )
    pairs = {row.field: row.value for row in rows}

    assert pairs["Estado serial"] in {"Activo", "Sin actividad reciente", "Con error"}
    assert pairs["Puerto"] == "COM5"
    assert pairs["Corriendo"] == "Sí"
    assert pairs["Bytes recibidos"] == "4096"
    assert pairs["Mensajes parseados"] == "70"
    assert pairs["Mensajes procesados"] == "55"
    assert pairs["Errores de parseo"] == "2"
    assert pairs["Errores de lectura"] == "1"
    assert "hace" in pairs["Última actividad"]
    assert "warning" in pairs["Último evento"].lower()


def test_diagnostic_serial_rows_distinguish_non_serial_session() -> None:
    rows = build_diagnostic_serial_rows(
        None,
        _build_udp_snapshot(SessionState.IDLE, "Sesion inactiva"),
    )
    pairs = {row.field: row.value for row in rows}
    assert pairs["Estado serial"] == "No disponible"
    assert "no aplica" in pairs["Runtime"].lower()


def test_operation_udp_block_for_runtime_not_available() -> None:
    block = build_operation_udp_block(
        None,
        _build_udp_snapshot(SessionState.IDLE, "Sesion inactiva"),
    )
    assert "No disponible" in block.status_label
    assert "no disponible" in block.summary.lower()


def test_operation_udp_block_for_active_runtime() -> None:
    runtime = _udp_runtime_snapshot(last_activity_ts=100.0)
    block = build_operation_udp_block(
        runtime,
        _build_udp_snapshot(SessionState.RUNNING, "Sesion iniciada"),
        now_monotonic=101.0,
    )

    assert "Activo" in block.status_label
    assert block.bind == "Bind: 127.0.0.1"
    assert "EVT 5005 / STAT 5006" in block.ports
    assert block.evt_packets == "EVT recibidos: 128"
    assert block.stat_packets == "STAT recibidos: 64"
    assert block.recent_activity == "Actividad reciente: Sí"


def test_operation_udp_block_for_runtime_error() -> None:
    runtime = _udp_runtime_snapshot(last_error="Error de recepcion UDP en EVT")
    block = build_operation_udp_block(
        runtime,
        _build_udp_snapshot(SessionState.RUNNING, "Sesion iniciada"),
        now_monotonic=120.0,
    )
    assert "Con error" in block.status_label
    assert "recepcion udp" in block.last_error.lower()


def test_operation_udp_block_for_running_without_recent_activity() -> None:
    runtime = _udp_runtime_snapshot(last_activity_ts=100.0, last_error=None)
    block = build_operation_udp_block(
        runtime,
        _build_udp_snapshot(SessionState.RUNNING, "Sesion iniciada"),
        now_monotonic=110.0,
    )
    assert "Sin actividad reciente" in block.status_label
    assert block.recent_activity == "Actividad reciente: No"


def test_operation_udp_block_for_non_udp_session() -> None:
    runtime = _udp_runtime_snapshot()
    block = build_operation_udp_block(
        runtime,
        _build_snapshot(SessionState.RUNNING, "Sesion serial"),
    )
    assert "No disponible" in block.status_label
    assert "no aplica" in block.summary.lower()


def test_diagnostic_udp_rows_include_technical_fields() -> None:
    runtime = _udp_runtime_snapshot(
        total_evt_packets=150,
        total_stat_packets=75,
        total_bytes_received=8888,
        parse_errors=3,
        socket_errors=2,
        messages_routed=149,
        last_activity_ts=100.0,
        last_packet_summary="EVT node=10 seq=20",
    )
    rows = build_diagnostic_udp_rows(
        runtime,
        _build_udp_snapshot(SessionState.RUNNING, "Sesion UDP"),
        now_monotonic=102.0,
    )
    pairs = {row.field: row.value for row in rows}

    assert pairs["Estado UDP"] in {"Activo", "Sin actividad reciente", "Con error"}
    assert pairs["Bind IP"] == "127.0.0.1"
    assert pairs["Puerto EVT"] == "5005"
    assert pairs["Puerto STAT"] == "5006"
    assert pairs["Corriendo"] == "Sí"
    assert pairs["EVT totales"] == "150"
    assert pairs["STAT totales"] == "75"
    assert pairs["Bytes recibidos"] == "8888"
    assert pairs["Mensajes MIDI ruteados"] == "149"
    assert pairs["Errores de parseo"] == "3"
    assert pairs["Errores de socket"] == "2"
    assert "hace" in pairs["Última actividad"]
    assert "id=10" in pairs["Último EVT"]
    assert "caja=Caja 2" in pairs["Último EVT"]
    assert "vbat=3700" in pairs["Último STAT"]


def test_diagnostic_udp_rows_distinguish_non_udp_session() -> None:
    rows = build_diagnostic_udp_rows(
        None,
        _build_snapshot(SessionState.IDLE, "Sesion inactiva"),
    )
    pairs = {row.field: row.value for row in rows}
    assert pairs["Estado UDP"] == "No disponible"
    assert "no aplica" in pairs["Runtime"].lower()


def test_operation_udp_block_supports_lab_profile_with_udp_runtime() -> None:
    runtime = _udp_runtime_snapshot()
    block = build_operation_udp_block(
        runtime,
        _build_lab_udp_snapshot(SessionState.RUNNING, "Sesion LAB sobre UDP"),
        now_monotonic=101.0,
    )
    assert "Activo" in block.status_label
    assert block.evt_packets == "EVT recibidos: 128"


def test_node_status_format_is_coherent() -> None:
    online = format_node_status(_node_snapshot(node_id=1, status=NodeStatus.ONLINE))
    calibrating = format_node_status(_node_snapshot(node_id=4, status=NodeStatus.CALIBRATING))
    degraded = format_node_status(_node_snapshot(node_id=2, status=NodeStatus.DEGRADED))
    offline = format_node_status(_node_snapshot(node_id=3, status=NodeStatus.OFFLINE))
    assert online == "En línea"
    assert calibrating == "En calibración"
    assert degraded == "Degradado"
    assert offline == "Fuera de línea"


def test_node_status_reason_and_detail_are_coherent() -> None:
    snapshot = _node_snapshot(
        node_id=9,
        status=NodeStatus.DEGRADED,
        status_reason="recovering",
    )
    assert format_node_status_reason(snapshot) == "recuperándose"
    assert "motivo: recuperándose" in format_node_status_detail(snapshot).lower()


def test_node_last_seen_format_is_coherent() -> None:
    seen = format_node_last_seen(
        _node_snapshot(node_id=10, status=NodeStatus.ONLINE, last_seen_pc_ts=100.0),
        now_monotonic=100.3,
    )
    missing = format_node_last_seen(
        _node_snapshot(node_id=11, status=NodeStatus.ONLINE, last_seen_pc_ts=None),
        now_monotonic=100.3,
    )
    assert seen == "hace 0.3 s"
    assert missing == "—"


def test_node_last_seen_freezes_after_ten_minutes() -> None:
    frozen = format_node_last_seen(
        _node_snapshot(node_id=10, status=NodeStatus.OFFLINE, last_seen_pc_ts=100.0),
        now_monotonic=760.1,
    )
    assert frozen == "hace más de 10 min"


def test_node_pps_loss_and_rssi_format_is_coherent() -> None:
    snapshot = _node_snapshot(
        node_id=20,
        status=NodeStatus.ONLINE,
        pps_evt=1.25,
        pps_stat=0.5,
        loss_evt_pct=3.2,
        loss_stat_pct=0.0,
        rssi_dbm=-65,
    )
    assert format_node_pps(snapshot) == "EVT 1.2 | STAT 0.5"
    assert format_node_loss(snapshot) == "EVT 3.2% | STAT 0.0%"
    assert format_node_rssi(snapshot) == "-65 dBm"


def test_node_note_velocity_and_optional_metadata_format_are_coherent() -> None:
    with_values = _node_snapshot(
        node_id=30,
        status=NodeStatus.ONLINE,
        note=64,
        vel=100,
        label="Nodo A",
        node_type="Fruta",
    )
    without_values = _node_snapshot(
        node_id=31,
        status=NodeStatus.ONLINE,
        note=None,
        vel=None,
        label=None,
        node_type=None,
    )
    assert format_node_last_note_velocity(with_values) == "64 / 100"
    assert format_node_last_note_velocity(without_values) == "—"
    assert format_node_label(with_values) == "EF6"
    assert format_node_type(with_values) == "Fruta"
    assert format_node_label(without_values) == "EB7"
    assert format_node_type(without_values) == "—"


def test_nodes_tab_state_non_udp_is_clear_no_aplica() -> None:
    state = build_nodes_tab_view_state(
        _build_snapshot(SessionState.RUNNING, "Sesion serial"),
        summary=None,
        shown_nodes=0,
    )
    assert state.show_table is False
    assert "disponible para sesiones udp" in state.title.lower()
    assert "inicia una sesión udp" in state.hint.lower()


def test_nodes_tab_state_udp_running_without_nodes_is_clear() -> None:
    summary = SimpleNamespace(
        total_nodes=0,
        online_count=0,
        degraded_count=0,
        offline_count=0,
        total_pps_evt=0.0,
        total_pps_stat=0.0,
    )
    state = build_nodes_tab_view_state(
        _build_udp_snapshot(SessionState.RUNNING, "Sesion udp"),
        summary=summary,
        shown_nodes=0,
    )
    assert state.show_table is False
    assert "aún no hay nodos en vivo" in state.title.lower()
    assert "tráfico evt/stat" in state.hint.lower()


def test_node_snapshots_sort_is_stable_by_node_id() -> None:
    snapshots = [
        _node_snapshot(node_id=22, status=NodeStatus.ONLINE),
        _node_snapshot(node_id=7, status=NodeStatus.ONLINE),
        _node_snapshot(node_id=15, status=NodeStatus.ONLINE),
    ]
    sorted_ids = [item.node_id for item in sort_node_snapshots_by_id(snapshots)]
    assert sorted_ids == [7, 15, 22]
