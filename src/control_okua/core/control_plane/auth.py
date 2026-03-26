from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
import re
import sys
from typing import Final

CONTROL_SECRET_ENV: Final[str] = "CKV2_CONTROL_SECRET"
CONTROL_SECRET_FILE_ENV: Final[str] = "CKV2_CONTROL_SECRET_FILE"
_PLACEHOLDER_SECRETS: Final[set[str]] = {
    "CHANGE_ME_CONTROL_SECRET",
    "YOUR_CONTROL_PLANE_SHARED_SECRET",
    "CHANGE_ME",
}


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
        text = _read_secret_from_file(file_path)
        return _normalize_secret(text)

    for candidate in _iter_default_secret_candidates():
        secret = _try_read_secret_candidate(candidate)
        if secret is None:
            continue
        return _normalize_secret(secret)

    raise ControlSecretNotConfiguredError(
        "No hay secreto de control configurado. Define CKV2_CONTROL_SECRET "
        "o CKV2_CONTROL_SECRET_FILE; tambien puedes usar control_plane_secret.txt "
        "junto al ejecutable (build) o firmware/okua_node_udp_v1/okua_node_secrets.h (dev)."
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


def _read_secret_from_file(file_path: Path) -> str:
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ControlSecretFileError(
            f"No se pudo leer el archivo de secreto '{file_path}': {exc}"
        ) from exc

    if file_path.suffix.lower() in {".h", ".hpp"}:
        secret = _extract_secret_from_header_text(text)
    else:
        secret = text.strip()

    if not secret:
        raise ControlSecretFileError(
            f"El archivo de secreto '{file_path}' esta vacio."
        )
    if secret in _PLACEHOLDER_SECRETS:
        raise ControlSecretFileError(
            f"El archivo de secreto '{file_path}' contiene un placeholder no valido."
        )
    return secret


def _try_read_secret_candidate(file_path: Path) -> str | None:
    if not file_path.exists():
        return None
    try:
        return _read_secret_from_file(file_path)
    except ControlSecretFileError:
        return None


def _extract_secret_from_header_text(text: str) -> str:
    match = re.search(
        r'#define\s+OKUA_CONTROL_SECRET\s+"([^"]+)"',
        text,
    )
    if not match:
        return ""
    return match.group(1).strip()


def _iter_default_secret_candidates() -> tuple[Path, ...]:
    dirs: list[Path] = []
    if getattr(sys, "frozen", False):
        dirs.extend(
            [
                Path(sys.executable).resolve().parent,
                Path.cwd().resolve(),
            ]
        )
    else:
        repo_root = _resolve_repo_root()
        dirs.extend([repo_root, Path.cwd().resolve()])

    seen: set[Path] = set()
    candidates: list[Path] = []
    for base_dir in dirs:
        resolved_base = base_dir.resolve()
        if resolved_base in seen:
            continue
        seen.add(resolved_base)
        candidates.extend(
            [
                resolved_base / ".control_plane_secret",
                resolved_base / "control_plane_secret.txt",
                resolved_base / "okua_node_secrets.h",
                resolved_base / "firmware" / "okua_node_udp_v1" / "okua_node_secrets.h",
            ]
        )
    return tuple(candidates)


def _resolve_repo_root() -> Path:
    # auth.py -> control_plane -> core -> control_okua -> src -> repo_root
    return Path(__file__).resolve().parents[4]
