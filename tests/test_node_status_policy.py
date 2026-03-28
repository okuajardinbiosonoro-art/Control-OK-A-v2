from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.registry import (  # noqa: E402
    NodeRegistryConfig,
    NodeStatus,
    NodeStatusInputs,
    evaluate_node_status,
)


def _inputs(**overrides) -> NodeStatusInputs:
    payload = {
        "last_seen_pc_ts": 100.0,
        "last_stat_pc_ts": 100.0,
        "pps_evt": 1.0,
        "pps_stat": 1.0,
        "loss_evt_pct": 0.0,
        "loss_stat_pct": 0.0,
        "last_seq_evt": 10,
        "last_seq_stat": 10,
        "last_uptime_s": 120,
        "last_reboot_detected_pc_ts": None,
        "evt_recovery_streak": 4,
        "stat_recovery_streak": 4,
    }
    payload.update(overrides)
    return NodeStatusInputs(**payload)


def test_online_stable_node_is_reported_as_online() -> None:
    evaluation = evaluate_node_status(
        _inputs(),
        NodeRegistryConfig(),
        now=101.0,
    )
    assert evaluation.status is NodeStatus.ONLINE
    assert evaluation.reason == "healthy traffic"


def test_partial_activity_node_is_reported_as_degraded() -> None:
    evaluation = evaluate_node_status(
        _inputs(last_seen_pc_ts=95.5, last_stat_pc_ts=95.5),
        NodeRegistryConfig(t_green_s=4.0, t_red_s=8.0),
        now=100.0,
    )
    assert evaluation.status is NodeStatus.DEGRADED
    assert evaluation.reason == "partial traffic"


def test_missing_recent_packets_node_is_reported_as_offline() -> None:
    evaluation = evaluate_node_status(
        _inputs(last_seen_pc_ts=90.0, last_stat_pc_ts=90.0),
        NodeRegistryConfig(t_green_s=4.0, t_red_s=8.0),
        now=100.0,
    )
    assert evaluation.status is NodeStatus.OFFLINE
    assert evaluation.reason == "no recent packets"


def test_recent_reboot_is_reported_as_calibrating() -> None:
    evaluation = evaluate_node_status(
        _inputs(
            last_seen_pc_ts=100.0,
            last_stat_pc_ts=100.0,
            last_uptime_s=6,
            last_reboot_detected_pc_ts=99.5,
        ),
        NodeRegistryConfig(),
        now=100.5,
    )
    assert evaluation.status is NodeStatus.CALIBRATING
    assert evaluation.reason == "calibrating"


def test_recovery_requires_stable_good_packets_before_returning_online() -> None:
    config = NodeRegistryConfig(stat_loss_yellow_pct=25.0, stat_recovery_packets_online=3)

    recovering = evaluate_node_status(
        _inputs(loss_stat_pct=40.0, stat_recovery_streak=1),
        config,
        now=100.5,
    )
    recovered = evaluate_node_status(
        _inputs(loss_stat_pct=40.0, stat_recovery_streak=3),
        config,
        now=100.5,
    )

    assert recovering.status is NodeStatus.DEGRADED
    assert recovering.reason == "recovering"
    assert recovered.status is NodeStatus.ONLINE
    assert recovered.reason == "healthy traffic"


def test_small_changes_do_not_trigger_absurd_flapping() -> None:
    config = NodeRegistryConfig(stat_loss_yellow_pct=25.0, stat_recovery_packets_online=3)
    first = evaluate_node_status(
        _inputs(loss_stat_pct=35.0, stat_recovery_streak=1),
        config,
        now=100.2,
    )
    second = evaluate_node_status(
        _inputs(loss_stat_pct=35.0, stat_recovery_streak=2),
        config,
        now=100.4,
    )
    third = evaluate_node_status(
        _inputs(loss_stat_pct=35.0, stat_recovery_streak=3),
        config,
        now=100.6,
    )

    assert first.status is NodeStatus.DEGRADED
    assert second.status is NodeStatus.DEGRADED
    assert third.status is NodeStatus.ONLINE


def test_reason_is_never_empty_in_relevant_cases() -> None:
    reasons = [
        evaluate_node_status(_inputs(), NodeRegistryConfig(), now=101.0).reason,
        evaluate_node_status(
            _inputs(last_seen_pc_ts=90.0),
            NodeRegistryConfig(t_green_s=4.0, t_red_s=8.0),
            now=100.0,
        ).reason,
        evaluate_node_status(
            _inputs(last_uptime_s=5, last_reboot_detected_pc_ts=99.0),
            NodeRegistryConfig(),
            now=100.0,
        ).reason,
    ]

    assert all(reason.strip() for reason in reasons)
