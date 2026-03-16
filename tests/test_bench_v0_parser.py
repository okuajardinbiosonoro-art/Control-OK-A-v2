from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.udp import (  # noqa: E402
    BENCH_V0_PACKET_SIZE,
    BenchV0MsgType,
    BenchV0ParseError,
    build_bench_v0_evt_packet,
    build_bench_v0_ping_packet,
    build_bench_v0_pong_packet,
    build_bench_v0_stat_packet,
    parse_bench_v0_packet,
)


def test_parse_valid_bench_v0_evt_packet() -> None:
    raw = build_bench_v0_evt_packet(
        node_id=0x1234,
        seq=0x5678,
        midi_bus=2,
        midi_ch=1,
        note=64,
        vel=110,
        ts_ms=0x10203040,
        rssi_dbm=-45,
        flags=0xA1,
        aux16=321,
        rtt_ms=12,
        aux32=123456,
        aux_u8_a=7,
        aux_u8_b=8,
    )
    packet = parse_bench_v0_packet(raw, validate_crc=True)

    assert len(raw) == BENCH_V0_PACKET_SIZE
    assert raw[4:6] == b"\x34\x12"
    assert raw[6:8] == b"\x78\x56"
    assert packet.header.msg_type is BenchV0MsgType.EVT
    assert packet.note == 64
    assert packet.vel == 110
    assert packet.ts_ms == 0x10203040
    assert packet.aux16 == 321
    assert packet.rtt_ms == 12


def test_parse_valid_bench_v0_stat_packet() -> None:
    raw = build_bench_v0_stat_packet(
        node_id=17,
        seq=33,
        state_flags=0x11,
        reset_reason=0x02,
        uptime_s=999,
        rssi_dbm=-58,
        stat_flags=0x04,
        pps_x10=77,
        vbat_mv=3722,
        free_heap=210000,
        fw_major=3,
        fw_minor=4,
        aux16=0xABCD,
    )
    packet = parse_bench_v0_packet(raw, validate_crc=True)

    assert packet.header.msg_type is BenchV0MsgType.STAT
    assert packet.uptime_s == 999
    assert packet.pps_x10 == 77
    assert packet.vbat_mv == 3722
    assert packet.fw_major == 3
    assert packet.fw_minor == 4
    assert packet.aux16 == 0xABCD


def test_parse_valid_bench_v0_ping_and_pong_packets() -> None:
    ping_raw = build_bench_v0_ping_packet(
        node_id=44,
        seq=80,
        ts_ms=1234,
        rtt_ms=15,
        aux16=9,
        flags=1,
    )
    pong_raw = build_bench_v0_pong_packet(
        node_id=44,
        seq=80,
        ts_ms=1234,
        rtt_ms=15,
        aux16=9,
        flags=1,
    )
    ping = parse_bench_v0_packet(ping_raw, validate_crc=True)
    pong = parse_bench_v0_packet(pong_raw, validate_crc=True)

    assert ping.header.msg_type is BenchV0MsgType.PING
    assert pong.header.msg_type is BenchV0MsgType.PONG
    assert ping.ts_ms == 1234
    assert pong.rtt_ms == 15


def test_invalid_version_or_length_raise_controlled_error() -> None:
    raw = bytearray(
        build_bench_v0_evt_packet(
            node_id=1,
            seq=1,
            midi_bus=0,
            midi_ch=0,
            note=60,
            vel=100,
            ts_ms=1,
        )
    )
    raw[2] = 1
    try:
        parse_bench_v0_packet(raw)
        assert False, "parse_bench_v0_packet debia fallar por version"
    except BenchV0ParseError as exc:
        assert exc.code == "unsupported_version"

    try:
        parse_bench_v0_packet(bytes(raw[:-1]))
        assert False, "parse_bench_v0_packet debia fallar por longitud"
    except BenchV0ParseError as exc:
        assert exc.code == "truncated_packet"
