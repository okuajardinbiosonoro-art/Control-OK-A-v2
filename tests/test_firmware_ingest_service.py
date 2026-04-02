from __future__ import annotations

import hashlib
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.firmware import (  # noqa: E402
    DEFAULT_MANAGED_FIRMWARE_STORE_DIRNAME,
    FirmwareCatalogStore,
    FirmwareImportRequest,
    FirmwareIngestService,
    FirmwareStatus,
)


def _build_service(
    tmp_path: Path,
) -> tuple[FirmwareIngestService, FirmwareCatalogStore, Path, Path]:
    catalog_path = tmp_path / "data" / "firmware_catalog.json"
    store = FirmwareCatalogStore(catalog_path)
    service = FirmwareIngestService(store)
    managed_store_dir = catalog_path.parent / DEFAULT_MANAGED_FIRMWARE_STORE_DIRNAME
    return service, store, catalog_path, managed_store_dir


def _write_bin(tmp_path: Path, name: str, content: bytes) -> tuple[Path, str]:
    path = tmp_path / name
    path.write_bytes(content)
    return path, hashlib.sha256(content).hexdigest()


def test_import_new_bin_creates_artifact_and_managed_copy(tmp_path: Path) -> None:
    service, store, _catalog_path, managed_store_dir = _build_service(tmp_path)
    source_path, sha256 = _write_bin(tmp_path, "plant_v1.bin", b"plant-v1")

    result = service.import_artifact(
        FirmwareImportRequest(
            source_file_path=source_path,
            target_kind="plant",
            target_variant="eb1",
            version="1.0.0",
            version_label="v1.0.0",
            status="beta",
            display_name="Firmware planta",
            changelog="- import inicial",
            notes="ticket 20",
            source_kind="manual_import",
            source_notes="bin compilado en banco",
            tags=["beta", "plant"],
            compatibility=["eb1", "f3"],
        )
    )

    assert result.success is True
    assert result.was_duplicate is False
    assert result.catalog_updated is True
    assert result.current_changed is False
    assert result.artifact_id == f"sha256:{sha256}"
    assert result.imported_artifact is not None

    stored_path = Path(result.stored_file_path or "")
    assert stored_path.exists()
    assert stored_path.parent == managed_store_dir
    assert stored_path.name == f"{sha256}.bin"

    catalog = store.load()
    assert catalog.artifact_count == 1
    artifact = catalog.artifacts[0]
    assert artifact.file_path == str(stored_path)
    assert artifact.file_name == "plant_v1.bin"
    assert artifact.display_name == "Firmware planta"
    assert artifact.source_kind == "manual_import"
    assert artifact.compatibility == ("eb1", "f3")


def test_import_duplicate_by_hash_reuses_existing_artifact(tmp_path: Path) -> None:
    service, store, _catalog_path, managed_store_dir = _build_service(tmp_path)
    first_path, sha256 = _write_bin(tmp_path, "first.bin", b"same-content")
    second_path, _ = _write_bin(tmp_path, "second.bin", b"same-content")

    first_result = service.import_artifact(
        FirmwareImportRequest(
            source_file_path=first_path,
            target_kind="plant",
            target_variant="eb1",
            version="1.0.0",
        )
    )
    second_result = service.import_artifact(
        FirmwareImportRequest(
            source_file_path=second_path,
            target_kind="plant",
            target_variant="eb1",
            version="1.0.0",
        )
    )

    assert first_result.success is True
    assert second_result.success is True
    assert second_result.was_duplicate is True
    assert second_result.artifact_id == first_result.artifact_id
    assert second_result.catalog_updated is False
    assert store.load().artifact_count == 1
    assert len(list(managed_store_dir.glob("*.bin"))) == 1
    assert Path(second_result.stored_file_path or "").name == f"{sha256}.bin"


def test_import_with_mark_as_current_demotes_previous_current(tmp_path: Path) -> None:
    service, store, _catalog_path, _managed_store_dir = _build_service(tmp_path)
    old_path, _ = _write_bin(tmp_path, "old.bin", b"old-version")
    new_path, _ = _write_bin(tmp_path, "new.bin", b"new-version")

    first_result = service.import_artifact(
        FirmwareImportRequest(
            source_file_path=old_path,
            target_kind="plant",
            target_variant="eb1",
            version="1.0.0",
            mark_as_current=True,
        )
    )
    second_result = service.import_artifact(
        FirmwareImportRequest(
            source_file_path=new_path,
            target_kind="plant",
            target_variant="eb1",
            version="1.1.0",
            mark_as_current=True,
        )
    )

    assert first_result.success is True
    assert first_result.current_changed is True
    assert second_result.success is True
    assert second_result.current_changed is True

    catalog = store.load()
    current = store.get_current_for_target("plant", "eb1")
    obsolete = store.filter_by_status("obsolete")

    assert catalog.artifact_count == 2
    assert current is not None
    assert current.version == "1.1.0"
    assert len(obsolete) == 1
    assert obsolete[0].version == "1.0.0"


def test_import_nonexistent_file_fails_without_catalog_changes(tmp_path: Path) -> None:
    service, _store, catalog_path, managed_store_dir = _build_service(tmp_path)
    missing_path = tmp_path / "missing.bin"

    result = service.import_artifact(
        FirmwareImportRequest(
            source_file_path=missing_path,
            target_kind="plant",
            version="1.0.0",
        )
    )

    assert result.success is False
    assert "no existe" in result.message.lower()
    assert not catalog_path.exists()
    assert not managed_store_dir.exists()


def test_import_empty_file_fails_without_catalog_changes(tmp_path: Path) -> None:
    service, _store, catalog_path, managed_store_dir = _build_service(tmp_path)
    empty_path = tmp_path / "empty.bin"
    empty_path.write_bytes(b"")

    result = service.import_artifact(
        FirmwareImportRequest(
            source_file_path=empty_path,
            target_kind="plant",
            version="1.0.0",
        )
    )

    assert result.success is False
    assert "vacío" in result.message.lower() or "vacio" in result.message.lower()
    assert not catalog_path.exists()
    assert not managed_store_dir.exists()


def test_import_persists_catalog_after_reload(tmp_path: Path) -> None:
    service, _store, catalog_path, _managed_store_dir = _build_service(tmp_path)
    source_path, _ = _write_bin(tmp_path, "persisted.bin", b"persisted-firmware")

    result = service.import_artifact(
        FirmwareImportRequest(
            source_file_path=source_path,
            target_kind="fruit",
            target_variant="generic",
            version="2.0.0",
            version_label="v2.0.0",
        )
    )

    reloaded_store = FirmwareCatalogStore(catalog_path)
    catalog = reloaded_store.load()

    assert result.success is True
    assert catalog.artifact_count == 1
    assert catalog.artifacts[0].artifact_id == result.artifact_id
    assert catalog.artifacts[0].target_kind.value == "fruit"


def test_import_generates_display_name_when_missing(tmp_path: Path) -> None:
    service, _store, _catalog_path, _managed_store_dir = _build_service(tmp_path)
    source_path, _ = _write_bin(tmp_path, "fw_plant-beta_v2.bin", b"display-name")

    result = service.import_artifact(
        FirmwareImportRequest(
            source_file_path=source_path,
            target_kind="plant",
            target_variant="eb1",
            version="2.0.0",
        )
    )

    assert result.success is True
    assert result.imported_artifact is not None
    assert result.imported_artifact.display_name == "fw plant beta v2"


def test_import_reuses_managed_file_when_duplicate_is_already_copied(tmp_path: Path) -> None:
    service, _store, _catalog_path, managed_store_dir = _build_service(tmp_path)
    original_path, sha256 = _write_bin(tmp_path, "managed_first.bin", b"managed-content")
    duplicate_path, _ = _write_bin(tmp_path, "managed_second.bin", b"managed-content")

    first_result = service.import_artifact(
        FirmwareImportRequest(
            source_file_path=original_path,
            target_kind="plant",
            target_variant="ec1",
            version="3.0.0",
        )
    )
    managed_path = Path(first_result.stored_file_path or "")
    second_result = service.import_artifact(
        FirmwareImportRequest(
            source_file_path=duplicate_path,
            target_kind="plant",
            target_variant="ec1",
            version="3.0.0",
        )
    )

    assert first_result.success is True
    assert managed_path.exists()
    assert managed_path.name == f"{sha256}.bin"
    assert second_result.success is True
    assert second_result.was_duplicate is True
    assert Path(second_result.stored_file_path or "") == managed_path
    assert len(list(managed_store_dir.glob("*.bin"))) == 1


def test_import_requires_explicit_version(tmp_path: Path) -> None:
    service, _store, catalog_path, managed_store_dir = _build_service(tmp_path)
    source_path, _ = _write_bin(tmp_path, "version_required.bin", b"version-required")

    try:
        request = FirmwareImportRequest(
            source_file_path=source_path,
            target_kind="plant",
            version="   ",
        )
        assert False, f"FirmwareImportRequest debió fallar: {request}"
    except ValueError as exc:
        assert "version es obligatoria" in str(exc).lower()

    assert not catalog_path.exists()
    assert not managed_store_dir.exists()


def test_delete_artifact_removes_catalog_entry_and_managed_file(tmp_path: Path) -> None:
    service, store, _catalog_path, managed_store_dir = _build_service(tmp_path)
    source_path, sha256 = _write_bin(tmp_path, "delete_me.bin", b"delete-me")

    import_result = service.import_artifact(
        FirmwareImportRequest(
            source_file_path=source_path,
            target_kind="plant",
            target_variant="ed1",
            version="1.0.0",
        )
    )
    assert import_result.success is True
    managed_path = managed_store_dir / f"{sha256}.bin"
    assert managed_path.exists()

    delete_result = service.delete_artifact(import_result.artifact_id or "")

    assert delete_result.success is True
    assert delete_result.catalog_updated is True
    assert delete_result.managed_file_deleted is True
    assert not managed_path.exists()
    assert store.load().artifact_count == 0
