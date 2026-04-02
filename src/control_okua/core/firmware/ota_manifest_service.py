from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
import shutil
import tempfile

from control_okua.core.firmware.catalog_models import (
    FirmwareArtifact,
    FirmwareStatus,
    FirmwareTargetKind,
    normalize_text,
    utc_now_iso,
)
from control_okua.core.firmware.catalog_store import (
    FirmwareCatalogStore,
    resolve_firmware_catalog_path,
)
from control_okua.core.firmware.ingest_service import DEFAULT_MANAGED_FIRMWARE_STORE_DIRNAME
from control_okua.core.firmware.ota_manifest_models import (
    DEFAULT_OTA_BUILD_PROFILE,
    DEFAULT_OTA_PUBLISH_DIRNAME,
    OTA_MANIFEST_SCHEMA_VERSION,
    OtaManifest,
    OtaManifestFlags,
    OtaManifestValidationError,
    OtaRolloutPublishRequest,
    OtaRolloutPublishResult,
    derive_version_code,
    normalize_rollout_channel,
)


class OtaManifestServiceError(RuntimeError):
    """Base error for OTA rollout manifest publication."""


def resolve_ota_publish_root(catalog_path: Path | str | None = None) -> Path:
    base_catalog_path = (
        Path(catalog_path).expanduser()
        if catalog_path is not None
        else resolve_firmware_catalog_path()
    )
    return base_catalog_path.parent / DEFAULT_OTA_PUBLISH_DIRNAME


class OtaManifestService:
    def __init__(
        self,
        catalog_store: FirmwareCatalogStore | None = None,
        *,
        publish_root_dir: Path | str | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._catalog_store = catalog_store or FirmwareCatalogStore()
        self._publish_root_dir = (
            Path(publish_root_dir).expanduser()
            if publish_root_dir is not None
            else resolve_ota_publish_root(self._catalog_store.catalog_path)
        )
        self._logger = logger or logging.getLogger(__name__)

    @property
    def catalog_store(self) -> FirmwareCatalogStore:
        return self._catalog_store

    @property
    def publish_root_dir(self) -> Path:
        return self._publish_root_dir

    @property
    def managed_store_dir(self) -> Path:
        return self._catalog_store.catalog_path.parent / DEFAULT_MANAGED_FIRMWARE_STORE_DIRNAME

    def resolve_rollout_dir(
        self,
        rollout_token_hex: str,
        *,
        publish_root_dir: Path | None = None,
    ) -> Path:
        root_dir = publish_root_dir or self._publish_root_dir
        return root_dir / "ota" / "rollouts" / rollout_token_hex

    def resolve_manifest_url(self, *, host: str, port: int, rollout_token_hex: str) -> str:
        return f"http://{host}:{port}/ota/rollouts/{rollout_token_hex}/manifest.json"

    def resolve_download_url(self, *, host: str, port: int, rollout_token_hex: str) -> str:
        return f"http://{host}:{port}/ota/rollouts/{rollout_token_hex}/firmware.bin"

    def build_manifest(self, request: OtaRolloutPublishRequest) -> OtaManifest:
        resolved_request = self._coerce_request(request)
        artifact = self._resolve_artifact(resolved_request.artifact_id)
        verified_source_path = self._validate_artifact_for_rollout(artifact)
        self._validate_source_contents(artifact, verified_source_path)

        rollout_channel = self._resolve_rollout_channel(resolved_request, artifact)
        rollout_id = self._resolve_rollout_id(resolved_request, artifact)
        changelog_short = self._resolve_changelog_short(resolved_request, artifact)
        build_profile = self._resolve_build_profile(resolved_request, artifact)
        download_url = self.resolve_download_url(
            host=resolved_request.host,
            port=resolved_request.port,
            rollout_token_hex=resolved_request.rollout_token,
        )

        return OtaManifest(
            schema_version=OTA_MANIFEST_SCHEMA_VERSION,
            rollout_id=rollout_id,
            firmware_family=resolved_request.firmware_family,
            target_kind=artifact.target_kind.value,
            target_variant=artifact.target_variant,
            compatible_hw=tuple(resolved_request.compatible_hw),
            build_profile=build_profile,
            protocol_version=resolved_request.protocol_version,
            version=artifact.version,
            version_code=derive_version_code(artifact.version),
            artifact_id=artifact.artifact_id,
            sha256=artifact.sha256,
            file_size=artifact.file_size,
            download_url=download_url,
            rollout_channel=rollout_channel,
            changelog_short=changelog_short,
            published_at_utc=utc_now_iso(),
            flags=OtaManifestFlags(
                reboot_required=resolved_request.reboot_required,
                allow_auto_rollback=resolved_request.allow_auto_rollback,
                allow_downgrade=resolved_request.allow_downgrade,
            ),
        )

    def publish_rollout(self, request: OtaRolloutPublishRequest) -> OtaRolloutPublishResult:
        resolved_request = self._coerce_request(request)
        artifact = self._resolve_artifact(resolved_request.artifact_id)
        source_path = self._validate_artifact_for_rollout(artifact)
        self._validate_source_contents(artifact, source_path)

        manifest = self.build_manifest(resolved_request)
        rollout_dir = self.resolve_rollout_dir(
            resolved_request.rollout_token,
            publish_root_dir=self._resolve_publish_root_dir(resolved_request),
        )
        firmware_path = rollout_dir / "firmware.bin"
        manifest_path = rollout_dir / "manifest.json"

        existing = self._reuse_existing_rollout_if_identical(
            rollout_dir=rollout_dir,
            manifest=manifest,
            artifact=artifact,
            request=resolved_request,
        )
        if existing is not None:
            return existing

        created_manifest_tmp: Path | None = None
        created_firmware_tmp: Path | None = None
        try:
            rollout_dir.mkdir(parents=True, exist_ok=True)
            created_firmware_tmp = self._copy_atomically(
                source_path,
                firmware_path,
            )
            created_manifest_tmp = self._write_manifest_atomically(
                manifest_path,
                manifest,
            )
        except OSError as exc:
            self._cleanup_temp_file(created_manifest_tmp)
            self._cleanup_temp_file(created_firmware_tmp)
            firmware_path.unlink(missing_ok=True)
            manifest_path.unlink(missing_ok=True)
            raise OtaManifestServiceError(
                f"No se pudo publicar rollout OTA '{manifest.rollout_id}': {exc}"
            ) from exc

        warnings: list[str] = []
        if artifact.status is FirmwareStatus.BETA:
            warnings.append("Se publicó un artefacto beta para OTA.")
        if artifact.status is FirmwareStatus.SITUATIONAL:
            warnings.append("Se publicó un artefacto situacional para OTA.")
        if resolved_request.allow_downgrade:
            warnings.append(
                "El rollout OTA fue publicado con allow_downgrade=true; "
                "el nodo podrá instalar una versión no más nueva si el firmware lo permite."
            )
        if not normalize_text(resolved_request.build_profile):
            inferred_profile = self._infer_build_profile_from_artifact(artifact)
            if inferred_profile:
                warnings.append(
                    f"build_profile inferido desde metadata del artifact: {inferred_profile}"
                )

        return OtaRolloutPublishResult(
            success=True,
            rollout_token=resolved_request.rollout_token,
            rollout_id=manifest.rollout_id,
            artifact_id=artifact.artifact_id,
            published_dir=str(rollout_dir),
            manifest_path=str(manifest_path),
            firmware_path=str(firmware_path),
            manifest_url=self.resolve_manifest_url(
                host=resolved_request.host,
                port=resolved_request.port,
                rollout_token_hex=resolved_request.rollout_token,
            ),
            download_url=manifest.download_url,
            warnings=tuple(warnings),
            manifest=manifest,
            message="Rollout OTA publicado correctamente.",
        )

    def _coerce_request(self, request: OtaRolloutPublishRequest) -> OtaRolloutPublishRequest:
        if isinstance(request, OtaRolloutPublishRequest):
            return request
        raise OtaManifestValidationError(
            "request invalido: se esperaba OtaRolloutPublishRequest"
        )

    def _resolve_publish_root_dir(self, request: OtaRolloutPublishRequest) -> Path:
        return request.publish_root_dir or self._publish_root_dir

    def _resolve_artifact(self, artifact_id: str) -> FirmwareArtifact:
        self._catalog_store.load()
        artifact = self._catalog_store.get_by_id(artifact_id)
        if artifact is None:
            raise OtaManifestValidationError(
                f"artifact_id no existe en el catálogo: {artifact_id!r}"
            )
        return artifact

    def _validate_artifact_for_rollout(self, artifact: FirmwareArtifact) -> Path:
        if artifact.target_kind is FirmwareTargetKind.UNKNOWN:
            raise OtaManifestValidationError(
                "No se puede publicar OTA para target_kind=unknown"
            )
        if artifact.status is FirmwareStatus.OBSOLETE:
            raise OtaManifestValidationError(
                "No se puede publicar OTA para artefactos obsolete"
            )
        if not artifact.version:
            raise OtaManifestValidationError(
                f"El artefacto {artifact.artifact_id} no tiene version válida"
            )
        source_path = Path(artifact.file_path).expanduser().resolve()
        if not source_path.exists() or not source_path.is_file():
            raise OtaManifestValidationError(
                f"El bin del artefacto no existe o no es archivo: '{source_path}'"
            )
        if source_path.suffix.lower() != ".bin":
            raise OtaManifestValidationError(
                f"El artefacto OTA debe apuntar a un .bin válido: '{source_path.name}'"
            )
        if not self._is_managed_store_path(source_path):
            raise OtaManifestValidationError(
                f"El bin OTA debe provenir del managed store: '{source_path}'"
            )
        return source_path

    def _validate_source_contents(self, artifact: FirmwareArtifact, source_path: Path) -> None:
        sha256 = hashlib.sha256()
        total_size = 0
        with source_path.open("rb") as stream:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                total_size += len(chunk)
                sha256.update(chunk)

        resolved_sha256 = sha256.hexdigest()
        if resolved_sha256 != artifact.sha256:
            raise OtaManifestValidationError(
                f"sha256 del bin no coincide con el catálogo para '{artifact.artifact_id}'"
            )
        if total_size != artifact.file_size:
            raise OtaManifestValidationError(
                f"file_size del bin no coincide con el catálogo para '{artifact.artifact_id}'"
            )

    def _resolve_rollout_id(
        self,
        request: OtaRolloutPublishRequest,
        artifact: FirmwareArtifact,
    ) -> str:
        if request.rollout_id:
            return request.rollout_id
        version_token = artifact.version.replace(".", "_")
        return f"{artifact.target_kind.value}-{artifact.target_variant}-{version_token}-{request.rollout_token}"

    def _resolve_rollout_channel(
        self,
        request: OtaRolloutPublishRequest,
        artifact: FirmwareArtifact,
    ) -> str:
        if request.rollout_channel:
            return normalize_rollout_channel(request.rollout_channel)
        if artifact.status is FirmwareStatus.CURRENT:
            return "stable"
        if artifact.status is FirmwareStatus.BETA:
            return "beta"
        if artifact.status is FirmwareStatus.SITUATIONAL:
            return "situational"
        raise OtaManifestValidationError(
            f"No se pudo inferir rollout_channel desde status={artifact.status.value!r}"
        )

    def _resolve_changelog_short(
        self,
        request: OtaRolloutPublishRequest,
        artifact: FirmwareArtifact,
    ) -> str:
        if request.changelog_short:
            return request.changelog_short
        if artifact.changelog:
            first_line = normalize_text(artifact.changelog.splitlines()[0])
            if first_line:
                return first_line
        version_label = artifact.version_label or artifact.version
        return f"{artifact.display_name} {version_label}"

    def _resolve_build_profile(
        self,
        request: OtaRolloutPublishRequest,
        artifact: FirmwareArtifact,
    ) -> str:
        explicit_profile = normalize_text(request.build_profile)
        if explicit_profile:
            return explicit_profile
        inferred_profile = self._infer_build_profile_from_artifact(artifact)
        if inferred_profile:
            return inferred_profile
        return DEFAULT_OTA_BUILD_PROFILE

    @staticmethod
    def _infer_build_profile_from_artifact(artifact: FirmwareArtifact) -> str:
        for tag in artifact.tags:
            normalized = normalize_text(tag).lower()
            if normalized.startswith("build_profile_"):
                candidate = normalize_text(normalized[len("build_profile_") :])
                if candidate:
                    return candidate
            if normalized.startswith("profile_"):
                candidate = normalize_text(normalized[len("profile_") :])
                if candidate:
                    return candidate
        return ""

    def _reuse_existing_rollout_if_identical(
        self,
        *,
        rollout_dir: Path,
        manifest: OtaManifest,
        artifact: FirmwareArtifact,
        request: OtaRolloutPublishRequest,
    ) -> OtaRolloutPublishResult | None:
        manifest_path = rollout_dir / "manifest.json"
        firmware_path = rollout_dir / "firmware.bin"
        if not manifest_path.exists() and not firmware_path.exists():
            return None
        if not manifest_path.exists() or not firmware_path.exists():
            raise OtaManifestValidationError(
                f"El rollout '{manifest.rollout_id}' ya existe parcialmente y no es seguro reutilizarlo: '{rollout_dir}'"
            )

        try:
            existing_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OtaManifestValidationError(
                f"El rollout existente tiene manifest inválido: '{manifest_path}'"
            ) from exc

        expected_payload = manifest.to_dict()
        existing_payload["published_at_utc"] = expected_payload["published_at_utc"]
        if existing_payload != expected_payload:
            raise OtaManifestValidationError(
                f"El rollout token '{rollout_dir.name}' ya está publicado con otro manifest"
            )

        actual_size = firmware_path.stat().st_size
        if actual_size != artifact.file_size:
            raise OtaManifestValidationError(
                f"El rollout existente tiene un firmware.bin con tamaño inesperado: '{firmware_path}'"
            )
        existing_sha256 = hashlib.sha256(firmware_path.read_bytes()).hexdigest()
        if existing_sha256 != artifact.sha256:
            raise OtaManifestValidationError(
                f"El rollout existente tiene un firmware.bin con sha256 inesperado: '{firmware_path}'"
            )

        return OtaRolloutPublishResult(
            success=True,
            rollout_token=rollout_dir.name,
            rollout_id=manifest.rollout_id,
            artifact_id=artifact.artifact_id,
            published_dir=str(rollout_dir),
            manifest_path=str(manifest_path),
            firmware_path=str(firmware_path),
            manifest_url=self.resolve_manifest_url(
                host=request.host,
                port=request.port,
                rollout_token_hex=rollout_dir.name,
            ),
            download_url=manifest.download_url,
            warnings=("El rollout ya existía y se reutilizaron sus archivos publicados.",),
            manifest=manifest,
            message="Rollout OTA ya publicado; se reutilizó sin cambios.",
        )

    def _copy_atomically(self, source_path: Path, target_path: Path) -> Path | None:
        tmp_path: Path | None = None
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=target_path.parent,
            prefix=f"{target_path.stem}.",
            suffix=".tmp",
            delete=False,
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)
        try:
            shutil.copyfile(source_path, tmp_path)
            tmp_path.replace(target_path)
        except OSError:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise
        return tmp_path

    def _write_manifest_atomically(self, target_path: Path, manifest: OtaManifest) -> Path | None:
        serialized = json.dumps(
            manifest.to_dict(),
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        tmp_path: Path | None = None
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=target_path.parent,
            prefix=f"{target_path.stem}.",
            suffix=".tmp",
            delete=False,
        ) as tmp_file:
            tmp_file.write(serialized)
            tmp_path = Path(tmp_file.name)
        try:
            tmp_path.replace(target_path)
        except OSError:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise
        return tmp_path

    def _cleanup_temp_file(self, path: Path | None) -> None:
        if path is None or not path.exists():
            return
        path.unlink(missing_ok=True)

    def _is_managed_store_path(self, path: Path) -> bool:
        try:
            path.relative_to(self.managed_store_dir.resolve())
            return True
        except ValueError:
            return False
