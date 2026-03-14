from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
import time
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal

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

ConfigProvider = Callable[[], dict[str, Any]]
RecorderBuilder = Callable[[dict[str, Any]], JsonlSessionRecorder]


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
                return runtime_snapshot()
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

    def start_session(self) -> bool:
        transition = self._apply_transition(
            SessionEvent.REQUEST_START,
            message="Solicitud de inicio de sesion recibida.",
        )
        if not transition.is_valid:
            return False

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
