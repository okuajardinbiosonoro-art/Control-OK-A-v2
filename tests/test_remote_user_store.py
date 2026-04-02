from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.services.remote_user_store import (  # noqa: E402
    RemoteUserStore,
    RemoteUserStoreError,
    build_remote_user_record,
)


def test_remote_user_store_create_update_delete_and_reload(tmp_path: Path) -> None:
    store_path = tmp_path / "remote_api_users.json"
    store = RemoteUserStore(store_path)

    created = store.bootstrap_users(
        [
            build_remote_user_record(
                username="admin.okua",
                password_hash="hash-admin",
                role="admin",
            )
        ]
    )

    assert len(created) == 1
    assert store_path.exists()
    assert store.get_user("admin.okua") is not None

    tecnico = store.create_user(
        build_remote_user_record(
            username="tecnico.okua",
            password_hash="hash-tech",
            role="tecnico",
            notes="Banco A",
        )
    )
    assert tecnico.username == "tecnico.okua"

    updated = store.update_user(
        "tecnico.okua",
        new_username="tecnico2.okua",
        new_role="observador",
        enabled=False,
        notes="Banco B",
    )
    assert updated.username == "tecnico2.okua"
    assert updated.role == "observador"
    assert updated.enabled is False
    assert updated.notes == "Banco B"

    reloaded = RemoteUserStore(store_path)
    assert reloaded.get_user("tecnico2.okua") is not None

    reloaded.delete_user("tecnico2.okua")
    assert reloaded.get_user("tecnico2.okua") is None


def test_remote_user_store_requires_at_least_one_enabled_admin(tmp_path: Path) -> None:
    store = RemoteUserStore(tmp_path / "remote_api_users.json")
    store.bootstrap_users(
        [
            build_remote_user_record(
                username="admin.okua",
                password_hash="hash-admin",
                role="admin",
            )
        ]
    )

    with pytest.raises(RemoteUserStoreError) as disable_exc:
        store.update_user("admin.okua", enabled=False)

    assert disable_exc.value.code == "last_admin_violation"

    with pytest.raises(RemoteUserStoreError) as delete_exc:
        store.delete_user("admin.okua")

    assert delete_exc.value.code == "last_admin_violation"
