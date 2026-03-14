from __future__ import annotations

from datetime import datetime, timezone
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.recording import (  # noqa: E402
    SessionLogEventType,
    SessionLogFormat,
    SessionLogRecord,
    SessionReportAccumulator,
    create_session_id,
)


def _record(event_type: SessionLogEventType, *, session_id: str = "s1", ts_rel_ms: int = 0) -> SessionLogRecord:
    return SessionLogRecord(
        schema_version=int(SessionLogFormat.V1),
        session_id=session_id,
        event_type=event_type,
        ts_rel_ms=ts_rel_ms,
        wall_time_utc="2026-03-14T00:00:00Z",
        payload={"ok": True},
    )


def test_schema_version_stable_for_recording_foundation() -> None:
    assert int(SessionLogFormat.V1) == 1
    record = _record(SessionLogEventType.SESSION_STARTED)
    assert record.schema_version == 1


def test_report_accumulator_counts_event_types_and_generates_close_report() -> None:
    acc = SessionReportAccumulator(
        session_id="session-r1",
        profile_id="udp_jardin",
        mode="udp",
        backend_kind="udp",
        started_at_utc="2026-03-14T00:00:00Z",
        start_monotonic=100.0,
        clock=lambda: 101.8,
    )
    acc.observe_record(_record(SessionLogEventType.SESSION_STARTED, session_id="session-r1", ts_rel_ms=0))
    acc.observe_record(_record(SessionLogEventType.MIDI_EVENT, session_id="session-r1", ts_rel_ms=10))
    acc.observe_record(_record(SessionLogEventType.UDP_EVT, session_id="session-r1", ts_rel_ms=20))
    acc.observe_record(_record(SessionLogEventType.UDP_STAT, session_id="session-r1", ts_rel_ms=30))
    acc.observe_record(_record(SessionLogEventType.SERIAL_MESSAGE, session_id="session-r1", ts_rel_ms=40))
    acc.observe_record(_record(SessionLogEventType.BACKEND_RUNTIME, session_id="session-r1", ts_rel_ms=50))
    acc.observe_record(_record(SessionLogEventType.NODE_SUMMARY, session_id="session-r1", ts_rel_ms=60))
    acc.observe_record(_record(SessionLogEventType.SESSION_ERROR, session_id="session-r1", ts_rel_ms=70))

    report = acc.build_close_report(
        final_state="error",
        ended_at_utc="2026-03-14T00:00:02Z",
    )
    assert report.session_id == "session-r1"
    assert report.profile_id == "udp_jardin"
    assert report.mode == "udp"
    assert report.backend_kind == "udp"
    assert report.duration_ms == 1800
    assert report.total_records == 8
    assert report.total_midi_events == 1
    assert report.total_udp_evt == 1
    assert report.total_udp_stat == 1
    assert report.total_serial_messages == 1
    assert report.total_runtime_snapshots == 1
    assert report.total_node_summaries == 1
    assert report.total_errors == 1
    assert report.had_errors is True
    assert "registros" in report.summary.lower()
    report_dict = report.to_dict()
    assert report_dict["total_records"] == 8
    assert report_dict["had_errors"] is True


def test_report_accumulator_rejects_record_from_other_session() -> None:
    acc = SessionReportAccumulator(
        session_id="session-r2",
        started_at_utc="2026-03-14T00:00:00Z",
        start_monotonic=10.0,
        clock=lambda: 10.5,
    )
    try:
        acc.observe_record(_record(SessionLogEventType.MIDI_EVENT, session_id="other"))
        assert False, "observe_record() debio fallar para session_id distinto"
    except ValueError as exc:
        assert "does not match" in str(exc).lower()


def test_create_session_id_is_filesystem_friendly() -> None:
    session_id = create_session_id(
        utc_now=datetime(2026, 3, 14, 16, 45, 10, 654321, tzinfo=timezone.utc),
        suffix="ff00aa",
    )
    assert " " not in session_id
    assert ":" not in session_id
    assert session_id.endswith("-ff00aa")
