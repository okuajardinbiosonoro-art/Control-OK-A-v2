from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.control_plane.runtime_snapshot import (  # noqa: E402
    ControlPlaneNodeResolutionStatus,
    ControlPlaneNodeSnapshotInput,
    build_control_plane_node_snapshot,
)


def test_snapshot_of_resolvable_node_is_marked_as_resolved() -> None:
    snapshot = build_control_plane_node_snapshot(
        ControlPlaneNodeSnapshotInput(
            node_id=7,
            resolved_ip="10.12.0.7",
            resolution_observed_at_monotonic=98.0,
            last_seen_pc_ts=98.5,
            last_command_name="PING",
            last_cmd_seq=101,
            last_nonce=0xABCD000000000101,
            last_final_status="ack_matched",
            last_ack_stage=1,
            last_status_code=0,
            last_err_detail=0,
        ),
        now_monotonic=100.0,
    )

    assert snapshot.node_id == 7
    assert snapshot.resolved_ip == "10.12.0.7"
    assert snapshot.resolution_status is ControlPlaneNodeResolutionStatus.RESOLVED
    assert snapshot.resolution_age_s == 2.0
    assert snapshot.last_seen_pc_ts == 98.5
    assert snapshot.last_final_status == "ack_matched"
    assert snapshot.last_ack_stage == 1


def test_snapshot_of_unresolvable_node_is_marked_as_unresolved() -> None:
    snapshot = build_control_plane_node_snapshot(
        ControlPlaneNodeSnapshotInput(
            node_id=9,
            resolved_ip=None,
            last_seen_pc_ts=None,
        ),
        now_monotonic=100.0,
    )

    assert snapshot.node_id == 9
    assert snapshot.resolved_ip is None
    assert snapshot.resolution_status is ControlPlaneNodeResolutionStatus.UNRESOLVED
    assert snapshot.resolution_age_s is None
    assert "sin ip resuelta" in snapshot.message.lower()


def test_snapshot_of_stale_node_resolution_is_marked_as_stale() -> None:
    snapshot = build_control_plane_node_snapshot(
        ControlPlaneNodeSnapshotInput(
            node_id=11,
            resolved_ip="192.168.0.11",
            resolution_observed_at_monotonic=50.0,
        ),
        now_monotonic=70.0,
        resolution_stale_after_s=8.0,
    )

    assert snapshot.resolution_status is ControlPlaneNodeResolutionStatus.STALE
    assert snapshot.resolution_age_s == 20.0
    assert "stale" in snapshot.message.lower()


def test_snapshot_with_active_transaction_marks_transaction_active() -> None:
    snapshot = build_control_plane_node_snapshot(
        ControlPlaneNodeSnapshotInput(
            node_id=2,
            resolved_ip="10.0.0.2",
            resolution_observed_at_monotonic=199.0,
            transaction_active=True,
            last_command_name="REQUEST_STAT_NOW",
        ),
        now_monotonic=200.0,
    )

    assert snapshot.transaction_active is True
    assert snapshot.last_command_name == "REQUEST_STAT_NOW"
    assert "transaccion" in snapshot.message.lower()


def test_snapshot_with_last_final_result_and_ack_fields() -> None:
    snapshot = build_control_plane_node_snapshot(
        ControlPlaneNodeSnapshotInput(
            node_id=5,
            resolved_ip="10.0.0.5",
            resolution_observed_at_monotonic=1.0,
            last_command_name="REQUEST_STAT_NOW",
            last_cmd_seq=222,
            last_nonce=0x1111222200000033,
            last_final_status="ack_matched",
            last_ack_stage=1,
            last_status_code=0,
            last_err_detail=0,
            last_tx_started_at="2026-03-23T14:00:00.000Z",
            last_tx_finished_at="2026-03-23T14:00:00.450Z",
        ),
        now_monotonic=2.0,
    )

    assert snapshot.last_command_name == "REQUEST_STAT_NOW"
    assert snapshot.last_cmd_seq == 222
    assert snapshot.last_nonce == 0x1111222200000033
    assert snapshot.last_final_status == "ack_matched"
    assert snapshot.last_ack_stage == 1
    assert snapshot.last_status_code == 0
    assert snapshot.last_err_detail == 0
    assert snapshot.last_tx_started_at == "2026-03-23T14:00:00.000Z"
    assert snapshot.last_tx_finished_at == "2026-03-23T14:00:00.450Z"


def test_snapshot_with_timeout_or_reject_preserves_error_fields() -> None:
    snapshot = build_control_plane_node_snapshot(
        ControlPlaneNodeSnapshotInput(
            node_id=3,
            resolved_ip="10.0.0.3",
            resolution_observed_at_monotonic=10.0,
            last_command_name="REBOOT_SOFT",
            last_cmd_seq=333,
            last_nonce=0x7777000000000001,
            last_final_status="timeout",
            last_ack_stage=1,
            last_status_code=9,
            last_err_detail=44,
            last_error_message="Timeout esperando ACK de REBOOT_SOFT.",
        ),
        now_monotonic=11.0,
    )

    assert snapshot.last_final_status == "timeout"
    assert snapshot.last_status_code == 9
    assert snapshot.last_err_detail == 44
    assert snapshot.last_error_message == "Timeout esperando ACK de REBOOT_SOFT."
    assert "timeout esperando ack" in snapshot.message.lower()


def test_snapshot_includes_reboot_verification_summary_when_available() -> None:
    summary = (
        "verificación_reinicio_resumen: intentos=4 corte=1 recuperado=1 "
        "uptime_reset=1 reset_reason_change=0 boot_marker_change=1"
    )
    snapshot = build_control_plane_node_snapshot(
        ControlPlaneNodeSnapshotInput(
            node_id=8,
            resolved_ip="10.0.0.8",
            resolution_observed_at_monotonic=20.0,
            last_reboot_verification_status="confirmed",
            last_reboot_verification_summary=summary,
            last_uptime_s=12,
            last_reset_reason=2,
            last_boot_marker=3,
        ),
        now_monotonic=21.0,
    )

    assert snapshot.last_reboot_verification_status == "confirmed"
    assert snapshot.last_reboot_verification_summary == summary
    assert snapshot.last_uptime_s == 12
    assert snapshot.last_reset_reason == 2
    assert snapshot.last_boot_marker == 3
    assert snapshot.message == summary
