from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Any, Callable, Protocol

from control_okua.core.midi import MidiRouter, ParsedMidiMessage
from control_okua.core.session import BackendAvailability, BackendKind, SessionSpec
from control_okua.transports.serial import (
    SerialRuntimeEvent,
    SerialTransportAdapter,
    SerialTransportConfig,
    SerialTransportSnapshot,
)


class MidiRouterLike(Protocol):
    def open(self) -> None:
        ...

    def close(self) -> None:
        ...

    def opened_buses(self) -> list[int]:
        ...

    def send_note_on(self, bus: int, ch: int, note: int, vel: int) -> None:
        ...

    def send_note_off(self, bus: int, ch: int, note: int, vel: int = 0) -> None:
        ...

    def send_raw_midi(self, bus: int, data: bytes | list[int] | tuple[int, ...]) -> None:
        ...


class SerialTransportLike(Protocol):
    def start(self) -> bool:
        ...

    def stop(self) -> None:
        ...

    def is_running(self) -> bool:
        ...

    def snapshot(self) -> SerialTransportSnapshot:
        ...


RouterBuilder = Callable[[dict[str, Any]], MidiRouterLike]
TransportBuilder = Callable[..., SerialTransportLike]


class SerialBackendStartError(RuntimeError):
    """Raised when serial backend cannot start cleanly."""


class SerialBackendStopError(RuntimeError):
    """Raised when serial backend cannot stop cleanly."""


@dataclass(frozen=True)
class SerialBackendRuntimeSnapshot:
    is_running: bool
    port: str | None
    messages_routed: int
    last_activity_ts: float | None
    last_error: str | None
    last_event: str | None
    default_bus: int | None
    transport: SerialTransportSnapshot | None


def route_serial_message_to_midi_router(
    router: MidiRouterLike,
    message: ParsedMidiMessage,
    *,
    bus: int,
) -> None:
    if message.message_type == "note_on" and message.channel is not None and len(message.data) >= 2:
        router.send_note_on(bus=bus, ch=message.channel, note=message.data[0], vel=message.data[1])
        return

    if message.message_type == "note_off" and message.channel is not None and len(message.data) >= 2:
        router.send_note_off(bus=bus, ch=message.channel, note=message.data[0], vel=message.data[1])
        return

    router.send_raw_midi(bus=bus, data=message.raw_bytes)


class SerialSessionBackend:
    kind = BackendKind.SERIAL

    def __init__(
        self,
        cfg: dict[str, Any],
        *,
        router_builder: RouterBuilder | None = None,
        transport_builder: TransportBuilder | None = None,
        serial_port_factory: Callable[[SerialTransportConfig], Any] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._cfg = cfg if isinstance(cfg, dict) else {}
        self._router_builder = router_builder or MidiRouter.from_config
        self._transport_builder = transport_builder or SerialTransportAdapter
        self._serial_port_factory = serial_port_factory
        self._clock = clock or time.monotonic

        self._lock = threading.Lock()
        self._router: MidiRouterLike | None = None
        self._transport: SerialTransportLike | None = None
        self._default_bus: int | None = None
        self._messages_routed = 0
        self._last_activity_ts: float | None = None
        self._last_error: str | None = None
        self._last_event: str | None = None
        self._last_transport_snapshot: SerialTransportSnapshot | None = None

    def start(self, spec: SessionSpec) -> None:
        if not spec.is_valid:
            raise SerialBackendStartError(f"SessionSpec invalido para serial: {spec.reason}")
        if spec.backend is not BackendKind.SERIAL:
            raise SerialBackendStartError("SessionSpec no corresponde a backend serial.")
        if self.is_running():
            return

        self._last_error = None
        self._last_event = None
        self._messages_routed = 0
        self._last_activity_ts = None

        router = self._router_builder(self._cfg)
        try:
            router.open()
            default_bus = self._resolve_default_bus(router)
            with self._lock:
                self._router = router
                self._default_bus = default_bus
            transport = self._build_transport()
            started = transport.start()
            if not started:
                raise SerialBackendStartError("No se pudo iniciar transporte serial.")
        except Exception as exc:
            with self._lock:
                self._transport = None
                self._router = None
                self._default_bus = None
            try:
                router.close()
            except Exception:
                pass
            self._last_error = f"No se pudo iniciar backend serial: {exc}"
            raise SerialBackendStartError(self._last_error) from exc

        with self._lock:
            self._transport = transport
            self._capture_transport_snapshot_locked()

    def stop(self) -> None:
        transport = self._transport
        router = self._router
        stop_error: str | None = None

        if transport is not None:
            try:
                transport.stop()
            except Exception as exc:
                stop_error = f"Error deteniendo transporte serial: {exc}"
            finally:
                with self._lock:
                    self._capture_transport_snapshot_locked()

        if router is not None:
            try:
                router.close()
            except Exception as exc:
                msg = f"Error cerrando MIDI router serial: {exc}"
                if stop_error is None:
                    stop_error = msg
                else:
                    stop_error = f"{stop_error}; {msg}"

        with self._lock:
            self._transport = None
            self._router = None
            self._default_bus = None
            if stop_error is not None:
                self._last_error = stop_error

        if stop_error is not None:
            raise SerialBackendStopError(f"No se pudo detener backend serial: {stop_error}")

    def describe(self) -> str:
        snapshot = self.runtime_snapshot()
        port = snapshot.port or "sin puerto"
        bus = "?" if snapshot.default_bus is None else str(snapshot.default_bus)
        return f"Serial backend (port={port}, bus={bus})"

    def availability(self) -> BackendAvailability:
        return BackendAvailability(
            is_implemented=True,
            is_available=True,
            reason="Backend serial real disponible.",
        )

    def is_running(self) -> bool:
        transport = self._transport
        if transport is None:
            return False
        return transport.is_running()

    def runtime_snapshot(self) -> SerialBackendRuntimeSnapshot:
        with self._lock:
            transport_snapshot = self._snapshot_transport_locked()
            port = None
            if transport_snapshot is not None:
                port = transport_snapshot.port
            return SerialBackendRuntimeSnapshot(
                is_running=self.is_running(),
                port=port,
                messages_routed=self._messages_routed,
                last_activity_ts=self._last_activity_ts,
                last_error=self._last_error,
                last_event=self._last_event,
                default_bus=self._default_bus,
                transport=transport_snapshot,
            )

    def _build_transport(self) -> SerialTransportLike:
        kwargs: dict[str, Any] = {
            "config": SerialTransportConfig.from_config(self._cfg),
            "on_message": self._on_serial_message,
            "on_event": self._on_serial_event,
        }
        if self._serial_port_factory is not None:
            kwargs["serial_port_factory"] = self._serial_port_factory
        return self._transport_builder(**kwargs)

    def _on_serial_message(self, message: ParsedMidiMessage) -> None:
        router = self._router
        bus = self._default_bus
        if router is None or bus is None:
            return

        try:
            route_serial_message_to_midi_router(router, message, bus=bus)
        except Exception as exc:
            with self._lock:
                self._last_error = f"Error enrutando MIDI serial: {exc}"
            return

        with self._lock:
            self._messages_routed += 1
            self._last_activity_ts = self._clock()
            self._capture_transport_snapshot_locked()

    def _on_serial_event(self, event: SerialRuntimeEvent) -> None:
        with self._lock:
            self._last_event = f"{event.level}: {event.message}"
            if event.level.lower() == "error":
                self._last_error = event.message
            self._capture_transport_snapshot_locked()

    @staticmethod
    def _resolve_default_bus(router: MidiRouterLike) -> int:
        buses = router.opened_buses()
        if not buses:
            raise SerialBackendStartError("MidiRouter no abrio buses de salida.")
        if 0 in buses:
            return 0
        return sorted(buses)[0]

    def _snapshot_transport_locked(self) -> SerialTransportSnapshot | None:
        transport = self._transport
        if transport is None:
            return self._last_transport_snapshot
        try:
            snapshot = transport.snapshot()
        except Exception:
            return self._last_transport_snapshot
        self._last_transport_snapshot = snapshot
        return snapshot

    def _capture_transport_snapshot_locked(self) -> None:
        _ = self._snapshot_transport_locked()
