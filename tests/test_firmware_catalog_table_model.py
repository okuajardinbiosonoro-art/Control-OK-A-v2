from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.models.firmware_catalog_table_model import (  # noqa: E402
    FirmwareCatalogTableModel,
)
from control_okua.app_qt.viewmodels.firmware_manager_vm import (  # noqa: E402
    build_firmware_catalog_rows,
)
from control_okua.core.firmware import FirmwareArtifact  # noqa: E402


def _ensure_qapp() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


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
        "created_at_utc": "2026-03-28T18:00:00Z",
        "imported_at_utc": "2026-03-28T18:10:00Z",
        "source_kind": "manual_import",
        "source_notes": "",
        "changelog": "",
        "notes": "",
        "compatibility": ["eb1"],
        "tags": ["test"],
    }
    payload.update(overrides)
    return FirmwareArtifact(**payload)


def test_table_model_exposes_expected_columns_and_values(tmp_path: Path) -> None:
    _ensure_qapp()
    file_path, sha256, file_size = _write_firmware_file(
        tmp_path,
        "table.bin",
        b"table-model",
    )
    rows = build_firmware_catalog_rows(
        [_build_artifact(file_path, sha256, file_size, status="current")]
    )

    model = FirmwareCatalogTableModel()
    model.set_rows(rows)

    assert model.rowCount() == 1
    assert model.columnCount() == 10
    assert model.headerData(0, Qt.Horizontal, Qt.DisplayRole) == "Nombre"
    assert model.data(model.index(0, 0), Qt.DisplayRole) == "Firmware"
    assert model.data(model.index(0, 5), Qt.DisplayRole) == "current"
    assert model.data(model.index(0, 6), Qt.DisplayRole) == "Sí"
    assert model.data(model.index(0, 8), Qt.DisplayRole) == sha256[:12]


def test_table_model_sort_orders_rows_by_version_and_imported_at(tmp_path: Path) -> None:
    _ensure_qapp()
    file_a, sha_a, size_a = _write_firmware_file(tmp_path, "a.bin", b"a")
    file_b, sha_b, size_b = _write_firmware_file(tmp_path, "b.bin", b"b")
    file_c, sha_c, size_c = _write_firmware_file(tmp_path, "c.bin", b"c")
    rows = build_firmware_catalog_rows(
        [
            _build_artifact(file_a, sha_a, size_a, display_name="Gamma", version="1.2.0", imported_at_utc="2026-03-28T18:05:00Z"),
            _build_artifact(file_b, sha_b, size_b, display_name="Alpha", version="1.10.0", imported_at_utc="2026-03-28T18:15:00Z"),
            _build_artifact(file_c, sha_c, size_c, display_name="Beta", version="1.3.0", imported_at_utc="2026-03-28T18:10:00Z"),
        ]
    )

    model = FirmwareCatalogTableModel()
    model.set_rows(rows)

    model.sort(0, Qt.AscendingOrder)
    assert model.data(model.index(0, 0), Qt.DisplayRole) == "Alpha"

    model.sort(1, Qt.DescendingOrder)
    assert model.data(model.index(0, 1), Qt.DisplayRole) == "1.10.0"

    model.sort(9, Qt.DescendingOrder)
    assert model.data(model.index(0, 9), Qt.DisplayRole) == "2026-03-28T18:15:00.000Z"
