from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.udp import (  # noqa: E402
    OKUA_EVT_PACKET_SIZE,
    OKUA_STAT_PACKET_SIZE,
    OkuaPacketType,
    parse_okua_packet,
)


def _load_sender_module():
    sender_path = ROOT_DIR / "tools" / "udp_okua_v1_sender.py"
    spec = importlib.util.spec_from_file_location("udp_okua_v1_sender", sender_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("No se pudo cargar tools/udp_okua_v1_sender.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_evt_packet_matches_okua_v1_and_little_endian() -> None:
    sender = _load_sender_module()
    packet = sender.build_okua_evt_packet(
        node_id=0x1234,
        seq=0x5678,
        midi_bus=2,
        midi_ch=3,
        note=64,
        vel=99,
        ts_ms=0x0A0B0C0D,
        rssi_dbm=-40,
        flags=0x55,
    )
    parsed = parse_okua_packet(packet, expected_type=OkuaPacketType.EVT)

    assert len(packet) == OKUA_EVT_PACKET_SIZE
    assert packet[4:6] == b"\x34\x12"
    assert packet[6:8] == b"\x78\x56"
    assert parsed.header.node_id == 0x1234
    assert parsed.header.seq == 0x5678
    assert parsed.note == 64
    assert parsed.vel == 99
    assert parsed.ts_ms == 0x0A0B0C0D


def test_build_stat_packet_matches_okua_v1_and_little_endian() -> None:
    sender = _load_sender_module()
    packet = sender.build_okua_stat_packet(
        node_id=0x2211,
        seq=0x4433,
        uptime_s=321,
        rssi_dbm=-52,
        state_flags=0x02,
        pps_x10=42,
        vbat_mv=3680,
        free_heap=123456,
        fw_major=3,
        fw_minor=9,
        reset_reason=4,
    )
    parsed = parse_okua_packet(packet, expected_type=OkuaPacketType.STAT)

    assert len(packet) == OKUA_STAT_PACKET_SIZE
    assert packet[4:6] == b"\x11\x22"
    assert packet[6:8] == b"\x33\x44"
    assert parsed.header.node_id == 0x2211
    assert parsed.header.seq == 0x4433
    assert parsed.uptime_s == 321
    assert parsed.vbat_mv == 3680


def test_sender_routes_evt_and_stat_to_separate_ports() -> None:
    sender = _load_sender_module()

    class _FakeSocket:
        def __init__(self) -> None:
            self.sent: list[tuple[bytes, tuple[str, int]]] = []
            self.closed = False

        def sendto(self, data: bytes, address: tuple[str, int]) -> int:
            self.sent.append((bytes(data), address))
            return len(data)

        def close(self) -> None:
            self.closed = True

    fake_socket = _FakeSocket()
    stats = sender.send_okua_v1_packets(
        host="127.0.0.1",
        evt_port=5005,
        stat_port=5006,
        node_id=7,
        seq_start=100,
        count=3,
        mode="both",
        interval_ms=0,
        ts_ms_start=1000,
        socket_factory=lambda: fake_socket,
        sleep_fn=lambda _seconds: None,
    )

    evt_targets = [address for payload, address in fake_socket.sent if len(payload) == OKUA_EVT_PACKET_SIZE]
    stat_targets = [address for payload, address in fake_socket.sent if len(payload) == OKUA_STAT_PACKET_SIZE]

    assert fake_socket.closed is True
    assert stats.evt_sent == 3
    assert stats.stat_sent == 3
    assert all(target == ("127.0.0.1", 5005) for target in evt_targets)
    assert all(target == ("127.0.0.1", 5006) for target in stat_targets)
