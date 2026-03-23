from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

from control_okua.core.control_plane.protocol import (
    AckParseError,
    ParsedOkuaAck,
    parse_okua_ack_bytes,
)


class SentCommandLike(Protocol):
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


@dataclass(frozen=True)
class PendingCommand:
    sent_command: SentCommandLike
    registered_ts: float


class AckCorrelationStatus(str, Enum):
    MATCHED = "matched"
    UNMATCHED_ACK = "unmatched_ack"
    INVALID_ACK = "invalid_ack"


@dataclass(frozen=True)
class AckCorrelationResult:
    status: AckCorrelationStatus
    ack: ParsedOkuaAck | None = None
    sent_command: SentCommandLike | None = None
    parse_error_code: str | None = None
    parse_error_message: str | None = None
    source_ip: str | None = None
    source_port: int | None = None
    received_ts: float | None = None
    raw_len: int | None = None


class PendingCommandStore:
    """In-memory pending command registry for basic ACK correlation."""

    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.monotonic
        self._pending: dict[tuple[int, int, int], PendingCommand] = {}

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def register_sent_command(
        self,
        sent_command: SentCommandLike,
        *,
        registered_ts: float | None = None,
    ) -> PendingCommand:
        key = _command_key(
            cmd_seq=sent_command.cmd_seq,
            cmd_id=sent_command.cmd_id,
            nonce=sent_command.nonce,
        )
        resolved_ts = float(self._clock()) if registered_ts is None else float(registered_ts)
        pending = PendingCommand(sent_command=sent_command, registered_ts=resolved_ts)
        self._pending[key] = pending
        return pending

    def correlate_parsed_ack(
        self,
        ack: ParsedOkuaAck,
        *,
        source_ip: str | None = None,
        source_port: int | None = None,
        received_ts: float | None = None,
    ) -> AckCorrelationResult:
        key = _command_key(
            cmd_seq=ack.cmd_seq,
            cmd_id=ack.cmd_id_echo,
            nonce=ack.nonce_echo,
        )
        pending = self._pending.pop(key, None)
        resolved_ts = float(self._clock()) if received_ts is None else float(received_ts)

        if pending is None:
            return AckCorrelationResult(
                status=AckCorrelationStatus.UNMATCHED_ACK,
                ack=ack,
                sent_command=None,
                source_ip=source_ip,
                source_port=source_port,
                received_ts=resolved_ts,
            )

        return AckCorrelationResult(
            status=AckCorrelationStatus.MATCHED,
            ack=ack,
            sent_command=pending.sent_command,
            source_ip=source_ip,
            source_port=source_port,
            received_ts=resolved_ts,
        )

    def correlate_ack_datagram(
        self,
        data: bytes | bytearray | memoryview,
        *,
        source_ip: str,
        source_port: int,
        received_ts: float | None = None,
    ) -> AckCorrelationResult:
        payload = bytes(data)
        resolved_ts = float(self._clock()) if received_ts is None else float(received_ts)
        try:
            ack = parse_okua_ack_bytes(payload)
        except AckParseError as exc:
            return AckCorrelationResult(
                status=AckCorrelationStatus.INVALID_ACK,
                ack=None,
                sent_command=None,
                parse_error_code=exc.code.value,
                parse_error_message=str(exc),
                source_ip=source_ip,
                source_port=int(source_port),
                received_ts=resolved_ts,
                raw_len=len(payload),
            )

        return self.correlate_parsed_ack(
            ack,
            source_ip=source_ip,
            source_port=int(source_port),
            received_ts=resolved_ts,
        )

    def clear(self) -> None:
        self._pending.clear()

    def list_pending(self) -> list[PendingCommand]:
        return list(self._pending.values())


def _command_key(*, cmd_seq: int, cmd_id: int, nonce: int) -> tuple[int, int, int]:
    return (int(cmd_seq) & 0xFFFF, int(cmd_id) & 0xFF, int(nonce) & 0xFFFFFFFFFFFFFFFF)
