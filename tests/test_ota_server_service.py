from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.request import urlopen


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.firmware import (  # noqa: E402
    FirmwareCatalogStore,
    FirmwareImportRequest,
    FirmwareIngestService,
    OtaManifestService,
    OtaRolloutPublishRequest,
)
from control_okua.services.ota_server_service import OtaServerService  # noqa: E402


def test_ota_server_serves_manifest_and_bin_for_published_rollout(tmp_path: Path) -> None:
    catalog_path = tmp_path / "artifacts" / "firmware_catalog.json"
    publish_root = tmp_path / "ota_http_root"
    store = FirmwareCatalogStore(catalog_path)
    ingest_service = FirmwareIngestService(store)
    manifest_service = OtaManifestService(store, publish_root_dir=publish_root)

    source_path = tmp_path / "ota_publish.bin"
    source_bytes = b"ota-http-payload"
    source_path.write_bytes(source_bytes)
    import_result = ingest_service.import_artifact(
        FirmwareImportRequest(
            source_file_path=source_path,
            target_kind="plant",
            target_variant="eb1",
            version="3.4.5",
            status="current",
            display_name="ota-http",
            source_kind="manual_import",
        )
    )
    assert import_result.success is True
    artifact = import_result.imported_artifact
    assert artifact is not None

    server = OtaServerService(root_dir=publish_root, bind_host="127.0.0.1", port=0)
    server.start()
    try:
        publish_result = manifest_service.publish_rollout(
            OtaRolloutPublishRequest(
                rollout_token="20260402",
                artifact_id=artifact.artifact_id,
                rollout_id="plant-eb1-2026-04-02-r1",
                host="127.0.0.1",
                port=server.port,
            )
        )

        with urlopen(publish_result.manifest_url, timeout=5) as response:
            manifest_payload = json.loads(response.read().decode("utf-8"))
            manifest_content_type = response.headers.get_content_type()
        with urlopen(publish_result.download_url, timeout=5) as response:
            firmware_payload = response.read()
            firmware_content_type = response.headers.get_content_type()

        assert manifest_content_type == "application/json"
        assert firmware_content_type == "application/octet-stream"
        assert manifest_payload["rollout_id"] == "plant-eb1-2026-04-02-r1"
        assert manifest_payload["version_code"] == 30405
        assert manifest_payload["artifact_id"] == artifact.artifact_id
        assert firmware_payload == source_bytes
    finally:
        server.stop()
