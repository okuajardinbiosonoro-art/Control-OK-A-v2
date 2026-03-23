from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from control_okua.core.control_plane.audit import (
    ControlAuditEvent,
    ControlAuditEventType,
    build_control_audit_event,
)
from control_okua.core.control_plane.protocol import ParsedOkuaAck
from control_okua.core.control_plane.runtime import (
    ControlPlaneNodeResolutionError,
    ControlPlaneRuntime,
)
from control_okua.services.control_transaction_service import (
    ControlTransactionFinalStatus,
    ControlTransactionResult,
)


@dataclass
class _PendingStoreStub:
    pending_count: int = 0


class _AckListenerStub:
    def __init__(self, *, ack_port: int = 5008, pending_count: int = 0, running: bool = True) -> None:
        self.ack_port = ack_port
        self.pending_store = _PendingStoreStub(pending_count=pending_count)
        self._running = running
        self.stop_calls = 0

    def is_running(self) -> bool:
        return self._running

    def stop(self) -> None:
        self.stop_calls += 1
        self._running = False


class _QueuedTransactionService:
    def __init__(self, results: list[ControlTransactionResult]) -> None:
        self._results = list(results)
        self.calls: list[tuple[str, str, int, str, int, int]] = []

    def _pop_result(self) -> ControlTransactionResult:
        if not self._results:
            raise AssertionError("No hay resultados de transacción en cola.")
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
        self.calls.append(("PING", node_ip, int(node_id), source, int(ack_timeout_ms), int(max_retries)))
        return self._pop_result()

    def send_request_stat_now_and_wait_ack(
        self,
        node_ip: str,
        node_id: int,
        *,
        source: str = "manual",
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
    ) -> ControlTransactionResult:
        self.calls.append(
            (
                "REQUEST_STAT_NOW",
                node_ip,
                int(node_id),
                source,
                int(ack_timeout_ms),
                int(max_retries),
            )
        )
        return self._pop_result()

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
        _ = delay_ms
        self.calls.append(
            (
                "REBOOT_SOFT",
                node_ip,
                int(node_id),
                source,
                int(ack_timeout_ms),
                int(max_retries),
            )
        )
        return self._pop_result()


def _fixed_utc() -> datetime:
    return datetime(2026, 3, 23, 12, 0, 0, tzinfo=timezone.utc)


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
    elapsed_ms: float = 42.0,
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
        elapsed_ms=elapsed_ms,
        last_error=last_error,
        events=events,
    )


def test_runtime_dispatch_uses_node_id_resolution_internally() -> None:
    resolver_calls: list[int] = []

    def _resolver(node_id: int) -> str:
        resolver_calls.append(int(node_id))
        return "192.168.10.55"

    tx = _QueuedTransactionService(
        [
            _tx_result(
                command_name="PING",
                cmd_id=0x01,
                node_ip="192.168.10.55",
                node_id=33,
                cmd_seq=700,
                nonce=0x1111222200000001,
                final_status=ControlTransactionFinalStatus.ACK_MATCHED,
                ack=_ack(node_id=33, cmd_seq=700, cmd_id=0x01, nonce=0x1111222200000001),
                events=(
                    _event(
                        ControlAuditEventType.COMMAND_SENT,
                        command_name="PING",
                        cmd_id=0x01,
                        node_ip="192.168.10.55",
                        node_id=33,
                        cmd_seq=700,
                        nonce=0x1111222200000001,
                        attempt_index=1,
                    ),
                    _event(
                        ControlAuditEventType.COMMAND_ACK,
                        command_name="PING",
                        cmd_id=0x01,
                        node_ip="192.168.10.55",
                        node_id=33,
                        cmd_seq=700,
                        nonce=0x1111222200000001,
                        attempt_index=1,
                        ack_stage=1,
                        status_code=0,
                        err_detail=0,
                    ),
                ),
            )
        ]
    )
    runtime = ControlPlaneRuntime(
        transaction_service=tx,
        ack_listener=_AckListenerStub(),
        node_ip_resolver=_resolver,
    )

    result = runtime.send_ping(
        node_id=33,
        ack_timeout_ms=600,
        max_retries=2,
        source="ui_manual",
    )

    assert resolver_calls == [33]
    assert tx.calls == [("PING", "192.168.10.55", 33, "ui_manual", 600, 2)]
    assert result.node_ip == "192.168.10.55"


def test_runtime_returns_controlled_error_when_node_ip_is_not_resolvable() -> None:
    def _resolver(_node_id: int) -> str:
        raise RuntimeError("node_id sin IP en runtime")

    runtime = ControlPlaneRuntime(
        transaction_service=_QueuedTransactionService([]),
        ack_listener=_AckListenerStub(),
        node_ip_resolver=_resolver,
    )

    try:
        runtime.send_ping(node_id=90, ack_timeout_ms=200, max_retries=0)
        assert False, "Se esperaba ControlPlaneNodeResolutionError"
    except ControlPlaneNodeResolutionError as exc:
        assert "node_id sin IP" in str(exc)


def test_runtime_snapshot_and_recording_sink_reflect_send_retry_ack_timeout() -> None:
    sink_rows: list[tuple[str, dict[str, object]]] = []

    def _sink(event_type: str, payload: dict[str, object]) -> None:
        sink_rows.append((event_type, payload))

    tx = _QueuedTransactionService(
        [
            _tx_result(
                command_name="PING",
                cmd_id=0x01,
                node_ip="10.0.0.7",
                node_id=7,
                cmd_seq=101,
                nonce=0xAAAA000000000001,
                final_status=ControlTransactionFinalStatus.TIMEOUT,
                attempt_count=2,
                last_error="Timeout final",
                events=(
                    _event(
                        ControlAuditEventType.COMMAND_SENT,
                        command_name="PING",
                        cmd_id=0x01,
                        node_ip="10.0.0.7",
                        node_id=7,
                        cmd_seq=101,
                        nonce=0xAAAA000000000001,
                        attempt_index=1,
                    ),
                    _event(
                        ControlAuditEventType.COMMAND_RETRY,
                        command_name="PING",
                        cmd_id=0x01,
                        node_ip="10.0.0.7",
                        node_id=7,
                        cmd_seq=101,
                        nonce=0xAAAA000000000001,
                        attempt_index=2,
                    ),
                    _event(
                        ControlAuditEventType.UNMATCHED_ACK_SEEN,
                        command_name="PING",
                        cmd_id=0x01,
                        node_ip="10.0.0.7",
                        node_id=7,
                        cmd_seq=101,
                        nonce=0xAAAA000000000001,
                        attempt_index=2,
                        detail="orphan",
                    ),
                    _event(
                        ControlAuditEventType.INVALID_ACK_SEEN,
                        command_name="PING",
                        cmd_id=0x01,
                        node_ip="10.0.0.7",
                        node_id=7,
                        cmd_seq=101,
                        nonce=0xAAAA000000000001,
                        attempt_index=2,
                        detail="invalid magic",
                    ),
                    _event(
                        ControlAuditEventType.COMMAND_TIMEOUT,
                        command_name="PING",
                        cmd_id=0x01,
                        node_ip="10.0.0.7",
                        node_id=7,
                        cmd_seq=101,
                        nonce=0xAAAA000000000001,
                        attempt_index=2,
                    ),
                ),
            ),
            _tx_result(
                command_name="REQUEST_STAT_NOW",
                cmd_id=0x07,
                node_ip="10.0.0.7",
                node_id=7,
                cmd_seq=102,
                nonce=0xAAAA000000000002,
                final_status=ControlTransactionFinalStatus.ACK_MATCHED,
                ack=_ack(node_id=7, cmd_seq=102, cmd_id=0x07, nonce=0xAAAA000000000002),
                events=(
                    _event(
                        ControlAuditEventType.COMMAND_SENT,
                        command_name="REQUEST_STAT_NOW",
                        cmd_id=0x07,
                        node_ip="10.0.0.7",
                        node_id=7,
                        cmd_seq=102,
                        nonce=0xAAAA000000000002,
                        attempt_index=1,
                    ),
                    _event(
                        ControlAuditEventType.COMMAND_ACK,
                        command_name="REQUEST_STAT_NOW",
                        cmd_id=0x07,
                        node_ip="10.0.0.7",
                        node_id=7,
                        cmd_seq=102,
                        nonce=0xAAAA000000000002,
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
        ack_listener=_AckListenerStub(ack_port=5008, pending_count=0, running=True),
        node_ip_resolver=lambda _node_id: "10.0.0.7",
        recording_sink=_sink,
        session_id_provider=lambda: "S-CTRL-1",
        utc_now_provider=_fixed_utc,
    )

    timeout_result = runtime.send_ping(node_id=7, ack_timeout_ms=150, max_retries=1, source="manual")
    assert timeout_result.final_status is ControlTransactionFinalStatus.TIMEOUT

    ack_result = runtime.send_request_stat_now(node_id=7, ack_timeout_ms=150, max_retries=0, source="manual")
    assert ack_result.final_status is ControlTransactionFinalStatus.ACK_MATCHED

    snapshot = runtime.snapshot()
    assert snapshot.is_available is True
    assert snapshot.listener_active is True
    assert snapshot.ack_port == 5008
    assert snapshot.commands_sent_total == 2
    assert snapshot.command_retry_total == 1
    assert snapshot.command_ack_total == 1
    assert snapshot.command_timeout_total == 1
    assert snapshot.invalid_ack_total == 1
    assert snapshot.unmatched_ack_total == 1
    assert snapshot.last_result is not None
    assert snapshot.last_result.command_name == "REQUEST_STAT_NOW"
    assert snapshot.last_result.final_status == ControlTransactionFinalStatus.ACK_MATCHED.value
    assert snapshot.per_node_last_status[0].node_id == 7
    assert snapshot.per_node_last_status[0].cmd_seq == 102
    assert len(snapshot.recent_results) == 2

    sink_event_types = [row[0] for row in sink_rows]
    assert sink_event_types == [
        "command_sent",
        "command_retry",
        "command_timeout",
        "command_sent",
        "command_ack",
    ]
    for _event_type, payload in sink_rows:
        assert payload["plane"] == "control_f3"
        assert payload["session_id"] == "S-CTRL-1"
        assert payload["node_id"] == 7


def test_runtime_per_node_status_keeps_newer_cmd_seq_when_older_result_arrives_later() -> None:
    tx = _QueuedTransactionService(
        [
            _tx_result(
                command_name="PING",
                cmd_id=0x01,
                node_ip="10.0.0.8",
                node_id=8,
                cmd_seq=900,
                nonce=0xAAAABBBB00000900,
                final_status=ControlTransactionFinalStatus.ACK_MATCHED,
                ack=_ack(node_id=8, cmd_seq=900, cmd_id=0x01, nonce=0xAAAABBBB00000900),
                events=(
                    _event(
                        ControlAuditEventType.COMMAND_SENT,
                        command_name="PING",
                        cmd_id=0x01,
                        node_ip="10.0.0.8",
                        node_id=8,
                        cmd_seq=900,
                        nonce=0xAAAABBBB00000900,
                        attempt_index=1,
                    ),
                    _event(
                        ControlAuditEventType.COMMAND_ACK,
                        command_name="PING",
                        cmd_id=0x01,
                        node_ip="10.0.0.8",
                        node_id=8,
                        cmd_seq=900,
                        nonce=0xAAAABBBB00000900,
                        attempt_index=1,
                        ack_stage=1,
                        status_code=0,
                        err_detail=0,
                    ),
                ),
            ),
            _tx_result(
                command_name="PING",
                cmd_id=0x01,
                node_ip="10.0.0.8",
                node_id=8,
                cmd_seq=899,
                nonce=0xAAAABBBB00000899,
                final_status=ControlTransactionFinalStatus.TIMEOUT,
                last_error="Timeout antiguo.",
                events=(
                    _event(
                        ControlAuditEventType.COMMAND_SENT,
                        command_name="PING",
                        cmd_id=0x01,
                        node_ip="10.0.0.8",
                        node_id=8,
                        cmd_seq=899,
                        nonce=0xAAAABBBB00000899,
                        attempt_index=1,
                    ),
                    _event(
                        ControlAuditEventType.COMMAND_TIMEOUT,
                        command_name="PING",
                        cmd_id=0x01,
                        node_ip="10.0.0.8",
                        node_id=8,
                        cmd_seq=899,
                        nonce=0xAAAABBBB00000899,
                        attempt_index=1,
                    ),
                ),
            ),
        ]
    )
    runtime = ControlPlaneRuntime(
        transaction_service=tx,
        ack_listener=_AckListenerStub(),
        node_ip_resolver=lambda _node_id: "10.0.0.8",
        utc_now_provider=_fixed_utc,
    )

    runtime.send_ping(node_id=8, ack_timeout_ms=120, max_retries=0)
    runtime.send_ping(node_id=8, ack_timeout_ms=120, max_retries=0)

    row = runtime.snapshot().per_node_last_status[0]
    assert row.node_id == 8
    assert row.cmd_seq == 900
    assert row.final_status == "ack_matched"
    assert row.ack_stage == 1
    assert row.last_error_message is None


def test_runtime_per_node_status_prefers_more_complete_row_when_cmd_seq_matches() -> None:
    tx = _QueuedTransactionService(
        [
            _tx_result(
                command_name="REQUEST_STAT_NOW",
                cmd_id=0x07,
                node_ip="10.0.0.9",
                node_id=9,
                cmd_seq=1200,
                nonce=0xCCCCDDDD00001200,
                final_status=ControlTransactionFinalStatus.TIMEOUT,
                last_error="Timeout esperando ACK.",
                events=(
                    _event(
                        ControlAuditEventType.COMMAND_SENT,
                        command_name="REQUEST_STAT_NOW",
                        cmd_id=0x07,
                        node_ip="10.0.0.9",
                        node_id=9,
                        cmd_seq=1200,
                        nonce=0xCCCCDDDD00001200,
                        attempt_index=1,
                    ),
                    _event(
                        ControlAuditEventType.COMMAND_TIMEOUT,
                        command_name="REQUEST_STAT_NOW",
                        cmd_id=0x07,
                        node_ip="10.0.0.9",
                        node_id=9,
                        cmd_seq=1200,
                        nonce=0xCCCCDDDD00001200,
                        attempt_index=1,
                    ),
                ),
            ),
            _tx_result(
                command_name="REQUEST_STAT_NOW",
                cmd_id=0x07,
                node_ip="10.0.0.9",
                node_id=9,
                cmd_seq=1200,
                nonce=0xCCCCDDDD00001200,
                final_status=ControlTransactionFinalStatus.ACK_MATCHED,
                ack=_ack(node_id=9, cmd_seq=1200, cmd_id=0x07, nonce=0xCCCCDDDD00001200),
                events=(
                    _event(
                        ControlAuditEventType.COMMAND_SENT,
                        command_name="REQUEST_STAT_NOW",
                        cmd_id=0x07,
                        node_ip="10.0.0.9",
                        node_id=9,
                        cmd_seq=1200,
                        nonce=0xCCCCDDDD00001200,
                        attempt_index=1,
                    ),
                    _event(
                        ControlAuditEventType.COMMAND_ACK,
                        command_name="REQUEST_STAT_NOW",
                        cmd_id=0x07,
                        node_ip="10.0.0.9",
                        node_id=9,
                        cmd_seq=1200,
                        nonce=0xCCCCDDDD00001200,
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
        node_ip_resolver=lambda _node_id: "10.0.0.9",
        utc_now_provider=_fixed_utc,
    )

    runtime.send_request_stat_now(node_id=9, ack_timeout_ms=120, max_retries=0)
    runtime.send_request_stat_now(node_id=9, ack_timeout_ms=120, max_retries=0)

    row = runtime.snapshot().per_node_last_status[0]
    assert row.node_id == 9
    assert row.cmd_seq == 1200
    assert row.final_status == "ack_matched"
    assert row.ack_stage == 1
    assert row.status_code == 0
    assert row.err_detail == 0
