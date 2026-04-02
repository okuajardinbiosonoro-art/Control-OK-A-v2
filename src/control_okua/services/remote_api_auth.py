from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from typing import Mapping


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
    ) -> None:
        super().__init__(message)
        self.actor_type = actor_type
        self.actor_id = actor_id


@dataclass(frozen=True)
class RemoteApiAuthContext:
    actor_type: str
    actor_id: str


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


def authenticate_bearer_request(
    authorization_header: str | None,
    *,
    expected_token: str,
) -> RemoteApiAuthContext:
    scheme, token = _parse_authorization_header(authorization_header)
    if scheme is None or token is None:
        raise RemoteApiUnauthorizedError(
            "Authorization bearer token requerido.",
            actor_type="anonymous",
            actor_id="anonymous",
        )
    if scheme.lower() != "bearer":
        raise RemoteApiUnauthorizedError(
            "Authorization bearer token requerido.",
            actor_type="anonymous",
            actor_id="anonymous",
        )

    actor_id = build_actor_id_for_token(token)
    if not hmac.compare_digest(token, expected_token):
        raise RemoteApiUnauthorizedError(
            "Bearer token invalido.",
            actor_type="technical_token",
            actor_id=actor_id,
        )
    return RemoteApiAuthContext(
        actor_type="technical_token",
        actor_id=actor_id,
    )


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
