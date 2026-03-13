from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from control_okua.core.session.session_models import SessionErrorInfo, SessionState


class SessionEvent(str, Enum):
    REQUEST_START = "request_start"
    BACKEND_STARTED = "backend_started"
    START_FAILED = "start_failed"
    REQUEST_STOP = "request_stop"
    BACKEND_STOPPED = "backend_stopped"
    STOP_FAILED = "stop_failed"
    RESET_ERROR = "reset_error"


@dataclass(frozen=True)
class SessionTransition:
    from_state: SessionState
    event: SessionEvent
    to_state: SessionState
    is_valid: bool
    message: str
    error: SessionErrorInfo | None = None


_TRANSITIONS: dict[SessionState, dict[SessionEvent, SessionState]] = {
    SessionState.IDLE: {
        SessionEvent.REQUEST_START: SessionState.STARTING,
    },
    SessionState.STARTING: {
        SessionEvent.BACKEND_STARTED: SessionState.RUNNING,
        SessionEvent.START_FAILED: SessionState.ERROR,
    },
    SessionState.RUNNING: {
        SessionEvent.REQUEST_STOP: SessionState.STOPPING,
    },
    SessionState.STOPPING: {
        SessionEvent.BACKEND_STOPPED: SessionState.IDLE,
        SessionEvent.STOP_FAILED: SessionState.ERROR,
    },
    SessionState.ERROR: {
        SessionEvent.RESET_ERROR: SessionState.IDLE,
    },
}


def initial_session_state() -> SessionState:
    return SessionState.IDLE


def can_transition(state: SessionState, event: SessionEvent) -> bool:
    return event in _TRANSITIONS.get(state, {})


def apply_session_event(
    state: SessionState,
    event: SessionEvent,
    *,
    detail: str | None = None,
) -> SessionTransition:
    next_state = _TRANSITIONS.get(state, {}).get(event)
    if next_state is None:
        return SessionTransition(
            from_state=state,
            event=event,
            to_state=state,
            is_valid=False,
            message="Transicion invalida para el estado actual.",
            error=SessionErrorInfo(
                code="invalid_transition",
                message="Evento no permitido en el estado actual.",
                detail=f"state={state.value}, event={event.value}",
            ),
        )

    error: SessionErrorInfo | None = None
    if event is SessionEvent.START_FAILED:
        error = SessionErrorInfo(
            code=SessionEvent.START_FAILED.value,
            message="Fallo al iniciar backend de sesion.",
            detail=detail,
        )
    elif event is SessionEvent.STOP_FAILED:
        error = SessionErrorInfo(
            code=SessionEvent.STOP_FAILED.value,
            message="Fallo al detener backend de sesion.",
            detail=detail,
        )

    return SessionTransition(
        from_state=state,
        event=event,
        to_state=next_state,
        is_valid=True,
        message=f"Transicion aplicada: {state.value} -> {next_state.value}",
        error=error,
    )


def allowed_events_for_state(state: SessionState) -> tuple[SessionEvent, ...]:
    events = _TRANSITIONS.get(state, {})
    return tuple(events.keys())
