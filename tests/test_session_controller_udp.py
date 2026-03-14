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
    OKUA_MAGIC,
    OKUA_VERSION,
    OkuaEvtPacket,
    OkuaHeader,
    OkuaPacketType,
    OkuaStatPacket,
)
from control_okua.services.backends import UdpSessionBackend  # noqa: E402
from control_okua.services.session_controller import SessionController  # noqa: E402
from control_okua.transports.udp import (  # noqa: E402
    UdpReceivedEvtPacket,
    UdpReceivedStatPacket,
    UdpRuntimeEvent,
    UdpTransportConfig,
    UdpTransportSnapshot,
)


def _build_udp_cfg() -> dict[str, Any]:
    return {
        "profile": {"active": "udp_jardin"},
        "mode": "udp",
        "udp": {
            "bind_ip": "127.0.0.1",
            "evt_port": 5005,
            "stat_port": 5006,
            "cmd_port": 5007,
            "rcvbuf_bytes": 262144,
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


class _FakeUdpTransport:
    def __init__(
        self,
        *,
        config: UdpTransportConfig,
        on_evt_packet=None,
        on_stat_packet=None,
        on_event=None,
        start_result: bool = True,
        start_error: Exception | None = None,
    ) -> None:
        self._config = config
        self._on_evt_packet = on_evt_packet
        self._on_stat_packet = on_stat_packet
        self._on_event = on_event
        self._start_result = start_result
        self._start_error = start_error
        self._running = False
        self._evt_count = 0
        self._stat_count = 0
        self._bytes = 0
        self._parse_errors = 0
        self._socket_errors = 0
        self._last_summary: str | None = None
        self._last_error: str | None = None

    def start(self) -> bool:
        if self._start_error is not None:
            raise self._start_error
        self._running = self._start_result
        return self._start_result

    def stop(self) -> None:
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def snapshot(self) -> UdpTransportSnapshot:
        return UdpTransportSnapshot(
            bind_ip=self._config.bind_ip,
            evt_port=self._config.evt_port,
            stat_port=self._config.stat_port,
            is_running=self._running,
            evt_socket_open=self._running,
            stat_socket_open=self._running,
            total_evt_packets=self._evt_count,
            total_stat_packets=self._stat_count,
            total_bytes_received=self._bytes,
            parse_errors=self._parse_errors,
            socket_errors=self._socket_errors,
            last_activity_ts=10.0 if self._running else None,
            last_packet_summary=self._last_summary,
            last_error=self._last_error,
        )

    def emit_evt(self, *, vel: int = 100) -> None:
        packet = OkuaEvtPacket(
            header=OkuaHeader(
                magic=OKUA_MAGIC,
                version=OKUA_VERSION,
                packet_type=OkuaPacketType.EVT,
                node_id=70,
                seq=80,
            ),
            midi_bus=1,
            midi_ch=0,
            note=65,
            vel=vel,
            ts_ms=5000,
            rssi_dbm=-61,
            flags=0,
            rsv=(0, 0),
        )
        self._evt_count += 1
        self._bytes += 20
        self._last_summary = "EVT node=70 seq=80"
        if self._on_evt_packet is not None:
            self._on_evt_packet(
                UdpReceivedEvtPacket(
                    packet=packet,
                    source_ip="127.0.0.1",
                    source_port=5005,
                    received_ts=100.0,
                )
            )

    def emit_stat(self) -> None:
        packet = OkuaStatPacket(
            header=OkuaHeader(
                magic=OKUA_MAGIC,
                version=OKUA_VERSION,
                packet_type=OkuaPacketType.STAT,
                node_id=90,
                seq=91,
            ),
            uptime_s=777,
            rssi_dbm=-51,
            state_flags=1,
            pps_x10=120,
            vbat_mv=3710,
            free_heap=200000,
            fw_major=1,
            fw_minor=1,
            reset_reason=0,
            rsv=(0, 0, 0),
        )
        self._stat_count += 1
        self._bytes += 28
        self._last_summary = "STAT node=90 seq=91"
        if self._on_stat_packet is not None:
            self._on_stat_packet(
                UdpReceivedStatPacket(
                    packet=packet,
                    source_ip="127.0.0.1",
                    source_port=5006,
                    received_ts=101.0,
                )
            )

    def emit_parse_error(self, message: str) -> None:
        self._parse_errors += 1
        self._last_error = message
        if self._on_event is not None:
            self._on_event(UdpRuntimeEvent(level="warning", message=message))


@dataclass
class _RecordingBackendFactory:
    backend: Any
    build_calls: int = 0

    def build_backend_for_spec(self, _spec: SessionSpec) -> Any:
        self.build_calls += 1
        return self.backend


def test_controller_udp_backend_reaches_running_routes_evt_and_updates_stat_runtime() -> None:
    holder: dict[str, _FakeUdpTransport] = {}
    router = _FakeMidiRouter()

    def _transport_builder(**kwargs):
        transport = _FakeUdpTransport(**kwargs)
        holder["transport"] = transport
        return transport

    backend = UdpSessionBackend(
        _build_udp_cfg(),
        router_builder=lambda _cfg: router,
        transport_builder=_transport_builder,
    )
    backend_factory = _RecordingBackendFactory(backend=backend)
    controller = SessionController(_build_udp_cfg(), backend_factory=backend_factory)

    assert controller.start_session() is True
    assert controller.get_state() is SessionState.RUNNING

    holder["transport"].emit_evt(vel=0)
    holder["transport"].emit_stat()

    runtime_snapshot = controller.get_backend_runtime_snapshot()
    node_summary = controller.get_node_registry_summary(now=102.0)
    node_snapshots = controller.get_node_snapshots(now=102.0)
    node_70 = controller.get_node_snapshot(70, now=102.0)
    node_90 = controller.get_node_snapshot(90, now=102.0)
    assert runtime_snapshot is not None
    assert runtime_snapshot.messages_routed >= 1
    assert runtime_snapshot.last_stat is not None
    assert runtime_snapshot.total_evt_packets >= 1
    assert runtime_snapshot.total_stat_packets >= 1
    assert node_summary is not None
    assert node_summary.total_nodes >= 2
    assert len(node_snapshots) >= 2
    assert node_70 is not None
    assert node_90 is not None
    assert ("note_off", 1, 0, 65, 0) in router.sent

    assert controller.stop_session() is True
    assert controller.get_state() is SessionState.IDLE
    assert controller.get_node_snapshots() == []
    assert controller.get_node_registry_summary() is None
    assert backend_factory.build_calls == 1


def test_controller_udp_backend_start_failure_never_reports_running() -> None:
    backend = UdpSessionBackend(
        _build_udp_cfg(),
        router_builder=lambda _cfg: _FakeMidiRouter(),
        transport_builder=lambda **kwargs: _FakeUdpTransport(
            **kwargs,
            start_error=RuntimeError("No se pudo abrir sockets UDP: Address already in use"),
        ),
    )
    backend_factory = _RecordingBackendFactory(backend=backend)
    controller = SessionController(_build_udp_cfg(), backend_factory=backend_factory)
    states: list[str] = []
    controller.session_state_changed.connect(states.append)

    result = controller.start_session()

    assert result is False
    assert controller.get_state() is SessionState.ERROR
    assert "running" not in states


def test_controller_udp_restart_has_no_ghost_nodes() -> None:
    holder: dict[str, _FakeUdpTransport] = {}

    def _transport_builder(**kwargs):
        transport = _FakeUdpTransport(**kwargs)
        holder["transport"] = transport
        return transport

    backend = UdpSessionBackend(
        _build_udp_cfg(),
        router_builder=lambda _cfg: _FakeMidiRouter(),
        transport_builder=_transport_builder,
    )
    backend_factory = _RecordingBackendFactory(backend=backend)
    controller = SessionController(_build_udp_cfg(), backend_factory=backend_factory)

    assert controller.start_session() is True
    holder["transport"].emit_evt()
    assert controller.get_node_snapshot(70, now=101.0) is not None
    assert controller.stop_session() is True

    assert controller.start_session() is True
    restarted_summary = controller.get_node_registry_summary(now=101.0)
    assert restarted_summary is not None
    assert restarted_summary.total_nodes == 0
    assert controller.get_node_snapshot(70, now=101.0) is None
    assert controller.stop_session() is True
