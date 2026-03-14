from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Protocol

from control_okua.core.midi.byte_stream_parser import (
    MidiByteStreamParser,
    ParsedMidiMessage,
)
from control_okua.transports.serial.serial_models import (
    SerialTransportConfig,
    SerialTransportMetrics,
    SerialTransportSnapshot,
)

try:
    import serial  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - resolved by environment in runtime
    serial = None


class SerialPortLike(Protocol):
    is_open: bool

    def read(self, size: int = ...) -> bytes:
        ...

    def close(self) -> None:
        ...


class SerialTransportError(RuntimeError):
    """Base error for serial transport operations."""


class SerialTransportConfigError(SerialTransportError):
    """Raised when serial transport configuration is invalid."""


class SerialTransportOpenError(SerialTransportError):
    """Raised when serial transport cannot open the configured port."""


@dataclass(frozen=True)
class SerialRuntimeEvent:
    level: str
    message: str


SerialPortFactory = Callable[[SerialTransportConfig], SerialPortLike]
OnMidiMessage = Callable[[ParsedMidiMessage], None]
OnRuntimeEvent = Callable[[SerialRuntimeEvent], None]


def default_serial_port_factory(cfg: SerialTransportConfig) -> SerialPortLike:
    if serial is None:
        raise SerialTransportOpenError("PySerial no esta disponible en este entorno.")
    return serial.Serial(
        port=cfg.port,
        baudrate=cfg.baudrate,
        timeout=cfg.timeout_s,
    )


class SerialTransportAdapter:
    """Real serial byte reader + MIDI parser with controlled runtime metrics."""

    def __init__(
        self,
        *,
        config: SerialTransportConfig,
        serial_port_factory: SerialPortFactory | None = None,
        parser: MidiByteStreamParser | None = None,
        on_message: OnMidiMessage | None = None,
        on_event: OnRuntimeEvent | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._config = config
        self._factory = serial_port_factory or default_serial_port_factory
        self._parser = parser or MidiByteStreamParser(
            enable_running_status=config.running_status
        )
        self._on_message = on_message
        self._on_event = on_event
        self._clock = clock or time.monotonic

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._serial_port: SerialPortLike | None = None
        self._messages: deque[ParsedMidiMessage] = deque()

        self._bytes_received = 0
        self._messages_parsed = 0
        self._parse_errors = 0
        self._read_errors = 0
        self._last_activity_ts: float | None = None
        self._last_error: str | None = None

    def start(self) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False

            if not isinstance(self._config.port, str) or not self._config.port.strip():
                msg = "No se puede iniciar serial: serial.port no configurado."
                self._last_error = msg
                self._emit_event("error", msg)
                raise SerialTransportConfigError(msg)

            try:
                self._serial_port = self._factory(self._config)
            except Exception as exc:
                msg = f"No se pudo abrir puerto serial '{self._config.port}': {exc}"
                self._last_error = msg
                self._emit_event("error", msg)
                raise SerialTransportOpenError(msg) from exc

            self._stop_event.clear()
            self._thread = threading.Thread(target=self._read_loop, daemon=True)
            self._thread.start()
            self._emit_event(
                "info",
                f"Serial iniciado en puerto '{self._config.port}' a {self._config.baudrate} baudios.",
            )
            return True

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

        with self._lock:
            self._thread = None
            self._close_port_locked()

    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive() and not self._stop_event.is_set()

    def snapshot(self) -> SerialTransportSnapshot:
        with self._lock:
            return SerialTransportSnapshot(
                port=self._config.port,
                baudrate=self._config.baudrate,
                is_running=self.is_running(),
                is_open=self._is_port_open_locked(),
                bytes_received=self._bytes_received,
                messages_parsed=self._messages_parsed,
                parse_errors=self._parse_errors,
                read_errors=self._read_errors,
                last_activity_ts=self._last_activity_ts,
                last_error=self._last_error,
            )

    def metrics(self) -> SerialTransportMetrics:
        with self._lock:
            return SerialTransportMetrics(
                bytes_received=self._bytes_received,
                messages_parsed=self._messages_parsed,
                parse_errors=self._parse_errors,
                read_errors=self._read_errors,
                last_activity_ts=self._last_activity_ts,
                last_error=self._last_error,
            )

    def pop_messages(self, *, max_items: int | None = None) -> list[ParsedMidiMessage]:
        with self._lock:
            if max_items is None or max_items < 0:
                max_items = len(self._messages)
            items: list[ParsedMidiMessage] = []
            for _ in range(min(max_items, len(self._messages))):
                items.append(self._messages.popleft())
            return items

    def _read_loop(self) -> None:
        while not self._stop_event.is_set():
            port = self._serial_port
            if port is None:
                break
            try:
                chunk = port.read(self._config.read_size)
            except Exception as exc:
                msg = f"Error de lectura serial: {exc}"
                with self._lock:
                    self._read_errors += 1
                    self._last_error = msg
                self._emit_event("error", msg)
                break

            if not chunk:
                continue

            now = self._clock()
            batch = self._parser.feed(chunk)
            with self._lock:
                self._bytes_received += len(chunk)
                self._messages_parsed += len(batch.messages)
                self._parse_errors += len(batch.issues)
                self._last_activity_ts = now
                self._messages.extend(batch.messages)
                if batch.issues:
                    self._last_error = f"Parseo MIDI con {len(batch.issues)} issue(s)."

            for issue in batch.issues:
                self._emit_event(
                    "warning",
                    f"Parseo MIDI serial ({issue.code}): {issue.message}",
                )

            if self._on_message is not None:
                for message in batch.messages:
                    try:
                        self._on_message(message)
                    except Exception:
                        # Callback failures should not crash serial runtime.
                        pass

        with self._lock:
            self._close_port_locked()

    def _is_port_open_locked(self) -> bool:
        port = self._serial_port
        if port is None:
            return False
        is_open = getattr(port, "is_open", True)
        return bool(is_open)

    def _close_port_locked(self) -> None:
        port = self._serial_port
        if port is None:
            return
        try:
            port.close()
        except Exception as exc:
            self._last_error = f"Error cerrando puerto serial: {exc}"
            self._emit_event("warning", self._last_error)
        finally:
            self._serial_port = None

    def _emit_event(self, level: str, message: str) -> None:
        callback = self._on_event
        if callback is None:
            return
        try:
            callback(SerialRuntimeEvent(level=level, message=message))
        except Exception:
            # Callback failures should not crash transport runtime.
            pass
