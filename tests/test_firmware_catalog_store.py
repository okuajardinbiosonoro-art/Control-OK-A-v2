from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.firmware import (  # noqa: E402
    FirmwareArtifact,
    FirmwareCatalogStore,
    FirmwareStatus,
    artifact_to_dict,
)


def _write_firmware_file(tmp_path: Path, name: str, content: bytes) -> tuple[Path, str, int]:
    file_path = tmp_path / name
    file_path.write_bytes(content)
    sha256 = hashlib.sha256(content).hexdigest()
    return file_path, sha256, len(content)


def _build_artifact(
    file_path: Path,
    sha256: str,
    file_size: int,
    **overrides,
) -> FirmwareArtifact:
    payload = {
        "artifact_id": "ignored",
        "display_name": "Firmware",
        "version": "1.0.0",
        "version_label": "v1.0.0",
        "target_kind": "plant",
        "target_variant": "eb1",
        "status": "beta",
        "file_name": file_path.name,
        "file_path": str(file_path),
        "sha256": sha256,
        "file_size": file_size,
        "created_at_utc": "2026-03-28T15:00:00Z",
        "imported_at_utc": "2026-03-28T15:05:00Z",
        "source_kind": "local",
        "source_notes": "",
        "changelog": "",
        "notes": "",
        "compatibility": ["eb1"],
        "tags": ["test"],
    }
    payload.update(overrides)
    return FirmwareArtifact(**payload)


def _artifact_dict(artifact: FirmwareArtifact) -> dict[str, object]:
    return artifact_to_dict(artifact)


def test_load_missing_catalog_creates_empty_catalog(tmp_path: Path) -> None:
    catalog_path = tmp_path / "data" / "firmware_catalog.json"
    store = FirmwareCatalogStore(catalog_path)

    catalog = store.load()

    assert catalog.artifact_count == 0
    assert catalog_path.exists()
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert payload["artifacts"] == []


def test_save_and_reload_catalog_roundtrip(tmp_path: Path) -> None:
    catalog_path = tmp_path / "data" / "firmware_catalog.json"
    file_path, sha256, file_size = _write_firmware_file(
        tmp_path,
        "firmware_roundtrip.bin",
        b"firmware-roundtrip",
    )
    artifact = _build_artifact(file_path, sha256, file_size)

    store = FirmwareCatalogStore(catalog_path)
    store.load()
    store.add_artifact(artifact)
    current = store.set_current(artifact.artifact_id)
    store.save()

    reloaded_store = FirmwareCatalogStore(catalog_path)
    reloaded_catalog = reloaded_store.load()
    reloaded_current = reloaded_store.get_current_for_target("plant", "eb1")

    assert reloaded_catalog.artifact_count == 1
    assert reloaded_current is not None
    assert reloaded_current.artifact_id == current.artifact_id
    assert reloaded_current.status is FirmwareStatus.CURRENT


def test_add_artifact_deduplicates_by_sha256(tmp_path: Path) -> None:
    catalog_path = tmp_path / "firmware_catalog.json"
    file_path, sha256, file_size = _write_firmware_file(
        tmp_path,
        "firmware_dup.bin",
        b"same-binary",
    )
    artifact_a = _build_artifact(file_path, sha256, file_size, display_name="Firmware A")
    artifact_b = _build_artifact(file_path, sha256, file_size, display_name="Firmware B")

    store = FirmwareCatalogStore(catalog_path)
    store.load()
    inserted = store.add_artifact(artifact_a)
    duplicate = store.add_artifact(artifact_b)

    assert inserted.artifact_id == duplicate.artifact_id
    assert len(store.list_all()) == 1
    assert store.find_by_sha256(sha256) is not None


def test_set_current_disables_previous_current_for_same_target(tmp_path: Path) -> None:
    catalog_path = tmp_path / "firmware_catalog.json"
    file_a, sha_a, size_a = _write_firmware_file(tmp_path, "firmware_a.bin", b"aaa")
    file_b, sha_b, size_b = _write_firmware_file(tmp_path, "firmware_b.bin", b"bbb")
    artifact_a = _build_artifact(
        file_a,
        sha_a,
        size_a,
        version="1.0.0",
        version_label="v1.0.0",
        status="current",
    )
    artifact_b = _build_artifact(
        file_b,
        sha_b,
        size_b,
        version="1.1.0",
        version_label="v1.1.0",
        status="beta",
        imported_at_utc="2026-03-28T15:10:00Z",
    )

    store = FirmwareCatalogStore(catalog_path)
    store.load()
    store.add_artifact(artifact_a)
    store.add_artifact(artifact_b)
    promoted = store.set_current(artifact_b.artifact_id)

    previous = store.get_by_id(artifact_a.artifact_id)
    assert promoted.status is FirmwareStatus.CURRENT
    assert previous is not None
    assert previous.status is FirmwareStatus.OBSOLETE
    assert promoted.supersedes_artifact_id == artifact_a.artifact_id
    assert store.get_current_for_target("plant", "eb1") == promoted


def test_filter_by_target_and_status(tmp_path: Path) -> None:
    catalog_path = tmp_path / "firmware_catalog.json"
    file_a, sha_a, size_a = _write_firmware_file(tmp_path, "plant_eb1.bin", b"plant-eb1")
    file_b, sha_b, size_b = _write_firmware_file(tmp_path, "plant_ec1.bin", b"plant-ec1")
    file_c, sha_c, size_c = _write_firmware_file(tmp_path, "fruit.bin", b"fruit-generic")

    store = FirmwareCatalogStore(catalog_path)
    store.load()
    store.add_artifact(_build_artifact(file_a, sha_a, size_a, target_variant="eb1", status="beta"))
    store.add_artifact(_build_artifact(file_b, sha_b, size_b, target_variant="ec1", status="obsolete"))
    store.add_artifact(
        _build_artifact(
            file_c,
            sha_c,
            size_c,
            target_kind="fruit",
            target_variant="generic",
            status="current",
        )
    )

    plant_artifacts = store.filter_by_target("plant")
    plant_ec1 = store.filter_by_target("plant", "ec1")
    obsolete = store.filter_by_status("obsolete")

    assert len(plant_artifacts) == 2
    assert len(plant_ec1) == 1
    assert plant_ec1[0].target_variant == "ec1"
    assert len(obsolete) == 1
    assert obsolete[0].status is FirmwareStatus.OBSOLETE


def test_load_recovers_from_corrupt_json(tmp_path: Path) -> None:
    catalog_path = tmp_path / "data" / "firmware_catalog.json"
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text("{ invalid json", encoding="utf-8")

    store = FirmwareCatalogStore(catalog_path)
    catalog = store.load()

    assert catalog.artifact_count == 0
    backups = list(catalog_path.parent.glob("firmware_catalog.corrupt.*.json"))
    assert backups
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert payload["artifacts"] == []


def test_load_normalizes_multiple_current_artifacts_for_same_target(tmp_path: Path) -> None:
    catalog_path = tmp_path / "data" / "firmware_catalog.json"
    catalog_path.parent.mkdir(parents=True, exist_ok=True)

    file_a, sha_a, size_a = _write_firmware_file(tmp_path, "plant_old.bin", b"old")
    file_b, sha_b, size_b = _write_firmware_file(tmp_path, "plant_new.bin", b"new")
    artifact_a = _build_artifact(
        file_a,
        sha_a,
        size_a,
        status="current",
        imported_at_utc="2026-03-28T15:00:00Z",
    )
    artifact_b = _build_artifact(
        file_b,
        sha_b,
        size_b,
        status="current",
        version="1.1.0",
        version_label="v1.1.0",
        imported_at_utc="2026-03-28T15:30:00Z",
    )
    payload = {
        "schema_version": 1,
        "created_at_utc": "2026-03-28T15:00:00Z",
        "updated_at_utc": "2026-03-28T15:30:00Z",
        "artifacts": [
            _artifact_dict(artifact_a),
            _artifact_dict(artifact_b),
        ],
    }
    catalog_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    store = FirmwareCatalogStore(catalog_path)
    catalog = store.load()
    current = store.get_current_for_target("plant", "eb1")
    obsolete = store.filter_by_status("obsolete")

    assert catalog.artifact_count == 2
    assert current is not None
    assert current.sha256 == sha_b
    assert len(obsolete) == 1
    assert obsolete[0].sha256 == sha_a
