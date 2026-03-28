from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum, IntEnum
from pathlib import Path
import re
from typing import Iterable


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_KEY_PATTERN = re.compile(r"[^a-z0-9]+")


class FirmwareCatalogFormat(IntEnum):
    V1 = 1


class FirmwareCatalogValidationError(ValueError):
    """Raised when a firmware catalog entity is invalid."""


class FirmwareStatus(str, Enum):
    CURRENT = "current"
    BETA = "beta"
    OBSOLETE = "obsolete"
    SITUATIONAL = "situational"


class FirmwareTargetKind(str, Enum):
    PLANT = "plant"
    FRUIT = "fruit"
    LAB_TEST = "lab_test"
    DIAGNOSTICS = "diagnostics"
    UNKNOWN = "unknown"


def format_utc_timestamp(value: datetime) -> str:
    resolved = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return resolved.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def utc_now_iso() -> str:
    return format_utc_timestamp(datetime.now(timezone.utc))


def normalize_utc_timestamp(value: object, *, fallback: str | None = None) -> str:
    if isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise FirmwareCatalogValidationError(f"timestamp UTC invalido: {text!r}") from exc
        return format_utc_timestamp(parsed)
    if fallback is not None:
        return fallback
    return utc_now_iso()


def normalize_sha256(value: object) -> str:
    text = str(value or "").strip().lower()
    if not _SHA256_PATTERN.fullmatch(text):
        raise FirmwareCatalogValidationError(f"sha256 invalido: {value!r}")
    return text


def build_artifact_id(sha256: object) -> str:
    return f"sha256:{normalize_sha256(sha256)}"


def extract_sha256_from_artifact_id(value: object) -> str | None:
    text = str(value or "").strip().lower()
    if text.startswith("sha256:"):
        candidate = text.split(":", 1)[1]
        if _SHA256_PATTERN.fullmatch(candidate):
            return candidate
    if _SHA256_PATTERN.fullmatch(text):
        return text
    return None


def coerce_firmware_status(value: FirmwareStatus | str) -> FirmwareStatus:
    if isinstance(value, FirmwareStatus):
        return value
    raw = str(value or "").strip().lower()
    try:
        return FirmwareStatus(raw)
    except ValueError as exc:
        raise FirmwareCatalogValidationError(f"estado de firmware invalido: {value!r}") from exc


def normalize_target_kind(value: FirmwareTargetKind | str | None) -> FirmwareTargetKind:
    if isinstance(value, FirmwareTargetKind):
        return value
    raw = normalize_key(value)
    if not raw:
        return FirmwareTargetKind.UNKNOWN
    try:
        return FirmwareTargetKind(raw)
    except ValueError:
        return FirmwareTargetKind.UNKNOWN


def normalize_target_variant(value: object) -> str:
    normalized = normalize_key(value)
    return normalized or "generic"


def normalize_key(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return _KEY_PATTERN.sub("_", text).strip("_")


def normalize_text(value: object, *, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def normalize_string_list(values: Iterable[object] | None) -> tuple[str, ...]:
    if values is None:
        return ()

    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = normalize_key(value)
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return tuple(normalized)


def normalize_file_path(value: object) -> str:
    text = normalize_text(value)
    if not text:
        raise FirmwareCatalogValidationError("file_path debe ser un string no vacio")

    path = Path(text).expanduser()
    if not path.name:
        raise FirmwareCatalogValidationError(f"file_path invalido: {value!r}")
    return str(path)


@dataclass(frozen=True)
class FirmwareArtifact:
    artifact_id: str
    display_name: str
    version: str
    version_label: str
    target_kind: FirmwareTargetKind | str = FirmwareTargetKind.UNKNOWN
    target_variant: str = "generic"
    status: FirmwareStatus | str = FirmwareStatus.SITUATIONAL
    file_name: str = ""
    file_path: str = ""
    sha256: str = ""
    file_size: int = 0
    created_at_utc: str = field(default_factory=utc_now_iso)
    imported_at_utc: str = field(default_factory=utc_now_iso)
    source_kind: str = "local"
    source_notes: str = ""
    changelog: str = ""
    notes: str = ""
    compatibility: tuple[str, ...] | list[str] = field(default_factory=tuple)
    supersedes_artifact_id: str | None = None
    tags: tuple[str, ...] | list[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        normalized_sha256 = normalize_sha256(self.sha256)
        normalized_file_path = normalize_file_path(self.file_path)
        normalized_file_name = normalize_text(
            self.file_name,
            fallback=Path(normalized_file_path).name,
        )
        if not normalized_file_name:
            raise FirmwareCatalogValidationError("file_name no pudo resolverse")

        normalized_display_name = normalize_text(
            self.display_name,
            fallback=Path(normalized_file_name).stem or normalized_file_name,
        )
        normalized_version = normalize_text(
            self.version,
            fallback=normalize_text(self.version_label, fallback="unknown"),
        )
        normalized_version_label = normalize_text(
            self.version_label,
            fallback=normalized_version,
        )
        normalized_target_kind = normalize_target_kind(self.target_kind)
        normalized_target_variant = normalize_target_variant(self.target_variant)
        normalized_status = coerce_firmware_status(self.status)
        normalized_source_kind = normalize_key(self.source_kind) or "local"
        normalized_source_notes = normalize_text(self.source_notes)
        normalized_changelog = normalize_text(self.changelog)
        normalized_notes = normalize_text(self.notes)
        normalized_created_at = normalize_utc_timestamp(self.created_at_utc)
        normalized_imported_at = normalize_utc_timestamp(
            self.imported_at_utc,
            fallback=normalized_created_at,
        )
        normalized_compatibility = normalize_string_list(self.compatibility)
        normalized_tags = normalize_string_list(self.tags)
        normalized_file_size = int(self.file_size)
        if normalized_file_size <= 0:
            raise FirmwareCatalogValidationError(
                f"file_size debe ser > 0 para '{normalized_file_name}'"
            )

        normalized_supersedes = self._normalize_supersedes_artifact_id(self.supersedes_artifact_id)
        canonical_artifact_id = build_artifact_id(normalized_sha256)

        object.__setattr__(self, "artifact_id", canonical_artifact_id)
        object.__setattr__(self, "display_name", normalized_display_name)
        object.__setattr__(self, "version", normalized_version)
        object.__setattr__(self, "version_label", normalized_version_label)
        object.__setattr__(self, "target_kind", normalized_target_kind)
        object.__setattr__(self, "target_variant", normalized_target_variant)
        object.__setattr__(self, "status", normalized_status)
        object.__setattr__(self, "file_name", normalized_file_name)
        object.__setattr__(self, "file_path", normalized_file_path)
        object.__setattr__(self, "sha256", normalized_sha256)
        object.__setattr__(self, "file_size", normalized_file_size)
        object.__setattr__(self, "created_at_utc", normalized_created_at)
        object.__setattr__(self, "imported_at_utc", normalized_imported_at)
        object.__setattr__(self, "source_kind", normalized_source_kind)
        object.__setattr__(self, "source_notes", normalized_source_notes)
        object.__setattr__(self, "changelog", normalized_changelog)
        object.__setattr__(self, "notes", normalized_notes)
        object.__setattr__(self, "compatibility", normalized_compatibility)
        object.__setattr__(self, "supersedes_artifact_id", normalized_supersedes)
        object.__setattr__(self, "tags", normalized_tags)

    @property
    def is_current(self) -> bool:
        return self.status is FirmwareStatus.CURRENT

    @property
    def target_key(self) -> tuple[str, str]:
        return (self.target_kind.value, self.target_variant)

    def matches_target(
        self,
        target_kind: FirmwareTargetKind | str | None,
        target_variant: str | None = None,
    ) -> bool:
        normalized_kind = normalize_target_kind(target_kind)
        if self.target_kind is not normalized_kind:
            return False
        if target_variant is None:
            return True
        return self.target_variant == normalize_target_variant(target_variant)

    def with_status(self, status: FirmwareStatus | str) -> "FirmwareArtifact":
        return replace(self, status=coerce_firmware_status(status))

    def with_supersedes(self, artifact_id: str | None) -> "FirmwareArtifact":
        return replace(self, supersedes_artifact_id=artifact_id)

    @staticmethod
    def _normalize_supersedes_artifact_id(value: object) -> str | None:
        if value is None:
            return None
        sha256 = extract_sha256_from_artifact_id(value)
        if sha256 is None:
            raise FirmwareCatalogValidationError(
                f"supersedes_artifact_id invalido: {value!r}"
            )
        return build_artifact_id(sha256)


@dataclass(frozen=True)
class FirmwareCatalog:
    schema_version: int = int(FirmwareCatalogFormat.V1)
    created_at_utc: str = field(default_factory=utc_now_iso)
    updated_at_utc: str = field(default_factory=utc_now_iso)
    artifacts: tuple[FirmwareArtifact, ...] | list[FirmwareArtifact] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        normalized_schema_version = int(self.schema_version)
        if normalized_schema_version != int(FirmwareCatalogFormat.V1):
            raise FirmwareCatalogValidationError(
                f"schema_version no soportado: {self.schema_version}"
            )

        normalized_created_at = normalize_utc_timestamp(self.created_at_utc)
        normalized_updated_at = normalize_utc_timestamp(
            self.updated_at_utc,
            fallback=normalized_created_at,
        )

        normalized_artifacts = tuple(self.artifacts)
        seen_artifact_ids: set[str] = set()
        seen_sha256: set[str] = set()
        current_targets: set[tuple[str, str]] = set()

        for artifact in normalized_artifacts:
            if artifact.artifact_id in seen_artifact_ids:
                raise FirmwareCatalogValidationError(
                    f"artifact_id duplicado en catalogo: {artifact.artifact_id}"
                )
            seen_artifact_ids.add(artifact.artifact_id)

            if artifact.sha256 in seen_sha256:
                raise FirmwareCatalogValidationError(
                    f"sha256 duplicado en catalogo: {artifact.sha256}"
                )
            seen_sha256.add(artifact.sha256)

            if artifact.is_current:
                if artifact.target_key in current_targets:
                    raise FirmwareCatalogValidationError(
                        "No puede haber mas de un firmware current para el mismo target"
                    )
                current_targets.add(artifact.target_key)

        object.__setattr__(self, "schema_version", normalized_schema_version)
        object.__setattr__(self, "created_at_utc", normalized_created_at)
        object.__setattr__(self, "updated_at_utc", normalized_updated_at)
        object.__setattr__(self, "artifacts", normalized_artifacts)

    @property
    def artifact_count(self) -> int:
        return len(self.artifacts)

    @classmethod
    def empty(cls) -> "FirmwareCatalog":
        now = utc_now_iso()
        return cls(created_at_utc=now, updated_at_utc=now, artifacts=())
