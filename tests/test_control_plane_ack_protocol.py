from __future__ import annotations

import struct

import pytest

from control_okua.core.control_plane.protocol import (
    AckParseError,
    AckParseErrorCode,
    OKUA_ACK_PACKET_SIZE,
    OKUA_TYPE_ACK,
    parse_okua_ack_bytes,
)
from control_okua.core.udp.packet_models import OKUA_MAGIC, OKUA_VERSION

_ACK_STRUCT = struct.Struct("<HBBHHBBBBHHQI")


def _build_ack_packet(
    *,
    magic: int = OKUA_MAGIC,
    version: int = OKUA_VERSION,
    packet_type: int = OKUA_TYPE_ACK,
    node_id: int = 12,
    cmd_seq: int = 101,
    cmd_id_echo: int = 0x07,
    ack_stage: int = 1,
    status_code: int = 0x00,
    ack_flags: int = 0x00,
    err_detail: int = 0x0000,
    retry_after_ms: int = 0,
    nonce_echo: int = 0x1122334455667788,
    auth_tag32: int = 0xA1B2C3D4,
) -> bytes:
    return _ACK_STRUCT.pack(
        magic & 0xFFFF,
        version & 0xFF,
        packet_type & 0xFF,
        node_id & 0xFFFF,
        cmd_seq & 0xFFFF,
        cmd_id_echo & 0xFF,
        ack_stage & 0xFF,
        status_code & 0xFF,
        ack_flags & 0xFF,
        err_detail & 0xFFFF,
        retry_after_ms & 0xFFFF,
        nonce_echo & 0xFFFFFFFFFFFFFFFF,
        auth_tag32 & 0xFFFFFFFF,
    )


def test_parse_okua_ack_bytes_valid_28b_packet_extracts_expected_fields() -> None:
    raw = _build_ack_packet(
        node_id=22,
        cmd_seq=0x4455,
        cmd_id_echo=0x02,
        ack_stage=1,
        status_code=0x00,
        err_detail=0x000A,
        retry_after_ms=150,
        nonce_echo=0x0102030405060708,
        auth_tag32=0x89ABCDEF,
    )
    parsed = parse_okua_ack_bytes(raw)

    assert len(raw) == OKUA_ACK_PACKET_SIZE
    assert parsed.node_id_source == 22
    assert parsed.cmd_seq == 0x4455
    assert parsed.cmd_id_echo == 0x02
    assert parsed.nonce_echo == 0x0102030405060708
    assert parsed.ack_stage == 1
    assert parsed.status_code == 0x00
    assert parsed.err_detail == 0x000A
    assert parsed.retry_after_ms == 150
    assert parsed.auth_tag32 == 0x89ABCDEF


def test_parse_okua_ack_bytes_rejects_invalid_size() -> None:
    with pytest.raises(AckParseError) as exc_info:
        parse_okua_ack_bytes(b"\x00" * 27)
    assert exc_info.value.code is AckParseErrorCode.INVALID_SIZE


def test_parse_okua_ack_bytes_rejects_invalid_magic() -> None:
    raw = _build_ack_packet(magic=0x0001)
    with pytest.raises(AckParseError) as exc_info:
        parse_okua_ack_bytes(raw)
    assert exc_info.value.code is AckParseErrorCode.INVALID_MAGIC


def test_parse_okua_ack_bytes_rejects_invalid_version() -> None:
    raw = _build_ack_packet(version=0x09)
    with pytest.raises(AckParseError) as exc_info:
        parse_okua_ack_bytes(raw)
    assert exc_info.value.code is AckParseErrorCode.INVALID_VERSION


def test_parse_okua_ack_bytes_rejects_invalid_type() -> None:
    raw = _build_ack_packet(packet_type=0x03)
    with pytest.raises(AckParseError) as exc_info:
        parse_okua_ack_bytes(raw)
    assert exc_info.value.code is AckParseErrorCode.INVALID_TYPE
