from __future__ import annotations

from dataclasses import dataclass
import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.session import BackendKind, SessionSpec  # noqa: E402
from control_okua.core.udp import (  # noqa: E402
    BENCH_V0_MAGIC,
    BENCH_V0_VERSION,
    BenchV0EvtPacket,
    BenchV0Header,
    BenchV0MsgType,
    BenchV0PingPacket,
    BenchV0PongPacket,
    BenchV0StatPacket,
)
from control_okua.services.backends import UdpBenchCompatSessionBackend  # noqa: E402
from control_okua.transports.udp import (  # noqa: E402
    BenchV0ReceivedEvtPacket,
    BenchV0ReceivedPingPacket,
    BenchV0ReceivedPongPacket,
    BenchV0ReceivedStatPacket,
    BenchV0RuntimeEvent,
    BenchV0TransportConfig,
    BenchV0TransportSnapshot,
)


def _bench_spec() -> SessionSpec:
    return SessionSpec(
        profile_id="udp_bench_lab",
        mode="udp",
        backend=BackendKind.LAB,
        is_valid=True,
        reason="ok",
    )


def _bench_cfg() -> dict[str, Any]:
    return {
        "profile": {"active": "udp_bench_lab"},
        "mode": "udp",
        "udp": {
            "bind_ip": "127.0.0.1",
            "evt_port": 5005,
            "stat_port": 5006,
            "cmd_port": 5007,
            "rcvbuf_bytes": 262144,
            "bench_auto_pong": True,
        },
        "midi": {
            "backend": "rtmidi",
            "outputs": {"0": "loopMIDI Port 1", "1": "loopMIDI Port 2"},
            "send_noteoff_on_vel0": True,
        },
    }


class _FakeMidiRouter:
    def __init__(self) -> None:
        self._buses = [0, 1]
        self.sent: list[tuple[Any, ...]] = []

    def open(self) -> None:
        return None

    def close(self) -> None:
        return None

    def opened_buses(self) -> list[int]:
        return list(self._buses)

    def send_note_on(self, bus: int, ch: int, note: int, vel: int) -> None:
        if vel == 0:
            self.send_note_off(bus=bus, ch=ch, note=note, vel=0)
            return
        self.sent.append(("note_on", bus, ch, note, vel))

    def send_note_off(self, bus: int, ch: int, note: int, vel: int = 0) -> None:
        self.sent.append(("note_off", bus, ch, note, vel))

    def send_raw_midi(self, bus: int, data: bytes | list[int] | tuple[int, ...]) -> None:
        self.sent.append(("raw", bus, tuple(int(value) for value in data)))


class _FakeBenchTransport:
    def __init__(
        self,
        *,
        config: BenchV0TransportConfig,
        on_evt_packet=None,
        on_stat_packet=None,
        on_ping_packet=None,
        on_pong_packet=None,
        on_event=None,
        start_result: bool = True,
    ) -> None:
        self._config = config
        self._on_evt_packet = on_evt_packet
        self._on_stat_packet = on_stat_packet
        self._on_ping_packet = on_ping_packet
        self._on_pong_packet = on_pong_packet
        self._on_event = on_event
        self._running = False
        self._start_result = start_result
        self._evt_count = 0
        self._stat_count = 0
        self._ping_count = 0
        self._pong_count = 0
        self._pong_sent = 0
        self._bytes = 0
        self._parse_errors = 0
        self._socket_errors = 0
        self._last_summary: str | None = None
        self._last_error: str | None = None

    def start(self) -> bool:
        self._running = self._start_result
        return self._start_result

    def stop(self) -> None:
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def snapshot(self) -> BenchV0TransportSnapshot:
        return BenchV0TransportSnapshot(
            bind_ip=self._config.bind_ip,
            bench_port=self._config.bench_port,
            evt_port=self._config.bench_port,
            stat_port=self._config.bench_port,
            is_running=self._running,
            socket_open=self._running,
            total_evt_packets=self._evt_count,
            total_stat_packets=self._stat_count,
            total_ping_packets=self._ping_count,
            total_pong_packets=self._pong_count,
            total_pong_sent=self._pong_sent,
            total_bytes_received=self._bytes,
            parse_errors=self._parse_errors,
            socket_errors=self._socket_errors,
            last_activity_ts=10.0 if self._running else None,
            last_packet_summary=self._last_summary,
            last_error=self._last_error,
        )

    def emit_evt(self, *, seq: int, note: int = 60, vel: int = 100) -> None:
        packet = BenchV0EvtPacket(
            header=BenchV0Header(
                magic=BENCH_V0_MAGIC,
                version=BENCH_V0_VERSION,
                msg_type=BenchV0MsgType.EVT,
                node_id=7,
                seq=seq,
            ),
            midi_bus=1,
            midi_ch=0,
            note=note,
            vel=vel,
            ts_ms=1234,
            rssi_dbm=-55,
            flags=0,
            aux16=0,
            rtt_ms=0,
            aux32=0,
            aux_u8_a=0,
            aux_u8_b=0,
            crc16=0,
        )
        self._evt_count += 1
        self._bytes += 32
        self._last_summary = f"EVT node=7 seq={seq}"
        if self._on_evt_packet is not None:
            self._on_evt_packet(
                BenchV0ReceivedEvtPacket(
                    packet=packet,
                    source_ip="127.0.0.1",
                    source_port=5005,
                    received_ts=100.0 + float(seq),
                )
            )

    def emit_stat(self, *, seq: int) -> None:
        packet = BenchV0StatPacket(
            header=BenchV0Header(
                magic=BENCH_V0_MAGIC,
                version=BENCH_V0_VERSION,
                msg_type=BenchV0MsgType.STAT,
                node_id=7,
                seq=seq,
            ),
            state_flags=1,
            reset_reason=0,
            uptime_s=500,
            rssi_dbm=-54,
            stat_flags=0,
            pps_x10=20,
            vbat_mv=3700,
            free_heap=220000,
            fw_major=1,
            fw_minor=2,
            aux16=0,
            crc16=0,
        )
        self._stat_count += 1
        self._bytes += 32
        self._last_summary = f"STAT node=7 seq={seq}"
        if self._on_stat_packet is not None:
            self._on_stat_packet(
                BenchV0ReceivedStatPacket(
                    packet=packet,
                    source_ip="127.0.0.1",
                    source_port=5005,
                    received_ts=200.0 + float(seq),
                )
            )

    def emit_ping(self, *, seq: int) -> None:
        packet = BenchV0PingPacket(
            header=BenchV0Header(
                magic=BENCH_V0_MAGIC,
                version=BENCH_V0_VERSION,
                msg_type=BenchV0MsgType.PING,
                node_id=7,
                seq=seq,
            ),
            ts_ms=3000,
            rssi_dbm=-50,
            flags=1,
            aux16=5,
            rtt_ms=7,
            aux32=0,
            aux_u8_a=0,
            aux_u8_b=0,
            crc16=0,
        )
        self._ping_count += 1
        self._bytes += 32
        self._last_summary = f"PING node=7 seq={seq}"
        if self._on_ping_packet is not None:
            self._on_ping_packet(
                BenchV0ReceivedPingPacket(
                    packet=packet,
                    source_ip="127.0.0.1",
                    source_port=5005,
                    received_ts=300.0 + float(seq),
                )
            )

    def emit_pong(self, *, seq: int) -> None:
        packet = BenchV0PongPacket(
            header=BenchV0Header(
                magic=BENCH_V0_MAGIC,
                version=BENCH_V0_VERSION,
                msg_type=BenchV0MsgType.PONG,
                node_id=7,
                seq=seq,
            ),
            ts_ms=3001,
            rssi_dbm=-49,
            flags=1,
            aux16=6,
            rtt_ms=8,
            aux32=0,
            aux_u8_a=0,
            aux_u8_b=0,
            crc16=0,
        )
        self._pong_count += 1
        self._bytes += 32
        self._last_summary = f"PONG node=7 seq={seq}"
        if self._on_pong_packet is not None:
            self._on_pong_packet(
                BenchV0ReceivedPongPacket(
                    packet=packet,
                    source_ip="127.0.0.1",
                    source_port=5005,
                    received_ts=400.0 + float(seq),
                )
            )

    def emit_parse_warning(self, message: str) -> None:
        self._parse_errors += 1
        self._last_error = message
        if self._on_event is not None:
            self._on_event(BenchV0RuntimeEvent(level="warning", message=message))


def test_bench_backend_routes_evt_stat_and_avoids_false_loss_from_global_seq() -> None:
    holder: dict[str, _FakeBenchTransport] = {}
    router = _FakeMidiRouter()

    def _transport_builder(**kwargs):
        transport = _FakeBenchTransport(**kwargs)
        holder["transport"] = transport
        return transport

    backend = UdpBenchCompatSessionBackend(
        _bench_cfg(),
        router_builder=lambda _cfg: router,
        transport_builder=_transport_builder,
    )
    backend.start(_bench_spec())
    transport = holder["transport"]

    # Secuencia global bench intercalada: EVT/STAT/PING/PONG comparten g_seq.
    transport.emit_evt(seq=10, note=64, vel=120)
    transport.emit_ping(seq=11)
    transport.emit_stat(seq=12)
    transport.emit_pong(seq=13)
    transport.emit_evt(seq=14, note=65, vel=0)
    transport.emit_stat(seq=15)

    runtime = backend.runtime_snapshot()
    node = backend.get_node_snapshot(7, now=1000.0)
    summary = backend.get_node_registry_summary(now=1000.0)

    assert runtime.is_running is True
    assert runtime.total_evt_packets >= 2
    assert runtime.total_stat_packets >= 2
    assert runtime.total_ping_packets >= 1
    assert runtime.total_pong_packets >= 1
    assert runtime.messages_routed >= 2
    assert runtime.last_evt is not None
    assert runtime.last_stat is not None
    assert runtime.last_ping is not None
    assert runtime.last_pong is not None
    assert node is not None
    assert node.loss_evt_pct == 0.0
    assert node.loss_stat_pct == 0.0
    assert summary is not None
    assert summary.total_nodes == 1
    assert ("note_off", 1, 0, 65, 0) in router.sent

    backend.stop()
    assert backend.get_node_snapshots() == []


def test_bench_backend_rejects_non_bench_spec() -> None:
    backend = UdpBenchCompatSessionBackend(
        _bench_cfg(),
        router_builder=lambda _cfg: _FakeMidiRouter(),
        transport_builder=lambda **kwargs: _FakeBenchTransport(**kwargs),
    )
    invalid_spec = SessionSpec(
        profile_id="lab_sim",
        mode="udp",
        backend=BackendKind.LAB,
        is_valid=True,
        reason="ok",
    )
    try:
        backend.start(invalid_spec)
        assert False, "start() debia fallar para perfil no bench"
    except Exception as exc:
        assert "udp_bench_lab" in str(exc).lower()


def test_bench_backend_runtime_tracks_transport_warnings() -> None:
    holder: dict[str, _FakeBenchTransport] = {}

    def _transport_builder(**kwargs):
        transport = _FakeBenchTransport(**kwargs)
        holder["transport"] = transport
        return transport

    backend = UdpBenchCompatSessionBackend(
        _bench_cfg(),
        router_builder=lambda _cfg: _FakeMidiRouter(),
        transport_builder=_transport_builder,
    )
    backend.start(_bench_spec())
    holder["transport"].emit_parse_warning("Bench parse warning")
    runtime = backend.runtime_snapshot()
    backend.stop()

    assert runtime.parse_errors >= 1
    assert runtime.last_event is not None
