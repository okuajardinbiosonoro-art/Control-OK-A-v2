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
    FirmwareCatalog,
    FirmwareCatalogValidationError,
    FirmwareStatus,
    FirmwareTargetKind,
    artifact_from_dict,
    artifact_to_dict,
    catalog_from_dict,
    catalog_to_dict,
)


def _write_firmware_file(tmp_path: Path, name: str, content: bytes) -> tuple[Path, str, int]:
    file_path = tmp_path / name
    file_path.write_bytes(content)
    sha256 = hashlib.sha256(content).hexdigest()
    return file_path, sha256, len(content)


def _build_artifact(
    artifact_path: Path,
    sha256: str,
    file_size: int,
    **overrides,
) -> FirmwareArtifact:
    payload = {
        "artifact_id": "manual-id",
        "display_name": "Firmware planta",
        "version": "1.2.3",
        "version_label": "v1.2.3",
        "target_kind": "plant",
        "target_variant": "eb1",
        "status": "beta",
        "file_name": artifact_path.name,
        "file_path": str(artifact_path),
        "sha256": sha256,
        "file_size": file_size,
        "created_at_utc": "2026-03-28T14:00:00Z",
        "imported_at_utc": "2026-03-28T14:05:00Z",
        "source_kind": "local",
        "source_notes": "import manual",
        "changelog": "- ajuste de tiempos",
        "notes": "uso de laboratorio",
        "compatibility": ["eb1", "f3"],
        "tags": ["stable", "plant"],
    }
    payload.update(overrides)
    return FirmwareArtifact(**payload)


def test_artifact_valid_normalizes_identity_and_fields(tmp_path: Path) -> None:
    file_path, sha256, file_size = _write_firmware_file(
        tmp_path,
        "firmware_plant.bin",
        b"firmware-plant-v123",
    )

    artifact = _build_artifact(
        file_path,
        sha256,
        file_size,
        artifact_id="custom-id",
        display_name="  Firmware planta EB1  ",
        target_kind="Plant",
        target_variant=" EB1 ",
        status="current",
        file_name="",
        source_kind=" Local Import ",
        tags=[" stable ", "PLANT", "stable"],
    )

    assert artifact.artifact_id == f"sha256:{sha256}"
    assert artifact.file_name == "firmware_plant.bin"
    assert artifact.display_name == "Firmware planta EB1"
    assert artifact.target_kind is FirmwareTargetKind.PLANT
    assert artifact.target_variant == "eb1"
    assert artifact.status is FirmwareStatus.CURRENT
    assert artifact.is_current is True
    assert artifact.source_kind == "local_import"
    assert artifact.tags == ("stable", "plant")


def test_artifact_rejects_invalid_status(tmp_path: Path) -> None:
    file_path, sha256, file_size = _write_firmware_file(
        tmp_path,
        "firmware_invalid.bin",
        b"invalid-status-artifact",
    )

    try:
        _build_artifact(file_path, sha256, file_size, status="released")
        assert False, "FirmwareArtifact debio rechazar un status invalido"
    except FirmwareCatalogValidationError as exc:
        assert "estado de firmware invalido" in str(exc).lower()


def test_artifact_normalizes_invalid_target_kind_to_unknown(tmp_path: Path) -> None:
    file_path, sha256, file_size = _write_firmware_file(
        tmp_path,
        "firmware_unknown.bin",
        b"unknown-target-artifact",
    )

    artifact = _build_artifact(
        file_path,
        sha256,
        file_size,
        target_kind="satellite",
    )

    assert artifact.target_kind is FirmwareTargetKind.UNKNOWN


def test_artifact_rejects_missing_sha256_or_blank_path(tmp_path: Path) -> None:
    file_path, sha256, file_size = _write_firmware_file(
        tmp_path,
        "firmware_required_fields.bin",
        b"required-fields",
    )

    try:
        _build_artifact(file_path, "", file_size)
        assert False, "FirmwareArtifact debio rechazar sha256 vacio"
    except FirmwareCatalogValidationError as exc:
        assert "sha256 invalido" in str(exc).lower()

    try:
        _build_artifact(file_path, sha256, file_size, **{"file_path": "   "})
        assert False, "FirmwareArtifact debio rechazar file_path vacio"
    except FirmwareCatalogValidationError as exc:
        assert "file_path" in str(exc).lower()


def test_schema_roundtrip_preserves_important_fields(tmp_path: Path) -> None:
    file_path, sha256, file_size = _write_firmware_file(
        tmp_path,
        "firmware_roundtrip.bin",
        b"roundtrip-artifact",
    )
    artifact = _build_artifact(file_path, sha256, file_size, status="beta")

    encoded_artifact = artifact_to_dict(artifact)
    restored_artifact = artifact_from_dict(encoded_artifact, base_dir=tmp_path)
    catalog = FirmwareCatalog(artifacts=[artifact])
    encoded_catalog = catalog_to_dict(catalog)
    restored_catalog, issues = catalog_from_dict(encoded_catalog, base_dir=tmp_path)

    assert not issues
    assert restored_artifact.artifact_id == artifact.artifact_id
    assert restored_artifact.sha256 == artifact.sha256
    assert restored_artifact.file_path == artifact.file_path
    assert restored_catalog.artifact_count == 1
    assert restored_catalog.artifacts[0].version_label == "v1.2.3"
    assert restored_catalog.artifacts[0].compatibility == ("eb1", "f3")
