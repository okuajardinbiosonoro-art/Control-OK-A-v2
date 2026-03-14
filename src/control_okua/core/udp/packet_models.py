from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


OKUA_MAGIC = 0x4B4F
OKUA_VERSION = 1
OKUA_HEADER_SIZE = 8
OKUA_EVT_PACKET_SIZE = 20
OKUA_STAT_PACKET_SIZE = 28


class OkuaPacketType(IntEnum):
    EVT = 1
    STAT = 2
    CMD = 3
    ACK = 4


@dataclass(frozen=True)
class OkuaHeader:
    magic: int
    version: int
    packet_type: OkuaPacketType
    node_id: int
    seq: int


@dataclass(frozen=True)
class OkuaEvtPacket:
    header: OkuaHeader
    midi_bus: int
    midi_ch: int
    note: int
    vel: int
    ts_ms: int
    rssi_dbm: int
    flags: int
    rsv: tuple[int, int]


@dataclass(frozen=True)
class OkuaStatPacket:
    header: OkuaHeader
    uptime_s: int
    rssi_dbm: int
    state_flags: int
    pps_x10: int
    vbat_mv: int
    free_heap: int
    fw_major: int
    fw_minor: int
    reset_reason: int
    rsv: tuple[int, int, int]


OkuaPacket = OkuaEvtPacket | OkuaStatPacket
