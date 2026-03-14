from __future__ import annotations

from datetime import datetime, timezone
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.recording import (  # noqa: E402
    JsonlSessionRecorder,
    SessionLogEventType,
    SessionLogFormat,
    SessionLogRecord,
    build_session_artifact_paths,
    create_session_id,
)


class _Clock:
    def __init__(self, values: list[float]) -> None:
        self._values = list(values)
        self._index = 0

    def __call__(self) -> float:
        if self._index >= len(self._values):
            return float(self._values[-1])
        value = float(self._values[self._index])
        self._index += 1
        return value


class _UtcNow:
    def __init__(self, values: list[datetime]) -> None:
        self._values = list(values)
        self._index = 0

    def __call__(self) -> datetime:
        if self._index >= len(self._values):
            return self._values[-1]
        value = self._values[self._index]
        self._index += 1
        return value


def test_create_session_id_and_artifact_paths_are_coherent(tmp_path: Path) -> None:
    session_id = create_session_id(
        utc_now=datetime(2026, 3, 14, 12, 30, 45, 123456, tzinfo=timezone.utc),
        suffix="abc123",
    )
    assert session_id.endswith("-abc123")
    assert "20260314T123045123456Z" in session_id

    paths = build_session_artifact_paths(tmp_path / "logs" / "sessions", session_id)
    assert paths.session_dir == (tmp_path / "logs" / "sessions" / session_id)
    assert paths.session_jsonl_path.name == "session.jsonl"
    assert paths.report_json_path.name == "report.json"
    assert paths.exports_dir.name == "exports"


def test_session_log_record_serializes_to_json_dict() -> None:
    record = SessionLogRecord(
        schema_version=int(SessionLogFormat.V1),
        session_id="s1",
        event_type=SessionLogEventType.SESSION_STARTED,
        ts_rel_ms=0,
        wall_time_utc="2026-03-14T12:30:45Z",
        payload={"profile_id": "udp_jardin"},
    )
    as_dict = record.to_dict()
    assert as_dict["schema_version"] == 1
    assert as_dict["event_type"] == "session_started"
    encoded = json.dumps(as_dict, ensure_ascii=False)
    decoded = json.loads(encoded)
    assert decoded["session_id"] == "s1"


def test_writer_creates_session_folder_and_writes_valid_jsonl(tmp_path: Path) -> None:
    clock = _Clock([10.0, 10.05, 10.15, 10.35])
    utc_now = _UtcNow(
        [
            datetime(2026, 3, 14, 12, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 3, 14, 12, 0, 0, 50000, tzinfo=timezone.utc),
            datetime(2026, 3, 14, 12, 0, 0, 150000, tzinfo=timezone.utc),
            datetime(2026, 3, 14, 12, 0, 0, 350000, tzinfo=timezone.utc),
        ]
    )
    recorder = JsonlSessionRecorder(
        base_sessions_dir=tmp_path / "logs" / "sessions",
        clock=clock,
        utc_now=utc_now,
    )
    paths = recorder.open_session(session_id="session-test-1")
    assert paths.session_dir.exists()
    assert paths.session_jsonl_path.exists()
    assert recorder.session_id == "session-test-1"

    record1 = recorder.write_event(
        SessionLogEventType.SESSION_STARTED,
        {"mode": "udp"},
    )
    record2 = recorder.write_event(
        SessionLogEventType.UDP_EVT,
        {"node_id": 7, "seq": 100},
    )
    record3 = recorder.write_event(
        SessionLogEventType.NODE_SUMMARY,
        {"total_nodes": 1},
    )
    closed_paths = recorder.close_session()
    assert closed_paths.session_jsonl_path == paths.session_jsonl_path

    assert record1.ts_rel_ms >= 0
    assert record2.ts_rel_ms >= record1.ts_rel_ms
    assert record3.ts_rel_ms >= record2.ts_rel_ms

    lines = paths.session_jsonl_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["event_type"] == "session_started"
    assert parsed[1]["event_type"] == "udp_evt"
    assert parsed[2]["event_type"] == "node_summary"


def test_writer_rejects_non_serializable_payload(tmp_path: Path) -> None:
    recorder = JsonlSessionRecorder(
        base_sessions_dir=tmp_path / "logs" / "sessions",
        clock=_Clock([1.0, 1.1]),
        utc_now=_UtcNow([datetime(2026, 3, 14, 0, 0, tzinfo=timezone.utc)]),
    )
    recorder.open_session(session_id="session-test-2")

    try:
        recorder.write_event(SessionLogEventType.MIDI_EVENT, {"bad": {1, 2, 3}})
        assert False, "write_event() debio fallar para payload no serializable"
    except ValueError as exc:
        assert "json-serializable" in str(exc).lower()
    finally:
        recorder.close_session()
