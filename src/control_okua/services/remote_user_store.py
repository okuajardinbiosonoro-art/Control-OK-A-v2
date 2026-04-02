from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile


VALID_REMOTE_ACCOUNT_ROLES: tuple[str, ...] = ("observador", "tecnico", "admin")
_USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")


class _UnsetSentinel:
    pass


_UNSET = _UnsetSentinel()


class RemoteUserStoreError(RuntimeError):
    """Raised when the remote user store cannot be read or updated safely."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class RemoteUserRecord:
    username: str
    password_hash: str
    role: str
    enabled: bool
    created_at: str
    updated_at: str
    last_password_change_at: str
    notes: str | None = None

    def to_public_dict(self) -> dict[str, object | None]:
        return {
            "username": self.username,
            "role": self.role,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_password_change_at": self.last_password_change_at,
            "notes": self.notes,
        }


class RemoteUserStore:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def exists(self) -> bool:
        return self._path.exists()

    def is_bootstrap_required(self) -> bool:
        return len(self.list_users()) == 0

    def list_users(self) -> tuple[RemoteUserRecord, ...]:
        data = self._load_store_data()
        records = tuple(sorted(data["users"], key=lambda item: item.username))
        return records

    def get_user(self, username: str) -> RemoteUserRecord | None:
        normalized = normalize_remote_username(username)
        for item in self.list_users():
            if item.username == normalized:
                return item
        return None

    def bootstrap_users(self, users: list[RemoteUserRecord]) -> tuple[RemoteUserRecord, ...]:
        if not users:
            raise RemoteUserStoreError("invalid_bootstrap", "Bootstrap inicial vacío.")
        if self.list_users():
            raise RemoteUserStoreError(
                "bootstrap_already_completed",
                "El bootstrap inicial ya fue completado para este sitio.",
            )
        normalized_users = self._normalize_records(users)
        self._assert_enabled_admin_survives(normalized_users)
        self._save_records(normalized_users)
        return tuple(sorted(normalized_users, key=lambda item: item.username))

    def create_user(self, record: RemoteUserRecord) -> RemoteUserRecord:
        records = list(self.list_users())
        normalized = self._normalize_record(record)
        if any(item.username == normalized.username for item in records):
            raise RemoteUserStoreError(
                "username_conflict",
                f"Ya existe un usuario remoto con username '{normalized.username}'.",
            )
        records.append(normalized)
        self._assert_enabled_admin_survives(records)
        self._save_records(records)
        return normalized

    def update_user(
        self,
        username: str,
        *,
        new_username: str | None = None,
        new_role: str | None = None,
        enabled: bool | None = None,
        notes: str | None | object = _UNSET,
        new_password_hash: str | None = None,
        password_changed_at: str | None = None,
    ) -> RemoteUserRecord:
        records = list(self.list_users())
        target_username = normalize_remote_username(username)
        current = next((item for item in records if item.username == target_username), None)
        if current is None:
            raise RemoteUserStoreError(
                "user_not_found",
                f"No existe usuario remoto '{target_username}'.",
            )

        updated = RemoteUserRecord(
            username=normalize_remote_username(new_username or current.username),
            password_hash=str(new_password_hash or current.password_hash),
            role=normalize_remote_role(new_role or current.role),
            enabled=current.enabled if enabled is None else bool(enabled),
            created_at=current.created_at,
            updated_at=_utc_now_iso(),
            last_password_change_at=password_changed_at or current.last_password_change_at,
            notes=current.notes if notes is _UNSET else normalize_remote_notes(notes),
        )

        for item in records:
            if item.username == updated.username and item.username != current.username:
                raise RemoteUserStoreError(
                    "username_conflict",
                    f"Ya existe un usuario remoto con username '{updated.username}'.",
                )

        new_records = [
            updated if item.username == current.username else item
            for item in records
        ]
        self._assert_enabled_admin_survives(new_records)
        self._save_records(new_records)
        return updated

    def delete_user(self, username: str) -> None:
        records = list(self.list_users())
        target_username = normalize_remote_username(username)
        new_records = [item for item in records if item.username != target_username]
        if len(new_records) == len(records):
            raise RemoteUserStoreError(
                "user_not_found",
                f"No existe usuario remoto '{target_username}'.",
            )
        self._assert_enabled_admin_survives(new_records)
        self._save_records(new_records)

    def _load_store_data(self) -> dict[str, object]:
        if not self._path.exists():
            return {"schema_version": 1, "users": []}

        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RemoteUserStoreError(
                "corrupt_store",
                f"No se pudo leer store de usuarios remotos: {exc}",
            ) from exc

        if not isinstance(payload, dict):
            raise RemoteUserStoreError(
                "invalid_store",
                "Store de usuarios remotos con raíz inválida.",
            )
        if payload.get("schema_version") != 1:
            raise RemoteUserStoreError(
                "invalid_store",
                "Store de usuarios remotos con schema_version no soportado.",
            )

        raw_users = payload.get("users")
        if not isinstance(raw_users, list):
            raise RemoteUserStoreError(
                "invalid_store",
                "Store de usuarios remotos sin lista de usuarios válida.",
            )

        users: list[RemoteUserRecord] = []
        for item in raw_users:
            if not isinstance(item, dict):
                raise RemoteUserStoreError(
                    "invalid_store",
                    "Store de usuarios remotos contiene un registro no-dict.",
                )
            users.append(
                self._normalize_record(
                    RemoteUserRecord(
                        username=str(item.get("username", "")),
                        password_hash=str(item.get("password_hash", "")),
                        role=str(item.get("role", "")),
                        enabled=bool(item.get("enabled", False)),
                        created_at=str(item.get("created_at", "")),
                        updated_at=str(item.get("updated_at", "")),
                        last_password_change_at=str(item.get("last_password_change_at", "")),
                        notes=normalize_remote_notes(item.get("notes")),
                    )
                )
            )
        return {"schema_version": 1, "users": users}

    def _save_records(self, records: list[RemoteUserRecord]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "updated_at_utc": _utc_now_iso(),
            "users": [
                {
                    "username": item.username,
                    "password_hash": item.password_hash,
                    "role": item.role,
                    "enabled": item.enabled,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                    "last_password_change_at": item.last_password_change_at,
                    "notes": item.notes,
                }
                for item in sorted(records, key=lambda user: user.username)
            ],
        }
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(self._path.parent),
            delete=False,
            prefix="remote_users_",
            suffix=".tmp",
        ) as tmp:
            json.dump(payload, tmp, indent=2, ensure_ascii=False, sort_keys=False)
            tmp.write("\n")
            tmp_path = Path(tmp.name)
        tmp_path.replace(self._path)

    @staticmethod
    def _normalize_records(records: list[RemoteUserRecord]) -> list[RemoteUserRecord]:
        normalized = [RemoteUserStore._normalize_record(item) for item in records]
        usernames = [item.username for item in normalized]
        if len(usernames) != len(set(usernames)):
            raise RemoteUserStoreError(
                "username_conflict",
                "El bootstrap contiene usernames remotos duplicados.",
            )
        return normalized

    @staticmethod
    def _normalize_record(record: RemoteUserRecord) -> RemoteUserRecord:
        username = normalize_remote_username(record.username)
        role = normalize_remote_role(record.role)
        password_hash = str(record.password_hash).strip()
        if not password_hash:
            raise RemoteUserStoreError(
                "invalid_password_hash",
                f"Usuario remoto '{username}' sin password_hash válido.",
            )
        created_at = normalize_iso_utc(record.created_at, field_name="created_at")
        updated_at = normalize_iso_utc(record.updated_at, field_name="updated_at")
        last_password_change_at = normalize_iso_utc(
            record.last_password_change_at,
            field_name="last_password_change_at",
        )
        return RemoteUserRecord(
            username=username,
            password_hash=password_hash,
            role=role,
            enabled=bool(record.enabled),
            created_at=created_at,
            updated_at=updated_at,
            last_password_change_at=last_password_change_at,
            notes=normalize_remote_notes(record.notes),
        )

    @staticmethod
    def _assert_enabled_admin_survives(records: list[RemoteUserRecord]) -> None:
        enabled_admins = [
            item for item in records if item.enabled and item.role == "admin"
        ]
        if not enabled_admins:
            raise RemoteUserStoreError(
                "last_admin_violation",
                "Debe permanecer al menos un usuario admin habilitado.",
            )


def build_remote_user_record(
    *,
    username: str,
    password_hash: str,
    role: str,
    enabled: bool = True,
    created_at: str | None = None,
    updated_at: str | None = None,
    last_password_change_at: str | None = None,
    notes: str | None = None,
) -> RemoteUserRecord:
    now_iso = _utc_now_iso()
    return RemoteUserRecord(
        username=normalize_remote_username(username),
        password_hash=str(password_hash).strip(),
        role=normalize_remote_role(role),
        enabled=bool(enabled),
        created_at=created_at or now_iso,
        updated_at=updated_at or now_iso,
        last_password_change_at=last_password_change_at or now_iso,
        notes=normalize_remote_notes(notes),
    )


def normalize_remote_username(username: str) -> str:
    text = str(username).strip().lower()
    if not _USERNAME_PATTERN.match(text):
        raise RemoteUserStoreError(
            "invalid_username",
            f"username remoto inválido: {username!r}.",
        )
    return text


def normalize_remote_role(role: str) -> str:
    text = str(role).strip()
    if text not in VALID_REMOTE_ACCOUNT_ROLES:
        raise RemoteUserStoreError(
            "invalid_role",
            f"role remoto inválido: {role!r}.",
        )
    return text


def normalize_remote_notes(notes: object) -> str | None:
    if notes is None:
        return None
    text = str(notes).strip()
    return text or None


def normalize_iso_utc(value: str, *, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise RemoteUserStoreError(
            "invalid_timestamp",
            f"{field_name} remoto inválido.",
        )
    return text


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
