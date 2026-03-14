from __future__ import annotations

from dataclasses import dataclass
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Callable


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.midi import ParsedMidiMessage  # noqa: E402
from control_okua.core.recording import JsonlSessionRecorder  # noqa: E402
from control_okua.core.session import (  # noqa: E402
    BackendAvailability,
    BackendKind,
    SessionSpec,
    SessionState,
)
from control_okua.core.udp import (  # noqa: E402
    OKUA_MAGIC,
    OKUA_VERSION,
    OkuaEvtPacket,
    OkuaHeader,
    OkuaPacketType,
    OkuaStatPacket,
)
from control_okua.services.backends import SerialSessionBackend, UdpSessionBackend  # noqa: E402
from control_okua.services.session_controller import SessionController  # noqa: E402
from control_okua.transports.serial import (  # noqa: E402
    SerialTransportConfig,
    SerialTransportSnapshot,
)
from control_okua.transports.udp import (  # noqa: E402
    UdpReceivedEvtPacket,
    UdpReceivedStatPacket,
    UdpTransportConfig,
    UdpTransportSnapshot,
)


def _build_serial_cfg(*, logging_enabled: bool) -> dict[str, Any]:
    return {
        "profile": {"active": "serial_local"},
        "mode": "serial",
        "serial": {
            "port": "COM_TEST",
            "baudrate": 115200,
            "flush_ms": 5,
            "running_status": True,
            "max_silence_s": 3.0,
        },
        "midi": {
            "backend": "rtmidi",
            "outputs": {"0": "loopMIDI Port 1"},
            "send_noteoff_on_vel0": True,
        },
        "logging": {"enabled": logging_enabled, "folder": "logs", "format": "csv"},
    }


def _build_udp_cfg(*, logging_enabled: bool) -> dict[str, Any]:
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
        "logging": {"enabled": logging_enabled, "folder": "logs", "format": "jsonl"},
    }


class _FakeMidiRouter:
    def __init__(self, buses: list[int] | None = None) -> None:
        self._buses = buses or [0, 1]
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


class _FakeSerialTransport:
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
        self.messages_parsed = 0
        self.bytes_received = 0

    def start(self) -> bool:
        self._running = self._start_result
        return self._start_result

    def stop(self) -> None:
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def snapshot(self) -> SerialTransportSnapshot:
        return SerialTransportSnapshot(
            port=self._config.port,
            baudrate=self._config.baudrate,
            is_running=self._running,
            is_open=self._running,
            bytes_received=self.bytes_received,
            messages_parsed=self.messages_parsed,
            parse_errors=0,
            read_errors=0,
            last_activity_ts=None,
            last_error=None,
        )

    def emit_message(self, status: int, data: tuple[int, ...], message_type: str, channel: int | None) -> None:
        self.messages_parsed += 1
        self.bytes_received += 1 + len(data)
        if self._on_message is not None:
            self._on_message(
                ParsedMidiMessage(
                    status=status,
                    data=data,
                    message_type=message_type,
                    channel=channel,
                )
            )


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
        self._evt_count = 0
        self._stat_count = 0
        self._bytes = 0
        self._last_summary: str | None = None

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
            total_evt_packets=self._evt_count,
            total_stat_packets=self._stat_count,
            total_bytes_received=self._bytes,
            parse_errors=0,
            socket_errors=0,
            last_activity_ts=10.0 if self._running else None,
            last_packet_summary=self._last_summary,
            last_error=None,
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


@dataclass
class _FakeUnavailableBackend:
    kind: BackendKind = BackendKind.SERIAL
    reason: str = "Backend no implementado."

    def start(self, spec: SessionSpec) -> None:
        return None

    def stop(self) -> None:
        return None

    def describe(self) -> str:
        return "Fake unavailable backend"

    def availability(self) -> BackendAvailability:
        return BackendAvailability(
            is_implemented=False,
            is_available=False,
            reason=self.reason,
        )


@dataclass
class _BackendFactory:
    backend: Any
    build_calls: int = 0

    def build_backend_for_spec(self, _spec: SessionSpec) -> Any:
        self.build_calls += 1
        return self.backend


@dataclass
class _RecorderBuilder:
    base_dir: Path
    calls: int = 0

    def __call__(self, _cfg: dict[str, Any]) -> JsonlSessionRecorder:
        self.calls += 1
        return JsonlSessionRecorder(base_sessions_dir=self.base_dir)


def _read_jsonl_events(path: Path) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _load_artifacts(controller: SessionController) -> tuple[Path, Path]:
    paths = controller.get_last_recording_artifacts()
    assert paths is not None
    jsonl_path = getattr(paths, "session_jsonl_path", None)
    report_path = getattr(paths, "report_json_path", None)
    assert isinstance(jsonl_path, Path)
    assert isinstance(report_path, Path)
    assert jsonl_path.exists()
    assert report_path.exists()
    return jsonl_path, report_path


def test_logging_enabled_preflight_blocked_still_writes_evidence(tmp_path: Path) -> None:
    cfg = {
        "profile": {"active": None},
        "mode": "invalid_mode",
        "logging": {"enabled": True, "folder": "logs"},
    }
    recorder_builder = _RecorderBuilder(tmp_path / "sessions")
    controller = SessionController(
        cfg,
        backend_factory=_BackendFactory(_FakeUnavailableBackend()),
        recorder_builder=recorder_builder,
    )

    assert controller.start_session() is False
    jsonl_path, report_path = _load_artifacts(controller)
    events = _read_jsonl_events(jsonl_path)
    event_types = [row["event_type"] for row in events]
    assert "session_started" in event_types
    assert "preflight_report" in event_types
    assert "session_error" in event_types
    assert "report_generated" in event_types

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["final_state"] == "error"
    assert report["session_id"] == events[0]["session_id"]
    assert controller.get_active_recording_session_id() is None
    assert recorder_builder.calls == 1


def test_logging_enabled_backend_start_failure_still_writes_evidence(tmp_path: Path) -> None:
    cfg = _build_serial_cfg(logging_enabled=True)
    recorder_builder = _RecorderBuilder(tmp_path / "sessions")
    controller = SessionController(
        cfg,
        backend_factory=_BackendFactory(
            _FakeUnavailableBackend(reason="Backend SERIAL aun no implementado.")
        ),
        recorder_builder=recorder_builder,
    )

    assert controller.start_session() is False
    jsonl_path, report_path = _load_artifacts(controller)
    events = _read_jsonl_events(jsonl_path)
    event_types = [row["event_type"] for row in events]
    assert "session_started" in event_types
    assert "preflight_report" in event_types
    assert "session_error" in event_types
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["final_state"] == "error"
    assert report["had_errors"] is True
    assert controller.get_active_recording_session_id() is None


def test_logging_enabled_serial_start_stop_writes_jsonl_report_and_midi_events(tmp_path: Path) -> None:
    holder: dict[str, _FakeSerialTransport] = {}

    def _transport_builder(**kwargs):
        transport = _FakeSerialTransport(**kwargs)
        holder["transport"] = transport
        return transport

    serial_backend = SerialSessionBackend(
        _build_serial_cfg(logging_enabled=True),
        router_builder=lambda _cfg: _FakeMidiRouter([0]),
        transport_builder=_transport_builder,
    )
    recorder_builder = _RecorderBuilder(tmp_path / "sessions")
    controller = SessionController(
        _build_serial_cfg(logging_enabled=True),
        backend_factory=_BackendFactory(serial_backend),
        recorder_builder=recorder_builder,
    )

    assert controller.start_session() is True
    holder["transport"].emit_message(0x90, (60, 100), "note_on", channel=0)
    assert controller.stop_session() is True

    jsonl_path, report_path = _load_artifacts(controller)
    events = _read_jsonl_events(jsonl_path)
    event_types = [row["event_type"] for row in events]
    assert "session_stopped" in event_types
    assert "serial_message" in event_types
    assert "midi_event" in event_types
    assert "backend_runtime" in event_types

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["final_state"] == "idle"
    assert report["profile_id"] == "serial_local"
    assert report["mode"] == "serial"
    assert report["backend_kind"] == "serial"
    assert report["total_midi_events"] >= 1
    assert report["total_serial_messages"] >= 1
    assert report["had_errors"] is False
    assert controller.get_active_recording_session_id() is None

    session_dir = jsonl_path.parent
    shutil.rmtree(session_dir)
    assert not session_dir.exists()


def test_logging_disabled_keeps_lifecycle_without_creating_artifacts(tmp_path: Path) -> None:
    holder: dict[str, _FakeSerialTransport] = {}

    def _transport_builder(**kwargs):
        transport = _FakeSerialTransport(**kwargs)
        holder["transport"] = transport
        return transport

    serial_backend = SerialSessionBackend(
        _build_serial_cfg(logging_enabled=False),
        router_builder=lambda _cfg: _FakeMidiRouter([0]),
        transport_builder=_transport_builder,
    )
    recorder_builder = _RecorderBuilder(tmp_path / "sessions")
    controller = SessionController(
        _build_serial_cfg(logging_enabled=False),
        backend_factory=_BackendFactory(serial_backend),
        recorder_builder=recorder_builder,
    )

    assert controller.start_session() is True
    assert controller.stop_session() is True
    assert controller.get_last_recording_artifacts() is None
    assert controller.get_active_recording_session_id() is None
    assert recorder_builder.calls == 0
    assert not (tmp_path / "sessions").exists()


def test_logging_enabled_udp_flow_writes_udp_events_and_node_summary(tmp_path: Path) -> None:
    holder: dict[str, _FakeUdpTransport] = {}

    def _transport_builder(**kwargs):
        transport = _FakeUdpTransport(**kwargs)
        holder["transport"] = transport
        return transport

    udp_backend = UdpSessionBackend(
        _build_udp_cfg(logging_enabled=True),
        router_builder=lambda _cfg: _FakeMidiRouter([0, 1]),
        transport_builder=_transport_builder,
    )
    controller = SessionController(
        _build_udp_cfg(logging_enabled=True),
        backend_factory=_BackendFactory(udp_backend),
        recorder_builder=_RecorderBuilder(tmp_path / "sessions"),
    )

    assert controller.start_session() is True
    holder["transport"].emit_evt(vel=0)
    holder["transport"].emit_stat()
    assert controller.stop_session() is True

    jsonl_path, report_path = _load_artifacts(controller)
    events = _read_jsonl_events(jsonl_path)
    event_types = [row["event_type"] for row in events]
    assert "udp_evt" in event_types
    assert "udp_stat" in event_types
    assert "midi_event" in event_types
    assert "node_summary" in event_types

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["mode"] == "udp"
    assert report["backend_kind"] == "udp"
    assert report["total_udp_evt"] >= 1
    assert report["total_udp_stat"] >= 1
    assert controller.get_active_recording_session_id() is None
    assert controller.get_state() is SessionState.IDLE
