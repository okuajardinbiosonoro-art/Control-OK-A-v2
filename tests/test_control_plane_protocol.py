from __future__ import annotations

import struct

from control_okua.core.control_plane.auth import compute_auth_tag32
from control_okua.core.control_plane.protocol import (
    CMD_FLAG_ACK_REQUIRED,
    CmdSequenceManager,
    OKUA_CMD_PACKET_SIZE,
    OKUA_TYPE_CMD,
    OkuaCmdId,
    build_ping_command,
    build_request_stat_now_command,
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
