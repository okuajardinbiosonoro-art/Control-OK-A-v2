from __future__ import annotations

import hashlib
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.firmware import (  # noqa: E402
    FirmwareArtifact,
    FirmwareCatalogStore,
    FirmwareImportRequest,
    FirmwareIngestService,
    OtaManifestService,
    OtaManifestValidationError,
    OtaRolloutPublishRequest,
)


def _build_services(
    tmp_path: Path,
) -> tuple[FirmwareCatalogStore, FirmwareIngestService, OtaManifestService]:
    catalog_path = tmp_path / "artifacts" / "firmware_catalog.json"
    store = FirmwareCatalogStore(catalog_path)
    ingest_service = FirmwareIngestService(store)
    manifest_service = OtaManifestService(store, publish_root_dir=tmp_path / "ota_http_root")
    return store, ingest_service, manifest_service


def _import_artifact(
    tmp_path: Path,
    *,
    target_kind: str = "plant",
    target_variant: str = "eb1",
    version: str = "1.2.3",
    status: str = "current",
    content: bytes = b"ota-artifact",
) -> FirmwareArtifact:
    store, ingest_service, _manifest_service = _build_services(tmp_path)
    source_path = tmp_path / f"{target_kind}_{target_variant}.bin"
    source_path.write_bytes(content)

    result = ingest_service.import_artifact(
        FirmwareImportRequest(
            source_file_path=source_path,
            target_kind=target_kind,
            target_variant=target_variant,
            version=version,
            status=status,
            display_name=f"{target_kind}-{target_variant}",
            changelog="Ajuste OTA inicial",
            source_kind="manual_import",
        )
    )

    assert result.success is True
    artifact = result.imported_artifact
    assert artifact is not None
    store.save()
    return artifact


def test_build_manifest_from_valid_artifact_produces_expected_fields(tmp_path: Path) -> None:
    artifact = _import_artifact(tmp_path, version="1.2.3", status="current")
    _store, _ingest_service, manifest_service = _build_services(tmp_path)

    manifest = manifest_service.build_manifest(
        OtaRolloutPublishRequest(
            rollout_token="0x20260328",
            rollout_id="plant-eb1-2026-03-28-r1",
            artifact_id=artifact.artifact_id,
            host="192.168.88.254",
            port=8080,
            rollout_channel="stable",
        )
    )

    assert manifest.rollout_id == "plant-eb1-2026-03-28-r1"
    assert manifest.target_kind == "plant"
    assert manifest.target_variant == "eb1"
    assert manifest.version == "1.2.3"
    assert manifest.version_code == 10203
    assert manifest.artifact_id == artifact.artifact_id
    assert manifest.sha256 == artifact.sha256
    assert manifest.file_size == artifact.file_size
    assert manifest.download_url == "http://192.168.88.254:8080/ota/rollouts/20260328/firmware.bin"
    assert manifest.firmware_family == "okua_node_udp_v1"
    assert manifest.build_profile == "field"
    assert manifest.protocol_version == "okua_v1"
    assert manifest.compatible_hw == ("esp32dev",)
    assert manifest.flags.allow_downgrade is False


def test_build_manifest_infers_build_profile_from_artifact_tags_when_request_omits_it(
    tmp_path: Path,
) -> None:
    store, ingest_service, manifest_service = _build_services(tmp_path)
    source_path = tmp_path / "plant_ed1_test.bin"
    source_path.write_bytes(b"ota-profile-test")

    import_result = ingest_service.import_artifact(
        FirmwareImportRequest(
            source_file_path=source_path,
            target_kind="plant",
            target_variant="ed1",
            version="1.0.2-dev",
            status="situational",
            display_name="plant-ed1-test",
            changelog="Comparativo OTA test",
            source_kind="artifact_agent",
            tags=("ota_b", "situational", "comparative", "build_profile_test"),
        )
    )
    assert import_result.success is True
    artifact = import_result.imported_artifact
    assert artifact is not None
    store.save()

    manifest = manifest_service.build_manifest(
        OtaRolloutPublishRequest(
            rollout_token="0x20260331",
            artifact_id=artifact.artifact_id,
            host="192.168.1.70",
            port=8080,
        )
    )

    assert manifest.target_kind == "plant"
    assert manifest.target_variant == "ed1"
    assert manifest.build_profile == "test"


def test_publish_rollout_creates_manifest_and_self_contained_bin(tmp_path: Path) -> None:
    artifact = _import_artifact(tmp_path, version="2.0.0", status="beta", content=b"payload-ota")
    _store, _ingest_service, manifest_service = _build_services(tmp_path)

    result = manifest_service.publish_rollout(
        OtaRolloutPublishRequest(
            rollout_token="20260329",
            artifact_id=artifact.artifact_id,
            rollout_id="plant-eb1-2026-03-29-r1",
            host="127.0.0.1",
            port=18080,
        )
    )

    manifest_path = Path(result.manifest_path)
    firmware_path = Path(result.firmware_path)

    assert result.success is True
    assert manifest_path.exists()
    assert firmware_path.exists()
    assert Path(result.published_dir).name == "20260329"
    assert result.manifest_url.endswith("/ota/rollouts/20260329/manifest.json")
    assert result.download_url.endswith("/ota/rollouts/20260329/firmware.bin")
    assert "beta" in result.warnings[0].lower()
    assert firmware_path.read_bytes() == b"payload-ota"


def test_publish_rollout_can_mark_manifest_as_allow_downgrade(tmp_path: Path) -> None:
    artifact = _import_artifact(tmp_path, version="2.0.0", status="situational", content=b"payload-downgrade")
    _store, _ingest_service, manifest_service = _build_services(tmp_path)

    result = manifest_service.publish_rollout(
        OtaRolloutPublishRequest(
            rollout_token="20260340",
            artifact_id=artifact.artifact_id,
            host="192.168.80.14",
            port=8080,
            allow_downgrade=True,
        )
    )

    assert result.success is True
    assert result.manifest is not None
    assert result.manifest.flags.allow_downgrade is True
    assert any("allow_downgrade" in warning for warning in result.warnings)


def test_publish_rollout_rejects_unknown_target(tmp_path: Path) -> None:
    store, _ingest_service, manifest_service = _build_services(tmp_path)
    managed_dir = store.catalog_path.parent / "firmware_store"
    managed_dir.mkdir(parents=True, exist_ok=True)
    firmware_path = managed_dir / ("a" * 64 + ".bin")
    firmware_path.write_bytes(b"unknown-target")
    sha256 = hashlib.sha256(b"unknown-target").hexdigest()

    artifact = FirmwareArtifact(
        artifact_id=sha256,
        display_name="unknown",
        version="1.0.0",
        version_label="1.0.0",
        target_kind="unknown",
        target_variant="generic",
        status="situational",
        file_name="unknown.bin",
        file_path=str(firmware_path),
        sha256=sha256,
        file_size=firmware_path.stat().st_size,
    )
    store.add_artifact(artifact)
    store.save()

    try:
        manifest_service.publish_rollout(
            OtaRolloutPublishRequest(
                rollout_token="20260330",
                artifact_id=artifact.artifact_id,
                host="127.0.0.1",
                port=8080,
            )
        )
        assert False, "La publicación OTA debió rechazar target_kind=unknown"
    except OtaManifestValidationError as exc:
        assert "target_kind=unknown" in str(exc)


def test_publish_rollout_rejects_missing_or_drifted_managed_bin(tmp_path: Path) -> None:
    store, _ingest_service, manifest_service = _build_services(tmp_path)
    managed_dir = store.catalog_path.parent / "firmware_store"
    managed_dir.mkdir(parents=True, exist_ok=True)
    firmware_path = managed_dir / "drifted.bin"
    firmware_path.write_bytes(b"real-content")
    sha256 = hashlib.sha256(b"other-content").hexdigest()

    artifact = FirmwareArtifact(
        artifact_id=sha256,
        display_name="drifted",
        version="1.0.1",
        version_label="1.0.1",
        target_kind="plant",
        target_variant="eb1",
        status="beta",
        file_name="drifted.bin",
        file_path=str(firmware_path),
        sha256=sha256,
        file_size=firmware_path.stat().st_size,
    )
    store.add_artifact(artifact)
    store.save()

    try:
        manifest_service.publish_rollout(
            OtaRolloutPublishRequest(
                rollout_token="20260331",
                artifact_id=artifact.artifact_id,
                host="127.0.0.1",
                port=8080,
            )
        )
        assert False, "La publicación OTA debió rechazar bin drifted"
    except OtaManifestValidationError as exc:
        assert "sha256 del bin" in str(exc).lower()


def test_publish_rollout_rejects_unparseable_version_for_version_code(tmp_path: Path) -> None:
    store, _ingest_service, manifest_service = _build_services(tmp_path)
    managed_dir = store.catalog_path.parent / "firmware_store"
    managed_dir.mkdir(parents=True, exist_ok=True)
    firmware_bytes = b"manual-version-bin"
    sha256 = hashlib.sha256(firmware_bytes).hexdigest()
    firmware_path = managed_dir / f"{sha256}.bin"
    firmware_path.write_bytes(firmware_bytes)

    artifact = FirmwareArtifact(
        artifact_id=sha256,
        display_name="manual-version",
        version="release-candidate",
        version_label="release-candidate",
        target_kind="plant",
        target_variant="eb1",
        status="beta",
        file_name="manual-version.bin",
        file_path=str(firmware_path),
        sha256=sha256,
        file_size=len(firmware_bytes),
    )
    store.add_artifact(artifact)
    store.save()

    try:
        manifest_service.build_manifest(
            OtaRolloutPublishRequest(
                rollout_token="20260401",
                artifact_id=artifact.artifact_id,
                host="127.0.0.1",
                port=8080,
            )
        )
        assert False, "La generación OTA debió exigir semver para version_code"
    except OtaManifestValidationError as exc:
        assert "semver" in str(exc).lower()
