from __future__ import annotations

from dataclasses import dataclass
import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.control_plane.runtime import (  # noqa: E402
    ControlPlaneNodeStatusSnapshot,
    ControlPlaneRuntimeSnapshot,
)
from control_okua.core.control_plane.protocol import ParsedOkuaAck  # noqa: E402
from control_okua.core.control_plane.runtime_snapshot import (  # noqa: E402
    ControlPlaneResolvedIp,
    ControlPlaneNodeResolutionStatus,
)
from control_okua.core.registry.node_models import NodeSnapshot, NodeStatus  # noqa: E402
from control_okua.services.control_transaction_service import (  # noqa: E402
    ControlTransactionFinalStatus,
    ControlTransactionResult,
)
from control_okua.services.session_controller import SessionController  # noqa: E402


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
        runtime_snapshot: ControlPlaneRuntimeSnapshot,
        active_node_ids: tuple[int, ...] = tuple(),
    ) -> None:
        self._runtime_snapshot = runtime_snapshot
        self._active_node_ids = tuple(active_node_ids)

    def snapshot(self) -> ControlPlaneRuntimeSnapshot:
        return self._runtime_snapshot

    def active_node_ids(self) -> tuple[int, ...]:
        return self._active_node_ids


def _build_cfg() -> dict[str, Any]:
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


def _node_snapshot(*, node_id: int, last_seen_pc_ts: float, uptime: int, reset_reason: int, flags: int) -> NodeSnapshot:
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
        last_note=64,
        last_velocity=100,
        last_evt_ts_ms=1234,
        last_evt_flags=0,
        last_state_flags=flags,
        last_uptime_s=uptime,
        reported_pps_x10=10,
        status=NodeStatus.ONLINE,
        reset_reason=reset_reason,
    )


def _control_runtime_snapshot() -> ControlPlaneRuntimeSnapshot:
    return ControlPlaneRuntimeSnapshot(
        is_available=True,
        listener_active=True,
        ack_port=5008,
        pending_count=1,
        commands_sent_total=3,
        command_retry_total=1,
        command_ack_total=1,
        command_timeout_total=1,
        invalid_ack_total=0,
        unmatched_ack_total=0,
        last_command=None,
        last_result=None,
        per_node_last_status=(
            ControlPlaneNodeStatusSnapshot(
                node_id=1,
                node_ip="10.0.0.1",
                command_name="REQUEST_STAT_NOW",
                cmd_seq=100,
                nonce=0xAAAA000000000001,
                final_status="ack_matched",
                ack_stage=1,
                status_code=0,
                err_detail=0,
                last_error_message=None,
                tx_started_at_utc="2026-03-23T14:00:00.000Z",
                tx_finished_at_utc="2026-03-23T14:00:00.300Z",
                ts_utc="2026-03-23T14:00:00.300Z",
            ),
            ControlPlaneNodeStatusSnapshot(
                node_id=2,
                node_ip="10.0.0.2",
                command_name="REBOOT_SOFT",
                cmd_seq=101,
                nonce=0xAAAA000000000002,
                final_status="timeout",
                ack_stage=1,
                status_code=9,
                err_detail=44,
                last_error_message="Timeout esperando ACK.",
                tx_started_at_utc="2026-03-23T14:01:00.000Z",
                tx_finished_at_utc="2026-03-23T14:01:01.500Z",
                ts_utc="2026-03-23T14:01:01.500Z",
            ),
        ),
        recent_results=tuple(),
    )


def test_session_controller_exposes_canonical_control_plane_snapshot_api() -> None:
    controller = SessionController(_build_cfg())
    controller._active_backend = _BackendStub(
        node_snapshots=[
            _node_snapshot(node_id=1, last_seen_pc_ts=99.5, uptime=80, reset_reason=1, flags=0x10),
            _node_snapshot(node_id=2, last_seen_pc_ts=96.0, uptime=120, reset_reason=2, flags=0x20),
        ],
        runtime_snapshot=_BackendRuntimeSnapshot(
            last_evt=_BackendHolder(node_id=1, source_ip="10.0.0.1", received_ts=99.0),
            last_stat=_BackendHolder(node_id=2, source_ip="10.0.0.2", received_ts=80.0),
        ),
    )
    controller._control_plane_runtime = _ControlRuntimeStub(
        runtime_snapshot=_control_runtime_snapshot(),
        active_node_ids=(2,),
    )
    controller.record_control_plane_reboot_verification(
        node_id=2,
        status="confirmed",
        summary="verificación_reinicio_resumen: intentos=4 corte=1 recuperado=1",
    )

    snapshots = controller.get_control_plane_node_snapshots(now=100.0)
    by_id = {item.node_id: item for item in snapshots}

    assert 1 in by_id
    assert 2 in by_id
    assert by_id[1].resolution_status is ControlPlaneNodeResolutionStatus.RESOLVED
    assert by_id[1].resolved_ip == "10.0.0.1"
    assert by_id[1].last_uptime_s == 80
    assert by_id[1].last_reset_reason == 1
    assert by_id[1].last_boot_marker == 1

    assert by_id[2].resolution_status is ControlPlaneNodeResolutionStatus.STALE
    assert by_id[2].transaction_active is True
    assert by_id[2].last_final_status == "timeout"
    assert by_id[2].last_status_code == 9
    assert by_id[2].last_err_detail == 44
    assert by_id[2].last_reboot_verification_status == "confirmed"
    assert "verificación_reinicio_resumen" in (by_id[2].last_reboot_verification_summary or "")

    one_node = controller.get_control_plane_node_snapshot(node_id=1, now=100.0)
    assert one_node is not None
    assert one_node.node_id == 1
    assert one_node.last_command_name == "REQUEST_STAT_NOW"
    assert one_node.last_cmd_seq == 100
    assert one_node.last_nonce == 0xAAAA000000000001
    assert one_node.last_tx_started_at == "2026-03-23T14:00:00.000Z"
    assert one_node.last_tx_finished_at == "2026-03-23T14:00:00.300Z"

    unresolved = controller.get_control_plane_node_snapshot(node_id=77, now=100.0)
    assert unresolved is not None
    assert unresolved.resolution_status is ControlPlaneNodeResolutionStatus.UNRESOLVED


def test_session_controller_control_plane_snapshot_api_has_no_widget_dependency() -> None:
    controller = SessionController(_build_cfg())

    snapshots = controller.get_control_plane_node_snapshots(now=100.0)
    single = controller.get_control_plane_node_snapshot(node_id=1, now=100.0)

    assert snapshots == []
    assert single is not None
    assert single.node_id == 1
    assert single.resolution_status is ControlPlaneNodeResolutionStatus.UNRESOLVED


@dataclass
class _ControlRuntimeWriteBackStub:
    runtime_snapshot: ControlPlaneRuntimeSnapshot
    ping_result: ControlTransactionResult
    request_stat_result: ControlTransactionResult

    def snapshot(self) -> ControlPlaneRuntimeSnapshot:
        return self.runtime_snapshot

    def active_node_ids(self) -> tuple[int, ...]:
        return tuple()

    def send_ping(
        self,
        *,
        node_id: int,
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
        source: str = "manual_ui",
    ) -> ControlTransactionResult:
        _ = (node_id, ack_timeout_ms, max_retries, source)
        return self.ping_result

    def send_request_stat_now(
        self,
        *,
        node_id: int,
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
        source: str = "manual_ui",
    ) -> ControlTransactionResult:
        _ = (node_id, ack_timeout_ms, max_retries, source)
        return self.request_stat_result

    def send_reboot_soft(
        self,
        *,
        node_id: int,
        delay_ms: int = 0,
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
        source: str = "manual_ui",
    ) -> ControlTransactionResult:
        _ = (node_id, delay_ms, ack_timeout_ms, max_retries, source)
        return self.request_stat_result


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
    ack: ParsedOkuaAck | None,
    last_error: str | None,
) -> ControlTransactionResult:
    return ControlTransactionResult(
        command_name=command_name,
        cmd_id=cmd_id,
        node_ip=node_ip,
        node_id=node_id,
        cmd_seq=cmd_seq,
        nonce=nonce,
        attempt_count=1,
        final_status=final_status,
        ack=ack,
        matched_sent_command=None,
        elapsed_ms=30.0,
        last_error=last_error,
        events=tuple(),
    )


def test_session_controller_write_back_uses_newer_result_even_if_runtime_snapshot_is_old() -> None:
    old_runtime = ControlPlaneRuntimeSnapshot(
        is_available=True,
        listener_active=True,
        ack_port=5008,
        pending_count=0,
        commands_sent_total=1,
        command_retry_total=0,
        command_ack_total=0,
        command_timeout_total=1,
        invalid_ack_total=0,
        unmatched_ack_total=0,
        last_command=None,
        last_result=None,
        per_node_last_status=(
            ControlPlaneNodeStatusSnapshot(
                node_id=1,
                node_ip="10.0.0.1",
                command_name="PING",
                cmd_seq=100,
                nonce=0xAAAA000000000100,
                final_status="timeout",
                ack_stage=None,
                status_code=None,
                err_detail=None,
                last_error_message="Timeout viejo.",
                tx_started_at_utc="2026-03-23T10:00:00.000Z",
                tx_finished_at_utc="2026-03-23T10:00:01.000Z",
                ts_utc="2026-03-23T10:00:01.000Z",
            ),
        ),
        recent_results=tuple(),
    )
    ack_result = _tx_result(
        command_name="PING",
        cmd_id=0x01,
        node_ip="10.0.0.1",
        node_id=1,
        cmd_seq=101,
        nonce=0xAAAA000000000101,
        final_status=ControlTransactionFinalStatus.ACK_MATCHED,
        ack=_ack(node_id=1, cmd_seq=101, cmd_id=0x01, nonce=0xAAAA000000000101),
        last_error=None,
    )
    timeout_other_node = _tx_result(
        command_name="PING",
        cmd_id=0x01,
        node_ip="10.0.0.3",
        node_id=3,
        cmd_seq=50,
        nonce=0xBBBB000000000050,
        final_status=ControlTransactionFinalStatus.TIMEOUT,
        ack=None,
        last_error="Timeout nodo 3.",
    )
    runtime = _ControlRuntimeWriteBackStub(
        runtime_snapshot=old_runtime,
        ping_result=ack_result,
        request_stat_result=timeout_other_node,
    )

    controller = SessionController(_build_cfg())
    controller._control_plane_runtime = runtime
    controller._ensure_control_plane_runtime = lambda: runtime  # type: ignore[method-assign]
    controller._control_plane_node_ip_cache[1] = ControlPlaneResolvedIp(
        node_id=1,
        ip="10.0.0.1",
        observed_at_monotonic=99.0,
    )
    controller._control_plane_node_ip_cache[3] = ControlPlaneResolvedIp(
        node_id=3,
        ip="10.0.0.3",
        observed_at_monotonic=99.0,
    )

    controller.send_control_ping(node_id=1, ack_timeout_ms=120, max_retries=0)
    controller.send_control_request_stat_now(node_id=3, ack_timeout_ms=120, max_retries=0)

    one = controller.get_control_plane_node_snapshot(node_id=1, now=100.0)
    three = controller.get_control_plane_node_snapshot(node_id=3, now=100.0)
    assert one is not None
    assert three is not None
    assert one.last_cmd_seq == 101
    assert one.last_final_status == "ack_matched"
    assert one.last_ack_stage == 1
    assert one.last_error_message is None
    assert three.last_cmd_seq == 50
    assert three.last_final_status == "timeout"
    assert three.last_ack_stage is None
    assert "timeout" in (three.last_error_message or "").lower()


def test_session_controller_write_back_state_is_session_scoped_and_cleared_on_reload() -> None:
    controller = SessionController(_build_cfg())
    controller._control_plane_tx_cache[1] = ControlPlaneNodeStatusSnapshot(
        node_id=1,
        node_ip="10.0.0.1",
        command_name="PING",
        cmd_seq=300,
        nonce=0xAAAA000000000300,
        final_status="ack_matched",
        ack_stage=1,
        status_code=0,
        err_detail=0,
        last_error_message=None,
        tx_started_at_utc="2026-03-23T13:00:00.000Z",
        tx_finished_at_utc="2026-03-23T13:00:00.200Z",
        ts_utc="2026-03-23T13:00:00.200Z",
    )
    controller._control_plane_node_ip_cache[1] = ControlPlaneResolvedIp(
        node_id=1,
        ip="10.0.0.1",
        observed_at_monotonic=99.0,
    )

    updated_snapshot = controller.reload_config(_build_cfg())
    assert updated_snapshot is not None
    assert controller._control_plane_tx_cache == {}

    node = controller.get_control_plane_node_snapshot(node_id=1, now=100.0)
    assert node is not None
    assert node.last_cmd_seq is None
    assert node.last_final_status is None
