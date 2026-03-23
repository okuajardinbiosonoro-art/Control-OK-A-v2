from __future__ import annotations

from dataclasses import dataclass
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.control_plane.audit import ControlAuditEventType  # noqa: E402
from control_okua.core.control_plane.pending import (  # noqa: E402
    AckCorrelationResult,
    AckCorrelationStatus,
    PendingCommandStore,
)
from control_okua.core.control_plane.protocol import ParsedOkuaAck  # noqa: E402
from control_okua.core.control_plane.runtime import (  # noqa: E402
    ControlPlaneNodeStatusSnapshot,
    ControlPlaneRuntimeSnapshot,
)
from control_okua.core.control_plane.runtime_snapshot import (  # noqa: E402
    ControlPlaneNodeResolutionStatus,
)
from control_okua.core.registry.node_models import NodeSnapshot, NodeStatus  # noqa: E402
from control_okua.services.cmd_service import SentOkuaCommand  # noqa: E402
from control_okua.services.control_transaction_service import (  # noqa: E402
    ControlTransactionFinalStatus,
    ControlTransactionService,
)
from control_okua.services.session_controller import SessionController  # noqa: E402


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += max(0.0, float(seconds))


class _FakeCmdService:
    def __init__(self, *, cmd_seq: int, nonce: int) -> None:
        self._cmd_seq = int(cmd_seq)
        self._nonce = int(nonce)

    def send_ping(self, node_ip: str, node_id: int, *, source: str = "manual") -> SentOkuaCommand:
        return SentOkuaCommand(
            source=source,
            command_name="PING",
            cmd_id=0x01,
            node_ip=str(node_ip),
            node_id=int(node_id),
            cmd_seq=self._cmd_seq,
            nonce=self._nonce,
            target_port=5007,
            packet=b"\xAA" * 28,
            bytes_sent=28,
        )

    def resend_sent_command(
        self,
        sent_command: SentOkuaCommand,
        *,
        source: str = "retry",
    ) -> SentOkuaCommand:
        return SentOkuaCommand(
            source=source,
            command_name=sent_command.command_name,
            cmd_id=sent_command.cmd_id,
            node_ip=sent_command.node_ip,
            node_id=sent_command.node_id,
            cmd_seq=sent_command.cmd_seq,
            nonce=sent_command.nonce,
            target_port=sent_command.target_port,
            packet=sent_command.packet,
            bytes_sent=len(sent_command.packet),
        )

    def send_request_stat_now(
        self,
        node_ip: str,
        node_id: int,
        *,
        source: str = "manual",
    ) -> SentOkuaCommand:
        _ = (node_ip, node_id, source)
        raise AssertionError("No se esperaba REQUEST_STAT_NOW en este test.")

    def send_reboot_soft(
        self,
        node_ip: str,
        node_id: int,
        *,
        delay_ms: int = 0,
        source: str = "manual",
    ) -> SentOkuaCommand:
        _ = (node_ip, node_id, delay_ms, source)
        raise AssertionError("No se esperaba REBOOT_SOFT en este test.")


class _FakeAckListener:
    def __init__(
        self,
        *,
        pending_store: PendingCommandStore,
        scripted_results: list[AckCorrelationResult | None],
    ) -> None:
        self._pending_store = pending_store
        self._scripted_results = list(scripted_results)

    @property
    def pending_store(self) -> PendingCommandStore:
        return self._pending_store

    def is_running(self) -> bool:
        return True

    def start(self) -> bool:
        return True

    def poll_once(self) -> AckCorrelationResult | None:
        if self._scripted_results:
            return self._scripted_results.pop(0)
        return None


def _make_sent(
    *,
    node_ip: str,
    node_id: int,
    cmd_seq: int,
    nonce: int,
) -> SentOkuaCommand:
    return SentOkuaCommand(
        source="manual",
        command_name="PING",
        cmd_id=0x01,
        node_ip=node_ip,
        node_id=node_id,
        cmd_seq=cmd_seq,
        nonce=nonce,
        target_port=5007,
        packet=b"\xAA" * 28,
        bytes_sent=28,
    )


def _ack_for(sent: SentOkuaCommand) -> ParsedOkuaAck:
    return ParsedOkuaAck(
        node_id_source=sent.node_id,
        cmd_seq=sent.cmd_seq,
        cmd_id_echo=sent.cmd_id,
        nonce_echo=sent.nonce,
        ack_stage=1,
        status_code=0,
        ack_flags=0,
        err_detail=0,
        retry_after_ms=0,
        auth_tag32=0x11223344,
    )


def _matched_for(sent: SentOkuaCommand) -> AckCorrelationResult:
    return AckCorrelationResult(
        status=AckCorrelationStatus.MATCHED,
        ack=_ack_for(sent),
        sent_command=sent,
        source_ip=sent.node_ip,
        source_port=5008,
        received_ts=0.0,
    )


def _orphan_ack_for_node(
    *,
    node_id: int,
    cmd_seq: int,
    nonce: int,
    node_ip: str,
) -> AckCorrelationResult:
    return AckCorrelationResult(
        status=AckCorrelationStatus.UNMATCHED_ACK,
        ack=ParsedOkuaAck(
            node_id_source=node_id,
            cmd_seq=cmd_seq,
            cmd_id_echo=0x01,
            nonce_echo=nonce,
            ack_stage=1,
            status_code=0,
            ack_flags=0,
            err_detail=0,
            retry_after_ms=0,
            auth_tag32=0x55667788,
        ),
        sent_command=None,
        source_ip=node_ip,
        source_port=5008,
        received_ts=0.0,
    )


def _event_types(result) -> list[str]:
    return [event.event_type for event in result.events]


def test_ack_of_node_b_during_wait_of_node_a_does_not_close_a_transaction() -> None:
    clock = _FakeClock()
    store = PendingCommandStore(clock=clock)
    cmd = _FakeCmdService(cmd_seq=1001, nonce=0xAAAABBBB00000001)
    sent_a = _make_sent(
        node_ip="10.0.0.1",
        node_id=1,
        cmd_seq=1001,
        nonce=0xAAAABBBB00000001,
    )
    sent_b = _make_sent(
        node_ip="10.0.0.3",
        node_id=3,
        cmd_seq=2002,
        nonce=0xCCCCDDDD00000003,
    )
    listener = _FakeAckListener(
        pending_store=store,
        scripted_results=[
            _matched_for(sent_b),
            _matched_for(sent_a),
        ],
    )
    service = ControlTransactionService(
        cmd_service=cmd,
        ack_listener=listener,
        clock=clock,
        sleep_fn=clock.sleep,
    )

    result = service.send_ping_and_wait_ack(
        "10.0.0.1",
        1,
        ack_timeout_ms=60,
        max_retries=0,
        poll_interval_ms=10,
    )

    assert result.final_status is ControlTransactionFinalStatus.ACK_MATCHED
    assert result.node_id == 1
    assert result.node_ip == "10.0.0.1"
    assert result.ack is not None
    assert result.ack.node_id_source == 1
    events = _event_types(result)
    assert ControlAuditEventType.UNMATCHED_ACK_SEEN.value in events
    assert events[-1] == ControlAuditEventType.COMMAND_ACK.value


def test_orphan_ack_of_node_b_is_observed_but_does_not_close_node_a_transaction() -> None:
    clock = _FakeClock()
    store = PendingCommandStore(clock=clock)
    cmd = _FakeCmdService(cmd_seq=501, nonce=0x1234000000000001)
    listener = _FakeAckListener(
        pending_store=store,
        scripted_results=[
            _orphan_ack_for_node(
                node_id=3,
                cmd_seq=3333,
                nonce=0xDEAD000000000003,
                node_ip="10.0.0.3",
            ),
            None,
            None,
        ],
    )
    service = ControlTransactionService(
        cmd_service=cmd,
        ack_listener=listener,
        clock=clock,
        sleep_fn=clock.sleep,
    )

    result = service.send_ping_and_wait_ack(
        "10.0.0.1",
        1,
        ack_timeout_ms=20,
        max_retries=0,
        poll_interval_ms=10,
    )

    assert result.final_status is ControlTransactionFinalStatus.UNMATCHED_ACK_SEEN
    assert result.node_id == 1
    assert result.ack is None
    events = _event_types(result)
    assert ControlAuditEventType.UNMATCHED_ACK_SEEN.value in events
    assert ControlAuditEventType.COMMAND_TIMEOUT.value in events


@dataclass(frozen=True)
class _BackendHolder:
    node_id: int
    source_ip: str
    received_ts: float


@dataclass(frozen=True)
class _BackendRuntimeSnapshot:
    last_evt: object | None = None
    last_stat: object | None = None


class _BackendStub:
    def __init__(self, *, node_snapshots: list[NodeSnapshot], runtime_snapshot: object) -> None:
        self._node_snapshots = {int(item.node_id): item for item in node_snapshots}
        self._runtime_snapshot = runtime_snapshot

    def runtime_snapshot(self) -> object:
        return self._runtime_snapshot

    def get_node_snapshots(self, now: float | None = None) -> list[NodeSnapshot]:
        _ = now
        return list(self._node_snapshots.values())

    def get_node_snapshot(self, node_id: int, now: float | None = None) -> NodeSnapshot | None:
        _ = now
        return self._node_snapshots.get(int(node_id))


class _ControlRuntimeStub:
    def __init__(
        self,
        *,
        snapshot: ControlPlaneRuntimeSnapshot,
        active_node_ids: tuple[int, ...],
    ) -> None:
        self._snapshot = snapshot
        self._active_node_ids = tuple(active_node_ids)

    def snapshot(self) -> ControlPlaneRuntimeSnapshot:
        return self._snapshot

    def active_node_ids(self) -> tuple[int, ...]:
        return self._active_node_ids


def _build_cfg() -> dict[str, object]:
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
    }


def _node_snapshot(*, node_id: int, last_seen_pc_ts: float, uptime_s: int) -> NodeSnapshot:
    return NodeSnapshot(
        node_id=node_id,
        label=None,
        node_type=None,
        last_seen_pc_ts=last_seen_pc_ts,
        last_seq_evt=1,
        last_seq_stat=1,
        pps_evt=1.0,
        pps_stat=1.0,
        loss_evt_pct=0.0,
        loss_stat_pct=0.0,
        rssi_dbm=-60,
        last_note=60,
        last_velocity=100,
        last_evt_ts_ms=1000,
        last_evt_flags=0,
        last_state_flags=0x10 if node_id == 1 else 0x20,
        last_uptime_s=uptime_s,
        reported_pps_x10=10,
        status=NodeStatus.ONLINE,
        reset_reason=1 if node_id == 1 else 2,
    )


def test_session_snapshot_isolation_keeps_results_reboot_and_activity_per_node() -> None:
    controller = SessionController(_build_cfg())
    controller._active_backend = _BackendStub(
        node_snapshots=[
            _node_snapshot(node_id=1, last_seen_pc_ts=99.0, uptime_s=80),
            _node_snapshot(node_id=3, last_seen_pc_ts=98.0, uptime_s=140),
        ],
        runtime_snapshot=_BackendRuntimeSnapshot(
            last_evt=_BackendHolder(node_id=1, source_ip="10.0.0.1", received_ts=99.0),
        ),
    )
    controller._control_plane_runtime = _ControlRuntimeStub(
        snapshot=ControlPlaneRuntimeSnapshot(
            is_available=True,
            listener_active=True,
            ack_port=5008,
            pending_count=1,
            commands_sent_total=2,
            command_retry_total=0,
            command_ack_total=1,
            command_timeout_total=1,
            invalid_ack_total=0,
            unmatched_ack_total=1,
            last_command=None,
            last_result=None,
            per_node_last_status=(
                ControlPlaneNodeStatusSnapshot(
                    node_id=1,
                    node_ip="10.0.0.1",
                    command_name="PING",
                    cmd_seq=10,
                    nonce=0xAAAABBBB00000001,
                    final_status="ack_matched",
                    ack_stage=1,
                    status_code=0,
                    err_detail=0,
                    last_error_message=None,
                    tx_started_at_utc="2026-03-23T15:00:00.000Z",
                    tx_finished_at_utc="2026-03-23T15:00:00.200Z",
                    ts_utc="2026-03-23T15:00:00.200Z",
                ),
                ControlPlaneNodeStatusSnapshot(
                    node_id=3,
                    node_ip="10.0.0.3",
                    command_name="PING",
                    cmd_seq=11,
                    nonce=0xCCCCDDDD00000003,
                    final_status="timeout",
                    ack_stage=None,
                    status_code=None,
                    err_detail=None,
                    last_error_message="Timeout esperando ACK de nodo 3.",
                    tx_started_at_utc="2026-03-23T15:00:01.000Z",
                    tx_finished_at_utc="2026-03-23T15:00:02.000Z",
                    ts_utc="2026-03-23T15:00:02.000Z",
                ),
            ),
            recent_results=tuple(),
        ),
        active_node_ids=(1,),
    )
    controller.record_control_plane_reboot_verification(
        node_id=1,
        status="confirmed",
        summary="verificación_reinicio_resumen: nodo=1 intentos=3 corte=1 recuperado=1",
    )

    snapshots = controller.get_control_plane_node_snapshots(now=100.0)
    by_id = {item.node_id: item for item in snapshots}
    node_a = by_id[1]
    node_b = by_id[3]

    assert node_a.resolved_ip == "10.0.0.1"
    assert node_a.resolution_status is ControlPlaneNodeResolutionStatus.RESOLVED
    assert node_a.last_final_status == "ack_matched"
    assert node_a.last_reboot_verification_status == "confirmed"
    assert node_a.transaction_active is True

    assert node_b.resolution_status is ControlPlaneNodeResolutionStatus.UNRESOLVED
    assert node_b.last_final_status == "timeout"
    assert node_b.last_reboot_verification_status is None
    assert node_b.last_reboot_verification_summary is None
    assert node_b.transaction_active is False
    assert "nodo=1" not in (node_b.message or "")
