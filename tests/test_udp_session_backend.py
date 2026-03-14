from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.session import BackendKind, SessionSpec  # noqa: E402
from control_okua.core.udp import (  # noqa: E402
    OKUA_MAGIC,
    OKUA_VERSION,
    OkuaEvtPacket,
    OkuaHeader,
    OkuaPacketType,
    OkuaStatPacket,
)
from control_okua.services.backends import (  # noqa: E402
    UdpSessionBackend,
    route_udp_evt_to_midi_router,
)
from control_okua.services.backends.udp_session_backend import (  # noqa: E402
    UdpBackendStartError,
)
from control_okua.transports.udp import (  # noqa: E402
    UdpReceivedEvtPacket,
    UdpReceivedStatPacket,
    UdpRuntimeEvent,
    UdpTransportConfig,
    UdpTransportSnapshot,
)


def _udp_spec() -> SessionSpec:
    return SessionSpec(
        profile_id="udp_jardin",
        mode="udp",
        backend=BackendKind.UDP,
        is_valid=True,
        reason="ok",
    )


def _lab_udp_spec() -> SessionSpec:
    return SessionSpec(
        profile_id="lab_sim",
        mode="udp",
        backend=BackendKind.LAB,
        is_valid=True,
        reason="ok",
    )


def _cfg() -> dict[str, Any]:
    return {
        "profile": {"active": "udp_jardin"},
        "udp": {
            "bind_ip": "127.0.0.1",
            "evt_port": 5005,
            "stat_port": 5006,
            "rcvbuf_bytes": 262144,
        },
        "midi": {
            "backend": "rtmidi",
            "outputs": {"0": "loopMIDI Port 1", "1": "loopMIDI Port 2"},
            "send_noteoff_on_vel0": True,
        },
    }


class _FakeMidiRouter:
    def __init__(self, buses: list[int] | None = None) -> None:
        self._buses = buses or [0, 1]
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
    ) -> None:
        self._config = config
        self._on_evt_packet = on_evt_packet
        self._on_stat_packet = on_stat_packet
        self._on_event = on_event
        self._start_result = start_result
        self._running = False
        self._total_evt_packets = 0
        self._total_stat_packets = 0
        self._total_bytes_received = 0
        self._parse_errors = 0
        self._socket_errors = 0
        self._last_packet_summary: str | None = None
        self._last_error: str | None = None

    def start(self) -> bool:
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
            total_evt_packets=self._total_evt_packets,
            total_stat_packets=self._total_stat_packets,
            total_bytes_received=self._total_bytes_received,
            parse_errors=self._parse_errors,
            socket_errors=self._socket_errors,
            last_activity_ts=1.0 if self._running else None,
            last_packet_summary=self._last_packet_summary,
            last_error=self._last_error,
        )

    def emit_evt(self, packet: OkuaEvtPacket, *, source_ip: str = "127.0.0.1", source_port: int = 5005) -> None:
        self._total_evt_packets += 1
        self._total_bytes_received += 20
        self._last_packet_summary = f"EVT node={packet.header.node_id} seq={packet.header.seq}"
        if self._on_evt_packet is not None:
            self._on_evt_packet(
                UdpReceivedEvtPacket(
                    packet=packet,
                    source_ip=source_ip,
                    source_port=source_port,
                    received_ts=10.5,
                )
            )

    def emit_stat(self, packet: OkuaStatPacket, *, source_ip: str = "127.0.0.1", source_port: int = 5006) -> None:
        self._total_stat_packets += 1
        self._total_bytes_received += 28
        self._last_packet_summary = f"STAT node={packet.header.node_id} seq={packet.header.seq}"
        if self._on_stat_packet is not None:
            self._on_stat_packet(
                UdpReceivedStatPacket(
                    packet=packet,
                    source_ip=source_ip,
                    source_port=source_port,
                    received_ts=11.5,
                )
            )

    def emit_event(self, level: str, message: str) -> None:
        if level.lower() == "error":
            self._socket_errors += 1
            self._last_error = message
        if self._on_event is not None:
            self._on_event(UdpRuntimeEvent(level=level, message=message))


def _evt_packet(
    *,
    node_id: int = 33,
    seq: int = 88,
    bus: int = 1,
    ch: int = 2,
    note: int = 64,
    vel: int = 100,
) -> OkuaEvtPacket:
    return OkuaEvtPacket(
        header=OkuaHeader(
            magic=OKUA_MAGIC,
            version=OKUA_VERSION,
            packet_type=OkuaPacketType.EVT,
            node_id=node_id,
            seq=seq,
        ),
        midi_bus=bus,
        midi_ch=ch,
        note=note,
        vel=vel,
        ts_ms=12345,
        rssi_dbm=-60,
        flags=1,
        rsv=(0, 0),
    )


def _stat_packet(*, node_id: int = 44, seq: int = 99) -> OkuaStatPacket:
    return OkuaStatPacket(
        header=OkuaHeader(
            magic=OKUA_MAGIC,
            version=OKUA_VERSION,
            packet_type=OkuaPacketType.STAT,
            node_id=node_id,
            seq=seq,
        ),
        uptime_s=777,
        rssi_dbm=-50,
        state_flags=0x03,
        pps_x10=120,
        vbat_mv=3690,
        free_heap=123456,
        fw_major=1,
        fw_minor=2,
        reset_reason=0,
        rsv=(0, 0, 0),
    )


def test_udp_backend_start_stop_and_runtime_snapshot() -> None:
    holder: dict[str, _FakeUdpTransport] = {}
    router = _FakeMidiRouter()

    def _build_transport(**kwargs):
        transport = _FakeUdpTransport(**kwargs)
        holder["transport"] = transport
        return transport

    backend = UdpSessionBackend(
        _cfg(),
        router_builder=lambda _cfg_value: router,
        transport_builder=_build_transport,
    )

    backend.start(_udp_spec())
    holder["transport"].emit_evt(_evt_packet())
    holder["transport"].emit_stat(_stat_packet())

    snapshot = backend.runtime_snapshot()
    assert backend.is_running() is True
    assert snapshot.is_running is True
    assert snapshot.messages_routed >= 1
    assert snapshot.last_evt is not None
    assert snapshot.last_stat is not None
    assert snapshot.total_evt_packets >= 1
    assert snapshot.total_stat_packets >= 1
    assert ("note_on", 1, 2, 64, 100) in router.sent
    node_summary = backend.get_node_registry_summary(now=12.0)
    node_snapshots = backend.get_node_snapshots(now=12.0)
    assert node_summary is not None
    assert node_summary.total_nodes >= 2
    assert len(node_snapshots) >= 2

    backend.stop()
    stopped_snapshot = backend.runtime_snapshot()
    assert stopped_snapshot.is_running is False
    assert router.close_called == 1


def test_udp_backend_node_registry_starts_clean_and_updates_with_evt_stat() -> None:
    holder: dict[str, _FakeUdpTransport] = {}
    backend = UdpSessionBackend(
        _cfg(),
        router_builder=lambda _cfg_value: _FakeMidiRouter(),
        transport_builder=lambda **kwargs: holder.setdefault("transport", _FakeUdpTransport(**kwargs)),
    )
    backend.start(_udp_spec())

    empty_summary = backend.get_node_registry_summary(now=1.0)
    assert empty_summary is not None
    assert empty_summary.total_nodes == 0
    assert backend.get_node_snapshots(now=1.0) == []

    holder["transport"].emit_evt(_evt_packet(node_id=200, seq=10, note=70, vel=101))
    holder["transport"].emit_stat(_stat_packet(node_id=200, seq=20))
    snapshot = backend.get_node_snapshot(200, now=12.0)

    assert snapshot is not None
    assert snapshot.last_seq_evt == 10
    assert snapshot.last_seq_stat == 20
    assert snapshot.last_note == 70
    assert snapshot.reported_pps_x10 == 120
    backend.stop()


def test_udp_backend_tracks_multiple_nodes_in_registry() -> None:
    holder: dict[str, _FakeUdpTransport] = {}
    backend = UdpSessionBackend(
        _cfg(),
        router_builder=lambda _cfg_value: _FakeMidiRouter(),
        transport_builder=lambda **kwargs: holder.setdefault("transport", _FakeUdpTransport(**kwargs)),
    )
    backend.start(_udp_spec())

    holder["transport"].emit_evt(_evt_packet(node_id=301, seq=1))
    holder["transport"].emit_evt(_evt_packet(node_id=302, seq=1))
    holder["transport"].emit_stat(_stat_packet(node_id=303, seq=1))

    snapshots = backend.get_node_snapshots(now=15.0)
    ids = {item.node_id for item in snapshots}
    assert ids == {301, 302, 303}
    backend.stop()


def test_udp_backend_registry_is_not_exposed_after_stop_and_no_ghosts_on_restart() -> None:
    holder: dict[str, _FakeUdpTransport] = {}

    def _build_transport(**kwargs):
        transport = _FakeUdpTransport(**kwargs)
        holder["transport"] = transport
        return transport

    backend = UdpSessionBackend(
        _cfg(),
        router_builder=lambda _cfg_value: _FakeMidiRouter(),
        transport_builder=_build_transport,
    )
    backend.start(_udp_spec())
    holder["transport"].emit_evt(_evt_packet(node_id=401, seq=1))
    assert backend.get_node_snapshot(401, now=20.0) is not None
    backend.stop()

    assert backend.get_node_snapshots(now=20.0) == []
    assert backend.get_node_registry_summary(now=20.0) is None

    backend.start(_udp_spec())
    restarted_summary = backend.get_node_registry_summary(now=21.0)
    assert restarted_summary is not None
    assert restarted_summary.total_nodes == 0
    assert backend.get_node_snapshot(401, now=21.0) is None
    backend.stop()


def test_udp_backend_start_failure_does_not_leave_running_state() -> None:
    router = _FakeMidiRouter()
    backend = UdpSessionBackend(
        _cfg(),
        router_builder=lambda _cfg_value: router,
        transport_builder=lambda **kwargs: _FakeUdpTransport(**kwargs, start_result=False),
    )

    try:
        backend.start(_udp_spec())
        assert False, "start() debia fallar cuando el transporte no inicia"
    except UdpBackendStartError as exc:
        assert "no se pudo iniciar backend udp" in str(exc).lower()

    assert backend.is_running() is False
    assert router.close_called == 1


def test_route_helper_keeps_note_on_vel_zero_semantics() -> None:
    router = _FakeMidiRouter()
    route_udp_evt_to_midi_router(router, _evt_packet(vel=0))
    assert router.sent == [("note_off", 1, 2, 64, 0)]


def test_udp_backend_runtime_tracks_transport_errors() -> None:
    holder: dict[str, _FakeUdpTransport] = {}
    backend = UdpSessionBackend(
        _cfg(),
        router_builder=lambda _cfg_value: _FakeMidiRouter(),
        transport_builder=lambda **kwargs: holder.setdefault("transport", _FakeUdpTransport(**kwargs)),
    )
    backend.start(_udp_spec())
    holder["transport"].emit_event("error", "Error de recepcion UDP en EVT: socket closed")

    snapshot = backend.runtime_snapshot()
    backend.stop()

    assert snapshot.last_error is not None
    assert "recepcion udp" in snapshot.last_error.lower()
    assert snapshot.socket_errors >= 1


def test_udp_backend_accepts_lab_spec_when_mode_is_udp() -> None:
    backend = UdpSessionBackend(
        _cfg(),
        router_builder=lambda _cfg_value: _FakeMidiRouter(),
        transport_builder=lambda **kwargs: _FakeUdpTransport(**kwargs),
    )
    backend.start(_lab_udp_spec())
    assert backend.is_running() is True
    backend.stop()


def test_udp_backend_rejects_non_udp_spec() -> None:
    backend = UdpSessionBackend(
        _cfg(),
        router_builder=lambda _cfg_value: _FakeMidiRouter(),
        transport_builder=lambda **kwargs: _FakeUdpTransport(**kwargs),
    )
    invalid_spec = SessionSpec(
        profile_id="serial_local",
        mode="serial",
        backend=BackendKind.SERIAL,
        is_valid=True,
        reason="ok",
    )
    try:
        backend.start(invalid_spec)
        assert False, "start() debia fallar para spec no UDP"
    except UdpBackendStartError as exc:
        assert "no corresponde a una operacion udp" in str(exc).lower()
