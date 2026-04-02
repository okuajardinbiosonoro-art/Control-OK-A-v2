from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from control_okua.core.firmware.catalog_models import (
    FirmwareArtifact,
    FirmwareStatus,
    FirmwareTargetKind,
    coerce_firmware_status,
    normalize_key,
    normalize_target_kind,
    normalize_target_variant,
    normalize_text,
)


class FirmwareImportValidationError(ValueError):
    """Raised when a firmware import request is invalid."""


@dataclass(frozen=True)
class FirmwareImportRequest:
    source_file_path: Path | str
    target_kind: FirmwareTargetKind | str
    version: str
    target_variant: str = "generic"
    version_label: str = ""
    status: FirmwareStatus | str = FirmwareStatus.BETA
    display_name: str = ""
    changelog: str = ""
    notes: str = ""
    source_kind: str = "file_import"
    source_notes: str = ""
    tags: tuple[str, ...] | list[str] = field(default_factory=tuple)
    compatibility: tuple[str, ...] | list[str] = field(default_factory=tuple)
    mark_as_current: bool = False
    copy_to_managed_store: bool = True

    def __post_init__(self) -> None:
        resolved_path = Path(self.source_file_path).expanduser()
        resolved_version = normalize_text(self.version)
        if not resolved_version:
            raise FirmwareImportValidationError("version es obligatoria para importar firmware")

        normalized_target_kind = _coerce_import_target_kind(self.target_kind)
        normalized_target_variant = normalize_target_variant(self.target_variant)
        normalized_version_label = normalize_text(self.version_label, fallback=resolved_version)
        normalized_status = coerce_firmware_status(self.status)
        normalized_display_name = normalize_text(self.display_name)
        normalized_changelog = normalize_text(self.changelog)
        normalized_notes = normalize_text(self.notes)
        normalized_source_kind = normalize_key(self.source_kind) or "file_import"
        normalized_source_notes = normalize_text(self.source_notes)

        object.__setattr__(self, "source_file_path", resolved_path)
        object.__setattr__(self, "target_kind", normalized_target_kind)
        object.__setattr__(self, "target_variant", normalized_target_variant)
        object.__setattr__(self, "version", resolved_version)
        object.__setattr__(self, "version_label", normalized_version_label)
        object.__setattr__(self, "status", normalized_status)
        object.__setattr__(self, "display_name", normalized_display_name)
        object.__setattr__(self, "changelog", normalized_changelog)
        object.__setattr__(self, "notes", normalized_notes)
        object.__setattr__(self, "source_kind", normalized_source_kind)
        object.__setattr__(self, "source_notes", normalized_source_notes)
        object.__setattr__(self, "mark_as_current", bool(self.mark_as_current))
        object.__setattr__(self, "copy_to_managed_store", bool(self.copy_to_managed_store))


@dataclass(frozen=True)
class FirmwareImportResult:
    success: bool
    artifact_id: str | None = None
    sha256: str | None = None
    was_duplicate: bool = False
    stored_file_path: str | None = None
    catalog_updated: bool = False
    current_changed: bool = False
    imported_artifact: FirmwareArtifact | None = None
    message: str = ""
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FirmwareDeleteResult:
    success: bool
    artifact_id: str | None = None
    deleted_artifact: FirmwareArtifact | None = None
    catalog_updated: bool = False
    managed_file_deleted: bool = False
    managed_file_path: str | None = None
    message: str = ""
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _coerce_import_target_kind(value: FirmwareTargetKind | str) -> FirmwareTargetKind:
    raw = normalize_key(value)
    if not raw:
        raise FirmwareImportValidationError("target_kind es obligatorio")

    normalized = normalize_target_kind(value)
    if normalized is FirmwareTargetKind.UNKNOWN and raw != FirmwareTargetKind.UNKNOWN.value:
        raise FirmwareImportValidationError(f"target_kind invalido: {value!r}")
    return normalized
