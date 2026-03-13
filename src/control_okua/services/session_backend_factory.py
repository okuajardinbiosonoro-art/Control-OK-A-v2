from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from control_okua.core.session import (
    BackendAvailability,
    BackendKind,
    SessionBackendContract,
    SessionSpec,
)


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


class SessionBackendFactory:
    """Factory used by SessionController to resolve a backend from SessionSpec."""

    _DEFAULT_UNAVAILABLE_REASONS: dict[BackendKind, str] = {
        BackendKind.SERIAL: "Serial backend aún no implementado en este ticket.",
        BackendKind.UDP: "UDP backend aún no implementado en este ticket.",
        BackendKind.LAB: "Lab backend aún no implementado en este ticket.",
    }

    def __init__(self, builders: dict[BackendKind, BackendBuilder] | None = None) -> None:
        self._builders = builders.copy() if builders else {}

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

        reason = self._DEFAULT_UNAVAILABLE_REASONS.get(
            spec.backend,
            f"Backend '{spec.backend.value}' no implementado.",
        )
        return UnavailableSessionBackend(kind=spec.backend, reason=reason)
