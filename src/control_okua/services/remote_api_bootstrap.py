from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import socket
import subprocess
from typing import Any, MutableMapping

from control_okua.services.remote_api_auth import build_remote_api_token_entry
from control_okua.services.remote_api_contract import RemoteApiConfig


@dataclass(frozen=True)
class RemoteApiBootstrapCredential:
    env_var: str
    role: str
    label: str | None
    token: str


@dataclass(frozen=True)
class RemoteApiBootstrapResult:
    secrets_path: Path
    access_note_path: Path
    credentials: tuple[RemoteApiBootstrapCredential, ...]
    access_urls: tuple[str, ...]
    warnings: tuple[str, ...]


def ensure_remote_api_runtime_config(
    cfg: dict[str, Any],
) -> tuple[dict[str, Any], tuple[str, ...], bool]:
    if not isinstance(cfg, dict):
        return cfg, tuple(), False
    remote_cfg = cfg.get("remote_api")
    if not isinstance(remote_cfg, dict):
        return cfg, tuple(), False
    if remote_cfg.get("enabled") is not True:
        return cfg, tuple(), False

    warnings: list[str] = []
    changed = False

    bind_host = remote_cfg.get("bind_host")
    if bind_host in {"127.0.0.1", "::1"}:
        remote_cfg["bind_host"] = "0.0.0.0"
        warnings.append(
            "remote_api.bind_host actualizado a '0.0.0.0' para acceso LAN/Tailscale."
        )
        changed = True

    auth_mode = remote_cfg.get("auth_mode")
    raw_tokens = remote_cfg.get("tokens")
    if auth_mode == "bearer_token_inventory" and (not isinstance(raw_tokens, list) or not raw_tokens):
        remote_cfg["tokens"] = build_default_remote_api_token_inventory_dicts()
        warnings.append(
            "remote_api.tokens estaba vacío; se cargó inventario local por defecto para observador/tecnico/admin."
        )
        changed = True

    return cfg, tuple(warnings), changed


def ensure_remote_api_local_credentials(
    config: RemoteApiConfig,
    *,
    config_path: Path,
    environ: MutableMapping[str, str] | None = None,
) -> RemoteApiBootstrapResult:
    env_map = environ if environ is not None else {}
    secrets_path = config_path.with_name("remote_api_tokens.json")
    access_note_path = config_path.with_name("remote_api_access.txt")
    store = _load_secret_store(secrets_path)
    warnings: list[str] = []

    credentials: list[RemoteApiBootstrapCredential] = []
    for entry in _iter_required_entries(config):
        token_text = str(env_map.get(entry.env_var, "")).strip()
        if not token_text:
            token_text = _load_token_from_store(store, entry.env_var)
        if not token_text:
            token_text = secrets.token_urlsafe(32)
            warnings.append(
                f"token local generado automáticamente para role={entry.role} env_var={entry.env_var}."
            )
        env_map[entry.env_var] = token_text
        credentials.append(
            RemoteApiBootstrapCredential(
                env_var=entry.env_var,
                role=entry.role,
                label=entry.label,
                token=token_text,
            )
        )

    _save_secret_store(
        secrets_path=secrets_path,
        config=config,
        credentials=tuple(credentials),
    )
    access_urls = build_remote_api_access_urls(config)
    _save_access_note(
        access_note_path=access_note_path,
        config=config,
        credentials=tuple(credentials),
        access_urls=access_urls,
    )
    warnings.append(f"credenciales remotas locales disponibles en '{access_note_path.name}'.")

    return RemoteApiBootstrapResult(
        secrets_path=secrets_path,
        access_note_path=access_note_path,
        credentials=tuple(credentials),
        access_urls=access_urls,
        warnings=tuple(warnings),
    )


def build_default_remote_api_token_inventory_dicts() -> list[dict[str, str]]:
    return [
        {
            "env_var": "CKV2_REMOTE_API_OBSERVER_TOKEN",
            "role": "observador",
            "label": "observer-main",
        },
        {
            "env_var": "CKV2_REMOTE_API_TECH_TOKEN",
            "role": "tecnico",
            "label": "tech-main",
        },
        {
            "env_var": "CKV2_REMOTE_API_ADMIN_TOKEN",
            "role": "admin",
            "label": "admin-main",
        },
    ]


def build_remote_api_access_urls(config: RemoteApiConfig) -> tuple[str, ...]:
    port = int(config.port)
    bind_host = str(config.bind_host).strip() or "127.0.0.1"
    urls: list[str] = [f"http://127.0.0.1:{port}/remote/"]
    if bind_host not in {"127.0.0.1", "::1"}:
        if bind_host not in {"0.0.0.0", "::"}:
            urls.append(f"http://{bind_host}:{port}/remote/")
        else:
            for hostname in _discover_access_hostnames():
                urls.append(f"http://{hostname}:{port}/remote/")
            for address in _discover_local_ipv4_addresses():
                urls.append(f"http://{address}:{port}/remote/")
    deduped: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        deduped.append(url)
    return tuple(deduped)


def _discover_access_hostnames() -> tuple[str, ...]:
    hostnames: list[str] = []
    seen: set[str] = set()

    def add(hostname: str) -> None:
        text = str(hostname).strip().rstrip(".")
        if not text:
            return
        normalized = text.lower()
        if normalized in {"localhost", "0.0.0.0", "::", "::1"}:
            return
        if normalized in seen:
            return
        seen.add(normalized)
        hostnames.append(text)

    try:
        add(socket.gethostname())
    except OSError:
        pass

    try:
        fqdn = socket.getfqdn()
    except OSError:
        fqdn = ""
    if fqdn:
        add(fqdn)

    tailscale_dns_name = _discover_tailscale_dns_name()
    if tailscale_dns_name:
        add(tailscale_dns_name)
        short_name = tailscale_dns_name.split(".", 1)[0].strip()
        if short_name:
            add(short_name)

    return tuple(hostnames)


def _discover_tailscale_dns_name() -> str:
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0 and not result.stdout.strip():
        return ""
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    self_payload = payload.get("Self")
    if not isinstance(self_payload, dict):
        return ""
    dns_name = self_payload.get("DNSName")
    if not isinstance(dns_name, str):
        return ""
    return dns_name.strip().rstrip(".")


def _iter_required_entries(
    config: RemoteApiConfig,
) -> tuple[Any, ...]:
    if config.auth_mode == "bearer_token_inventory":
        return config.tokens
    return (
        build_remote_api_token_entry(
            env_var=config.token_env_var,
            role="admin",
            label="legacy-admin",
        ),
    )


def _load_secret_store(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_token_from_store(store: dict[str, Any], env_var: str) -> str:
    tokens = store.get("tokens")
    if not isinstance(tokens, list):
        return ""
    for item in tokens:
        if not isinstance(item, dict):
            continue
        if item.get("env_var") != env_var:
            continue
        token = item.get("token")
        if isinstance(token, str) and token.strip():
            return token.strip()
    return ""


def _save_secret_store(
    *,
    secrets_path: Path,
    config: RemoteApiConfig,
    credentials: tuple[RemoteApiBootstrapCredential, ...],
) -> None:
    payload = {
        "schema_version": 1,
        "generated_at_utc": _utc_now_iso(),
        "auth_mode": config.auth_mode,
        "tokens": [
            {
                "env_var": credential.env_var,
                "role": credential.role,
                "label": credential.label,
                "token": credential.token,
            }
            for credential in credentials
        ],
    }
    secrets_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _save_access_note(
    *,
    access_note_path: Path,
    config: RemoteApiConfig,
    credentials: tuple[RemoteApiBootstrapCredential, ...],
    access_urls: tuple[str, ...],
) -> None:
    lines = [
        "CKv2 Remote Console Access",
        "",
        f"Generated at UTC: {_utc_now_iso()}",
        f"Auth mode: {config.auth_mode}",
        "",
        "Console URLs:",
    ]
    lines.extend(f"- {url}" for url in access_urls)
    lines.extend(
        [
            "",
            "Tokens:",
        ]
    )
    for credential in credentials:
        label_suffix = f" ({credential.label})" if credential.label else ""
        lines.append(
            f"- role={credential.role}{label_suffix} env_var={credential.env_var} token={credential.token}"
        )
    lines.extend(
        [
            "",
            "Usage:",
            "- Open one of the URLs above in the browser.",
            "- Paste the token that matches the role you want to test.",
            "- The backend remains the source of truth for permissions.",
        ]
    )
    access_note_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _discover_local_ipv4_addresses() -> tuple[str, ...]:
    addresses: list[str] = []
    seen: set[str] = set()

    def add(address: str) -> None:
        text = str(address).strip()
        if not text or text.startswith("127.") or text.startswith("169.254."):
            return
        if text in seen:
            return
        seen.add(text)
        addresses.append(text)

    try:
        host_name = socket.gethostname()
        for address in socket.gethostbyname_ex(host_name)[2]:
            add(address)
    except OSError:
        pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            add(sock.getsockname()[0])
    except OSError:
        pass

    return tuple(addresses)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
