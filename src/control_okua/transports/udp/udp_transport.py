from __future__ import annotations

import ipaddress
import socket
import threading
import time
from collections import deque
from typing import Callable, Protocol

from control_okua.core.udp.packet_models import (
    OkuaEvtPacket,
    OkuaPacket,
    OkuaPacketType,
    OkuaStatPacket,
)
from control_okua.core.udp.packet_parser import OkuaPacketParseError, parse_okua_packet
from control_okua.transports.udp.udp_models import (
    UdpReceivedEvtPacket,
    UdpReceivedStatPacket,
    UdpRuntimeEvent,
    UdpTransportConfig,
    UdpTransportMetrics,
    UdpTransportSnapshot,
)


class UdpSocketLike(Protocol):
    def bind(self, address: tuple[str, int]) -> None:
        ...

    def recvfrom(self, bufsize: int) -> tuple[bytes, tuple[str, int]]:
        ...

    def close(self) -> None:
        ...

    def settimeout(self, value: float) -> None:
        ...

    def setsockopt(self, level: int, optname: int, value: int) -> None:
        ...

    def fileno(self) -> int:
        ...


class UdpTransportError(RuntimeError):
    """Base error for UDP transport operations."""


class UdpTransportConfigError(UdpTransportError):
    """Raised when UDP transport configuration is invalid."""


class UdpTransportOpenError(UdpTransportError):
    """Raised when UDP transport cannot bind configured sockets."""


UdpSocketFactory = Callable[[], UdpSocketLike]
UdpPacketParser = Callable[[bytes, OkuaPacketType], OkuaPacket]
OnEvtPacket = Callable[[UdpReceivedEvtPacket], None]
OnStatPacket = Callable[[UdpReceivedStatPacket], None]
OnRuntimeEvent = Callable[[UdpRuntimeEvent], None]


def default_udp_socket_factory() -> UdpSocketLike:
    return socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def default_udp_packet_parser(payload: bytes, expected_type: OkuaPacketType) -> OkuaPacket:
    return parse_okua_packet(payload, expected_type=expected_type)


class UdpTransportAdapter:
    """UDP adapter for OKUA EVT/STAT packets with runtime metrics."""

    def __init__(
        self,
        *,
        config: UdpTransportConfig,
        socket_factory: UdpSocketFactory | None = None,
        packet_parser: UdpPacketParser | None = None,
        on_evt_packet: OnEvtPacket | None = None,
        on_stat_packet: OnStatPacket | None = None,
        on_event: OnRuntimeEvent | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._config = config
        self._socket_factory = socket_factory or default_udp_socket_factory
        self._packet_parser = packet_parser or default_udp_packet_parser
        self._on_evt_packet = on_evt_packet
        self._on_stat_packet = on_stat_packet
        self._on_event = on_event
        self._clock = clock or time.monotonic

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._evt_thread: threading.Thread | None = None
        self._stat_thread: threading.Thread | None = None
        self._evt_socket: UdpSocketLike | None = None
        self._stat_socket: UdpSocketLike | None = None
        self._evt_packets: deque[UdpReceivedEvtPacket] = deque()
        self._stat_packets: deque[UdpReceivedStatPacket] = deque()

        self._total_evt_packets = 0
        self._total_stat_packets = 0
        self._total_bytes_received = 0
        self._parse_errors = 0
        self._socket_errors = 0
        self._last_activity_ts: float | None = None
        self._last_packet_summary: str | None = None
        self._last_error: str | None = None

    def start(self) -> bool:
        with self._lock:
            if self._is_running_locked():
                return False

            self._validate_config_locked()
            self._stop_event.clear()

            try:
                self._evt_socket = self._create_bound_socket_locked(self._config.evt_port)
                self._stat_socket = self._create_bound_socket_locked(self._config.stat_port)
            except Exception as exc:
                msg = (
                    "No se pudo abrir sockets UDP "
                    f"({self._config.bind_ip}:{self._config.evt_port}/{self._config.stat_port}): {exc}"
                )
                self._socket_errors += 1
                self._last_error = msg
                self._close_socket_locked("evt")
                self._close_socket_locked("stat")
                self._emit_event("error", msg)
                raise UdpTransportOpenError(msg) from exc

            self._evt_thread = threading.Thread(
                target=self._recv_loop,
                args=("evt", OkuaPacketType.EVT),
                daemon=True,
            )
            self._stat_thread = threading.Thread(
                target=self._recv_loop,
                args=("stat", OkuaPacketType.STAT),
                daemon=True,
            )
            self._evt_thread.start()
            self._stat_thread.start()

        self._emit_event(
            "info",
            (
                "UDP iniciado en "
                f"{self._config.bind_ip} (evt:{self._config.evt_port}, stat:{self._config.stat_port})."
            ),
        )
        return True

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            self._close_socket_locked("evt")
            self._close_socket_locked("stat")

        evt_thread = self._evt_thread
        stat_thread = self._stat_thread
        if evt_thread is not None and evt_thread.is_alive():
            evt_thread.join(timeout=2.0)
        if stat_thread is not None and stat_thread.is_alive():
            stat_thread.join(timeout=2.0)

        with self._lock:
            self._evt_thread = None
            self._stat_thread = None

    def is_running(self) -> bool:
        with self._lock:
            return self._is_running_locked()

    def snapshot(self) -> UdpTransportSnapshot:
        with self._lock:
            return UdpTransportSnapshot(
                bind_ip=self._config.bind_ip,
                evt_port=self._config.evt_port,
                stat_port=self._config.stat_port,
                is_running=self._is_running_locked(),
                evt_socket_open=self._is_socket_open_locked(self._evt_socket),
                stat_socket_open=self._is_socket_open_locked(self._stat_socket),
                total_evt_packets=self._total_evt_packets,
                total_stat_packets=self._total_stat_packets,
                total_bytes_received=self._total_bytes_received,
                parse_errors=self._parse_errors,
                socket_errors=self._socket_errors,
                last_activity_ts=self._last_activity_ts,
                last_packet_summary=self._last_packet_summary,
                last_error=self._last_error,
            )

    def metrics(self) -> UdpTransportMetrics:
        with self._lock:
            return UdpTransportMetrics(
                total_evt_packets=self._total_evt_packets,
                total_stat_packets=self._total_stat_packets,
                total_bytes_received=self._total_bytes_received,
                parse_errors=self._parse_errors,
                socket_errors=self._socket_errors,
                last_activity_ts=self._last_activity_ts,
                last_packet_summary=self._last_packet_summary,
                last_error=self._last_error,
            )

    def pop_evt_packets(self, *, max_items: int | None = None) -> list[UdpReceivedEvtPacket]:
        with self._lock:
            take = len(self._evt_packets) if max_items is None or max_items < 0 else max_items
            items: list[UdpReceivedEvtPacket] = []
            for _ in range(min(take, len(self._evt_packets))):
                items.append(self._evt_packets.popleft())
            return items

    def pop_stat_packets(self, *, max_items: int | None = None) -> list[UdpReceivedStatPacket]:
        with self._lock:
            take = len(self._stat_packets) if max_items is None or max_items < 0 else max_items
            items: list[UdpReceivedStatPacket] = []
            for _ in range(min(take, len(self._stat_packets))):
                items.append(self._stat_packets.popleft())
            return items

    def _recv_loop(self, channel: str, expected_type: OkuaPacketType) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                sock = self._evt_socket if channel == "evt" else self._stat_socket
            if sock is None:
                break

            try:
                payload, address = sock.recvfrom(self._config.recv_size)
            except socket.timeout:
                continue
            except OSError as exc:
                if self._stop_event.is_set():
                    break
                msg = f"Error de recepcion UDP en {channel.upper()}: {exc}"
                with self._lock:
                    self._socket_errors += 1
                    self._last_error = msg
                self._emit_event("error", msg)
                break

            if not payload:
                continue

            now = self._clock()
            with self._lock:
                self._total_bytes_received += len(payload)
                self._last_activity_ts = now

            try:
                parsed = self._packet_parser(payload, expected_type)
            except OkuaPacketParseError as exc:
                msg = (
                    f"Paquete UDP invalido en {channel.upper()} "
                    f"({exc.code}): {exc}"
                )
                with self._lock:
                    self._parse_errors += 1
                    self._last_error = msg
                self._emit_event("warning", msg)
                continue
            except Exception as exc:
                msg = f"Error parseando paquete UDP en {channel.upper()}: {exc}"
                with self._lock:
                    self._parse_errors += 1
                    self._last_error = msg
                self._emit_event("warning", msg)
                continue

            source_ip, source_port = _normalize_address(address)
            if expected_type is OkuaPacketType.EVT and isinstance(parsed, OkuaEvtPacket):
                event = UdpReceivedEvtPacket(
                    packet=parsed,
                    source_ip=source_ip,
                    source_port=source_port,
                    received_ts=now,
                )
                with self._lock:
                    self._total_evt_packets += 1
                    self._last_packet_summary = (
                        "EVT "
                        f"node={parsed.header.node_id} seq={parsed.header.seq} "
                        f"note={parsed.note} vel={parsed.vel} "
                        f"src={source_ip}:{source_port}"
                    )
                    self._evt_packets.append(event)
                self._dispatch_evt_packet(event)
                continue

            if expected_type is OkuaPacketType.STAT and isinstance(parsed, OkuaStatPacket):
                event = UdpReceivedStatPacket(
                    packet=parsed,
                    source_ip=source_ip,
                    source_port=source_port,
                    received_ts=now,
                )
                with self._lock:
                    self._total_stat_packets += 1
                    self._last_packet_summary = (
                        "STAT "
                        f"node={parsed.header.node_id} seq={parsed.header.seq} "
                        f"uptime={parsed.uptime_s}s vbat={parsed.vbat_mv}mV "
                        f"src={source_ip}:{source_port}"
                    )
                    self._stat_packets.append(event)
                self._dispatch_stat_packet(event)
                continue

            msg = (
                f"Canal {channel.upper()} recibio tipo inesperado "
                f"({type(parsed).__name__})."
            )
            with self._lock:
                self._parse_errors += 1
                self._last_error = msg
            self._emit_event("warning", msg)

    def _validate_config_locked(self) -> None:
        bind_ip = self._config.bind_ip.strip() if isinstance(self._config.bind_ip, str) else ""
        if not bind_ip:
            msg = "No se puede iniciar UDP: udp.bind_ip no configurado."
            self._last_error = msg
            self._emit_event("error", msg)
            raise UdpTransportConfigError(msg)

        try:
            ipaddress.ip_address(bind_ip)
        except ValueError as exc:
            msg = f"No se puede iniciar UDP: udp.bind_ip invalido ('{bind_ip}')."
            self._last_error = msg
            self._emit_event("error", msg)
            raise UdpTransportConfigError(msg) from exc

        evt_port = self._config.evt_port
        stat_port = self._config.stat_port
        if not _valid_port(evt_port) or not _valid_port(stat_port):
            msg = "No se puede iniciar UDP: puertos evt/stat fuera de rango (1..65535)."
            self._last_error = msg
            self._emit_event("error", msg)
            raise UdpTransportConfigError(msg)
        if evt_port == stat_port:
            msg = "No se puede iniciar UDP: udp.evt_port y udp.stat_port deben ser distintos."
            self._last_error = msg
            self._emit_event("error", msg)
            raise UdpTransportConfigError(msg)

    def _create_bound_socket_locked(self, port: int) -> UdpSocketLike:
        sock = self._socket_factory()
        sock.settimeout(0.2)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self._config.rcvbuf_bytes)
        except OSError:
            # Best-effort tuning; keep transport functional if platform rejects value.
            pass
        sock.bind((self._config.bind_ip, port))
        return sock

    def _close_socket_locked(self, channel: str) -> None:
        if channel == "evt":
            sock = self._evt_socket
        else:
            sock = self._stat_socket
        if sock is None:
            return
        try:
            sock.close()
        except OSError as exc:
            self._socket_errors += 1
            self._last_error = f"Error cerrando socket UDP {channel.upper()}: {exc}"
            self._emit_event("warning", self._last_error)
        finally:
            if channel == "evt":
                self._evt_socket = None
            else:
                self._stat_socket = None

    def _is_running_locked(self) -> bool:
        if self._stop_event.is_set():
            return False
        evt_alive = self._evt_thread is not None and self._evt_thread.is_alive()
        stat_alive = self._stat_thread is not None and self._stat_thread.is_alive()
        return evt_alive or stat_alive

    @staticmethod
    def _is_socket_open_locked(sock: UdpSocketLike | None) -> bool:
        if sock is None:
            return False
        try:
            return sock.fileno() >= 0
        except OSError:
            return False

    def _dispatch_evt_packet(self, event: UdpReceivedEvtPacket) -> None:
        callback = self._on_evt_packet
        if callback is None:
            return
        try:
            callback(event)
        except Exception:
            pass

    def _dispatch_stat_packet(self, event: UdpReceivedStatPacket) -> None:
        callback = self._on_stat_packet
        if callback is None:
            return
        try:
            callback(event)
        except Exception:
            pass

    def _emit_event(self, level: str, message: str) -> None:
        callback = self._on_event
        if callback is None:
            return
        try:
            callback(UdpRuntimeEvent(level=level, message=message))
        except Exception:
            pass


def _valid_port(value: int) -> bool:
    return 1 <= int(value) <= 65535


def _normalize_address(address: tuple[str, int] | tuple[str, int, int, int]) -> tuple[str, int]:
    if len(address) >= 2:
        return str(address[0]), int(address[1])
    return "0.0.0.0", 0
