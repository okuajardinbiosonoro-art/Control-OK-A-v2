from __future__ import annotations

import struct
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.udp import (  # noqa: E402
    OKUA_MAGIC,
    OKUA_VERSION,
    OkuaPacketParseError,
    OkuaPacketType,
    parse_okua_header,
    parse_okua_packet,
)


def _build_evt_packet(
    *,
    node_id: int = 0x1234,
    seq: int = 0xABCD,
    midi_bus: int = 2,
    midi_ch: int = 5,
    note: int = 64,
    vel: int = 100,
    ts_ms: int = 0x11223344,
    rssi_dbm: int = -70,
    flags: int = 0xA5,
) -> bytes:
    return struct.pack(
        "<HBBHHBBBBIbB2s",
        OKUA_MAGIC,
        OKUA_VERSION,
        OkuaPacketType.EVT,
        node_id,
        seq,
        midi_bus,
        midi_ch,
        note,
        vel,
        ts_ms,
        rssi_dbm,
        flags,
        bytes([0x11, 0x22]),
    )


def _build_stat_packet(
    *,
    node_id: int = 0x4401,
    seq: int = 0x5502,
    uptime_s: int = 9001,
    rssi_dbm: int = -55,
    state_flags: int = 0x03,
    pps_x10: int = 123,
    vbat_mv: int = 3710,
    free_heap: int = 654321,
    fw_major: int = 2,
    fw_minor: int = 7,
    reset_reason: int = 4,
) -> bytes:
    return struct.pack(
        "<HBBHHIbBHHIBBB3s",
        OKUA_MAGIC,
        OKUA_VERSION,
        OkuaPacketType.STAT,
        node_id,
        seq,
        uptime_s,
        rssi_dbm,
        state_flags,
        pps_x10,
        vbat_mv,
        free_heap,
        fw_major,
        fw_minor,
        reset_reason,
        bytes([0x99, 0x88, 0x77]),
    )


def test_parse_valid_okua_evt_packet() -> None:
    packet = parse_okua_packet(_build_evt_packet())
    assert packet.header.packet_type is OkuaPacketType.EVT
    assert packet.header.node_id == 0x1234
    assert packet.header.seq == 0xABCD
    assert packet.midi_bus == 2
    assert packet.note == 64
    assert packet.vel == 100
    assert packet.ts_ms == 0x11223344
    assert packet.rssi_dbm == -70
    assert packet.flags == 0xA5
    assert packet.rsv == (0x11, 0x22)


def test_parse_valid_okua_stat_packet() -> None:
    packet = parse_okua_packet(_build_stat_packet())
    assert packet.header.packet_type is OkuaPacketType.STAT
    assert packet.header.node_id == 0x4401
    assert packet.header.seq == 0x5502
    assert packet.uptime_s == 9001
    assert packet.rssi_dbm == -55
    assert packet.state_flags == 0x03
    assert packet.pps_x10 == 123
    assert packet.vbat_mv == 3710
    assert packet.free_heap == 654321
    assert packet.fw_major == 2
    assert packet.fw_minor == 7
    assert packet.reset_reason == 4
    assert packet.rsv == (0x99, 0x88, 0x77)


def test_invalid_magic_raises_controlled_error() -> None:
    raw = bytearray(_build_evt_packet())
    raw[0] = 0x00
    raw[1] = 0x00
    try:
        parse_okua_packet(raw)
        assert False, "parse_okua_packet debia fallar por magic invalido"
    except OkuaPacketParseError as exc:
        assert exc.code == "invalid_magic"


def test_unsupported_version_raises_controlled_error() -> None:
    raw = bytearray(_build_evt_packet())
    raw[2] = 0x02
    try:
        parse_okua_packet(raw)
        assert False, "parse_okua_packet debia fallar por version no soportada"
    except OkuaPacketParseError as exc:
        assert exc.code == "unsupported_version"


def test_truncated_packet_raises_controlled_error() -> None:
    truncated = _build_stat_packet()[:-3]
    try:
        parse_okua_packet(truncated)
        assert False, "parse_okua_packet debia fallar por truncamiento"
    except OkuaPacketParseError as exc:
        assert exc.code == "truncated_packet"


def test_unsupported_type_for_this_ticket_raises_coherent_error() -> None:
    cmd_like = struct.pack(
        "<HBBHH",
        OKUA_MAGIC,
        OKUA_VERSION,
        OkuaPacketType.CMD,
        10,
        20,
    )
    try:
        parse_okua_packet(cmd_like)
        assert False, "parse_okua_packet debia fallar para tipo CMD"
    except OkuaPacketParseError as exc:
        assert exc.code == "unsupported_packet_type"
        assert "cmd" in str(exc).lower()


def test_header_fields_decode_in_little_endian() -> None:
    raw_header = struct.pack("<HBBHH", OKUA_MAGIC, OKUA_VERSION, OkuaPacketType.EVT, 0x3412, 0x7856)
    header = parse_okua_header(raw_header)
    assert header.node_id == 0x3412
    assert header.seq == 0x7856
