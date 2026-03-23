from __future__ import annotations

import struct

from control_okua.core.control_plane.pending import (
    AckCorrelationStatus,
    PendingCommandStore,
)
from control_okua.core.control_plane.protocol import OKUA_TYPE_ACK, parse_okua_ack_bytes
from control_okua.core.udp.packet_models import OKUA_MAGIC, OKUA_VERSION
from control_okua.services.cmd_service import SentOkuaCommand

_ACK_STRUCT = struct.Struct("<HBBHHBBBBHHQI")


def _build_ack_packet(
    *,
    node_id: int = 12,
    cmd_seq: int = 500,
    cmd_id_echo: int = 0x01,
    nonce_echo: int = 0x1111222233334444,
    ack_stage: int = 1,
    status_code: int = 0x00,
    err_detail: int = 0,
    retry_after_ms: int = 0,
    auth_tag32: int = 0xAABBCCDD,
) -> bytes:
    return _ACK_STRUCT.pack(
        OKUA_MAGIC,
        OKUA_VERSION,
        OKUA_TYPE_ACK,
        node_id & 0xFFFF,
        cmd_seq & 0xFFFF,
        cmd_id_echo & 0xFF,
        ack_stage & 0xFF,
        status_code & 0xFF,
        0,
        err_detail & 0xFFFF,
        retry_after_ms & 0xFFFF,
        nonce_echo & 0xFFFFFFFFFFFFFFFF,
        auth_tag32 & 0xFFFFFFFF,
    )


def test_pending_command_store_correlates_sent_command_and_ack() -> None:
    store = PendingCommandStore(clock=lambda: 100.0)
    sent = SentOkuaCommand(
        source="manual",
        command_name="PING",
        cmd_id=0x01,
        node_ip="192.168.1.55",
        node_id=12,
        cmd_seq=500,
        nonce=0x1111222233334444,
        target_port=5007,
        packet=b"\x00" * 28,
        bytes_sent=28,
    )
    store.register_sent_command(sent)

    ack = parse_okua_ack_bytes(
        _build_ack_packet(
            cmd_seq=500,
            cmd_id_echo=0x01,
            nonce_echo=0x1111222233334444,
        )
    )
    result = store.correlate_parsed_ack(
        ack,
        source_ip="192.168.1.55",
        source_port=5008,
        received_ts=101.0,
    )

    assert result.status is AckCorrelationStatus.MATCHED
    assert result.sent_command == sent
    assert result.ack == ack
    assert result.source_port == 5008
    assert store.pending_count == 0


def test_pending_command_store_classifies_orphan_ack_as_unmatched() -> None:
    store = PendingCommandStore(clock=lambda: 200.0)
    orphan_ack = parse_okua_ack_bytes(
        _build_ack_packet(
            cmd_seq=999,
            cmd_id_echo=0x07,
            nonce_echo=0xABCDEF0000000001,
        )
    )
    result = store.correlate_parsed_ack(
        orphan_ack,
        source_ip="10.0.0.77",
        source_port=5008,
    )

    assert result.status is AckCorrelationStatus.UNMATCHED_ACK
    assert result.sent_command is None
    assert result.ack == orphan_ack
    assert store.pending_count == 0


def test_pending_command_store_classifies_invalid_ack_datagram() -> None:
    store = PendingCommandStore(clock=lambda: 300.0)
    result = store.correlate_ack_datagram(
        b"\x01\x02\x03",
        source_ip="10.0.0.88",
        source_port=5008,
    )

    assert result.status is AckCorrelationStatus.INVALID_ACK
    assert result.ack is None
    assert result.sent_command is None
    assert result.parse_error_code == "invalid_size"
