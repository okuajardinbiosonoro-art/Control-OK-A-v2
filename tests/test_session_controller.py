from __future__ import annotations

from dataclasses import dataclass
import sys
from pathlib import Path
from typing import Any, Callable


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.preflight import PreflightReport, ReadinessLevel  # noqa: E402
from control_okua.core.session import (  # noqa: E402
    BackendAvailability,
    BackendKind,
    SessionSpec,
    SessionState,
)
from control_okua.services.session_controller import SessionController  # noqa: E402


def _build_cfg(profile_id: str | None, mode: str | None = None) -> dict[str, Any]:
    return {
        "profile": {"active": profile_id},
        "mode": mode,
    }


@dataclass
class _FakeBackend:
    kind: BackendKind
    implemented: bool = False
    available: bool = False
    reason: str = "backend no implementado"
    start_calls: int = 0
    stop_calls: int = 0

    def start(self, spec: SessionSpec) -> None:
        self.start_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1

    def describe(self) -> str:
        return f"Fake backend ({self.kind.value})"

    def availability(self) -> BackendAvailability:
        return BackendAvailability(
            is_implemented=self.implemented,
            is_available=self.available,
            reason=self.reason,
        )


class _RecordingBackendFactory:
    def __init__(self, backend: _FakeBackend, on_build: Callable[[], None] | None = None) -> None:
        self._backend = backend
        self._on_build = on_build
        self.build_calls = 0

    def build_backend_for_spec(self, spec: SessionSpec) -> _FakeBackend:
        self.build_calls += 1
        if self._on_build is not None:
            self._on_build()
        return self._backend


def test_controller_starts_in_idle() -> None:
    controller = SessionController(_build_cfg("serial_local", "serial"))
    assert controller.get_state() is SessionState.IDLE


def test_get_snapshot_is_coherent_on_init() -> None:
    controller = SessionController(_build_cfg("serial_local", "serial"))
    snapshot = controller.get_snapshot()
    preflight = controller.get_last_preflight_report()

    assert snapshot.state is SessionState.IDLE
    assert snapshot.active_profile == "serial_local"
    assert snapshot.mode == "serial"
    assert snapshot.can_start is True
    assert snapshot.can_stop is False
    assert preflight.readiness in {ReadinessLevel.READY, ReadinessLevel.READY_WITH_WARNINGS}


def test_start_session_runs_preflight_before_backend_resolution() -> None:
    observed_reports: list[PreflightReport] = []
    holder: dict[str, SessionController] = {}
    backend = _FakeBackend(
        kind=BackendKind.SERIAL,
        implemented=False,
        available=False,
        reason="Serial backend aun no implementado.",
    )

    def _capture_report() -> None:
        observed_reports.append(holder["controller"].get_last_preflight_report())

    backend_factory = _RecordingBackendFactory(backend=backend, on_build=_capture_report)
    controller = SessionController(_build_cfg("serial_local", "serial"), backend_factory=backend_factory)
    holder["controller"] = controller
    controller.start_session()

    assert backend_factory.build_calls == 1
    assert len(observed_reports) == 1
    assert observed_reports[0].readiness is not ReadinessLevel.BLOCKED


def test_start_session_with_preflight_blocked_goes_to_error() -> None:
    backend = _FakeBackend(kind=BackendKind.SERIAL, implemented=True, available=True, reason="ok")
    backend_factory = _RecordingBackendFactory(backend=backend)
    controller = SessionController(_build_cfg(None, "invalid_mode"), backend_factory=backend_factory)

    result = controller.start_session()

    assert result is False
    assert controller.get_state() is SessionState.ERROR
    assert controller.get_snapshot().error is not None
    assert controller.get_last_preflight_report().readiness is ReadinessLevel.BLOCKED
    assert "no se puede iniciar la sesion" in controller.get_snapshot().message.lower()
    assert backend_factory.build_calls == 0
    assert backend.start_calls == 0


def test_preflight_ready_with_warnings_continues_to_backend_factory() -> None:
    backend = _FakeBackend(
        kind=BackendKind.SERIAL,
        implemented=False,
        available=False,
        reason="Serial backend aun no implementado.",
    )
    backend_factory = _RecordingBackendFactory(backend=backend)
    controller = SessionController(_build_cfg("serial_local", "serial"), backend_factory=backend_factory)

    result = controller.start_session()

    assert result is False
    assert controller.get_state() is SessionState.ERROR
    assert controller.get_last_preflight_report().readiness is ReadinessLevel.READY_WITH_WARNINGS
    assert backend_factory.build_calls == 1


def test_backend_unavailable_remains_honest_even_when_preflight_passes() -> None:
    backend = _FakeBackend(
        kind=BackendKind.SERIAL,
        implemented=False,
        available=False,
        reason="Backend SERIAL aun no implementado.",
    )
    backend_factory = _RecordingBackendFactory(backend=backend)
    controller = SessionController(_build_cfg("serial_local", "serial"), backend_factory=backend_factory)

    result = controller.start_session()

    assert result is False
    assert controller.get_state() is SessionState.ERROR
    assert controller.get_last_preflight_report().readiness is ReadinessLevel.READY_WITH_WARNINGS
    assert "backend serial aun no implementado" in controller.get_snapshot().message.lower()


def test_last_preflight_report_is_accessible_after_start_attempt() -> None:
    controller = SessionController(_build_cfg("serial_local", "serial"))
    controller.start_session()

    report = controller.get_last_preflight_report()
    assert isinstance(report, PreflightReport)
    assert report.summary.strip() != ""


def test_reset_error_returns_to_idle_and_keeps_preflight_consistency() -> None:
    controller = SessionController(_build_cfg(None, "invalid_mode"))
    controller.start_session()

    assert controller.get_state() is SessionState.ERROR
    assert controller.reset_error() is True
    assert controller.get_state() is SessionState.IDLE
    assert controller.get_last_preflight_report().readiness is ReadinessLevel.BLOCKED


def test_stop_session_in_idle_is_safe() -> None:
    controller = SessionController(_build_cfg("serial_local", "serial"))
    messages: list[str] = []
    controller.session_message.connect(messages.append)

    result = controller.stop_session()

    assert result is False
    assert controller.get_state() is SessionState.IDLE
    assert any("stop ignorado" in message.lower() for message in messages)


def test_controller_does_not_mark_running_when_backend_fails_start() -> None:
    controller = SessionController(_build_cfg("serial_local", "serial"))
    states: list[str] = []
    controller.session_state_changed.connect(states.append)

    controller.start_session()

    assert "running" not in states
    assert controller.get_state() is SessionState.ERROR


def test_preflight_signal_and_messages_reflect_blocked_start() -> None:
    controller = SessionController(_build_cfg(None, "invalid_mode"))
    reports: list[PreflightReport] = []
    messages: list[str] = []
    errors: list[str] = []

    controller.preflight_report_changed.connect(reports.append)
    controller.session_message.connect(messages.append)
    controller.session_error.connect(errors.append)

    result = controller.start_session()

    assert result is False
    assert any(report.readiness is ReadinessLevel.BLOCKED for report in reports)
    assert any("no se puede iniciar la sesion" in message.lower() for message in messages)
    assert any("fallo al iniciar backend de sesion" in err.lower() for err in errors)
