from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QDialog


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt import firmware_manager_dialog as fm_module  # noqa: E402
from control_okua.app_qt.firmware_manager_dialog import FirmwareManagerDialog  # noqa: E402
from control_okua.app_qt.main_window import MainWindow  # noqa: E402
from control_okua.core.firmware import (  # noqa: E402
    FirmwareArtifact,
    FirmwareCatalog,
    FirmwareCatalogStore,
    FirmwareStatus,
    FirmwareTargetKind,
)


def _ensure_qapp() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _build_cfg() -> dict[str, object]:
    return {
        "version": 2,
        "mode": "udp",
        "profile": {"active": "udp_jardin"},
    }


class _SessionControllerStub:
    def __init__(self, snapshots: list[object] | None = None) -> None:
        self._snapshots = snapshots or []

    def get_node_snapshots(self, now=None):  # pragma: no cover - Qt callback signature
        return self._snapshots


class _RecordingDeployDialog:
    instances: list["_RecordingDeployDialog"] = []

    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs
        self.exec_calls = 0
        type(self).instances.append(self)

    def exec(self) -> int:
        self.exec_calls += 1
        return QDialog.DialogCode.Accepted

    @classmethod
    def reset(cls) -> None:
        cls.instances = []


class _RecordingCampaignDialog:
    instances: list["_RecordingCampaignDialog"] = []

    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs
        self.exec_calls = 0
        type(self).instances.append(self)

    def exec(self) -> int:
        self.exec_calls += 1
        return QDialog.DialogCode.Accepted

    @classmethod
    def reset(cls) -> None:
        cls.instances = []


class _FirmwareManagerStub:
    instances: list["_FirmwareManagerStub"] = []

    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs
        self.modal_values: list[bool] = []
        self.refresh_calls = 0
        self.show_calls = 0
        self.raise_calls = 0
        self.activate_calls = 0
        type(self).instances.append(self)

    def setModal(self, value: bool) -> None:
        self.modal_values.append(bool(value))

    def refresh_catalog(self) -> None:
        self.refresh_calls += 1

    def show(self) -> None:
        self.show_calls += 1

    def raise_(self) -> None:
        self.raise_calls += 1

    def activateWindow(self) -> None:
        self.activate_calls += 1

    @classmethod
    def reset(cls) -> None:
        cls.instances = []


def _build_current_artifact(tmp_path: Path) -> tuple[FirmwareCatalogStore, FirmwareArtifact]:
    payload = b"firmware-manager-ui"
    source_path = tmp_path / "firmware.bin"
    source_path.write_bytes(payload)
    sha256 = hashlib.sha256(payload).hexdigest()
    artifact = FirmwareArtifact(
        artifact_id="ignored",
        display_name="Firmware QA",
        version="1.2.3",
        version_label="v1.2.3",
        target_kind=FirmwareTargetKind.PLANT,
        target_variant="eb1",
        status=FirmwareStatus.CURRENT,
        file_name=source_path.name,
        file_path=str(source_path),
        sha256=sha256,
        file_size=len(payload),
        source_kind="manual_import",
        notes="QA UI Firmware Manager",
    )
    catalog_store = FirmwareCatalogStore(catalog_path=tmp_path / "firmware_catalog.json")
    catalog_store.save(FirmwareCatalog(artifacts=(artifact,)))
    return catalog_store, artifact


def test_firmware_manager_dialog_handles_empty_catalog_and_missing_session(tmp_path: Path) -> None:
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))

    notifications: list[dict[str, object]] = []
    dialog = FirmwareManagerDialog(
        catalog_store=FirmwareCatalogStore(catalog_path=tmp_path / "firmware_catalog.json"),
        on_notify=lambda **kwargs: notifications.append(kwargs),
    )
    try:
        dialog.show()
        app.processEvents()

        assert dialog.catalog_stack.currentIndex() == 0
        assert dialog.empty_title_label.text() == "Aún no hay artefactos firmware registrados"
        assert "agregar el primero" in dialog.empty_hint_label.text()
        assert dialog.summary_label.text() == "Artefactos totales: 0 | visibles: 0"
        assert dialog.mark_current_button.isEnabled() is False
        assert dialog.delete_button.isEnabled() is False
        assert dialog.ota_deploy_button.isEnabled() is False
        assert dialog.ota_campaign_button.isEnabled() is False

        dialog._on_ota_deploy_clicked()
        dialog._on_ota_campaign_clicked()

        assert [item["title"] for item in notifications] == [
            "OTA Deploy no disponible",
            "OTA Campaign no disponible",
        ]
        assert all(item["level"] == "warning" for item in notifications)
    finally:
        dialog.close()


def test_firmware_manager_dialog_handoffs_selected_artifact_to_ota_flows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _ensure_qapp()
    app.setStyleSheet((ROOT_DIR / "assets" / "theme.qss").read_text(encoding="utf-8"))

    catalog_store, artifact = _build_current_artifact(tmp_path)
    session_controller = _SessionControllerStub([SimpleNamespace(node_id=1)])
    dialog = FirmwareManagerDialog(
        catalog_store=catalog_store,
        session_controller=session_controller,
        on_notify=lambda **kwargs: None,
    )
    try:
        dialog.show()
        app.processEvents()

        assert dialog.catalog_stack.currentIndex() == 1
        assert dialog.catalog_table_model.rowCount() == 1
        assert dialog.current_summary_label.text() == "Current activo para plant/eb1."
        assert dialog.mark_current_button.isEnabled() is True
        assert dialog.delete_button.isEnabled() is True
        assert dialog.ota_deploy_button.isEnabled() is True
        assert dialog.ota_campaign_button.isEnabled() is True

        _RecordingDeployDialog.reset()
        _RecordingCampaignDialog.reset()
        monkeypatch.setattr(fm_module, "OtaDeployDialog", _RecordingDeployDialog)
        monkeypatch.setattr(fm_module, "OtaCampaignDialog", _RecordingCampaignDialog)

        open_urls: list[str] = []

        def _record_open(url) -> bool:
            open_urls.append(url.toString())
            return True

        monkeypatch.setattr(QDesktopServices, "openUrl", _record_open)

        dialog._on_ota_deploy_clicked()
        assert len(_RecordingDeployDialog.instances) == 1
        deploy_stub = _RecordingDeployDialog.instances[0]
        assert deploy_stub.kwargs["session_controller"] is session_controller
        assert deploy_stub.kwargs["catalog_store"] is catalog_store
        assert deploy_stub.kwargs["preselected_artifact_id"] == artifact.artifact_id
        assert deploy_stub.kwargs["parent"] is dialog
        assert deploy_stub.exec_calls == 1

        dialog._on_ota_campaign_clicked()
        assert len(_RecordingCampaignDialog.instances) == 1
        campaign_stub = _RecordingCampaignDialog.instances[0]
        assert campaign_stub.kwargs["session_controller"] is session_controller
        assert campaign_stub.kwargs["catalog_store"] is catalog_store
        assert campaign_stub.kwargs["preselected_artifact_id"] == artifact.artifact_id
        assert campaign_stub.kwargs["parent"] is dialog
        assert campaign_stub.exec_calls == 1

        dialog._open_managed_store_folder()
        assert catalog_store.load().artifact_count == 1
        assert dialog._ingest_service.managed_store_dir.exists() is True
        assert open_urls
        assert open_urls[-1].startswith("file:///")
    finally:
        dialog.close()


def test_main_window_opens_firmware_manager_modeless_and_refreshes_catalog(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _ensure_qapp()
    monkeypatch.setattr(
        "control_okua.app_qt.main_window.FirmwareManagerDialog",
        _FirmwareManagerStub,
    )
    _FirmwareManagerStub.reset()

    window = MainWindow(
        cfg=_build_cfg(),
        config_path=tmp_path / "config.json",
        warnings=[],
    )
    try:
        window.open_firmware_manager()

        assert len(_FirmwareManagerStub.instances) == 1
        stub = _FirmwareManagerStub.instances[0]
        assert stub.kwargs["session_controller"] is window.session_controller
        assert stub.kwargs["parent"] is window
        assert stub.modal_values == [False]
        assert stub.refresh_calls == 1
        assert stub.show_calls == 1
        assert stub.raise_calls == 1
        assert stub.activate_calls == 1
        assert window._firmware_manager_dialog is stub

        window.open_firmware_manager()
        assert len(_FirmwareManagerStub.instances) == 1
        assert stub.refresh_calls == 2
        assert stub.show_calls == 2
        assert stub.raise_calls == 2
        assert stub.activate_calls == 2
    finally:
        window.close()
