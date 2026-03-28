from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

from control_okua.core.firmware import (
    FirmwareArtifact,
    FirmwareImportResult,
    FirmwareStatus,
    FirmwareTargetKind,
    coerce_firmware_status,
    normalize_target_kind,
)


ALL_FIRMWARE_FILTER = "__all__"
_DISPLAY_NAME_SEPARATOR_PATTERN = re.compile(r"[_\-]+")
_STATUS_SORT_ORDER = {
    FirmwareStatus.CURRENT: 0,
    FirmwareStatus.BETA: 1,
    FirmwareStatus.SITUATIONAL: 2,
    FirmwareStatus.OBSOLETE: 3,
}


@dataclass(frozen=True)
class FirmwareCatalogRow:
    artifact_id: str
    display_name: str
    version: str
    version_label: str
    target_kind: str
    target_variant: str
    status: str
    status_sort_order: int
    current_label: str
    current_sort_order: int
    file_name: str
    sha256: str
    sha256_short: str
    imported_at_utc: str
    search_text: str
    artifact: FirmwareArtifact


@dataclass(frozen=True)
class FirmwareArtifactDetail:
    scalar_fields: tuple[tuple[str, str], ...]
    changelog: str
    notes: str


@dataclass(frozen=True)
class FirmwareImportFeedback:
    title: str
    summary: str
    details: str
    severity: str


def build_firmware_catalog_rows(artifacts: Iterable[FirmwareArtifact]) -> list[FirmwareCatalogRow]:
    return [build_firmware_catalog_row(artifact) for artifact in artifacts]


def build_firmware_catalog_row(artifact: FirmwareArtifact) -> FirmwareCatalogRow:
    status = coerce_firmware_status(artifact.status)
    target_kind = normalize_target_kind(artifact.target_kind)
    sha256_short = build_sha256_short(artifact.sha256)
    search_parts = (
        artifact.display_name,
        artifact.version,
        artifact.version_label,
        artifact.file_name,
        artifact.target_variant,
        artifact.sha256,
        artifact.artifact_id,
        target_kind.value,
    )
    return FirmwareCatalogRow(
        artifact_id=artifact.artifact_id,
        display_name=artifact.display_name,
        version=artifact.version,
        version_label=artifact.version_label,
        target_kind=build_target_label(target_kind),
        target_variant=artifact.target_variant,
        status=build_status_label(status),
        status_sort_order=_STATUS_SORT_ORDER[status],
        current_label=build_current_label(artifact),
        current_sort_order=0 if artifact.is_current else 1,
        file_name=artifact.file_name,
        sha256=artifact.sha256,
        sha256_short=sha256_short,
        imported_at_utc=artifact.imported_at_utc,
        search_text=" ".join(part.casefold() for part in search_parts if part),
        artifact=artifact,
    )


def filter_firmware_catalog_rows(
    rows: Iterable[FirmwareCatalogRow],
    *,
    search_text: str = "",
    target_filter: str = ALL_FIRMWARE_FILTER,
    status_filter: str = ALL_FIRMWARE_FILTER,
    current_only: bool = False,
) -> list[FirmwareCatalogRow]:
    normalized_search = str(search_text or "").strip().casefold()
    normalized_target = str(target_filter or ALL_FIRMWARE_FILTER).strip().lower()
    normalized_status = str(status_filter or ALL_FIRMWARE_FILTER).strip().lower()

    filtered: list[FirmwareCatalogRow] = []
    for row in rows:
        if current_only and not row.artifact.is_current:
            continue
        if normalized_target != ALL_FIRMWARE_FILTER and row.artifact.target_kind.value != normalized_target:
            continue
        if normalized_status != ALL_FIRMWARE_FILTER and row.artifact.status.value != normalized_status:
            continue
        if normalized_search and normalized_search not in row.search_text:
            continue
        filtered.append(row)
    return filtered


def build_firmware_detail(artifact: FirmwareArtifact | None) -> FirmwareArtifactDetail:
    if artifact is None:
        return FirmwareArtifactDetail(
            scalar_fields=(
                ("Artifact ID", "-"),
                ("SHA-256", "-"),
                ("Ruta gestionada", "-"),
                ("Tamaño", "-"),
                ("Target", "-"),
                ("Variante", "-"),
                ("Status", "-"),
                ("Current", "-"),
                ("Nombre", "-"),
                ("Versión", "-"),
                ("Etiqueta", "-"),
                ("Origen", "-"),
                ("Notas origen", "-"),
                ("Compatibilidad", "-"),
                ("Tags", "-"),
                ("Importado UTC", "-"),
                ("Creado UTC", "-"),
            ),
            changelog="—",
            notes="—",
        )

    return FirmwareArtifactDetail(
        scalar_fields=(
            ("Artifact ID", artifact.artifact_id),
            ("SHA-256", artifact.sha256),
            ("Ruta gestionada", artifact.file_path),
            ("Tamaño", build_file_size_text(artifact.file_size)),
            ("Target", build_target_label(artifact.target_kind)),
            ("Variante", artifact.target_variant),
            ("Status", build_status_label(artifact.status)),
            ("Current", build_current_label(artifact)),
            ("Nombre", artifact.display_name),
            ("Versión", artifact.version),
            ("Etiqueta", artifact.version_label),
            ("Origen", artifact.source_kind),
            ("Notas origen", artifact.source_notes or "—"),
            ("Compatibilidad", ", ".join(artifact.compatibility) if artifact.compatibility else "—"),
            ("Tags", ", ".join(artifact.tags) if artifact.tags else "—"),
            ("Importado UTC", artifact.imported_at_utc),
            ("Creado UTC", artifact.created_at_utc),
        ),
        changelog=artifact.changelog or "—",
        notes=artifact.notes or "—",
    )


def build_target_filter_options() -> list[tuple[str, str]]:
    return [(ALL_FIRMWARE_FILTER, "Todos")] + [
        (item.value, item.value) for item in FirmwareTargetKind
    ]


def build_status_filter_options() -> list[tuple[str, str]]:
    return [(ALL_FIRMWARE_FILTER, "Todos")] + [
        (item.value, item.value) for item in FirmwareStatus
    ]


def build_empty_catalog_state(*, total_artifacts: int, filtered_artifacts: int) -> tuple[str, str]:
    if total_artifacts <= 0:
        return (
            "Aún no hay artefactos firmware registrados",
            "Usa Importar firmware para agregar el primero.",
        )
    if filtered_artifacts <= 0:
        return (
            "No hay artefactos que coincidan con los filtros actuales",
            "Ajusta texto, target o status para ver resultados.",
        )
    return ("", "")


def build_import_feedback(result: FirmwareImportResult) -> FirmwareImportFeedback:
    warnings_text = summarize_warnings(result.warnings)
    if not result.success:
        details = warnings_text if warnings_text != "Sin advertencias." else ""
        return FirmwareImportFeedback(
            title="Importación fallida",
            summary=result.message or "No se pudo importar el firmware.",
            details=details,
            severity="error",
        )

    artifact_label = result.artifact_id or "artefacto sin id"
    if result.was_duplicate:
        summary = (
            "Duplicado detectado: se reutilizó el artefacto existente "
            f"{artifact_label}."
        )
        if result.current_changed:
            summary += " También quedó marcado como current."
        return FirmwareImportFeedback(
            title="Firmware duplicado",
            summary=summary,
            details=warnings_text,
            severity="warning" if result.warnings else "info",
        )

    summary = (
        f"Firmware importado correctamente como {artifact_label}."
    )
    if result.current_changed:
        summary += " Quedó marcado como current para su target."
    return FirmwareImportFeedback(
        title="Firmware importado",
        summary=summary,
        details=warnings_text,
        severity="warning" if result.warnings else "info",
    )


def summarize_warnings(warnings: Iterable[str] | None) -> str:
    warning_list = [str(item).strip() for item in (warnings or ()) if str(item).strip()]
    if not warning_list:
        return "Sin advertencias."
    return "\n".join(f"- {item}" for item in warning_list)


def build_current_summary(artifact: FirmwareArtifact | None) -> str:
    if artifact is None:
        return "Sin selección."
    if artifact.is_current:
        return (
            f"Current activo para {artifact.target_kind.value}/{artifact.target_variant}."
        )
    return (
        f"No es current para {artifact.target_kind.value}/{artifact.target_variant}."
    )


def build_mark_current_confirmation_text(artifact: FirmwareArtifact) -> str:
    return (
        "Este firmware pasará a ser el current para el target "
        f"{artifact.target_kind.value}/{artifact.target_variant}. ¿Continuar?"
    )


def build_target_label(target_kind: FirmwareTargetKind | str) -> str:
    return normalize_target_kind(target_kind).value


def build_status_label(status: FirmwareStatus | str) -> str:
    return coerce_firmware_status(status).value


def build_current_label(artifact: FirmwareArtifact) -> str:
    return "Sí" if artifact.is_current else "No"


def build_sha256_short(sha256: str, *, size: int = 12) -> str:
    text = str(sha256 or "").strip()
    if len(text) <= size:
        return text
    return text[:size]


def build_file_size_text(file_size: int) -> str:
    size = int(file_size)
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KiB"
    return f"{size / (1024 * 1024):.2f} MiB"


def build_display_name_suggestion(path: str | Path) -> str:
    source = Path(path)
    stem = source.stem.strip()
    if not stem:
        return source.name
    text = _DISPLAY_NAME_SEPARATOR_PATTERN.sub(" ", stem)
    return re.sub(r"\s+", " ", text).strip()


def build_version_sort_key(version: str) -> tuple[object, ...]:
    tokens = re.split(r"([0-9]+)", str(version or "").strip().casefold())
    result: list[object] = []
    for token in tokens:
        if not token:
            continue
        if token.isdigit():
            result.append((1, int(token)))
        else:
            result.append((0, token))
    return tuple(result)
