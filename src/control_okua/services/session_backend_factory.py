from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from control_okua.core.config.config_schema import validate_and_fix
from control_okua.core.session import (
    BackendAvailability,
    BackendKind,
    SessionBackendContract,
    SessionSpec,
)
from control_okua.services.backends import SerialSessionBackend, UdpSessionBackend


class SessionBackendError(RuntimeError):
    """Base error for session backend operations."""


class SessionStartError(SessionBackendError):
    """Raised when a backend cannot start for a valid session request."""


class SessionStopError(SessionBackendError):
    """Raised when a backend cannot stop safely."""


class BackendUnavailableError(SessionStartError):
    """Raised when a backend is not implemented or not available."""


@dataclass
class UnavailableSessionBackend:
    kind: BackendKind
    reason: str
    is_implemented: bool = False
    is_available: bool = False

    def start(self, spec: SessionSpec) -> None:
        raise BackendUnavailableError(
            f"No se puede iniciar backend '{self.kind.value}': {self.reason}"
        )

    def stop(self) -> None:
        raise SessionStopError(
            f"No se puede detener backend '{self.kind.value}': backend no iniciado."
        )

    def describe(self) -> str:
        return f"Unavailable backend ({self.kind.value})"

    def availability(self) -> BackendAvailability:
        return BackendAvailability(
            is_implemented=self.is_implemented,
            is_available=self.is_available,
            reason=self.reason,
        )


BackendBuilder = Callable[[SessionSpec], SessionBackendContract]
ConfigProvider = Callable[[], dict[str, Any]]


class SessionBackendFactory:
    """Factory used by SessionController to resolve a backend from SessionSpec."""

    _DEFAULT_UNAVAILABLE_REASONS: dict[BackendKind, str] = {
        BackendKind.LAB: "Lab backend aún no implementado en este ticket.",
    }

    def __init__(
        self,
        builders: dict[BackendKind, BackendBuilder] | None = None,
        cfg_provider: ConfigProvider | None = None,
    ) -> None:
        self._builders = builders.copy() if builders else {}
        self._cfg_provider = cfg_provider or (lambda: {})

    def register_builder(self, backend_kind: BackendKind, builder: BackendBuilder) -> None:
        self._builders[backend_kind] = builder

    def build_backend_for_spec(self, spec: SessionSpec) -> SessionBackendContract:
        if not spec.is_valid:
            raise SessionStartError(f"SessionSpec invalido: {spec.reason}")
        if spec.backend is None:
            raise SessionStartError("SessionSpec no define backend esperado.")

        builder = self._builders.get(spec.backend)
        if builder is not None:
            return builder(spec)

        if spec.backend is BackendKind.SERIAL:
            cfg = self._get_effective_cfg()
            return SerialSessionBackend(cfg)
        if spec.backend is BackendKind.UDP:
            cfg = self._get_effective_cfg()
            return UdpSessionBackend(cfg)
        if spec.backend is BackendKind.LAB and spec.mode == "udp":
            cfg = self._get_effective_cfg()
            return UdpSessionBackend(cfg)

        reason = self._DEFAULT_UNAVAILABLE_REASONS.get(
            spec.backend,
            f"Backend '{spec.backend.value}' no implementado.",
        )
        return UnavailableSessionBackend(kind=spec.backend, reason=reason)

    def _get_effective_cfg(self) -> dict[str, Any]:
        try:
            cfg = self._cfg_provider()
        except Exception:
            cfg = {}
        raw_cfg = cfg if isinstance(cfg, dict) else {}
        effective_cfg, _warnings = validate_and_fix(raw_cfg)
        return effective_cfg
