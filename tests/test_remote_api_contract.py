from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.control_plane.runtime_snapshot import (  # noqa: E402
    ControlPlaneNodeResolutionStatus,
    ControlPlaneNodeSnapshot,
)
from control_okua.core.registry.node_models import NodeSnapshot, NodeStatus  # noqa: E402
from control_okua.core.session import (  # noqa: E402
    BackendKind,
    SessionSnapshot,
    SessionState,
)
from control_okua.services.remote_api_contract import (  # noqa: E402
    resolve_remote_api_config,
    serialize_node_detail,
    serialize_session_snapshot,
)


def test_resolve_remote_api_config_reads_expected_defaults_and_overrides() -> None:
    cfg = {
        "remote_api": {
            "enabled": True,
            "bind_host": "0.0.0.0",
            "port": 9999,
            "auth_mode": "bearer_token_inventory",
            "token_env_var": "CKV2_REMOTE_API_TOKEN",
            "tokens": [
                {
                    "env_var": "CKV2_REMOTE_API_OBSERVER_TOKEN",
                    "role": "observador",
                    "label": "observer-main",
                },
                {
                    "env_var": "CKV2_REMOTE_API_ADMIN_TOKEN",
                    "role": "admin",
                },
            ],
            "audit_enabled": False,
            "audit_folder": "logs/custom_remote",
            "user_store_filename": "site_users.json",
            "session_ttl_s": 7200,
        }
    }

    resolved = resolve_remote_api_config(cfg)

    assert resolved.enabled is True
    assert resolved.bind_host == "0.0.0.0"
    assert resolved.port == 9999
    assert resolved.auth_mode == "bearer_token_inventory"
    assert resolved.token_env_var == "CKV2_REMOTE_API_TOKEN"
    assert len(resolved.tokens) == 2
    assert resolved.tokens[0].role == "observador"
    assert resolved.tokens[0].label == "observer-main"
    assert resolved.audit_enabled is False
    assert resolved.audit_folder == "logs/custom_remote"
    assert resolved.user_store_filename == "site_users.json"
    assert resolved.session_ttl_s == 7200


def test_serialize_session_snapshot_and_node_detail_follow_runtime_source_of_truth() -> None:
    session_snapshot = SessionSnapshot(
        state=SessionState.RUNNING,
        active_profile="udp_jardin",
        mode="udp",
        backend=BackendKind.UDP,
        message="Sesion iniciada.",
        error=None,
        can_start=False,
        can_stop=True,
    )
    node_snapshot = NodeSnapshot(
        node_id=11,
        label=None,
        node_type=None,
        last_seen_pc_ts=100.0,
        last_seq_evt=1,
        last_seq_stat=1,
        pps_evt=8.0,
        pps_stat=1.0,
        loss_evt_pct=0.0,
        loss_stat_pct=0.0,
        rssi_dbm=-57,
        last_note=60,
        last_velocity=100,
        last_evt_ts_ms=1234,
        last_evt_flags=0,
        last_state_flags=0,
        last_uptime_s=900,
        reported_pps_x10=10,
        status=NodeStatus.ONLINE,
        fw_major=1,
        fw_minor=2,
        health_summary="nodo sano",
        status_reason="trafico estable",
        last_seen_age_s=0.4,
        last_stat_age_s=1.2,
        status_age_s=3.4,
        ota_state_key="idle",
        ota_error_key="none",
    )
    control_snapshot = ControlPlaneNodeSnapshot(
        node_id=11,
        label="EB3",
        resolved_ip="192.168.88.31",
        resolution_status=ControlPlaneNodeResolutionStatus.RESOLVED,
        resolution_age_s=0.7,
        last_seen_pc_ts=100.0,
        transaction_active=False,
        last_command_name="REQUEST_STAT_NOW",
        last_cmd_seq=42,
        last_nonce=777,
        last_final_status="ack_matched",
        last_ack_stage=1,
        last_status_code=0,
        last_err_detail=0,
        last_error_message=None,
        last_tx_started_at="2026-04-02T20:11:43.101Z",
        last_tx_finished_at="2026-04-02T20:11:43.551Z",
        last_reboot_verification_status="confirmed",
        last_reboot_verification_summary="Nodo visible tras reboot esperado.",
        last_uptime_s=900,
        last_reset_reason=1,
        last_boot_marker=1,
        message="Ultimo resultado de control-plane: ack_matched.",
    )

    session_payload = serialize_session_snapshot(session_snapshot)
    node_payload = serialize_node_detail(
        node_snapshot,
        control_plane_snapshot=control_snapshot,
    )

    assert session_payload["state"] == "running"
    assert session_payload["backend_kind"] == "udp"
    assert node_payload["label"] == "EB3"
    assert node_payload["box_label"] == "Caja 3"
    assert node_payload["runtime"]["fw_major"] == 1
    assert node_payload["control_plane"]["resolved_ip"] == "192.168.88.31"
    assert node_payload["control_plane"]["last_final_status"] == "ack_matched"
