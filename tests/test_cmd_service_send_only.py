from __future__ import annotations

from control_okua.core.control_plane.nonce_manager import NonceManager
from control_okua.core.control_plane.protocol import (
    OKUA_CMD_PACKET_SIZE,
    OKUA_CMD_PORT,
    CmdSequenceManager,
)
from control_okua.services.cmd_service import CmdService


class _FakeSendOnlySocket:
    def __init__(self) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []
        self.bind_calls: list[tuple[str, int]] = []
        self.recvfrom_calls = 0
        self.closed = False

    def sendto(self, data: bytes, address: tuple[str, int]) -> int:
        self.sent.append((bytes(data), address))
        return len(data)

    def bind(self, address: tuple[str, int]) -> None:
        self.bind_calls.append(address)
        raise AssertionError("CmdService no debe abrir listener ACK en este ticket.")

    def recvfrom(self, _bufsize: int):
        self.recvfrom_calls += 1
        raise AssertionError("CmdService no debe recibir ACK en este ticket.")

    def close(self) -> None:
        self.closed = True


def test_cmd_service_sends_cmd_to_port_5007_without_ack_listener(tmp_path) -> None:
    created_sockets: list[_FakeSendOnlySocket] = []

    def socket_factory() -> _FakeSendOnlySocket:
        sock = _FakeSendOnlySocket()
        created_sockets.append(sock)
        return sock

    service = CmdService(
        secret=b"ticket-14-1-secret",
        nonce_manager=NonceManager(
            state_path=tmp_path / "control_plane_state.json",
            time_provider=lambda: 1_800_000_000,
        ),
        seq_manager=CmdSequenceManager(start_seq=321),
        socket_factory=socket_factory,
    )
    sent = service.send_ping("192.168.0.80", 12, source="manual")

    assert len(created_sockets) == 1
    fake_socket = created_sockets[0]
    assert fake_socket.closed is True
    assert fake_socket.recvfrom_calls == 0
    assert fake_socket.bind_calls == []
    assert len(fake_socket.sent) == 1
    payload, target = fake_socket.sent[0]
    assert target == ("192.168.0.80", OKUA_CMD_PORT)
    assert len(payload) == OKUA_CMD_PACKET_SIZE

    assert sent.target_port == OKUA_CMD_PORT
    assert sent.cmd_seq == 321
    assert sent.bytes_sent == OKUA_CMD_PACKET_SIZE
    assert sent.command_name == "PING"


def test_cmd_service_cmd_seq_increments_for_new_logical_commands(tmp_path) -> None:
    created_sockets: list[_FakeSendOnlySocket] = []

    def socket_factory() -> _FakeSendOnlySocket:
        sock = _FakeSendOnlySocket()
        created_sockets.append(sock)
        return sock

    service = CmdService(
        secret=b"ticket-14-1-secret",
        nonce_manager=NonceManager(
            state_path=tmp_path / "control_plane_state.json",
            time_provider=lambda: 1_900_000_000,
        ),
        seq_manager=CmdSequenceManager(start_seq=1000),
        socket_factory=socket_factory,
    )
    sent_1 = service.send_request_stat_now("10.0.0.15", 33)
    sent_2 = service.send_reboot_soft("10.0.0.15", 33, delay_ms=200)

    assert sent_1.cmd_seq == 1000
    assert sent_2.cmd_seq == 1001
    assert sent_1.target_port == OKUA_CMD_PORT
    assert sent_2.target_port == OKUA_CMD_PORT
    assert len(created_sockets) == 2
    assert all(entry[1][1] == OKUA_CMD_PORT for sock in created_sockets for entry in sock.sent)
