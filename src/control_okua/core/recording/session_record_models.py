from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum, IntEnum
import json
from pathlib import Path
import secrets
from typing import Any


class SessionLogFormat(IntEnum):
    V1 = 1


class SessionLogEventType(str, Enum):
    SESSION_STARTED = "session_started"
    SESSION_STOPPED = "session_stopped"
    SESSION_ERROR = "session_error"
    SESSION_STATE_CHANGED = "session_state_changed"
    PREFLIGHT_REPORT = "preflight_report"
    BACKEND_RUNTIME = "backend_runtime"
    MIDI_EVENT = "midi_event"
    UDP_EVT = "udp_evt"
    UDP_STAT = "udp_stat"
    SERIAL_MESSAGE = "serial_message"
    NODE_SUMMARY = "node_summary"
    REPORT_GENERATED = "report_generated"
    COMMAND_SENT = "command_sent"
    COMMAND_RETRY = "command_retry"
    COMMAND_ACK = "command_ack"
    COMMAND_TIMEOUT = "command_timeout"


def coerce_event_type(value: SessionLogEventType | str) -> SessionLogEventType:
    if isinstance(value, SessionLogEventType):
        return value
    raw = str(value).strip()
    try:
        return SessionLogEventType(raw)
    except ValueError as exc:
        raise ValueError(f"Unsupported session log event type: {raw}") from exc


def format_utc(dt: datetime) -> str:
    resolved = dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    return resolved.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def now_utc_iso() -> str:
    return format_utc(datetime.now(timezone.utc))


def create_session_id(*, utc_now: datetime | None = None, suffix: str | None = None) -> str:
    timestamp = format_utc(utc_now or datetime.now(timezone.utc))
    compact = (
        timestamp.replace("-", "")
        .replace(":", "")
        .replace(".", "")
        .replace("+00:00", "Z")
    )
    if compact.endswith("Z"):
        compact = compact[:-1] + "Z"
    suffix_text = suffix if isinstance(suffix, str) and suffix.strip() else secrets.token_hex(3)
    return f"{compact}-{suffix_text}"


def build_session_artifact_paths(base_sessions_dir: Path | str, session_id: str) -> "SessionArtifactPaths":
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session_id must be a non-empty string")
    base_dir = Path(base_sessions_dir).expanduser()
    session_dir = base_dir / session_id
    return SessionArtifactPaths(
        base_sessions_dir=base_dir,
        session_dir=session_dir,
        session_jsonl_path=session_dir / "session.jsonl",
        report_json_path=session_dir / "report.json",
        exports_dir=session_dir / "exports",
    )


def ensure_json_serializable(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")
    try:
        json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"payload is not JSON-serializable: {exc}") from exc
    return payload


@dataclass(frozen=True)
class SessionLogRecord:
    schema_version: int
    session_id: str
    event_type: SessionLogEventType
    ts_rel_ms: int
    wall_time_utc: str
    payload: dict[str, Any]

    def __post_init__(self) -> None:
        if int(self.schema_version) != int(SessionLogFormat.V1):
            raise ValueError(
                f"Unsupported schema_version: {self.schema_version}; expected {int(SessionLogFormat.V1)}"
            )
        if not isinstance(self.session_id, str) or not self.session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        if int(self.ts_rel_ms) < 0:
            raise ValueError("ts_rel_ms must be >= 0")
        if not isinstance(self.wall_time_utc, str) or not self.wall_time_utc.strip():
            raise ValueError("wall_time_utc must be a non-empty string")
        ensure_json_serializable(self.payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "session_id": self.session_id,
            "event_type": self.event_type.value,
            "ts_rel_ms": int(self.ts_rel_ms),
            "wall_time_utc": self.wall_time_utc,
            "payload": self.payload,
        }


@dataclass(frozen=True)
class SessionArtifactPaths:
    base_sessions_dir: Path
    session_dir: Path
    session_jsonl_path: Path
    report_json_path: Path
    exports_dir: Path

    def to_dict(self) -> dict[str, str]:
        return {
            "base_sessions_dir": str(self.base_sessions_dir),
            "session_dir": str(self.session_dir),
            "session_jsonl_path": str(self.session_jsonl_path),
            "report_json_path": str(self.report_json_path),
            "exports_dir": str(self.exports_dir),
        }


@dataclass(frozen=True)
class SessionCloseReport:
    session_id: str
    profile_id: str | None
    mode: str | None
    backend_kind: str | None
    started_at_utc: str
    ended_at_utc: str
    duration_ms: int
    final_state: str
    total_records: int
    total_midi_events: int
    total_udp_evt: int
    total_udp_stat: int
    total_serial_messages: int
    total_errors: int
    total_runtime_snapshots: int
    total_node_summaries: int
    had_errors: bool
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "profile_id": self.profile_id,
            "mode": self.mode,
            "backend_kind": self.backend_kind,
            "started_at_utc": self.started_at_utc,
            "ended_at_utc": self.ended_at_utc,
            "duration_ms": int(self.duration_ms),
            "final_state": self.final_state,
            "total_records": int(self.total_records),
            "total_midi_events": int(self.total_midi_events),
            "total_udp_evt": int(self.total_udp_evt),
            "total_udp_stat": int(self.total_udp_stat),
            "total_serial_messages": int(self.total_serial_messages),
            "total_errors": int(self.total_errors),
            "total_runtime_snapshots": int(self.total_runtime_snapshots),
            "total_node_summaries": int(self.total_node_summaries),
            "had_errors": bool(self.had_errors),
            "summary": self.summary,
        }
