from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Final

DEFAULT_CONTROL_PLANE_STATE_FILENAME: Final[str] = "control_plane_state.json"
_U32_MAX: Final[int] = 0xFFFFFFFF


class NonceManagerError(RuntimeError):
    """Base error for control-plane nonce manager."""


class NonceStatePersistenceError(NonceManagerError):
    """Raised when nonce persistent state cannot be loaded/saved safely."""


@dataclass(frozen=True)
class ControlPlaneState:
    last_control_epoch_s: int = 0


def resolve_control_plane_state_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / DEFAULT_CONTROL_PLANE_STATE_FILENAME
    repo_root = Path(__file__).resolve().parents[4]
    return repo_root / DEFAULT_CONTROL_PLANE_STATE_FILENAME


def load_control_plane_state(path: Path | str | None = None) -> ControlPlaneState:
    state_path = Path(path) if path is not None else resolve_control_plane_state_path()
    if not state_path.exists():
        return ControlPlaneState()

    try:
        raw_text = state_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise NonceStatePersistenceError(
            f"No se pudo leer estado de control-plane en '{state_path}': {exc}"
        ) from exc

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise NonceStatePersistenceError(
            f"Estado de control-plane corrupto en '{state_path}': {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise NonceStatePersistenceError(
            f"Estado de control-plane invalido en '{state_path}': raiz no es objeto JSON."
        )

    raw_epoch = payload.get("last_control_epoch_s", 0)
    try:
        epoch = int(raw_epoch)
    except (TypeError, ValueError) as exc:
        raise NonceStatePersistenceError(
            f"last_control_epoch_s invalido en '{state_path}': {raw_epoch!r}"
        ) from exc

    if epoch < 0 or epoch > _U32_MAX:
        raise NonceStatePersistenceError(
            f"last_control_epoch_s fuera de rango u32 en '{state_path}': {epoch}"
        )
    return ControlPlaneState(last_control_epoch_s=epoch)


def save_control_plane_state(state: ControlPlaneState, path: Path | str | None = None) -> None:
    state_path = Path(path) if path is not None else resolve_control_plane_state_path()
    payload = {
        "last_control_epoch_s": _validate_u32(
            "last_control_epoch_s",
            state.last_control_epoch_s,
        )
    }
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise NonceStatePersistenceError(
            f"No se pudo guardar estado de control-plane en '{state_path}': {exc}"
        ) from exc


def compose_nonce(control_epoch_s: int, cmd_counter: int) -> int:
    high = _validate_u32("control_epoch_s", control_epoch_s)
    low = _validate_u32("cmd_counter", cmd_counter)
    return (high << 32) | low


class NonceManager:
    """
    Manages nonce generation under F3 rules:
    - nonce = (control_epoch_s << 32) | cmd_counter
    - control_epoch_s monotonic across app restarts
    - cmd_counter starts at 0 for each control session
    """

    def __init__(
        self,
        *,
        state_path: Path | str | None = None,
        time_provider: Callable[[], float] | None = None,
    ) -> None:
        self._state_path = Path(state_path) if state_path is not None else resolve_control_plane_state_path()
        self._time_provider = time_provider or time.time

        persisted = load_control_plane_state(self._state_path)
        unix_time_s = _normalize_unix_seconds(self._time_provider())
        self._control_epoch_s = max(unix_time_s, persisted.last_control_epoch_s + 1)
        self._cmd_counter = 0

        save_control_plane_state(
            ControlPlaneState(last_control_epoch_s=self._control_epoch_s),
            self._state_path,
        )

    @property
    def control_epoch_s(self) -> int:
        return self._control_epoch_s

    @property
    def cmd_counter_next(self) -> int:
        return self._cmd_counter

    def next_nonce(self) -> int:
        if self._cmd_counter > _U32_MAX:
            raise NonceManagerError(
                "cmd_counter agotado para esta sesion de control; reinicia la sesion."
            )
        nonce = compose_nonce(self._control_epoch_s, self._cmd_counter)
        self._cmd_counter += 1
        return nonce


def _normalize_unix_seconds(raw_value: float) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise NonceManagerError(f"time_provider retorno valor invalido: {raw_value!r}") from exc
    if value < 0:
        return 0
    return value


def _validate_u32(field_name: str, value: int) -> int:
    resolved = int(value)
    if resolved < 0 or resolved > _U32_MAX:
        raise ValueError(f"{field_name} fuera de rango u32: {value}")
    return resolved
