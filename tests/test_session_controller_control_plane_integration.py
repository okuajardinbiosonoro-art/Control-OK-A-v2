from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.control_plane.audit import (  # noqa: E402
    ControlAuditEvent,
    ControlAuditEventType,
    build_control_audit_event,
)
from control_okua.core.control_plane.protocol import ParsedOkuaAck  # noqa: E402
from control_okua.core.control_plane.runtime import ControlPlaneRuntime  # noqa: E402
from control_okua.core.recording import JsonlSessionRecorder  # noqa: E402
from control_okua.services.backends import UdpSessionBackend  # noqa: E402
from control_okua.services.control_transaction_service import (  # noqa: E402
    ControlTransactionFinalStatus,
    ControlTransactionResult,
)
from control_okua.services.session_controller import SessionController  # noqa: E402
from control_okua.transports.udp import UdpTransportConfig, UdpTransportSnapshot  # noqa: E402


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
    def open(self) -> None:
        return None

    def close(self) -> None:
        return None

    def opened_buses(self) -> list[int]:
        return [0, 1]

    def send_note_on(self, bus: int, ch: int, note: int, vel: int) -> None:
        _ = (bus, ch, note, vel)

    def send_note_off(self, bus: int, ch: int, note: int, vel: int = 0) -> None:
        _ = (bus, ch, note, vel)

    def send_raw_midi(self, bus: int, data: bytes | list[int] | tuple[int, ...]) -> None:
        _ = (bus, data)


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
        _ = (on_evt_packet, on_stat_packet, on_event)
        self._config = config
        self._start_result = start_result
        self._running = False

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
            total_evt_packets=0,
            total_stat_packets=0,
            total_bytes_received=0,
            parse_errors=0,
            socket_errors=0,
            last_activity_ts=1.0 if self._running else None,
            last_packet_summary=None,
            last_error=None,
        )


@dataclass
class _BackendFactory:
    backend: Any
    build_calls: int = 0

    def build_backend_for_spec(self, _spec: object) -> Any:
        self.build_calls += 1
        return self.backend


@dataclass
class _PendingStoreStub:
    pending_count: int = 0


class _AckListenerStub:
    def __init__(self) -> None:
        self.ack_port = 5008
        self.pending_store = _PendingStoreStub()
        self._running = True
        self.stop_calls = 0

    def is_running(self) -> bool:
        return self._running

    def stop(self) -> None:
        self.stop_calls += 1
        self._running = False


class _QueuedTransactionService:
    def __init__(self, results: list[ControlTransactionResult]) -> None:
        self._results = list(results)
        self.calls: list[str] = []

    def _pop_result(self, command_name: str) -> ControlTransactionResult:
        self.calls.append(command_name)
        if not self._results:
            raise AssertionError("No hay resultados en cola para transacción.")
        return self._results.pop(0)

    def send_ping_and_wait_ack(
        self,
        node_ip: str,
        node_id: int,
        *,
        source: str = "manual",
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
    ) -> ControlTransactionResult:
        _ = (node_ip, node_id, source, ack_timeout_ms, max_retries)
        return self._pop_result("PING")

    def send_request_stat_now_and_wait_ack(
        self,
        node_ip: str,
        node_id: int,
        *,
        source: str = "manual",
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
    ) -> ControlTransactionResult:
        _ = (node_ip, node_id, source, ack_timeout_ms, max_retries)
        return self._pop_result("REQUEST_STAT_NOW")

    def send_reboot_soft_and_wait_ack(
        self,
        node_ip: str,
        node_id: int,
        *,
        delay_ms: int = 0,
        source: str = "manual",
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
    ) -> ControlTransactionResult:
        _ = (node_ip, node_id, delay_ms, source, ack_timeout_ms, max_retries)
        return self._pop_result("REBOOT_SOFT")


def _fixed_utc() -> datetime:
    return datetime(2026, 3, 23, 14, 0, 0, tzinfo=timezone.utc)


def _event(
    event_type: ControlAuditEventType,
    *,
    command_name: str,
    cmd_id: int,
    node_ip: str,
    node_id: int,
    cmd_seq: int,
    nonce: int,
    attempt_index: int,
    ack_stage: int | None = None,
    status_code: int | None = None,
    err_detail: int | None = None,
    detail: str | None = None,
) -> ControlAuditEvent:
    return build_control_audit_event(
        event_type=event_type,
        command_name=command_name,
        cmd_id=cmd_id,
        node_ip=node_ip,
        node_id=node_id,
        cmd_seq=cmd_seq,
        nonce=nonce,
        attempt_index=attempt_index,
        ack_stage=ack_stage,
        status_code=status_code,
        err_detail=err_detail,
        detail=detail,
        utc_now_provider=_fixed_utc,
    )


def _ack(*, node_id: int, cmd_seq: int, cmd_id: int, nonce: int) -> ParsedOkuaAck:
    return ParsedOkuaAck(
        node_id_source=node_id,
        cmd_seq=cmd_seq,
        cmd_id_echo=cmd_id,
        nonce_echo=nonce,
        ack_stage=1,
        status_code=0,
        ack_flags=0,
        err_detail=0,
        retry_after_ms=0,
        auth_tag32=0x11223344,
    )


def _tx_result(
    *,
    command_name: str,
    cmd_id: int,
    node_ip: str,
    node_id: int,
    cmd_seq: int,
    nonce: int,
    final_status: ControlTransactionFinalStatus,
    events: tuple[ControlAuditEvent, ...],
    ack: ParsedOkuaAck | None = None,
    attempt_count: int = 1,
    last_error: str | None = None,
) -> ControlTransactionResult:
    return ControlTransactionResult(
        command_name=command_name,
        cmd_id=cmd_id,
        node_ip=node_ip,
        node_id=node_id,
        cmd_seq=cmd_seq,
        nonce=nonce,
        attempt_count=attempt_count,
        final_status=final_status,
        ack=ack,
        matched_sent_command=None,
        elapsed_ms=10.0,
        last_error=last_error,
        events=events,
    )


def _load_jsonl_event_types(path: Path) -> list[str]:
    rows = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return [str(row["event_type"]) for row in rows]


def test_control_plane_events_are_recorded_in_session_jsonl(tmp_path: Path) -> None:
    backend = UdpSessionBackend(
        _build_udp_cfg(logging_enabled=True),
        router_builder=lambda _cfg: _FakeMidiRouter(),
        transport_builder=lambda **kwargs: _FakeUdpTransport(**kwargs),
    )
    controller = SessionController(
        _build_udp_cfg(logging_enabled=True),
        backend_factory=_BackendFactory(backend),
        recorder_builder=lambda _cfg: JsonlSessionRecorder(base_sessions_dir=tmp_path / "sessions"),
    )
    assert controller.start_session() is True

    tx = _QueuedTransactionService(
        [
            _tx_result(
                command_name="PING",
                cmd_id=0x01,
                node_ip="127.0.0.1",
                node_id=10,
                cmd_seq=500,
                nonce=0xABCD000000000001,
                final_status=ControlTransactionFinalStatus.TIMEOUT,
                attempt_count=2,
                last_error="Timeout final",
                events=(
                    _event(
                        ControlAuditEventType.COMMAND_SENT,
                        command_name="PING",
                        cmd_id=0x01,
                        node_ip="127.0.0.1",
                        node_id=10,
                        cmd_seq=500,
                        nonce=0xABCD000000000001,
                        attempt_index=1,
                    ),
                    _event(
                        ControlAuditEventType.COMMAND_RETRY,
                        command_name="PING",
                        cmd_id=0x01,
                        node_ip="127.0.0.1",
                        node_id=10,
                        cmd_seq=500,
                        nonce=0xABCD000000000001,
                        attempt_index=2,
                    ),
                    _event(
                        ControlAuditEventType.COMMAND_TIMEOUT,
                        command_name="PING",
                        cmd_id=0x01,
                        node_ip="127.0.0.1",
                        node_id=10,
                        cmd_seq=500,
                        nonce=0xABCD000000000001,
                        attempt_index=2,
                    ),
                ),
            ),
            _tx_result(
                command_name="REQUEST_STAT_NOW",
                cmd_id=0x07,
                node_ip="127.0.0.1",
                node_id=10,
                cmd_seq=501,
                nonce=0xABCD000000000002,
                final_status=ControlTransactionFinalStatus.ACK_MATCHED,
                ack=_ack(node_id=10, cmd_seq=501, cmd_id=0x07, nonce=0xABCD000000000002),
                events=(
                    _event(
                        ControlAuditEventType.COMMAND_SENT,
                        command_name="REQUEST_STAT_NOW",
                        cmd_id=0x07,
                        node_ip="127.0.0.1",
                        node_id=10,
                        cmd_seq=501,
                        nonce=0xABCD000000000002,
                        attempt_index=1,
                    ),
                    _event(
                        ControlAuditEventType.COMMAND_ACK,
                        command_name="REQUEST_STAT_NOW",
                        cmd_id=0x07,
                        node_ip="127.0.0.1",
                        node_id=10,
                        cmd_seq=501,
                        nonce=0xABCD000000000002,
                        attempt_index=1,
                        ack_stage=1,
                        status_code=0,
                        err_detail=0,
                    ),
                ),
            ),
        ]
    )
    runtime = ControlPlaneRuntime(
        transaction_service=tx,
        ack_listener=_AckListenerStub(),
        node_ip_resolver=lambda _node_id: "127.0.0.1",
        recording_sink=controller._record_event,
        session_id_provider=controller.get_active_recording_session_id,
        utc_now_provider=_fixed_utc,
    )
    controller._control_plane_runtime = runtime

    timeout_result = controller.send_control_ping(node_id=10, ack_timeout_ms=120, max_retries=1)
    ack_result = controller.send_control_request_stat_now(node_id=10, ack_timeout_ms=120, max_retries=0)
    assert timeout_result.final_status is ControlTransactionFinalStatus.TIMEOUT
    assert ack_result.final_status is ControlTransactionFinalStatus.ACK_MATCHED

    snapshot = controller.get_control_plane_runtime_snapshot()
    assert snapshot.commands_sent_total == 2
    assert snapshot.command_retry_total == 1
    assert snapshot.command_timeout_total == 1
    assert snapshot.command_ack_total == 1

    assert controller.stop_session() is True

    artifacts = controller.get_last_recording_artifacts()
    assert artifacts is not None
    session_jsonl_path = getattr(artifacts, "session_jsonl_path")
    session_dir = getattr(artifacts, "session_dir")
    assert isinstance(session_jsonl_path, Path)
    assert isinstance(session_dir, Path)

    event_types = _load_jsonl_event_types(session_jsonl_path)
    assert "command_sent" in event_types
    assert "command_retry" in event_types
    assert "command_timeout" in event_types
    assert "command_ack" in event_types

    extra_jsonl_files = [
        path.name
        for path in session_dir.glob("*.jsonl")
        if path.name != "session.jsonl"
    ]
    assert extra_jsonl_files == []
