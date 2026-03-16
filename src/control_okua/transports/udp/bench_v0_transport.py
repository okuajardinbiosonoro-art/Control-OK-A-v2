from __future__ import annotations

import ipaddress
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from control_okua.core.udp import (
    BenchV0EvtPacket,
    BenchV0MsgType,
    BenchV0Packet,
    BenchV0ParseError,
    BenchV0PingPacket,
    BenchV0PongPacket,
    BenchV0StatPacket,
    build_bench_v0_pong_from_ping,
    parse_bench_v0_packet,
)


class BenchSocketLike(Protocol):
    def bind(self, address: tuple[str, int]) -> None:
        ...

    def recvfrom(self, bufsize: int) -> tuple[bytes, tuple[str, int]]:
        ...

    def sendto(self, payload: bytes, address: tuple[str, int]) -> int:
        ...

    def close(self) -> None:
        ...

    def settimeout(self, value: float) -> None:
        ...

    def setsockopt(self, level: int, optname: int, value: int) -> None:
        ...

    def fileno(self) -> int:
        ...


@dataclass(frozen=True)
class BenchV0TransportConfig:
    bind_ip: str
    bench_port: int = 5005
    rcvbuf_bytes: int = 262144
    recv_size: int = 2048
    auto_pong: bool = True

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "BenchV0TransportConfig":
        udp_cfg = cfg.get("udp") if isinstance(cfg.get("udp"), dict) else {}
        raw_bind_ip = udp_cfg.get("bind_ip", "0.0.0.0")
        bind_ip = raw_bind_ip.strip() if isinstance(raw_bind_ip, str) else "0.0.0.0"
        if not bind_ip:
            bind_ip = "0.0.0.0"

        raw_bench_port = udp_cfg.get("bench_port")
        if raw_bench_port is None:
            raw_bench_port = udp_cfg.get("evt_port", 5005)
        bench_port = _safe_port(raw_bench_port, fallback=5005)
        rcvbuf_bytes = _safe_positive_int(udp_cfg.get("rcvbuf_bytes"), fallback=262144)
        recv_size = _safe_positive_int(udp_cfg.get("recv_size"), fallback=2048)
        auto_pong = udp_cfg.get("bench_auto_pong")
        auto_pong_value = bool(auto_pong) if isinstance(auto_pong, bool) else True
        return cls(
            bind_ip=bind_ip,
            bench_port=bench_port,
            rcvbuf_bytes=rcvbuf_bytes,
            recv_size=recv_size,
            auto_pong=auto_pong_value,
        )


@dataclass(frozen=True)
class BenchV0RuntimeEvent:
    level: str
    message: str


@dataclass(frozen=True)
class BenchV0ReceivedEvtPacket:
    packet: BenchV0EvtPacket
    source_ip: str
    source_port: int
    received_ts: float


@dataclass(frozen=True)
class BenchV0ReceivedStatPacket:
    packet: BenchV0StatPacket
    source_ip: str
    source_port: int
    received_ts: float


@dataclass(frozen=True)
class BenchV0ReceivedPingPacket:
    packet: BenchV0PingPacket
    source_ip: str
    source_port: int
    received_ts: float


@dataclass(frozen=True)
class BenchV0ReceivedPongPacket:
    packet: BenchV0PongPacket
    source_ip: str
    source_port: int
    received_ts: float


@dataclass(frozen=True)
class BenchV0TransportSnapshot:
    bind_ip: str
    bench_port: int
    evt_port: int
    stat_port: int
    is_running: bool
    socket_open: bool
    total_evt_packets: int
    total_stat_packets: int
    total_ping_packets: int
    total_pong_packets: int
    total_pong_sent: int
    total_bytes_received: int
    parse_errors: int
    socket_errors: int
    last_activity_ts: float | None
    last_packet_summary: str | None
    last_error: str | None


class BenchV0TransportError(RuntimeError):
    pass


class BenchV0TransportConfigError(BenchV0TransportError):
    pass


class BenchV0TransportOpenError(BenchV0TransportError):
    pass


BenchSocketFactory = Callable[[], BenchSocketLike]
BenchPacketParser = Callable[[bytes], BenchV0Packet]
OnEvtPacket = Callable[[BenchV0ReceivedEvtPacket], None]
OnStatPacket = Callable[[BenchV0ReceivedStatPacket], None]
OnPingPacket = Callable[[BenchV0ReceivedPingPacket], None]
OnPongPacket = Callable[[BenchV0ReceivedPongPacket], None]
OnRuntimeEvent = Callable[[BenchV0RuntimeEvent], None]


def default_bench_socket_factory() -> BenchSocketLike:
    return socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def default_bench_packet_parser(payload: bytes) -> BenchV0Packet:
    return parse_bench_v0_packet(payload)


class BenchV0TransportAdapter:
    def __init__(
        self,
        *,
        config: BenchV0TransportConfig,
        socket_factory: BenchSocketFactory | None = None,
        packet_parser: BenchPacketParser | None = None,
        on_evt_packet: OnEvtPacket | None = None,
        on_stat_packet: OnStatPacket | None = None,
        on_ping_packet: OnPingPacket | None = None,
        on_pong_packet: OnPongPacket | None = None,
        on_event: OnRuntimeEvent | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._config = config
        self._socket_factory = socket_factory or default_bench_socket_factory
        self._packet_parser = packet_parser or default_bench_packet_parser
        self._on_evt_packet = on_evt_packet
        self._on_stat_packet = on_stat_packet
        self._on_ping_packet = on_ping_packet
        self._on_pong_packet = on_pong_packet
        self._on_event = on_event
        self._clock = clock or time.monotonic

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._recv_thread: threading.Thread | None = None
        self._socket: BenchSocketLike | None = None
        self._evt_packets: deque[BenchV0ReceivedEvtPacket] = deque()
        self._stat_packets: deque[BenchV0ReceivedStatPacket] = deque()
        self._ping_packets: deque[BenchV0ReceivedPingPacket] = deque()
        self._pong_packets: deque[BenchV0ReceivedPongPacket] = deque()

        self._total_evt_packets = 0
        self._total_stat_packets = 0
        self._total_ping_packets = 0
        self._total_pong_packets = 0
        self._total_pong_sent = 0
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
                self._socket = self._create_bound_socket_locked(self._config.bench_port)
            except Exception as exc:
                message = (
                    "No se pudo abrir socket UDP bench "
                    f"({self._config.bind_ip}:{self._config.bench_port}): {exc}"
                )
                self._socket_errors += 1
                self._last_error = message
                self._close_socket_locked()
                self._emit_event("error", message)
                raise BenchV0TransportOpenError(message) from exc

            self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
            self._recv_thread.start()

        self._emit_event(
            "info",
            (
                "UDP bench iniciado en "
                f"{self._config.bind_ip}:{self._config.bench_port} (auto_pong={self._config.auto_pong})."
            ),
        )
        return True

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            self._close_socket_locked()
        recv_thread = self._recv_thread
        if recv_thread is not None and recv_thread.is_alive():
            recv_thread.join(timeout=2.0)
        with self._lock:
            self._recv_thread = None

    def is_running(self) -> bool:
        with self._lock:
            return self._is_running_locked()

    def snapshot(self) -> BenchV0TransportSnapshot:
        with self._lock:
            return BenchV0TransportSnapshot(
                bind_ip=self._config.bind_ip,
                bench_port=self._config.bench_port,
                evt_port=self._config.bench_port,
                stat_port=self._config.bench_port,
                is_running=self._is_running_locked(),
                socket_open=self._is_socket_open_locked(self._socket),
                total_evt_packets=self._total_evt_packets,
                total_stat_packets=self._total_stat_packets,
                total_ping_packets=self._total_ping_packets,
                total_pong_packets=self._total_pong_packets,
                total_pong_sent=self._total_pong_sent,
                total_bytes_received=self._total_bytes_received,
                parse_errors=self._parse_errors,
                socket_errors=self._socket_errors,
                last_activity_ts=self._last_activity_ts,
                last_packet_summary=self._last_packet_summary,
                last_error=self._last_error,
            )

    def pop_evt_packets(self, *, max_items: int | None = None) -> list[BenchV0ReceivedEvtPacket]:
        return self._pop_items(self._evt_packets, max_items=max_items)

    def pop_stat_packets(self, *, max_items: int | None = None) -> list[BenchV0ReceivedStatPacket]:
        return self._pop_items(self._stat_packets, max_items=max_items)

    def pop_ping_packets(self, *, max_items: int | None = None) -> list[BenchV0ReceivedPingPacket]:
        return self._pop_items(self._ping_packets, max_items=max_items)

    def pop_pong_packets(self, *, max_items: int | None = None) -> list[BenchV0ReceivedPongPacket]:
        return self._pop_items(self._pong_packets, max_items=max_items)

    def _pop_items(self, queue: deque, *, max_items: int | None) -> list[Any]:
        with self._lock:
            take = len(queue) if max_items is None or max_items < 0 else int(max_items)
            items: list[Any] = []
            for _ in range(min(take, len(queue))):
                items.append(queue.popleft())
            return items

    def _recv_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                sock = self._socket
            if sock is None:
                break

            try:
                payload, address = sock.recvfrom(self._config.recv_size)
            except socket.timeout:
                continue
            except OSError as exc:
                if self._stop_event.is_set():
                    break
                message = f"Error de recepcion UDP bench: {exc}"
                with self._lock:
                    self._socket_errors += 1
                    self._last_error = message
                self._emit_event("error", message)
                break

            if not payload:
                continue

            now = self._clock()
            with self._lock:
                self._total_bytes_received += len(payload)
                self._last_activity_ts = now

            try:
                packet = self._packet_parser(payload)
            except BenchV0ParseError as exc:
                message = f"Paquete BenchPktV0 invalido ({exc.code}): {exc}"
                with self._lock:
                    self._parse_errors += 1
                    self._last_error = message
                self._emit_event("warning", message)
                continue
            except Exception as exc:
                message = f"Error parseando BenchPktV0: {exc}"
                with self._lock:
                    self._parse_errors += 1
                    self._last_error = message
                self._emit_event("warning", message)
                continue

            source_ip, source_port = _normalize_address(address)
            self._dispatch_packet(packet, source_ip=source_ip, source_port=source_port, now=now)

            if (
                self._config.auto_pong
                and isinstance(packet, BenchV0PingPacket)
                and not self._stop_event.is_set()
            ):
                self._respond_with_pong(packet, destination=(source_ip, source_port))

    def _dispatch_packet(
        self,
        packet: BenchV0Packet,
        *,
        source_ip: str,
        source_port: int,
        now: float,
    ) -> None:
        if isinstance(packet, BenchV0EvtPacket):
            event = BenchV0ReceivedEvtPacket(
                packet=packet,
                source_ip=source_ip,
                source_port=source_port,
                received_ts=now,
            )
            with self._lock:
                self._total_evt_packets += 1
                self._last_packet_summary = (
                    f"EVT node={packet.header.node_id} seq={packet.header.seq} "
                    f"note={packet.note} vel={packet.vel} src={source_ip}:{source_port}"
                )
                self._evt_packets.append(event)
            self._dispatch_evt_packet(event)
            return

        if isinstance(packet, BenchV0StatPacket):
            event = BenchV0ReceivedStatPacket(
                packet=packet,
                source_ip=source_ip,
                source_port=source_port,
                received_ts=now,
            )
            with self._lock:
                self._total_stat_packets += 1
                self._last_packet_summary = (
                    f"STAT node={packet.header.node_id} seq={packet.header.seq} "
                    f"uptime={packet.uptime_s}s vbat={packet.vbat_mv}mV src={source_ip}:{source_port}"
                )
                self._stat_packets.append(event)
            self._dispatch_stat_packet(event)
            return

        if isinstance(packet, BenchV0PingPacket):
            event = BenchV0ReceivedPingPacket(
                packet=packet,
                source_ip=source_ip,
                source_port=source_port,
                received_ts=now,
            )
            with self._lock:
                self._total_ping_packets += 1
                self._last_packet_summary = (
                    f"PING node={packet.header.node_id} seq={packet.header.seq} src={source_ip}:{source_port}"
                )
                self._ping_packets.append(event)
            self._dispatch_ping_packet(event)
            return

        event = BenchV0ReceivedPongPacket(
            packet=packet,
            source_ip=source_ip,
            source_port=source_port,
            received_ts=now,
        )
        with self._lock:
            self._total_pong_packets += 1
            self._last_packet_summary = (
                f"PONG node={packet.header.node_id} seq={packet.header.seq} src={source_ip}:{source_port}"
            )
            self._pong_packets.append(event)
        self._dispatch_pong_packet(event)

    def _respond_with_pong(
        self,
        ping: BenchV0PingPacket,
        *,
        destination: tuple[str, int],
    ) -> None:
        with self._lock:
            sock = self._socket
        if sock is None:
            return
        try:
            payload = build_bench_v0_pong_from_ping(ping)
            sock.sendto(payload, destination)
            with self._lock:
                self._total_pong_sent += 1
        except OSError as exc:
            message = f"No se pudo enviar PONG bench a {destination[0]}:{destination[1]}: {exc}"
            with self._lock:
                self._socket_errors += 1
                self._last_error = message
            self._emit_event("warning", message)

    def _validate_config_locked(self) -> None:
        bind_ip = self._config.bind_ip.strip() if isinstance(self._config.bind_ip, str) else ""
        if not bind_ip:
            message = "No se puede iniciar UDP bench: udp.bind_ip no configurado."
            self._last_error = message
            self._emit_event("error", message)
            raise BenchV0TransportConfigError(message)

        try:
            ipaddress.ip_address(bind_ip)
        except ValueError as exc:
            message = f"No se puede iniciar UDP bench: udp.bind_ip invalido ('{bind_ip}')."
            self._last_error = message
            self._emit_event("error", message)
            raise BenchV0TransportConfigError(message) from exc

        if not _valid_port(self._config.bench_port):
            message = "No se puede iniciar UDP bench: udp.bench_port fuera de rango (1..65535)."
            self._last_error = message
            self._emit_event("error", message)
            raise BenchV0TransportConfigError(message)

    def _create_bound_socket_locked(self, port: int) -> BenchSocketLike:
        sock = self._socket_factory()
        sock.settimeout(0.2)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self._config.rcvbuf_bytes)
        except OSError:
            pass
        sock.bind((self._config.bind_ip, port))
        return sock

    def _close_socket_locked(self) -> None:
        sock = self._socket
        if sock is None:
            return
        try:
            sock.close()
        except OSError as exc:
            self._socket_errors += 1
            self._last_error = f"Error cerrando socket UDP bench: {exc}"
            self._emit_event("warning", self._last_error)
        finally:
            self._socket = None

    def _is_running_locked(self) -> bool:
        if self._stop_event.is_set():
            return False
        recv_alive = self._recv_thread is not None and self._recv_thread.is_alive()
        return recv_alive

    @staticmethod
    def _is_socket_open_locked(sock: BenchSocketLike | None) -> bool:
        if sock is None:
            return False
        try:
            return sock.fileno() >= 0
        except OSError:
            return False

    def _dispatch_evt_packet(self, event: BenchV0ReceivedEvtPacket) -> None:
        callback = self._on_evt_packet
        if callback is None:
            return
        try:
            callback(event)
        except Exception:
            return

    def _dispatch_stat_packet(self, event: BenchV0ReceivedStatPacket) -> None:
        callback = self._on_stat_packet
        if callback is None:
            return
        try:
            callback(event)
        except Exception:
            return

    def _dispatch_ping_packet(self, event: BenchV0ReceivedPingPacket) -> None:
        callback = self._on_ping_packet
        if callback is None:
            return
        try:
            callback(event)
        except Exception:
            return

    def _dispatch_pong_packet(self, event: BenchV0ReceivedPongPacket) -> None:
        callback = self._on_pong_packet
        if callback is None:
            return
        try:
            callback(event)
        except Exception:
            return

    def _emit_event(self, level: str, message: str) -> None:
        callback = self._on_event
        if callback is None:
            return
        try:
            callback(BenchV0RuntimeEvent(level=level, message=message))
        except Exception:
            return


def _safe_positive_int(value: Any, *, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    if parsed < 1:
        return fallback
    return parsed


def _safe_port(value: Any, *, fallback: int) -> int:
    port = _safe_positive_int(value, fallback=fallback)
    if port > 65535:
        return fallback
    return port


def _valid_port(value: int) -> bool:
    return 1 <= int(value) <= 65535


def _normalize_address(address: tuple[str, int] | tuple[str, int, int, int]) -> tuple[str, int]:
    if len(address) >= 2:
        return str(address[0]), int(address[1])
    return "0.0.0.0", 0
