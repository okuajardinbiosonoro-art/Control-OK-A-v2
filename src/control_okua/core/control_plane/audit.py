from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable


class ControlAuditEventType(str, Enum):
    COMMAND_SENT = "command_sent"
    COMMAND_RETRY = "command_retry"
    COMMAND_ACK = "command_ack"
    COMMAND_TIMEOUT = "command_timeout"
    INVALID_ACK_SEEN = "invalid_ack_seen"
    UNMATCHED_ACK_SEEN = "unmatched_ack_seen"
    LISTENER_NOT_RUNNING = "listener_not_running"
    SEND_ERROR = "send_error"


@dataclass(frozen=True)
class ControlAuditEvent:
    ts_utc: str
    event_type: str
    command_name: str
    cmd_id: int
    node_ip: str
    node_id: int
    cmd_seq: int | None
    nonce: int | None
    attempt_index: int
    ack_stage: int | None = None
    status_code: int | None = None
    err_detail: int | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, object | None]:
        return {
            "ts_utc": self.ts_utc,
            "event_type": self.event_type,
            "command_name": self.command_name,
            "cmd_id": self.cmd_id,
            "node_ip": self.node_ip,
            "node_id": self.node_id,
            "cmd_seq": self.cmd_seq,
            "nonce": self.nonce,
            "attempt_index": self.attempt_index,
            "ack_stage": self.ack_stage,
            "status_code": self.status_code,
            "err_detail": self.err_detail,
            "detail": self.detail,
        }


def build_control_audit_event(
    *,
    event_type: str | ControlAuditEventType,
    command_name: str,
    cmd_id: int,
    node_ip: str,
    node_id: int,
    cmd_seq: int | None,
    nonce: int | None,
    attempt_index: int,
    ack_stage: int | None = None,
    status_code: int | None = None,
    err_detail: int | None = None,
    detail: str | None = None,
    utc_now_provider: Callable[[], datetime] | None = None,
) -> ControlAuditEvent:
    now_provider = utc_now_provider or _utc_now
    now = now_provider()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    ts_utc = now.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    if isinstance(event_type, ControlAuditEventType):
        event_type_value = event_type.value
    else:
        event_type_value = str(event_type)

    return ControlAuditEvent(
        ts_utc=ts_utc,
        event_type=event_type_value,
        command_name=str(command_name),
        cmd_id=int(cmd_id) & 0xFF,
        node_ip=str(node_ip),
        node_id=int(node_id) & 0xFFFF,
        cmd_seq=None if cmd_seq is None else (int(cmd_seq) & 0xFFFF),
        nonce=None if nonce is None else (int(nonce) & 0xFFFFFFFFFFFFFFFF),
        attempt_index=max(0, int(attempt_index)),
        ack_stage=None if ack_stage is None else (int(ack_stage) & 0xFF),
        status_code=None if status_code is None else (int(status_code) & 0xFF),
        err_detail=None if err_detail is None else (int(err_detail) & 0xFFFF),
        detail=None if detail is None else str(detail),
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
