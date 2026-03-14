from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any, Callable, TextIO

from control_okua.core.recording.session_record_models import (
    SessionArtifactPaths,
    SessionCloseReport,
    SessionLogEventType,
    SessionLogFormat,
    SessionLogRecord,
    build_session_artifact_paths,
    coerce_event_type,
    create_session_id,
    format_utc,
    now_utc_iso,
)


class JsonlSessionRecorder:
    """Base JSONL recorder for one session at a time."""

    def __init__(
        self,
        *,
        base_sessions_dir: Path | str = Path("logs") / "sessions",
        clock: Callable[[], float] | None = None,
        utc_now: Callable[[], datetime] | None = None,
        session_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._base_sessions_dir = Path(base_sessions_dir)
        self._clock = clock or time.monotonic
        self._utc_now = utc_now or (lambda: datetime.now(timezone.utc))
        self._session_id_factory = session_id_factory or create_session_id

        self._session_id: str | None = None
        self._paths: SessionArtifactPaths | None = None
        self._start_monotonic: float | None = None
        self._opened_at_utc: str | None = None
        self._jsonl_fp: TextIO | None = None

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def base_sessions_dir(self) -> Path:
        return self._base_sessions_dir

    @property
    def paths(self) -> SessionArtifactPaths | None:
        return self._paths

    @property
    def is_open(self) -> bool:
        return self._jsonl_fp is not None

    @property
    def opened_at_utc(self) -> str | None:
        return self._opened_at_utc

    @property
    def start_monotonic(self) -> float | None:
        return self._start_monotonic

    def open_session(self, *, session_id: str | None = None) -> SessionArtifactPaths:
        if self.is_open:
            raise RuntimeError("Recorder already has an open session.")

        resolved_session_id = (
            session_id if isinstance(session_id, str) and session_id.strip() else self._session_id_factory()
        )
        paths = build_session_artifact_paths(self._base_sessions_dir, resolved_session_id)
        paths.session_dir.mkdir(parents=True, exist_ok=False)
        fp = paths.session_jsonl_path.open(mode="w", encoding="utf-8", newline="\n")

        self._session_id = resolved_session_id
        self._paths = paths
        self._start_monotonic = float(self._clock())
        self._opened_at_utc = format_utc(self._utc_now())
        self._jsonl_fp = fp
        return paths

    def write_event(
        self,
        event_type: SessionLogEventType | str,
        payload: dict[str, Any],
        *,
        ts_rel_ms: int | None = None,
        wall_time_utc: str | None = None,
    ) -> SessionLogRecord:
        if not self.is_open or self._session_id is None:
            raise RuntimeError("No open session. Call open_session() first.")
        rel_ms = self._current_rel_ms() if ts_rel_ms is None else int(ts_rel_ms)
        if rel_ms < 0:
            raise ValueError("ts_rel_ms must be >= 0")
        wall = wall_time_utc or format_utc(self._utc_now())
        record = SessionLogRecord(
            schema_version=int(SessionLogFormat.V1),
            session_id=self._session_id,
            event_type=coerce_event_type(event_type),
            ts_rel_ms=rel_ms,
            wall_time_utc=wall,
            payload=payload,
        )
        self.write_record(record)
        return record

    def write_record(self, record: SessionLogRecord) -> None:
        fp = self._jsonl_fp
        if fp is None or self._session_id is None:
            raise RuntimeError("No open session. Call open_session() first.")
        if record.session_id != self._session_id:
            raise ValueError(
                f"Record session_id '{record.session_id}' does not match open session_id '{self._session_id}'."
            )
        line = json.dumps(record.to_dict(), ensure_ascii=False, separators=(",", ":"))
        fp.write(line)
        fp.write("\n")
        fp.flush()

    def close_session(self, *, report: SessionCloseReport | None = None) -> SessionArtifactPaths:
        if not self.is_open or self._paths is None:
            raise RuntimeError("No open session to close.")

        fp = self._jsonl_fp
        assert fp is not None
        fp.flush()
        fp.close()

        if report is not None:
            self._paths.report_json_path.write_text(
                json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )

        closed_paths = self._paths
        self._jsonl_fp = None
        self._session_id = None
        self._paths = None
        self._start_monotonic = None
        self._opened_at_utc = None
        return closed_paths

    def _current_rel_ms(self) -> int:
        start = self._start_monotonic
        if start is None:
            return 0
        now = float(self._clock())
        return max(0, int(round((now - start) * 1000.0)))


def write_report_json(path: Path | str, report: SessionCloseReport) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def read_jsonl_records(path: Path | str) -> list[dict[str, Any]]:
    source = Path(path)
    rows: list[dict[str, Any]] = []
    if not source.exists():
        return rows
    for raw_line in source.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def make_wall_time_utc(utc_now: Callable[[], datetime] | None = None) -> str:
    if utc_now is None:
        return now_utc_iso()
    return format_utc(utc_now())
