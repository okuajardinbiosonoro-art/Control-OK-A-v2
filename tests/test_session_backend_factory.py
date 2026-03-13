from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.session import BackendKind, SessionSpec  # noqa: E402
from control_okua.services.session_backend_factory import (  # noqa: E402
    BackendUnavailableError,
    SessionBackendFactory,
    UnavailableSessionBackend,
)


def _build_valid_spec(backend: BackendKind) -> SessionSpec:
    mode = "serial" if backend is BackendKind.SERIAL else "udp"
    return SessionSpec(
        profile_id="serial_local",
        mode=mode,
        backend=backend,
        is_valid=True,
        reason="ok",
    )


def test_factory_returns_backend_for_serial_spec() -> None:
    spec = _build_valid_spec(BackendKind.SERIAL)
    backend = SessionBackendFactory().build_backend_for_spec(spec)
    assert backend.kind is BackendKind.SERIAL
    assert isinstance(backend, UnavailableSessionBackend)


def test_unavailable_backend_reports_honest_availability() -> None:
    spec = _build_valid_spec(BackendKind.UDP)
    backend = SessionBackendFactory().build_backend_for_spec(spec)
    availability = backend.availability()

    assert availability.is_implemented is False
    assert availability.is_available is False
    assert availability.reason != ""


def test_unavailable_backend_start_raises_clear_error() -> None:
    spec = _build_valid_spec(BackendKind.LAB)
    backend = SessionBackendFactory().build_backend_for_spec(spec)

    try:
        backend.start(spec)
        assert False, "start() debía fallar para backend no implementado"
    except BackendUnavailableError as exc:
        assert "no se puede iniciar backend" in str(exc).lower()
