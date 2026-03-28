from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.viewmodels.main_window_vm import (  # noqa: E402
    build_node_runtime_tooltip,
    format_node_health_summary,
    format_node_recent_events,
)
from control_okua.core.registry import (  # noqa: E402
    NodeRegistry,
    NodeRegistryConfig,
    NodeRuntimeEventType,
    NodeStatus,
)
from control_okua.core.udp import (  # noqa: E402
    OKUA_MAGIC,
    OKUA_VERSION,
    OkuaEvtPacket,
    OkuaHeader,
    OkuaPacketType,
    OkuaStatPacket,
)


def _evt(
    *,
    node_id: int = 11,
    seq: int = 1,
    note: int = 60,
    vel: int = 100,
    ts_ms: int = 123,
    rssi_dbm: int = -70,
    flags: int = 0x01,
) -> OkuaEvtPacket:
    return OkuaEvtPacket(
        header=OkuaHeader(
            magic=OKUA_MAGIC,
            version=OKUA_VERSION,
            packet_type=OkuaPacketType.EVT,
            node_id=node_id,
            seq=seq,
        ),
        midi_bus=0,
        midi_ch=1,
        note=note,
        vel=vel,
        ts_ms=ts_ms,
        rssi_dbm=rssi_dbm,
        flags=flags,
        rsv=(0, 0),
    )


def _stat(
    *,
    node_id: int = 11,
    seq: int = 1,
    uptime_s: int = 100,
    rssi_dbm: int = -65,
    state_flags: int = 0x03,
    pps_x10: int = 120,
    vbat_mv: int = 3700,
    free_heap: int = 111111,
    fw_major: int = 1,
    fw_minor: int = 2,
    reset_reason: int = 0,
    rsv: tuple[int, int, int] = (0, 0, 0),
) -> OkuaStatPacket:
    return OkuaStatPacket(
        header=OkuaHeader(
            magic=OKUA_MAGIC,
            version=OKUA_VERSION,
            packet_type=OkuaPacketType.STAT,
            node_id=node_id,
            seq=seq,
        ),
        uptime_s=uptime_s,
        rssi_dbm=rssi_dbm,
        state_flags=state_flags,
        pps_x10=pps_x10,
        vbat_mv=vbat_mv,
        free_heap=free_heap,
        fw_major=fw_major,
        fw_minor=fw_minor,
        reset_reason=reset_reason,
        rsv=rsv,
    )


def test_snapshot_exposes_observability_fields_for_calibrating_node() -> None:
    registry = NodeRegistry(
        NodeRegistryConfig(
            calibrating_hold_s=6.0,
            calibrating_uptime_s=20,
        )
    )
    registry.observe_stat(_stat(node_id=71, seq=1, uptime_s=5, reset_reason=2), received_at=0.0)

    snapshot = registry.get_node_snapshot(71, now=0.5)
    assert snapshot is not None
    assert snapshot.status is NodeStatus.CALIBRATING
    assert snapshot.status_reason == "calibrating"
    assert snapshot.health_summary == "reboot recent"
    assert snapshot.reboot_recent is True
    assert snapshot.recovering is False
    assert snapshot.last_status_change_pc_ts == 0.0
    assert snapshot.last_reboot_detected_pc_ts == 0.0
    assert snapshot.last_seen_age_s is not None and abs(snapshot.last_seen_age_s - 0.5) < 1e-9
    assert snapshot.last_stat_age_s is not None and abs(snapshot.last_stat_age_s - 0.5) < 1e-9
    assert snapshot.status_age_s is not None and abs(snapshot.status_age_s - 0.5) < 1e-9
    assert snapshot.reboot_age_s is not None and abs(snapshot.reboot_age_s - 0.5) < 1e-9
    assert snapshot.recent_events
    assert any(event.event_type is NodeRuntimeEventType.REBOOT_DETECTED for event in snapshot.recent_events)


def test_last_status_change_timestamp_stays_stable_while_status_does_not_change() -> None:
    registry = NodeRegistry(NodeRegistryConfig())
    registry.observe_stat(_stat(node_id=76, seq=1, uptime_s=100), received_at=0.0)

    first = registry.get_node_snapshot(76, now=0.5)
    registry.observe_stat(_stat(node_id=76, seq=2, uptime_s=101), received_at=1.0)
    second = registry.get_node_snapshot(76, now=1.1)

    assert first is not None and second is not None
    assert first.status is NodeStatus.ONLINE
    assert second.status is NodeStatus.ONLINE
    assert first.last_status_change_pc_ts == 0.0
    assert second.last_status_change_pc_ts == 0.0


def test_recent_events_are_bounded_and_newest_first() -> None:
    registry = NodeRegistry(
        NodeRegistryConfig(
            t_green_s=4.0,
            t_red_s=8.0,
            calibrating_hold_s=6.0,
            calibrating_uptime_s=20,
            max_runtime_events_per_node=3,
        )
    )
    registry.observe_stat(_stat(node_id=72, seq=1, uptime_s=5, reset_reason=1), received_at=0.0)
    registry.get_node_snapshot(72, now=9.0)
    registry.observe_stat(_stat(node_id=72, seq=2, uptime_s=100, reset_reason=1), received_at=9.1)

    snapshot = registry.get_node_snapshot(72, now=9.2)
    assert snapshot is not None
    assert len(snapshot.recent_events) == 3
    assert snapshot.recent_events[0].event_type is NodeRuntimeEventType.RECOVERED_ONLINE
    assert snapshot.recent_events[1].event_type is NodeRuntimeEventType.MOVED_OFFLINE


def test_recovery_to_online_leaves_observable_evidence() -> None:
    registry = NodeRegistry(
        NodeRegistryConfig(
            t_green_s=4.0,
            t_red_s=8.0,
            stat_loss_yellow_pct=25.0,
            stat_recovery_packets_online=3,
        )
    )
    registry.observe_stat(_stat(node_id=73, seq=1), received_at=0.0)
    registry.observe_stat(_stat(node_id=73, seq=2), received_at=1.0)
    registry.observe_stat(_stat(node_id=73, seq=5), received_at=2.0)
    registry.observe_stat(_stat(node_id=73, seq=6), received_at=3.0)
    registry.observe_stat(_stat(node_id=73, seq=7), received_at=4.0)

    snapshot = registry.get_node_snapshot(73, now=4.1)
    assert snapshot is not None
    assert snapshot.status is NodeStatus.ONLINE
    assert snapshot.status_reason == "healthy traffic"
    assert snapshot.recent_events[0].event_type is NodeRuntimeEventType.RECOVERED_ONLINE
    assert "healthy traffic" in snapshot.last_transition_summary


def test_offline_snapshot_keeps_coherent_cause_and_transition() -> None:
    registry = NodeRegistry(NodeRegistryConfig(t_green_s=4.0, t_red_s=8.0))
    registry.observe_evt(_evt(node_id=74, seq=1), received_at=0.0)

    snapshot = registry.get_node_snapshot(74, now=9.0)
    assert snapshot is not None
    assert snapshot.status is NodeStatus.OFFLINE
    assert snapshot.status_reason == "no recent packets"
    assert snapshot.health_summary == "no recent packets"
    assert snapshot.recent_events[0].event_type is NodeRuntimeEventType.MOVED_OFFLINE


def test_runtime_tooltip_and_recent_events_are_actionable() -> None:
    registry = NodeRegistry(
        NodeRegistryConfig(
            t_green_s=4.0,
            t_red_s=8.0,
            stat_loss_yellow_pct=25.0,
            stat_recovery_packets_online=3,
        )
    )
    registry.observe_stat(_stat(node_id=75, seq=1), received_at=0.0)
    registry.observe_stat(_stat(node_id=75, seq=2), received_at=1.0)
    registry.observe_stat(_stat(node_id=75, seq=5), received_at=2.0)

    snapshot = registry.get_node_snapshot(75, now=2.1)
    assert snapshot is not None
    tooltip = build_node_runtime_tooltip(snapshot, now_monotonic=2.1)
    recent_events = format_node_recent_events(snapshot, now_monotonic=2.1, limit=2)

    assert format_node_health_summary(snapshot) == "recuperándose"
    assert "Estado: Degradado" in tooltip
    assert "Resumen: recuperándose" in tooltip
    assert "Último paquete: hace 0.1 s" in tooltip
    assert "Eventos recientes:" in tooltip
    assert recent_events
    assert any("degradado" in item.lower() for item in recent_events)


def test_runtime_tooltip_surfaces_ota_runtime_when_present() -> None:
    registry = NodeRegistry()
    registry.observe_stat(
        _stat(
            node_id=79,
            seq=1,
            rsv=(4, 0, 0x01),
        ),
        received_at=0.0,
    )

    snapshot = registry.get_node_snapshot(79, now=0.1)
    assert snapshot is not None
    tooltip = build_node_runtime_tooltip(snapshot, now_monotonic=0.1)

    assert "OTA: descargando firmware" in tooltip
    assert "OTA flags: check pendiente" in tooltip
