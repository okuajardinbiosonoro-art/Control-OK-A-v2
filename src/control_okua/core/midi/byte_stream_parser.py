from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class ParsedMidiMessage:
    status: int
    data: tuple[int, ...]
    message_type: str
    channel: int | None
    is_running_status: bool = False

    @property
    def normalized_type(self) -> str:
        if self.message_type == "note_on" and len(self.data) >= 2 and self.data[1] == 0:
            return "note_off"
        return self.message_type

    @property
    def raw_bytes(self) -> tuple[int, ...]:
        return (self.status, *self.data)


@dataclass(frozen=True)
class MidiParseIssue:
    code: str
    message: str
    byte_value: int | None = None


@dataclass(frozen=True)
class MidiParseBatch:
    messages: tuple[ParsedMidiMessage, ...]
    issues: tuple[MidiParseIssue, ...]


@dataclass(frozen=True)
class MidiParserState:
    running_status: int | None
    pending_data_bytes: int
    in_sysex: bool
    sysex_length: int


_CHANNEL_STATUS_DATA_BYTES: dict[int, int] = {
    0x8: 2,
    0x9: 2,
    0xA: 2,
    0xB: 2,
    0xC: 1,
    0xD: 1,
    0xE: 2,
}

_SYSTEM_COMMON_DATA_BYTES: dict[int, int] = {
    0xF1: 1,
    0xF2: 2,
    0xF3: 1,
    0xF6: 0,
}

_REALTIME_STATUS: set[int] = {0xF8, 0xFA, 0xFB, 0xFC, 0xFE, 0xFF}

_CHANNEL_STATUS_NAMES: dict[int, str] = {
    0x8: "note_off",
    0x9: "note_on",
    0xA: "poly_aftertouch",
    0xB: "control_change",
    0xC: "program_change",
    0xD: "channel_aftertouch",
    0xE: "pitch_bend",
}

_SYSTEM_COMMON_NAMES: dict[int, str] = {
    0xF1: "time_code_quarter_frame",
    0xF2: "song_position_pointer",
    0xF3: "song_select",
    0xF6: "tune_request",
}

_REALTIME_NAMES: dict[int, str] = {
    0xF8: "timing_clock",
    0xFA: "start",
    0xFB: "continue",
    0xFC: "stop",
    0xFE: "active_sensing",
    0xFF: "system_reset",
}


class MidiByteStreamParser:
    """Incremental MIDI byte parser compatible with running status behavior."""

    def __init__(self, *, enable_running_status: bool = True, max_sysex_bytes: int = 4096) -> None:
        self._enable_running_status = bool(enable_running_status)
        self._max_sysex_bytes = max(1, int(max_sysex_bytes))
        self.reset()

    def reset(self) -> None:
        self._running_status: int | None = None
        self._active_status: int | None = None
        self._active_from_running_status = False
        self._expected_data_len = 0
        self._pending_data: list[int] = []
        self._in_sysex = False
        self._sysex_data: list[int] = []

    def snapshot(self) -> MidiParserState:
        return MidiParserState(
            running_status=self._running_status,
            pending_data_bytes=len(self._pending_data),
            in_sysex=self._in_sysex,
            sysex_length=len(self._sysex_data),
        )

    def feed(self, chunk: bytes | bytearray | Sequence[int]) -> MidiParseBatch:
        messages: list[ParsedMidiMessage] = []
        issues: list[MidiParseIssue] = []
        values = self._coerce_bytes(chunk, issues)
        for value in values:
            self._consume_byte(value, messages, issues)
        return MidiParseBatch(messages=tuple(messages), issues=tuple(issues))

    def _coerce_bytes(
        self,
        chunk: bytes | bytearray | Sequence[int],
        issues: list[MidiParseIssue],
    ) -> list[int]:
        coerced: list[int] = []
        if isinstance(chunk, (bytes, bytearray)):
            return list(chunk)

        for raw_value in chunk:
            try:
                value = int(raw_value)
            except (TypeError, ValueError):
                issues.append(
                    MidiParseIssue(
                        code="invalid_byte_type",
                        message="Se ignoro valor no convertible a byte MIDI.",
                    )
                )
                continue
            if value < 0 or value > 255:
                issues.append(
                    MidiParseIssue(
                        code="byte_out_of_range",
                        message="Se ignoro byte MIDI fuera de rango (0..255).",
                        byte_value=value,
                    )
                )
                continue
            coerced.append(value)
        return coerced

    def _consume_byte(
        self,
        value: int,
        messages: list[ParsedMidiMessage],
        issues: list[MidiParseIssue],
    ) -> None:
        if value in _REALTIME_STATUS:
            messages.append(
                ParsedMidiMessage(
                    status=value,
                    data=(),
                    message_type=_REALTIME_NAMES.get(value, "system_realtime"),
                    channel=None,
                    is_running_status=False,
                )
            )
            return

        if self._in_sysex:
            if value == 0xF7:
                messages.append(
                    ParsedMidiMessage(
                        status=0xF0,
                        data=tuple(self._sysex_data),
                        message_type="sysex",
                        channel=None,
                    )
                )
                self._in_sysex = False
                self._sysex_data = []
                return
            if value >= 0x80:
                issues.append(
                    MidiParseIssue(
                        code="sysex_interrupted",
                        message="Sysex interrumpido por status inesperado.",
                        byte_value=value,
                    )
                )
                self._in_sysex = False
                self._sysex_data = []
                # Reconsume as normal status byte.
                self._consume_byte(value, messages, issues)
                return

            self._sysex_data.append(value)
            if len(self._sysex_data) > self._max_sysex_bytes:
                issues.append(
                    MidiParseIssue(
                        code="sysex_too_long",
                        message="Sysex excede longitud maxima configurada; buffer reiniciado.",
                    )
                )
                self._in_sysex = False
                self._sysex_data = []
            return

        if value >= 0x80:
            self._consume_status_byte(value, messages, issues)
            return

        self._consume_data_byte(value, messages, issues)

    def _consume_status_byte(
        self,
        status: int,
        messages: list[ParsedMidiMessage],
        issues: list[MidiParseIssue],
    ) -> None:
        if 0x80 <= status <= 0xEF:
            self._active_status = status
            self._active_from_running_status = False
            self._expected_data_len = _CHANNEL_STATUS_DATA_BYTES[status >> 4]
            self._pending_data = []
            if self._enable_running_status:
                self._running_status = status
            else:
                self._running_status = None
            return

        if status == 0xF0:
            self._in_sysex = True
            self._sysex_data = []
            self._active_status = None
            self._active_from_running_status = False
            self._expected_data_len = 0
            self._pending_data = []
            self._running_status = None
            return

        if status == 0xF7:
            issues.append(
                MidiParseIssue(
                    code="unexpected_sysex_end",
                    message="Se recibio Fin de Sysex (F7) sin Sysex activo.",
                    byte_value=status,
                )
            )
            self._active_status = None
            self._active_from_running_status = False
            self._expected_data_len = 0
            self._pending_data = []
            self._running_status = None
            return

        system_data_len = _SYSTEM_COMMON_DATA_BYTES.get(status)
        if system_data_len is not None:
            if system_data_len == 0:
                messages.append(
                    ParsedMidiMessage(
                        status=status,
                        data=(),
                        message_type=_SYSTEM_COMMON_NAMES.get(status, "system_common"),
                        channel=None,
                    )
                )
                self._active_status = None
                self._active_from_running_status = False
                self._expected_data_len = 0
                self._pending_data = []
            else:
                self._active_status = status
                self._active_from_running_status = False
                self._expected_data_len = system_data_len
                self._pending_data = []
            self._running_status = None
            return

        issues.append(
            MidiParseIssue(
                code="unsupported_status",
                message="Status MIDI no soportado; byte ignorado.",
                byte_value=status,
            )
        )
        self._active_status = None
        self._active_from_running_status = False
        self._expected_data_len = 0
        self._pending_data = []
        self._running_status = None

    def _consume_data_byte(
        self,
        value: int,
        messages: list[ParsedMidiMessage],
        issues: list[MidiParseIssue],
    ) -> None:
        if self._active_status is None:
            if self._enable_running_status and self._running_status is not None:
                self._active_status = self._running_status
                self._active_from_running_status = True
                self._expected_data_len = _CHANNEL_STATUS_DATA_BYTES[self._running_status >> 4]
                self._pending_data = [value]
                self._finalize_if_complete(messages)
                return

            issues.append(
                MidiParseIssue(
                    code="data_without_status",
                    message="Byte de datos recibido sin status MIDI activo.",
                    byte_value=value,
                )
            )
            return

        self._pending_data.append(value)
        self._finalize_if_complete(messages)

    def _finalize_if_complete(
        self,
        messages: list[ParsedMidiMessage],
    ) -> None:
        if self._active_status is None:
            return
        if len(self._pending_data) < self._expected_data_len:
            return

        status = self._active_status
        data = tuple(self._pending_data[: self._expected_data_len])
        messages.append(
            ParsedMidiMessage(
                status=status,
                data=data,
                message_type=self._message_type_for_status(status),
                channel=(status & 0x0F) if 0x80 <= status <= 0xEF else None,
                is_running_status=self._active_from_running_status,
            )
        )
        self._pending_data = []
        if 0x80 <= status <= 0xEF and self._enable_running_status:
            self._active_status = None
            self._active_from_running_status = False
            self._expected_data_len = 0
            return

        self._active_status = None
        self._active_from_running_status = False
        self._expected_data_len = 0

    @staticmethod
    def _message_type_for_status(status: int) -> str:
        if 0x80 <= status <= 0xEF:
            return _CHANNEL_STATUS_NAMES.get(status >> 4, "channel_message")
        if status in _SYSTEM_COMMON_NAMES:
            return _SYSTEM_COMMON_NAMES[status]
        if status in _REALTIME_NAMES:
            return _REALTIME_NAMES[status]
        if status == 0xF0:
            return "sysex"
        return "system_common"
