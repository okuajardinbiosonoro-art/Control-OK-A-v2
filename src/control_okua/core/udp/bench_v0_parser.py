from __future__ import annotations

import struct

from control_okua.core.udp.bench_v0_models import (
    BENCH_V0_HEADER_SIZE,
    BENCH_V0_MAGIC,
    BENCH_V0_PACKET_SIZE,
    BENCH_V0_VERSION,
    BenchV0EvtPacket,
    BenchV0Header,
    BenchV0MsgType,
    BenchV0Packet,
    BenchV0PingPacket,
    BenchV0PongPacket,
    BenchV0StatPacket,
)


_HEADER_STRUCT = struct.Struct("<HBBHH")
_BODY_STRUCT = struct.Struct("<BBBBIbBHHIBBHH")
_CRC_OFFSET = BENCH_V0_PACKET_SIZE - 2


class BenchV0ParseError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def parse_bench_v0_header(raw_packet: bytes | bytearray | memoryview) -> BenchV0Header:
    payload = bytes(raw_packet)
    if len(payload) < BENCH_V0_HEADER_SIZE:
        raise BenchV0ParseError(
            "truncated_header",
            (
                f"Header BenchPktV0 truncado: esperados {BENCH_V0_HEADER_SIZE} bytes, "
                f"recibidos {len(payload)}."
            ),
        )

    magic, version, msg_type_raw, node_id, seq = _HEADER_STRUCT.unpack_from(payload, 0)
    if magic != BENCH_V0_MAGIC:
        raise BenchV0ParseError(
            "invalid_magic",
            f"Magic BenchPktV0 invalido: 0x{magic:04X} (esperado 0x{BENCH_V0_MAGIC:04X}).",
        )
    if version != BENCH_V0_VERSION:
        raise BenchV0ParseError(
            "unsupported_version",
            (
                f"Version BenchPktV0 no soportada: {version} "
                f"(esperada {BENCH_V0_VERSION})."
            ),
        )
    try:
        msg_type = BenchV0MsgType(msg_type_raw)
    except ValueError as exc:
        raise BenchV0ParseError(
            "unknown_msg_type",
            f"Tipo BenchPktV0 desconocido: {msg_type_raw}.",
        ) from exc

    return BenchV0Header(
        magic=magic,
        version=version,
        msg_type=msg_type,
        node_id=node_id,
        seq=seq,
    )


def parse_bench_v0_packet(
    raw_packet: bytes | bytearray | memoryview,
    *,
    validate_crc: bool = False,
) -> BenchV0Packet:
    payload = bytes(raw_packet)
    _validate_packet_length(payload)
    header = parse_bench_v0_header(payload)

    if validate_crc:
        expected_crc = bench_v0_crc16_ccitt(payload[:_CRC_OFFSET])
        received_crc = int.from_bytes(payload[_CRC_OFFSET:], byteorder="little", signed=False)
        if expected_crc != received_crc:
            raise BenchV0ParseError(
                "invalid_crc",
                f"CRC BenchPktV0 invalido: esperado 0x{expected_crc:04X}, recibido 0x{received_crc:04X}.",
            )

    (
        f0,
        f1,
        f2,
        f3,
        f4,
        f5,
        f6,
        f7,
        f8,
        f9,
        f10,
        f11,
        f12,
        f13,
    ) = _BODY_STRUCT.unpack(payload[BENCH_V0_HEADER_SIZE:])

    if header.msg_type is BenchV0MsgType.EVT:
        return BenchV0EvtPacket(
            header=header,
            midi_bus=f0,
            midi_ch=f1,
            note=f2,
            vel=f3,
            ts_ms=f4,
            rssi_dbm=f5,
            flags=f6,
            aux16=f7,
            rtt_ms=f8,
            aux32=f9,
            aux_u8_a=f10,
            aux_u8_b=f11,
            crc16=f13,
        )

    if header.msg_type is BenchV0MsgType.STAT:
        return BenchV0StatPacket(
            header=header,
            state_flags=f2,
            reset_reason=f3,
            uptime_s=f4,
            rssi_dbm=f5,
            stat_flags=f6,
            pps_x10=f7,
            vbat_mv=f8,
            free_heap=f9,
            fw_major=f10,
            fw_minor=f11,
            aux16=f12,
            crc16=f13,
        )

    if header.msg_type is BenchV0MsgType.PING:
        return BenchV0PingPacket(
            header=header,
            ts_ms=f4,
            rssi_dbm=f5,
            flags=f6,
            aux16=f7,
            rtt_ms=f8,
            aux32=f9,
            aux_u8_a=f10,
            aux_u8_b=f11,
            crc16=f13,
        )

    return BenchV0PongPacket(
        header=header,
        ts_ms=f4,
        rssi_dbm=f5,
        flags=f6,
        aux16=f7,
        rtt_ms=f8,
        aux32=f9,
        aux_u8_a=f10,
        aux_u8_b=f11,
        crc16=f13,
    )


def build_bench_v0_evt_packet(
    *,
    node_id: int,
    seq: int,
    midi_bus: int,
    midi_ch: int,
    note: int,
    vel: int,
    ts_ms: int,
    rssi_dbm: int = -60,
    flags: int = 0,
    aux16: int = 0,
    rtt_ms: int = 0,
    aux32: int = 0,
    aux_u8_a: int = 0,
    aux_u8_b: int = 0,
    crc16: int | None = None,
) -> bytes:
    return _build_bench_v0_packet_bytes(
        msg_type=BenchV0MsgType.EVT,
        node_id=node_id,
        seq=seq,
        f0=midi_bus,
        f1=midi_ch,
        f2=note,
        f3=vel,
        f4=ts_ms,
        f5=rssi_dbm,
        f6=flags,
        f7=aux16,
        f8=rtt_ms,
        f9=aux32,
        f10=aux_u8_a,
        f11=aux_u8_b,
        f12=0,
        crc16=crc16,
    )


def build_bench_v0_stat_packet(
    *,
    node_id: int,
    seq: int,
    state_flags: int = 0,
    reset_reason: int = 0,
    uptime_s: int = 1,
    rssi_dbm: int = -60,
    stat_flags: int = 0,
    pps_x10: int = 10,
    vbat_mv: int = 3700,
    free_heap: int = 200000,
    fw_major: int = 1,
    fw_minor: int = 0,
    aux16: int = 0,
    crc16: int | None = None,
) -> bytes:
    return _build_bench_v0_packet_bytes(
        msg_type=BenchV0MsgType.STAT,
        node_id=node_id,
        seq=seq,
        f0=0,
        f1=0,
        f2=state_flags,
        f3=reset_reason,
        f4=uptime_s,
        f5=rssi_dbm,
        f6=stat_flags,
        f7=pps_x10,
        f8=vbat_mv,
        f9=free_heap,
        f10=fw_major,
        f11=fw_minor,
        f12=aux16,
        crc16=crc16,
    )


def build_bench_v0_ping_packet(
    *,
    node_id: int,
    seq: int,
    ts_ms: int,
    rssi_dbm: int = -60,
    flags: int = 0,
    aux16: int = 0,
    rtt_ms: int = 0,
    aux32: int = 0,
    aux_u8_a: int = 0,
    aux_u8_b: int = 0,
    crc16: int | None = None,
) -> bytes:
    return _build_bench_v0_packet_bytes(
        msg_type=BenchV0MsgType.PING,
        node_id=node_id,
        seq=seq,
        f0=0,
        f1=0,
        f2=flags,
        f3=0,
        f4=ts_ms,
        f5=rssi_dbm,
        f6=flags,
        f7=aux16,
        f8=rtt_ms,
        f9=aux32,
        f10=aux_u8_a,
        f11=aux_u8_b,
        f12=0,
        crc16=crc16,
    )


def build_bench_v0_pong_packet(
    *,
    node_id: int,
    seq: int,
    ts_ms: int,
    rssi_dbm: int = -60,
    flags: int = 0,
    aux16: int = 0,
    rtt_ms: int = 0,
    aux32: int = 0,
    aux_u8_a: int = 0,
    aux_u8_b: int = 0,
    crc16: int | None = None,
) -> bytes:
    return _build_bench_v0_packet_bytes(
        msg_type=BenchV0MsgType.PONG,
        node_id=node_id,
        seq=seq,
        f0=0,
        f1=0,
        f2=flags,
        f3=0,
        f4=ts_ms,
        f5=rssi_dbm,
        f6=flags,
        f7=aux16,
        f8=rtt_ms,
        f9=aux32,
        f10=aux_u8_a,
        f11=aux_u8_b,
        f12=0,
        crc16=crc16,
    )


def build_bench_v0_pong_from_ping(
    ping: BenchV0PingPacket,
    *,
    seq: int | None = None,
    ts_ms: int | None = None,
    rtt_ms: int | None = None,
) -> bytes:
    return build_bench_v0_pong_packet(
        node_id=ping.header.node_id,
        seq=ping.header.seq if seq is None else seq,
        ts_ms=ping.ts_ms if ts_ms is None else ts_ms,
        rssi_dbm=ping.rssi_dbm,
        flags=ping.flags,
        aux16=ping.aux16,
        rtt_ms=ping.rtt_ms if rtt_ms is None else rtt_ms,
        aux32=ping.aux32,
        aux_u8_a=ping.aux_u8_a,
        aux_u8_b=ping.aux_u8_b,
        crc16=None,
    )


def bench_v0_crc16_ccitt(payload: bytes | bytearray | memoryview, *, seed: int = 0xFFFF) -> int:
    crc = int(seed) & 0xFFFF
    for byte in bytes(payload):
        crc ^= (int(byte) & 0xFF) << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF


def _validate_packet_length(payload: bytes) -> None:
    if len(payload) == BENCH_V0_PACKET_SIZE:
        return
    if len(payload) < BENCH_V0_PACKET_SIZE:
        code = "truncated_packet"
    else:
        code = "invalid_length"
    raise BenchV0ParseError(
        code,
        (
            f"Longitud BenchPktV0 invalida: esperada {BENCH_V0_PACKET_SIZE}, "
            f"recibida {len(payload)}."
        ),
    )


def _build_bench_v0_packet_bytes(
    *,
    msg_type: BenchV0MsgType,
    node_id: int,
    seq: int,
    f0: int,
    f1: int,
    f2: int,
    f3: int,
    f4: int,
    f5: int,
    f6: int,
    f7: int,
    f8: int,
    f9: int,
    f10: int,
    f11: int,
    f12: int,
    crc16: int | None,
) -> bytes:
    header = _HEADER_STRUCT.pack(
        BENCH_V0_MAGIC,
        BENCH_V0_VERSION,
        int(msg_type) & 0xFF,
        int(node_id) & 0xFFFF,
        int(seq) & 0xFFFF,
    )
    body_without_crc = _BODY_STRUCT.pack(
        _u8(f0),
        _u8(f1),
        _u8(f2),
        _u8(f3),
        _u32(f4),
        _i8(f5),
        _u8(f6),
        _u16(f7),
        _u16(f8),
        _u32(f9),
        _u8(f10),
        _u8(f11),
        _u16(f12),
        0,
    )
    packet_without_crc = header + body_without_crc
    resolved_crc = _u16(crc16) if crc16 is not None else bench_v0_crc16_ccitt(
        packet_without_crc[:_CRC_OFFSET]
    )
    body = _BODY_STRUCT.pack(
        _u8(f0),
        _u8(f1),
        _u8(f2),
        _u8(f3),
        _u32(f4),
        _i8(f5),
        _u8(f6),
        _u16(f7),
        _u16(f8),
        _u32(f9),
        _u8(f10),
        _u8(f11),
        _u16(f12),
        resolved_crc,
    )
    return header + body


def _u8(value: int) -> int:
    return int(value) & 0xFF


def _u16(value: int | None) -> int:
    return int(value or 0) & 0xFFFF


def _u32(value: int) -> int:
    return int(value) & 0xFFFFFFFF


def _i8(value: int) -> int:
    raw = int(value)
    if raw < -128:
        return -128
    if raw > 127:
        return 127
    return raw
