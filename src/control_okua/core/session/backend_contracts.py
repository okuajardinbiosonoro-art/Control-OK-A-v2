from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from control_okua.core.session.session_models import BackendKind, SessionSpec


@dataclass(frozen=True)
class BackendAvailability:
    is_implemented: bool
    is_available: bool
    reason: str = ""


class SessionBackendContract(Protocol):
    kind: BackendKind

    def start(self, spec: SessionSpec) -> None:
        ...

    def stop(self) -> None:
        ...

    def describe(self) -> str:
        ...

    def availability(self) -> BackendAvailability:
        ...
