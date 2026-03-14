from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Any, Callable, Protocol

from control_okua.core.midi import MidiRouter
from control_okua.core.registry import (
    NodeRegistry,
    NodeRegistrySummary,
    NodeSnapshot,
)
from control_okua.core.session import BackendAvailability, BackendKind, SessionSpec
from control_okua.core.udp import OkuaEvtPacket, OkuaStatPacket
from control_okua.transports.udp import (
    UdpReceivedEvtPacket,
    UdpReceivedStatPacket,
    UdpRuntimeEvent,
    UdpTransportAdapter,
    UdpTransportConfig,
    UdpTransportSnapshot,
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


class UdpTransportLike(Protocol):
    def start(self) -> bool:
        ...

    def stop(self) -> None:
        ...

    def is_running(self) -> bool:
        ...

    def snapshot(self) -> UdpTransportSnapshot:
        ...


RouterBuilder = Callable[[dict[str, Any]], MidiRouterLike]
TransportBuilder = Callable[..., UdpTransportLike]
RecordEventSink = Callable[[str, dict[str, Any]], None]


class UdpBackendStartError(RuntimeError):
    """Raised when UDP backend cannot start cleanly."""


class UdpBackendStopError(RuntimeError):
    """Raised when UDP backend cannot stop cleanly."""


@dataclass(frozen=True)
class UdpEvtRuntimeSummary:
    node_id: int
    seq: int
    midi_bus: int
    midi_ch: int
    note: int
    vel: int
    ts_ms: int
    source_ip: str
    source_port: int
    received_ts: float


@dataclass(frozen=True)
class UdpStatRuntimeSummary:
    node_id: int
    seq: int
    uptime_s: int
    rssi_dbm: int
    pps_x10: int
    vbat_mv: int
    source_ip: str
    source_port: int
    received_ts: float


@dataclass(frozen=True)
class UdpBackendRuntimeSnapshot:
    is_running: bool
    messages_routed: int
    last_activity_ts: float | None
    last_error: str | None
    last_event: str | None
    opened_buses: tuple[int, ...]
    total_evt_packets: int
    total_stat_packets: int
    total_bytes_received: int
    parse_errors: int
    socket_errors: int
    last_packet_summary: str | None
    last_evt: UdpEvtRuntimeSummary | None
    last_stat: UdpStatRuntimeSummary | None
    transport: UdpTransportSnapshot | None


def route_udp_evt_to_midi_router(router: MidiRouterLike, packet: OkuaEvtPacket) -> None:
    router.send_note_on(
        bus=packet.midi_bus,
        ch=packet.midi_ch,
        note=packet.note,
        vel=packet.vel,
    )


class UdpSessionBackend:
    kind = BackendKind.UDP

    def __init__(
        self,
        cfg: dict[str, Any],
        *,
        router_builder: RouterBuilder | None = None,
        transport_builder: TransportBuilder | None = None,
        socket_factory: Callable[[], Any] | None = None,
        clock: Callable[[], float] | None = None,
        record_event_sink: RecordEventSink | None = None,
    ) -> None:
        self._cfg = cfg if isinstance(cfg, dict) else {}
        self._router_builder = router_builder or MidiRouter.from_config
        self._transport_builder = transport_builder or UdpTransportAdapter
        self._socket_factory = socket_factory
        self._clock = clock or time.monotonic
        self._record_event_sink = record_event_sink

        self._lock = threading.Lock()
        self._router: MidiRouterLike | None = None
        self._transport: UdpTransportLike | None = None
        self._messages_routed = 0
        self._last_activity_ts: float | None = None
        self._last_error: str | None = None
        self._last_event: str | None = None
        self._last_evt: UdpEvtRuntimeSummary | None = None
        self._last_stat: UdpStatRuntimeSummary | None = None
        self._opened_buses: tuple[int, ...] = ()
        self._last_transport_snapshot: UdpTransportSnapshot | None = None
        self._node_registry: NodeRegistry | None = None

    def set_record_event_sink(self, sink: RecordEventSink | None) -> None:
        self._record_event_sink = sink

    def start(self, spec: SessionSpec) -> None:
        if not spec.is_valid:
            raise UdpBackendStartError(f"SessionSpec invalido para UDP: {spec.reason}")
        if not _is_udp_compatible_spec(spec):
            raise UdpBackendStartError("SessionSpec no corresponde a una operacion UDP.")
        if self.is_running():
            return

        self._last_error = None
        self._last_event = None
        self._messages_routed = 0
        self._last_activity_ts = None
        self._last_evt = None
        self._last_stat = None
        self._opened_buses = ()
        self._node_registry = NodeRegistry(clock=self._clock)

        router = self._router_builder(self._cfg)
        transport: UdpTransportLike | None = None
        try:
            router.open()
            opened_buses = tuple(sorted(router.opened_buses()))
            if not opened_buses:
                raise UdpBackendStartError("MidiRouter no abrio buses de salida.")
            with self._lock:
                self._router = router
                self._opened_buses = opened_buses
            transport = self._build_transport()
            started = transport.start()
            if not started:
                raise UdpBackendStartError("No se pudo iniciar transporte UDP.")
        except Exception as exc:
            if transport is not None:
                try:
                    transport.stop()
                except Exception:
                    pass
            with self._lock:
                self._transport = None
                self._router = None
                self._opened_buses = ()
                self._node_registry = None
            try:
                router.close()
            except Exception:
                pass
            self._last_error = f"No se pudo iniciar backend UDP: {exc}"
            raise UdpBackendStartError(self._last_error) from exc

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
                stop_error = f"Error deteniendo transporte UDP: {exc}"
            finally:
                with self._lock:
                    self._capture_transport_snapshot_locked()

        if router is not None:
            try:
                router.close()
            except Exception as exc:
                msg = f"Error cerrando MIDI router UDP: {exc}"
                if stop_error is None:
                    stop_error = msg
                else:
                    stop_error = f"{stop_error}; {msg}"

        with self._lock:
            self._transport = None
            self._router = None
            self._opened_buses = ()
            if self._node_registry is not None:
                self._node_registry.clear()
            self._node_registry = None
            if stop_error is not None:
                self._last_error = stop_error

        if stop_error is not None:
            raise UdpBackendStopError(f"No se pudo detener backend UDP: {stop_error}")

    def describe(self) -> str:
        snapshot = self.runtime_snapshot()
        transport = snapshot.transport
        if transport is None:
            return "UDP backend (sin transporte activo)"
        return (
            "UDP backend "
            f"({transport.bind_ip} evt:{transport.evt_port} stat:{transport.stat_port})"
        )

    def availability(self) -> BackendAvailability:
        return BackendAvailability(
            is_implemented=True,
            is_available=True,
            reason="Backend UDP real disponible.",
        )

    def is_running(self) -> bool:
        transport = self._transport
        if transport is None:
            return False
        return transport.is_running()

    def runtime_snapshot(self) -> UdpBackendRuntimeSnapshot:
        with self._lock:
            transport_snapshot = self._snapshot_transport_locked()
            total_evt_packets = 0
            total_stat_packets = 0
            total_bytes_received = 0
            parse_errors = 0
            socket_errors = 0
            last_packet_summary: str | None = None
            if transport_snapshot is not None:
                total_evt_packets = transport_snapshot.total_evt_packets
                total_stat_packets = transport_snapshot.total_stat_packets
                total_bytes_received = transport_snapshot.total_bytes_received
                parse_errors = transport_snapshot.parse_errors
                socket_errors = transport_snapshot.socket_errors
                last_packet_summary = transport_snapshot.last_packet_summary

            return UdpBackendRuntimeSnapshot(
                is_running=self.is_running(),
                messages_routed=self._messages_routed,
                last_activity_ts=self._last_activity_ts,
                last_error=self._last_error,
                last_event=self._last_event,
                opened_buses=self._opened_buses,
                total_evt_packets=total_evt_packets,
                total_stat_packets=total_stat_packets,
                total_bytes_received=total_bytes_received,
                parse_errors=parse_errors,
                socket_errors=socket_errors,
                last_packet_summary=last_packet_summary,
                last_evt=self._last_evt,
                last_stat=self._last_stat,
                transport=transport_snapshot,
            )

    def get_node_registry_summary(self, now: float | None = None) -> NodeRegistrySummary | None:
        with self._lock:
            if self._node_registry is None:
                return None
            return self._node_registry.get_summary(now=now)

    def get_node_snapshots(self, now: float | None = None) -> list[NodeSnapshot]:
        with self._lock:
            if self._node_registry is None:
                return []
            return self._node_registry.get_all_node_snapshots(now=now)

    def get_node_snapshot(self, node_id: int, now: float | None = None) -> NodeSnapshot | None:
        with self._lock:
            if self._node_registry is None:
                return None
            return self._node_registry.get_node_snapshot(node_id=node_id, now=now)

    def _build_transport(self) -> UdpTransportLike:
        kwargs: dict[str, Any] = {
            "config": UdpTransportConfig.from_config(self._cfg),
            "on_evt_packet": self._on_evt_packet,
            "on_stat_packet": self._on_stat_packet,
            "on_event": self._on_transport_event,
        }
        if self._socket_factory is not None:
            kwargs["socket_factory"] = self._socket_factory
        return self._transport_builder(**kwargs)

    def _on_evt_packet(self, event: UdpReceivedEvtPacket) -> None:
        router = self._router
        if router is None:
            return

        evt_payload = {
            "node_id": int(event.packet.header.node_id),
            "seq": int(event.packet.header.seq),
            "midi_bus": int(event.packet.midi_bus),
            "midi_ch": int(event.packet.midi_ch),
            "note": int(event.packet.note),
            "vel": int(event.packet.vel),
            "ts_ms": int(event.packet.ts_ms),
            "rssi_dbm": int(event.packet.rssi_dbm),
            "flags": int(event.packet.flags),
            "source_ip": str(event.source_ip),
            "source_port": int(event.source_port),
            "received_ts": float(event.received_ts),
        }
        self._emit_record_event("udp_evt", evt_payload)

        midi_event_kind = "note_off" if int(event.packet.vel) == 0 else "note_on"
        self._emit_record_event(
            "midi_event",
            {
                "source": "udp_evt",
                "event_kind": midi_event_kind,
                "bus": int(event.packet.midi_bus),
                "channel": int(event.packet.midi_ch),
                "note": int(event.packet.note),
                "velocity": int(event.packet.vel),
                "node_id": int(event.packet.header.node_id),
                "seq": int(event.packet.header.seq),
            },
        )

        with self._lock:
            if self._node_registry is not None:
                self._node_registry.observe_evt(event.packet, received_at=event.received_ts)

        try:
            route_udp_evt_to_midi_router(router, event.packet)
        except Exception as exc:
            with self._lock:
                self._last_error = f"Error enrutando EVT UDP a MIDI: {exc}"
            return

        with self._lock:
            self._messages_routed += 1
            self._last_activity_ts = self._clock()
            self._last_evt = _build_evt_summary(event)
            self._capture_transport_snapshot_locked()

    def _on_stat_packet(self, event: UdpReceivedStatPacket) -> None:
        self._emit_record_event(
            "udp_stat",
            {
                "node_id": int(event.packet.header.node_id),
                "seq": int(event.packet.header.seq),
                "uptime_s": int(event.packet.uptime_s),
                "rssi_dbm": int(event.packet.rssi_dbm),
                "state_flags": int(event.packet.state_flags),
                "pps_x10": int(event.packet.pps_x10),
                "vbat_mv": int(event.packet.vbat_mv),
                "source_ip": str(event.source_ip),
                "source_port": int(event.source_port),
                "received_ts": float(event.received_ts),
            },
        )
        with self._lock:
            if self._node_registry is not None:
                self._node_registry.observe_stat(event.packet, received_at=event.received_ts)
            self._last_activity_ts = self._clock()
            self._last_stat = _build_stat_summary(event)
            self._capture_transport_snapshot_locked()

    def _on_transport_event(self, event: UdpRuntimeEvent) -> None:
        with self._lock:
            self._last_event = f"{event.level}: {event.message}"
            if event.level.lower() == "error":
                self._last_error = event.message
            self._capture_transport_snapshot_locked()
        self._emit_record_event(
            "backend_runtime",
            {
                "source": "udp_event",
                "level": str(event.level),
                "message": str(event.message),
            },
        )

    def _snapshot_transport_locked(self) -> UdpTransportSnapshot | None:
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

    def _emit_record_event(self, event_type: str, payload: dict[str, Any]) -> None:
        sink = self._record_event_sink
        if sink is None:
            return
        try:
            sink(event_type, payload)
        except Exception:
            # Recording must never break backend runtime behavior.
            return


def _is_udp_compatible_spec(spec: SessionSpec) -> bool:
    if spec.mode != "udp":
        return False
    return spec.backend in {BackendKind.UDP, BackendKind.LAB}


def _build_evt_summary(event: UdpReceivedEvtPacket) -> UdpEvtRuntimeSummary:
    packet: OkuaEvtPacket = event.packet
    return UdpEvtRuntimeSummary(
        node_id=packet.header.node_id,
        seq=packet.header.seq,
        midi_bus=packet.midi_bus,
        midi_ch=packet.midi_ch,
        note=packet.note,
        vel=packet.vel,
        ts_ms=packet.ts_ms,
        source_ip=event.source_ip,
        source_port=event.source_port,
        received_ts=event.received_ts,
    )


def _build_stat_summary(event: UdpReceivedStatPacket) -> UdpStatRuntimeSummary:
    packet: OkuaStatPacket = event.packet
    return UdpStatRuntimeSummary(
        node_id=packet.header.node_id,
        seq=packet.header.seq,
        uptime_s=packet.uptime_s,
        rssi_dbm=packet.rssi_dbm,
        pps_x10=packet.pps_x10,
        vbat_mv=packet.vbat_mv,
        source_ip=event.source_ip,
        source_port=event.source_port,
        received_ts=event.received_ts,
    )
