from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.midi.byte_stream_parser import MidiByteStreamParser  # noqa: E402


def test_valid_stream_produces_expected_messages() -> None:
    parser = MidiByteStreamParser()
    batch = parser.feed(bytes([0x90, 60, 100, 0x80, 60, 0]))

    assert len(batch.issues) == 0
    assert len(batch.messages) == 2
    assert batch.messages[0].message_type == "note_on"
    assert batch.messages[0].channel == 0
    assert batch.messages[0].data == (60, 100)
    assert batch.messages[1].message_type == "note_off"
    assert batch.messages[1].data == (60, 0)


def test_partial_stream_is_buffered_without_crashing() -> None:
    parser = MidiByteStreamParser()

    first = parser.feed(bytes([0x90, 60]))
    second = parser.feed(bytes([100]))

    assert len(first.messages) == 0
    assert len(first.issues) == 0
    assert parser.snapshot().pending_data_bytes == 0
    assert len(second.messages) == 1
    assert second.messages[0].message_type == "note_on"
    assert second.messages[0].data == (60, 100)


def test_invalid_or_corrupt_bytes_do_not_break_parser() -> None:
    parser = MidiByteStreamParser()
    batch = parser.feed([0x01, 0x02, 0x90, 64, 127, 0xF7])

    assert len(batch.messages) == 1
    assert batch.messages[0].message_type == "note_on"
    assert len(batch.issues) >= 1
    assert any(issue.code in {"data_without_status", "unexpected_sysex_end"} for issue in batch.issues)


def test_multiple_messages_with_running_status_are_parsed() -> None:
    parser = MidiByteStreamParser(enable_running_status=True)
    batch = parser.feed(bytes([0x90, 60, 100, 61, 110, 62, 0]))

    assert len(batch.issues) == 0
    assert len(batch.messages) == 3
    assert batch.messages[0].data == (60, 100)
    assert batch.messages[1].data == (61, 110)
    assert batch.messages[1].is_running_status is True
    assert batch.messages[2].message_type == "note_on"
    assert batch.messages[2].normalized_type == "note_off"
