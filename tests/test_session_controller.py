from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.session import SessionState  # noqa: E402
from control_okua.services.session_controller import SessionController  # noqa: E402


def _build_cfg(profile_id: str | None, mode: str | None = None) -> dict[str, Any]:
    return {
        "profile": {"active": profile_id},
        "mode": mode,
    }


def test_controller_starts_in_idle() -> None:
    controller = SessionController(_build_cfg("serial_local", "serial"))
    assert controller.get_state() is SessionState.IDLE


def test_get_snapshot_is_coherent_on_init() -> None:
    controller = SessionController(_build_cfg("serial_local", "serial"))
    snapshot = controller.get_snapshot()

    assert snapshot.state is SessionState.IDLE
    assert snapshot.active_profile == "serial_local"
    assert snapshot.mode == "serial"
    assert snapshot.can_start is True
    assert snapshot.can_stop is False


def test_start_session_with_invalid_config_goes_to_error() -> None:
    controller = SessionController(_build_cfg(None, "invalid_mode"))
    result = controller.start_session()

    assert result is False
    assert controller.get_state() is SessionState.ERROR
    assert controller.get_snapshot().error is not None


def test_start_session_with_unimplemented_backend_goes_to_error() -> None:
    controller = SessionController(_build_cfg("serial_local", "serial"))
    states: list[str] = []
    errors: list[str] = []
    snapshots: list[object] = []

    controller.session_state_changed.connect(states.append)
    controller.session_error.connect(errors.append)
    controller.session_snapshot_changed.connect(snapshots.append)

    result = controller.start_session()

    assert result is False
    assert controller.get_state() is SessionState.ERROR
    assert "starting" in states
    assert "error" in states
    assert len(snapshots) >= 2
    assert len(errors) >= 1


def test_reset_error_returns_to_idle() -> None:
    controller = SessionController(_build_cfg("udp_jardin", "udp"))
    controller.start_session()

    assert controller.get_state() is SessionState.ERROR
    assert controller.reset_error() is True
    assert controller.get_state() is SessionState.IDLE


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
