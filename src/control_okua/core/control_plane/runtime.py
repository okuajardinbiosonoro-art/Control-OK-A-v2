from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol

from control_okua.services.control_transaction_service import (
    ControlTransactionFinalStatus,
    ControlTransactionResult,
    ControlTransactionService,
)

_DEFAULT_RECENT_RESULTS_LIMIT = 20


class ControlPlaneRuntimeError(RuntimeError):
    """Base runtime error for integrated F3 control-plane dispatch."""


class ControlPlaneRuntimeUnavailableError(ControlPlaneRuntimeError):
    """Raised when control-plane runtime is not available for current session state."""


class ControlPlaneNodeResolutionError(ControlPlaneRuntimeError):
    """Raised when node_id cannot be resolved to an IP in current runtime."""


class AckListenerLike(Protocol):
    @property
    def ack_port(self) -> int:
        ...

    @property
    def pending_store(self) -> object:
        ...

    def is_running(self) -> bool:
        ...

    def stop(self) -> None:
        ...


NodeIpResolver = Callable[[int], str | None]
RecordingSink = Callable[[str, dict[str, object]], None]
SessionIdProvider = Callable[[], str | None]
UtcNowProvider = Callable[[], datetime]


@dataclass(frozen=True)
class ControlPlaneNodeStatusSnapshot:
    node_id: int
    node_ip: str
    command_name: str
    cmd_seq: int | None
    nonce: int | None
    final_status: str
    ack_stage: int | None
    status_code: int | None
    err_detail: int | None
    last_error_message: str | None
    tx_started_at_utc: str | None
    tx_finished_at_utc: str | None
    ts_utc: str


@dataclass(frozen=True)
class ControlPlaneResultSummary:
    command_name: str
    node_id: int
    node_ip: str
    cmd_seq: int | None
    nonce: int | None
    attempt_count: int
    final_status: str
    ack_stage: int | None
    status_code: int | None
    err_detail: int | None
    elapsed_ms: float
    ts_utc: str


@dataclass(frozen=True)
class ControlPlaneRuntimeSnapshot:
    is_available: bool
    listener_active: bool
    ack_port: int
    pending_count: int
    commands_sent_total: int
    command_retry_total: int
    command_ack_total: int
    command_timeout_total: int
    invalid_ack_total: int
    unmatched_ack_total: int
    last_command: ControlPlaneResultSummary | None
    last_result: ControlPlaneResultSummary | None
    per_node_last_status: tuple[ControlPlaneNodeStatusSnapshot, ...]
    recent_results: tuple[ControlPlaneResultSummary, ...]


def build_unavailable_control_plane_snapshot(
    *,
    ack_port: int = 5008,
) -> ControlPlaneRuntimeSnapshot:
    return ControlPlaneRuntimeSnapshot(
        is_available=False,
        listener_active=False,
        ack_port=int(ack_port),
        pending_count=0,
        commands_sent_total=0,
        command_retry_total=0,
        command_ack_total=0,
        command_timeout_total=0,
        invalid_ack_total=0,
        unmatched_ack_total=0,
        last_command=None,
        last_result=None,
        per_node_last_status=tuple(),
        recent_results=tuple(),
    )


class ControlPlaneRuntime:
    """
    Integrated runtime facade for F3 command transactions.

    Responsibilities:
    - dispatch command by node_id using runtime node_id->ip resolution
    - keep compact runtime snapshot for diagnostics/UI
    - bridge control-plane audit events into session recording sink
    """

    def __init__(
        self,
        *,
        transaction_service: ControlTransactionService,
        ack_listener: AckListenerLike,
        node_ip_resolver: NodeIpResolver,
        recording_sink: RecordingSink | None = None,
        session_id_provider: SessionIdProvider | None = None,
        utc_now_provider: UtcNowProvider | None = None,
        recent_results_limit: int = _DEFAULT_RECENT_RESULTS_LIMIT,
    ) -> None:
        self._transaction_service = transaction_service
        self._ack_listener = ack_listener
        self._node_ip_resolver = node_ip_resolver
        self._recording_sink = recording_sink
        self._session_id_provider = session_id_provider
        self._utc_now = utc_now_provider or _utc_now
        self._recent_results_limit = max(1, int(recent_results_limit))

        self._commands_sent_total = 0
        self._command_retry_total = 0
        self._command_ack_total = 0
        self._command_timeout_total = 0
        self._invalid_ack_total = 0
        self._unmatched_ack_total = 0

        self._last_command: ControlPlaneResultSummary | None = None
        self._last_result: ControlPlaneResultSummary | None = None
        self._recent_results: deque[ControlPlaneResultSummary] = deque(
            maxlen=self._recent_results_limit
        )
        self._per_node_last_status: dict[int, ControlPlaneNodeStatusSnapshot] = {}

    def stop(self) -> None:
        try:
            self._ack_listener.stop()
        except Exception:
            pass

    def send_ping(
        self,
        *,
        node_id: int,
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
        source: str = "manual_ui",
    ) -> ControlTransactionResult:
        node_ip = self._resolve_node_ip(node_id)
        result = self._transaction_service.send_ping_and_wait_ack(
            node_ip,
            int(node_id),
            source=source,
            ack_timeout_ms=ack_timeout_ms,
            max_retries=max_retries,
        )
        self._consume_transaction_result(result)
        return result

    def send_request_stat_now(
        self,
        *,
        node_id: int,
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
        source: str = "manual_ui",
    ) -> ControlTransactionResult:
        node_ip = self._resolve_node_ip(node_id)
        result = self._transaction_service.send_request_stat_now_and_wait_ack(
            node_ip,
            int(node_id),
            source=source,
            ack_timeout_ms=ack_timeout_ms,
            max_retries=max_retries,
        )
        self._consume_transaction_result(result)
        return result

    def send_reboot_soft(
        self,
        *,
        node_id: int,
        delay_ms: int = 0,
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
        source: str = "manual_ui",
    ) -> ControlTransactionResult:
        node_ip = self._resolve_node_ip(node_id)
        result = self._transaction_service.send_reboot_soft_and_wait_ack(
            node_ip,
            int(node_id),
            delay_ms=delay_ms,
            source=source,
            ack_timeout_ms=ack_timeout_ms,
            max_retries=max_retries,
        )
        self._consume_transaction_result(result)
        return result

    def snapshot(self) -> ControlPlaneRuntimeSnapshot:
        pending_store = self._ack_listener.pending_store
        pending_count = int(getattr(pending_store, "pending_count", 0))
        listener_active = bool(self._ack_listener.is_running())
        return ControlPlaneRuntimeSnapshot(
            is_available=True,
            listener_active=listener_active,
            ack_port=int(self._ack_listener.ack_port),
            pending_count=max(0, pending_count),
            commands_sent_total=self._commands_sent_total,
            command_retry_total=self._command_retry_total,
            command_ack_total=self._command_ack_total,
            command_timeout_total=self._command_timeout_total,
            invalid_ack_total=self._invalid_ack_total,
            unmatched_ack_total=self._unmatched_ack_total,
            last_command=self._last_command,
            last_result=self._last_result,
            per_node_last_status=tuple(
                self._per_node_last_status[key]
                for key in sorted(self._per_node_last_status)
            ),
            recent_results=tuple(self._recent_results),
        )

    def active_node_ids(self) -> tuple[int, ...]:
        pending_store = self._ack_listener.pending_store
        list_pending = getattr(pending_store, "list_pending", None)
        if not callable(list_pending):
            return tuple()
        try:
            pending_rows = list_pending()
        except Exception:
            return tuple()

        active: set[int] = set()
        for row in pending_rows:
            sent_command = getattr(row, "sent_command", None)
            raw_node_id = getattr(sent_command, "node_id", None)
            try:
                node_id = int(raw_node_id)
            except (TypeError, ValueError):
                continue
            if node_id < 1 or node_id > 0xFFFF:
                continue
            active.add(node_id)
        return tuple(sorted(active))

    def _resolve_node_ip(self, node_id: int) -> str:
        try:
            resolved_id = int(node_id)
        except (TypeError, ValueError) as exc:
            raise ControlPlaneNodeResolutionError(
                f"node_id inválido para control-plane: {node_id!r}"
            ) from exc
        if resolved_id < 1 or resolved_id > 0xFFFF:
            raise ControlPlaneNodeResolutionError(
                f"node_id fuera de rango unicast: {node_id}"
            )

        try:
            node_ip = self._node_ip_resolver(resolved_id)
        except Exception as exc:
            raise ControlPlaneNodeResolutionError(str(exc)) from exc
        if not isinstance(node_ip, str) or not node_ip.strip():
            raise ControlPlaneNodeResolutionError(
                "No se pudo resolver IP para node_id en runtime actual."
            )
        return node_ip.strip()

    def _consume_transaction_result(self, result: ControlTransactionResult) -> None:
        tx_finished_dt = self._utc_now()
        elapsed_ms = max(0.0, float(result.elapsed_ms))
        tx_started_dt = tx_finished_dt - timedelta(milliseconds=elapsed_ms)
        tx_started_at_utc = _format_utc(tx_started_dt)
        tx_finished_at_utc = _format_utc(tx_finished_dt)
        summary = ControlPlaneResultSummary(
            command_name=result.command_name,
            node_id=int(result.node_id),
            node_ip=str(result.node_ip),
            cmd_seq=result.cmd_seq,
            nonce=result.nonce,
            attempt_count=int(result.attempt_count),
            final_status=result.final_status.value,
            ack_stage=None if result.ack is None else result.ack.ack_stage,
            status_code=None if result.ack is None else result.ack.status_code,
            err_detail=None if result.ack is None else result.ack.err_detail,
            elapsed_ms=elapsed_ms,
            ts_utc=tx_finished_at_utc,
        )
        self._last_command = summary
        self._last_result = summary
        self._recent_results.append(summary)
        self._per_node_last_status[int(result.node_id)] = ControlPlaneNodeStatusSnapshot(
            node_id=int(result.node_id),
            node_ip=str(result.node_ip),
            command_name=result.command_name,
            cmd_seq=result.cmd_seq,
            nonce=result.nonce,
            final_status=result.final_status.value,
            ack_stage=None if result.ack is None else result.ack.ack_stage,
            status_code=None if result.ack is None else result.ack.status_code,
            err_detail=None if result.ack is None else result.ack.err_detail,
            last_error_message=result.last_error,
            tx_started_at_utc=tx_started_at_utc,
            tx_finished_at_utc=tx_finished_at_utc,
            ts_utc=tx_finished_at_utc,
        )

        session_id = self._session_id_provider() if self._session_id_provider is not None else None
        for event in result.events:
            event_type = str(event.event_type)
            if event_type == "command_sent":
                self._commands_sent_total += 1
            elif event_type == "command_retry":
                self._command_retry_total += 1
            elif event_type == "command_ack":
                self._command_ack_total += 1
            elif event_type == "command_timeout":
                self._command_timeout_total += 1
            elif event_type == "invalid_ack_seen":
                self._invalid_ack_total += 1
            elif event_type == "unmatched_ack_seen":
                self._unmatched_ack_total += 1

            if event_type not in {
                "command_sent",
                "command_retry",
                "command_ack",
                "command_timeout",
            }:
                continue
            if self._recording_sink is None:
                continue

            payload: dict[str, object] = {
                "ts_utc": event.ts_utc,
                "session_id": session_id,
                "plane": "control_f3",
                "event_type": event_type,
                "node_id": event.node_id,
                "node_ip": event.node_ip,
                "cmd_id": event.cmd_id,
                "command_name": event.command_name,
                "cmd_seq": event.cmd_seq,
                "nonce": event.nonce,
                "attempt_index": event.attempt_index,
                "ack_stage": event.ack_stage,
                "status_code": event.status_code,
                "err_detail": event.err_detail,
                "detail": event.detail,
                "elapsed_ms": float(result.elapsed_ms),
                "final_status": result.final_status.value,
            }
            self._recording_sink(event_type, payload)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_utc(value: datetime) -> str:
    dt = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
