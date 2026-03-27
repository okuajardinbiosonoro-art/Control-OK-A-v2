from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import Callable, Protocol

from control_okua.core.control_plane.auth import (
    ControlSecretError,
    resolve_control_secret,
)
from control_okua.core.control_plane.nonce_manager import NonceManager
from control_okua.core.control_plane.protocol import (
    OKUA_CMD_PACKET_SIZE,
    OKUA_CMD_PORT,
    CmdSequenceManager,
    OkuaCmdId,
    build_ping_command,
    build_reboot_soft_command,
    build_request_stat_now_command,
    build_set_stat_rate_command,
    build_set_throttle_command,
)


class CmdSendSocketLike(Protocol):
    def sendto(self, data: bytes, address: tuple[str, int]) -> int:
        ...

    def close(self) -> None:
        ...


CmdSocketFactory = Callable[[], CmdSendSocketLike]


class CmdServiceError(RuntimeError):
    """Base error for CMD send-only service operations."""


class CmdServiceConfigError(CmdServiceError):
    """Raised when CMD service configuration is missing or invalid."""


class CmdServiceSendError(CmdServiceError):
    """Raised when UDP send operation fails."""


@dataclass(frozen=True)
class SentOkuaCommand:
    source: str
    command_name: str
    cmd_id: int
    node_ip: str
    node_id: int
    cmd_seq: int
    nonce: int
    target_port: int
    packet: bytes
    bytes_sent: int


def default_cmd_socket_factory() -> CmdSendSocketLike:
    return socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


class CmdService:
    """
    Minimal send-only service for F3 OKUA_CMD emission.

    This service intentionally does not bind/listen ACK sockets, parse ACK, or manage retries.
    """

    def __init__(
        self,
        *,
        secret: str | bytes | None = None,
        nonce_manager: NonceManager | None = None,
        seq_manager: CmdSequenceManager | None = None,
        socket_factory: CmdSocketFactory | None = None,
        cmd_port: int = OKUA_CMD_PORT,
    ) -> None:
        try:
            self._secret = resolve_control_secret(secret)
        except ControlSecretError as exc:
            raise CmdServiceConfigError(str(exc)) from exc

        self._nonce_manager = nonce_manager or NonceManager()
        self._seq_manager = seq_manager or CmdSequenceManager()
        self._socket_factory = socket_factory or default_cmd_socket_factory
        self._cmd_port = _validate_udp_port(cmd_port)

    def send_ping(self, node_ip: str, node_id: int, *, source: str = "manual") -> SentOkuaCommand:
        return self._send_new_command(
            node_ip=node_ip,
            node_id=node_id,
            source=source,
            command_name="PING",
            cmd_id=int(OkuaCmdId.PING),
            packet_builder=lambda resolved_node_id, cmd_seq, nonce: build_ping_command(
                secret=self._secret,
                node_id_target=resolved_node_id,
                cmd_seq=cmd_seq,
                nonce=nonce,
            ),
        )

    def send_request_stat_now(
        self,
        node_ip: str,
        node_id: int,
        *,
        source: str = "manual",
    ) -> SentOkuaCommand:
        return self._send_new_command(
            node_ip=node_ip,
            node_id=node_id,
            source=source,
            command_name="REQUEST_STAT_NOW",
            cmd_id=int(OkuaCmdId.REQUEST_STAT_NOW),
            packet_builder=lambda resolved_node_id, cmd_seq, nonce: build_request_stat_now_command(
                secret=self._secret,
                node_id_target=resolved_node_id,
                cmd_seq=cmd_seq,
                nonce=nonce,
            ),
        )

    def send_reboot_soft(
        self,
        node_ip: str,
        node_id: int,
        *,
        delay_ms: int = 0,
        source: str = "manual",
    ) -> SentOkuaCommand:
        return self._send_new_command(
            node_ip=node_ip,
            node_id=node_id,
            source=source,
            command_name="REBOOT_SOFT",
            cmd_id=int(OkuaCmdId.REBOOT_SOFT),
            packet_builder=lambda resolved_node_id, cmd_seq, nonce: build_reboot_soft_command(
                secret=self._secret,
                node_id_target=resolved_node_id,
                cmd_seq=cmd_seq,
                nonce=nonce,
                delay_ms=delay_ms,
            ),
        )

    def send_set_stat_rate(
        self,
        node_ip: str,
        node_id: int,
        *,
        stat_rate_ms: int,
        source: str = "manual",
    ) -> SentOkuaCommand:
        return self._send_new_command(
            node_ip=node_ip,
            node_id=node_id,
            source=source,
            command_name="SET_STAT_RATE",
            cmd_id=int(OkuaCmdId.SET_STAT_RATE),
            packet_builder=lambda resolved_node_id, cmd_seq, nonce: build_set_stat_rate_command(
                secret=self._secret,
                node_id_target=resolved_node_id,
                cmd_seq=cmd_seq,
                nonce=nonce,
                stat_rate_ms=stat_rate_ms,
            ),
        )

    def send_set_throttle(
        self,
        node_ip: str,
        node_id: int,
        *,
        throttle_percent: int,
        source: str = "manual",
    ) -> SentOkuaCommand:
        return self._send_new_command(
            node_ip=node_ip,
            node_id=node_id,
            source=source,
            command_name="SET_THROTTLE",
            cmd_id=int(OkuaCmdId.SET_THROTTLE),
            packet_builder=lambda resolved_node_id, cmd_seq, nonce: build_set_throttle_command(
                secret=self._secret,
                node_id_target=resolved_node_id,
                cmd_seq=cmd_seq,
                nonce=nonce,
                throttle_percent=throttle_percent,
            ),
        )

    def resend_sent_command(
        self,
        sent_command: SentOkuaCommand,
        *,
        source: str = "retry",
    ) -> SentOkuaCommand:
        """
        Resend an already-built logical command preserving cmd_seq/nonce/packet bytes.
        Used by transaction retry logic (idempotent app-side retry).
        """
        resolved_source = source.strip() if isinstance(source, str) and source.strip() else "retry"
        bytes_sent = self._send_packet(
            packet=sent_command.packet,
            node_ip=sent_command.node_ip,
        )
        return SentOkuaCommand(
            source=resolved_source,
            command_name=sent_command.command_name,
            cmd_id=sent_command.cmd_id,
            node_ip=sent_command.node_ip,
            node_id=sent_command.node_id,
            cmd_seq=sent_command.cmd_seq,
            nonce=sent_command.nonce,
            target_port=sent_command.target_port,
            packet=sent_command.packet,
            bytes_sent=bytes_sent,
        )

    def _send_new_command(
        self,
        *,
        node_ip: str,
        node_id: int,
        source: str,
        command_name: str,
        cmd_id: int,
        packet_builder: Callable[[int, int, int], bytes],
    ) -> SentOkuaCommand:
        resolved_node_ip = _normalize_node_ip(node_ip)
        resolved_node_id = _validate_unicast_node_id(node_id)
        resolved_source = source.strip() if isinstance(source, str) and source.strip() else "manual"

        cmd_seq = self._seq_manager.next_cmd_seq()
        nonce = self._nonce_manager.next_nonce()
        packet = packet_builder(resolved_node_id, cmd_seq, nonce)
        bytes_sent = self._send_packet(packet=packet, node_ip=resolved_node_ip)

        return SentOkuaCommand(
            source=resolved_source,
            command_name=command_name,
            cmd_id=cmd_id,
            node_ip=resolved_node_ip,
            node_id=resolved_node_id,
            cmd_seq=cmd_seq,
            nonce=nonce,
            target_port=self._cmd_port,
            packet=packet,
            bytes_sent=bytes_sent,
        )

    def _send_packet(self, *, packet: bytes, node_ip: str) -> int:
        payload = bytes(packet)
        if len(payload) != OKUA_CMD_PACKET_SIZE:
            raise CmdServiceSendError(
                f"Longitud de CMD invalida: {len(payload)} (esperado {OKUA_CMD_PACKET_SIZE})."
            )

        sock = self._socket_factory()
        try:
            sent = int(sock.sendto(payload, (node_ip, self._cmd_port)))
        except OSError as exc:
            raise CmdServiceSendError(
                f"No se pudo enviar OKUA_CMD a {node_ip}:{self._cmd_port}: {exc}"
            ) from exc
        finally:
            try:
                sock.close()
            except Exception:
                pass

        if sent != len(payload):
            raise CmdServiceSendError(
                f"Envio UDP incompleto: {sent}/{len(payload)} bytes a {node_ip}:{self._cmd_port}."
            )
        return sent


def _validate_udp_port(port: int) -> int:
    resolved = int(port)
    if resolved < 1 or resolved > 65535:
        raise CmdServiceConfigError(f"cmd_port fuera de rango (1..65535): {port}")
    return resolved


def _validate_unicast_node_id(node_id: int) -> int:
    resolved = int(node_id)
    if resolved < 1 or resolved > 0xFFFF:
        raise ValueError(
            f"node_id debe ser unicast valido (1..65535) para este ticket, recibido: {node_id}"
        )
    return resolved


def _normalize_node_ip(node_ip: str) -> str:
    if not isinstance(node_ip, str):
        raise ValueError("node_ip debe ser string no vacio.")
    resolved = node_ip.strip()
    if not resolved:
        raise ValueError("node_ip debe ser string no vacio.")
    return resolved
