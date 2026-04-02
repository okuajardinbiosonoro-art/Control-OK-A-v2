from __future__ import annotations

from dataclasses import dataclass, field
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import socket
import sys
from typing import Any

import pytest


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.control_plane.protocol import ParsedOkuaAck  # noqa: E402
from control_okua.core.control_plane.runtime import (  # noqa: E402
    ControlPlaneRuntimeSnapshot,
)
from control_okua.core.control_plane.runtime_snapshot import (  # noqa: E402
    ControlPlaneNodeResolutionStatus,
    ControlPlaneNodeSnapshot,
)
from control_okua.core.registry.node_models import (  # noqa: E402
    NodeRegistrySummary,
    NodeSnapshot,
    NodeStatus,
)
from control_okua.core.session import (  # noqa: E402
    BackendKind,
    SessionSnapshot,
    SessionState,
)
from control_okua.services.control_transaction_service import (  # noqa: E402
    ControlTransactionFinalStatus,
    ControlTransactionResult,
)
from control_okua.services.remote_api_auth import build_remote_api_token_entry  # noqa: E402
from control_okua.services.remote_api_contract import RemoteApiConfig  # noqa: E402
from control_okua.services.remote_api_service import (  # noqa: E402
    RemoteApiService,
    RemoteApiServiceError,
)


@dataclass
class _RuntimeStub:
    snapshot: SessionSnapshot
    node_summary: NodeRegistrySummary | None
    nodes: dict[int, NodeSnapshot]
    control_plane_snapshot: ControlPlaneRuntimeSnapshot
    control_nodes: dict[int, ControlPlaneNodeSnapshot]
    request_stat_result: ControlTransactionResult | Exception | None = None
    reboot_result: ControlTransactionResult | Exception | None = None
    request_stat_calls: list[tuple[int, str]] = field(default_factory=list)
    reboot_calls: list[tuple[int, int, str]] = field(default_factory=list)

    def get_snapshot(self) -> SessionSnapshot:
        return self.snapshot

    def get_node_registry_summary(self, now: float | None = None) -> NodeRegistrySummary | None:
        _ = now
        return self.node_summary

    def get_node_snapshots(self, now: float | None = None) -> list[NodeSnapshot]:
        _ = now
        return list(self.nodes.values())

    def get_node_snapshot(self, node_id: int, now: float | None = None) -> NodeSnapshot | None:
        _ = now
        return self.nodes.get(int(node_id))

    def is_control_plane_available(self) -> bool:
        return bool(self.control_plane_snapshot.is_available)

    def get_control_plane_runtime_snapshot(self) -> ControlPlaneRuntimeSnapshot:
        return self.control_plane_snapshot

    def get_control_plane_node_snapshots(self, now: float | None = None) -> list[ControlPlaneNodeSnapshot]:
        _ = now
        return list(self.control_nodes.values())

    def get_control_plane_node_snapshot(
        self,
        node_id: int,
        now: float | None = None,
    ) -> ControlPlaneNodeSnapshot | None:
        _ = now
        return self.control_nodes.get(int(node_id))

    def send_control_request_stat_now(
        self,
        *,
        node_id: int,
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
        source: str = "remote_api",
    ) -> ControlTransactionResult:
        _ = (ack_timeout_ms, max_retries)
        self.request_stat_calls.append((int(node_id), source))
        if isinstance(self.request_stat_result, Exception):
            raise self.request_stat_result
        if self.request_stat_result is None:
            raise AssertionError("request_stat_result no configurado en stub.")
        return self.request_stat_result

    def send_control_reboot_soft(
        self,
        *,
        node_id: int,
        delay_ms: int = 0,
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
        source: str = "remote_api",
    ) -> ControlTransactionResult:
        _ = (ack_timeout_ms, max_retries)
        self.reboot_calls.append((int(node_id), int(delay_ms), source))
        if isinstance(self.reboot_result, Exception):
            raise self.reboot_result
        if self.reboot_result is None:
            raise AssertionError("reboot_result no configurado en stub.")
        return self.reboot_result


@pytest.fixture
def remote_token_envs(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    envs = {
        "observer_env": "CKV2_REMOTE_API_OBSERVER_TOKEN_TEST",
        "tech_env": "CKV2_REMOTE_API_TECH_TOKEN_TEST",
        "admin_env": "CKV2_REMOTE_API_ADMIN_TOKEN_TEST",
        "legacy_env": "CKV2_REMOTE_API_TOKEN_TEST",
    }
    monkeypatch.setenv(envs["observer_env"], "observer-test-token")
    monkeypatch.setenv(envs["tech_env"], "tech-test-token")
    monkeypatch.setenv(envs["admin_env"], "admin-test-token")
    monkeypatch.setenv(envs["legacy_env"], "legacy-test-token")
    return envs


def _request(
    port: int,
    *,
    method: str,
    path: str,
    token: str | None = None,
    body: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5.0)
    headers = {}
    payload = None
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    connection.request(method, path, body=payload, headers=headers)
    response = connection.getresponse()
    raw = response.read()
    connection.close()
    return response.status, json.loads(raw.decode("utf-8"))


def _session_snapshot(state: SessionState) -> SessionSnapshot:
    return SessionSnapshot(
        state=state,
        active_profile="udp_jardin",
        mode="udp",
        backend=BackendKind.UDP,
        message="Sesion lista.",
        error=None,
        can_start=state is SessionState.IDLE,
        can_stop=state is SessionState.RUNNING,
    )


def _node_snapshot(node_id: int) -> NodeSnapshot:
    return NodeSnapshot(
        node_id=node_id,
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
        last_note=64,
        last_velocity=100,
        last_evt_ts_ms=1234,
        last_evt_flags=0,
        last_state_flags=0,
        last_uptime_s=913,
        reported_pps_x10=10,
        status=NodeStatus.ONLINE,
        vbat_mv=4090,
        free_heap=201344,
        fw_major=1,
        fw_minor=0,
        reset_reason=1,
        health_summary="trafico reciente y stat estable",
        status_reason="stat reciente y sin perdida relevante",
        last_seen_age_s=0.4,
        last_stat_age_s=0.9,
        status_age_s=12.2,
        ota_state_key="idle",
        ota_error_key="none",
        ota_check_pending=False,
        ota_pending_reboot=False,
        ota_pending_verify=False,
        ota_health_confirmed=True,
    )


def _control_plane_snapshot(*, available: bool) -> ControlPlaneRuntimeSnapshot:
    return ControlPlaneRuntimeSnapshot(
        is_available=available,
        listener_active=available,
        ack_port=5008,
        pending_count=0,
        commands_sent_total=5,
        command_retry_total=1,
        command_ack_total=4,
        command_timeout_total=0,
        invalid_ack_total=0,
        unmatched_ack_total=0,
        last_command=None,
        last_result=None,
        per_node_last_status=tuple(),
        recent_results=tuple(),
    )


def _control_plane_node_snapshot(
    *,
    node_id: int,
    resolution_status: ControlPlaneNodeResolutionStatus = ControlPlaneNodeResolutionStatus.RESOLVED,
) -> ControlPlaneNodeSnapshot:
    return ControlPlaneNodeSnapshot(
        node_id=node_id,
        label="EB1",
        resolved_ip="127.0.0.1" if resolution_status is not ControlPlaneNodeResolutionStatus.UNRESOLVED else None,
        resolution_status=resolution_status,
        resolution_age_s=0.2 if resolution_status is not ControlPlaneNodeResolutionStatus.UNRESOLVED else None,
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
        last_uptime_s=913,
        last_reset_reason=1,
        last_boot_marker=1,
        message="Ultimo resultado de control-plane: ack_matched.",
    )


def _ack(node_id: int, cmd_seq: int, cmd_id: int, nonce: int) -> ParsedOkuaAck:
    return ParsedOkuaAck(
        node_id_source=node_id,
        cmd_seq=cmd_seq,
        cmd_id_echo=cmd_id,
        nonce_echo=nonce,
        ack_stage=1,
        status_code=0,
        ack_flags=0,
        err_detail=0,
        retry_after_ms=0,
        auth_tag32=0x11223344,
    )


def _tx_result(
    *,
    command_name: str,
    cmd_id: int,
    node_id: int,
    cmd_seq: int,
    nonce: int,
    final_status: ControlTransactionFinalStatus = ControlTransactionFinalStatus.ACK_MATCHED,
) -> ControlTransactionResult:
    return ControlTransactionResult(
        command_name=command_name,
        cmd_id=cmd_id,
        node_ip="127.0.0.1",
        node_id=node_id,
        cmd_seq=cmd_seq,
        nonce=nonce,
        attempt_count=1,
        final_status=final_status,
        ack=_ack(node_id, cmd_seq, cmd_id, nonce) if final_status is ControlTransactionFinalStatus.ACK_MATCHED else None,
        matched_sent_command=None,
        elapsed_ms=118.4,
        last_error=None if final_status is ControlTransactionFinalStatus.ACK_MATCHED else "Timeout esperando ACK.",
        events=tuple(),
    )


def _service_config(*, envs: dict[str, str], audit_folder: Path) -> RemoteApiConfig:
    return RemoteApiConfig(
        enabled=True,
        bind_host="127.0.0.1",
        port=0,
        auth_mode="bearer_token_inventory",
        token_env_var=envs["legacy_env"],
        tokens=(
            build_remote_api_token_entry(
                env_var=envs["observer_env"],
                role="observador",
                label="observer-main",
            ),
            build_remote_api_token_entry(
                env_var=envs["tech_env"],
                role="tecnico",
                label="tech-main",
            ),
            build_remote_api_token_entry(
                env_var=envs["admin_env"],
                role="admin",
                label="admin-main",
            ),
        ),
        audit_enabled=True,
        audit_folder=str(audit_folder),
    )


def test_remote_api_health_requires_valid_token_and_writes_auth_audit(
    tmp_path: Path,
    remote_token_envs: dict[str, str],
) -> None:
    runtime = _RuntimeStub(
        snapshot=_session_snapshot(SessionState.IDLE),
        node_summary=None,
        nodes={},
        control_plane_snapshot=_control_plane_snapshot(available=False),
        control_nodes={},
    )
    service = RemoteApiService(
        runtime_client=runtime,
        config=_service_config(envs=remote_token_envs, audit_folder=tmp_path / "audit"),
    )
    service.start()
    try:
        status_missing, payload_missing = _request(service.port, method="GET", path="/api/v1/health")
        status_invalid, payload_invalid = _request(
            service.port,
            method="GET",
            path="/api/v1/health",
            token="wrong-token",
        )
        status_forbidden, payload_forbidden = _request(
            service.port,
            method="POST",
            path="/api/v1/nodes/11/actions/request-stat-now",
            token="observer-test-token",
            body={},
        )
        status_ok, payload_ok = _request(
            service.port,
            method="GET",
            path="/api/v1/health",
            token="observer-test-token",
        )
    finally:
        service.stop()

    assert status_missing == 401
    assert payload_missing["error"]["code"] == "unauthorized"
    assert status_invalid == 401
    assert payload_invalid["error"]["code"] == "unauthorized"
    assert status_forbidden == 403
    assert payload_forbidden["error"]["code"] == "forbidden"
    assert status_ok == 200
    assert payload_ok["data"]["service"] == "ckv2-remote-site-service"

    audit_text = service.audit_path.read_text(encoding="utf-8")
    assert "wrong-token" not in audit_text
    assert "observer-test-token" not in audit_text
    assert '"role": "observador"' in audit_text
    assert '"authorization_result": "denied_forbidden_role"' in audit_text


def test_remote_api_read_endpoints_return_runtime_data(
    tmp_path: Path,
    remote_token_envs: dict[str, str],
) -> None:
    node = _node_snapshot(11)
    runtime = _RuntimeStub(
        snapshot=_session_snapshot(SessionState.RUNNING),
        node_summary=NodeRegistrySummary(
            total_nodes=1,
            online_count=1,
            degraded_count=0,
            offline_count=0,
            total_pps_evt=8.0,
            total_pps_stat=1.0,
            calibrating_count=0,
        ),
        nodes={11: node},
        control_plane_snapshot=_control_plane_snapshot(available=True),
        control_nodes={11: _control_plane_node_snapshot(node_id=11)},
    )
    service = RemoteApiService(
        runtime_client=runtime,
        config=_service_config(envs=remote_token_envs, audit_folder=tmp_path / "audit"),
    )
    service.start()
    try:
        health_status, health_payload = _request(
            service.port,
            method="GET",
            path="/api/v1/health",
            token="observer-test-token",
        )
        summary_status, summary_payload = _request(
            service.port,
            method="GET",
            path="/api/v1/runtime/summary",
            token="observer-test-token",
        )
        nodes_status, nodes_payload = _request(
            service.port,
            method="GET",
            path="/api/v1/nodes",
            token="observer-test-token",
        )
        node_status, node_payload = _request(
            service.port,
            method="GET",
            path="/api/v1/nodes/11",
            token="observer-test-token",
        )
    finally:
        service.stop()

    assert health_status == 200
    assert health_payload["data"]["control_plane"]["available"] is True
    assert summary_status == 200
    assert summary_payload["data"]["nodes"]["total_nodes"] == 1
    assert nodes_status == 200
    assert nodes_payload["data"]["nodes"][0]["label"] == "EB3"
    assert node_status == 200
    assert node_payload["data"]["control_plane"]["resolved_ip"] == "127.0.0.1"


def test_remote_api_actions_delegate_to_runtime_and_map_errors(
    tmp_path: Path,
    remote_token_envs: dict[str, str],
) -> None:
    node = _node_snapshot(11)
    runtime = _RuntimeStub(
        snapshot=_session_snapshot(SessionState.RUNNING),
        node_summary=None,
        nodes={11: node},
        control_plane_snapshot=_control_plane_snapshot(available=True),
        control_nodes={11: _control_plane_node_snapshot(node_id=11)},
        request_stat_result=_tx_result(
            command_name="REQUEST_STAT_NOW",
            cmd_id=0x07,
            node_id=11,
            cmd_seq=42,
            nonce=777,
        ),
        reboot_result=_tx_result(
            command_name="REBOOT_SOFT",
            cmd_id=0x02,
            node_id=11,
            cmd_seq=43,
            nonce=778,
        ),
    )
    service = RemoteApiService(
        runtime_client=runtime,
        config=_service_config(envs=remote_token_envs, audit_folder=tmp_path / "audit"),
    )
    service.start()
    try:
        stat_status, stat_payload = _request(
            service.port,
            method="POST",
            path="/api/v1/nodes/11/actions/request-stat-now",
            token="tech-test-token",
            body={},
        )
        forbidden_status, forbidden_payload = _request(
            service.port,
            method="POST",
            path="/api/v1/nodes/11/actions/reboot",
            token="tech-test-token",
            body={"delay_ms": 250},
        )
        reboot_status, reboot_payload = _request(
            service.port,
            method="POST",
            path="/api/v1/nodes/11/actions/reboot",
            token="admin-test-token",
            body={"delay_ms": 250},
        )
    finally:
        service.stop()

    assert stat_status == 200
    assert stat_payload["data"]["result"]["final_status"] == "ack_matched"
    assert runtime.request_stat_calls == [(11, "remote_api")]
    assert forbidden_status == 403
    assert forbidden_payload["error"]["code"] == "forbidden"
    assert reboot_status == 200
    assert reboot_payload["data"]["result"]["cmd_seq"] == 43
    assert runtime.reboot_calls == [(11, 250, "remote_api")]


def test_remote_api_actions_fail_cleanly_when_session_not_running_or_node_unresolved(
    tmp_path: Path,
    remote_token_envs: dict[str, str],
) -> None:
    idle_runtime = _RuntimeStub(
        snapshot=_session_snapshot(SessionState.IDLE),
        node_summary=None,
        nodes={11: _node_snapshot(11)},
        control_plane_snapshot=_control_plane_snapshot(available=False),
        control_nodes={11: _control_plane_node_snapshot(node_id=11)},
        request_stat_result=_tx_result(
            command_name="REQUEST_STAT_NOW",
            cmd_id=0x07,
            node_id=11,
            cmd_seq=42,
            nonce=777,
        ),
    )
    idle_service = RemoteApiService(
        runtime_client=idle_runtime,
        config=_service_config(envs=remote_token_envs, audit_folder=tmp_path / "audit_idle"),
    )
    idle_service.start()
    try:
        idle_status, idle_payload = _request(
            idle_service.port,
            method="POST",
            path="/api/v1/nodes/11/actions/request-stat-now",
            token="tech-test-token",
            body={},
        )
    finally:
        idle_service.stop()

    unresolved_runtime = _RuntimeStub(
        snapshot=_session_snapshot(SessionState.RUNNING),
        node_summary=None,
        nodes={11: _node_snapshot(11)},
        control_plane_snapshot=_control_plane_snapshot(available=True),
        control_nodes={
            11: _control_plane_node_snapshot(
                node_id=11,
                resolution_status=ControlPlaneNodeResolutionStatus.UNRESOLVED,
            )
        },
        request_stat_result=_tx_result(
            command_name="REQUEST_STAT_NOW",
            cmd_id=0x07,
            node_id=11,
            cmd_seq=42,
            nonce=777,
        ),
    )
    unresolved_service = RemoteApiService(
        runtime_client=unresolved_runtime,
        config=_service_config(envs=remote_token_envs, audit_folder=tmp_path / "audit_unresolved"),
    )
    unresolved_service.start()
    try:
        unresolved_status, unresolved_payload = _request(
            unresolved_service.port,
            method="POST",
            path="/api/v1/nodes/11/actions/request-stat-now",
            token="tech-test-token",
            body={},
        )
        missing_status, missing_payload = _request(
            unresolved_service.port,
            method="GET",
            path="/api/v1/nodes/77",
            token="observer-test-token",
        )
    finally:
        unresolved_service.stop()

    assert idle_status == 409
    assert idle_payload["error"]["code"] == "session_not_running"
    assert unresolved_status == 409
    assert unresolved_payload["error"]["code"] == "node_unresolved"
    assert missing_status == 404
    assert missing_payload["error"]["code"] == "node_not_found"


def test_remote_api_service_handles_bind_failure_and_stops_cleanly(
    tmp_path: Path,
    remote_token_envs: dict[str, str],
) -> None:
    runtime = _RuntimeStub(
        snapshot=_session_snapshot(SessionState.IDLE),
        node_summary=None,
        nodes={},
        control_plane_snapshot=_control_plane_snapshot(available=False),
        control_nodes={},
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    occupied_port = sock.getsockname()[1]
    conflicting = RemoteApiService(
        runtime_client=runtime,
        config=RemoteApiConfig(
            enabled=True,
            bind_host="127.0.0.1",
            port=occupied_port,
            auth_mode="bearer_token_inventory",
            token_env_var=remote_token_envs["legacy_env"],
            tokens=(
                build_remote_api_token_entry(
                    env_var=remote_token_envs["observer_env"],
                    role="observador",
                ),
                build_remote_api_token_entry(
                    env_var=remote_token_envs["tech_env"],
                    role="tecnico",
                ),
                build_remote_api_token_entry(
                    env_var=remote_token_envs["admin_env"],
                    role="admin",
                ),
            ),
            audit_enabled=True,
            audit_folder=str(tmp_path / "audit_bind"),
        ),
    )

    with pytest.raises(RemoteApiServiceError):
        conflicting.start()

    sock.close()

    service = RemoteApiService(
        runtime_client=runtime,
        config=_service_config(envs=remote_token_envs, audit_folder=tmp_path / "audit_stop"),
    )
    service.start()
    assert service.is_running is True
    service.stop()
    service.stop()
    assert service.is_running is False


def test_remote_api_service_supports_legacy_single_token_as_admin(
    tmp_path: Path,
    remote_token_envs: dict[str, str],
) -> None:
    runtime = _RuntimeStub(
        snapshot=_session_snapshot(SessionState.IDLE),
        node_summary=None,
        nodes={},
        control_plane_snapshot=_control_plane_snapshot(available=False),
        control_nodes={},
    )
    service = RemoteApiService(
        runtime_client=runtime,
        config=RemoteApiConfig(
            enabled=True,
            bind_host="127.0.0.1",
            port=0,
            auth_mode="bearer_token",
            token_env_var=remote_token_envs["legacy_env"],
            audit_enabled=True,
            audit_folder=str(tmp_path / "audit_legacy"),
        ),
    )
    service.start()
    try:
        status_ok, payload_ok = _request(
            service.port,
            method="GET",
            path="/api/v1/health",
            token="legacy-test-token",
        )
    finally:
        service.stop()

    assert status_ok == 200
    assert payload_ok["ok"] is True
    audit_text = service.audit_path.read_text(encoding="utf-8")
    assert '"authorization_result": "granted_legacy_admin"' in audit_text
