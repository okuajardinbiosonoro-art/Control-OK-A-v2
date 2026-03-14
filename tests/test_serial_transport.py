from __future__ import annotations

import sys
import time
from collections import deque
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.transports.serial import (  # noqa: E402
    SerialRuntimeEvent,
    SerialTransportAdapter,
    SerialTransportConfig,
    SerialTransportConfigError,
    SerialTransportOpenError,
)


class _FakeSerialPort:
    def __init__(
        self,
        chunks: list[bytes] | None = None,
        *,
        fail_on_read: bool = False,
    ) -> None:
        self._chunks = deque(chunks or [])
        self._fail_on_read = fail_on_read
        self.closed = False
        self.is_open = True

    def read(self, _size: int = 64) -> bytes:
        if self._fail_on_read:
            raise OSError("read failed")
        if self._chunks:
            return self._chunks.popleft()
        time.sleep(0.01)
        return b""

    def close(self) -> None:
        self.closed = True
        self.is_open = False


def _wait_until(predicate, timeout_s: float = 1.5) -> bool:
    start = time.monotonic()
    while (time.monotonic() - start) <= timeout_s:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_start_with_valid_config_reads_messages_from_fake_port() -> None:
    fake_port = _FakeSerialPort(chunks=[bytes([0x90, 60, 100])])
    events: list[SerialRuntimeEvent] = []

    adapter = SerialTransportAdapter(
        config=SerialTransportConfig(port="COM5", baudrate=115200),
        serial_port_factory=lambda _cfg: fake_port,
        on_event=events.append,
    )

    started = adapter.start()
    processed = _wait_until(lambda: adapter.snapshot().messages_parsed >= 1)
    messages = adapter.pop_messages()
    adapter.stop()

    assert started is True
    assert processed is True
    assert len(messages) >= 1
    assert messages[0].message_type == "note_on"
    assert messages[0].data == (60, 100)
    assert any(event.level == "info" for event in events)


def test_stop_closes_resources_cleanly_and_is_idempotent() -> None:
    fake_port = _FakeSerialPort(chunks=[])
    adapter = SerialTransportAdapter(
        config=SerialTransportConfig(port="COM6", baudrate=115200),
        serial_port_factory=lambda _cfg: fake_port,
    )

    adapter.start()
    adapter.stop()
    adapter.stop()

    snapshot = adapter.snapshot()
    assert snapshot.is_running is False
    assert snapshot.is_open is False
    assert fake_port.closed is True


def test_open_error_is_reported_with_controlled_exception() -> None:
    def _broken_factory(_cfg: SerialTransportConfig):
        raise OSError("port not found")

    adapter = SerialTransportAdapter(
        config=SerialTransportConfig(port="COM404", baudrate=115200),
        serial_port_factory=_broken_factory,
    )

    try:
        adapter.start()
        assert False, "start() debia fallar con SerialTransportOpenError"
    except SerialTransportOpenError as exc:
        assert "no se pudo abrir puerto serial" in str(exc).lower()


def test_read_error_is_reported_without_crashing_transport() -> None:
    fake_port = _FakeSerialPort(fail_on_read=True)
    events: list[SerialRuntimeEvent] = []
    adapter = SerialTransportAdapter(
        config=SerialTransportConfig(port="COM7", baudrate=115200),
        serial_port_factory=lambda _cfg: fake_port,
        on_event=events.append,
    )

    adapter.start()
    observed_error = _wait_until(lambda: adapter.snapshot().read_errors >= 1)
    adapter.stop()

    assert observed_error is True
    assert any(event.level == "error" for event in events)
    assert any("lectura serial" in event.message.lower() for event in events)


def test_metrics_update_for_bytes_messages_and_parse_issues() -> None:
    fake_port = _FakeSerialPort(chunks=[bytes([0x01, 0x90, 60, 120])])
    adapter = SerialTransportAdapter(
        config=SerialTransportConfig(port="COM8", baudrate=115200),
        serial_port_factory=lambda _cfg: fake_port,
    )

    adapter.start()
    processed = _wait_until(lambda: adapter.snapshot().messages_parsed >= 1)
    adapter.stop()
    metrics = adapter.metrics()

    assert processed is True
    assert metrics.bytes_received >= 4
    assert metrics.messages_parsed >= 1
    assert metrics.parse_errors >= 1


def test_missing_port_configuration_uses_controlled_config_error() -> None:
    adapter = SerialTransportAdapter(
        config=SerialTransportConfig(port=None, baudrate=115200),
        serial_port_factory=lambda _cfg: _FakeSerialPort(),
    )

    try:
        adapter.start()
        assert False, "start() debia fallar con SerialTransportConfigError"
    except SerialTransportConfigError as exc:
        assert "serial.port no configurado" in str(exc).lower()


def test_transport_can_run_fully_with_fake_source_without_hardware() -> None:
    fake_port = _FakeSerialPort(chunks=[bytes([0x90, 64, 100]), bytes([65, 0])])
    parsed_count = 0

    def _on_message(_message) -> None:
        nonlocal parsed_count
        parsed_count += 1

    adapter = SerialTransportAdapter(
        config=SerialTransportConfig(port="COM9", baudrate=115200),
        serial_port_factory=lambda _cfg: fake_port,
        on_message=_on_message,
    )

    adapter.start()
    processed = _wait_until(lambda: adapter.snapshot().messages_parsed >= 2)
    adapter.stop()

    assert processed is True
    assert parsed_count >= 2
