from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.session import BackendKind, SessionSpec  # noqa: E402
from control_okua.services.backends import (  # noqa: E402
    SerialSessionBackend,
    UdpSessionBackend,
)
from control_okua.services.session_backend_factory import (  # noqa: E402
    BackendUnavailableError,
    SessionBackendFactory,
)


def _build_valid_spec(
    backend: BackendKind,
    *,
    profile_id: str,
    mode: str,
) -> SessionSpec:
    return SessionSpec(
        profile_id=profile_id,
        mode=mode,
        backend=backend,
        is_valid=True,
        reason="ok",
    )


def test_factory_returns_backend_for_serial_spec() -> None:
    spec = _build_valid_spec(BackendKind.SERIAL, profile_id="serial_local", mode="serial")
    cfg = {
        "profile": {"active": "serial_local"},
        "serial": {"port": "COM_TEST", "baudrate": 115200, "flush_ms": 5, "running_status": True},
        "midi": {"outputs": {"0": "loopMIDI Port 1"}, "backend": "rtmidi"},
    }
    backend = SessionBackendFactory(cfg_provider=lambda: cfg).build_backend_for_spec(spec)
    assert backend.kind is BackendKind.SERIAL
    assert isinstance(backend, SerialSessionBackend)
    availability = backend.availability()
    assert availability.is_implemented is True
    assert availability.is_available is True


def test_factory_returns_udp_backend_for_udp_spec() -> None:
    spec = _build_valid_spec(BackendKind.UDP, profile_id="udp_jardin", mode="udp")
    cfg = {
        "profile": {"active": "udp_jardin"},
        "udp": {"bind_ip": "127.0.0.1", "evt_port": 5005, "stat_port": 5006, "rcvbuf_bytes": 262144},
        "midi": {"outputs": {"0": "loopMIDI Port 1"}, "backend": "rtmidi"},
    }
    backend = SessionBackendFactory(cfg_provider=lambda: cfg).build_backend_for_spec(spec)
    availability = backend.availability()

    assert isinstance(backend, UdpSessionBackend)
    assert availability.is_implemented is True
    assert availability.is_available is True


def test_factory_routes_lab_udp_spec_to_udp_backend() -> None:
    spec = _build_valid_spec(BackendKind.LAB, profile_id="lab_sim", mode="udp")
    cfg = {
        "profile": {"active": "lab_sim"},
        "udp": {"bind_ip": "127.0.0.1", "evt_port": 5005, "stat_port": 5006, "rcvbuf_bytes": 262144},
        "midi": {"outputs": {"0": "loopMIDI Port 1"}, "backend": "rtmidi"},
    }
    backend = SessionBackendFactory(cfg_provider=lambda: cfg).build_backend_for_spec(spec)
    assert isinstance(backend, UdpSessionBackend)


def test_unavailable_backend_start_raises_clear_error_for_non_udp_lab() -> None:
    spec = _build_valid_spec(BackendKind.LAB, profile_id="lab_sim", mode="serial")
    backend = SessionBackendFactory().build_backend_for_spec(spec)

    try:
        backend.start(spec)
        assert False, "start() debía fallar para backend no implementado"
    except BackendUnavailableError as exc:
        assert "no se puede iniciar backend" in str(exc).lower()
