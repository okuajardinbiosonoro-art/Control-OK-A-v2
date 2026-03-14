from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any, Callable, Iterable, Protocol

from control_okua.core.recording.session_replay_models import (
    ReplayEventKind,
    ReplayMidiEvent,
    ReplaySession,
    ReplayStats,
    build_replay_stats,
)


class MidiReplaySink(Protocol):
    def send_note_on(self, bus: int, channel: int, note: int, velocity: int) -> None:
        ...

    def send_note_off(self, bus: int, channel: int, note: int, velocity: int = 0) -> None:
        ...


class ReplayRecordError(ValueError):
    """Raised when a replay record is invalid in strict mode."""


def load_replay_session(path: Path | str, *, strict: bool = False) -> ReplaySession:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(source)

    rows: list[dict[str, Any]] = []
    first_session_id: str | None = None
    skipped_records = 0

    for line_number, raw_line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            if strict:
                raise ReplayRecordError(f"Invalid JSONL line {line_number}: {exc}") from exc
            skipped_records += 1
            continue
        if not isinstance(row, dict):
            if strict:
                raise ReplayRecordError(f"Line {line_number} must contain a JSON object.")
            skipped_records += 1
            continue
        if first_session_id is None:
            session_id_raw = row.get("session_id")
            if isinstance(session_id_raw, str) and session_id_raw.strip():
                first_session_id = session_id_raw.strip()
        rows.append(row)

    events, skipped_from_events = extract_replay_events(rows, strict=strict)
    skipped_records += skipped_from_events
    stats = build_replay_stats(events)
    session_id = first_session_id or source.parent.name or source.stem
    ordered_events = tuple(sorted(events, key=lambda event: int(event.ts_rel_ms)))
    return ReplaySession(
        session_id=session_id,
        events=ordered_events,
        duration_ms=stats.duration_ms,
        stats=stats,
        skipped_records=skipped_records,
    )


def extract_replay_events(
    records: Iterable[dict[str, Any]],
    *,
    strict: bool = False,
) -> tuple[list[ReplayMidiEvent], int]:
    events_with_pos: list[tuple[int, ReplayMidiEvent]] = []
    skipped_records = 0
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            if strict:
                raise ReplayRecordError(f"Record at position {index} must be a dict.")
            skipped_records += 1
            continue
        if record.get("event_type") != "midi_event":
            continue
        try:
            events_with_pos.append((index, _record_to_replay_event(record)))
        except ReplayRecordError:
            if strict:
                raise
            skipped_records += 1
            continue
    events = [item[1] for item in sorted(events_with_pos, key=lambda item: (item[1].ts_rel_ms, item[0]))]
    return events, skipped_records


def replay_stats_for_session(session: ReplaySession) -> ReplayStats:
    return build_replay_stats(list(session.events))


class SessionMidiReplayer:
    def __init__(self, *, sleep_fn: Callable[[float], None] | None = None) -> None:
        self._sleep = sleep_fn or time.sleep

    def replay(
        self,
        session: ReplaySession,
        sink: MidiReplaySink | None,
        *,
        speed: float = 1.0,
        dry_run: bool = False,
    ) -> ReplayStats:
        if speed <= 0:
            raise ValueError("speed must be > 0")
        if not dry_run and sink is None:
            raise ValueError("sink is required when dry_run is False")

        previous_ts: int | None = None
        for event in session.events:
            if previous_ts is not None:
                delta_ms = max(0, int(event.ts_rel_ms) - int(previous_ts))
                wait_seconds = (delta_ms / 1000.0) / float(speed)
                if not dry_run and wait_seconds > 0:
                    self._sleep(wait_seconds)
            previous_ts = int(event.ts_rel_ms)

            if dry_run:
                continue
            assert sink is not None
            if event.event_kind is ReplayEventKind.NOTE_ON:
                sink.send_note_on(int(event.bus), int(event.channel), int(event.note), int(event.velocity))
            else:
                sink.send_note_off(int(event.bus), int(event.channel), int(event.note), int(event.velocity))
        return session.stats


def _record_to_replay_event(record: dict[str, Any]) -> ReplayMidiEvent:
    ts_rel_ms_raw = record.get("ts_rel_ms")
    payload = record.get("payload")
    if not isinstance(payload, dict):
        raise ReplayRecordError("midi_event record payload must be a dict.")
    if ts_rel_ms_raw is None:
        raise ReplayRecordError("midi_event record is missing ts_rel_ms.")
    ts_rel_ms = _coerce_non_negative_int(ts_rel_ms_raw, field_name="ts_rel_ms")

    event_kind_raw = payload.get("event_kind")
    if not isinstance(event_kind_raw, str):
        raise ReplayRecordError("midi_event payload is missing event_kind.")
    normalized_kind = event_kind_raw.strip().lower()
    if normalized_kind == ReplayEventKind.NOTE_ON.value:
        event_kind = ReplayEventKind.NOTE_ON
    elif normalized_kind == ReplayEventKind.NOTE_OFF.value:
        event_kind = ReplayEventKind.NOTE_OFF
    else:
        raise ReplayRecordError(f"Unsupported midi event_kind: {event_kind_raw}")

    bus = _coerce_non_negative_int(payload.get("bus"), field_name="bus")
    channel = _coerce_non_negative_int(payload.get("channel"), field_name="channel")
    note = _coerce_non_negative_int(payload.get("note"), field_name="note")
    velocity = _coerce_non_negative_int(payload.get("velocity"), field_name="velocity")
    metadata = {
        key: value
        for key, value in payload.items()
        if key not in {"event_kind", "bus", "channel", "note", "velocity"}
    }
    return ReplayMidiEvent(
        ts_rel_ms=ts_rel_ms,
        event_kind=event_kind,
        bus=bus,
        channel=channel,
        note=note,
        velocity=velocity,
        metadata=metadata,
    )


def _coerce_non_negative_int(value: Any, *, field_name: str) -> int:
    if value is None:
        raise ReplayRecordError(f"{field_name} is required.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ReplayRecordError(f"{field_name} must be an integer.") from exc
    if parsed < 0:
        raise ReplayRecordError(f"{field_name} must be >= 0.")
    return parsed
