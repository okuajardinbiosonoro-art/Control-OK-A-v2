from __future__ import annotations

import socket
import struct
import sys
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.udp import OKUA_MAGIC, OKUA_VERSION, OkuaPacketType  # noqa: E402
from control_okua.transports.udp import (  # noqa: E402
    UdpTransportAdapter,
    UdpTransportConfig,
    UdpTransportConfigError,
    UdpTransportOpenError,
)


def _build_evt_packet(
    *,
    node_id: int = 1,
    seq: int = 1,
    note: int = 60,
    vel: int = 100,
) -> bytes:
    return struct.pack(
        "<HBBHHBBBBIbB2s",
        OKUA_MAGIC,
        OKUA_VERSION,
        OkuaPacketType.EVT,
        node_id,
        seq,
        0,
        0,
        note,
        vel,
        123456,
        -42,
        0x01,
        bytes([0x00, 0x00]),
    )


def _build_stat_packet(
    *,
    node_id: int = 2,
    seq: int = 7,
) -> bytes:
    return struct.pack(
        "<HBBHHIbBHHIBBB3s",
        OKUA_MAGIC,
        OKUA_VERSION,
        OkuaPacketType.STAT,
        node_id,
        seq,
        111,
        -33,
        0x02,
        89,
        3721,
        456789,
        1,
        9,
        3,
        bytes([0x00, 0x01, 0x02]),
    )


def _wait_until(predicate, timeout_s: float = 1.8) -> bool:
    start = time.monotonic()
    while (time.monotonic() - start) <= timeout_s:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _build_udp_config() -> UdpTransportConfig:
    evt_port = _get_free_port()
    stat_port = _get_free_port()
    while stat_port == evt_port:
        stat_port = _get_free_port()
    return UdpTransportConfig(
        bind_ip="127.0.0.1",
        evt_port=evt_port,
        stat_port=stat_port,
        rcvbuf_bytes=262144,
        recv_size=2048,
    )


def test_start_with_valid_udp_config_binds_sockets() -> None:
    adapter = UdpTransportAdapter(config=_build_udp_config())
    started = adapter.start()
    snapshot = adapter.snapshot()
    adapter.stop()

    assert started is True
    assert snapshot.is_running is True
    assert snapshot.evt_socket_open is True
    assert snapshot.stat_socket_open is True


def test_stop_releases_udp_resources_cleanly_and_is_idempotent() -> None:
    adapter = UdpTransportAdapter(config=_build_udp_config())
    adapter.start()
    adapter.stop()
    adapter.stop()
    snapshot = adapter.snapshot()

    assert snapshot.is_running is False
    assert snapshot.evt_socket_open is False
    assert snapshot.stat_socket_open is False


def test_loopback_receives_evt_and_stat_packets() -> None:
    cfg = _build_udp_config()
    adapter = UdpTransportAdapter(config=cfg)
    adapter.start()

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        sender.sendto(_build_evt_packet(node_id=11, seq=101, note=64, vel=120), (cfg.bind_ip, cfg.evt_port))
        sender.sendto(_build_stat_packet(node_id=22, seq=202), (cfg.bind_ip, cfg.stat_port))

    received = _wait_until(
        lambda: adapter.snapshot().total_evt_packets >= 1
        and adapter.snapshot().total_stat_packets >= 1
    )
    evt_packets = adapter.pop_evt_packets()
    stat_packets = adapter.pop_stat_packets()
    adapter.stop()

    assert received is True
    assert len(evt_packets) >= 1
    assert len(stat_packets) >= 1
    assert evt_packets[0].packet.header.packet_type is OkuaPacketType.EVT
    assert stat_packets[0].packet.header.packet_type is OkuaPacketType.STAT


def test_invalid_packet_increments_parse_error_without_crashing() -> None:
    cfg = _build_udp_config()
    adapter = UdpTransportAdapter(config=cfg)
    adapter.start()

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        sender.sendto(b"\x00\x00\x01\x01\x00\x00\x00\x00", (cfg.bind_ip, cfg.evt_port))

    observed = _wait_until(lambda: adapter.snapshot().parse_errors >= 1)
    still_running = adapter.snapshot().is_running
    adapter.stop()

    assert observed is True
    assert still_running is True


def test_bind_error_raises_controlled_exception() -> None:
    occupied = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    occupied.bind(("127.0.0.1", 0))
    busy_port = int(occupied.getsockname()[1])
    other_port = _get_free_port()
    while other_port == busy_port:
        other_port = _get_free_port()

    adapter = UdpTransportAdapter(
        config=UdpTransportConfig(
            bind_ip="127.0.0.1",
            evt_port=busy_port,
            stat_port=other_port,
        )
    )

    try:
        try:
            adapter.start()
            assert False, "start() debia fallar con UdpTransportOpenError"
        except UdpTransportOpenError as exc:
            assert "no se pudo abrir sockets udp" in str(exc).lower()
    finally:
        occupied.close()
        adapter.stop()


def test_invalid_bind_ip_raises_controlled_config_error() -> None:
    adapter = UdpTransportAdapter(
        config=UdpTransportConfig(bind_ip="invalid-ip", evt_port=5005, stat_port=5006)
    )

    try:
        adapter.start()
        assert False, "start() debia fallar con UdpTransportConfigError"
    except UdpTransportConfigError as exc:
        assert "udp.bind_ip invalido" in str(exc).lower()


def test_snapshot_runtime_updates_after_activity() -> None:
    cfg = _build_udp_config()
    adapter = UdpTransportAdapter(config=cfg)
    adapter.start()

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        sender.sendto(_build_evt_packet(node_id=33, seq=303, note=69, vel=90), (cfg.bind_ip, cfg.evt_port))

    observed = _wait_until(lambda: adapter.snapshot().total_evt_packets >= 1)
    snapshot = adapter.snapshot()
    adapter.stop()

    assert observed is True
    assert snapshot.total_bytes_received > 0
    assert snapshot.last_activity_ts is not None
    assert snapshot.last_packet_summary is not None
    assert "evt" in snapshot.last_packet_summary.lower()


def test_evt_stat_separation_is_visible_in_structured_output() -> None:
    cfg = _build_udp_config()
    evt_seen = []
    stat_seen = []

    adapter = UdpTransportAdapter(
        config=cfg,
        on_evt_packet=evt_seen.append,
        on_stat_packet=stat_seen.append,
    )
    adapter.start()

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        sender.sendto(_build_evt_packet(node_id=44, seq=404), (cfg.bind_ip, cfg.evt_port))
        sender.sendto(_build_stat_packet(node_id=55, seq=505), (cfg.bind_ip, cfg.stat_port))

    observed = _wait_until(lambda: len(evt_seen) >= 1 and len(stat_seen) >= 1)
    adapter.stop()

    assert observed is True
    assert evt_seen[0].packet.header.packet_type is OkuaPacketType.EVT
    assert stat_seen[0].packet.header.packet_type is OkuaPacketType.STAT
