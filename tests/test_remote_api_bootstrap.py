from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.services.remote_api_auth import build_remote_api_token_entry  # noqa: E402
from control_okua.services.remote_api_bootstrap import (  # noqa: E402
    build_remote_api_exposure_status,
    build_remote_api_access_urls,
    ensure_remote_api_local_credentials,
    ensure_remote_api_runtime_config,
    resolve_remote_api_bind_host,
)
from control_okua.services.remote_api_contract import RemoteApiConfig  # noqa: E402


def test_ensure_remote_api_runtime_config_infers_exposure_mode_and_inventory() -> None:
    cfg = {
        "remote_api": {
            "enabled": True,
            "bind_host": "0.0.0.0",
            "port": 8788,
            "auth_mode": "bearer_token_inventory",
            "token_env_var": "CKV2_REMOTE_API_TOKEN",
            "tokens": [],
            "audit_enabled": True,
            "audit_folder": "logs/remote_api",
        }
    }

    updated_cfg, warnings, changed = ensure_remote_api_runtime_config(cfg)

    assert changed is True
    assert updated_cfg["remote_api"]["exposure_mode"] == "custom_bind"
    assert len(updated_cfg["remote_api"]["tokens"]) == 3
    assert "remote_api.exposure_mode ausente o invalido; se infirio desde bind_host." in warnings


def test_ensure_remote_api_local_credentials_generates_and_reuses_local_token_store(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.json"
    config = RemoteApiConfig(
        enabled=True,
        bind_host="0.0.0.0",
        port=8788,
        auth_mode="bearer_token_inventory",
        tokens=(
            build_remote_api_token_entry(
                env_var="CKV2_REMOTE_API_OBSERVER_TOKEN",
                role="observador",
                label="observer-main",
            ),
            build_remote_api_token_entry(
                env_var="CKV2_REMOTE_API_TECH_TOKEN",
                role="tecnico",
                label="tech-main",
            ),
            build_remote_api_token_entry(
                env_var="CKV2_REMOTE_API_ADMIN_TOKEN",
                role="admin",
                label="admin-main",
            ),
        ),
    )
    env_map: dict[str, str] = {}

    first = ensure_remote_api_local_credentials(
        config,
        config_path=config_path,
        environ=env_map,
    )

    assert first.secrets_path.exists()
    assert first.access_note_path.exists()
    assert len(first.credentials) == 3
    assert env_map["CKV2_REMOTE_API_OBSERVER_TOKEN"]
    assert "role=observador" in first.access_note_path.read_text(encoding="utf-8")

    saved_store = json.loads(first.secrets_path.read_text(encoding="utf-8"))
    assert len(saved_store["tokens"]) == 3

    env_map_second: dict[str, str] = {}
    second = ensure_remote_api_local_credentials(
        config,
        config_path=config_path,
        environ=env_map_second,
    )

    first_tokens = {item.env_var: item.token for item in first.credentials}
    second_tokens = {item.env_var: item.token for item in second.credentials}
    assert first_tokens == second_tokens
    assert env_map_second["CKV2_REMOTE_API_ADMIN_TOKEN"] == first_tokens["CKV2_REMOTE_API_ADMIN_TOKEN"]


def test_build_remote_api_access_urls_includes_hostname_and_tailscale_magicdns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = RemoteApiConfig(
        enabled=True,
        exposure_mode="custom_bind",
        bind_host="0.0.0.0",
        port=8788,
        auth_mode="human_session_only",
    )
    monkeypatch.setattr(
        "control_okua.services.remote_api_bootstrap._discover_access_hostnames",
        lambda: ("turnflow-servidor", "turnflow-servidor.tailnet.ts.net"),
    )
    monkeypatch.setattr(
        "control_okua.services.remote_api_bootstrap._discover_local_ipv4_addresses",
        lambda: ("192.168.80.14",),
    )

    urls = build_remote_api_access_urls(config)

    assert "http://127.0.0.1:8788/remote/" in urls
    assert "http://turnflow-servidor:8788/remote/" in urls
    assert "http://turnflow-servidor.tailnet.ts.net:8788/remote/" in urls
    assert "http://192.168.80.14:8788/remote/" in urls


def test_resolve_remote_api_bind_host_for_tailscale_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = RemoteApiConfig(
        enabled=True,
        exposure_mode="tailscale_only",
        port=8788,
        auth_mode="human_session_only",
    )
    monkeypatch.setattr(
        "control_okua.services.remote_api_bootstrap._discover_tailscale_ipv4_address",
        lambda: "100.88.127.119",
    )

    bind_host = resolve_remote_api_bind_host(config)
    status = build_remote_api_exposure_status(config, effective_bind_host=bind_host)

    assert bind_host == "100.88.127.119"
    assert status.remote_access_url == "http://100.88.127.119:8788/remote/"


def test_resolve_remote_api_bind_host_fails_cleanly_without_tailscale_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = RemoteApiConfig(
        enabled=True,
        exposure_mode="tailscale_only",
        port=8788,
        auth_mode="human_session_only",
    )
    monkeypatch.setattr(
        "control_okua.services.remote_api_bootstrap._discover_tailscale_ipv4_address",
        lambda: "",
    )

    with pytest.raises(RuntimeError):
        resolve_remote_api_bind_host(config)
