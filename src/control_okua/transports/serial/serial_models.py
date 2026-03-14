from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SerialTransportConfig:
    port: str | None
    baudrate: int = 115200
    timeout_s: float = 0.05
    read_size: int = 64
    running_status: bool = True

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "SerialTransportConfig":
        serial_cfg = cfg.get("serial") if isinstance(cfg.get("serial"), dict) else {}
        raw_port = serial_cfg.get("port")
        port = raw_port.strip() if isinstance(raw_port, str) and raw_port.strip() else None

        raw_baudrate = serial_cfg.get("baudrate", 115200)
        try:
            baudrate = int(raw_baudrate)
        except (TypeError, ValueError):
            baudrate = 115200
        if baudrate <= 0:
            baudrate = 115200

        raw_timeout_ms = serial_cfg.get("flush_ms", 5)
        try:
            timeout_s = max(1, int(raw_timeout_ms)) / 1000.0
        except (TypeError, ValueError):
            timeout_s = 0.05

        running_status = bool(serial_cfg.get("running_status", True))
        return cls(
            port=port,
            baudrate=baudrate,
            timeout_s=timeout_s,
            read_size=64,
            running_status=running_status,
        )


@dataclass(frozen=True)
class SerialTransportMetrics:
    bytes_received: int
    messages_parsed: int
    parse_errors: int
    read_errors: int
    last_activity_ts: float | None
    last_error: str | None


@dataclass(frozen=True)
class SerialTransportSnapshot:
    port: str | None
    baudrate: int
    is_running: bool
    is_open: bool
    bytes_received: int
    messages_parsed: int
    parse_errors: int
    read_errors: int
    last_activity_ts: float | None
    last_error: str | None
