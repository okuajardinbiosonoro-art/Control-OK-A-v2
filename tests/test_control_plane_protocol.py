from __future__ import annotations

import struct

from control_okua.core.control_plane.auth import compute_auth_tag32
from control_okua.core.control_plane.protocol import (
    CMD_FLAG_ACK_REQUIRED,
    CmdSequenceManager,
    OKUA_CMD_PACKET_SIZE,
    OKUA_TYPE_CMD,
    SET_THROTTLE_ALLOWED_PERCENT,
    SET_STAT_RATE_ALLOWED_MS,
    OkuaCmdId,
    build_ota_check_now_command,
    build_ping_command,
    build_request_stat_now_command,
    build_set_throttle_command,
    build_set_stat_rate_command,
)
from control_okua.core.udp.packet_models import OKUA_MAGIC, OKUA_VERSION

_CMD_STRUCT = struct.Struct("<HBBHHBBHHQ2sI")


def test_okua_cmd_serializes_28_bytes_little_endian_and_cmd_header_fields() -> None:
    secret = b"ticket-14-1-secret"
    packet = build_ping_command(
        secret=secret,
        node_id_target=0x1234,
        cmd_seq=0xBEEF,
        nonce=0x1122334455667788,
    )
    (
        magic,
        version,
        packet_type,
        node_id_target,
        cmd_seq,
        cmd_id,
        cmd_flags,
        arg0,
        arg1,
        nonce,
        rsv0,
        auth_tag32,
    ) = _CMD_STRUCT.unpack(packet)

    assert len(packet) == OKUA_CMD_PACKET_SIZE
    assert packet[0:2] == b"\x4F\x4B"  # 0x4B4F in little-endian
    assert packet[4:6] == b"\x34\x12"
    assert packet[6:8] == b"\xEF\xBE"
    assert magic == OKUA_MAGIC
    assert version == OKUA_VERSION
    assert packet_type == OKUA_TYPE_CMD
    assert node_id_target == 0x1234
    assert cmd_seq == 0xBEEF  # cmd_seq = hdr.seq
    assert cmd_id == int(OkuaCmdId.PING)
    assert cmd_flags == CMD_FLAG_ACK_REQUIRED
    assert arg0 == 0
    assert arg1 == 0
    assert nonce == 0x1122334455667788
    assert rsv0 == b"\x00\x00"
    assert auth_tag32 == compute_auth_tag32(secret, packet[:24])


def test_auth_tag32_is_derived_from_bytes_0_23_only() -> None:
    secret = b"ticket-14-1-secret"
    packet = build_request_stat_now_command(
        secret=secret,
        node_id_target=77,
        cmd_seq=10,
        nonce=0xABCDEF0011223344,
    )
    original_tag = int.from_bytes(packet[24:28], byteorder="little", signed=False)

    assert original_tag == compute_auth_tag32(secret, packet[:24])

    mutated_prefix = bytearray(packet)
    mutated_prefix[23] ^= 0x01
    assert compute_auth_tag32(secret, bytes(mutated_prefix[:24])) != original_tag

    mutated_auth_bytes = bytearray(packet)
    mutated_auth_bytes[24] ^= 0x7F
    assert compute_auth_tag32(secret, bytes(mutated_auth_bytes[:24])) == original_tag


def test_cmd_seq_manager_is_monotonic_and_reflected_in_hdr_seq() -> None:
    seq_manager = CmdSequenceManager(start_seq=1000)
    secret = b"ticket-14-1-secret"

    seq1 = seq_manager.next_cmd_seq()
    packet1 = build_ping_command(
        secret=secret,
        node_id_target=12,
        cmd_seq=seq1,
        nonce=1,
    )
    unpacked1 = _CMD_STRUCT.unpack(packet1)

    seq2 = seq_manager.next_cmd_seq()
    packet2 = build_ping_command(
        secret=secret,
        node_id_target=12,
        cmd_seq=seq2,
        nonce=2,
    )
    unpacked2 = _CMD_STRUCT.unpack(packet2)

    assert seq1 == 1000
    assert seq2 == 1001
    assert unpacked1[4] == seq1
    assert unpacked2[4] == seq2


def test_set_stat_rate_command_serializes_allowlist_value() -> None:
    secret = b"ticket-17-2-secret"
    packet = build_set_stat_rate_command(
        secret=secret,
        node_id_target=12,
        cmd_seq=321,
        nonce=0x0102030405060708,
        stat_rate_ms=2000,
    )
    unpacked = _CMD_STRUCT.unpack(packet)

    assert len(packet) == OKUA_CMD_PACKET_SIZE
    assert unpacked[5] == int(OkuaCmdId.SET_STAT_RATE)
    assert unpacked[7] == 2000
    assert unpacked[8] == 0
    assert unpacked[6] == CMD_FLAG_ACK_REQUIRED


def test_set_stat_rate_command_rejects_values_outside_allowlist() -> None:
    secret = b"ticket-17-2-secret"
    assert SET_STAT_RATE_ALLOWED_MS == (1000, 2000, 5000)

    try:
        build_set_stat_rate_command(
            secret=secret,
            node_id_target=12,
            cmd_seq=1,
            nonce=1,
            stat_rate_ms=1500,
        )
    except ValueError as exc:
        assert "stat_rate_ms invalido" in str(exc)
    else:
        raise AssertionError("Se esperaba ValueError para stat_rate_ms fuera de allowlist.")


def test_set_throttle_command_serializes_allowlist_value() -> None:
    secret = b"ticket-18-2-secret"
    packet = build_set_throttle_command(
        secret=secret,
        node_id_target=12,
        cmd_seq=654,
        nonce=0x0807060504030201,
        throttle_percent=50,
    )
    unpacked = _CMD_STRUCT.unpack(packet)

    assert len(packet) == OKUA_CMD_PACKET_SIZE
    assert unpacked[5] == int(OkuaCmdId.SET_THROTTLE)
    assert unpacked[7] == 50
    assert unpacked[8] == 0
    assert unpacked[6] == CMD_FLAG_ACK_REQUIRED


def test_set_throttle_command_rejects_values_outside_allowlist() -> None:
    secret = b"ticket-18-2-secret"
    assert SET_THROTTLE_ALLOWED_PERCENT == (25, 50, 100)

    try:
        build_set_throttle_command(
            secret=secret,
            node_id_target=12,
            cmd_seq=1,
            nonce=1,
            throttle_percent=75,
        )
    except ValueError as exc:
        assert "throttle_percent invalido" in str(exc)
    else:
        raise AssertionError("Se esperaba ValueError para throttle_percent fuera de allowlist.")


def test_ota_check_now_command_serializes_rollout_token_across_arg0_arg1() -> None:
    secret = b"ticket-25-secret"
    packet = build_ota_check_now_command(
        secret=secret,
        node_id_target=22,
        cmd_seq=77,
        nonce=0x0102030405060708,
        rollout_token=0x20260328,
    )
    unpacked = _CMD_STRUCT.unpack(packet)

    assert len(packet) == OKUA_CMD_PACKET_SIZE
    assert unpacked[5] == int(OkuaCmdId.OTA_CHECK_NOW)
    assert unpacked[7] == 0x0328
    assert unpacked[8] == 0x2026
    assert unpacked[6] == CMD_FLAG_ACK_REQUIRED
