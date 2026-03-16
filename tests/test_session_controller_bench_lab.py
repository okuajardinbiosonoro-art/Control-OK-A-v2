from __future__ import annotations

from dataclasses import dataclass
import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.session import BackendKind, SessionSpec, SessionState  # noqa: E402
from control_okua.core.udp import (  # noqa: E402
    BENCH_V0_MAGIC,
    BENCH_V0_VERSION,
    BenchV0EvtPacket,
    BenchV0Header,
    BenchV0MsgType,
    BenchV0StatPacket,
)
from control_okua.services.backends import UdpBenchCompatSessionBackend  # noqa: E402
from control_okua.services.session_controller import SessionController  # noqa: E402
from control_okua.transports.udp import (  # noqa: E402
    BenchV0ReceivedEvtPacket,
    BenchV0ReceivedStatPacket,
    BenchV0TransportConfig,
    BenchV0TransportSnapshot,
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
    ) -> None:
        self._config = config
        self._on_evt_packet = on_evt_packet
        self._on_stat_packet = on_stat_packet
        self._running = False
        self._evt_count = 0
        self._stat_count = 0
        self._bytes = 0
        self._parse_errors = 0
        self._socket_errors = 0

    def start(self) -> bool:
        self._running = True
        return True

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
            total_ping_packets=0,
            total_pong_packets=0,
            total_pong_sent=0,
            total_bytes_received=self._bytes,
            parse_errors=self._parse_errors,
            socket_errors=self._socket_errors,
            last_activity_ts=100.0 if self._running else None,
            last_packet_summary="bench",
            last_error=None,
        )

    def emit_evt(self, *, seq: int) -> None:
        packet = BenchV0EvtPacket(
            header=BenchV0Header(
                magic=BENCH_V0_MAGIC,
                version=BENCH_V0_VERSION,
                msg_type=BenchV0MsgType.EVT,
                node_id=50,
                seq=seq,
            ),
            midi_bus=0,
            midi_ch=0,
            note=66,
            vel=90,
            ts_ms=1000,
            rssi_dbm=-48,
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
        if self._on_evt_packet is not None:
            self._on_evt_packet(
                BenchV0ReceivedEvtPacket(
                    packet=packet,
                    source_ip="127.0.0.1",
                    source_port=5005,
                    received_ts=101.0,
                )
            )

    def emit_stat(self, *, seq: int) -> None:
        packet = BenchV0StatPacket(
            header=BenchV0Header(
                magic=BENCH_V0_MAGIC,
                version=BENCH_V0_VERSION,
                msg_type=BenchV0MsgType.STAT,
                node_id=50,
                seq=seq,
            ),
            state_flags=1,
            reset_reason=0,
            uptime_s=777,
            rssi_dbm=-47,
            stat_flags=0,
            pps_x10=33,
            vbat_mv=3690,
            free_heap=180000,
            fw_major=1,
            fw_minor=3,
            aux16=0,
            crc16=0,
        )
        self._stat_count += 1
        self._bytes += 32
        if self._on_stat_packet is not None:
            self._on_stat_packet(
                BenchV0ReceivedStatPacket(
                    packet=packet,
                    source_ip="127.0.0.1",
                    source_port=5005,
                    received_ts=102.0,
                )
            )


@dataclass
class _RecordingFactory:
    backend: Any

    def build_backend_for_spec(self, _spec: SessionSpec) -> Any:
        return self.backend


def test_controller_bench_profile_exposes_runtime_and_nodes() -> None:
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
    controller = SessionController(
        _bench_cfg(),
        backend_factory=_RecordingFactory(backend=backend),
    )

    assert controller.start_session() is True
    assert controller.get_state() is SessionState.RUNNING
    holder["transport"].emit_evt(seq=10)
    holder["transport"].emit_stat(seq=12)

    runtime = controller.get_backend_runtime_snapshot()
    node_summary = controller.get_node_registry_summary(now=200.0)
    node = controller.get_node_snapshot(50, now=200.0)

    assert runtime is not None
    assert runtime.total_evt_packets >= 1
    assert runtime.total_stat_packets >= 1
    assert node_summary is not None
    assert node_summary.total_nodes == 1
    assert node is not None
    assert node.loss_evt_pct == 0.0
    assert node.loss_stat_pct == 0.0

    assert controller.stop_session() is True
    assert controller.get_state() is SessionState.IDLE
    assert controller.get_node_snapshots() == []


def test_controller_bench_restart_has_no_ghost_nodes() -> None:
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
    controller = SessionController(
        _bench_cfg(),
        backend_factory=_RecordingFactory(backend=backend),
    )

    assert controller.start_session() is True
    holder["transport"].emit_evt(seq=100)
    assert controller.get_node_snapshot(50, now=201.0) is not None
    assert controller.stop_session() is True

    assert controller.start_session() is True
    summary = controller.get_node_registry_summary(now=201.0)
    assert summary is not None
    assert summary.total_nodes == 0
    assert controller.stop_session() is True
