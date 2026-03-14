from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ReplayEventKind(str, Enum):
    NOTE_ON = "note_on"
    NOTE_OFF = "note_off"


@dataclass(frozen=True)
class ReplayMidiEvent:
    ts_rel_ms: int
    event_kind: ReplayEventKind
    bus: int
    channel: int
    note: int
    velocity: int
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        if int(self.ts_rel_ms) < 0:
            raise ValueError("ts_rel_ms must be >= 0")
        if int(self.bus) < 0:
            raise ValueError("bus must be >= 0")
        if int(self.channel) < 0:
            raise ValueError("channel must be >= 0")
        if int(self.note) < 0:
            raise ValueError("note must be >= 0")
        if int(self.velocity) < 0:
            raise ValueError("velocity must be >= 0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts_rel_ms": int(self.ts_rel_ms),
            "event_kind": self.event_kind.value,
            "bus": int(self.bus),
            "channel": int(self.channel),
            "note": int(self.note),
            "velocity": int(self.velocity),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ReplayStats:
    total_events: int
    total_note_on: int
    total_note_off: int
    first_ts_ms: int | None
    last_ts_ms: int | None
    duration_ms: int

    def to_dict(self) -> dict[str, int | None]:
        return {
            "total_events": int(self.total_events),
            "total_note_on": int(self.total_note_on),
            "total_note_off": int(self.total_note_off),
            "first_ts_ms": self.first_ts_ms,
            "last_ts_ms": self.last_ts_ms,
            "duration_ms": int(self.duration_ms),
        }


@dataclass(frozen=True)
class ReplaySession:
    session_id: str
    events: tuple[ReplayMidiEvent, ...]
    duration_ms: int
    stats: ReplayStats
    skipped_records: int = 0


def build_replay_stats(events: list[ReplayMidiEvent] | tuple[ReplayMidiEvent, ...]) -> ReplayStats:
    if not events:
        return ReplayStats(
            total_events=0,
            total_note_on=0,
            total_note_off=0,
            first_ts_ms=None,
            last_ts_ms=None,
            duration_ms=0,
        )
    ordered = sorted(events, key=lambda event: int(event.ts_rel_ms))
    total_note_on = sum(1 for event in ordered if event.event_kind is ReplayEventKind.NOTE_ON)
    total_note_off = sum(1 for event in ordered if event.event_kind is ReplayEventKind.NOTE_OFF)
    first_ts = int(ordered[0].ts_rel_ms)
    last_ts = int(ordered[-1].ts_rel_ms)
    return ReplayStats(
        total_events=len(ordered),
        total_note_on=total_note_on,
        total_note_off=total_note_off,
        first_ts_ms=first_ts,
        last_ts_ms=last_ts,
        duration_ms=max(0, last_ts - first_ts),
    )
