from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
from typing import Final

CONTROL_SECRET_ENV: Final[str] = "CKV2_CONTROL_SECRET"
CONTROL_SECRET_FILE_ENV: Final[str] = "CKV2_CONTROL_SECRET_FILE"


class ControlSecretError(RuntimeError):
    """Base error for control-plane shared secret resolution."""


class ControlSecretNotConfiguredError(ControlSecretError):
    """Raised when no control-plane shared secret is configured."""


class ControlSecretFileError(ControlSecretError):
    """Raised when a configured secret file cannot be read safely."""


def resolve_control_secret(
    explicit_secret: str | bytes | None = None,
    *,
    secret_env: str = CONTROL_SECRET_ENV,
    secret_file_env: str = CONTROL_SECRET_FILE_ENV,
) -> bytes:
    """
    Resolve control-plane shared secret with conservative precedence:
    1) explicit argument
    2) environment variable (default: CKV2_CONTROL_SECRET)
    3) secret file path from environment variable (default: CKV2_CONTROL_SECRET_FILE)
    """
    if explicit_secret is not None:
        return _normalize_secret(explicit_secret)

    env_secret = os.environ.get(secret_env, "").strip()
    if env_secret:
        return _normalize_secret(env_secret)

    secret_file = os.environ.get(secret_file_env, "").strip()
    if secret_file:
        file_path = Path(secret_file).expanduser()
        try:
            text = file_path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ControlSecretFileError(
                f"No se pudo leer el archivo de secreto '{file_path}': {exc}"
            ) from exc
        if not text:
            raise ControlSecretFileError(
                f"El archivo de secreto '{file_path}' esta vacio."
            )
        return _normalize_secret(text)

    raise ControlSecretNotConfiguredError(
        "No hay secreto de control configurado. Define CKV2_CONTROL_SECRET "
        "o CKV2_CONTROL_SECRET_FILE antes de enviar OKUA_CMD."
    )


def compute_auth_tag32(secret: bytes, packet_first_24: bytes) -> int:
    """
    Compute auth_tag32 as required by F3:
    HMAC-SHA256(secret, packet_bytes[0:24]), then digest[0:4] as little-endian u32.
    """
    normalized_secret = _normalize_secret(secret)
    prefix = bytes(packet_first_24)
    if len(prefix) != 24:
        raise ValueError(
            f"auth_tag32 requiere exactamente 24 bytes (bytes 0..23), llegaron {len(prefix)}."
        )
    digest = hmac.new(normalized_secret, prefix, hashlib.sha256).digest()
    return int.from_bytes(digest[:4], byteorder="little", signed=False)


def _normalize_secret(raw_secret: str | bytes) -> bytes:
    if isinstance(raw_secret, str):
        secret = raw_secret.strip().encode("utf-8")
    elif isinstance(raw_secret, bytes):
        secret = raw_secret.strip()
    else:
        raise TypeError("El secreto de control debe ser str o bytes.")

    if not secret:
        raise ControlSecretNotConfiguredError("El secreto de control esta vacio.")
    return secret
