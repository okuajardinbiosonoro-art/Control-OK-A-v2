from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
import re
import tempfile

from control_okua.core.firmware.catalog_models import (
    FirmwareArtifact,
    FirmwareCatalogValidationError,
    FirmwareStatus,
    format_utc_timestamp,
    utc_now_iso,
)
from control_okua.core.firmware.catalog_store import (
    FirmwareCatalogStore,
    FirmwareCatalogStoreError,
)
from control_okua.core.firmware.ingest_models import (
    FirmwareDeleteResult,
    FirmwareImportRequest,
    FirmwareImportResult,
    FirmwareImportValidationError,
)


DEFAULT_MANAGED_FIRMWARE_STORE_DIRNAME = "firmware_store"
_DISPLAY_NAME_SEPARATOR_PATTERN = re.compile(r"[_\-]+")
_ALLOWED_FIRMWARE_SUFFIXES = {".bin"}


class FirmwareIngestService:
    def __init__(
        self,
        catalog_store: FirmwareCatalogStore | None = None,
        *,
        managed_store_dir: Path | str | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._catalog_store = catalog_store or FirmwareCatalogStore()
        self._managed_store_dir = (
            Path(managed_store_dir).expanduser()
            if managed_store_dir is not None
            else self._catalog_store.catalog_path.parent / DEFAULT_MANAGED_FIRMWARE_STORE_DIRNAME
        )
        self._logger = logger or logging.getLogger(__name__)

    @property
    def catalog_store(self) -> FirmwareCatalogStore:
        return self._catalog_store

    @property
    def managed_store_dir(self) -> Path:
        return self._managed_store_dir

    def import_artifact(self, request: FirmwareImportRequest) -> FirmwareImportResult:
        warnings: list[str] = []
        created_managed_file: Path | None = None
        try:
            resolved_request = self._coerce_request(request)
            source_path = Path(resolved_request.source_file_path).resolve()
            source_bytes = self._read_source_bytes(source_path)
            sha256 = hashlib.sha256(source_bytes).hexdigest()
            file_size = len(source_bytes)
            imported_at_utc = utc_now_iso()
            created_at_utc = self._resolve_created_at_utc(source_path, fallback=imported_at_utc)

            self._catalog_store.load()
            existing_artifact = self._catalog_store.find_by_sha256(sha256)
            managed_path = self._build_managed_store_path(source_path, sha256)

            stored_file_path = str(source_path)
            if resolved_request.copy_to_managed_store:
                stored_file_path, reused_managed_path = self._ensure_managed_copy(
                    source_path=source_path,
                    source_bytes=source_bytes,
                    managed_path=managed_path,
                )
                if not reused_managed_path:
                    created_managed_file = Path(stored_file_path)
                if reused_managed_path:
                    warnings.append("Se reutilizó el bin gestionado existente para ese sha256.")

            if existing_artifact is not None:
                updated_existing = existing_artifact
                catalog_updated = False
                if (
                    resolved_request.copy_to_managed_store
                    and existing_artifact.file_path != stored_file_path
                ):
                    updated_existing = replace(existing_artifact, file_path=stored_file_path)
                    self._catalog_store.replace_artifact(updated_existing)
                    catalog_updated = True
                    warnings.append(
                        "El artefacto duplicado ya existía y se actualizó su ruta al store gestionado."
                    )

                warnings.extend(
                    self._duplicate_metadata_warnings(updated_existing, resolved_request)
                )

                current_changed = False
                if resolved_request.mark_as_current:
                    if updated_existing.matches_target(
                        resolved_request.target_kind,
                        resolved_request.target_variant,
                    ):
                        previous_current = self._catalog_store.get_current_for_target(
                            resolved_request.target_kind,
                            resolved_request.target_variant,
                        )
                        promoted = self._catalog_store.set_current(updated_existing.artifact_id)
                        updated_existing = promoted
                        if previous_current is None or previous_current.artifact_id != promoted.artifact_id:
                            current_changed = True
                    else:
                        warnings.append(
                            "No se promovió el duplicado a current porque su target difiere del solicitado."
                        )

                if catalog_updated or current_changed:
                    self._catalog_store.save()

                return FirmwareImportResult(
                    success=True,
                    artifact_id=updated_existing.artifact_id,
                    sha256=updated_existing.sha256,
                    was_duplicate=True,
                    stored_file_path=updated_existing.file_path,
                    catalog_updated=catalog_updated,
                    current_changed=current_changed,
                    imported_artifact=updated_existing,
                    message="Artefacto duplicado detectado; se reutilizó la entrada existente.",
                    warnings=tuple(warnings),
                )

            display_name = resolved_request.display_name or _default_display_name(source_path)
            artifact = FirmwareArtifact(
                artifact_id=sha256,
                display_name=display_name,
                version=resolved_request.version,
                version_label=resolved_request.version_label,
                target_kind=resolved_request.target_kind,
                target_variant=resolved_request.target_variant,
                status=resolved_request.status,
                file_name=source_path.name,
                file_path=stored_file_path,
                sha256=sha256,
                file_size=file_size,
                created_at_utc=created_at_utc,
                imported_at_utc=imported_at_utc,
                source_kind=resolved_request.source_kind,
                source_notes=resolved_request.source_notes,
                changelog=resolved_request.changelog,
                notes=resolved_request.notes,
                compatibility=resolved_request.compatibility,
                tags=resolved_request.tags,
            )
            imported_artifact = self._catalog_store.add_artifact(artifact)
            current_changed = False
            if resolved_request.mark_as_current:
                previous_current = self._catalog_store.get_current_for_target(
                    resolved_request.target_kind,
                    resolved_request.target_variant,
                )
                imported_artifact = self._catalog_store.set_current(imported_artifact.artifact_id)
                if previous_current is None or previous_current.artifact_id != imported_artifact.artifact_id:
                    current_changed = True

            self._catalog_store.save()
            return FirmwareImportResult(
                success=True,
                artifact_id=imported_artifact.artifact_id,
                sha256=imported_artifact.sha256,
                was_duplicate=False,
                stored_file_path=imported_artifact.file_path,
                catalog_updated=True,
                current_changed=current_changed,
                imported_artifact=imported_artifact,
                message="Artefacto de firmware importado correctamente.",
                warnings=tuple(warnings),
            )
        except (
            FirmwareImportValidationError,
            FirmwareCatalogValidationError,
            FirmwareCatalogStoreError,
            OSError,
        ) as exc:
            self._cleanup_created_managed_file(created_managed_file)
            self._rollback_catalog_state()
            self._logger.warning("Importación de firmware falló: %s", exc)
            return FirmwareImportResult(
                success=False,
                message=str(exc),
                warnings=tuple(warnings),
            )

    def delete_artifact(self, artifact_id: str) -> FirmwareDeleteResult:
        warnings: list[str] = []
        try:
            self._catalog_store.load()
            artifact = self._catalog_store.get_by_id(artifact_id)
            if artifact is None:
                raise FirmwareCatalogStoreError(
                    f"No se encontró el artifact a eliminar: {artifact_id}"
                )

            managed_file_deleted = False
            managed_file_path = normalize_path_or_none(artifact.file_path)
            managed_path = Path(managed_file_path) if managed_file_path else None
            if managed_path is not None and self._is_inside_managed_store(managed_path):
                if managed_path.exists():
                    managed_path.unlink()
                    managed_file_deleted = True
                else:
                    warnings.append("El bin gestionado ya no existía en disco; se eliminó solo la entrada del catálogo.")
            elif managed_file_path:
                warnings.append("El artifact apuntaba fuera del managed store; se eliminó solo la entrada del catálogo.")

            deleted_artifact = self._catalog_store.remove_artifact(artifact.artifact_id)
            self._catalog_store.save()
            return FirmwareDeleteResult(
                success=True,
                artifact_id=deleted_artifact.artifact_id,
                deleted_artifact=deleted_artifact,
                catalog_updated=True,
                managed_file_deleted=managed_file_deleted,
                managed_file_path=managed_file_path,
                message="Artifact eliminado correctamente del catálogo.",
                warnings=tuple(warnings),
            )
        except (
            FirmwareCatalogValidationError,
            FirmwareCatalogStoreError,
            OSError,
        ) as exc:
            self._rollback_catalog_state()
            self._logger.warning("Eliminación de firmware falló: %s", exc)
            return FirmwareDeleteResult(
                success=False,
                message=str(exc),
                warnings=tuple(warnings),
            )

    def _coerce_request(self, request: FirmwareImportRequest) -> FirmwareImportRequest:
        if isinstance(request, FirmwareImportRequest):
            return request
        raise FirmwareImportValidationError("request invalido: se esperaba FirmwareImportRequest")

    def _read_source_bytes(self, source_path: Path) -> bytes:
        if not source_path.exists():
            raise FirmwareImportValidationError(
                f"Archivo fuente de firmware no existe: '{source_path}'"
            )
        if not source_path.is_file():
            raise FirmwareImportValidationError(
                f"Ruta fuente no es un archivo regular: '{source_path}'"
            )
        if source_path.suffix.lower() not in _ALLOWED_FIRMWARE_SUFFIXES:
            raise FirmwareImportValidationError(
                f"Extensión de firmware no soportada: '{source_path.suffix}'"
            )

        try:
            payload = source_path.read_bytes()
        except OSError as exc:
            raise FirmwareImportValidationError(
                f"No se pudo leer el archivo fuente '{source_path}': {exc}"
            ) from exc

        if not payload:
            raise FirmwareImportValidationError(
                f"Archivo firmware vacío: '{source_path}'"
            )
        return payload

    def _resolve_created_at_utc(self, source_path: Path, *, fallback: str) -> str:
        try:
            stat_result = source_path.stat()
            return format_utc_timestamp(datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc))
        except OSError:
            return fallback

    def _build_managed_store_path(self, source_path: Path, sha256: str) -> Path:
        return self._managed_store_dir / f"{sha256}{source_path.suffix.lower()}"

    def _ensure_managed_copy(
        self,
        *,
        source_path: Path,
        source_bytes: bytes,
        managed_path: Path,
    ) -> tuple[str, bool]:
        resolved_managed_path = managed_path.resolve()
        if source_path.resolve() == resolved_managed_path:
            return str(resolved_managed_path), True
        if resolved_managed_path.exists():
            return str(resolved_managed_path), True

        resolved_managed_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "wb",
                dir=resolved_managed_path.parent,
                prefix=f"{resolved_managed_path.stem}.",
                suffix=".tmp",
                delete=False,
            ) as tmp_file:
                tmp_file.write(source_bytes)
                tmp_path = Path(tmp_file.name)
            tmp_path.replace(resolved_managed_path)
        except OSError as exc:
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise FirmwareCatalogStoreError(
                f"No se pudo copiar firmware al store gestionado '{resolved_managed_path}': {exc}"
            ) from exc
        return str(resolved_managed_path), False

    def _duplicate_metadata_warnings(
        self,
        artifact: FirmwareArtifact,
        request: FirmwareImportRequest,
    ) -> list[str]:
        warnings: list[str] = []
        if artifact.version != request.version:
            warnings.append(
                "El artefacto duplicado ya existe con una versión distinta; se conserva la metadata original."
            )
        if not artifact.matches_target(request.target_kind, request.target_variant):
            warnings.append(
                "El artefacto duplicado ya existe con un target distinto; no se modificó su clasificación."
            )
        return warnings

    def _rollback_catalog_state(self) -> None:
        try:
            if self._catalog_store.catalog_path.exists():
                self._catalog_store.load()
        except Exception:
            return

    def _cleanup_created_managed_file(self, managed_file_path: Path | None) -> None:
        if managed_file_path is None or not managed_file_path.exists():
            return
        try:
            managed_file_path.unlink()
        except OSError:
            return

    def _is_inside_managed_store(self, path: Path) -> bool:
        try:
            resolved_managed_dir = self._managed_store_dir.resolve()
            resolved_path = path.resolve()
        except OSError:
            return False
        return resolved_path.is_relative_to(resolved_managed_dir)


def _default_display_name(source_path: Path) -> str:
    stem = source_path.stem.strip()
    if not stem:
        return source_path.name
    text = _DISPLAY_NAME_SEPARATOR_PATTERN.sub(" ", stem)
    return re.sub(r"\s+", " ", text).strip()


def normalize_path_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
