from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.midi import ParsedMidiMessage  # noqa: E402
from control_okua.core.session import BackendKind, SessionSpec  # noqa: E402
from control_okua.services.backends import (  # noqa: E402
    SerialSessionBackend,
    route_serial_message_to_midi_router,
)
from control_okua.services.backends.serial_session_backend import (  # noqa: E402
    SerialBackendStartError,
)
from control_okua.transports.serial import (  # noqa: E402
    SerialRuntimeEvent,
    SerialTransportConfig,
    SerialTransportSnapshot,
)


def _serial_spec() -> SessionSpec:
    return SessionSpec(
        profile_id="serial_local",
        mode="serial",
        backend=BackendKind.SERIAL,
        is_valid=True,
        reason="ok",
    )


class _FakeMidiRouter:
    def __init__(self, buses: list[int] | None = None) -> None:
        self._buses = buses or [0]
        self.open_called = 0
        self.close_called = 0
        self.sent: list[tuple[Any, ...]] = []

    def open(self) -> None:
        self.open_called += 1

    def close(self) -> None:
        self.close_called += 1

    def opened_buses(self) -> list[int]:
        return list(self._buses)

    def send_note_on(self, bus: int, ch: int, note: int, vel: int) -> None:
        # Mirrors MidiRouter behavior where note_on vel=0 is translated to note_off.
        if vel == 0:
            self.send_note_off(bus=bus, ch=ch, note=note, vel=0)
            return
        self.sent.append(("note_on", bus, ch, note, vel))

    def send_note_off(self, bus: int, ch: int, note: int, vel: int = 0) -> None:
        self.sent.append(("note_off", bus, ch, note, vel))

    def send_raw_midi(self, bus: int, data: bytes | list[int] | tuple[int, ...]) -> None:
        self.sent.append(("raw", bus, tuple(int(value) for value in data)))


class _FakeTransport:
    def __init__(
        self,
        *,
        config: SerialTransportConfig,
        on_message=None,
        on_event=None,
        start_result: bool = True,
    ) -> None:
        self._config = config
        self._on_message = on_message
        self._on_event = on_event
        self._start_result = start_result
        self._running = False
        self._start_calls = 0
        self._stop_calls = 0
        self._bytes_received = 0
        self._messages_parsed = 0

    def start(self) -> bool:
        self._start_calls += 1
        self._running = self._start_result
        return self._start_result

    def stop(self) -> None:
        self._stop_calls += 1
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def snapshot(self) -> SerialTransportSnapshot:
        return SerialTransportSnapshot(
            port=self._config.port,
            baudrate=self._config.baudrate,
            is_running=self._running,
            is_open=self._running,
            bytes_received=self._bytes_received,
            messages_parsed=self._messages_parsed,
            parse_errors=0,
            read_errors=0,
            last_activity_ts=None,
            last_error=None,
        )

    def push_message(self, message: ParsedMidiMessage) -> None:
        self._messages_parsed += 1
        self._bytes_received += len(message.raw_bytes)
        if self._on_message is not None:
            self._on_message(message)

    def push_event(self, level: str, message: str) -> None:
        if self._on_event is not None:
            self._on_event(SerialRuntimeEvent(level=level, message=message))


def _cfg() -> dict[str, Any]:
    return {
        "profile": {"active": "serial_local"},
        "serial": {"port": "COM_TEST", "baudrate": 115200, "flush_ms": 5, "running_status": True},
        "midi": {"backend": "rtmidi", "outputs": {"0": "loopMIDI Port 1"}},
    }


def test_serial_backend_start_stop_and_runtime_snapshot() -> None:
    holder: dict[str, _FakeTransport] = {}
    router = _FakeMidiRouter()

    def _build_transport(**kwargs):
        transport = _FakeTransport(**kwargs)
        holder["transport"] = transport
        return transport

    backend = SerialSessionBackend(
        _cfg(),
        router_builder=lambda _cfg_value: router,
        transport_builder=_build_transport,
    )

    backend.start(_serial_spec())
    transport = holder["transport"]
    transport.push_message(
        ParsedMidiMessage(
            status=0x90,
            data=(60, 100),
            message_type="note_on",
            channel=0,
        )
    )

    snapshot = backend.runtime_snapshot()
    assert backend.is_running() is True
    assert snapshot.is_running is True
    assert snapshot.messages_routed >= 1
    assert snapshot.transport is not None
    assert ("note_on", 0, 0, 60, 100) in router.sent

    backend.stop()
    stopped_snapshot = backend.runtime_snapshot()
    assert backend.is_running() is False
    assert stopped_snapshot.is_running is False
    assert router.close_called == 1


def test_serial_backend_start_failure_does_not_leave_running_state() -> None:
    router = _FakeMidiRouter()
    backend = SerialSessionBackend(
        _cfg(),
        router_builder=lambda _cfg_value: router,
        transport_builder=lambda **kwargs: _FakeTransport(**kwargs, start_result=False),
    )

    try:
        backend.start(_serial_spec())
        assert False, "start() debia fallar cuando el transporte no inicia"
    except SerialBackendStartError as exc:
        assert "no se pudo iniciar backend serial" in str(exc).lower()

    assert backend.is_running() is False
    assert router.close_called == 1


def test_route_helper_keeps_note_on_vel_zero_semantics() -> None:
    router = _FakeMidiRouter()
    message = ParsedMidiMessage(
        status=0x90,
        data=(64, 0),
        message_type="note_on",
        channel=0,
    )

    route_serial_message_to_midi_router(router, message, bus=0)

    assert router.sent == [("note_off", 0, 0, 64, 0)]


def test_serial_backend_runtime_tracks_transport_errors() -> None:
    holder: dict[str, _FakeTransport] = {}
    backend = SerialSessionBackend(
        _cfg(),
        router_builder=lambda _cfg_value: _FakeMidiRouter(),
        transport_builder=lambda **kwargs: holder.setdefault("transport", _FakeTransport(**kwargs)),
    )
    backend.start(_serial_spec())
    holder["transport"].push_event("error", "Error de lectura serial: cable desconectado")

    snapshot = backend.runtime_snapshot()
    backend.stop()

    assert snapshot.last_error is not None
    assert "lectura serial" in snapshot.last_error.lower()
