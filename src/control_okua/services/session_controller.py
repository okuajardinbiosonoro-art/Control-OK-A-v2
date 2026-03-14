from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, Signal

from control_okua.core.preflight import (
    PreflightReport,
    ReadinessLevel,
    run_preflight_checks,
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
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._cfg_provider = self._normalize_cfg_provider(cfg_provider_or_cfg)
        self._backend_factory = backend_factory or SessionBackendFactory()
        self._active_backend = None

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

    def start_session(self) -> bool:
        transition = self._apply_transition(
            SessionEvent.REQUEST_START,
            message="Solicitud de inicio de sesion recibida.",
        )
        if not transition.is_valid:
            return False

        cfg = self._get_cfg()
        preflight_report = self._run_preflight(cfg, emit_signal=True)
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
            backend = self._backend_factory.build_backend_for_spec(self._current_spec)
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
            self._active_backend = None
            self._apply_transition(
                SessionEvent.START_FAILED,
                detail=str(exc),
                spec=self._current_spec,
                message=f"No se pudo iniciar sesion: {exc}",
            )
            return False

        self._active_backend = backend
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
            self._active_backend.stop()
        except Exception as exc:
            self._apply_transition(
                SessionEvent.STOP_FAILED,
                detail=str(exc),
                message=f"No se pudo detener sesion: {exc}",
            )
            return False

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
