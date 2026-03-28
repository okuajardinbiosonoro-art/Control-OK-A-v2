from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from control_okua.core.firmware.catalog_models import (
    FirmwareArtifact,
    FirmwareCatalog,
    FirmwareCatalogValidationError,
    FirmwareStatus,
    build_artifact_id,
    extract_sha256_from_artifact_id,
    normalize_key,
    normalize_text,
    normalize_utc_timestamp,
    utc_now_iso,
)


class FirmwareCatalogSchemaError(RuntimeError):
    """Raised when a firmware catalog payload cannot be parsed safely."""


def artifact_to_dict(artifact: FirmwareArtifact) -> dict[str, Any]:
    return {
        "artifact_id": artifact.artifact_id,
        "display_name": artifact.display_name,
        "version": artifact.version,
        "version_label": artifact.version_label,
        "target_kind": artifact.target_kind.value,
        "target_variant": artifact.target_variant,
        "status": artifact.status.value,
        "is_current": artifact.is_current,
        "file_name": artifact.file_name,
        "file_path": artifact.file_path,
        "sha256": artifact.sha256,
        "file_size": artifact.file_size,
        "created_at_utc": artifact.created_at_utc,
        "imported_at_utc": artifact.imported_at_utc,
        "source_kind": artifact.source_kind,
        "source_notes": artifact.source_notes,
        "changelog": artifact.changelog,
        "notes": artifact.notes,
        "compatibility": list(artifact.compatibility),
        "supersedes_artifact_id": artifact.supersedes_artifact_id,
        "tags": list(artifact.tags),
    }


def catalog_to_dict(catalog: FirmwareCatalog) -> dict[str, Any]:
    return {
        "schema_version": catalog.schema_version,
        "created_at_utc": catalog.created_at_utc,
        "updated_at_utc": catalog.updated_at_utc,
        "artifact_count": catalog.artifact_count,
        "artifacts": [artifact_to_dict(artifact) for artifact in catalog.artifacts],
    }


def artifact_from_dict(
    payload: dict[str, Any],
    *,
    base_dir: Path | None = None,
) -> FirmwareArtifact:
    if not isinstance(payload, dict):
        raise FirmwareCatalogSchemaError("artifact payload invalido: raiz no es objeto JSON")

    raw_artifact_id = payload.get("artifact_id")
    raw_sha256 = payload.get("sha256") or extract_sha256_from_artifact_id(raw_artifact_id)
    if raw_sha256 is None:
        raise FirmwareCatalogValidationError("artifact sin sha256")

    file_path = _resolve_file_path(payload.get("file_path"), base_dir=base_dir)
    if not file_path:
        raise FirmwareCatalogValidationError("artifact sin file_path valido")

    raw_status = payload.get("status")
    if raw_status in {None, ""} and bool(payload.get("is_current")):
        raw_status = FirmwareStatus.CURRENT.value

    source_kind = normalize_key(payload.get("source_kind")) or "local"

    return FirmwareArtifact(
        artifact_id=build_artifact_id(raw_sha256),
        display_name=normalize_text(payload.get("display_name")),
        version=normalize_text(payload.get("version")),
        version_label=normalize_text(payload.get("version_label")),
        target_kind=payload.get("target_kind"),
        target_variant=payload.get("target_variant") or "generic",
        status=raw_status or FirmwareStatus.SITUATIONAL.value,
        file_name=normalize_text(payload.get("file_name")),
        file_path=file_path,
        sha256=raw_sha256,
        file_size=int(payload.get("file_size", 0)),
        created_at_utc=normalize_utc_timestamp(payload.get("created_at_utc"), fallback=utc_now_iso()),
        imported_at_utc=normalize_utc_timestamp(payload.get("imported_at_utc"), fallback=utc_now_iso()),
        source_kind=source_kind,
        source_notes=normalize_text(payload.get("source_notes")),
        changelog=normalize_text(payload.get("changelog")),
        notes=normalize_text(payload.get("notes")),
        compatibility=_coerce_string_list(payload.get("compatibility")),
        supersedes_artifact_id=payload.get("supersedes_artifact_id"),
        tags=_coerce_string_list(payload.get("tags")),
    )


def catalog_from_dict(
    payload: dict[str, Any],
    *,
    base_dir: Path | None = None,
) -> tuple[FirmwareCatalog, list[str]]:
    if not isinstance(payload, dict):
        raise FirmwareCatalogSchemaError("catalog payload invalido: raiz no es objeto JSON")

    issues: list[str] = []
    created_at_utc = normalize_utc_timestamp(payload.get("created_at_utc"), fallback=utc_now_iso())
    updated_at_utc = normalize_utc_timestamp(
        payload.get("updated_at_utc"),
        fallback=created_at_utc,
    )

    raw_artifacts = payload.get("artifacts", [])
    if raw_artifacts is None:
        raw_artifacts = []
    if not isinstance(raw_artifacts, list):
        raise FirmwareCatalogSchemaError("catalog payload invalido: artifacts no es lista")

    artifacts: list[FirmwareArtifact] = []
    seen_sha256: set[str] = set()
    for index, item in enumerate(raw_artifacts):
        try:
            artifact = artifact_from_dict(item, base_dir=base_dir)
        except (FirmwareCatalogSchemaError, FirmwareCatalogValidationError, TypeError, ValueError) as exc:
            issues.append(f"artifact[{index}] descartado: {exc}")
            continue
        if artifact.sha256 in seen_sha256:
            issues.append(
                f"artifact[{index}] duplicado por sha256 descartado: {artifact.sha256}"
            )
            continue
        seen_sha256.add(artifact.sha256)
        artifacts.append(artifact)

    normalized_artifacts, current_issues = _normalize_single_current_per_target(artifacts)
    issues.extend(current_issues)

    catalog = FirmwareCatalog(
        schema_version=int(payload.get("schema_version", 1)),
        created_at_utc=created_at_utc,
        updated_at_utc=updated_at_utc,
        artifacts=tuple(normalized_artifacts),
    )
    return catalog, issues


def _resolve_file_path(value: object, *, base_dir: Path | None) -> str:
    text = normalize_text(value)
    if not text:
        return ""

    path = Path(text).expanduser()
    if not path.is_absolute() and base_dir is not None:
        path = (base_dir / path).resolve()
    else:
        path = path.resolve()
    return str(path)


def _coerce_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def _normalize_single_current_per_target(
    artifacts: list[FirmwareArtifact],
) -> tuple[list[FirmwareArtifact], list[str]]:
    issues: list[str] = []
    by_target: dict[tuple[str, str], list[FirmwareArtifact]] = {}
    for artifact in artifacts:
        if artifact.is_current:
            by_target.setdefault(artifact.target_key, []).append(artifact)

    winner_ids: dict[tuple[str, str], str] = {}
    for target_key, candidates in by_target.items():
        if len(candidates) == 1:
            winner_ids[target_key] = candidates[0].artifact_id
            continue
        winner = max(
            candidates,
            key=lambda item: (item.imported_at_utc, item.created_at_utc, item.artifact_id),
        )
        winner_ids[target_key] = winner.artifact_id
        issues.append(
            "Se normalizaron multiples current para target "
            f"{target_key[0]}:{target_key[1]}; se mantuvo {winner.artifact_id}."
        )

    normalized: list[FirmwareArtifact] = []
    for artifact in artifacts:
        winner_id = winner_ids.get(artifact.target_key)
        if artifact.is_current and winner_id is not None and artifact.artifact_id != winner_id:
            normalized.append(replace(artifact, status=FirmwareStatus.OBSOLETE))
        else:
            normalized.append(artifact)
    return normalized, issues
