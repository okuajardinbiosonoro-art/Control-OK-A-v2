from __future__ import annotations

import struct

from control_okua.core.udp.packet_models import (
    OKUA_EVT_PACKET_SIZE,
    OKUA_HEADER_SIZE,
    OKUA_MAGIC,
    OKUA_STAT_PACKET_SIZE,
    OKUA_VERSION,
    OkuaEvtPacket,
    OkuaHeader,
    OkuaPacket,
    OkuaPacketType,
    OkuaStatPacket,
)
from control_okua.core.udp.ota_runtime import decode_okua_ota_runtime


_HEADER_STRUCT = struct.Struct("<HBBHH")
_EVT_PAYLOAD_STRUCT = struct.Struct("<BBBBIbB2s")
_STAT_PAYLOAD_STRUCT = struct.Struct("<IbBHHIBBB3s")


class OkuaPacketParseError(ValueError):
    """Controlled parse error for invalid UDP packets."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def parse_okua_header(raw_packet: bytes | bytearray | memoryview) -> OkuaHeader:
    payload = bytes(raw_packet)
    if len(payload) < OKUA_HEADER_SIZE:
        raise OkuaPacketParseError(
            "truncated_header",
            f"Header truncado: se esperaban {OKUA_HEADER_SIZE} bytes y llegaron {len(payload)}.",
        )

    magic, version, packet_type_raw, node_id, seq = _HEADER_STRUCT.unpack_from(payload, 0)

    if magic != OKUA_MAGIC:
        raise OkuaPacketParseError(
            "invalid_magic",
            f"Magic invalido: 0x{magic:04X} (esperado 0x{OKUA_MAGIC:04X}).",
        )

    if version != OKUA_VERSION:
        raise OkuaPacketParseError(
            "unsupported_version",
            f"Version no soportada: {version} (esperada {OKUA_VERSION}).",
        )

    try:
        packet_type = OkuaPacketType(packet_type_raw)
    except ValueError as exc:
        raise OkuaPacketParseError(
            "unknown_packet_type",
            f"Tipo de paquete desconocido: {packet_type_raw}.",
        ) from exc

    return OkuaHeader(
        magic=magic,
        version=version,
        packet_type=packet_type,
        node_id=node_id,
        seq=seq,
    )


def parse_okua_packet(
    raw_packet: bytes | bytearray | memoryview,
    *,
    expected_type: OkuaPacketType | None = None,
) -> OkuaPacket:
    payload = bytes(raw_packet)
    header = parse_okua_header(payload)

    if header.packet_type not in {OkuaPacketType.EVT, OkuaPacketType.STAT}:
        raise OkuaPacketParseError(
            "unsupported_packet_type",
            f"Tipo {header.packet_type.name} no soportado en este ticket.",
        )

    if expected_type is not None and header.packet_type is not expected_type:
        raise OkuaPacketParseError(
            "unexpected_packet_type",
            (
                "Tipo de paquete inesperado para este canal: "
                f"llego {header.packet_type.name}, esperado {expected_type.name}."
            ),
        )

    expected_len = (
        OKUA_EVT_PACKET_SIZE
        if header.packet_type is OkuaPacketType.EVT
        else OKUA_STAT_PACKET_SIZE
    )
    actual_len = len(payload)
    if actual_len != expected_len:
        if actual_len < expected_len:
            code = "truncated_packet"
        else:
            code = "invalid_length"
        raise OkuaPacketParseError(
            code,
            (
                f"Longitud invalida para {header.packet_type.name}: "
                f"esperada {expected_len}, recibida {actual_len}."
            ),
        )

    body = payload[OKUA_HEADER_SIZE:]
    if header.packet_type is OkuaPacketType.EVT:
        (
            midi_bus,
            midi_ch,
            note,
            vel,
            ts_ms,
            rssi_dbm,
            flags,
            rsv_raw,
        ) = _EVT_PAYLOAD_STRUCT.unpack(body)
        return OkuaEvtPacket(
            header=header,
            midi_bus=midi_bus,
            midi_ch=midi_ch,
            note=note,
            vel=vel,
            ts_ms=ts_ms,
            rssi_dbm=rssi_dbm,
            flags=flags,
            rsv=tuple(rsv_raw),
        )

    (
        uptime_s,
        rssi_dbm,
        state_flags,
        pps_x10,
        vbat_mv,
        free_heap,
        fw_major,
        fw_minor,
        reset_reason,
        rsv_raw,
    ) = _STAT_PAYLOAD_STRUCT.unpack(body)
    ota_runtime = decode_okua_ota_runtime(tuple(rsv_raw))
    return OkuaStatPacket(
        header=header,
        uptime_s=uptime_s,
        rssi_dbm=rssi_dbm,
        state_flags=state_flags,
        pps_x10=pps_x10,
        vbat_mv=vbat_mv,
        free_heap=free_heap,
        fw_major=fw_major,
        fw_minor=fw_minor,
        reset_reason=reset_reason,
        rsv=tuple(rsv_raw),
        ota_state_code=ota_runtime.state_code,
        ota_error_code=ota_runtime.error_code,
        ota_flags=ota_runtime.flags,
    )
