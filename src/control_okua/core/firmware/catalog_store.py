from __future__ import annotations

from dataclasses import replace
import json
import logging
from pathlib import Path
import sys
import tempfile

from control_okua.core.firmware.catalog_models import (
    FirmwareArtifact,
    FirmwareCatalog,
    FirmwareCatalogValidationError,
    FirmwareStatus,
    FirmwareTargetKind,
    coerce_firmware_status,
    normalize_sha256,
    normalize_target_kind,
    normalize_target_variant,
    utc_now_iso,
)
from control_okua.core.firmware.catalog_schema import (
    FirmwareCatalogSchemaError,
    catalog_from_dict,
    catalog_to_dict,
)


DEFAULT_FIRMWARE_CATALOG_FILENAME = "firmware_catalog.json"


class FirmwareCatalogStoreError(RuntimeError):
    """Base error for firmware catalog persistence."""


class FirmwareArtifactNotFoundError(FirmwareCatalogStoreError):
    """Raised when a firmware artifact cannot be found in the catalog."""


def resolve_firmware_catalog_path() -> Path:
    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).resolve().parent
    else:
        base_dir = Path(__file__).resolve().parents[4]
    return base_dir / "artifacts" / DEFAULT_FIRMWARE_CATALOG_FILENAME


class FirmwareCatalogStore:
    def __init__(
        self,
        catalog_path: Path | str | None = None,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._catalog_path = (
            Path(catalog_path).expanduser()
            if catalog_path is not None
            else resolve_firmware_catalog_path()
        )
        self._logger = logger or logging.getLogger(__name__)
        self._catalog = FirmwareCatalog.empty()

    @property
    def catalog(self) -> FirmwareCatalog:
        return self._catalog

    @property
    def catalog_path(self) -> Path:
        return self._catalog_path

    def load(self) -> FirmwareCatalog:
        if not self._catalog_path.exists():
            self._catalog = FirmwareCatalog.empty()
            self.save(self._catalog)
            return self._catalog

        try:
            raw_text = self._catalog_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            self._logger.warning(
                "No se pudo leer catalogo de firmware '%s': %s",
                self._catalog_path,
                exc,
            )
            self._catalog = FirmwareCatalog.empty()
            return self._catalog

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            return self._recover_from_corrupt_file(reason=f"JSON corrupto: {exc}")

        try:
            catalog, issues = catalog_from_dict(
                payload,
                base_dir=self._catalog_path.parent,
            )
        except (FirmwareCatalogSchemaError, FirmwareCatalogValidationError, TypeError, ValueError) as exc:
            return self._recover_from_corrupt_file(reason=str(exc))

        self._catalog = catalog
        for issue in issues:
            self._logger.warning(
                "Catalogo de firmware '%s' normalizado: %s",
                self._catalog_path,
                issue,
            )

        canonical_payload = catalog_to_dict(catalog)
        if payload != canonical_payload:
            self.save(catalog)
        return self._catalog

    def save(self, catalog: FirmwareCatalog | None = None) -> FirmwareCatalog:
        if catalog is not None:
            self._catalog = catalog

        payload = catalog_to_dict(self._catalog)
        serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

        self._catalog_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self._catalog_path.parent,
                prefix=f"{self._catalog_path.stem}.",
                suffix=".tmp",
                delete=False,
            ) as tmp_file:
                tmp_file.write(serialized)
                tmp_path = Path(tmp_file.name)
            tmp_path.replace(self._catalog_path)
        except OSError as exc:
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise FirmwareCatalogStoreError(
                f"No se pudo guardar catalogo de firmware en '{self._catalog_path}': {exc}"
            ) from exc
        return self._catalog

    def list_all(self) -> list[FirmwareArtifact]:
        return list(self._catalog.artifacts)

    def get_by_id(self, artifact_id: str) -> FirmwareArtifact | None:
        normalized_sha256 = normalize_sha256_or_none(artifact_id)
        for artifact in self._catalog.artifacts:
            if artifact.artifact_id == artifact_id:
                return artifact
            if normalized_sha256 is not None and artifact.sha256 == normalized_sha256:
                return artifact
        return None

    def find_by_sha256(self, sha256: str) -> FirmwareArtifact | None:
        normalized_sha256 = normalize_sha256(sha256)
        for artifact in self._catalog.artifacts:
            if artifact.sha256 == normalized_sha256:
                return artifact
        return None

    def resolve_duplicate_by_hash(self, artifact_or_sha256: FirmwareArtifact | str) -> FirmwareArtifact | None:
        if isinstance(artifact_or_sha256, FirmwareArtifact):
            return self.find_by_sha256(artifact_or_sha256.sha256)
        return self.find_by_sha256(artifact_or_sha256)

    def filter_by_target(
        self,
        target_kind: FirmwareTargetKind | str | None,
        target_variant: str | None = None,
    ) -> list[FirmwareArtifact]:
        normalized_kind = normalize_target_kind(target_kind)
        normalized_variant = (
            normalize_target_variant(target_variant)
            if target_variant is not None
            else None
        )
        return [
            artifact
            for artifact in self._catalog.artifacts
            if artifact.target_kind is normalized_kind
            and (normalized_variant is None or artifact.target_variant == normalized_variant)
        ]

    def filter_by_status(self, status: FirmwareStatus | str) -> list[FirmwareArtifact]:
        normalized_status = coerce_firmware_status(status)
        return [
            artifact
            for artifact in self._catalog.artifacts
            if artifact.status is normalized_status
        ]

    def get_current_for_target(
        self,
        target_kind: FirmwareTargetKind | str | None,
        target_variant: str = "generic",
    ) -> FirmwareArtifact | None:
        normalized_kind = normalize_target_kind(target_kind)
        normalized_variant = normalize_target_variant(target_variant)
        for artifact in self._catalog.artifacts:
            if (
                artifact.target_kind is normalized_kind
                and artifact.target_variant == normalized_variant
                and artifact.is_current
            ):
                return artifact
        return None

    def add_artifact(self, artifact: FirmwareArtifact) -> FirmwareArtifact:
        duplicate = self.resolve_duplicate_by_hash(artifact)
        if duplicate is not None:
            return duplicate

        updated_artifacts = tuple(self._catalog.artifacts) + (artifact,)
        self._catalog = replace(
            self._catalog,
            artifacts=updated_artifacts,
            updated_at_utc=utc_now_iso(),
        )
        return artifact

    def set_current(self, artifact_id: str) -> FirmwareArtifact:
        target_artifact = self.get_by_id(artifact_id)
        if target_artifact is None:
            raise FirmwareArtifactNotFoundError(
                f"Firmware no encontrado para marcar current: {artifact_id}"
            )

        previous_current = self.get_current_for_target(
            target_artifact.target_kind,
            target_artifact.target_variant,
        )
        updated_artifacts: list[FirmwareArtifact] = []
        for artifact in self._catalog.artifacts:
            if artifact.artifact_id == target_artifact.artifact_id:
                updated = artifact.with_status(FirmwareStatus.CURRENT)
                if (
                    previous_current is not None
                    and previous_current.artifact_id != artifact.artifact_id
                    and not updated.supersedes_artifact_id
                ):
                    updated = updated.with_supersedes(previous_current.artifact_id)
                updated_artifacts.append(updated)
                continue

            if artifact.target_key == target_artifact.target_key and artifact.is_current:
                updated_artifacts.append(artifact.with_status(FirmwareStatus.OBSOLETE))
                continue

            updated_artifacts.append(artifact)

        self._catalog = replace(
            self._catalog,
            artifacts=tuple(updated_artifacts),
            updated_at_utc=utc_now_iso(),
        )
        resolved = self.get_by_id(target_artifact.artifact_id)
        if resolved is None:
            raise FirmwareCatalogStoreError("No se pudo resolver el firmware current actualizado")
        return resolved

    def _recover_from_corrupt_file(self, *, reason: str) -> FirmwareCatalog:
        backup_path = _build_corrupt_backup_path(self._catalog_path)
        try:
            self._catalog_path.parent.mkdir(parents=True, exist_ok=True)
            if self._catalog_path.exists():
                self._catalog_path.replace(backup_path)
        except OSError as exc:
            self._logger.warning(
                "No se pudo renombrar catalogo corrupto '%s' a backup: %s",
                self._catalog_path,
                exc,
            )
        else:
            self._logger.warning(
                "Catalogo de firmware corrupto movido a '%s': %s",
                backup_path,
                reason,
            )

        self._catalog = FirmwareCatalog.empty()
        self.save(self._catalog)
        return self._catalog


def normalize_sha256_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower().startswith("sha256:"):
        text = text.split(":", 1)[1]
    try:
        return normalize_sha256(text)
    except FirmwareCatalogValidationError:
        return None


def _build_corrupt_backup_path(path: Path) -> Path:
    timestamp = utc_now_iso().replace(":", "").replace("-", "").replace(".", "")
    timestamp = timestamp.replace("T", "_").replace("Z", "Z")
    counter = 1
    candidate = path.with_name(f"{path.stem}.corrupt.{timestamp}{path.suffix}")
    while candidate.exists():
        candidate = path.with_name(
            f"{path.stem}.corrupt.{timestamp}_{counter:02d}{path.suffix}"
        )
        counter += 1
    return candidate
