from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.session.session_models import (  # noqa: E402
    BackendKind,
    SessionState,
    build_session_request_from_profile,
    build_session_snapshot,
)


def test_serial_local_profile_resolves_serial_mode_and_backend() -> None:
    cfg = {"profile": {"active": "serial_local"}, "mode": None}
    spec = build_session_request_from_profile(cfg)
    assert spec.is_valid is True
    assert spec.mode == "serial"
    assert spec.backend is BackendKind.SERIAL


def test_udp_jardin_profile_resolves_udp_mode_and_backend() -> None:
    cfg = {"profile": {"active": "udp_jardin"}, "mode": None}
    spec = build_session_request_from_profile(cfg)
    assert spec.is_valid is True
    assert spec.mode == "udp"
    assert spec.backend is BackendKind.UDP


def test_lab_sim_profile_resolves_to_lab_backend() -> None:
    cfg = {"profile": {"active": "lab_sim"}, "mode": "udp"}
    spec = build_session_request_from_profile(cfg)
    assert spec.is_valid is True
    assert spec.profile_id == "lab_sim"
    assert spec.mode == "udp"
    assert spec.backend is BackendKind.LAB
    assert "runtime udp" in spec.reason.lower()

def test_invalid_or_missing_profile_returns_clear_reason() -> None:
    spec = build_session_request_from_profile({"mode": "invalid_mode"})
    assert spec.is_valid is False
    assert "no hay perfil activo valido" in spec.reason.lower()


def test_snapshot_exposes_start_stop_capabilities() -> None:
    spec = build_session_request_from_profile({"profile": {"active": "serial_local"}})

    idle_snapshot = build_session_snapshot(SessionState.IDLE, spec)
    running_snapshot = build_session_snapshot(SessionState.RUNNING, spec)

    assert idle_snapshot.can_start is True
    assert idle_snapshot.can_stop is False
    assert running_snapshot.can_start is False
    assert running_snapshot.can_stop is True
