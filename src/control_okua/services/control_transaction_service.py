from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Protocol

from control_okua.core.control_plane.audit import (
    ControlAuditEvent,
    ControlAuditEventType,
    build_control_audit_event,
)
from control_okua.core.control_plane.pending import (
    AckCorrelationResult,
    AckCorrelationStatus,
    PendingCommandStore,
    SentCommandLike,
)
from control_okua.core.control_plane.protocol import ParsedOkuaAck
from control_okua.services.cmd_service import SentOkuaCommand


class ControlTransactionFinalStatus(str, Enum):
    ACK_MATCHED = "ack_matched"
    TIMEOUT = "timeout"
    INVALID_ACK_SEEN = "invalid_ack_seen"
    UNMATCHED_ACK_SEEN = "unmatched_ack_seen"
    LISTENER_NOT_RUNNING = "listener_not_running"
    SEND_ERROR = "send_error"


@dataclass(frozen=True)
class ControlTransactionResult:
    command_name: str
    cmd_id: int
    node_ip: str
    node_id: int
    cmd_seq: int | None
    nonce: int | None
    attempt_count: int
    final_status: ControlTransactionFinalStatus
    ack: ParsedOkuaAck | None
    matched_sent_command: SentCommandLike | None
    elapsed_ms: float
    last_error: str | None
    events: tuple[ControlAuditEvent, ...]


class CmdTransactionClient(Protocol):
    def send_ping(self, node_ip: str, node_id: int, *, source: str = "manual") -> SentOkuaCommand:
        ...

    def send_request_stat_now(
        self,
        node_ip: str,
        node_id: int,
        *,
        source: str = "manual",
    ) -> SentOkuaCommand:
        ...

    def send_reboot_soft(
        self,
        node_ip: str,
        node_id: int,
        *,
        delay_ms: int = 0,
        source: str = "manual",
    ) -> SentOkuaCommand:
        ...

    def send_set_stat_rate(
        self,
        node_ip: str,
        node_id: int,
        *,
        stat_rate_ms: int,
        source: str = "manual",
    ) -> SentOkuaCommand:
        ...

    def resend_sent_command(
        self,
        sent_command: SentOkuaCommand,
        *,
        source: str = "retry",
    ) -> SentOkuaCommand:
        ...


class AckListenerClient(Protocol):
    @property
    def pending_store(self) -> PendingCommandStore:
        ...

    def is_running(self) -> bool:
        ...

    def start(self) -> bool:
        ...

    def poll_once(self) -> AckCorrelationResult | None:
        ...


class ControlTransactionService:
    """
    F3 app-side transaction manager with timeout/retry/idempotent-retry semantics.

    Listener lifecycle policy in this ticket:
    - if listener is not running, the service starts it in a controlled way;
    - once started, listener remains running (this service does not auto-stop it).
    """

    def __init__(
        self,
        *,
        cmd_service: CmdTransactionClient,
        ack_listener: AckListenerClient,
        pending_store: PendingCommandStore | None = None,
        clock: Callable[[], float] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        utc_now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._cmd_service = cmd_service
        self._ack_listener = ack_listener
        self._pending_store = pending_store or ack_listener.pending_store
        if self._pending_store is not ack_listener.pending_store:
            raise ValueError(
                "ControlTransactionService requiere que pending_store sea el mismo del AckListenerService."
            )
        self._clock = clock or time.monotonic
        self._sleep_fn = sleep_fn or time.sleep
        self._utc_now_provider = utc_now_provider

    def send_ping_and_wait_ack(
        self,
        node_ip: str,
        node_id: int,
        *,
        source: str = "manual",
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
        poll_interval_ms: int = 20,
    ) -> ControlTransactionResult:
        return self._execute_transaction(
            command_name="PING",
            cmd_id=0x01,
            node_ip=node_ip,
            node_id=node_id,
            ack_timeout_ms=ack_timeout_ms,
            max_retries=max_retries,
            poll_interval_ms=poll_interval_ms,
            initial_send=lambda: self._cmd_service.send_ping(node_ip, node_id, source=source),
        )

    def send_request_stat_now_and_wait_ack(
        self,
        node_ip: str,
        node_id: int,
        *,
        source: str = "manual",
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
        poll_interval_ms: int = 20,
    ) -> ControlTransactionResult:
        return self._execute_transaction(
            command_name="REQUEST_STAT_NOW",
            cmd_id=0x07,
            node_ip=node_ip,
            node_id=node_id,
            ack_timeout_ms=ack_timeout_ms,
            max_retries=max_retries,
            poll_interval_ms=poll_interval_ms,
            initial_send=lambda: self._cmd_service.send_request_stat_now(
                node_ip,
                node_id,
                source=source,
            ),
        )

    def send_reboot_soft_and_wait_ack(
        self,
        node_ip: str,
        node_id: int,
        *,
        delay_ms: int = 0,
        source: str = "manual",
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
        poll_interval_ms: int = 20,
    ) -> ControlTransactionResult:
        return self._execute_transaction(
            command_name="REBOOT_SOFT",
            cmd_id=0x02,
            node_ip=node_ip,
            node_id=node_id,
            ack_timeout_ms=ack_timeout_ms,
            max_retries=max_retries,
            poll_interval_ms=poll_interval_ms,
            initial_send=lambda: self._cmd_service.send_reboot_soft(
                node_ip,
                node_id,
                delay_ms=delay_ms,
                source=source,
            ),
        )

    def send_set_stat_rate_and_wait_ack(
        self,
        node_ip: str,
        node_id: int,
        *,
        stat_rate_ms: int,
        source: str = "manual",
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
        poll_interval_ms: int = 20,
    ) -> ControlTransactionResult:
        return self._execute_transaction(
            command_name="SET_STAT_RATE",
            cmd_id=0x05,
            node_ip=node_ip,
            node_id=node_id,
            ack_timeout_ms=ack_timeout_ms,
            max_retries=max_retries,
            poll_interval_ms=poll_interval_ms,
            initial_send=lambda: self._cmd_service.send_set_stat_rate(
                node_ip,
                node_id,
                stat_rate_ms=stat_rate_ms,
                source=source,
            ),
        )

    def _execute_transaction(
        self,
        *,
        command_name: str,
        cmd_id: int,
        node_ip: str,
        node_id: int,
        ack_timeout_ms: int,
        max_retries: int,
        poll_interval_ms: int,
        initial_send: Callable[[], SentOkuaCommand],
    ) -> ControlTransactionResult:
        ack_timeout_s = _validate_timeout_ms(ack_timeout_ms) / 1000.0
        poll_interval_s = _validate_poll_interval_ms(poll_interval_ms) / 1000.0
        retries = _validate_max_retries(max_retries)

        tx_started = float(self._clock())
        events: list[ControlAuditEvent] = []
        invalid_ack_seen = False
        unmatched_ack_seen = False
        attempt_count = 0
        last_error: str | None = None
        active_sent: SentOkuaCommand | None = None

        listener_error = self._ensure_listener_running()
        if listener_error is not None:
            events.append(
                self._audit_event(
                    event_type=ControlAuditEventType.LISTENER_NOT_RUNNING,
                    command_name=command_name,
                    cmd_id=cmd_id,
                    node_ip=node_ip,
                    node_id=node_id,
                    cmd_seq=None,
                    nonce=None,
                    attempt_index=0,
                    detail=listener_error,
                )
            )
            return self._build_result(
                command_name=command_name,
                cmd_id=cmd_id,
                node_ip=node_ip,
                node_id=node_id,
                cmd_seq=None,
                nonce=None,
                attempt_count=0,
                final_status=ControlTransactionFinalStatus.LISTENER_NOT_RUNNING,
                ack=None,
                matched_sent_command=None,
                tx_started=tx_started,
                last_error=listener_error,
                events=events,
            )

        for attempt_index in range(1, retries + 2):
            attempt_count = attempt_index
            is_retry = attempt_index > 1
            try:
                if is_retry:
                    if active_sent is None:
                        raise RuntimeError("No hay comando base para retry.")
                    resent = self._cmd_service.resend_sent_command(active_sent, source="retry")
                    _assert_retry_identity(active_sent, resent)
                    active_sent = resent
                else:
                    active_sent = initial_send()
            except Exception as exc:
                last_error = str(exc)
                events.append(
                    self._audit_event(
                        event_type=ControlAuditEventType.SEND_ERROR,
                        command_name=command_name,
                        cmd_id=cmd_id,
                        node_ip=node_ip,
                        node_id=node_id,
                        cmd_seq=None if active_sent is None else active_sent.cmd_seq,
                        nonce=None if active_sent is None else active_sent.nonce,
                        attempt_index=attempt_index,
                        detail=last_error,
                    )
                )
                return self._build_result(
                    command_name=command_name,
                    cmd_id=cmd_id,
                    node_ip=node_ip,
                    node_id=node_id,
                    cmd_seq=None if active_sent is None else active_sent.cmd_seq,
                    nonce=None if active_sent is None else active_sent.nonce,
                    attempt_count=attempt_count,
                    final_status=ControlTransactionFinalStatus.SEND_ERROR,
                    ack=None,
                    matched_sent_command=active_sent,
                    tx_started=tx_started,
                    last_error=last_error,
                    events=events,
                )

            self._pending_store.register_sent_command(active_sent)
            events.append(
                self._audit_event(
                    event_type=ControlAuditEventType.COMMAND_RETRY
                    if is_retry
                    else ControlAuditEventType.COMMAND_SENT,
                    command_name=active_sent.command_name,
                    cmd_id=active_sent.cmd_id,
                    node_ip=active_sent.node_ip,
                    node_id=active_sent.node_id,
                    cmd_seq=active_sent.cmd_seq,
                    nonce=active_sent.nonce,
                    attempt_index=attempt_index,
                )
            )

            deadline = float(self._clock()) + ack_timeout_s
            listener_runtime_error: str | None = None

            while float(self._clock()) < deadline:
                try:
                    observed = self._ack_listener.poll_once()
                except Exception as exc:
                    listener_runtime_error = str(exc)
                    break

                if observed is None:
                    if poll_interval_s > 0:
                        self._sleep_fn(poll_interval_s)
                    continue

                if observed.status is AckCorrelationStatus.MATCHED:
                    if observed.sent_command is not None and _same_command_identity(
                        observed.sent_command,
                        active_sent,
                    ):
                        ack = observed.ack
                        events.append(
                            self._audit_event(
                                event_type=ControlAuditEventType.COMMAND_ACK,
                                command_name=active_sent.command_name,
                                cmd_id=active_sent.cmd_id,
                                node_ip=active_sent.node_ip,
                                node_id=active_sent.node_id,
                                cmd_seq=active_sent.cmd_seq,
                                nonce=active_sent.nonce,
                                attempt_index=attempt_index,
                                ack_stage=None if ack is None else ack.ack_stage,
                                status_code=None if ack is None else ack.status_code,
                                err_detail=None if ack is None else ack.err_detail,
                            )
                        )
                        return self._build_result(
                            command_name=active_sent.command_name,
                            cmd_id=active_sent.cmd_id,
                            node_ip=active_sent.node_ip,
                            node_id=active_sent.node_id,
                            cmd_seq=active_sent.cmd_seq,
                            nonce=active_sent.nonce,
                            attempt_count=attempt_count,
                            final_status=ControlTransactionFinalStatus.ACK_MATCHED,
                            ack=ack,
                            matched_sent_command=observed.sent_command,
                            tx_started=tx_started,
                            last_error=None,
                            events=events,
                        )

                    unmatched_ack_seen = True
                    events.append(
                        self._audit_event(
                            event_type=ControlAuditEventType.UNMATCHED_ACK_SEEN,
                            command_name=active_sent.command_name,
                            cmd_id=active_sent.cmd_id,
                            node_ip=active_sent.node_ip,
                            node_id=active_sent.node_id,
                            cmd_seq=active_sent.cmd_seq,
                            nonce=active_sent.nonce,
                            attempt_index=attempt_index,
                            detail="Se observo ACK matched para otro comando pendiente.",
                        )
                    )
                    continue

                if observed.status is AckCorrelationStatus.INVALID_ACK:
                    invalid_ack_seen = True
                    events.append(
                        self._audit_event(
                            event_type=ControlAuditEventType.INVALID_ACK_SEEN,
                            command_name=active_sent.command_name,
                            cmd_id=active_sent.cmd_id,
                            node_ip=active_sent.node_ip,
                            node_id=active_sent.node_id,
                            cmd_seq=active_sent.cmd_seq,
                            nonce=active_sent.nonce,
                            attempt_index=attempt_index,
                            detail=observed.parse_error_message or observed.parse_error_code,
                        )
                    )
                    continue

                if observed.status is AckCorrelationStatus.UNMATCHED_ACK:
                    unmatched_ack_seen = True
                    events.append(
                        self._audit_event(
                            event_type=ControlAuditEventType.UNMATCHED_ACK_SEEN,
                            command_name=active_sent.command_name,
                            cmd_id=active_sent.cmd_id,
                            node_ip=active_sent.node_ip,
                            node_id=active_sent.node_id,
                            cmd_seq=active_sent.cmd_seq,
                            nonce=active_sent.nonce,
                            attempt_index=attempt_index,
                            detail="ACK huerfano durante ventana de espera.",
                        )
                    )
                    continue

            self._pending_store.discard_sent_command(active_sent)

            if listener_runtime_error is not None:
                events.append(
                    self._audit_event(
                        event_type=ControlAuditEventType.LISTENER_NOT_RUNNING,
                        command_name=active_sent.command_name,
                        cmd_id=active_sent.cmd_id,
                        node_ip=active_sent.node_ip,
                        node_id=active_sent.node_id,
                        cmd_seq=active_sent.cmd_seq,
                        nonce=active_sent.nonce,
                        attempt_index=attempt_index,
                        detail=listener_runtime_error,
                    )
                )
                return self._build_result(
                    command_name=active_sent.command_name,
                    cmd_id=active_sent.cmd_id,
                    node_ip=active_sent.node_ip,
                    node_id=active_sent.node_id,
                    cmd_seq=active_sent.cmd_seq,
                    nonce=active_sent.nonce,
                    attempt_count=attempt_count,
                    final_status=ControlTransactionFinalStatus.LISTENER_NOT_RUNNING,
                    ack=None,
                    matched_sent_command=active_sent,
                    tx_started=tx_started,
                    last_error=listener_runtime_error,
                    events=events,
                )

            events.append(
                self._audit_event(
                    event_type=ControlAuditEventType.COMMAND_TIMEOUT,
                    command_name=active_sent.command_name,
                    cmd_id=active_sent.cmd_id,
                    node_ip=active_sent.node_ip,
                    node_id=active_sent.node_id,
                    cmd_seq=active_sent.cmd_seq,
                    nonce=active_sent.nonce,
                    attempt_index=attempt_index,
                    detail=f"Timeout de ACK en intento {attempt_index}.",
                )
            )
            last_error = (
                f"Timeout esperando ACK para {active_sent.command_name} "
                f"(attempt={attempt_index}, cmd_seq={active_sent.cmd_seq}, nonce=0x{active_sent.nonce:016X})."
            )

        if active_sent is None:
            return self._build_result(
                command_name=command_name,
                cmd_id=cmd_id,
                node_ip=node_ip,
                node_id=node_id,
                cmd_seq=None,
                nonce=None,
                attempt_count=attempt_count,
                final_status=ControlTransactionFinalStatus.TIMEOUT,
                ack=None,
                matched_sent_command=None,
                tx_started=tx_started,
                last_error=last_error or "Transaccion sin envio efectivo.",
                events=events,
            )

        if invalid_ack_seen:
            final_status = ControlTransactionFinalStatus.INVALID_ACK_SEEN
        elif unmatched_ack_seen:
            final_status = ControlTransactionFinalStatus.UNMATCHED_ACK_SEEN
        else:
            final_status = ControlTransactionFinalStatus.TIMEOUT

        return self._build_result(
            command_name=active_sent.command_name,
            cmd_id=active_sent.cmd_id,
            node_ip=active_sent.node_ip,
            node_id=active_sent.node_id,
            cmd_seq=active_sent.cmd_seq,
            nonce=active_sent.nonce,
            attempt_count=attempt_count,
            final_status=final_status,
            ack=None,
            matched_sent_command=active_sent,
            tx_started=tx_started,
            last_error=last_error,
            events=events,
        )

    def _ensure_listener_running(self) -> str | None:
        if self._ack_listener.is_running():
            return None
        try:
            self._ack_listener.start()
        except Exception as exc:
            return f"No se pudo iniciar ACK listener: {exc}"
        if not self._ack_listener.is_running():
            return "ACK listener no quedo en estado running."
        return None

    def _audit_event(
        self,
        *,
        event_type: str | ControlAuditEventType,
        command_name: str,
        cmd_id: int,
        node_ip: str,
        node_id: int,
        cmd_seq: int | None,
        nonce: int | None,
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
            utc_now_provider=self._utc_now_provider,
        )

    def _build_result(
        self,
        *,
        command_name: str,
        cmd_id: int,
        node_ip: str,
        node_id: int,
        cmd_seq: int | None,
        nonce: int | None,
        attempt_count: int,
        final_status: ControlTransactionFinalStatus,
        ack: ParsedOkuaAck | None,
        matched_sent_command: SentCommandLike | None,
        tx_started: float,
        last_error: str | None,
        events: list[ControlAuditEvent],
    ) -> ControlTransactionResult:
        elapsed_ms = max(0.0, (float(self._clock()) - tx_started) * 1000.0)
        return ControlTransactionResult(
            command_name=command_name,
            cmd_id=int(cmd_id) & 0xFF,
            node_ip=node_ip,
            node_id=int(node_id) & 0xFFFF,
            cmd_seq=cmd_seq,
            nonce=nonce,
            attempt_count=max(0, int(attempt_count)),
            final_status=final_status,
            ack=ack,
            matched_sent_command=matched_sent_command,
            elapsed_ms=elapsed_ms,
            last_error=last_error,
            events=tuple(events),
        )


def _validate_timeout_ms(value: int) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"ack_timeout_ms debe ser > 0, recibido {value}.")
    return parsed


def _validate_poll_interval_ms(value: int) -> int:
    parsed = int(value)
    if parsed < 0:
        raise ValueError(f"poll_interval_ms debe ser >= 0, recibido {value}.")
    return parsed


def _validate_max_retries(value: int) -> int:
    parsed = int(value)
    if parsed < 0:
        raise ValueError(f"max_retries debe ser >= 0, recibido {value}.")
    return parsed


def _assert_retry_identity(previous: SentOkuaCommand, resent: SentOkuaCommand) -> None:
    if resent.cmd_seq != previous.cmd_seq:
        raise RuntimeError(
            f"Retry invalido: cmd_seq cambio ({previous.cmd_seq} -> {resent.cmd_seq})."
        )
    if resent.nonce != previous.nonce:
        raise RuntimeError(
            f"Retry invalido: nonce cambio (0x{previous.nonce:016X} -> 0x{resent.nonce:016X})."
        )
    if resent.packet != previous.packet:
        raise RuntimeError("Retry invalido: packet bytes difieren del comando original.")


def _same_command_identity(left: SentCommandLike, right: SentCommandLike) -> bool:
    return (
        int(left.cmd_seq) & 0xFFFF,
        int(left.cmd_id) & 0xFF,
        int(left.nonce) & 0xFFFFFFFFFFFFFFFF,
    ) == (
        int(right.cmd_seq) & 0xFFFF,
        int(right.cmd_id) & 0xFF,
        int(right.nonce) & 0xFFFFFFFFFFFFFFFF,
    )
