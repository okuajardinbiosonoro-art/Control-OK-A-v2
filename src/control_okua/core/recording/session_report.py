from __future__ import annotations

from typing import Callable
import time

from control_okua.core.recording.session_record_models import (
    SessionCloseReport,
    SessionLogEventType,
    SessionLogRecord,
    coerce_event_type,
    now_utc_iso,
)


class SessionReportAccumulator:
    """Pure accumulator that converts session records into a close report."""

    def __init__(
        self,
        *,
        session_id: str,
        profile_id: str | None = None,
        mode: str | None = None,
        backend_kind: str | None = None,
        started_at_utc: str | None = None,
        start_monotonic: float | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        self.session_id = session_id
        self.profile_id = profile_id
        self.mode = mode
        self.backend_kind = backend_kind
        self.started_at_utc = started_at_utc or now_utc_iso()
        self._clock = clock or time.monotonic
        self._start_monotonic = (
            float(start_monotonic) if start_monotonic is not None else float(self._clock())
        )

        self.total_records = 0
        self.total_midi_events = 0
        self.total_udp_evt = 0
        self.total_udp_stat = 0
        self.total_serial_messages = 0
        self.total_errors = 0
        self.total_runtime_snapshots = 0
        self.total_node_summaries = 0

    def observe_record(self, record: SessionLogRecord) -> None:
        if record.session_id != self.session_id:
            raise ValueError(
                f"Record session_id '{record.session_id}' does not match accumulator session_id '{self.session_id}'."
            )
        self.total_records += 1
        event_type = coerce_event_type(record.event_type)

        if event_type is SessionLogEventType.MIDI_EVENT:
            self.total_midi_events += 1
        elif event_type is SessionLogEventType.UDP_EVT:
            self.total_udp_evt += 1
        elif event_type is SessionLogEventType.UDP_STAT:
            self.total_udp_stat += 1
        elif event_type is SessionLogEventType.SERIAL_MESSAGE:
            self.total_serial_messages += 1
        elif event_type is SessionLogEventType.SESSION_ERROR:
            self.total_errors += 1
        elif event_type is SessionLogEventType.BACKEND_RUNTIME:
            self.total_runtime_snapshots += 1
        elif event_type is SessionLogEventType.NODE_SUMMARY:
            self.total_node_summaries += 1

    def build_close_report(
        self,
        *,
        final_state: str,
        ended_at_utc: str | None = None,
        end_monotonic: float | None = None,
        summary: str | None = None,
    ) -> SessionCloseReport:
        end_ts = float(end_monotonic) if end_monotonic is not None else float(self._clock())
        duration_ms = max(0, int(round((end_ts - self._start_monotonic) * 1000.0)))
        report_summary = summary or (
            f"Sesion '{self.session_id}' finalizada con {self.total_records} registros."
        )
        return SessionCloseReport(
            session_id=self.session_id,
            profile_id=self.profile_id,
            mode=self.mode,
            backend_kind=self.backend_kind,
            started_at_utc=self.started_at_utc,
            ended_at_utc=ended_at_utc or now_utc_iso(),
            duration_ms=duration_ms,
            final_state=str(final_state),
            total_records=self.total_records,
            total_midi_events=self.total_midi_events,
            total_udp_evt=self.total_udp_evt,
            total_udp_stat=self.total_udp_stat,
            total_serial_messages=self.total_serial_messages,
            total_errors=self.total_errors,
            total_runtime_snapshots=self.total_runtime_snapshots,
            total_node_summaries=self.total_node_summaries,
            had_errors=self.total_errors > 0,
            summary=report_summary,
        )
