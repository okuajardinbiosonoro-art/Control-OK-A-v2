from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.midi.midi_router import MidiRouter  # noqa: E402


class _FakePort:
    def __init__(self, name: str) -> None:
        self.name = name
        self.closed = False

    def send(self, _msg: object) -> None:
        return

    def close(self) -> None:
        self.closed = True


def test_open_retries_until_outputs_become_available(monkeypatch) -> None:
    class _State:
        get_calls = 0

    class _FakeBackend:
        def get_output_names(self) -> list[str]:
            _State.get_calls += 1
            if _State.get_calls < 4:
                return []
            return ["loopMIDI Port 1 1"]

        def open_output(self, name: str) -> _FakePort:
            return _FakePort(name)

    def _fake_backend_factory(_name: str | None = None) -> _FakeBackend:
        return _FakeBackend()

    sleep_calls: list[float] = []

    monkeypatch.setattr(
        "control_okua.core.midi.midi_router.mido.Backend",
        _fake_backend_factory,
    )
    monkeypatch.setattr(
        "control_okua.core.midi.midi_router.time.sleep",
        lambda seconds: sleep_calls.append(float(seconds)),
    )

    router = MidiRouter(
        outputs={0: "loopMIDI Port 1"},
        backend="rtmidi",
        open_retry_ms=400,
        open_retry_interval_ms=50,
    )

    router.open()
    try:
        assert router.opened_buses() == [0]
        assert sleep_calls, "Debe reintentar al menos una vez cuando no hay puertos."
    finally:
        router.close()


def test_open_falls_back_to_default_backend_when_primary_has_no_outputs(monkeypatch) -> None:
    backend_calls: list[str] = []

    class _FakeBackend:
        def __init__(self, name: str | None) -> None:
            self._name = name

        def get_output_names(self) -> list[str]:
            label = self._name if self._name is not None else "<default>"
            backend_calls.append(label)
            if self._name == "mido.backends.rtmidi":
                return []
            return ["loopMIDI Port 2 2"]

        def open_output(self, name: str) -> _FakePort:
            return _FakePort(name)

    def _fake_backend_factory(name: str | None = None) -> _FakeBackend:
        return _FakeBackend(name)

    monkeypatch.setattr(
        "control_okua.core.midi.midi_router.mido.Backend",
        _fake_backend_factory,
    )

    router = MidiRouter(
        outputs={1: "loopMIDI Port 2"},
        backend="rtmidi",
        open_retry_ms=0,
        open_retry_interval_ms=50,
    )

    router.open()
    try:
        assert router.opened_buses() == [1]
        assert "mido.backends.rtmidi" in backend_calls
        assert "<default>" in backend_calls
    finally:
        router.close()


def test_from_config_parses_open_retry_parameters() -> None:
    cfg = {
        "midi": {
            "outputs": {"0": "loopMIDI Port 1"},
            "open_retry_ms": "7000",
            "open_retry_interval_ms": "120",
        }
    }
    router = MidiRouter.from_config(cfg)

    assert router.open_retry_ms == 7000
    assert router.open_retry_interval_ms == 120
