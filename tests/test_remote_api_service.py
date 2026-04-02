from __future__ import annotations

from dataclasses import dataclass, field
from http.client import HTTPConnection
import json
from pathlib import Path
import socket
import sys

import pytest


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.control_plane.protocol import ParsedOkuaAck  # noqa: E402
from control_okua.core.control_plane.runtime import ControlPlaneRuntimeSnapshot  # noqa: E402
from control_okua.core.control_plane.runtime_snapshot import (  # noqa: E402
    ControlPlaneNodeResolutionStatus,
    ControlPlaneNodeSnapshot,
)
from control_okua.core.registry.node_models import (  # noqa: E402
    NodeRegistrySummary,
    NodeSnapshot,
    NodeStatus,
)
from control_okua.core.session import BackendKind, SessionSnapshot, SessionState  # noqa: E402
from control_okua.services.control_transaction_service import (  # noqa: E402
    ControlTransactionFinalStatus,
    ControlTransactionResult,
)
from control_okua.services.remote_api_auth import build_remote_api_token_entry  # noqa: E402
from control_okua.services.remote_api_contract import RemoteApiConfig  # noqa: E402
from control_okua.services.remote_api_service import RemoteApiService, RemoteApiServiceError  # noqa: E402
import control_okua.services.remote_api_service as remote_api_service_module  # noqa: E402


@dataclass
class _RuntimeStub:
    snapshot: SessionSnapshot
    node_summary: NodeRegistrySummary | None
    nodes: dict[int, NodeSnapshot]
    control_plane_snapshot: ControlPlaneRuntimeSnapshot
    control_nodes: dict[int, ControlPlaneNodeSnapshot]
    request_stat_result: ControlTransactionResult | None = None
    reboot_result: ControlTransactionResult | None = None
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

    def get_control_plane_node_snapshot(self, node_id: int, now: float | None = None) -> ControlPlaneNodeSnapshot | None:
        _ = now
        return self.control_nodes.get(int(node_id))

    def send_control_request_stat_now(self, *, node_id: int, source: str = "remote_api", **_: object) -> ControlTransactionResult:
        self.request_stat_calls.append((int(node_id), source))
        assert self.request_stat_result is not None
        return self.request_stat_result

    def send_control_reboot_soft(self, *, node_id: int, delay_ms: int = 0, source: str = "remote_api", **_: object) -> ControlTransactionResult:
        self.reboot_calls.append((int(node_id), int(delay_ms), source))
        assert self.reboot_result is not None
        return self.reboot_result


@pytest.fixture
def remote_token_envs(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    envs = {
        "observer_env": "CKV2_REMOTE_API_OBSERVER_TOKEN_TEST",
        "tech_env": "CKV2_REMOTE_API_TECH_TOKEN_TEST",
        "admin_env": "CKV2_REMOTE_API_ADMIN_TOKEN_TEST",
    }
    monkeypatch.setenv(envs["observer_env"], "observer-test-token")
    monkeypatch.setenv(envs["tech_env"], "tech-test-token")
    monkeypatch.setenv(envs["admin_env"], "admin-test-token")
    return envs


def _request(port: int, *, method: str, path: str, body: dict[str, object] | None = None, cookie: str | None = None, token: str | None = None) -> tuple[int, dict[str, object], dict[str, str]]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5.0)
    headers: dict[str, str] = {}
    payload = None
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if cookie is not None:
        headers["Cookie"] = cookie
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    connection.request(method, path, body=payload, headers=headers)
    response = connection.getresponse()
    raw = response.read().decode("utf-8")
    response_headers = {key.lower(): value for key, value in response.getheaders()}
    status = response.status
    connection.close()
    return status, json.loads(raw), response_headers


def _request_raw(port: int, *, path: str) -> tuple[int, str, str]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5.0)
    connection.request("GET", path)
    response = connection.getresponse()
    raw = response.read().decode("utf-8")
    content_type = response.getheader("Content-Type", "")
    status = response.status
    connection.close()
    return status, content_type, raw


def _runtime_stub() -> _RuntimeStub:
    return _RuntimeStub(
        snapshot=SessionSnapshot(
            state=SessionState.RUNNING,
            active_profile="udp_jardin",
            mode="udp",
            backend=BackendKind.UDP,
            message="Sesion lista.",
            error=None,
            can_start=False,
            can_stop=True,
        ),
        node_summary=NodeRegistrySummary(
            total_nodes=1,
            online_count=1,
            degraded_count=0,
            offline_count=0,
            calibrating_count=0,
            total_pps_evt=8.0,
            total_pps_stat=1.0,
        ),
        nodes={11: _node_snapshot(11)},
        control_plane_snapshot=_control_plane_snapshot(available=True),
        control_nodes={11: _control_plane_node_snapshot(node_id=11)},
        request_stat_result=_tx_result(command_name="REQUEST_STAT_NOW", cmd_id=2, node_id=11, cmd_seq=41, nonce=501),
        reboot_result=_tx_result(command_name="REBOOT_SOFT", cmd_id=3, node_id=11, cmd_seq=42, nonce=777),
    )


def _node_snapshot(node_id: int) -> NodeSnapshot:
    return NodeSnapshot(node_id=node_id, label=None, node_type=None, last_seen_pc_ts=100.0, last_seq_evt=1, last_seq_stat=1, pps_evt=8.0, pps_stat=1.0, loss_evt_pct=0.0, loss_stat_pct=0.0, rssi_dbm=-57, last_note=64, last_velocity=100, last_evt_ts_ms=1234, last_evt_flags=0, last_state_flags=0, last_uptime_s=913, reported_pps_x10=10, status=NodeStatus.ONLINE, vbat_mv=4090, free_heap=201344, fw_major=1, fw_minor=0, reset_reason=1, health_summary="trafico reciente y stat estable", status_reason="stat reciente y sin perdida relevante", last_seen_age_s=0.4, last_stat_age_s=0.9, status_age_s=12.2, ota_state_key="idle", ota_error_key="none", ota_check_pending=False, ota_pending_reboot=False, ota_pending_verify=False, ota_health_confirmed=True)


def _control_plane_snapshot(*, available: bool) -> ControlPlaneRuntimeSnapshot:
    return ControlPlaneRuntimeSnapshot(is_available=available, listener_active=available, ack_port=5008, pending_count=0, commands_sent_total=5, command_retry_total=1, command_ack_total=4, command_timeout_total=0, invalid_ack_total=0, unmatched_ack_total=0, last_command=None, last_result=None, per_node_last_status=tuple(), recent_results=tuple())


def _control_plane_node_snapshot(*, node_id: int, resolution_status: ControlPlaneNodeResolutionStatus = ControlPlaneNodeResolutionStatus.RESOLVED) -> ControlPlaneNodeSnapshot:
    return ControlPlaneNodeSnapshot(node_id=node_id, label="EB1", resolved_ip="127.0.0.1" if resolution_status is not ControlPlaneNodeResolutionStatus.UNRESOLVED else None, resolution_status=resolution_status, resolution_age_s=0.2 if resolution_status is not ControlPlaneNodeResolutionStatus.UNRESOLVED else None, last_seen_pc_ts=100.0, transaction_active=False, last_command_name="REQUEST_STAT_NOW", last_cmd_seq=42, last_nonce=777, last_final_status="ack_matched", last_ack_stage=1, last_status_code=0, last_err_detail=0, last_error_message=None, last_tx_started_at="2026-04-02T20:11:43.101Z", last_tx_finished_at="2026-04-02T20:11:43.551Z", last_reboot_verification_status="confirmed", last_reboot_verification_summary="Nodo visible tras reboot esperado.", last_uptime_s=913, last_reset_reason=1, last_boot_marker=1, message="Ultimo resultado de control-plane: ack_matched.")


def _ack(node_id: int, cmd_seq: int, cmd_id: int, nonce: int) -> ParsedOkuaAck:
    return ParsedOkuaAck(node_id_source=node_id, cmd_seq=cmd_seq, cmd_id_echo=cmd_id, nonce_echo=nonce, ack_stage=1, status_code=0, ack_flags=0, err_detail=0, retry_after_ms=0, auth_tag32=0x11223344)


def _tx_result(*, command_name: str, cmd_id: int, node_id: int, cmd_seq: int, nonce: int) -> ControlTransactionResult:
    return ControlTransactionResult(command_name=command_name, cmd_id=cmd_id, node_ip="127.0.0.1", node_id=node_id, cmd_seq=cmd_seq, nonce=nonce, attempt_count=1, final_status=ControlTransactionFinalStatus.ACK_MATCHED, ack=_ack(node_id, cmd_seq, cmd_id, nonce), matched_sent_command=None, elapsed_ms=118.4, last_error=None, events=tuple())


def _service_config(tmp_path: Path, envs: dict[str, str]) -> RemoteApiConfig:
    return RemoteApiConfig(enabled=True, bind_host="127.0.0.1", port=0, auth_mode="bearer_token_inventory", tokens=(build_remote_api_token_entry(env_var=envs["observer_env"], role="observador"), build_remote_api_token_entry(env_var=envs["tech_env"], role="tecnico"), build_remote_api_token_entry(env_var=envs["admin_env"], role="admin")), audit_enabled=True, audit_folder=str(tmp_path / "audit"), user_store_filename="remote_api_users.json", session_ttl_s=3600)


def test_remote_api_serves_assets_and_supports_legacy_bearer(tmp_path: Path, remote_token_envs: dict[str, str]) -> None:
    service = RemoteApiService(runtime_client=_runtime_stub(), config=_service_config(tmp_path, remote_token_envs), config_path=tmp_path / "config.json")
    service.start()
    try:
        status_html, content_type_html, raw_html = _request_raw(service.port, path="/remote/")
        status_js, content_type_js, _ = _request_raw(service.port, path="/remote/app.js")
        status_css, content_type_css, _ = _request_raw(service.port, path="/remote/styles.css")
        status_health, payload_health, _ = _request(service.port, method="GET", path="/api/v1/health", token="observer-test-token")
    finally:
        service.stop()

    assert status_html == 200
    assert "text/html" in content_type_html
    assert "Bootstrap inicial" in raw_html
    assert status_js == 200 and "javascript" in content_type_js
    assert status_css == 200 and "text/css" in content_type_css
    assert status_health == 200
    assert payload_health["ok"] is True


def test_remote_api_bootstrap_login_logout_and_role_authorization(tmp_path: Path, remote_token_envs: dict[str, str]) -> None:
    service = RemoteApiService(runtime_client=_runtime_stub(), config=_service_config(tmp_path, remote_token_envs), config_path=tmp_path / "config.json")
    service.start()
    try:
        status_session, payload_session, _ = _request(service.port, method="GET", path="/api/v1/auth/session")
        assert status_session == 200
        assert payload_session["data"]["bootstrap_required"] is True

        status_bootstrap, payload_bootstrap, headers_bootstrap = _request(service.port, method="POST", path="/api/v1/auth/bootstrap", body={"accounts": [{"username": "admin.okua", "password": "AdminPass123!", "role": "admin"}, {"username": "tecnico.okua", "password": "TechPass123!", "role": "tecnico"}, {"username": "observador.okua", "password": "ObserverPass123!", "role": "observador"}]})
        admin_cookie = headers_bootstrap.get("set-cookie")
        assert status_bootstrap == 200
        assert payload_bootstrap["data"]["authenticated"] is True
        assert admin_cookie

        status_reboot, _, _ = _request(service.port, method="POST", path="/api/v1/nodes/11/actions/reboot", cookie=admin_cookie, body={"delay_ms": 0})
        assert status_reboot == 200

        _request(service.port, method="POST", path="/api/v1/auth/logout", cookie=admin_cookie)

        status_login_tech, payload_login_tech, headers_login_tech = _request(service.port, method="POST", path="/api/v1/auth/login", body={"username": "tecnico.okua", "password": "TechPass123!"})
        tech_cookie = headers_login_tech.get("set-cookie")
        assert status_login_tech == 200
        assert payload_login_tech["data"]["user"]["role"] == "tecnico"

        status_request, _, _ = _request(service.port, method="POST", path="/api/v1/nodes/11/actions/request-stat-now", cookie=tech_cookie, body={})
        status_forbidden, payload_forbidden, _ = _request(service.port, method="POST", path="/api/v1/nodes/11/actions/reboot", cookie=tech_cookie, body={"delay_ms": 0})
        assert status_request == 200
        assert status_forbidden == 403
        assert payload_forbidden["error"]["code"] == "forbidden"

        _request(service.port, method="POST", path="/api/v1/auth/logout", cookie=tech_cookie)

        status_login_obs, payload_login_obs, headers_login_obs = _request(service.port, method="POST", path="/api/v1/auth/login", body={"username": "observador.okua", "password": "ObserverPass123!"})
        observer_cookie = headers_login_obs.get("set-cookie")
        assert status_login_obs == 200
        assert payload_login_obs["data"]["user"]["role"] == "observador"

        status_summary, _, _ = _request(service.port, method="GET", path="/api/v1/runtime/summary", cookie=observer_cookie)
        status_observer_action, payload_observer_action, _ = _request(service.port, method="POST", path="/api/v1/nodes/11/actions/request-stat-now", cookie=observer_cookie, body={})
        assert status_summary == 200
        assert status_observer_action == 403
        assert payload_observer_action["error"]["code"] == "forbidden"
    finally:
        service.stop()

    audit_text = service.audit_path.read_text(encoding="utf-8")
    assert '"action": "auth.bootstrap"' in audit_text
    assert '"action": "auth.login"' in audit_text
    assert '"action": "auth.logout"' in audit_text
    assert '"role": "admin"' in audit_text
    assert "AdminPass123!" not in audit_text
    assert "ObserverPass123!" not in audit_text


def test_remote_api_account_management_is_admin_only_and_disabled_session_stops_working(tmp_path: Path, remote_token_envs: dict[str, str]) -> None:
    service = RemoteApiService(runtime_client=_runtime_stub(), config=_service_config(tmp_path, remote_token_envs), config_path=tmp_path / "config.json")
    service.start()
    try:
        status_bootstrap, _, headers_bootstrap = _request(service.port, method="POST", path="/api/v1/auth/bootstrap", body={"accounts": [{"username": "admin.okua", "password": "AdminPass123!", "role": "admin"}, {"username": "tecnico.okua", "password": "TechPass123!", "role": "tecnico"}, {"username": "observador.okua", "password": "ObserverPass123!", "role": "observador"}]})
        admin_cookie = headers_bootstrap.get("set-cookie")
        assert status_bootstrap == 200

        status_accounts, payload_accounts, _ = _request(service.port, method="GET", path="/api/v1/accounts", cookie=admin_cookie)
        assert status_accounts == 200
        assert len(payload_accounts["data"]["users"]) == 3

        status_create, payload_create, _ = _request(service.port, method="POST", path="/api/v1/accounts", cookie=admin_cookie, body={"username": "aux.okua", "password": "AuxPass123!", "role": "tecnico", "enabled": True, "notes": "Auxiliar"})
        assert status_create == 201
        assert payload_create["data"]["user"]["username"] == "aux.okua"

        status_login_aux, _, headers_aux = _request(service.port, method="POST", path="/api/v1/auth/login", body={"username": "aux.okua", "password": "AuxPass123!"})
        aux_cookie = headers_aux.get("set-cookie")
        assert status_login_aux == 200

        status_forbidden, payload_forbidden, _ = _request(service.port, method="GET", path="/api/v1/accounts", cookie=aux_cookie)
        assert status_forbidden == 403
        assert payload_forbidden["error"]["code"] == "forbidden"

        status_patch, payload_patch, _ = _request(service.port, method="PATCH", path="/api/v1/accounts/aux.okua", cookie=admin_cookie, body={"enabled": False, "role": "tecnico", "username": "aux.okua", "notes": "Suspendido"})
        assert status_patch == 200
        assert payload_patch["data"]["user"]["enabled"] is False

        status_disabled, payload_disabled, _ = _request(service.port, method="GET", path="/api/v1/health", cookie=aux_cookie)
        assert status_disabled == 401
        assert payload_disabled["error"]["code"] == "unauthorized"

        status_password, _, _ = _request(service.port, method="POST", path="/api/v1/accounts/tecnico.okua/password", cookie=admin_cookie, body={"new_password": "TechPass456!"})
        assert status_password == 200

        status_delete, payload_delete, _ = _request(service.port, method="DELETE", path="/api/v1/accounts/aux.okua", cookie=admin_cookie)
        assert status_delete == 200
        assert payload_delete["data"]["deleted_username"] == "aux.okua"
    finally:
        service.stop()

    audit_text = service.audit_path.read_text(encoding="utf-8")
    assert '"action": "accounts.read"' in audit_text
    assert '"action": "account.create"' in audit_text
    assert '"action": "account.update"' in audit_text
    assert '"action": "account.change_password"' in audit_text
    assert '"action": "account.delete"' in audit_text
    assert "AuxPass123!" not in audit_text


def test_remote_api_bind_failure_is_reported_cleanly(tmp_path: Path, remote_token_envs: dict[str, str]) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]
    config = RemoteApiConfig(enabled=True, bind_host="127.0.0.1", port=port, auth_mode="bearer_token_inventory", tokens=(build_remote_api_token_entry(env_var=remote_token_envs["admin_env"], role="admin"),), audit_enabled=False, audit_folder=str(tmp_path / "audit"), user_store_filename="remote_api_users.json", session_ttl_s=3600)
    service = RemoteApiService(runtime_client=_runtime_stub(), config=config, config_path=tmp_path / "config.json")
    try:
        with pytest.raises(RemoteApiServiceError):
            service.start()
    finally:
        sock.close()


def test_remote_api_server_swallows_benign_disconnect_traces(
    tmp_path: Path,
    remote_token_envs: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RemoteApiService(
        runtime_client=_runtime_stub(),
        config=_service_config(tmp_path, remote_token_envs),
        config_path=tmp_path / "config.json",
    )
    server = remote_api_service_module._RemoteApiHttpServer(("127.0.0.1", 0), service)
    try:
        exc = ConnectionResetError("peer closed")
        monkeypatch.setattr(
            remote_api_service_module.sys,
            "exc_info",
            lambda: (ConnectionResetError, exc, None),
        )
        server.handle_error(object(), ("127.0.0.1", 54321))
    finally:
        server.server_close()


def test_remote_console_asset_path_supports_frozen_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle_root = tmp_path / "bundle"
    asset_path = (
        bundle_root
        / "src"
        / "control_okua"
        / "services"
        / "remote_console_assets"
        / "index.html"
    )
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_text("<html>bundled</html>", encoding="utf-8")

    monkeypatch.setattr(remote_api_service_module.sys, "_MEIPASS", str(bundle_root), raising=False)

    resolved = remote_api_service_module._remote_console_asset_path("index.html")

    assert resolved == asset_path
