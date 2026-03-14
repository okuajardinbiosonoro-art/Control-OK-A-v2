from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.registry import (  # noqa: E402
    NodeRegistry,
    NodeRegistryConfig,
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
    midi_bus: int = 0,
    midi_ch: int = 1,
) -> OkuaEvtPacket:
    return OkuaEvtPacket(
        header=OkuaHeader(
            magic=OKUA_MAGIC,
            version=OKUA_VERSION,
            packet_type=OkuaPacketType.EVT,
            node_id=node_id,
            seq=seq,
        ),
        midi_bus=midi_bus,
        midi_ch=midi_ch,
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
        rsv=(0, 0, 0),
    )


def test_empty_registry_snapshot_and_summary_are_coherent() -> None:
    registry = NodeRegistry()
    assert registry.get_all_node_snapshots(now=0.0) == []

    summary = registry.get_summary(now=0.0)
    assert summary.total_nodes == 0
    assert summary.online_count == 0
    assert summary.degraded_count == 0
    assert summary.offline_count == 0
    assert summary.total_pps_evt == 0.0
    assert summary.total_pps_stat == 0.0


def test_observe_evt_creates_new_node_and_updates_basic_fields() -> None:
    registry = NodeRegistry()
    registry.observe_evt(_evt(node_id=21, seq=10, note=64, vel=0, ts_ms=999, flags=0xAA), received_at=5.0)

    snapshot = registry.get_node_snapshot(21, now=5.0)
    assert snapshot is not None
    assert snapshot.node_id == 21
    assert snapshot.last_seen_pc_ts == 5.0
    assert snapshot.last_seq_evt == 10
    assert snapshot.rssi_dbm == -70
    assert snapshot.last_note == 64
    assert snapshot.last_velocity == 0
    assert snapshot.last_evt_ts_ms == 999
    assert snapshot.last_evt_flags == 0xAA


def test_observe_stat_updates_node_telemetry() -> None:
    registry = NodeRegistry()
    registry.observe_stat(
        _stat(
            node_id=21,
            seq=44,
            uptime_s=777,
            rssi_dbm=-52,
            state_flags=0x08,
            pps_x10=234,
            vbat_mv=3650,
            free_heap=555000,
            fw_major=2,
            fw_minor=9,
            reset_reason=3,
        ),
        received_at=6.0,
    )

    snapshot = registry.get_node_snapshot(21, now=6.0)
    assert snapshot is not None
    assert snapshot.last_seq_stat == 44
    assert snapshot.last_uptime_s == 777
    assert snapshot.rssi_dbm == -52
    assert snapshot.last_state_flags == 0x08
    assert snapshot.reported_pps_x10 == 234
    assert snapshot.vbat_mv == 3650
    assert snapshot.free_heap == 555000
    assert snapshot.fw_major == 2
    assert snapshot.fw_minor == 9
    assert snapshot.reset_reason == 3


def test_evt_sequence_gap_generates_expected_loss_pct() -> None:
    registry = NodeRegistry()
    registry.observe_evt(_evt(node_id=30, seq=10), received_at=1.0)
    registry.observe_evt(_evt(node_id=30, seq=11), received_at=2.0)
    registry.observe_evt(_evt(node_id=30, seq=14), received_at=3.0)

    snapshot = registry.get_node_snapshot(30, now=3.0)
    assert snapshot is not None
    assert snapshot.last_seq_evt == 14
    assert abs(snapshot.loss_evt_pct - 40.0) < 1e-9


def test_stat_sequence_gap_generates_expected_loss_pct() -> None:
    registry = NodeRegistry()
    registry.observe_stat(_stat(node_id=31, seq=10), received_at=1.0)
    registry.observe_stat(_stat(node_id=31, seq=11), received_at=2.0)
    registry.observe_stat(_stat(node_id=31, seq=14), received_at=3.0)

    snapshot = registry.get_node_snapshot(31, now=3.0)
    assert snapshot is not None
    assert snapshot.last_seq_stat == 14
    assert abs(snapshot.loss_stat_pct - 40.0) < 1e-9


def test_u16_wraparound_is_handled_without_false_loss() -> None:
    registry = NodeRegistry()
    registry.observe_evt(_evt(node_id=41, seq=65534), received_at=1.0)
    registry.observe_evt(_evt(node_id=41, seq=65535), received_at=2.0)
    registry.observe_evt(_evt(node_id=41, seq=0), received_at=3.0)
    registry.observe_evt(_evt(node_id=41, seq=1), received_at=4.0)

    snapshot = registry.get_node_snapshot(41, now=4.0)
    assert snapshot is not None
    assert snapshot.last_seq_evt == 1
    assert snapshot.loss_evt_pct == 0.0


def test_duplicate_and_out_of_order_packets_do_not_break_loss_tracking() -> None:
    registry = NodeRegistry()
    registry.observe_evt(_evt(node_id=50, seq=20), received_at=1.0)
    registry.observe_evt(_evt(node_id=50, seq=21), received_at=2.0)
    registry.observe_evt(_evt(node_id=50, seq=21), received_at=3.0)  # duplicate
    registry.observe_evt(_evt(node_id=50, seq=19), received_at=4.0)  # out-of-order
    registry.observe_evt(_evt(node_id=50, seq=22), received_at=5.0)

    snapshot = registry.get_node_snapshot(50, now=5.0)
    assert snapshot is not None
    assert snapshot.last_seq_evt == 22
    assert snapshot.loss_evt_pct == 0.0


def test_time_status_transitions_online_degraded_offline() -> None:
    registry = NodeRegistry(NodeRegistryConfig(t_green_s=5.0, t_red_s=10.0, pps_window_s=5.0))
    registry.observe_stat(_stat(node_id=61, seq=1), received_at=0.0)

    online = registry.get_node_snapshot(61, now=1.0)
    degraded = registry.get_node_snapshot(61, now=5.0)
    offline = registry.get_node_snapshot(61, now=10.0)

    assert online is not None and online.status is NodeStatus.ONLINE
    assert degraded is not None and degraded.status is NodeStatus.DEGRADED
    assert offline is not None and offline.status is NodeStatus.OFFLINE


def test_node_returns_to_online_after_new_traffic() -> None:
    registry = NodeRegistry(NodeRegistryConfig(t_green_s=5.0, t_red_s=10.0, pps_window_s=5.0))
    registry.observe_stat(_stat(node_id=62, seq=1), received_at=0.0)
    stale_snapshot = registry.get_node_snapshot(62, now=11.0)
    assert stale_snapshot is not None and stale_snapshot.status is NodeStatus.OFFLINE

    registry.observe_evt(_evt(node_id=62, seq=8), received_at=11.1)
    recovered_snapshot = registry.get_node_snapshot(62, now=11.1)
    assert recovered_snapshot is not None and recovered_snapshot.status is NodeStatus.ONLINE


def test_pps_evt_and_pps_stat_use_moving_window() -> None:
    registry = NodeRegistry(NodeRegistryConfig(pps_window_s=2.0, t_green_s=5.0, t_red_s=10.0))
    registry.observe_evt(_evt(node_id=70, seq=1), received_at=0.0)
    registry.observe_evt(_evt(node_id=70, seq=2), received_at=1.0)
    registry.observe_evt(_evt(node_id=70, seq=3), received_at=1.5)
    registry.observe_stat(_stat(node_id=70, seq=1), received_at=0.25)
    registry.observe_stat(_stat(node_id=70, seq=2), received_at=1.25)

    snapshot = registry.get_node_snapshot(70, now=1.5)
    assert snapshot is not None
    assert abs(snapshot.pps_evt - 1.5) < 1e-9  # 3 events / 2s window
    assert abs(snapshot.pps_stat - 1.0) < 1e-9  # 2 events / 2s window


def test_sparse_evt_with_healthy_stat_does_not_false_degrade_by_default() -> None:
    registry = NodeRegistry(
        NodeRegistryConfig(
            t_green_s=5.0,
            t_red_s=12.0,
            pps_min_yellow=10.0,
            pps_window_s=3.0,
        )
    )
    registry.observe_evt(_evt(node_id=80, seq=1), received_at=0.0)
    registry.observe_stat(_stat(node_id=80, seq=1), received_at=1.0)
    registry.observe_stat(_stat(node_id=80, seq=2), received_at=2.0)
    registry.observe_stat(_stat(node_id=80, seq=3), received_at=3.0)

    snapshot = registry.get_node_snapshot(80, now=3.5)
    assert snapshot is not None
    assert snapshot.status is NodeStatus.ONLINE


def test_clear_removes_all_nodes_and_metrics() -> None:
    registry = NodeRegistry()
    registry.observe_evt(_evt(node_id=90, seq=1), received_at=0.0)
    registry.observe_stat(_stat(node_id=91, seq=1), received_at=0.0)
    assert registry.get_summary(now=0.0).total_nodes == 2

    registry.clear()
    assert registry.get_node_snapshot(90, now=0.0) is None
    summary = registry.get_summary(now=0.0)
    assert summary.total_nodes == 0
    assert summary.online_count == 0
    assert summary.degraded_count == 0
    assert summary.offline_count == 0


def test_summary_counts_reflect_statuses_for_all_nodes() -> None:
    registry = NodeRegistry(NodeRegistryConfig(t_green_s=5.0, t_red_s=10.0, pps_window_s=5.0))
    registry.observe_stat(_stat(node_id=100, seq=1), received_at=18.0)  # online at now=20
    registry.observe_stat(_stat(node_id=101, seq=1), received_at=15.0)  # degraded at now=20
    registry.observe_stat(_stat(node_id=102, seq=1), received_at=8.0)  # offline at now=20

    summary = registry.get_summary(now=20.0)
    assert summary.total_nodes == 3
    assert summary.online_count == 1
    assert summary.degraded_count == 1
    assert summary.offline_count == 1
    assert summary.total_pps_evt >= 0.0
    assert summary.total_pps_stat >= 0.0
