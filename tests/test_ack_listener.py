from __future__ import annotations

import socket
import struct

from control_okua.core.control_plane.pending import AckCorrelationStatus, PendingCommandStore
from control_okua.core.control_plane.protocol import OKUA_ACK_PORT, OKUA_TYPE_ACK
from control_okua.core.udp.packet_models import OKUA_MAGIC, OKUA_VERSION
from control_okua.services.ack_listener import AckListenerService
from control_okua.services.cmd_service import SentOkuaCommand

_ACK_STRUCT = struct.Struct("<HBBHHBBBBHHQI")


def _build_ack_packet(
    *,
    cmd_seq: int,
    cmd_id_echo: int,
    nonce_echo: int,
    node_id: int = 12,
    ack_stage: int = 1,
    status_code: int = 0,
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
        0,
        0,
        nonce_echo & 0xFFFFFFFFFFFFFFFF,
        0x00112233,
    )


class _FakeAckSocket:
    def __init__(self) -> None:
        self.bound_address: tuple[str, int] | None = None
        self.timeout_value: float | None = None
        self.closed = False
        self.recv_queue: list[tuple[bytes, tuple[str, int]]] = []

    def bind(self, address: tuple[str, int]) -> None:
        self.bound_address = address

    def settimeout(self, value: float) -> None:
        self.timeout_value = float(value)

    def recvfrom(self, _bufsize: int) -> tuple[bytes, tuple[str, int]]:
        if not self.recv_queue:
            raise socket.timeout()
        return self.recv_queue.pop(0)

    def close(self) -> None:
        self.closed = True

    def fileno(self) -> int:
        return -1 if self.closed else 99


def test_ack_listener_binds_to_ack_port_5008_and_is_pollable_without_ui() -> None:
    fake_socket = _FakeAckSocket()
    listener = AckListenerService(
        bind_ip="127.0.0.1",
        ack_port=OKUA_ACK_PORT,
        socket_factory=lambda: fake_socket,
        timeout_s=0.01,
    )

    started = listener.start()
    polled = listener.poll_once()
    listener.stop()

    assert started is True
    assert fake_socket.bound_address == ("127.0.0.1", OKUA_ACK_PORT)
    assert polled is None
    assert fake_socket.closed is True


def test_ack_listener_poll_once_returns_matched_correlation_result() -> None:
    fake_socket = _FakeAckSocket()
    store = PendingCommandStore(clock=lambda: 1000.0)
    listener = AckListenerService(
        bind_ip="127.0.0.1",
        socket_factory=lambda: fake_socket,
        pending_store=store,
        clock=lambda: 1001.0,
    )
    listener.start()

    sent = SentOkuaCommand(
        source="manual",
        command_name="REQUEST_STAT_NOW",
        cmd_id=0x07,
        node_ip="127.0.0.1",
        node_id=12,
        cmd_seq=321,
        nonce=0xAA00000000000001,
        target_port=5007,
        packet=b"\x00" * 28,
        bytes_sent=28,
    )
    listener.register_pending_command(sent)
    fake_socket.recv_queue.append(
        (
            _build_ack_packet(
                cmd_seq=321,
                cmd_id_echo=0x07,
                nonce_echo=0xAA00000000000001,
            ),
            ("127.0.0.1", 5008),
        )
    )

    result = listener.poll_once()
    listener.stop()

    assert result is not None
    assert result.status is AckCorrelationStatus.MATCHED
    assert result.sent_command == sent
    assert result.ack is not None
    assert result.ack.cmd_seq == 321
    assert result.source_port == 5008


def test_ack_listener_poll_once_classifies_invalid_ack_datagram() -> None:
    fake_socket = _FakeAckSocket()
    listener = AckListenerService(
        bind_ip="127.0.0.1",
        socket_factory=lambda: fake_socket,
        clock=lambda: 77.0,
    )
    listener.start()
    fake_socket.recv_queue.append((b"\x01\x02", ("127.0.0.1", 5008)))

    result = listener.poll_once()
    listener.stop()

    assert result is not None
    assert result.status is AckCorrelationStatus.INVALID_ACK
    assert result.parse_error_code == "invalid_size"
