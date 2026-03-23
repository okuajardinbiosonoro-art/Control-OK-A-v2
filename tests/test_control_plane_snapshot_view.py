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


@dataclass(frozen=True)
class _SnapshotStub:
    label: str | None = None
    resolved_ip: str | None = None
    resolution_status: str | None = None
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
