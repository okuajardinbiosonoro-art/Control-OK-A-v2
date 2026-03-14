from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, Signal

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

        self._current_spec = self._resolve_spec()
        startup_message = (
            "Sesion lista para iniciar."
            if self._current_spec.is_valid
            else f"Sesion no iniciable: {self._current_spec.reason}"
        )
        self._snapshot = build_session_snapshot(
            initial_session_state(),
            self._current_spec,
            message=startup_message,
        )

    def get_snapshot(self) -> SessionSnapshot:
        return self._snapshot

    def get_state(self) -> SessionState:
        return self._snapshot.state

    def start_session(self) -> bool:
        transition = self._apply_transition(
            SessionEvent.REQUEST_START,
            message="Solicitud de inicio de sesion recibida.",
        )
        if not transition.is_valid:
            return False

        self._current_spec = self._resolve_spec()
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
        self._current_spec = self._resolve_spec()
        self._publish_snapshot(
            self.get_state(),
            self._current_spec,
            message="Estado de sesion reiniciado.",
            error=None,
        )
        return True

    def reload_config(self, cfg_provider_or_cfg: dict[str, Any] | ConfigProvider) -> SessionSnapshot:
        self._cfg_provider = self._normalize_cfg_provider(cfg_provider_or_cfg)
        self._current_spec = self._resolve_spec()
        self._publish_snapshot(
            self.get_state(),
            self._current_spec,
            message="Configuracion de sesion actualizada.",
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
        return build_session_request_from_profile(self._get_cfg())

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
