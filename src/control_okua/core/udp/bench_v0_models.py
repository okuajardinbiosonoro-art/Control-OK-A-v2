from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


BENCH_V0_MAGIC = 0x4B4F
BENCH_V0_VERSION = 0
BENCH_V0_PACKET_SIZE = 32
BENCH_V0_HEADER_SIZE = 8


class BenchV0MsgType(IntEnum):
    EVT = 1
    STAT = 2
    PING = 3
    PONG = 4


@dataclass(frozen=True)
class BenchV0Header:
    magic: int
    version: int
    msg_type: BenchV0MsgType
    node_id: int
    seq: int


@dataclass(frozen=True)
class BenchV0EvtPacket:
    header: BenchV0Header
    midi_bus: int
    midi_ch: int
    note: int
    vel: int
    ts_ms: int
    rssi_dbm: int
    flags: int
    aux16: int
    rtt_ms: int
    aux32: int
    aux_u8_a: int
    aux_u8_b: int
    crc16: int


@dataclass(frozen=True)
class BenchV0StatPacket:
    header: BenchV0Header
    state_flags: int
    reset_reason: int
    uptime_s: int
    rssi_dbm: int
    stat_flags: int
    pps_x10: int
    vbat_mv: int
    free_heap: int
    fw_major: int
    fw_minor: int
    aux16: int
    crc16: int


@dataclass(frozen=True)
class BenchV0PingPacket:
    header: BenchV0Header
    ts_ms: int
    rssi_dbm: int
    flags: int
    aux16: int
    rtt_ms: int
    aux32: int
    aux_u8_a: int
    aux_u8_b: int
    crc16: int


@dataclass(frozen=True)
class BenchV0PongPacket:
    header: BenchV0Header
    ts_ms: int
    rssi_dbm: int
    flags: int
    aux16: int
    rtt_ms: int
    aux32: int
    aux_u8_a: int
    aux_u8_b: int
    crc16: int


BenchV0Packet = BenchV0EvtPacket | BenchV0StatPacket | BenchV0PingPacket | BenchV0PongPacket
