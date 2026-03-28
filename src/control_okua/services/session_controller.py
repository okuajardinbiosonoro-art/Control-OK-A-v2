from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
import time
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal

from control_okua.core.control_plane.runtime import (
    ControlPlaneNodeStatusSnapshot,
    ControlPlaneRuntime,
    ControlPlaneRuntimeSnapshot,
    ControlPlaneRuntimeUnavailableError,
    build_unavailable_control_plane_snapshot,
)
from control_okua.core.control_plane.runtime_snapshot import (
    DEFAULT_CONTROL_PLANE_RESOLUTION_STALE_S,
    ControlPlaneNodeSnapshot,
    ControlPlaneNodeSnapshotInput,
    ControlPlaneRebootVerificationState,
    ControlPlaneResolvedIp,
    build_control_plane_node_snapshot,
    build_control_plane_node_snapshots,
)
from control_okua.core.control_plane.pending import PendingCommandStore
from control_okua.core.node_identity_policy import resolve_node_identity
from control_okua.core.preflight import (
    PreflightReport,
    ReadinessLevel,
    run_preflight_checks,
)
from control_okua.core.recording import (
    JsonlSessionRecorder,
    SessionLogEventType,
    SessionReportAccumulator,
)
from control_okua.core.session import (
    BackendKind,
    SessionErrorInfo,
    SessionEvent,
    SessionSnapshot,
    SessionSpec,
    SessionState,
    apply_session_event,
    build_session_request_from_profile,
    build_session_snapshot,
    can_transition,
    initial_session_state,
)
from control_okua.services.session_backend_factory import (
    BackendUnavailableError,
    SessionBackendFactory,
)
from control_okua.services.ack_listener import AckListenerService
from control_okua.services.cmd_service import CmdService
from control_okua.services.control_transaction_service import (
    ControlTransactionResult,
    ControlTransactionService,
)

ConfigProvider = Callable[[], dict[str, Any]]
RecorderBuilder = Callable[[dict[str, Any]], JsonlSessionRecorder]
_CONTROL_PLANE_IP_STALE_AFTER_S = DEFAULT_CONTROL_PLANE_RESOLUTION_STALE_S


class SessionController(QObject):
    session_state_changed = Signal(str)
    session_snapshot_changed = Signal(object)
    session_error = Signal(str)
    session_message = Signal(str)
    preflight_report_changed = Signal(object)

    def __init__(
        self,
        cfg_provider_or_cfg: dict[str, Any] | ConfigProvider,
        backend_factory: SessionBackendFactory | None = None,
        recorder_builder: RecorderBuilder | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._cfg_provider = self._normalize_cfg_provider(cfg_provider_or_cfg)
        self._backend_factory = backend_factory or SessionBackendFactory(
            cfg_provider=self._get_cfg
        )
        self._recorder_builder = recorder_builder or self._default_recorder_builder
        self._active_backend = None
        self._active_recorder: JsonlSessionRecorder | None = None
        self._report_accumulator: SessionReportAccumulator | None = None
        self._active_recording_paths: object | None = None
        self._last_recording_paths: object | None = None
        self._control_plane_runtime: ControlPlaneRuntime | None = None
        self._control_plane_node_ip_cache: dict[int, ControlPlaneResolvedIp] = {}
        self._control_plane_reboot_verification_cache: dict[int, ControlPlaneRebootVerificationState] = {}
        self._control_plane_tx_cache: dict[int, ControlPlaneNodeStatusSnapshot] = {}

        initial_cfg = self._get_cfg()
        self._last_preflight_report = self._run_preflight(initial_cfg, emit_signal=False)
        self._current_spec = self._resolve_spec_from_cfg(initial_cfg)
        startup_message = self._build_startup_message(self._current_spec, self._last_preflight_report)
        self._snapshot = build_session_snapshot(
            initial_session_state(),
            self._current_spec,
            message=startup_message,
        )

    def get_snapshot(self) -> SessionSnapshot:
        return self._snapshot

    def get_state(self) -> SessionState:
        return self._snapshot.state

    def get_last_preflight_report(self) -> PreflightReport:
        return self._last_preflight_report

    def get_last_recording_artifacts(self) -> object | None:
        return self._last_recording_paths

    def get_active_recording_session_id(self) -> str | None:
        recorder = self._active_recorder
        if recorder is None:
            return None
        return recorder.session_id

    def get_backend_runtime_snapshot(self) -> object | None:
        backend = self._active_backend
        if backend is None:
            return None
        runtime_snapshot = getattr(backend, "runtime_snapshot", None)
        if callable(runtime_snapshot):
            try:
                snapshot = runtime_snapshot()
                self._refresh_control_plane_node_ip_cache(snapshot)
                return snapshot
            except Exception:
                return None
        return None

    def get_node_registry_summary(self, now: float | None = None) -> object | None:
        backend = self._active_backend
        if backend is None:
            return None
        reader = getattr(backend, "get_node_registry_summary", None)
        if callable(reader):
            try:
                return reader(now=now)
            except Exception:
                return None
        return None

    def get_node_snapshots(self, now: float | None = None) -> list[object]:
        backend = self._active_backend
        if backend is None:
            return []
        reader = getattr(backend, "get_node_snapshots", None)
        if callable(reader):
            try:
                snapshots = reader(now=now)
            except Exception:
                return []
            if isinstance(snapshots, list):
                return snapshots
            return []
        return []

    def get_node_snapshot(self, node_id: int, now: float | None = None) -> object | None:
        backend = self._active_backend
        if backend is None:
            return None
        reader = getattr(backend, "get_node_snapshot", None)
        if callable(reader):
            try:
                return reader(node_id=node_id, now=now)
            except Exception:
                return None
        return None

    def is_control_plane_available(self) -> bool:
        runtime = self._control_plane_runtime
        if runtime is None:
            return False
        return self.get_state() is SessionState.RUNNING and self._is_udp_runtime_spec(self._current_spec)

    def get_control_plane_runtime_snapshot(self) -> ControlPlaneRuntimeSnapshot:
        runtime = self._control_plane_runtime
        if runtime is None:
            return build_unavailable_control_plane_snapshot()
        try:
            return runtime.snapshot()
        except Exception:
            return build_unavailable_control_plane_snapshot(ack_port=5008)

    def get_control_plane_node_snapshots(self, now: float | None = None) -> list[ControlPlaneNodeSnapshot]:
        resolved_now = self._resolve_monotonic_now(now)
        self._refresh_control_plane_node_ip_cache()

        runtime_snapshot = self.get_control_plane_runtime_snapshot()
        self._absorb_runtime_control_plane_status(runtime_snapshot)
        node_status_map = dict(self._control_plane_tx_cache)
        active_node_ids = self._active_control_plane_node_ids()

        node_snapshot_list = self.get_node_snapshots(now=resolved_now)
        node_snapshots_by_id: dict[int, object] = {}
        node_ids: set[int] = set()
        for snapshot in node_snapshot_list:
            raw_node_id = getattr(snapshot, "node_id", None)
            try:
                node_id = int(raw_node_id)
            except (TypeError, ValueError):
                continue
            if node_id < 1 or node_id > 0xFFFF:
                continue
            node_ids.add(node_id)
            node_snapshots_by_id[node_id] = snapshot

        node_ids.update(self._control_plane_node_ip_cache.keys())
        node_ids.update(self._control_plane_tx_cache.keys())
        node_ids.update(active_node_ids)
        node_ids.update(self._control_plane_reboot_verification_cache.keys())

        sources: list[ControlPlaneNodeSnapshotInput] = []
        for node_id in sorted(node_ids):
            sources.append(
                self._build_control_plane_node_snapshot_input(
                    node_id=node_id,
                    now_monotonic=resolved_now,
                    runtime_node_snapshot=node_snapshots_by_id.get(node_id),
                    runtime_control_status=node_status_map.get(node_id),
                    active_node_ids=active_node_ids,
                )
            )

        return list(
            build_control_plane_node_snapshots(
                sources,
                now_monotonic=resolved_now,
                resolution_stale_after_s=_CONTROL_PLANE_IP_STALE_AFTER_S,
            )
        )

    def get_control_plane_node_snapshot(
        self,
        node_id: int,
        now: float | None = None,
    ) -> ControlPlaneNodeSnapshot | None:
        try:
            resolved_node_id = int(node_id)
        except (TypeError, ValueError):
            return None
        if resolved_node_id < 1 or resolved_node_id > 0xFFFF:
            return None

        resolved_now = self._resolve_monotonic_now(now)
        self._refresh_control_plane_node_ip_cache()
        runtime_snapshot = self.get_control_plane_runtime_snapshot()
        self._absorb_runtime_control_plane_status(runtime_snapshot)
        active_node_ids = self._active_control_plane_node_ids()
        runtime_node_snapshot = self.get_node_snapshot(node_id=resolved_node_id, now=resolved_now)

        source = self._build_control_plane_node_snapshot_input(
            node_id=resolved_node_id,
            now_monotonic=resolved_now,
            runtime_node_snapshot=runtime_node_snapshot,
            runtime_control_status=self._control_plane_tx_cache.get(resolved_node_id),
            active_node_ids=active_node_ids,
        )
        try:
            return build_control_plane_node_snapshot(
                source,
                now_monotonic=resolved_now,
                resolution_stale_after_s=_CONTROL_PLANE_IP_STALE_AFTER_S,
            )
        except Exception:
            return None

    def record_control_plane_reboot_verification(
        self,
        *,
        node_id: int,
        status: str,
        summary: str,
        updated_at_utc: str | None = None,
    ) -> None:
        try:
            resolved_node_id = int(node_id)
        except (TypeError, ValueError):
            return
        if resolved_node_id < 1 or resolved_node_id > 0xFFFF:
            return
        status_text = str(status).strip()
        summary_text = str(summary).strip()
        if not status_text and not summary_text:
            return
        if not status_text:
            status_text = "unknown"
        if not summary_text:
            summary_text = status_text
        updated_text = None
        if updated_at_utc is not None:
            cleaned = str(updated_at_utc).strip()
            if cleaned:
                updated_text = cleaned
        self._control_plane_reboot_verification_cache[resolved_node_id] = (
            ControlPlaneRebootVerificationState(
                status=status_text,
                summary=summary_text,
                updated_at_utc=updated_text,
            )
        )

    def send_control_ping(
        self,
        *,
        node_id: int,
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
        source: str = "manual_ui",
    ) -> ControlTransactionResult:
        runtime = self._ensure_control_plane_runtime()
        result = runtime.send_ping(
            node_id=node_id,
            ack_timeout_ms=ack_timeout_ms,
            max_retries=max_retries,
            source=source,
        )
        self._record_control_plane_transaction_result(result=result, runtime=runtime)
        return result

    def send_control_request_stat_now(
        self,
        *,
        node_id: int,
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
        source: str = "manual_ui",
    ) -> ControlTransactionResult:
        runtime = self._ensure_control_plane_runtime()
        result = runtime.send_request_stat_now(
            node_id=node_id,
            ack_timeout_ms=ack_timeout_ms,
            max_retries=max_retries,
            source=source,
        )
        self._record_control_plane_transaction_result(result=result, runtime=runtime)
        return result

    def send_control_reboot_soft(
        self,
        *,
        node_id: int,
        delay_ms: int = 0,
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
        source: str = "manual_ui",
    ) -> ControlTransactionResult:
        runtime = self._ensure_control_plane_runtime()
        result = runtime.send_reboot_soft(
            node_id=node_id,
            delay_ms=delay_ms,
            ack_timeout_ms=ack_timeout_ms,
            max_retries=max_retries,
            source=source,
        )
        self._record_control_plane_transaction_result(result=result, runtime=runtime)
        return result

    def send_control_set_stat_rate(
        self,
        *,
        node_id: int,
        stat_rate_ms: int,
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
        source: str = "manual_ui",
    ) -> ControlTransactionResult:
        runtime = self._ensure_control_plane_runtime()
        result = runtime.send_set_stat_rate(
            node_id=node_id,
            stat_rate_ms=stat_rate_ms,
            ack_timeout_ms=ack_timeout_ms,
            max_retries=max_retries,
            source=source,
        )
        self._record_control_plane_transaction_result(result=result, runtime=runtime)
        return result

    def send_control_set_throttle(
        self,
        *,
        node_id: int,
        throttle_percent: int,
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
        source: str = "manual_ui",
    ) -> ControlTransactionResult:
        runtime = self._ensure_control_plane_runtime()
        result = runtime.send_set_throttle(
            node_id=node_id,
            throttle_percent=throttle_percent,
            ack_timeout_ms=ack_timeout_ms,
            max_retries=max_retries,
            source=source,
        )
        self._record_control_plane_transaction_result(result=result, runtime=runtime)
        return result

    def send_control_ota_check_now(
        self,
        *,
        node_id: int,
        rollout_token: int,
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
        source: str = "ota_manual_ui",
    ) -> ControlTransactionResult:
        runtime = self._ensure_control_plane_runtime()
        result = runtime.send_ota_check_now(
            node_id=node_id,
            rollout_token=rollout_token,
            ack_timeout_ms=ack_timeout_ms,
            max_retries=max_retries,
            source=source,
        )
        self._record_control_plane_transaction_result(result=result, runtime=runtime)
        return result

    def start_session(self) -> bool:
        transition = self._apply_transition(
            SessionEvent.REQUEST_START,
            message="Solicitud de inicio de sesion recibida.",
        )
        if not transition.is_valid:
            return False
        self._shutdown_control_plane_runtime()
        self._control_plane_node_ip_cache.clear()
        self._control_plane_reboot_verification_cache.clear()
        self._control_plane_tx_cache.clear()

        cfg = self._get_cfg()
        attempt_spec = self._resolve_spec_from_cfg(cfg)
        self._maybe_open_recording(cfg)
        self._record_event(
            SessionLogEventType.SESSION_STARTED,
            {
                "reason": "start_session_called",
                "profile_id": attempt_spec.profile_id,
                "mode": attempt_spec.mode,
                "backend_kind": attempt_spec.backend.value
                if attempt_spec.backend is not None
                else None,
            },
        )
        preflight_report = self._run_preflight(cfg, emit_signal=True)
        self._record_event(
            SessionLogEventType.PREFLIGHT_REPORT,
            self._preflight_payload(preflight_report),
        )
        self._current_spec = self._resolve_spec_from_cfg(cfg)

        if preflight_report.readiness is ReadinessLevel.BLOCKED:
            detail = self._preflight_block_reason(preflight_report)
            self._apply_transition(
                SessionEvent.START_FAILED,
                detail=detail,
                spec=self._current_spec,
                message=f"No se puede iniciar la sesion: {detail}",
            )
            return False

        if preflight_report.readiness is ReadinessLevel.READY_WITH_WARNINGS:
            self.session_message.emit(
                "La sesion esta lista con advertencias; intentando iniciar backend..."
            )

        if not self._current_spec.is_valid:
            self._apply_transition(
                SessionEvent.START_FAILED,
                detail=self._current_spec.reason,
                spec=self._current_spec,
                message=f"No se pudo iniciar sesion: {self._current_spec.reason}",
            )
            return False

        backend_kind = self._current_spec.backend
        if backend_kind is None:
            detail = "SessionSpec no define backend esperado."
            self._apply_transition(
                SessionEvent.START_FAILED,
                detail=detail,
                spec=self._current_spec,
                message=f"No se pudo iniciar sesion: {detail}",
            )
            return False

        try:
            backend = None
            backend = self._backend_factory.build_backend_for_spec(self._current_spec)
            self._attach_recording_sink_to_backend(backend)
            availability = backend.availability()
            if not availability.is_implemented:
                raise BackendUnavailableError(
                    availability.reason
                    or f"Backend '{backend_kind.value}' no implementado."
                )
            if not availability.is_available:
                raise BackendUnavailableError(
                    availability.reason
                    or f"Backend '{backend_kind.value}' no disponible."
                )
            backend.start(self._current_spec)
        except Exception as exc:
            if backend is not None:
                self._record_backend_runtime_snapshot(backend, reason="start_failed")
            self._active_backend = None
            self._shutdown_control_plane_runtime()
            self._apply_transition(
                SessionEvent.START_FAILED,
                detail=str(exc),
                spec=self._current_spec,
                message=f"No se pudo iniciar sesion: {exc}",
            )
            return False

        self._active_backend = backend
        self._record_backend_runtime_snapshot(backend, reason="backend_started")
        self._record_node_summary_snapshot(backend, reason="backend_started")
        self._apply_transition(
            SessionEvent.BACKEND_STARTED,
            spec=self._current_spec,
            message=f"Sesion iniciada: {backend.describe()}",
        )
        self._maybe_activate_control_plane_runtime()
        return True

    def stop_session(self) -> bool:
        if not can_transition(self.get_state(), SessionEvent.REQUEST_STOP):
            self.session_message.emit(
                f"Stop ignorado en estado '{self.get_state().value}'."
            )
            return False

        transition = self._apply_transition(
            SessionEvent.REQUEST_STOP,
            message="Solicitud de detencion de sesion recibida.",
        )
        if not transition.is_valid:
            return False

        if self._active_backend is None:
            detail = "No hay backend activo para detener."
            self._apply_transition(
                SessionEvent.STOP_FAILED,
                detail=detail,
                message=f"No se pudo detener sesion: {detail}",
            )
            return False

        try:
            self._record_backend_runtime_snapshot(self._active_backend, reason="before_stop")
            self._record_node_summary_snapshot(self._active_backend, reason="before_stop")
            self._active_backend.stop()
        except Exception as exc:
            self._shutdown_control_plane_runtime()
            self._apply_transition(
                SessionEvent.STOP_FAILED,
                detail=str(exc),
                message=f"No se pudo detener sesion: {exc}",
            )
            return False

        self._record_event(
            SessionLogEventType.SESSION_STOPPED,
            {
                "reason": "stop_session_called",
                "state_before": SessionState.STOPPING.value,
            },
        )
        self._active_backend = None
        self._shutdown_control_plane_runtime()
        self._control_plane_node_ip_cache.clear()
        self._control_plane_reboot_verification_cache.clear()
        self._control_plane_tx_cache.clear()
        self._current_spec = self._resolve_spec()
        self._apply_transition(
            SessionEvent.BACKEND_STOPPED,
            spec=self._current_spec,
            message="Sesion detenida.",
        )
        return True

    def reset_error(self) -> bool:
        transition = self._apply_transition(
            SessionEvent.RESET_ERROR,
            message="Solicitud de reinicio de error recibida.",
        )
        if not transition.is_valid:
            return False

        self._close_recording_if_open(
            final_state=SessionState.IDLE.value,
            summary="Recording cerrado por reset_error.",
        )
        self._shutdown_control_plane_runtime()
        self._control_plane_node_ip_cache.clear()
        self._control_plane_reboot_verification_cache.clear()
        self._control_plane_tx_cache.clear()
        self._active_backend = None
        cfg = self._get_cfg()
        preflight_report = self._run_preflight(cfg, emit_signal=True)
        self._current_spec = self._resolve_spec_from_cfg(cfg)
        message = "Estado de sesion reiniciado."
        if preflight_report.readiness is ReadinessLevel.BLOCKED:
            reason = self._preflight_block_reason(preflight_report)
            message = f"Estado de sesion reiniciado. Preflight bloqueado: {reason}"
        elif preflight_report.readiness is ReadinessLevel.READY_WITH_WARNINGS:
            message = "Estado de sesion reiniciado. Configuracion lista con advertencias."

        self._publish_snapshot(
            self.get_state(),
            self._current_spec,
            message=message,
            error=None,
        )
        return True

    def reload_config(self, cfg_provider_or_cfg: dict[str, Any] | ConfigProvider) -> SessionSnapshot:
        self._cfg_provider = self._normalize_cfg_provider(cfg_provider_or_cfg)
        self._shutdown_control_plane_runtime()
        self._control_plane_node_ip_cache.clear()
        self._control_plane_reboot_verification_cache.clear()
        self._control_plane_tx_cache.clear()
        cfg = self._get_cfg()
        preflight_report = self._run_preflight(cfg, emit_signal=True)
        self._current_spec = self._resolve_spec_from_cfg(cfg)
        message = "Configuracion de sesion actualizada."
        if preflight_report.readiness is ReadinessLevel.BLOCKED:
            message = (
                "Configuracion de sesion actualizada. "
                f"Preflight bloqueado: {self._preflight_block_reason(preflight_report)}"
            )
        elif preflight_report.readiness is ReadinessLevel.READY_WITH_WARNINGS:
            message = "Configuracion de sesion actualizada. Lista con advertencias."

        self._publish_snapshot(
            self.get_state(),
            self._current_spec,
            message=message,
            error=self._snapshot.error,
        )
        return self._snapshot

    def _apply_transition(
        self,
        event: SessionEvent,
        *,
        detail: str | None = None,
        message: str | None = None,
        spec: SessionSpec | None = None,
    ):
        transition = apply_session_event(self.get_state(), event, detail=detail)
        next_spec = spec or self._current_spec
        self._publish_snapshot(
            transition.to_state,
            next_spec,
            message=message or transition.message,
            error=transition.error,
        )
        self._record_event(
            SessionLogEventType.SESSION_STATE_CHANGED,
            {
                "event": transition.event.value,
                "from_state": transition.from_state.value,
                "to_state": transition.to_state.value,
                "is_valid": bool(transition.is_valid),
                "message": message or transition.message,
                "profile_id": next_spec.profile_id,
                "mode": next_spec.mode,
                "backend_kind": next_spec.backend.value if next_spec.backend is not None else None,
            },
        )
        if transition.error is not None:
            self._record_event(
                SessionLogEventType.SESSION_ERROR,
                {
                    "code": transition.error.code,
                    "message": transition.error.message,
                    "detail": transition.error.detail,
                },
            )
        if transition.event in {
            SessionEvent.START_FAILED,
            SessionEvent.STOP_FAILED,
            SessionEvent.BACKEND_STOPPED,
        }:
            self._close_recording_if_open(
                final_state=transition.to_state.value,
                summary=message or transition.message,
            )
        return transition

    def _publish_snapshot(
        self,
        state: SessionState,
        spec: SessionSpec,
        *,
        message: str,
        error: SessionErrorInfo | None,
    ) -> None:
        self._snapshot = build_session_snapshot(
            state,
            spec,
            message=message,
            error=error,
        )
        self.session_state_changed.emit(self._snapshot.state.value)
        self.session_snapshot_changed.emit(self._snapshot)
        self.session_message.emit(self._snapshot.message)
        if error is not None:
            rendered_error = error.message if error.detail is None else f"{error.message}: {error.detail}"
            self.session_error.emit(rendered_error)

    def _resolve_spec(self) -> SessionSpec:
        return self._resolve_spec_from_cfg(self._get_cfg())

    @staticmethod
    def _resolve_spec_from_cfg(cfg: dict[str, Any]) -> SessionSpec:
        return build_session_request_from_profile(cfg)

    @staticmethod
    def _preflight_block_reason(report: PreflightReport) -> str:
        for finding in report.findings:
            if finding.is_blocking:
                return finding.message
        for finding in report.findings:
            if finding.severity.value == "error":
                return finding.message
        return "la sesion no esta lista segun el preflight."

    @staticmethod
    def _build_startup_message(spec: SessionSpec, report: PreflightReport) -> str:
        if report.readiness is ReadinessLevel.BLOCKED:
            return f"Sesion no iniciable: {SessionController._preflight_block_reason(report)}"
        if report.readiness is ReadinessLevel.READY_WITH_WARNINGS:
            return "Sesion lista con advertencias."
        if spec.is_valid:
            return "Sesion lista para iniciar."
        return f"Sesion no iniciable: {spec.reason}"

    def _run_preflight(self, cfg: dict[str, Any], *, emit_signal: bool) -> PreflightReport:
        report = run_preflight_checks(cfg)
        self._last_preflight_report = report
        if emit_signal:
            self.preflight_report_changed.emit(report)
        return report

    def _get_cfg(self) -> dict[str, Any]:
        try:
            cfg = self._cfg_provider()
        except Exception:
            return {}
        return cfg if isinstance(cfg, dict) else {}

    @staticmethod
    def _normalize_cfg_provider(cfg_provider_or_cfg: dict[str, Any] | ConfigProvider) -> ConfigProvider:
        if callable(cfg_provider_or_cfg):
            return cfg_provider_or_cfg
        if isinstance(cfg_provider_or_cfg, dict):
            return lambda: cfg_provider_or_cfg
        raise TypeError("cfg_provider_or_cfg debe ser dict o callable sin argumentos.")

    def _maybe_open_recording(self, cfg: dict[str, Any]) -> None:
        if not self._is_recording_enabled(cfg):
            return
        if self._active_recorder is not None:
            self._close_recording_if_open(
                final_state=self.get_state().value,
                summary="Recording previo cerrado antes de abrir una nueva sesion.",
            )
        try:
            recorder = self._recorder_builder(cfg)
            paths = recorder.open_session()
        except Exception as exc:
            self.session_message.emit(f"Recording deshabilitado por error al abrir artefactos: {exc}")
            self._active_recorder = None
            self._report_accumulator = None
            self._active_recording_paths = None
            return

        self._active_recorder = recorder
        self._active_recording_paths = paths
        self._last_recording_paths = None
        attempt_spec = self._resolve_spec_from_cfg(cfg)
        self._report_accumulator = SessionReportAccumulator(
            session_id=recorder.session_id or "",
            profile_id=attempt_spec.profile_id,
            mode=attempt_spec.mode,
            backend_kind=attempt_spec.backend.value if attempt_spec.backend is not None else None,
            started_at_utc=recorder.opened_at_utc,
            start_monotonic=recorder.start_monotonic,
            clock=time.monotonic,
        )

    @staticmethod
    def _is_recording_enabled(cfg: dict[str, Any]) -> bool:
        logging_cfg = cfg.get("logging")
        if not isinstance(logging_cfg, dict):
            return False
        enabled = logging_cfg.get("enabled")
        return enabled is True

    @staticmethod
    def _default_recorder_builder(cfg: dict[str, Any]) -> JsonlSessionRecorder:
        logging_cfg = cfg.get("logging")
        folder = None
        if isinstance(logging_cfg, dict):
            raw_folder = logging_cfg.get("folder")
            if isinstance(raw_folder, str) and raw_folder.strip():
                folder = raw_folder.strip()
        if folder is None:
            base_dir = Path("logs") / "sessions"
        else:
            base_dir = Path(folder) / "sessions"
        return JsonlSessionRecorder(base_sessions_dir=base_dir)

    @staticmethod
    def _is_udp_runtime_spec(spec: SessionSpec) -> bool:
        if spec.mode != "udp":
            return False
        return spec.backend in {BackendKind.UDP, BackendKind.LAB}

    def _maybe_activate_control_plane_runtime(self) -> None:
        if not self._is_udp_runtime_spec(self._current_spec):
            self._shutdown_control_plane_runtime()
            return
        try:
            self._ensure_control_plane_runtime()
        except Exception as exc:
            self.session_message.emit(f"Control-plane no disponible en esta sesión: {exc}")

    def _ensure_control_plane_runtime(self) -> ControlPlaneRuntime:
        if self.get_state() is not SessionState.RUNNING:
            raise ControlPlaneRuntimeUnavailableError(
                "Control-plane requiere sesión RUNNING."
            )
        if not self._is_udp_runtime_spec(self._current_spec):
            raise ControlPlaneRuntimeUnavailableError(
                "Control-plane F3 solo está disponible para sesión UDP/LAB."
            )
        runtime = self._control_plane_runtime
        if runtime is not None:
            return runtime
        runtime = self._build_control_plane_runtime()
        self._control_plane_runtime = runtime
        return runtime

    def _build_control_plane_runtime(self) -> ControlPlaneRuntime:
        pending_store = PendingCommandStore()
        ack_listener = AckListenerService(pending_store=pending_store)
        cmd_service = CmdService()
        transaction_service = ControlTransactionService(
            cmd_service=cmd_service,
            ack_listener=ack_listener,
            pending_store=pending_store,
        )
        return ControlPlaneRuntime(
            transaction_service=transaction_service,
            ack_listener=ack_listener,
            node_ip_resolver=self._resolve_node_ip_for_control,
            recording_sink=self._record_event,
            session_id_provider=self.get_active_recording_session_id,
        )

    def _shutdown_control_plane_runtime(self) -> None:
        runtime = self._control_plane_runtime
        self._control_plane_runtime = None
        if runtime is None:
            return
        runtime.stop()

    def _refresh_control_plane_node_ip_cache(self, runtime_snapshot: object | None = None) -> None:
        snapshot = runtime_snapshot
        if snapshot is None:
            backend = self._active_backend
            if backend is None:
                return
            runtime_reader = getattr(backend, "runtime_snapshot", None)
            if not callable(runtime_reader):
                return
            try:
                snapshot = runtime_reader()
            except Exception:
                return
        if snapshot is None:
            return
        for holder_name in ("last_evt", "last_stat"):
            holder = getattr(snapshot, holder_name, None)
            if holder is None:
                continue
            raw_node_id = getattr(holder, "node_id", None)
            raw_source_ip = getattr(holder, "source_ip", None)
            try:
                node_id = int(raw_node_id)
            except (TypeError, ValueError):
                continue
            if node_id < 1 or node_id > 0xFFFF:
                continue
            if not isinstance(raw_source_ip, str):
                continue
            source_ip = raw_source_ip.strip()
            if not source_ip:
                continue
            observed_at = self._coerce_monotonic_ts(
                getattr(holder, "received_ts", None),
                fallback=time.monotonic(),
            )
            self._control_plane_node_ip_cache[node_id] = ControlPlaneResolvedIp(
                node_id=node_id,
                ip=source_ip,
                observed_at_monotonic=observed_at,
            )

    def _resolve_node_ip_for_control(self, node_id: int) -> str | None:
        try:
            resolved_node_id = int(node_id)
        except (TypeError, ValueError):
            return None
        if resolved_node_id < 1 or resolved_node_id > 0xFFFF:
            return None

        cached = self._control_plane_node_ip_cache.get(resolved_node_id)
        resolved_ip = self._extract_resolved_ip(cached)
        if resolved_ip is not None:
            return resolved_ip

        self._refresh_control_plane_node_ip_cache()
        cached = self._control_plane_node_ip_cache.get(resolved_node_id)
        resolved_ip = self._extract_resolved_ip(cached)
        if resolved_ip is not None:
            return resolved_ip

        # UDP runtime only exposes source IP on last EVT/STAT summaries.
        # Wait briefly for next packet so the target node can refresh cache.
        deadline = time.monotonic() + 0.9
        while time.monotonic() < deadline:
            self._refresh_control_plane_node_ip_cache()
            cached = self._control_plane_node_ip_cache.get(resolved_node_id)
            resolved_ip = self._extract_resolved_ip(cached)
            if resolved_ip is not None:
                return resolved_ip
            time.sleep(0.05)

        return None

    def _build_control_plane_runtime_status_map(
        self,
        runtime_snapshot: ControlPlaneRuntimeSnapshot,
    ) -> dict[int, ControlPlaneNodeStatusSnapshot]:
        rows = getattr(runtime_snapshot, "per_node_last_status", tuple())
        if not isinstance(rows, tuple):
            return {}
        mapped: dict[int, ControlPlaneNodeStatusSnapshot] = {}
        for row in rows:
            raw_node_id = getattr(row, "node_id", None)
            try:
                node_id = int(raw_node_id)
            except (TypeError, ValueError):
                continue
            if node_id < 1 or node_id > 0xFFFF:
                continue
            if not isinstance(row, ControlPlaneNodeStatusSnapshot):
                continue
            mapped[node_id] = row
        return mapped

    def _absorb_runtime_control_plane_status(
        self,
        runtime_snapshot: ControlPlaneRuntimeSnapshot,
    ) -> None:
        mapped = self._build_control_plane_runtime_status_map(runtime_snapshot)
        for row in mapped.values():
            self._upsert_control_plane_tx_status(row)

    def _record_control_plane_transaction_result(
        self,
        *,
        result: ControlTransactionResult,
        runtime: ControlPlaneRuntime | None = None,
    ) -> None:
        node_id = self._as_int_or_none(getattr(result, "node_id", None))
        if node_id is None or node_id < 1 or node_id > 0xFFFF:
            return

        fallback_row = self._build_control_plane_status_row_from_result(result)
        runtime_snapshot = self._safe_control_plane_runtime_snapshot(runtime)
        if runtime_snapshot is not None:
            mapped = self._build_control_plane_runtime_status_map(runtime_snapshot)
            runtime_row = mapped.get(node_id)
            if runtime_row is not None:
                self._upsert_control_plane_tx_status(runtime_row)
        self._upsert_control_plane_tx_status(fallback_row)

    def _safe_control_plane_runtime_snapshot(
        self,
        runtime: ControlPlaneRuntime | None,
    ) -> ControlPlaneRuntimeSnapshot | None:
        if runtime is None:
            return None
        reader = getattr(runtime, "snapshot", None)
        if not callable(reader):
            return None
        try:
            snapshot = reader()
        except Exception:
            return None
        if not isinstance(snapshot, ControlPlaneRuntimeSnapshot):
            return None
        return snapshot

    def _build_control_plane_status_row_from_result(
        self,
        result: ControlTransactionResult,
    ) -> ControlPlaneNodeStatusSnapshot:
        now_utc = datetime.now(timezone.utc)
        elapsed_ms = max(0.0, float(getattr(result, "elapsed_ms", 0.0)))
        started_utc = now_utc - timedelta(milliseconds=elapsed_ms)
        ack = getattr(result, "ack", None)
        return ControlPlaneNodeStatusSnapshot(
            node_id=int(result.node_id),
            node_ip=str(result.node_ip),
            command_name=str(result.command_name),
            cmd_seq=self._as_int_or_none(getattr(result, "cmd_seq", None)),
            nonce=self._as_int_or_none(getattr(result, "nonce", None)),
            final_status=str(getattr(result.final_status, "value", result.final_status)),
            ack_stage=self._as_int_or_none(None if ack is None else getattr(ack, "ack_stage", None)),
            status_code=self._as_int_or_none(None if ack is None else getattr(ack, "status_code", None)),
            err_detail=self._as_int_or_none(None if ack is None else getattr(ack, "err_detail", None)),
            last_error_message=self._as_text_or_none(getattr(result, "last_error", None)),
            tx_started_at_utc=self._format_utc_iso(started_utc),
            tx_finished_at_utc=self._format_utc_iso(now_utc),
            ts_utc=self._format_utc_iso(now_utc),
        )

    def _upsert_control_plane_tx_status(
        self,
        candidate: ControlPlaneNodeStatusSnapshot,
    ) -> None:
        node_id = self._as_int_or_none(getattr(candidate, "node_id", None))
        if node_id is None or node_id < 1 or node_id > 0xFFFF:
            return
        existing = self._control_plane_tx_cache.get(node_id)
        if existing is None:
            self._control_plane_tx_cache[node_id] = candidate
            return
        self._control_plane_tx_cache[node_id] = self._select_effective_control_plane_status(
            existing,
            candidate,
        )

    @classmethod
    def _select_effective_control_plane_status(
        cls,
        existing: ControlPlaneNodeStatusSnapshot,
        candidate: ControlPlaneNodeStatusSnapshot,
    ) -> ControlPlaneNodeStatusSnapshot:
        existing_seq = cls._as_int_or_none(existing.cmd_seq)
        candidate_seq = cls._as_int_or_none(candidate.cmd_seq)
        if existing_seq is not None and candidate_seq is not None:
            if existing_seq != candidate_seq:
                if cls._is_cmd_seq_newer(candidate_seq, existing_seq):
                    return candidate
                return existing
        elif existing_seq is None and candidate_seq is not None:
            return candidate
        elif existing_seq is not None and candidate_seq is None:
            return existing

        existing_score = cls._control_plane_status_score(existing)
        candidate_score = cls._control_plane_status_score(candidate)
        if candidate_score > existing_score:
            return candidate
        if candidate_score < existing_score:
            return existing

        existing_finished = cls._as_text_or_none(existing.tx_finished_at_utc)
        candidate_finished = cls._as_text_or_none(candidate.tx_finished_at_utc)
        if existing_finished is not None and candidate_finished is not None:
            if candidate_finished >= existing_finished:
                return candidate
            return existing
        if existing_finished is None and candidate_finished is not None:
            return candidate
        if existing_finished is not None and candidate_finished is None:
            return existing
        return candidate

    @classmethod
    def _control_plane_status_score(cls, row: ControlPlaneNodeStatusSnapshot) -> int:
        score = 0
        if cls._as_text_or_none(row.command_name) is not None:
            score += 2
        if cls._as_int_or_none(row.cmd_seq) is not None:
            score += 4
        if cls._as_int_or_none(row.nonce) is not None:
            score += 3
        if cls._as_text_or_none(row.final_status) is not None:
            score += 5
        if cls._as_int_or_none(row.ack_stage) is not None:
            score += 2
        if cls._as_int_or_none(row.status_code) is not None:
            score += 1
        if cls._as_int_or_none(row.err_detail) is not None:
            score += 1
        if cls._as_text_or_none(row.last_error_message) is not None:
            score += 1
        if cls._as_text_or_none(row.tx_started_at_utc) is not None:
            score += 1
        if cls._as_text_or_none(row.tx_finished_at_utc) is not None:
            score += 2
        return score

    @staticmethod
    def _is_cmd_seq_newer(candidate: int, reference: int) -> bool:
        left = int(candidate) & 0xFFFF
        right = int(reference) & 0xFFFF
        diff = (left - right) & 0xFFFF
        return 0 < diff < 0x8000

    @staticmethod
    def _format_utc_iso(value: datetime) -> str:
        return (
            value.astimezone(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

    def _active_control_plane_node_ids(self) -> set[int]:
        runtime = self._control_plane_runtime
        if runtime is None:
            return set()
        reader = getattr(runtime, "active_node_ids", None)
        if not callable(reader):
            return set()
        try:
            raw_ids = reader()
        except Exception:
            return set()
        node_ids: set[int] = set()
        for raw_node_id in raw_ids:
            try:
                node_id = int(raw_node_id)
            except (TypeError, ValueError):
                continue
            if node_id < 1 or node_id > 0xFFFF:
                continue
            node_ids.add(node_id)
        return node_ids

    def _build_control_plane_node_snapshot_input(
        self,
        *,
        node_id: int,
        now_monotonic: float,
        runtime_node_snapshot: object | None,
        runtime_control_status: object | None,
        active_node_ids: set[int],
    ) -> ControlPlaneNodeSnapshotInput:
        _ = now_monotonic
        identity = resolve_node_identity(node_id)
        ip_entry = self._control_plane_node_ip_cache.get(node_id)
        reboot_state = self._control_plane_reboot_verification_cache.get(node_id)

        last_state_flags = self._as_int_or_none(
            None if runtime_node_snapshot is None else getattr(runtime_node_snapshot, "last_state_flags", None)
        )
        last_boot_marker = self._resolve_boot_marker(last_state_flags)

        status_row = runtime_control_status
        return ControlPlaneNodeSnapshotInput(
            node_id=node_id,
            label=identity.node_label,
            resolved_ip=None if ip_entry is None else ip_entry.ip,
            resolution_observed_at_monotonic=None
            if ip_entry is None
            else ip_entry.observed_at_monotonic,
            last_seen_pc_ts=self._as_float_or_none(
                None if runtime_node_snapshot is None else getattr(runtime_node_snapshot, "last_seen_pc_ts", None)
            ),
            transaction_active=node_id in active_node_ids,
            last_command_name=self._as_text_or_none(
                None if status_row is None else getattr(status_row, "command_name", None)
            ),
            last_cmd_seq=self._as_int_or_none(
                None if status_row is None else getattr(status_row, "cmd_seq", None)
            ),
            last_nonce=self._as_int_or_none(
                None if status_row is None else getattr(status_row, "nonce", None)
            ),
            last_final_status=self._as_text_or_none(
                None if status_row is None else getattr(status_row, "final_status", None)
            ),
            last_ack_stage=self._as_int_or_none(
                None if status_row is None else getattr(status_row, "ack_stage", None)
            ),
            last_status_code=self._as_int_or_none(
                None if status_row is None else getattr(status_row, "status_code", None)
            ),
            last_err_detail=self._as_int_or_none(
                None if status_row is None else getattr(status_row, "err_detail", None)
            ),
            last_error_message=self._as_text_or_none(
                None if status_row is None else getattr(status_row, "last_error_message", None)
            ),
            last_tx_started_at=self._as_text_or_none(
                None if status_row is None else getattr(status_row, "tx_started_at_utc", None)
            ),
            last_tx_finished_at=self._as_text_or_none(
                None if status_row is None else getattr(status_row, "tx_finished_at_utc", None)
            ),
            last_reboot_verification_status=None if reboot_state is None else reboot_state.status,
            last_reboot_verification_summary=None if reboot_state is None else reboot_state.summary,
            last_uptime_s=self._as_int_or_none(
                None if runtime_node_snapshot is None else getattr(runtime_node_snapshot, "last_uptime_s", None)
            ),
            last_reset_reason=self._as_int_or_none(
                None if runtime_node_snapshot is None else getattr(runtime_node_snapshot, "reset_reason", None)
            ),
            last_boot_marker=last_boot_marker,
            message=None if reboot_state is None else reboot_state.summary,
        )

    @staticmethod
    def _resolve_monotonic_now(now: float | None) -> float:
        if now is None:
            return float(time.monotonic())
        try:
            return float(now)
        except (TypeError, ValueError):
            return float(time.monotonic())

    @staticmethod
    def _coerce_monotonic_ts(raw_value: object, *, fallback: float) -> float:
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return float(fallback)
        if value < 0:
            return float(fallback)
        return value

    @staticmethod
    def _resolve_boot_marker(state_flags: int | None) -> int | None:
        if state_flags is None:
            return None
        if state_flags < 0:
            return None
        if state_flags > 0xFF:
            return None
        return (state_flags >> 4) & 0x0F

    @staticmethod
    def _as_int_or_none(raw_value: object) -> int | None:
        try:
            if raw_value is None:
                return None
            return int(raw_value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_float_or_none(raw_value: object) -> float | None:
        try:
            if raw_value is None:
                return None
            return float(raw_value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_text_or_none(raw_value: object) -> str | None:
        if raw_value is None:
            return None
        text = str(raw_value).strip()
        if not text:
            return None
        return text

    @staticmethod
    def _extract_resolved_ip(entry: ControlPlaneResolvedIp | None) -> str | None:
        if entry is None:
            return None
        ip = str(entry.ip).strip()
        if not ip:
            return None
        return ip

    def _record_event(
        self,
        event_type: SessionLogEventType | str,
        payload: dict[str, Any],
    ) -> None:
        recorder = self._active_recorder
        accumulator = self._report_accumulator
        if recorder is None:
            return
        try:
            sanitized_payload = self._to_json_payload(payload)
            record = recorder.write_event(event_type, sanitized_payload)
            if accumulator is not None:
                accumulator.observe_record(record)
        except Exception as exc:
            self.session_message.emit(f"Error escribiendo evento de recording ({event_type}): {exc}")

    def _close_recording_if_open(self, *, final_state: str, summary: str) -> None:
        recorder = self._active_recorder
        if recorder is None:
            return
        accumulator = self._report_accumulator
        report = None
        try:
            self._record_event(
                SessionLogEventType.REPORT_GENERATED,
                {
                    "final_state": final_state,
                    "summary": summary,
                },
            )
            if accumulator is not None:
                report = accumulator.build_close_report(
                    final_state=final_state,
                    summary=summary,
                )
            closed_paths = recorder.close_session(report=report)
            self._last_recording_paths = closed_paths
        except Exception as exc:
            self.session_message.emit(f"Error cerrando recording de sesion: {exc}")
        finally:
            self._active_recorder = None
            self._report_accumulator = None
            self._active_recording_paths = None

    def _preflight_payload(self, report: PreflightReport) -> dict[str, Any]:
        findings: list[dict[str, Any]] = []
        for finding in report.findings:
            findings.append(
                {
                    "code": finding.code.value,
                    "severity": finding.severity.value,
                    "message": finding.message,
                    "is_blocking": bool(finding.is_blocking),
                    "details": self._to_json_payload(finding.details),
                }
            )
        return {
            "readiness": report.readiness.value,
            "blocking_count": int(report.blocking_count),
            "warning_count": int(report.warning_count),
            "info_count": int(report.info_count),
            "summary": report.summary,
            "can_start": bool(report.can_start),
            "profile_id": report.profile_id,
            "derived_mode": report.derived_mode,
            "backend_kind": report.backend_kind,
            "session_spec_valid": bool(report.session_spec_valid),
            "findings": findings,
        }

    def _attach_recording_sink_to_backend(self, backend: object) -> None:
        setter = getattr(backend, "set_record_event_sink", None)
        if callable(setter):
            try:
                setter(self._on_backend_record_event)
            except Exception:
                return

    def _on_backend_record_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self._record_event(event_type, payload)

    def _record_backend_runtime_snapshot(self, backend: object, *, reason: str) -> None:
        runtime_snapshot = getattr(backend, "runtime_snapshot", None)
        if not callable(runtime_snapshot):
            return
        try:
            snapshot = runtime_snapshot()
        except Exception:
            return
        self._record_event(
            SessionLogEventType.BACKEND_RUNTIME,
            {
                "reason": reason,
                "snapshot": self._to_json_payload(snapshot),
            },
        )

    def _record_node_summary_snapshot(self, backend: object, *, reason: str) -> None:
        summary_reader = getattr(backend, "get_node_registry_summary", None)
        if not callable(summary_reader):
            return
        try:
            summary = summary_reader()
        except Exception:
            return
        if summary is None:
            return
        self._record_event(
            SessionLogEventType.NODE_SUMMARY,
            {
                "reason": reason,
                "summary": self._to_json_payload(summary),
            },
        )

    def _to_json_payload(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, dict):
            return {str(key): self._to_json_payload(raw) for key, raw in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._to_json_payload(item) for item in value]
        if is_dataclass(value):
            return self._to_json_payload(asdict(value))
        return str(value)
