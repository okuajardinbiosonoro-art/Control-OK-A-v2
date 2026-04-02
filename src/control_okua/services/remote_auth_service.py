from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import secrets

from control_okua.services.remote_user_store import (
    RemoteUserRecord,
    RemoteUserStore,
    RemoteUserStoreError,
    build_remote_user_record,
    normalize_remote_role,
    normalize_remote_username,
)


PASSWORD_SCRYPT_N = 2**14
PASSWORD_SCRYPT_R = 8
PASSWORD_SCRYPT_P = 1
PASSWORD_SALT_BYTES = 16
MIN_REMOTE_PASSWORD_LENGTH = 8
REQUIRED_BOOTSTRAP_ROLES: tuple[str, ...] = ("admin", "tecnico", "observador")


class _UnsetSentinel:
    pass


_UNSET = _UnsetSentinel()


class RemoteAuthServiceError(RuntimeError):
    """Raised when remote human authentication cannot proceed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class RemoteAuthenticatedUser:
    username: str
    role: str
    enabled: bool
    notes: str | None
    created_at: str
    updated_at: str
    last_password_change_at: str

    @property
    def actor_id(self) -> str:
        return f"remote_user:{self.username}"

    def to_public_dict(self) -> dict[str, object | None]:
        return {
            "username": self.username,
            "role": self.role,
            "enabled": self.enabled,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_password_change_at": self.last_password_change_at,
        }


class RemoteAuthService:
    def __init__(self, user_store: RemoteUserStore) -> None:
        self._user_store = user_store

    @property
    def user_store(self) -> RemoteUserStore:
        return self._user_store

    def bootstrap_required(self) -> bool:
        return self._user_store.is_bootstrap_required()

    def bootstrap_initial_accounts(
        self,
        accounts: list[dict[str, object]],
    ) -> tuple[RemoteAuthenticatedUser, ...]:
        if not accounts:
            raise RemoteAuthServiceError(
                "invalid_bootstrap",
                "Bootstrap inicial sin cuentas.",
            )
        seen_roles: set[str] = set()
        records: list[RemoteUserRecord] = []
        for item in accounts:
            if not isinstance(item, dict):
                raise RemoteAuthServiceError(
                    "invalid_bootstrap",
                    "Bootstrap inicial con cuenta inválida.",
                )
            username = item.get("username")
            password = item.get("password")
            role = item.get("role")
            notes = item.get("notes")
            normalized_username = normalize_remote_username(str(username or ""))
            normalized_role = normalize_remote_role(str(role or ""))
            if normalized_role in seen_roles:
                raise RemoteAuthServiceError(
                    "invalid_bootstrap",
                    "Bootstrap inicial con roles duplicados.",
                )
            seen_roles.add(normalized_role)
            validate_remote_password(str(password or ""))
            password_hash = hash_remote_password(str(password))
            records.append(
                build_remote_user_record(
                    username=normalized_username,
                    password_hash=password_hash,
                    role=normalized_role,
                    notes=None if notes is None else str(notes).strip(),
                )
            )
        if set(REQUIRED_BOOTSTRAP_ROLES) != seen_roles:
            raise RemoteAuthServiceError(
                "invalid_bootstrap",
                "Bootstrap inicial debe incluir admin, tecnico y observador.",
            )
        try:
            created = self._user_store.bootstrap_users(records)
        except RemoteUserStoreError as exc:
            raise RemoteAuthServiceError(exc.code, exc.message) from exc
        return tuple(self._to_authenticated_user(item) for item in created)

    def authenticate_credentials(
        self,
        *,
        username: str,
        password: str,
    ) -> RemoteAuthenticatedUser:
        if self.bootstrap_required():
            raise RemoteAuthServiceError(
                "bootstrap_required",
                "El sitio requiere bootstrap inicial de cuentas remotas.",
            )
        try:
            account = self._user_store.get_user(username)
        except RemoteUserStoreError as exc:
            raise RemoteAuthServiceError(exc.code, exc.message) from exc
        if account is None:
            raise RemoteAuthServiceError(
                "invalid_credentials",
                "Usuario o contraseña inválidos.",
            )
        if not account.enabled:
            raise RemoteAuthServiceError(
                "account_disabled",
                "La cuenta remota está deshabilitada.",
            )
        if not verify_remote_password(password, account.password_hash):
            raise RemoteAuthServiceError(
                "invalid_credentials",
                "Usuario o contraseña inválidos.",
            )
        return self._to_authenticated_user(account)

    def get_user(self, username: str) -> RemoteAuthenticatedUser | None:
        try:
            account = self._user_store.get_user(username)
        except RemoteUserStoreError as exc:
            raise RemoteAuthServiceError(exc.code, exc.message) from exc
        if account is None:
            return None
        return self._to_authenticated_user(account)

    def list_public_users(self) -> tuple[RemoteAuthenticatedUser, ...]:
        try:
            users = self._user_store.list_users()
        except RemoteUserStoreError as exc:
            raise RemoteAuthServiceError(exc.code, exc.message) from exc
        return tuple(self._to_authenticated_user(item) for item in users)

    def create_user(
        self,
        *,
        username: str,
        password: str,
        role: str,
        notes: str | None = None,
        enabled: bool = True,
    ) -> RemoteAuthenticatedUser:
        validate_remote_password(password)
        try:
            record = self._user_store.create_user(
                build_remote_user_record(
                    username=username,
                    password_hash=hash_remote_password(password),
                    role=role,
                    enabled=enabled,
                    notes=notes,
                )
            )
        except RemoteUserStoreError as exc:
            raise RemoteAuthServiceError(exc.code, exc.message) from exc
        return self._to_authenticated_user(record)

    def update_user_profile(
        self,
        *,
        username: str,
        new_username: str | None = None,
        role: str | None = None,
        enabled: bool | None = None,
        notes: str | None | object = _UNSET,
    ) -> RemoteAuthenticatedUser:
        try:
            record = self._user_store.update_user(
                username,
                new_username=new_username,
                new_role=role,
                enabled=enabled,
                notes=notes,
            )
        except RemoteUserStoreError as exc:
            raise RemoteAuthServiceError(exc.code, exc.message) from exc
        return self._to_authenticated_user(record)

    def change_password(self, *, username: str, new_password: str) -> RemoteAuthenticatedUser:
        validate_remote_password(new_password)
        changed_at = _utc_now_iso()
        try:
            record = self._user_store.update_user(
                username,
                new_password_hash=hash_remote_password(new_password),
                password_changed_at=changed_at,
            )
        except RemoteUserStoreError as exc:
            raise RemoteAuthServiceError(exc.code, exc.message) from exc
        return self._to_authenticated_user(record)

    def delete_user(self, *, username: str) -> None:
        try:
            self._user_store.delete_user(username)
        except RemoteUserStoreError as exc:
            raise RemoteAuthServiceError(exc.code, exc.message) from exc

    @staticmethod
    def _to_authenticated_user(record: RemoteUserRecord) -> RemoteAuthenticatedUser:
        return RemoteAuthenticatedUser(
            username=record.username,
            role=record.role,
            enabled=record.enabled,
            notes=record.notes,
            created_at=record.created_at,
            updated_at=record.updated_at,
            last_password_change_at=record.last_password_change_at,
        )


def hash_remote_password(password: str) -> str:
    validate_remote_password(password)
    salt = secrets.token_bytes(PASSWORD_SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=PASSWORD_SCRYPT_N,
        r=PASSWORD_SCRYPT_R,
        p=PASSWORD_SCRYPT_P,
    )
    return (
        f"scrypt${PASSWORD_SCRYPT_N}${PASSWORD_SCRYPT_R}${PASSWORD_SCRYPT_P}$"
        f"{salt.hex()}${derived.hex()}"
    )


def verify_remote_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, n_text, r_text, p_text, salt_hex, hash_hex = str(stored_hash).split("$", 5)
    except ValueError:
        return False
    if algorithm != "scrypt":
        return False
    try:
        derived = hashlib.scrypt(
            str(password).encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n_text),
            r=int(r_text),
            p=int(p_text),
        )
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(derived.hex(), hash_hex)


def validate_remote_password(password: str) -> None:
    text = str(password)
    if len(text) < MIN_REMOTE_PASSWORD_LENGTH or not text.strip():
        raise RemoteAuthServiceError(
            "invalid_password",
            f"La contraseña remota debe tener al menos {MIN_REMOTE_PASSWORD_LENGTH} caracteres.",
        )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
