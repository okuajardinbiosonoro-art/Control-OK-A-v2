from __future__ import annotations

from dataclasses import dataclass
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.control_plane.runtime_snapshot import ControlPlaneResolvedIp  # noqa: E402
from control_okua.services.session_controller import SessionController  # noqa: E402


@dataclass(frozen=True)
class _RuntimeHolder:
    node_id: int
    source_ip: str
    received_ts: float


@dataclass(frozen=True)
class _RuntimeSnapshot:
    last_evt: object | None = None
    last_stat: object | None = None


class _BackendStub:
    def __init__(self, *, runtime_snapshot: object) -> None:
        self._runtime_snapshot = runtime_snapshot

    def runtime_snapshot(self) -> object:
        return self._runtime_snapshot


def _build_cfg() -> dict[str, object]:
    return {
        "profile": {"active": "udp_jardin"},
        "mode": "udp",
        "udp": {
            "bind_ip": "127.0.0.1",
            "evt_port": 5005,
            "stat_port": 5006,
            "cmd_port": 5007,
            "rcvbuf_bytes": 262144,
        },
    }


def test_resolver_returns_string_from_rich_cache_entry() -> None:
    controller = SessionController(_build_cfg())
    controller._control_plane_node_ip_cache[7] = ControlPlaneResolvedIp(
        node_id=7,
        ip="10.0.0.7",
        observed_at_monotonic=120.0,
    )

    resolved = controller._resolve_node_ip_for_control(7)

    assert resolved == "10.0.0.7"
    assert isinstance(resolved, str)
    assert not isinstance(resolved, ControlPlaneResolvedIp)


def test_resolver_returns_string_after_runtime_refresh() -> None:
    controller = SessionController(_build_cfg())
    controller._active_backend = _BackendStub(
        runtime_snapshot=_RuntimeSnapshot(
            last_evt=_RuntimeHolder(node_id=9, source_ip="192.168.1.9", received_ts=77.0)
        )
    )

    resolved = controller._resolve_node_ip_for_control(9)

    assert resolved == "192.168.1.9"
    assert isinstance(resolved, str)
    assert not isinstance(resolved, ControlPlaneResolvedIp)


def test_resolver_never_returns_cache_object_when_ip_is_not_usable(monkeypatch) -> None:
    controller = SessionController(_build_cfg())
    controller._control_plane_node_ip_cache[11] = ControlPlaneResolvedIp(
        node_id=11,
        ip="   ",
        observed_at_monotonic=11.0,
    )
    monkeypatch.setattr(
        "control_okua.services.session_controller.time.monotonic",
        _MonotonicStepper(start=0.0, step=1.0),
    )
    monkeypatch.setattr(
        "control_okua.services.session_controller.time.sleep",
        lambda _seconds: None,
    )

    resolved = controller._resolve_node_ip_for_control(11)

    assert resolved is None
    assert not isinstance(resolved, ControlPlaneResolvedIp)


def test_resolver_polling_without_resolution_returns_none(monkeypatch) -> None:
    controller = SessionController(_build_cfg())
    controller._active_backend = _BackendStub(runtime_snapshot=_RuntimeSnapshot())
    monkeypatch.setattr(
        "control_okua.services.session_controller.time.monotonic",
        _MonotonicStepper(start=10.0, step=1.0),
    )
    monkeypatch.setattr(
        "control_okua.services.session_controller.time.sleep",
        lambda _seconds: None,
    )

    resolved = controller._resolve_node_ip_for_control(42)

    assert resolved is None
    assert not isinstance(resolved, ControlPlaneResolvedIp)


def test_resolver_returns_only_string_or_none_across_paths(monkeypatch) -> None:
    controller = SessionController(_build_cfg())
    controller._control_plane_node_ip_cache[1] = ControlPlaneResolvedIp(
        node_id=1,
        ip="10.0.0.1",
        observed_at_monotonic=1.0,
    )
    from_cache = controller._resolve_node_ip_for_control(1)

    controller._control_plane_node_ip_cache.clear()
    controller._active_backend = _BackendStub(
        runtime_snapshot=_RuntimeSnapshot(
            last_stat=_RuntimeHolder(node_id=2, source_ip="10.0.0.2", received_ts=2.0)
        )
    )
    from_refresh = controller._resolve_node_ip_for_control(2)

    monkeypatch.setattr(
        "control_okua.services.session_controller.time.monotonic",
        _MonotonicStepper(start=100.0, step=1.0),
    )
    monkeypatch.setattr(
        "control_okua.services.session_controller.time.sleep",
        lambda _seconds: None,
    )
    unresolved = controller._resolve_node_ip_for_control(999)

    for value in (from_cache, from_refresh, unresolved):
        assert isinstance(value, str) or value is None
        assert not isinstance(value, ControlPlaneResolvedIp)


class _MonotonicStepper:
    def __init__(self, *, start: float, step: float) -> None:
        self._value = float(start)
        self._step = float(step)

    def __call__(self) -> float:
        self._value += self._step
        return self._value
