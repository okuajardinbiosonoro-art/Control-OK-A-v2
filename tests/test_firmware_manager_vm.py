from __future__ import annotations

import hashlib
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.viewmodels.firmware_manager_vm import (  # noqa: E402
    ALL_FIRMWARE_FILTER,
    build_current_summary,
    build_display_name_suggestion,
    build_empty_catalog_state,
    build_firmware_catalog_row,
    build_firmware_catalog_rows,
    build_firmware_detail,
    build_import_feedback,
    build_mark_current_confirmation_text,
    filter_firmware_catalog_rows,
)
from control_okua.core.firmware import (  # noqa: E402
    FirmwareArtifact,
    FirmwareImportResult,
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
        "display_name": "Firmware base",
        "version": "1.0.0",
        "version_label": "v1.0.0",
        "target_kind": "plant",
        "target_variant": "eb1",
        "status": "beta",
        "file_name": file_path.name,
        "file_path": str(file_path),
        "sha256": sha256,
        "file_size": file_size,
        "created_at_utc": "2026-03-28T18:00:00Z",
        "imported_at_utc": "2026-03-28T18:10:00Z",
        "source_kind": "manual_import",
        "source_notes": "importado por técnico",
        "changelog": "- nota de cambio",
        "notes": "uso interno",
        "compatibility": ["eb1", "f3"],
        "tags": ["beta", "plant"],
    }
    payload.update(overrides)
    return FirmwareArtifact(**payload)


def test_build_catalog_row_formats_status_current_and_sha(tmp_path: Path) -> None:
    file_path, sha256, file_size = _write_firmware_file(
        tmp_path,
        "plant_release.bin",
        b"plant-release",
    )
    artifact = _build_artifact(
        file_path,
        sha256,
        file_size,
        status="current",
        display_name="Firmware planta final",
    )

    row = build_firmware_catalog_row(artifact)

    assert row.display_name == "Firmware planta final"
    assert row.target_kind == "plant"
    assert row.status == "current"
    assert row.current_label == "Sí"
    assert row.sha256_short == sha256[:12]
    assert "firmware planta final" in row.search_text


def test_filter_rows_by_search_target_status_and_current(tmp_path: Path) -> None:
    file_a, sha_a, size_a = _write_firmware_file(tmp_path, "plant_eb1.bin", b"plant-eb1")
    file_b, sha_b, size_b = _write_firmware_file(tmp_path, "fruit_generic.bin", b"fruit-generic")
    file_c, sha_c, size_c = _write_firmware_file(tmp_path, "plant_ec1.bin", b"plant-ec1")

    rows = build_firmware_catalog_rows(
        [
            _build_artifact(file_a, sha_a, size_a, status="current", target_variant="eb1"),
            _build_artifact(file_b, sha_b, size_b, target_kind="fruit", target_variant="generic"),
            _build_artifact(file_c, sha_c, size_c, target_variant="ec1", status="obsolete"),
        ]
    )

    filtered = filter_firmware_catalog_rows(
        rows,
        search_text="fruit",
        target_filter="fruit",
        status_filter=ALL_FIRMWARE_FILTER,
        current_only=False,
    )
    current_only = filter_firmware_catalog_rows(
        rows,
        current_only=True,
        search_text=sha_a[:10],
        target_filter="plant",
        status_filter="current",
    )

    assert len(filtered) == 1
    assert filtered[0].artifact.target_kind.value == "fruit"
    assert len(current_only) == 1
    assert current_only[0].artifact.sha256 == sha_a


def test_build_detail_and_current_summary_render_expected_fields(tmp_path: Path) -> None:
    file_path, sha256, file_size = _write_firmware_file(
        tmp_path,
        "detail.bin",
        b"detail-firmware",
    )
    artifact = _build_artifact(file_path, sha256, file_size, status="current")

    detail = build_firmware_detail(artifact)
    summary = build_current_summary(artifact)
    confirmation = build_mark_current_confirmation_text(artifact)

    scalar = dict(detail.scalar_fields)
    assert scalar["SHA-256"] == sha256
    assert scalar["Current"] == "Sí"
    assert scalar["Compatibilidad"] == "eb1, f3"
    assert "Current activo" in summary
    assert "plant/eb1" in confirmation


def test_build_import_feedback_surfaces_duplicate_warnings() -> None:
    result = FirmwareImportResult(
        success=True,
        artifact_id="sha256:abc",
        sha256="abc",
        was_duplicate=True,
        stored_file_path="C:/tmp/abc.bin",
        catalog_updated=False,
        current_changed=False,
        imported_artifact=None,
        message="ok",
        warnings=(
            "El artefacto duplicado ya existe con una versión distinta; se conserva la metadata original.",
        ),
    )

    feedback = build_import_feedback(result)

    assert feedback.title == "Firmware duplicado"
    assert "duplicado detectado" in feedback.summary.lower()
    assert "versión distinta" in feedback.details.lower()
    assert feedback.severity == "warning"


def test_empty_state_and_display_name_suggestion_are_clear() -> None:
    empty_title, empty_hint = build_empty_catalog_state(total_artifacts=0, filtered_artifacts=0)
    filtered_title, filtered_hint = build_empty_catalog_state(total_artifacts=3, filtered_artifacts=0)
    suggestion = build_display_name_suggestion(Path("fw_plant-beta_v2.bin"))

    assert "aún no hay artefactos" in empty_title.lower()
    assert "agregar el primero" in empty_hint.lower()
    assert "no hay artefactos" in filtered_title.lower()
    assert "ajusta texto" in filtered_hint.lower()
    assert suggestion == "fw plant beta v2"
