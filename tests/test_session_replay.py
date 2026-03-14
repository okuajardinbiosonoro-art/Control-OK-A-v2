from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.recording import (  # noqa: E402
    ReplayEventKind,
    ReplayRecordError,
    SessionMidiReplayer,
    extract_replay_events,
    load_replay_session,
)


class _SinkFake:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int, int, int]] = []

    def send_note_on(self, bus: int, channel: int, note: int, velocity: int) -> None:
        self.calls.append(("note_on", bus, channel, note, velocity))

    def send_note_off(self, bus: int, channel: int, note: int, velocity: int = 0) -> None:
        self.calls.append(("note_off", bus, channel, note, velocity))


def _write_jsonl(path: Path, rows: list[dict[str, object]], *, with_empty_line: bool = False) -> None:
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    text = "\n".join(lines)
    if with_empty_line:
        text += "\n\n"
    path.write_text(text + "\n", encoding="utf-8")


def _midi_row(*, session_id: str, ts_rel_ms: int, kind: str, note: int, vel: int) -> dict[str, object]:
    return {
        "schema_version": 1,
        "session_id": session_id,
        "event_type": "midi_event",
        "ts_rel_ms": ts_rel_ms,
        "wall_time_utc": "2026-03-14T12:00:00Z",
        "payload": {
            "source": "udp_evt",
            "event_kind": kind,
            "bus": 1,
            "channel": 0,
            "note": note,
            "velocity": vel,
            "node_id": 9,
            "seq": 10,
        },
    }


def test_load_replay_session_reads_mixed_jsonl_and_keeps_only_midi_events(tmp_path: Path) -> None:
    source = tmp_path / "session.jsonl"
    rows = [
        {
            "schema_version": 1,
            "session_id": "s-replay-1",
            "event_type": "session_started",
            "ts_rel_ms": 0,
            "wall_time_utc": "2026-03-14T12:00:00Z",
            "payload": {"mode": "udp"},
        },
        _midi_row(session_id="s-replay-1", ts_rel_ms=200, kind="note_on", note=62, vel=101),
        {
            "schema_version": 1,
            "session_id": "s-replay-1",
            "event_type": "udp_evt",
            "ts_rel_ms": 210,
            "wall_time_utc": "2026-03-14T12:00:00Z",
            "payload": {"node_id": 9, "seq": 11},
        },
        _midi_row(session_id="s-replay-1", ts_rel_ms=50, kind="note_off", note=62, vel=0),
    ]
    _write_jsonl(source, rows, with_empty_line=True)

    session = load_replay_session(source)
    assert session.session_id == "s-replay-1"
    assert [event.ts_rel_ms for event in session.events] == [50, 200]
    assert [event.event_kind for event in session.events] == [
        ReplayEventKind.NOTE_OFF,
        ReplayEventKind.NOTE_ON,
    ]
    assert session.stats.total_events == 2


def test_extract_replay_events_sorts_by_ts_rel_ms_stably() -> None:
    records = [
        _midi_row(session_id="s1", ts_rel_ms=100, kind="note_on", note=60, vel=90),
        _midi_row(session_id="s1", ts_rel_ms=50, kind="note_on", note=61, vel=80),
        _midi_row(session_id="s1", ts_rel_ms=100, kind="note_off", note=60, vel=0),
    ]
    events, skipped = extract_replay_events(records)
    assert skipped == 0
    assert [(event.ts_rel_ms, event.note, event.event_kind.value) for event in events] == [
        (50, 61, "note_on"),
        (100, 60, "note_on"),
        (100, 60, "note_off"),
    ]


def test_replay_stats_duration_is_coherent(tmp_path: Path) -> None:
    source = tmp_path / "session.jsonl"
    rows = [
        _midi_row(session_id="s-replay-2", ts_rel_ms=10, kind="note_on", note=60, vel=100),
        _midi_row(session_id="s-replay-2", ts_rel_ms=210, kind="note_off", note=60, vel=0),
        _midi_row(session_id="s-replay-2", ts_rel_ms=410, kind="note_on", note=64, vel=90),
    ]
    _write_jsonl(source, rows)
    session = load_replay_session(source)

    assert session.stats.total_events == 3
    assert session.stats.total_note_on == 2
    assert session.stats.total_note_off == 1
    assert session.stats.first_ts_ms == 10
    assert session.stats.last_ts_ms == 410
    assert session.stats.duration_ms == 400


def test_dry_run_does_not_call_sink_or_sleep(tmp_path: Path) -> None:
    source = tmp_path / "session.jsonl"
    rows = [
        _midi_row(session_id="s-replay-3", ts_rel_ms=0, kind="note_on", note=60, vel=100),
        _midi_row(session_id="s-replay-3", ts_rel_ms=150, kind="note_off", note=60, vel=0),
    ]
    _write_jsonl(source, rows)
    session = load_replay_session(source)
    sink = _SinkFake()
    waits: list[float] = []
    replayer = SessionMidiReplayer(sleep_fn=lambda seconds: waits.append(seconds))

    replay_stats = replayer.replay(session, sink, dry_run=True)
    assert replay_stats.total_events == 2
    assert sink.calls == []
    assert waits == []


def test_replay_real_calls_sink_in_order_and_emits_note_on_off(tmp_path: Path) -> None:
    source = tmp_path / "session.jsonl"
    rows = [
        _midi_row(session_id="s-replay-4", ts_rel_ms=0, kind="note_on", note=60, vel=110),
        _midi_row(session_id="s-replay-4", ts_rel_ms=120, kind="note_off", note=60, vel=0),
        _midi_row(session_id="s-replay-4", ts_rel_ms=200, kind="note_on", note=64, vel=95),
    ]
    _write_jsonl(source, rows)
    session = load_replay_session(source)
    sink = _SinkFake()
    waits: list[float] = []
    replayer = SessionMidiReplayer(sleep_fn=lambda seconds: waits.append(seconds))

    replayer.replay(session, sink, dry_run=False, speed=1.0)
    assert sink.calls == [
        ("note_on", 1, 0, 60, 110),
        ("note_off", 1, 0, 60, 0),
        ("note_on", 1, 0, 64, 95),
    ]
    assert waits == [pytest.approx(0.12, abs=1e-6), pytest.approx(0.08, abs=1e-6)]


def test_replay_speed_2_reduces_wait_time_vs_speed_1(tmp_path: Path) -> None:
    source = tmp_path / "session.jsonl"
    rows = [
        _midi_row(session_id="s-replay-5", ts_rel_ms=0, kind="note_on", note=60, vel=100),
        _midi_row(session_id="s-replay-5", ts_rel_ms=100, kind="note_off", note=60, vel=0),
        _midi_row(session_id="s-replay-5", ts_rel_ms=250, kind="note_on", note=67, vel=90),
    ]
    _write_jsonl(source, rows)
    session = load_replay_session(source)

    waits_1x: list[float] = []
    waits_2x: list[float] = []
    SessionMidiReplayer(sleep_fn=lambda seconds: waits_1x.append(seconds)).replay(
        session,
        _SinkFake(),
        speed=1.0,
        dry_run=False,
    )
    SessionMidiReplayer(sleep_fn=lambda seconds: waits_2x.append(seconds)).replay(
        session,
        _SinkFake(),
        speed=2.0,
        dry_run=False,
    )

    assert sum(waits_2x) == pytest.approx(sum(waits_1x) / 2.0, rel=1e-6)


def test_invalid_midi_event_is_skipped_in_non_strict_mode(tmp_path: Path) -> None:
    source = tmp_path / "session.jsonl"
    rows = [
        _midi_row(session_id="s-replay-6", ts_rel_ms=0, kind="note_on", note=60, vel=100),
        {
            "schema_version": 1,
            "session_id": "s-replay-6",
            "event_type": "midi_event",
            "ts_rel_ms": 20,
            "wall_time_utc": "2026-03-14T12:00:00Z",
            "payload": {
                "event_kind": "note_off",
                "bus": 1,
                "channel": 0,
                "velocity": 0,
            },
        },
    ]
    _write_jsonl(source, rows)

    session = load_replay_session(source, strict=False)
    assert len(session.events) == 1
    assert session.skipped_records == 1


def test_invalid_midi_event_raises_in_strict_mode(tmp_path: Path) -> None:
    source = tmp_path / "session.jsonl"
    rows = [
        {
            "schema_version": 1,
            "session_id": "s-replay-7",
            "event_type": "midi_event",
            "ts_rel_ms": 10,
            "wall_time_utc": "2026-03-14T12:00:00Z",
            "payload": {
                "event_kind": "note_broken",
                "bus": 1,
                "channel": 0,
                "note": 60,
                "velocity": 100,
            },
        }
    ]
    _write_jsonl(source, rows)
    with pytest.raises(ReplayRecordError):
        _ = load_replay_session(source, strict=True)


def test_file_without_midi_events_returns_empty_replay_session(tmp_path: Path) -> None:
    source = tmp_path / "session.jsonl"
    rows = [
        {
            "schema_version": 1,
            "session_id": "s-replay-8",
            "event_type": "session_started",
            "ts_rel_ms": 0,
            "wall_time_utc": "2026-03-14T12:00:00Z",
            "payload": {"mode": "udp"},
        },
        {
            "schema_version": 1,
            "session_id": "s-replay-8",
            "event_type": "udp_stat",
            "ts_rel_ms": 100,
            "wall_time_utc": "2026-03-14T12:00:00Z",
            "payload": {"node_id": 7},
        },
    ]
    _write_jsonl(source, rows, with_empty_line=True)

    session = load_replay_session(source)
    assert session.session_id == "s-replay-8"
    assert session.events == ()
    assert session.stats.total_events == 0
    assert session.stats.duration_ms == 0


def test_empty_file_returns_empty_replay_session(tmp_path: Path) -> None:
    source = tmp_path / "session.jsonl"
    source.write_text("", encoding="utf-8")

    session = load_replay_session(source)
    assert session.events == ()
    assert session.stats.total_events == 0
    assert session.stats.duration_ms == 0
