from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from typing import Mapping

from control_okua.services.remote_api_contract import (
    RemoteApiConfig,
    RemoteApiTokenInventoryEntry,
)


VALID_REMOTE_API_ROLES: tuple[str, ...] = ("observador", "tecnico", "admin")
_READ_ONLY_ACTIONS: frozenset[str] = frozenset(
    {
        "health.read",
        "runtime.summary.read",
        "nodes.read",
        "node.read",
    }
)
_TECH_ACTIONS: frozenset[str] = frozenset({"node.request_stat_now"})
_ADMIN_ACTIONS: frozenset[str] = frozenset({"node.reboot"})


class RemoteApiAuthError(RuntimeError):
    """Base error for remote API auth helpers."""


class RemoteApiAuthConfigError(RemoteApiAuthError):
    """Raised when auth configuration is invalid or incomplete."""


class RemoteApiUnauthorizedError(RemoteApiAuthError):
    """Raised when a request does not satisfy bearer token auth."""

    def __init__(
        self,
        message: str,
        *,
        actor_type: str,
        actor_id: str,
        authorization_result: str,
        role: str | None = None,
        token_label: str | None = None,
    ) -> None:
        super().__init__(message)
        self.actor_type = actor_type
        self.actor_id = actor_id
        self.authorization_result = authorization_result
        self.role = role
        self.token_label = token_label


class RemoteApiForbiddenError(RemoteApiAuthError):
    """Raised when a valid token lacks sufficient role permissions."""

    def __init__(
        self,
        message: str,
        *,
        actor_type: str,
        actor_id: str,
        role: str,
        authorization_result: str,
        token_label: str | None = None,
    ) -> None:
        super().__init__(message)
        self.actor_type = actor_type
        self.actor_id = actor_id
        self.role = role
        self.authorization_result = authorization_result
        self.token_label = token_label


@dataclass(frozen=True)
class RemoteApiTokenBinding:
    env_var: str
    role: str
    token_label: str | None
    token_value: str
    actor_id: str
    granted_authorization_result: str


@dataclass(frozen=True)
class RemoteApiAuthContext:
    actor_type: str
    actor_id: str
    role: str
    token_label: str | None
    authorization_result: str


def build_token_fingerprint(token: str) -> str:
    text = str(token).strip()
    if not text:
        return "missing"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return digest[:12]


def build_actor_id_for_token(token: str) -> str:
    return f"remote_api_token:{build_token_fingerprint(token)}"


def resolve_expected_bearer_token(
    token_env_var: str,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    env_map = environ or {}
    env_name = str(token_env_var).strip()
    if not env_name:
        raise RemoteApiAuthConfigError(
            "remote_api.token_env_var invalido: se esperaba nombre de variable de entorno."
        )
    token = env_map.get(env_name)
    if token is None:
        raise RemoteApiAuthConfigError(
            f"No se encontró token remoto en la variable de entorno '{env_name}'."
        )
    token_text = str(token).strip()
    if not token_text:
        raise RemoteApiAuthConfigError(
            f"La variable de entorno '{env_name}' está vacía."
        )
    return token_text


def resolve_remote_api_token_bindings(
    config: RemoteApiConfig,
    *,
    environ: Mapping[str, str] | None = None,
) -> tuple[RemoteApiTokenBinding, ...]:
    env_map = environ or {}
    if config.auth_mode == "bearer_token":
        token_value = resolve_expected_bearer_token(
            config.token_env_var,
            environ=env_map,
        )
        return (
            RemoteApiTokenBinding(
                env_var=config.token_env_var,
                role="admin",
                token_label="legacy-admin",
                token_value=token_value,
                actor_id=build_actor_id_for_token(token_value),
                granted_authorization_result="granted_legacy_admin",
            ),
        )

    if config.auth_mode != "bearer_token_inventory":
        raise RemoteApiAuthConfigError(
            f"remote_api.auth_mode no soportado: {config.auth_mode!r}"
        )
    if not config.tokens:
        raise RemoteApiAuthConfigError(
            "remote_api.tokens vacío: se esperaba al menos un token para bearer_token_inventory."
        )

    bindings: list[RemoteApiTokenBinding] = []
    seen_tokens: set[str] = set()
    for entry in config.tokens:
        token_value = resolve_expected_bearer_token(entry.env_var, environ=env_map)
        if token_value in seen_tokens:
            raise RemoteApiAuthConfigError(
                "remote_api.tokens ambiguo: hay tokens repetidos en el inventario."
            )
        seen_tokens.add(token_value)
        bindings.append(
            RemoteApiTokenBinding(
                env_var=entry.env_var,
                role=entry.role,
                token_label=entry.label,
                token_value=token_value,
                actor_id=build_actor_id_for_token(token_value),
                granted_authorization_result="granted",
            )
        )
    return tuple(bindings)


def authenticate_bearer_request(
    authorization_header: str | None,
    *,
    token_bindings: tuple[RemoteApiTokenBinding, ...],
) -> RemoteApiAuthContext:
    scheme, token = _parse_authorization_header(authorization_header)
    if scheme is None or token is None:
        raise RemoteApiUnauthorizedError(
            "Authorization bearer token requerido.",
            actor_type="anonymous",
            actor_id="anonymous",
            authorization_result="denied_missing_token",
        )
    if scheme.lower() != "bearer":
        raise RemoteApiUnauthorizedError(
            "Authorization bearer token requerido.",
            actor_type="anonymous",
            actor_id="anonymous",
            authorization_result="denied_missing_token",
        )

    actor_id = build_actor_id_for_token(token)
    for binding in token_bindings:
        if hmac.compare_digest(token, binding.token_value):
            return RemoteApiAuthContext(
                actor_type="technical_token",
                actor_id=binding.actor_id,
                role=binding.role,
                token_label=binding.token_label,
                authorization_result=binding.granted_authorization_result,
            )

    raise RemoteApiUnauthorizedError(
        "Bearer token invalido.",
        actor_type="technical_token",
        actor_id=actor_id,
        authorization_result="denied_invalid_token",
    )


def authorize_remote_api_action(
    *,
    role: str,
    action: str,
    actor_type: str,
    actor_id: str,
    token_label: str | None = None,
) -> None:
    if action == "request.invalid":
        return
    normalized_role = _normalize_role(role)
    if action in _READ_ONLY_ACTIONS:
        return
    if action in _TECH_ACTIONS and normalized_role in {"tecnico", "admin"}:
        return
    if action in _ADMIN_ACTIONS and normalized_role == "admin":
        return
    raise RemoteApiForbiddenError(
        f"El rol '{normalized_role}' no tiene permiso para '{action}'.",
        actor_type=actor_type,
        actor_id=actor_id,
        role=normalized_role,
        authorization_result="denied_forbidden_role",
        token_label=token_label,
    )


def build_remote_api_token_entry(
    *,
    env_var: str,
    role: str,
    label: str | None = None,
) -> RemoteApiTokenInventoryEntry:
    normalized_env_var = str(env_var).strip()
    if not normalized_env_var:
        raise RemoteApiAuthConfigError(
            "remote_api.tokens[].env_var invalido: se esperaba texto no vacío."
        )
    normalized_role = _normalize_role(role)
    normalized_label = None
    if label is not None:
        label_text = str(label).strip()
        if label_text:
            normalized_label = label_text
    return RemoteApiTokenInventoryEntry(
        env_var=normalized_env_var,
        role=normalized_role,
        label=normalized_label,
    )


def _normalize_role(role: str) -> str:
    text = str(role).strip()
    if text not in VALID_REMOTE_API_ROLES:
        raise RemoteApiAuthConfigError(
            f"remote_api role invalido: {role!r}. Roles válidos: {', '.join(VALID_REMOTE_API_ROLES)}."
        )
    return text


def _parse_authorization_header(value: str | None) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    raw = str(value).strip()
    if not raw:
        return None, None
    parts = raw.split(None, 1)
    if len(parts) != 2:
        return None, None
    scheme = parts[0].strip()
    token = parts[1].strip()
    if not scheme or not token:
        return None, None
    return scheme, token
