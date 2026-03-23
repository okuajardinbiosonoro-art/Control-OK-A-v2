from __future__ import annotations

from dataclasses import dataclass
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.viewmodels.control_plane_snapshot_view import (  # noqa: E402
    build_control_plane_snapshot_view,
)
from control_okua.core.control_plane.runtime_snapshot import (  # noqa: E402
    ControlPlaneNodeResolutionStatus,
)


@dataclass(frozen=True)
class _SnapshotStub:
    label: str | None = None
    resolved_ip: str | None = None
    resolution_status: object | None = None
    resolution_age_s: float | None = None
    transaction_active: bool = False
    last_command_name: str | None = None
    last_cmd_seq: int | None = None
    last_nonce: int | None = None
    last_final_status: str | None = None
    last_ack_stage: int | None = None
    last_status_code: int | None = None
    last_err_detail: int | None = None
    last_error_message: str | None = None
    last_tx_started_at: str | None = None
    last_tx_finished_at: str | None = None
    last_reboot_verification_status: str | None = None
    last_reboot_verification_summary: str | None = None
    last_uptime_s: int | None = None
    last_reset_reason: int | None = None
    last_boot_marker: int | None = None
    message: str | None = None


@dataclass(frozen=True)
class _FinalStatusStub:
    value: str


@dataclass(frozen=True)
class _AckStub:
    ack_stage: int | None = None
    status_code: int | None = None
    err_detail: int | None = None


@dataclass(frozen=True)
class _LocalResultStub:
    command_name: str
    cmd_seq: int
    nonce: int
    final_status: object
    ack: object | None = None
    last_error: str | None = None


def test_snapshot_view_formats_resolved_status() -> None:
    view = build_control_plane_snapshot_view(
        node_id=1,
        snapshot=_SnapshotStub(
            label="EB1",
            resolved_ip="192.168.88.121",
            resolution_status="resolved",
            resolution_age_s=1.4,
        ),
    )

    assert view.label_text == "EB1"
    assert view.resolution_status_text == "RESOLVED"
    assert view.resolution_age_text == "1.4 s"
    assert view.resolution_message_text == "Nodo 1 resuelto a 192.168.88.121."
    assert view.is_unresolved is False
    assert view.is_stale is False


def test_snapshot_view_accepts_resolution_enum_without_false_unresolved() -> None:
    view = build_control_plane_snapshot_view(
        node_id=1,
        snapshot=_SnapshotStub(
            label="EB1",
            resolved_ip="192.168.88.121",
            resolution_status=ControlPlaneNodeResolutionStatus.RESOLVED,
            resolution_age_s=0.2,
        ),
    )

    assert view.resolution_status_text == "RESOLVED"
    assert view.is_unresolved is False
    assert "resuelto" in view.resolution_message_text.lower()


def test_snapshot_view_infers_resolution_from_ip_when_raw_status_is_legacy_string() -> None:
    view = build_control_plane_snapshot_view(
        node_id=1,
        snapshot=_SnapshotStub(
            label="EB1",
            resolved_ip="192.168.88.121",
            resolution_status="ControlPlaneNodeResolutionStatus.RESOLVED",
            resolution_age_s=0.2,
        ),
    )

    assert view.resolution_status_text == "RESOLVED"
    assert view.is_unresolved is False


def test_snapshot_view_formats_stale_status() -> None:
    view = build_control_plane_snapshot_view(
        node_id=3,
        snapshot=_SnapshotStub(
            label="ED1",
            resolved_ip="192.168.88.123",
            resolution_status="stale",
            resolution_age_s=12.0,
        ),
    )

    assert view.resolution_status_text == "STALE"
    assert view.resolution_message_text == "Nodo 3 resuelto, pero sin actividad reciente."
    assert view.is_stale is True
    assert view.is_unresolved is False


def test_snapshot_view_formats_unresolved_status() -> None:
    view = build_control_plane_snapshot_view(
        node_id=4,
        snapshot=_SnapshotStub(
            label="EE1",
            resolved_ip=None,
            resolution_status="unresolved",
            resolution_age_s=None,
        ),
    )

    assert view.resolution_status_text == "UNRESOLVED"
    assert view.resolution_age_text == "-"
    assert view.resolution_message_text == "Nodo 4 no resoluble todavía; primero debe emitir EVT/STAT."
    assert view.is_unresolved is True


def test_snapshot_view_formats_ack_present_and_absent() -> None:
    no_ack = build_control_plane_snapshot_view(
        node_id=1,
        snapshot=_SnapshotStub(last_ack_stage=None, last_status_code=None, last_err_detail=None),
    )
    with_ack = build_control_plane_snapshot_view(
        node_id=1,
        snapshot=_SnapshotStub(last_ack_stage=1, last_status_code=0, last_err_detail=0),
    )

    assert no_ack.ack_message_text == "Sin ACK registrado."
    assert with_ack.ack_stage_text == "1"
    assert with_ack.ack_status_code_text == "0"
    assert with_ack.ack_err_detail_text == "0"
    assert "ACK registrado" in with_ack.ack_message_text


def test_snapshot_view_does_not_show_ack_empty_when_ack_matched_but_ack_fields_missing() -> None:
    view = build_control_plane_snapshot_view(
        node_id=1,
        snapshot=_SnapshotStub(
            last_final_status="ack_matched",
            last_ack_stage=None,
            last_status_code=None,
            last_err_detail=None,
        ),
    )

    assert "Sin ACK registrado" not in view.ack_message_text
    assert "ACK correlacionado" in view.ack_message_text


def test_snapshot_view_ack_matched_clears_timeout_error_text() -> None:
    view = build_control_plane_snapshot_view(
        node_id=1,
        snapshot=_SnapshotStub(
            last_final_status="ack_matched",
            last_error_message="Timeout esperando ACK para REQUEST_STAT_NOW.",
            last_ack_stage=1,
            last_status_code=0,
            last_err_detail=0,
        ),
    )

    assert view.last_final_status_text == "ack_matched"
    assert view.last_error_text == "-"
    assert view.ack_message_text.startswith("ACK registrado:")


def test_snapshot_view_timeout_forces_ack_absent_and_timeout_error() -> None:
    view = build_control_plane_snapshot_view(
        node_id=1,
        snapshot=_SnapshotStub(
            last_final_status="timeout",
            last_error_message=None,
            last_ack_stage=1,
            last_status_code=0,
            last_err_detail=0,
        ),
    )

    assert view.last_final_status_text == "timeout"
    assert "timeout" in view.last_error_text.lower()
    assert view.ack_stage_text == "-"
    assert view.ack_status_code_text == "-"
    assert view.ack_err_detail_text == "-"
    assert view.ack_message_text == "Sin ACK registrado."


def test_snapshot_view_uses_recent_local_result_when_snapshot_lacks_ack_details() -> None:
    local_result = _LocalResultStub(
        command_name="REQUEST_STAT_NOW",
        cmd_seq=123,
        nonce=0xAA,
        final_status=_FinalStatusStub(value="ack_matched"),
        ack=_AckStub(ack_stage=1, status_code=0, err_detail=0),
    )
    view = build_control_plane_snapshot_view(
        node_id=1,
        snapshot=_SnapshotStub(
            last_command_name="REQUEST_STAT_NOW",
            last_final_status="timeout",
            last_ack_stage=None,
            last_status_code=None,
            last_err_detail=None,
        ),
        local_result=local_result,
        local_result_age_s=0.8,
    )

    assert view.last_final_status_text == "ack_matched"
    assert view.ack_stage_text == "1"
    assert view.ack_status_code_text == "0"
    assert view.ack_err_detail_text == "0"
    assert "Sin ACK registrado" not in view.ack_message_text


def test_snapshot_view_snapshot_complete_has_priority_when_same_cmd_seq() -> None:
    local_result = _LocalResultStub(
        command_name="REQUEST_STAT_NOW",
        cmd_seq=222,
        nonce=0xAA,
        final_status=_FinalStatusStub(value="timeout"),
        ack=None,
        last_error="Timeout esperando ACK para REQUEST_STAT_NOW.",
    )
    view = build_control_plane_snapshot_view(
        node_id=1,
        snapshot=_SnapshotStub(
            last_command_name="REQUEST_STAT_NOW",
            last_cmd_seq=222,
            last_nonce=0xAA,
            last_final_status="ack_matched",
            last_ack_stage=1,
            last_status_code=0,
            last_err_detail=0,
            last_error_message=None,
            last_tx_finished_at="2026-03-23T10:00:00.000Z",
        ),
        local_result=local_result,
        local_result_age_s=0.2,
    )

    assert view.last_final_status_text == "ack_matched"
    assert view.last_error_text == "-"
    assert view.ack_stage_text == "1"
    assert "Sin ACK registrado" not in view.ack_message_text


def test_snapshot_view_local_newer_cmd_seq_replaces_full_result_atomically() -> None:
    local_result = _LocalResultStub(
        command_name="REQUEST_STAT_NOW",
        cmd_seq=301,
        nonce=0xBB,
        final_status=_FinalStatusStub(value="ack_matched"),
        ack=_AckStub(ack_stage=1, status_code=0, err_detail=0),
        last_error=None,
    )
    view = build_control_plane_snapshot_view(
        node_id=1,
        snapshot=_SnapshotStub(
            last_command_name="REQUEST_STAT_NOW",
            last_cmd_seq=300,
            last_nonce=0xAA,
            last_final_status="timeout",
            last_ack_stage=None,
            last_status_code=None,
            last_err_detail=None,
            last_error_message="Timeout esperando ACK para REQUEST_STAT_NOW.",
        ),
        local_result=local_result,
        local_result_age_s=0.4,
    )

    assert view.last_cmd_seq_text == "301"
    assert view.last_final_status_text == "ack_matched"
    assert view.last_error_text == "-"
    assert view.ack_stage_text == "1"
    assert "Sin ACK registrado" not in view.ack_message_text


def test_snapshot_view_old_local_fallback_does_not_contaminate_newer_snapshot() -> None:
    local_result = _LocalResultStub(
        command_name="REQUEST_STAT_NOW",
        cmd_seq=401,
        nonce=0xCC,
        final_status=_FinalStatusStub(value="ack_matched"),
        ack=_AckStub(ack_stage=1, status_code=0, err_detail=0),
    )
    view = build_control_plane_snapshot_view(
        node_id=1,
        snapshot=_SnapshotStub(
            last_command_name="REQUEST_STAT_NOW",
            last_cmd_seq=402,
            last_nonce=0xDD,
            last_final_status="timeout",
            last_ack_stage=None,
            last_status_code=None,
            last_err_detail=None,
            last_error_message="Timeout esperando ACK para REQUEST_STAT_NOW.",
        ),
        local_result=local_result,
        local_result_age_s=25.0,
    )

    assert view.last_cmd_seq_text == "402"
    assert view.last_final_status_text == "timeout"
    assert "timeout" in view.last_error_text.lower()
    assert view.ack_message_text == "Sin ACK registrado."


def test_snapshot_view_keeps_ack_empty_when_no_ack_exists() -> None:
    view = build_control_plane_snapshot_view(
        node_id=1,
        snapshot=_SnapshotStub(
            last_final_status="timeout",
            last_ack_stage=None,
            last_status_code=None,
            last_err_detail=None,
        ),
    )

    assert view.ack_message_text == "Sin ACK registrado."


def test_snapshot_view_formats_reboot_summary_present_and_absent() -> None:
    summary = "verificación_reinicio_resumen: intentos=3 corte=1 recuperado=1"
    no_reboot = build_control_plane_snapshot_view(
        node_id=1,
        snapshot=_SnapshotStub(last_reboot_verification_status=None, last_reboot_verification_summary=None),
    )
    with_reboot = build_control_plane_snapshot_view(
        node_id=1,
        snapshot=_SnapshotStub(
            last_reboot_verification_status="confirmed",
            last_reboot_verification_summary=summary,
        ),
    )

    assert no_reboot.reboot_summary_text == "Sin verificación de reinicio registrada."
    assert with_reboot.reboot_status_text == "confirmed"
    assert with_reboot.reboot_summary_text == summary
