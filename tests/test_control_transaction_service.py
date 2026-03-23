from __future__ import annotations

from dataclasses import replace

from control_okua.core.control_plane.audit import ControlAuditEventType
from control_okua.core.control_plane.pending import (
    AckCorrelationResult,
    AckCorrelationStatus,
    PendingCommandStore,
)
from control_okua.core.control_plane.protocol import ParsedOkuaAck
from control_okua.services.cmd_service import CmdServiceSendError, SentOkuaCommand
from control_okua.services.control_transaction_service import (
    ControlTransactionFinalStatus,
    ControlTransactionService,
)


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += max(0.0, float(seconds))


class _FakeCmdService:
    def __init__(
        self,
        *,
        cmd_seq: int = 500,
        nonce: int = 0x1234567800000000,
        fail_on_send: bool = False,
        fail_on_retry: bool = False,
    ) -> None:
        self.cmd_seq = cmd_seq
        self.nonce = nonce
        self.fail_on_send = fail_on_send
        self.fail_on_retry = fail_on_retry
        self.send_calls: list[tuple[str, str, int]] = []
        self.retry_calls: list[SentOkuaCommand] = []

    def send_ping(self, node_ip: str, node_id: int, *, source: str = "manual") -> SentOkuaCommand:
        return self._send(
            command_name="PING",
            cmd_id=0x01,
            node_ip=node_ip,
            node_id=node_id,
            source=source,
        )

    def send_request_stat_now(
        self,
        node_ip: str,
        node_id: int,
        *,
        source: str = "manual",
    ) -> SentOkuaCommand:
        return self._send(
            command_name="REQUEST_STAT_NOW",
            cmd_id=0x07,
            node_ip=node_ip,
            node_id=node_id,
            source=source,
        )

    def send_reboot_soft(
        self,
        node_ip: str,
        node_id: int,
        *,
        delay_ms: int = 0,
        source: str = "manual",
    ) -> SentOkuaCommand:
        _ = delay_ms
        return self._send(
            command_name="REBOOT_SOFT",
            cmd_id=0x02,
            node_ip=node_ip,
            node_id=node_id,
            source=source,
        )

    def resend_sent_command(
        self,
        sent_command: SentOkuaCommand,
        *,
        source: str = "retry",
    ) -> SentOkuaCommand:
        self.retry_calls.append(sent_command)
        if self.fail_on_retry:
            raise CmdServiceSendError("retry failed")
        return replace(
            sent_command,
            source=source,
            bytes_sent=len(sent_command.packet),
        )

    def _send(
        self,
        *,
        command_name: str,
        cmd_id: int,
        node_ip: str,
        node_id: int,
        source: str,
    ) -> SentOkuaCommand:
        self.send_calls.append((command_name, node_ip, node_id))
        if self.fail_on_send:
            raise CmdServiceSendError("send failed")
        return SentOkuaCommand(
            source=source,
            command_name=command_name,
            cmd_id=cmd_id,
            node_ip=node_ip,
            node_id=node_id,
            cmd_seq=self.cmd_seq,
            nonce=self.nonce,
            target_port=5007,
            packet=b"\xAA" * 28,
            bytes_sent=28,
        )


class _FakeAckListener:
    def __init__(
        self,
        *,
        pending_store: PendingCommandStore,
        scripted_results: list[AckCorrelationResult | None] | None = None,
        running: bool = True,
        start_ok: bool = True,
    ) -> None:
        self._pending_store = pending_store
        self._scripted_results = list(scripted_results or [])
        self._running = running
        self._start_ok = start_ok
        self.start_calls = 0
        self.poll_calls = 0

    @property
    def pending_store(self) -> PendingCommandStore:
        return self._pending_store

    def is_running(self) -> bool:
        return self._running

    def start(self) -> bool:
        self.start_calls += 1
        if not self._start_ok:
            raise RuntimeError("listener start failed")
        self._running = True
        return True

    def poll_once(self) -> AckCorrelationResult | None:
        self.poll_calls += 1
        if self._scripted_results:
            return self._scripted_results.pop(0)
        return None


def _make_sent(
    *,
    command_name: str,
    cmd_id: int,
    node_ip: str,
    node_id: int,
    cmd_seq: int,
    nonce: int,
) -> SentOkuaCommand:
    return SentOkuaCommand(
        source="manual",
        command_name=command_name,
        cmd_id=cmd_id,
        node_ip=node_ip,
        node_id=node_id,
        cmd_seq=cmd_seq,
        nonce=nonce,
        target_port=5007,
        packet=b"\xAA" * 28,
        bytes_sent=28,
    )


def _make_ack_for(sent: SentOkuaCommand) -> ParsedOkuaAck:
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
        auth_tag32=0x01020304,
    )


def _matched_for(sent: SentOkuaCommand) -> AckCorrelationResult:
    return AckCorrelationResult(
        status=AckCorrelationStatus.MATCHED,
        ack=_make_ack_for(sent),
        sent_command=sent,
        source_ip=sent.node_ip,
        source_port=5008,
        received_ts=0.0,
    )


def _invalid_ack_result() -> AckCorrelationResult:
    return AckCorrelationResult(
        status=AckCorrelationStatus.INVALID_ACK,
        ack=None,
        sent_command=None,
        parse_error_code="invalid_size",
        parse_error_message="ACK invalido: longitud 2 bytes (esperado 28).",
        source_ip="127.0.0.1",
        source_port=5008,
        received_ts=0.0,
        raw_len=2,
    )


def _unmatched_ack_result() -> AckCorrelationResult:
    return AckCorrelationResult(
        status=AckCorrelationStatus.UNMATCHED_ACK,
        ack=ParsedOkuaAck(
            node_id_source=99,
            cmd_seq=999,
            cmd_id_echo=0x07,
            nonce_echo=0xABCDEF0000000001,
            ack_stage=1,
            status_code=0,
            ack_flags=0,
            err_detail=0,
            retry_after_ms=0,
            auth_tag32=0x11223344,
        ),
        sent_command=None,
        source_ip="10.0.0.9",
        source_port=5008,
        received_ts=0.0,
    )


def _event_types(result) -> list[str]:
    return [event.event_type for event in result.events]


def test_transaction_success_with_matched_ack() -> None:
    clock = _FakeClock()
    store = PendingCommandStore(clock=clock)
    cmd = _FakeCmdService(cmd_seq=123, nonce=0xAAAABBBB00000000)
    expected_sent = _make_sent(
        command_name="PING",
        cmd_id=0x01,
        node_ip="192.168.1.40",
        node_id=12,
        cmd_seq=123,
        nonce=0xAAAABBBB00000000,
    )
    listener = _FakeAckListener(
        pending_store=store,
        scripted_results=[_matched_for(expected_sent)],
        running=True,
    )
    service = ControlTransactionService(
        cmd_service=cmd,
        ack_listener=listener,
        clock=clock,
        sleep_fn=clock.sleep,
    )

    result = service.send_ping_and_wait_ack(
        "192.168.1.40",
        12,
        ack_timeout_ms=50,
        max_retries=1,
        poll_interval_ms=10,
    )

    assert result.final_status is ControlTransactionFinalStatus.ACK_MATCHED
    assert result.attempt_count == 1
    assert result.ack is not None
    assert result.cmd_seq == 123
    assert result.nonce == 0xAAAABBBB00000000
    assert result.matched_sent_command is not None
    assert cmd.retry_calls == []
    assert listener.start_calls == 0
    assert _event_types(result) == [
        ControlAuditEventType.COMMAND_SENT.value,
        ControlAuditEventType.COMMAND_ACK.value,
    ]


def test_transaction_timeout_without_ack() -> None:
    clock = _FakeClock()
    store = PendingCommandStore(clock=clock)
    cmd = _FakeCmdService(cmd_seq=300, nonce=0x1111000000000000)
    listener = _FakeAckListener(pending_store=store, running=True)
    service = ControlTransactionService(
        cmd_service=cmd,
        ack_listener=listener,
        clock=clock,
        sleep_fn=clock.sleep,
    )

    result = service.send_ping_and_wait_ack(
        "192.168.1.77",
        14,
        ack_timeout_ms=20,
        max_retries=0,
        poll_interval_ms=10,
    )

    assert result.final_status is ControlTransactionFinalStatus.TIMEOUT
    assert result.attempt_count == 1
    assert result.ack is None
    assert store.pending_count == 0
    assert ControlAuditEventType.COMMAND_TIMEOUT.value in _event_types(result)


def test_transaction_retries_after_partial_timeout_and_reuses_seq_nonce() -> None:
    clock = _FakeClock()
    store = PendingCommandStore(clock=clock)
    cmd = _FakeCmdService(cmd_seq=444, nonce=0x2222333300000001)
    expected_sent = _make_sent(
        command_name="REQUEST_STAT_NOW",
        cmd_id=0x07,
        node_ip="10.0.0.15",
        node_id=33,
        cmd_seq=444,
        nonce=0x2222333300000001,
    )
    listener = _FakeAckListener(
        pending_store=store,
        scripted_results=[
            None,
            None,
            _matched_for(expected_sent),
        ],
        running=True,
    )
    service = ControlTransactionService(
        cmd_service=cmd,
        ack_listener=listener,
        clock=clock,
        sleep_fn=clock.sleep,
    )

    result = service.send_request_stat_now_and_wait_ack(
        "10.0.0.15",
        33,
        ack_timeout_ms=20,
        max_retries=1,
        poll_interval_ms=10,
    )

    assert result.final_status is ControlTransactionFinalStatus.ACK_MATCHED
    assert result.attempt_count == 2
    assert len(cmd.retry_calls) == 1
    retried = cmd.retry_calls[0]
    assert retried.cmd_seq == 444
    assert retried.nonce == 0x2222333300000001
    assert result.cmd_seq == 444
    assert result.nonce == 0x2222333300000001
    assert ControlAuditEventType.COMMAND_RETRY.value in _event_types(result)


def test_invalid_ack_does_not_close_transaction_prematurely() -> None:
    clock = _FakeClock()
    store = PendingCommandStore(clock=clock)
    cmd = _FakeCmdService(cmd_seq=600, nonce=0x3333000000000001)
    expected_sent = _make_sent(
        command_name="PING",
        cmd_id=0x01,
        node_ip="127.0.0.1",
        node_id=12,
        cmd_seq=600,
        nonce=0x3333000000000001,
    )
    listener = _FakeAckListener(
        pending_store=store,
        scripted_results=[_invalid_ack_result(), _matched_for(expected_sent)],
        running=True,
    )
    service = ControlTransactionService(
        cmd_service=cmd,
        ack_listener=listener,
        clock=clock,
        sleep_fn=clock.sleep,
    )

    result = service.send_ping_and_wait_ack(
        "127.0.0.1",
        12,
        ack_timeout_ms=80,
        max_retries=0,
        poll_interval_ms=10,
    )

    assert result.final_status is ControlTransactionFinalStatus.ACK_MATCHED
    events = _event_types(result)
    assert ControlAuditEventType.INVALID_ACK_SEEN.value in events
    assert ControlAuditEventType.COMMAND_ACK.value in events


def test_unmatched_ack_does_not_close_transaction_prematurely() -> None:
    clock = _FakeClock()
    store = PendingCommandStore(clock=clock)
    cmd = _FakeCmdService(cmd_seq=700, nonce=0x4444000000000001)
    expected_sent = _make_sent(
        command_name="PING",
        cmd_id=0x01,
        node_ip="127.0.0.1",
        node_id=12,
        cmd_seq=700,
        nonce=0x4444000000000001,
    )
    listener = _FakeAckListener(
        pending_store=store,
        scripted_results=[_unmatched_ack_result(), _matched_for(expected_sent)],
        running=True,
    )
    service = ControlTransactionService(
        cmd_service=cmd,
        ack_listener=listener,
        clock=clock,
        sleep_fn=clock.sleep,
    )

    result = service.send_ping_and_wait_ack(
        "127.0.0.1",
        12,
        ack_timeout_ms=80,
        max_retries=0,
        poll_interval_ms=10,
    )

    assert result.final_status is ControlTransactionFinalStatus.ACK_MATCHED
    events = _event_types(result)
    assert ControlAuditEventType.UNMATCHED_ACK_SEEN.value in events
    assert ControlAuditEventType.COMMAND_ACK.value in events


def test_listener_is_started_automatically_when_not_running() -> None:
    clock = _FakeClock()
    store = PendingCommandStore(clock=clock)
    cmd = _FakeCmdService(cmd_seq=800, nonce=0x5555000000000001)
    expected_sent = _make_sent(
        command_name="PING",
        cmd_id=0x01,
        node_ip="127.0.0.1",
        node_id=12,
        cmd_seq=800,
        nonce=0x5555000000000001,
    )
    listener = _FakeAckListener(
        pending_store=store,
        scripted_results=[_matched_for(expected_sent)],
        running=False,
        start_ok=True,
    )
    service = ControlTransactionService(
        cmd_service=cmd,
        ack_listener=listener,
        clock=clock,
        sleep_fn=clock.sleep,
    )

    result = service.send_ping_and_wait_ack(
        "127.0.0.1",
        12,
        ack_timeout_ms=50,
        max_retries=0,
    )

    assert result.final_status is ControlTransactionFinalStatus.ACK_MATCHED
    assert listener.start_calls == 1
    assert listener.is_running() is True


def test_listener_start_failure_returns_listener_not_running() -> None:
    clock = _FakeClock()
    store = PendingCommandStore(clock=clock)
    cmd = _FakeCmdService()
    listener = _FakeAckListener(
        pending_store=store,
        running=False,
        start_ok=False,
    )
    service = ControlTransactionService(
        cmd_service=cmd,
        ack_listener=listener,
        clock=clock,
        sleep_fn=clock.sleep,
    )

    result = service.send_ping_and_wait_ack("127.0.0.1", 12, ack_timeout_ms=50, max_retries=0)

    assert result.final_status is ControlTransactionFinalStatus.LISTENER_NOT_RUNNING
    assert result.attempt_count == 0
    assert ControlAuditEventType.LISTENER_NOT_RUNNING.value in _event_types(result)


def test_send_error_returns_send_error_status() -> None:
    clock = _FakeClock()
    store = PendingCommandStore(clock=clock)
    cmd = _FakeCmdService(fail_on_send=True)
    listener = _FakeAckListener(pending_store=store, running=True)
    service = ControlTransactionService(
        cmd_service=cmd,
        ack_listener=listener,
        clock=clock,
        sleep_fn=clock.sleep,
    )

    result = service.send_ping_and_wait_ack("127.0.0.1", 12, ack_timeout_ms=50, max_retries=0)

    assert result.final_status is ControlTransactionFinalStatus.SEND_ERROR
    assert result.attempt_count == 1
    assert ControlAuditEventType.SEND_ERROR.value in _event_types(result)


def test_invalid_ack_seen_status_when_only_invalid_acks_and_timeout() -> None:
    clock = _FakeClock()
    store = PendingCommandStore(clock=clock)
    cmd = _FakeCmdService(cmd_seq=910, nonce=0x9999000000000001)
    listener = _FakeAckListener(
        pending_store=store,
        scripted_results=[_invalid_ack_result(), None, None],
        running=True,
    )
    service = ControlTransactionService(
        cmd_service=cmd,
        ack_listener=listener,
        clock=clock,
        sleep_fn=clock.sleep,
    )

    result = service.send_ping_and_wait_ack(
        "127.0.0.1",
        12,
        ack_timeout_ms=20,
        max_retries=0,
        poll_interval_ms=10,
    )

    assert result.final_status is ControlTransactionFinalStatus.INVALID_ACK_SEEN


def test_unmatched_ack_seen_status_when_only_unmatched_acks_and_timeout() -> None:
    clock = _FakeClock()
    store = PendingCommandStore(clock=clock)
    cmd = _FakeCmdService(cmd_seq=920, nonce=0xAAAA000000000001)
    listener = _FakeAckListener(
        pending_store=store,
        scripted_results=[_unmatched_ack_result(), None, None],
        running=True,
    )
    service = ControlTransactionService(
        cmd_service=cmd,
        ack_listener=listener,
        clock=clock,
        sleep_fn=clock.sleep,
    )

    result = service.send_ping_and_wait_ack(
        "127.0.0.1",
        12,
        ack_timeout_ms=20,
        max_retries=0,
        poll_interval_ms=10,
    )

    assert result.final_status is ControlTransactionFinalStatus.UNMATCHED_ACK_SEEN
