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
    RemoteApiUnauthorizedError,
    authenticate_bearer_request,
    build_actor_id_for_token,
    build_token_fingerprint,
    resolve_expected_bearer_token,
)


def test_build_token_fingerprint_and_actor_id_do_not_expose_plain_token() -> None:
    token = "super-secret-remote-token"

    fingerprint = build_token_fingerprint(token)
    actor_id = build_actor_id_for_token(token)

    assert token not in fingerprint
    assert token not in actor_id
    assert actor_id.startswith("remote_api_token:")
    assert len(fingerprint) == 12


def test_authenticate_bearer_request_rejects_missing_token() -> None:
    with pytest.raises(RemoteApiUnauthorizedError) as excinfo:
        authenticate_bearer_request(None, expected_token="expected-token")

    assert excinfo.value.actor_type == "anonymous"
    assert excinfo.value.actor_id == "anonymous"


def test_authenticate_bearer_request_rejects_invalid_token() -> None:
    with pytest.raises(RemoteApiUnauthorizedError) as excinfo:
        authenticate_bearer_request(
            "Bearer wrong-token",
            expected_token="expected-token",
        )

    assert excinfo.value.actor_type == "technical_token"
    assert excinfo.value.actor_id.startswith("remote_api_token:")
    assert "wrong-token" not in excinfo.value.actor_id


def test_authenticate_bearer_request_accepts_valid_token() -> None:
    context = authenticate_bearer_request(
        "Bearer expected-token",
        expected_token="expected-token",
    )

    assert context.actor_type == "technical_token"
    assert context.actor_id == build_actor_id_for_token("expected-token")


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
