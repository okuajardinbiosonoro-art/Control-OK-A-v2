from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from control_okua.core.udp.packet_models import OkuaEvtPacket, OkuaStatPacket


@dataclass(frozen=True)
class UdpTransportConfig:
    bind_ip: str
    evt_port: int = 5005
    stat_port: int = 5006
    rcvbuf_bytes: int = 262144
    recv_size: int = 2048

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "UdpTransportConfig":
        udp_cfg = cfg.get("udp") if isinstance(cfg.get("udp"), dict) else {}

        raw_bind_ip = udp_cfg.get("bind_ip", "0.0.0.0")
        bind_ip = raw_bind_ip.strip() if isinstance(raw_bind_ip, str) else "0.0.0.0"
        if not bind_ip:
            bind_ip = "0.0.0.0"

        evt_port = _safe_port(udp_cfg.get("evt_port"), fallback=5005)
        stat_port = _safe_port(udp_cfg.get("stat_port"), fallback=5006)
        rcvbuf_bytes = _safe_positive_int(
            udp_cfg.get("rcvbuf_bytes"),
            fallback=262144,
        )
        recv_size = _safe_positive_int(udp_cfg.get("recv_size"), fallback=2048)
        return cls(
            bind_ip=bind_ip,
            evt_port=evt_port,
            stat_port=stat_port,
            rcvbuf_bytes=rcvbuf_bytes,
            recv_size=recv_size,
        )


@dataclass(frozen=True)
class UdpTransportMetrics:
    total_evt_packets: int
    total_stat_packets: int
    total_bytes_received: int
    parse_errors: int
    socket_errors: int
    last_activity_ts: float | None
    last_packet_summary: str | None
    last_error: str | None


@dataclass(frozen=True)
class UdpTransportSnapshot:
    bind_ip: str
    evt_port: int
    stat_port: int
    is_running: bool
    evt_socket_open: bool
    stat_socket_open: bool
    total_evt_packets: int
    total_stat_packets: int
    total_bytes_received: int
    parse_errors: int
    socket_errors: int
    last_activity_ts: float | None
    last_packet_summary: str | None
    last_error: str | None


@dataclass(frozen=True)
class UdpRuntimeEvent:
    level: str
    message: str


@dataclass(frozen=True)
class UdpReceivedEvtPacket:
    packet: OkuaEvtPacket
    source_ip: str
    source_port: int
    received_ts: float


@dataclass(frozen=True)
class UdpReceivedStatPacket:
    packet: OkuaStatPacket
    source_ip: str
    source_port: int
    received_ts: float


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
