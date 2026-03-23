from __future__ import annotations

import ipaddress
import socket
import time
from typing import Callable, Protocol

from control_okua.core.control_plane.pending import (
    AckCorrelationResult,
    PendingCommandStore,
    SentCommandLike,
)
from control_okua.core.control_plane.protocol import OKUA_ACK_PORT


class AckSocketLike(Protocol):
    def bind(self, address: tuple[str, int]) -> None:
        ...

    def recvfrom(self, bufsize: int) -> tuple[bytes, tuple[str, int]]:
        ...

    def close(self) -> None:
        ...

    def settimeout(self, value: float) -> None:
        ...

    def fileno(self) -> int:
        ...


AckSocketFactory = Callable[[], AckSocketLike]


class AckListenerError(RuntimeError):
    """Base error for ACK listener service."""


class AckListenerConfigError(AckListenerError):
    """Raised when ACK listener configuration is invalid."""


class AckListenerOpenError(AckListenerError):
    """Raised when ACK listener cannot bind/open UDP socket."""


def default_ack_socket_factory() -> AckSocketLike:
    return socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


class AckListenerService:
    """Minimal ACK UDP listener with strict parse + basic correlation."""

    def __init__(
        self,
        *,
        bind_ip: str = "0.0.0.0",
        ack_port: int = OKUA_ACK_PORT,
        recv_size: int = 2048,
        timeout_s: float = 0.05,
        socket_factory: AckSocketFactory | None = None,
        pending_store: PendingCommandStore | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._bind_ip = _validate_bind_ip(bind_ip)
        self._ack_port = _validate_port(ack_port)
        self._recv_size = _validate_positive_int("recv_size", recv_size)
        self._timeout_s = _validate_timeout(timeout_s)
        self._socket_factory = socket_factory or default_ack_socket_factory
        self._pending_store = pending_store or PendingCommandStore()
        self._clock = clock or time.monotonic
        self._socket: AckSocketLike | None = None

    @property
    def ack_port(self) -> int:
        return self._ack_port

    @property
    def pending_store(self) -> PendingCommandStore:
        return self._pending_store

    def start(self) -> bool:
        if self.is_running():
            return False
        sock = self._socket_factory()
        try:
            sock.settimeout(self._timeout_s)
            sock.bind((self._bind_ip, self._ack_port))
        except OSError as exc:
            try:
                sock.close()
            except Exception:
                pass
            raise AckListenerOpenError(
                f"No se pudo abrir ACK listener en {self._bind_ip}:{self._ack_port}: {exc}"
            ) from exc

        self._socket = sock
        return True

    def stop(self) -> None:
        sock = self._socket
        self._socket = None
        if sock is None:
            return
        try:
            sock.close()
        except OSError as exc:
            raise AckListenerError(f"No se pudo cerrar ACK listener: {exc}") from exc

    def is_running(self) -> bool:
        sock = self._socket
        if sock is None:
            return False
        try:
            return sock.fileno() >= 0
        except OSError:
            return False

    def register_pending_command(self, sent_command: SentCommandLike) -> None:
        self._pending_store.register_sent_command(sent_command)

    def poll_once(self) -> AckCorrelationResult | None:
        sock = self._socket
        if sock is None:
            raise AckListenerError("ACK listener no esta iniciado.")

        try:
            payload, address = sock.recvfrom(self._recv_size)
        except socket.timeout:
            return None
        except OSError as exc:
            raise AckListenerError(f"Error recibiendo ACK UDP: {exc}") from exc

        source_ip, source_port = _normalize_address(address)
        received_ts = float(self._clock())
        return self._pending_store.correlate_ack_datagram(
            payload,
            source_ip=source_ip,
            source_port=source_port,
            received_ts=received_ts,
        )


def _validate_bind_ip(bind_ip: str) -> str:
    if not isinstance(bind_ip, str) or not bind_ip.strip():
        raise AckListenerConfigError("bind_ip invalido para ACK listener.")
    resolved = bind_ip.strip()
    try:
        ipaddress.ip_address(resolved)
    except ValueError as exc:
        raise AckListenerConfigError(f"bind_ip invalido para ACK listener: '{resolved}'.") from exc
    return resolved


def _validate_port(port: int) -> int:
    resolved = int(port)
    if resolved < 1 or resolved > 65535:
        raise AckListenerConfigError(f"ack_port fuera de rango (1..65535): {port}")
    return resolved


def _validate_positive_int(field_name: str, value: int) -> int:
    resolved = int(value)
    if resolved < 1:
        raise AckListenerConfigError(f"{field_name} debe ser > 0, recibido {value}.")
    return resolved


def _validate_timeout(value: float) -> float:
    resolved = float(value)
    if resolved <= 0:
        raise AckListenerConfigError(f"timeout_s debe ser > 0, recibido {value}.")
    return resolved


def _normalize_address(address: tuple[str, int]) -> tuple[str, int]:
    if len(address) < 2:
        return "0.0.0.0", 0
    return str(address[0]), int(address[1])
