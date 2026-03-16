from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Any, Callable, Protocol

from control_okua.core.midi import MidiRouter
from control_okua.core.registry import NodeRegistry, NodeRegistrySummary, NodeSnapshot
from control_okua.core.session import BackendAvailability, BackendKind, SessionSpec
from control_okua.core.udp import (
    OKUA_MAGIC,
    OKUA_VERSION,
    BenchV0EvtPacket,
    BenchV0PingPacket,
    BenchV0PongPacket,
    BenchV0StatPacket,
    OkuaEvtPacket,
    OkuaHeader,
    OkuaPacketType,
    OkuaStatPacket,
)
from control_okua.transports.udp import (
    BenchV0ReceivedEvtPacket,
    BenchV0ReceivedPingPacket,
    BenchV0ReceivedPongPacket,
    BenchV0ReceivedStatPacket,
    BenchV0RuntimeEvent,
    BenchV0TransportAdapter,
    BenchV0TransportConfig,
    BenchV0TransportSnapshot,
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


class BenchTransportLike(Protocol):
    def start(self) -> bool:
        ...

    def stop(self) -> None:
        ...

    def is_running(self) -> bool:
        ...

    def snapshot(self) -> BenchV0TransportSnapshot:
        ...


RouterBuilder = Callable[[dict[str, Any]], MidiRouterLike]
TransportBuilder = Callable[..., BenchTransportLike]
RecordEventSink = Callable[[str, dict[str, Any]], None]


class UdpBenchCompatBackendStartError(RuntimeError):
    pass


class UdpBenchCompatBackendStopError(RuntimeError):
    pass


@dataclass(frozen=True)
class BenchEvtRuntimeSummary:
    node_id: int
    seq: int
    bench_seq: int
    midi_bus: int
    midi_ch: int
    note: int
    vel: int
    ts_ms: int
    source_ip: str
    source_port: int
    received_ts: float


@dataclass(frozen=True)
class BenchStatRuntimeSummary:
    node_id: int
    seq: int
    bench_seq: int
    uptime_s: int
    rssi_dbm: int
    pps_x10: int
    vbat_mv: int
    source_ip: str
    source_port: int
    received_ts: float


@dataclass(frozen=True)
class BenchPingRuntimeSummary:
    node_id: int
    bench_seq: int
    ts_ms: int
    rtt_ms: int
    source_ip: str
    source_port: int
    received_ts: float


@dataclass(frozen=True)
class BenchPongRuntimeSummary:
    node_id: int
    bench_seq: int
    ts_ms: int
    rtt_ms: int
    source_ip: str
    source_port: int
    received_ts: float


@dataclass(frozen=True)
class UdpBenchCompatRuntimeSnapshot:
    is_running: bool
    messages_routed: int
    last_activity_ts: float | None
    last_error: str | None
    last_event: str | None
    opened_buses: tuple[int, ...]
    total_evt_packets: int
    total_stat_packets: int
    total_ping_packets: int
    total_pong_packets: int
    total_pong_sent: int
    total_bytes_received: int
    parse_errors: int
    socket_errors: int
    last_packet_summary: str | None
    last_evt: BenchEvtRuntimeSummary | None
    last_stat: BenchStatRuntimeSummary | None
    last_ping: BenchPingRuntimeSummary | None
    last_pong: BenchPongRuntimeSummary | None
    transport: BenchV0TransportSnapshot | None


def route_bench_evt_to_midi_router(router: MidiRouterLike, packet: BenchV0EvtPacket) -> None:
    router.send_note_on(
        bus=int(packet.midi_bus),
        ch=int(packet.midi_ch),
        note=int(packet.note),
        vel=int(packet.vel),
    )


class UdpBenchCompatSessionBackend:
    kind = BackendKind.LAB

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
        self._transport_builder = transport_builder or BenchV0TransportAdapter
        self._socket_factory = socket_factory
        self._clock = clock or time.monotonic
        self._record_event_sink = record_event_sink

        self._lock = threading.Lock()
        self._router: MidiRouterLike | None = None
        self._transport: BenchTransportLike | None = None
        self._messages_routed = 0
        self._last_activity_ts: float | None = None
        self._last_error: str | None = None
        self._last_event: str | None = None
        self._last_evt: BenchEvtRuntimeSummary | None = None
        self._last_stat: BenchStatRuntimeSummary | None = None
        self._last_ping: BenchPingRuntimeSummary | None = None
        self._last_pong: BenchPongRuntimeSummary | None = None
        self._opened_buses: tuple[int, ...] = ()
        self._last_transport_snapshot: BenchV0TransportSnapshot | None = None
        self._node_registry: NodeRegistry | None = None
        self._virtual_evt_seq_by_node: dict[int, int] = {}
        self._virtual_stat_seq_by_node: dict[int, int] = {}

    def set_record_event_sink(self, sink: RecordEventSink | None) -> None:
        self._record_event_sink = sink

    def start(self, spec: SessionSpec) -> None:
        if not spec.is_valid:
            raise UdpBenchCompatBackendStartError(f"SessionSpec invalido para bench: {spec.reason}")
        if not _is_bench_compatible_spec(spec):
            raise UdpBenchCompatBackendStartError(
                "SessionSpec no corresponde a una operacion udp_bench_lab."
            )
        if self.is_running():
            return

        self._last_error = None
        self._last_event = None
        self._messages_routed = 0
        self._last_activity_ts = None
        self._last_evt = None
        self._last_stat = None
        self._last_ping = None
        self._last_pong = None
        self._opened_buses = ()
        self._node_registry = NodeRegistry(clock=self._clock)
        self._virtual_evt_seq_by_node.clear()
        self._virtual_stat_seq_by_node.clear()

        router = self._router_builder(self._cfg)
        transport: BenchTransportLike | None = None
        try:
            router.open()
            opened_buses = tuple(sorted(router.opened_buses()))
            if not opened_buses:
                raise UdpBenchCompatBackendStartError("MidiRouter no abrio buses de salida.")
            with self._lock:
                self._router = router
                self._opened_buses = opened_buses
            transport = self._build_transport()
            started = transport.start()
            if not started:
                raise UdpBenchCompatBackendStartError("No se pudo iniciar transporte UDP bench.")
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
                self._virtual_evt_seq_by_node.clear()
                self._virtual_stat_seq_by_node.clear()
            try:
                router.close()
            except Exception:
                pass
            self._last_error = f"No se pudo iniciar backend UDP bench: {exc}"
            raise UdpBenchCompatBackendStartError(self._last_error) from exc

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
                stop_error = f"Error deteniendo transporte UDP bench: {exc}"
            finally:
                with self._lock:
                    self._capture_transport_snapshot_locked()

        if router is not None:
            try:
                router.close()
            except Exception as exc:
                message = f"Error cerrando MIDI router bench: {exc}"
                if stop_error is None:
                    stop_error = message
                else:
                    stop_error = f"{stop_error}; {message}"

        with self._lock:
            self._transport = None
            self._router = None
            self._opened_buses = ()
            if self._node_registry is not None:
                self._node_registry.clear()
            self._node_registry = None
            self._virtual_evt_seq_by_node.clear()
            self._virtual_stat_seq_by_node.clear()
            if stop_error is not None:
                self._last_error = stop_error

        if stop_error is not None:
            raise UdpBenchCompatBackendStopError(
                f"No se pudo detener backend UDP bench: {stop_error}"
            )

    def describe(self) -> str:
        snapshot = self.runtime_snapshot()
        transport = snapshot.transport
        if transport is None:
            return "UDP bench backend (sin transporte activo)"
        return (
            "UDP bench backend "
            f"({transport.bind_ip} bench:{transport.bench_port} auto_pong=si)"
        )

    def availability(self) -> BackendAvailability:
        return BackendAvailability(
            is_implemented=True,
            is_available=True,
            reason="Backend UDP bench de compatibilidad disponible.",
        )

    def is_running(self) -> bool:
        transport = self._transport
        if transport is None:
            return False
        return transport.is_running()

    def runtime_snapshot(self) -> UdpBenchCompatRuntimeSnapshot:
        with self._lock:
            transport_snapshot = self._snapshot_transport_locked()
            total_evt_packets = 0
            total_stat_packets = 0
            total_ping_packets = 0
            total_pong_packets = 0
            total_pong_sent = 0
            total_bytes_received = 0
            parse_errors = 0
            socket_errors = 0
            last_packet_summary: str | None = None
            if transport_snapshot is not None:
                total_evt_packets = transport_snapshot.total_evt_packets
                total_stat_packets = transport_snapshot.total_stat_packets
                total_ping_packets = transport_snapshot.total_ping_packets
                total_pong_packets = transport_snapshot.total_pong_packets
                total_pong_sent = transport_snapshot.total_pong_sent
                total_bytes_received = transport_snapshot.total_bytes_received
                parse_errors = transport_snapshot.parse_errors
                socket_errors = transport_snapshot.socket_errors
                last_packet_summary = transport_snapshot.last_packet_summary

            return UdpBenchCompatRuntimeSnapshot(
                is_running=self.is_running(),
                messages_routed=self._messages_routed,
                last_activity_ts=self._last_activity_ts,
                last_error=self._last_error,
                last_event=self._last_event,
                opened_buses=self._opened_buses,
                total_evt_packets=total_evt_packets,
                total_stat_packets=total_stat_packets,
                total_ping_packets=total_ping_packets,
                total_pong_packets=total_pong_packets,
                total_pong_sent=total_pong_sent,
                total_bytes_received=total_bytes_received,
                parse_errors=parse_errors,
                socket_errors=socket_errors,
                last_packet_summary=last_packet_summary,
                last_evt=self._last_evt,
                last_stat=self._last_stat,
                last_ping=self._last_ping,
                last_pong=self._last_pong,
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

    def _build_transport(self) -> BenchTransportLike:
        kwargs: dict[str, Any] = {
            "config": BenchV0TransportConfig.from_config(self._cfg),
            "on_evt_packet": self._on_evt_packet,
            "on_stat_packet": self._on_stat_packet,
            "on_ping_packet": self._on_ping_packet,
            "on_pong_packet": self._on_pong_packet,
            "on_event": self._on_transport_event,
        }
        if self._socket_factory is not None:
            kwargs["socket_factory"] = self._socket_factory
        return self._transport_builder(**kwargs)

    def _on_evt_packet(self, event: BenchV0ReceivedEvtPacket) -> None:
        router = self._router
        if router is None:
            return

        packet = event.packet
        node_id = int(packet.header.node_id)
        bench_seq = int(packet.header.seq)
        virtual_seq = self._next_virtual_seq(self._virtual_evt_seq_by_node, node_id)
        translated_evt = _translate_bench_evt_to_okua(packet, virtual_seq=virtual_seq)

        self._emit_record_event(
            "bench_evt",
            {
                "node_id": node_id,
                "bench_seq": bench_seq,
                "virtual_seq_evt": virtual_seq,
                "midi_bus": int(packet.midi_bus),
                "midi_ch": int(packet.midi_ch),
                "note": int(packet.note),
                "vel": int(packet.vel),
                "ts_ms": int(packet.ts_ms),
                "rssi_dbm": int(packet.rssi_dbm),
                "source_ip": str(event.source_ip),
                "source_port": int(event.source_port),
                "received_ts": float(event.received_ts),
            },
        )
        midi_event_kind = "note_off" if int(packet.vel) == 0 else "note_on"
        self._emit_record_event(
            "midi_event",
            {
                "source": "bench_evt",
                "event_kind": midi_event_kind,
                "bus": int(packet.midi_bus),
                "channel": int(packet.midi_ch),
                "note": int(packet.note),
                "velocity": int(packet.vel),
                "node_id": node_id,
                "bench_seq": bench_seq,
                "virtual_seq_evt": virtual_seq,
            },
        )

        with self._lock:
            if self._node_registry is not None:
                self._node_registry.observe_evt(translated_evt, received_at=event.received_ts)

        try:
            route_bench_evt_to_midi_router(router, packet)
        except Exception as exc:
            with self._lock:
                self._last_error = f"Error enrutando EVT bench a MIDI: {exc}"
            return

        with self._lock:
            self._messages_routed += 1
            self._last_activity_ts = self._clock()
            self._last_evt = BenchEvtRuntimeSummary(
                node_id=node_id,
                seq=virtual_seq,
                bench_seq=bench_seq,
                midi_bus=int(packet.midi_bus),
                midi_ch=int(packet.midi_ch),
                note=int(packet.note),
                vel=int(packet.vel),
                ts_ms=int(packet.ts_ms),
                source_ip=str(event.source_ip),
                source_port=int(event.source_port),
                received_ts=float(event.received_ts),
            )
            self._capture_transport_snapshot_locked()

    def _on_stat_packet(self, event: BenchV0ReceivedStatPacket) -> None:
        packet = event.packet
        node_id = int(packet.header.node_id)
        bench_seq = int(packet.header.seq)
        virtual_seq = self._next_virtual_seq(self._virtual_stat_seq_by_node, node_id)
        translated_stat = _translate_bench_stat_to_okua(packet, virtual_seq=virtual_seq)

        self._emit_record_event(
            "bench_stat",
            {
                "node_id": node_id,
                "bench_seq": bench_seq,
                "virtual_seq_stat": virtual_seq,
                "uptime_s": int(packet.uptime_s),
                "rssi_dbm": int(packet.rssi_dbm),
                "state_flags": int(packet.state_flags),
                "pps_x10": int(packet.pps_x10),
                "vbat_mv": int(packet.vbat_mv),
                "source_ip": str(event.source_ip),
                "source_port": int(event.source_port),
                "received_ts": float(event.received_ts),
            },
        )

        with self._lock:
            if self._node_registry is not None:
                self._node_registry.observe_stat(translated_stat, received_at=event.received_ts)
            self._last_activity_ts = self._clock()
            self._last_stat = BenchStatRuntimeSummary(
                node_id=node_id,
                seq=virtual_seq,
                bench_seq=bench_seq,
                uptime_s=int(packet.uptime_s),
                rssi_dbm=int(packet.rssi_dbm),
                pps_x10=int(packet.pps_x10),
                vbat_mv=int(packet.vbat_mv),
                source_ip=str(event.source_ip),
                source_port=int(event.source_port),
                received_ts=float(event.received_ts),
            )
            self._capture_transport_snapshot_locked()

    def _on_ping_packet(self, event: BenchV0ReceivedPingPacket) -> None:
        packet = event.packet
        self._emit_record_event(
            "bench_ping",
            {
                "node_id": int(packet.header.node_id),
                "bench_seq": int(packet.header.seq),
                "ts_ms": int(packet.ts_ms),
                "rtt_ms": int(packet.rtt_ms),
                "source_ip": str(event.source_ip),
                "source_port": int(event.source_port),
                "received_ts": float(event.received_ts),
            },
        )
        with self._lock:
            self._last_activity_ts = self._clock()
            self._last_ping = BenchPingRuntimeSummary(
                node_id=int(packet.header.node_id),
                bench_seq=int(packet.header.seq),
                ts_ms=int(packet.ts_ms),
                rtt_ms=int(packet.rtt_ms),
                source_ip=str(event.source_ip),
                source_port=int(event.source_port),
                received_ts=float(event.received_ts),
            )
            self._capture_transport_snapshot_locked()

    def _on_pong_packet(self, event: BenchV0ReceivedPongPacket) -> None:
        packet = event.packet
        self._emit_record_event(
            "bench_pong",
            {
                "node_id": int(packet.header.node_id),
                "bench_seq": int(packet.header.seq),
                "ts_ms": int(packet.ts_ms),
                "rtt_ms": int(packet.rtt_ms),
                "source_ip": str(event.source_ip),
                "source_port": int(event.source_port),
                "received_ts": float(event.received_ts),
            },
        )
        with self._lock:
            self._last_activity_ts = self._clock()
            self._last_pong = BenchPongRuntimeSummary(
                node_id=int(packet.header.node_id),
                bench_seq=int(packet.header.seq),
                ts_ms=int(packet.ts_ms),
                rtt_ms=int(packet.rtt_ms),
                source_ip=str(event.source_ip),
                source_port=int(event.source_port),
                received_ts=float(event.received_ts),
            )
            self._capture_transport_snapshot_locked()

    def _on_transport_event(self, event: BenchV0RuntimeEvent) -> None:
        with self._lock:
            self._last_event = f"{event.level}: {event.message}"
            if event.level.lower() == "error":
                self._last_error = event.message
            self._capture_transport_snapshot_locked()
        self._emit_record_event(
            "backend_runtime",
            {
                "source": "udp_bench_event",
                "level": str(event.level),
                "message": str(event.message),
            },
        )

    def _snapshot_transport_locked(self) -> BenchV0TransportSnapshot | None:
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
            return

    @staticmethod
    def _next_virtual_seq(storage: dict[int, int], node_id: int) -> int:
        last = storage.get(int(node_id))
        if last is None:
            seq = 0
        else:
            seq = (int(last) + 1) & 0xFFFF
        storage[int(node_id)] = seq
        return seq


def _is_bench_compatible_spec(spec: SessionSpec) -> bool:
    if spec.mode != "udp":
        return False
    if spec.backend is not BackendKind.LAB:
        return False
    return spec.profile_id == "udp_bench_lab"


def _translate_bench_evt_to_okua(packet: BenchV0EvtPacket, *, virtual_seq: int) -> OkuaEvtPacket:
    return OkuaEvtPacket(
        header=OkuaHeader(
            magic=OKUA_MAGIC,
            version=OKUA_VERSION,
            packet_type=OkuaPacketType.EVT,
            node_id=int(packet.header.node_id) & 0xFFFF,
            seq=int(virtual_seq) & 0xFFFF,
        ),
        midi_bus=int(packet.midi_bus) & 0xFF,
        midi_ch=int(packet.midi_ch) & 0xFF,
        note=int(packet.note) & 0xFF,
        vel=int(packet.vel) & 0xFF,
        ts_ms=int(packet.ts_ms) & 0xFFFFFFFF,
        rssi_dbm=int(packet.rssi_dbm),
        flags=int(packet.flags) & 0xFF,
        rsv=(0, 0),
    )


def _translate_bench_stat_to_okua(packet: BenchV0StatPacket, *, virtual_seq: int) -> OkuaStatPacket:
    return OkuaStatPacket(
        header=OkuaHeader(
            magic=OKUA_MAGIC,
            version=OKUA_VERSION,
            packet_type=OkuaPacketType.STAT,
            node_id=int(packet.header.node_id) & 0xFFFF,
            seq=int(virtual_seq) & 0xFFFF,
        ),
        uptime_s=int(packet.uptime_s) & 0xFFFFFFFF,
        rssi_dbm=int(packet.rssi_dbm),
        state_flags=int(packet.state_flags) & 0xFF,
        pps_x10=int(packet.pps_x10) & 0xFFFF,
        vbat_mv=int(packet.vbat_mv) & 0xFFFF,
        free_heap=int(packet.free_heap) & 0xFFFFFFFF,
        fw_major=int(packet.fw_major) & 0xFF,
        fw_minor=int(packet.fw_minor) & 0xFF,
        reset_reason=int(packet.reset_reason) & 0xFF,
        rsv=(0, 0, 0),
    )
