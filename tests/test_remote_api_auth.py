from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.services.remote_api_auth import (  # noqa: E402
    RemoteApiAuthConfigError,
    RemoteApiForbiddenError,
    RemoteApiUnauthorizedError,
    authenticate_bearer_request,
    authorize_remote_api_action,
    build_actor_id_for_token,
    build_remote_api_token_entry,
    build_token_fingerprint,
    resolve_expected_bearer_token,
    resolve_remote_api_token_bindings,
)
from control_okua.services.remote_api_contract import RemoteApiConfig  # noqa: E402


def test_build_token_fingerprint_and_actor_id_do_not_expose_plain_token() -> None:
    token = "super-secret-remote-token"

    fingerprint = build_token_fingerprint(token)
    actor_id = build_actor_id_for_token(token)

    assert token not in fingerprint
    assert token not in actor_id
    assert actor_id.startswith("remote_api_token:")
    assert len(fingerprint) == 12


def test_build_remote_api_token_entry_validates_role_and_env_var() -> None:
    entry = build_remote_api_token_entry(
        env_var=" CKV2_REMOTE_API_ADMIN_TOKEN ",
        role="admin",
        label=" admin-main ",
    )

    assert entry.env_var == "CKV2_REMOTE_API_ADMIN_TOKEN"
    assert entry.role == "admin"
    assert entry.label == "admin-main"

    with pytest.raises(RemoteApiAuthConfigError):
        build_remote_api_token_entry(env_var=" ", role="admin")

    with pytest.raises(RemoteApiAuthConfigError):
        build_remote_api_token_entry(env_var="CKV2_ROLELESS", role="root")


def test_resolve_expected_bearer_token_requires_present_non_empty_env_var() -> None:
    with pytest.raises(RemoteApiAuthConfigError):
        resolve_expected_bearer_token("CKV2_REMOTE_API_TOKEN", environ={})

    with pytest.raises(RemoteApiAuthConfigError):
        resolve_expected_bearer_token(
            "CKV2_REMOTE_API_TOKEN",
            environ={"CKV2_REMOTE_API_TOKEN": "   "},
        )

    assert (
        resolve_expected_bearer_token(
            "CKV2_REMOTE_API_TOKEN",
            environ={"CKV2_REMOTE_API_TOKEN": "token-ok"},
        )
        == "token-ok"
    )


def test_resolve_remote_api_token_bindings_accepts_inventory_and_labels() -> None:
    config = RemoteApiConfig(
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

    bindings = resolve_remote_api_token_bindings(
        config,
        environ={
            "CKV2_REMOTE_API_OBSERVER_TOKEN": "observer-token",
            "CKV2_REMOTE_API_TECH_TOKEN": "tech-token",
            "CKV2_REMOTE_API_ADMIN_TOKEN": "admin-token",
        },
    )

    assert tuple(binding.role for binding in bindings) == ("observador", "tecnico", "admin")
    assert tuple(binding.token_label for binding in bindings) == (
        "observer-main",
        "tech-main",
        "admin-main",
    )
    assert all(binding.granted_authorization_result == "granted" for binding in bindings)


def test_resolve_remote_api_token_bindings_rejects_missing_or_duplicate_tokens() -> None:
    inventory_config = RemoteApiConfig(
        auth_mode="bearer_token_inventory",
        tokens=(
            build_remote_api_token_entry(
                env_var="CKV2_REMOTE_API_OBSERVER_TOKEN",
                role="observador",
            ),
        ),
    )

    with pytest.raises(RemoteApiAuthConfigError):
        resolve_remote_api_token_bindings(inventory_config, environ={})

    duplicate_config = RemoteApiConfig(
        auth_mode="bearer_token_inventory",
        tokens=(
            build_remote_api_token_entry(
                env_var="CKV2_REMOTE_API_OBSERVER_TOKEN",
                role="observador",
            ),
            build_remote_api_token_entry(
                env_var="CKV2_REMOTE_API_ADMIN_TOKEN",
                role="admin",
            ),
        ),
    )

    with pytest.raises(RemoteApiAuthConfigError):
        resolve_remote_api_token_bindings(
            duplicate_config,
            environ={
                "CKV2_REMOTE_API_OBSERVER_TOKEN": "same-token",
                "CKV2_REMOTE_API_ADMIN_TOKEN": "same-token",
            },
        )


def test_authenticate_bearer_request_rejects_missing_and_invalid_token() -> None:
    bindings = resolve_remote_api_token_bindings(
        RemoteApiConfig(
            auth_mode="bearer_token_inventory",
            tokens=(
                build_remote_api_token_entry(
                    env_var="CKV2_REMOTE_API_ADMIN_TOKEN",
                    role="admin",
                ),
            ),
        ),
        environ={"CKV2_REMOTE_API_ADMIN_TOKEN": "admin-token"},
    )

    with pytest.raises(RemoteApiUnauthorizedError) as missing_exc:
        authenticate_bearer_request(None, token_bindings=bindings)

    assert missing_exc.value.actor_type == "anonymous"
    assert missing_exc.value.authorization_result == "denied_missing_token"

    with pytest.raises(RemoteApiUnauthorizedError) as invalid_exc:
        authenticate_bearer_request(
            "Bearer wrong-token",
            token_bindings=bindings,
        )

    assert invalid_exc.value.actor_type == "technical_token"
    assert invalid_exc.value.authorization_result == "denied_invalid_token"
    assert "wrong-token" not in invalid_exc.value.actor_id


def test_authenticate_bearer_request_resolves_inventory_roles() -> None:
    bindings = resolve_remote_api_token_bindings(
        RemoteApiConfig(
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
        ),
        environ={
            "CKV2_REMOTE_API_OBSERVER_TOKEN": "observer-token",
            "CKV2_REMOTE_API_TECH_TOKEN": "tech-token",
            "CKV2_REMOTE_API_ADMIN_TOKEN": "admin-token",
        },
    )

    observer = authenticate_bearer_request("Bearer observer-token", token_bindings=bindings)
    technician = authenticate_bearer_request("Bearer tech-token", token_bindings=bindings)
    admin = authenticate_bearer_request("Bearer admin-token", token_bindings=bindings)

    assert observer.role == "observador"
    assert observer.token_label == "observer-main"
    assert observer.authorization_result == "granted"
    assert technician.role == "tecnico"
    assert admin.role == "admin"


def test_authenticate_bearer_request_supports_legacy_single_token_as_admin() -> None:
    bindings = resolve_remote_api_token_bindings(
        RemoteApiConfig(
            auth_mode="bearer_token",
            token_env_var="CKV2_REMOTE_API_TOKEN",
        ),
        environ={"CKV2_REMOTE_API_TOKEN": "legacy-token"},
    )

    context = authenticate_bearer_request(
        "Bearer legacy-token",
        token_bindings=bindings,
    )

    assert context.role == "admin"
    assert context.token_label == "legacy-admin"
    assert context.authorization_result == "granted_legacy_admin"


def test_authorize_remote_api_action_enforces_v1_role_matrix() -> None:
    authorize_remote_api_action(
        role="observador",
        action="health.read",
        actor_type="technical_token",
        actor_id="remote_api_token:observer",
    )
    authorize_remote_api_action(
        role="tecnico",
        action="node.request_stat_now",
        actor_type="technical_token",
        actor_id="remote_api_token:tech",
    )
    authorize_remote_api_action(
        role="admin",
        action="node.reboot",
        actor_type="technical_token",
        actor_id="remote_api_token:admin",
    )

    with pytest.raises(RemoteApiForbiddenError):
        authorize_remote_api_action(
            role="observador",
            action="node.request_stat_now",
            actor_type="technical_token",
            actor_id="remote_api_token:observer",
        )

    with pytest.raises(RemoteApiForbiddenError):
        authorize_remote_api_action(
            role="tecnico",
            action="node.reboot",
            actor_type="technical_token",
            actor_id="remote_api_token:tech",
        )
