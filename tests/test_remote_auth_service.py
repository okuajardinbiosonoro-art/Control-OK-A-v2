from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.services.remote_auth_service import (  # noqa: E402
    RemoteAuthService,
    RemoteAuthServiceError,
    hash_remote_password,
    verify_remote_password,
)
from control_okua.services.remote_user_store import RemoteUserStore  # noqa: E402


def test_remote_auth_password_hashing_uses_salt_and_verification(tmp_path: Path) -> None:
    password = "ClaveSegura123!"
    first = hash_remote_password(password)
    second = hash_remote_password(password)

    assert first != password
    assert second != password
    assert first != second
    assert verify_remote_password(password, first) is True
    assert verify_remote_password("otra-clave", first) is False


def test_remote_auth_bootstrap_login_and_user_management(tmp_path: Path) -> None:
    auth = RemoteAuthService(RemoteUserStore(tmp_path / "remote_api_users.json"))

    created = auth.bootstrap_initial_accounts(
        [
            {
                "username": "admin.okua",
                "password": "AdminPass123!",
                "role": "admin",
            },
            {
                "username": "tecnico.okua",
                "password": "TechPass123!",
                "role": "tecnico",
            },
            {
                "username": "observador.okua",
                "password": "ObserverPass123!",
                "role": "observador",
            },
        ]
    )

    assert {item.role for item in created} == {"admin", "tecnico", "observador"}

    admin = auth.authenticate_credentials(
        username="admin.okua",
        password="AdminPass123!",
    )
    assert admin.role == "admin"

    created_user = auth.create_user(
        username="aux.okua",
        password="Auxiliar123!",
        role="observador",
        notes="Prueba",
    )
    assert created_user.username == "aux.okua"

    updated = auth.update_user_profile(
        username="aux.okua",
        role="tecnico",
        enabled=False,
        notes="Deshabilitado",
    )
    assert updated.role == "tecnico"
    assert updated.enabled is False

    changed = auth.change_password(
        username="tecnico.okua",
        new_password="TechPass456!",
    )
    assert changed.last_password_change_at

    auth.delete_user(username="aux.okua")
    assert auth.get_user("aux.okua") is None


def test_remote_auth_rejects_incomplete_bootstrap_and_invalid_login(tmp_path: Path) -> None:
    auth = RemoteAuthService(RemoteUserStore(tmp_path / "remote_api_users.json"))

    with pytest.raises(RemoteAuthServiceError) as bootstrap_exc:
        auth.bootstrap_initial_accounts(
            [
                {
                    "username": "admin.okua",
                    "password": "AdminPass123!",
                    "role": "admin",
                }
            ]
        )

    assert bootstrap_exc.value.code == "invalid_bootstrap"

    auth.bootstrap_initial_accounts(
        [
            {
                "username": "admin.okua",
                "password": "AdminPass123!",
                "role": "admin",
            },
            {
                "username": "tecnico.okua",
                "password": "TechPass123!",
                "role": "tecnico",
            },
            {
                "username": "observador.okua",
                "password": "ObserverPass123!",
                "role": "observador",
            },
        ]
    )

    with pytest.raises(RemoteAuthServiceError) as login_exc:
        auth.authenticate_credentials(
            username="admin.okua",
            password="mala-clave",
        )

    assert login_exc.value.code == "invalid_credentials"
