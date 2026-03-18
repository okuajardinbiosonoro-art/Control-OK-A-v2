from __future__ import annotations

import json

from control_okua.core.control_plane.nonce_manager import (
    NonceManager,
    compose_nonce,
    load_control_plane_state,
)


def test_nonce_composes_control_epoch_high32_and_counter_low32(tmp_path) -> None:
    state_path = tmp_path / "control_plane_state.json"

    manager = NonceManager(
        state_path=state_path,
        time_provider=lambda: 1_700_000_000,
    )
    nonce0 = manager.next_nonce()
    nonce1 = manager.next_nonce()

    assert (nonce0 >> 32) == 1_700_000_000
    assert (nonce0 & 0xFFFFFFFF) == 0
    assert (nonce1 >> 32) == 1_700_000_000
    assert (nonce1 & 0xFFFFFFFF) == 1
    assert nonce0 == compose_nonce(1_700_000_000, 0)
    assert nonce1 == compose_nonce(1_700_000_000, 1)


def test_control_epoch_is_monotonic_even_if_clock_rolls_back(tmp_path) -> None:
    state_path = tmp_path / "control_plane_state.json"

    manager_1 = NonceManager(
        state_path=state_path,
        time_provider=lambda: 2_000_000_000,
    )
    assert manager_1.control_epoch_s == 2_000_000_000

    manager_2 = NonceManager(
        state_path=state_path,
        time_provider=lambda: 1_999_999_000,  # Simulated clock rollback
    )
    assert manager_2.control_epoch_s == 2_000_000_001

    persisted = load_control_plane_state(state_path)
    assert persisted.last_control_epoch_s == 2_000_000_001

    raw_payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert raw_payload["last_control_epoch_s"] == 2_000_000_001
