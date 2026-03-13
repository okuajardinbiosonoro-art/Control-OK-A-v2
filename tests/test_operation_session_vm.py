from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.viewmodels.main_window_vm import (  # noqa: E402
    build_session_action_state,
    build_session_backend_summary,
    build_session_message_summary,
    build_session_status_summary,
)
from control_okua.core.session import (  # noqa: E402
    BackendKind,
    SessionSpec,
    SessionState,
    build_session_snapshot,
)


def _build_spec(backend: BackendKind = BackendKind.SERIAL, is_valid: bool = True) -> SessionSpec:
    return SessionSpec(
        profile_id="serial_local",
        mode="serial",
        backend=backend,
        is_valid=is_valid,
        reason="ok" if is_valid else "invalid",
    )


def test_session_status_summary_idle() -> None:
    snapshot = build_session_snapshot(SessionState.IDLE, _build_spec())
    assert build_session_status_summary(snapshot) == "Estado de sesión: inactiva"


def test_session_status_summary_starting() -> None:
    snapshot = build_session_snapshot(SessionState.STARTING, _build_spec())
    assert build_session_status_summary(snapshot) == "Estado de sesión: iniciando"


def test_session_status_summary_error() -> None:
    snapshot = build_session_snapshot(SessionState.ERROR, _build_spec())
    assert build_session_status_summary(snapshot) == "Estado de sesión: en error"


def test_session_backend_summary_is_human_readable() -> None:
    snapshot = build_session_snapshot(SessionState.IDLE, _build_spec(BackendKind.UDP))
    assert build_session_backend_summary(snapshot) == "Backend esperado: UDP"


def test_session_action_state_from_snapshot() -> None:
    idle_snapshot = build_session_snapshot(SessionState.IDLE, _build_spec())
    running_snapshot = build_session_snapshot(SessionState.RUNNING, _build_spec())
    error_snapshot = build_session_snapshot(SessionState.ERROR, _build_spec())

    idle_actions = build_session_action_state(idle_snapshot)
    running_actions = build_session_action_state(running_snapshot)
    error_actions = build_session_action_state(error_snapshot)

    assert idle_actions.can_start_session is True
    assert idle_actions.can_stop_session is False
    assert idle_actions.can_reset_error is False
    assert idle_actions.can_edit_configuration is True

    assert running_actions.can_start_session is False
    assert running_actions.can_stop_session is True
    assert running_actions.can_reset_error is False
    assert running_actions.can_edit_configuration is False

    assert error_actions.can_reset_error is True
    assert error_actions.can_edit_configuration is True


def test_session_message_summary_is_readable() -> None:
    snapshot = build_session_snapshot(
        SessionState.ERROR,
        _build_spec(),
        message="No se pudo iniciar sesión: backend no implementado.",
    )
    summary = build_session_message_summary(snapshot)
    assert "Mensaje actual:" in summary
    assert "backend no implementado" in summary.lower()
