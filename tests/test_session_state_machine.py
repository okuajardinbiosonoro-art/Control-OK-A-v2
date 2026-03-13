from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.session.session_models import SessionState  # noqa: E402
from control_okua.core.session.session_state_machine import (  # noqa: E402
    SessionEvent,
    apply_session_event,
    can_transition,
    initial_session_state,
)


def test_initial_state_is_idle() -> None:
    assert initial_session_state() is SessionState.IDLE


def test_request_start_transitions_idle_to_starting() -> None:
    transition = apply_session_event(SessionState.IDLE, SessionEvent.REQUEST_START)
    assert transition.is_valid is True
    assert transition.to_state is SessionState.STARTING


def test_backend_started_transitions_starting_to_running() -> None:
    transition = apply_session_event(SessionState.STARTING, SessionEvent.BACKEND_STARTED)
    assert transition.is_valid is True
    assert transition.to_state is SessionState.RUNNING


def test_start_failed_transitions_starting_to_error() -> None:
    transition = apply_session_event(
        SessionState.STARTING,
        SessionEvent.START_FAILED,
        detail="serial port unavailable",
    )
    assert transition.is_valid is True
    assert transition.to_state is SessionState.ERROR
    assert transition.error is not None
    assert transition.error.code == "start_failed"


def test_request_stop_transitions_running_to_stopping() -> None:
    transition = apply_session_event(SessionState.RUNNING, SessionEvent.REQUEST_STOP)
    assert transition.is_valid is True
    assert transition.to_state is SessionState.STOPPING


def test_backend_stopped_transitions_stopping_to_idle() -> None:
    transition = apply_session_event(SessionState.STOPPING, SessionEvent.BACKEND_STOPPED)
    assert transition.is_valid is True
    assert transition.to_state is SessionState.IDLE


def test_reset_error_transitions_error_to_idle() -> None:
    transition = apply_session_event(SessionState.ERROR, SessionEvent.RESET_ERROR)
    assert transition.is_valid is True
    assert transition.to_state is SessionState.IDLE


def test_invalid_transition_is_detected_without_crashing() -> None:
    assert can_transition(SessionState.IDLE, SessionEvent.BACKEND_STARTED) is False
    transition = apply_session_event(SessionState.IDLE, SessionEvent.BACKEND_STARTED)
    assert transition.is_valid is False
    assert transition.to_state is SessionState.IDLE
    assert transition.error is not None
    assert transition.error.code == "invalid_transition"
