from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from urllib.parse import urlparse

from control_okua.core.firmware.catalog_models import normalize_text


DEFAULT_OTA_HTTP_PORT = 8080
DEFAULT_OTA_PUBLISH_DIRNAME = "ota_publish"
DEFAULT_OTA_FIRMWARE_FAMILY = "okua_node_udp_v1"
DEFAULT_OTA_BUILD_PROFILE = "field"
DEFAULT_OTA_PROTOCOL_VERSION = "okua_v1"
DEFAULT_OTA_COMPATIBLE_HW = ("esp32dev",)
OTA_MANIFEST_SCHEMA_VERSION = 1
_ROLLOUT_CHANNELS = {"stable", "beta", "situational"}
_SEMVER_PATTERN = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:[-+][0-9A-Za-z._-]+)?$"
)


class OtaManifestValidationError(ValueError):
    """Raised when OTA manifest publication input is invalid."""


def normalize_rollout_token_hex(value: int | str) -> str:
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            raise OtaManifestValidationError("rollout_token es obligatorio")
        if text.startswith("0x"):
            text = text[2:]
        try:
            numeric_value = int(text, 16)
        except ValueError as exc:
            raise OtaManifestValidationError(
                f"rollout_token invalido: {value!r}"
            ) from exc
    else:
        try:
            numeric_value = int(value)
        except (TypeError, ValueError) as exc:
            raise OtaManifestValidationError(
                f"rollout_token invalido: {value!r}"
            ) from exc

    if numeric_value <= 0 or numeric_value > 0xFFFFFFFF:
        raise OtaManifestValidationError(
            f"rollout_token fuera de rango (1..0xFFFFFFFF): {value!r}"
        )
    return f"{numeric_value:08x}"


def derive_version_code(version: str) -> int:
    text = normalize_text(version)
    match = _SEMVER_PATTERN.fullmatch(text)
    if match is None:
        raise OtaManifestValidationError(
            f"version invalida para OTA; se esperaba semver MAJOR.MINOR.PATCH: {version!r}"
        )
    major = int(match.group("major"))
    minor = int(match.group("minor"))
    patch = int(match.group("patch"))
    return major * 10000 + minor * 100 + patch


def normalize_rollout_channel(value: str) -> str:
    text = normalize_text(value).lower()
    if text not in _ROLLOUT_CHANNELS:
        raise OtaManifestValidationError(
            f"rollout_channel invalido: {value!r}. Esperado uno de {_ROLLOUT_CHANNELS!r}"
        )
    return text


def normalize_http_host(value: str) -> str:
    text = normalize_text(value)
    if not text:
        raise OtaManifestValidationError("host es obligatorio para construir URLs OTA")
    if text == "0.0.0.0":
        raise OtaManifestValidationError(
            "host no puede ser 0.0.0.0 en un manifest OTA; usa la IP o hostname alcanzable del PC"
        )
    return text


def normalize_http_port(value: int) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise OtaManifestValidationError(f"port invalido: {value!r}") from exc
    if port < 1 or port > 65535:
        raise OtaManifestValidationError(f"port fuera de rango (1..65535): {value!r}")
    return port


def validate_http_url(value: str) -> str:
    text = normalize_text(value)
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise OtaManifestValidationError(f"URL OTA invalida: {value!r}")
    return text


@dataclass(frozen=True)
class OtaManifestFlags:
    reboot_required: bool = True
    allow_auto_rollback: bool = True
    allow_downgrade: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {
            "reboot_required": bool(self.reboot_required),
            "allow_auto_rollback": bool(self.allow_auto_rollback),
            "allow_downgrade": bool(self.allow_downgrade),
        }


@dataclass(frozen=True)
class OtaManifest:
    schema_version: int
    rollout_id: str
    firmware_family: str
    target_kind: str
    target_variant: str
    compatible_hw: tuple[str, ...]
    build_profile: str
    protocol_version: str
    version: str
    version_code: int
    artifact_id: str
    sha256: str
    file_size: int
    download_url: str
    rollout_channel: str
    changelog_short: str
    published_at_utc: str
    flags: OtaManifestFlags = field(default_factory=OtaManifestFlags)

    def __post_init__(self) -> None:
        if int(self.schema_version) != OTA_MANIFEST_SCHEMA_VERSION:
            raise OtaManifestValidationError(
                f"schema_version no soportado: {self.schema_version!r}"
            )
        if not normalize_text(self.rollout_id):
            raise OtaManifestValidationError("rollout_id es obligatorio")
        if not normalize_text(self.firmware_family):
            raise OtaManifestValidationError("firmware_family es obligatorio")
        if not normalize_text(self.target_kind):
            raise OtaManifestValidationError("target_kind es obligatorio")
        if not normalize_text(self.target_variant):
            raise OtaManifestValidationError("target_variant es obligatorio")
        if not normalize_text(self.build_profile):
            raise OtaManifestValidationError("build_profile es obligatorio")
        if not normalize_text(self.protocol_version):
            raise OtaManifestValidationError("protocol_version es obligatorio")
        if not normalize_text(self.version):
            raise OtaManifestValidationError("version es obligatorio")
        if int(self.version_code) <= 0:
            raise OtaManifestValidationError("version_code debe ser > 0")
        if not normalize_text(self.artifact_id):
            raise OtaManifestValidationError("artifact_id es obligatorio")
        if not normalize_text(self.sha256):
            raise OtaManifestValidationError("sha256 es obligatorio")
        if int(self.file_size) <= 0:
            raise OtaManifestValidationError("file_size debe ser > 0")
        validate_http_url(self.download_url)
        normalize_rollout_channel(self.rollout_channel)
        if not normalize_text(self.changelog_short):
            raise OtaManifestValidationError("changelog_short es obligatorio")
        if not normalize_text(self.published_at_utc):
            raise OtaManifestValidationError("published_at_utc es obligatorio")
        compatible_hw = tuple(normalize_text(item) for item in self.compatible_hw if normalize_text(item))
        if not compatible_hw:
            raise OtaManifestValidationError("compatible_hw debe contener al menos un hardware")
        object.__setattr__(self, "compatible_hw", compatible_hw)
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "version_code", int(self.version_code))
        object.__setattr__(self, "file_size", int(self.file_size))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "rollout_id": self.rollout_id,
            "firmware_family": self.firmware_family,
            "target_kind": self.target_kind,
            "target_variant": self.target_variant,
            "compatible_hw": list(self.compatible_hw),
            "build_profile": self.build_profile,
            "protocol_version": self.protocol_version,
            "version": self.version,
            "version_code": self.version_code,
            "artifact_id": self.artifact_id,
            "sha256": self.sha256,
            "file_size": self.file_size,
            "download_url": self.download_url,
            "rollout_channel": self.rollout_channel,
            "changelog_short": self.changelog_short,
            "published_at_utc": self.published_at_utc,
            "flags": self.flags.to_dict(),
        }


@dataclass(frozen=True)
class OtaRolloutPublishRequest:
    rollout_token: int | str
    artifact_id: str
    rollout_id: str | None = None
    rollout_channel: str | None = None
    changelog_short: str = ""
    host: str = "127.0.0.1"
    port: int = DEFAULT_OTA_HTTP_PORT
    firmware_family: str = DEFAULT_OTA_FIRMWARE_FAMILY
    compatible_hw: tuple[str, ...] | list[str] = DEFAULT_OTA_COMPATIBLE_HW
    build_profile: str = ""
    protocol_version: str = DEFAULT_OTA_PROTOCOL_VERSION
    publish_root_dir: Path | str | None = None
    reboot_required: bool = True
    allow_auto_rollback: bool = True
    allow_downgrade: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "rollout_token", normalize_rollout_token_hex(self.rollout_token))
        object.__setattr__(self, "artifact_id", normalize_text(self.artifact_id))
        object.__setattr__(self, "rollout_id", normalize_text(self.rollout_id))
        object.__setattr__(self, "rollout_channel", normalize_text(self.rollout_channel).lower())
        object.__setattr__(self, "changelog_short", normalize_text(self.changelog_short))
        object.__setattr__(self, "host", normalize_http_host(self.host))
        object.__setattr__(self, "port", normalize_http_port(self.port))
        object.__setattr__(self, "firmware_family", normalize_text(self.firmware_family))
        object.__setattr__(self, "build_profile", normalize_text(self.build_profile))
        object.__setattr__(self, "protocol_version", normalize_text(self.protocol_version))
        compatible_hw = tuple(
            normalize_text(item)
            for item in self.compatible_hw
            if normalize_text(item)
        )
        if not compatible_hw:
            raise OtaManifestValidationError(
                "compatible_hw es obligatorio para publicar OTA"
            )
        object.__setattr__(self, "compatible_hw", compatible_hw)
        if self.publish_root_dir is not None:
            object.__setattr__(
                self,
                "publish_root_dir",
                Path(self.publish_root_dir).expanduser(),
            )


@dataclass(frozen=True)
class OtaRolloutPublishResult:
    success: bool
    rollout_token: str
    rollout_id: str
    artifact_id: str
    published_dir: str
    manifest_path: str
    firmware_path: str
    manifest_url: str
    download_url: str
    warnings: tuple[str, ...] = ()
    manifest: OtaManifest | None = None
    message: str = ""
