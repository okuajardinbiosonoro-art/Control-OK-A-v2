from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.viewmodels.ota_deploy_vm import (  # noqa: E402
    build_ota_ack_label,
    build_ota_artifact_options,
    build_ota_deploy_result_details,
    build_ota_deploy_result_summary,
    build_ota_node_options,
    build_ota_node_result_rows,
    build_recommended_rollout_channel,
    evaluate_ota_artifact_eligibility,
    format_ota_deploy_phase,
    infer_artifact_pc_ip,
)
from control_okua.core.firmware import (  # noqa: E402
    FirmwareArtifact,
    OtaDeployResult,
    OtaNodeDeployPhase,
    OtaNodeDeployStatus,
)


def _artifact(
    tmp_path: Path,
    *,
    version: str = "1.2.3",
    target_kind: str = "plant",
    status: str = "beta",
    notes: str = "",
    source_notes: str = "",
) -> FirmwareArtifact:
    payload = f"ota-deploy-vm:{target_kind}:{version}:{status}".encode("utf-8")
    file_path = tmp_path / f"{target_kind}_{version}.bin"
    file_path.write_bytes(payload)
    sha256 = hashlib.sha256(payload).hexdigest()
    return FirmwareArtifact(
        artifact_id="ignored",
        display_name="OTA VM Artifact",
        version=version,
        version_label=version,
        target_kind=target_kind,
        target_variant="eb1",
        status=status,
        file_name=file_path.name,
        file_path=str(file_path),
        sha256=sha256,
        file_size=len(payload),
        source_kind="manual_import",
        notes=notes,
        source_notes=source_notes,
    )


def test_artifact_options_mark_eligibility_and_recommended_channel(tmp_path: Path) -> None:
    valid = _artifact(
        tmp_path,
        version="2.3.4",
        status="current",
        notes="Red embebida: MARIANA (SSID, canal 13, PC_IP=192.168.80.14).",
    )
    unknown = _artifact(tmp_path, version="2.3.4", target_kind="unknown")
    invalid_version = _artifact(tmp_path, version="release-candidate")

    options = build_ota_artifact_options([unknown, invalid_version, valid])

    assert options[0].artifact_id == valid.artifact_id
    assert options[0].is_eligible is True
    assert options[0].recommended_host == "192.168.80.14"
    assert "Host sugerido=192.168.80.14" in options[0].summary
    assert build_recommended_rollout_channel(valid) == "stable"

    eligibility_unknown = evaluate_ota_artifact_eligibility(unknown)
    eligibility_invalid_version = evaluate_ota_artifact_eligibility(invalid_version)
    assert eligibility_unknown == (False, "target_kind unknown")
    assert "version_code" in eligibility_invalid_version[1]


def test_infer_artifact_pc_ip_accepts_notes_or_source_notes(tmp_path: Path) -> None:
    from_notes = _artifact(
        tmp_path,
        notes="Red embebida: KITTY (Kitty_2.4, canal 13, PC_IP=192.168.1.70).",
    )
    from_source_notes = _artifact(
        tmp_path,
        version="1.2.4",
        source_notes="Perfil de red: MIKROTIK. PC_IP=192.168.88.254.",
    )
    without_ip = _artifact(tmp_path, version="1.2.5", notes="Sin PC_IP usable.")

    assert infer_artifact_pc_ip(from_notes) == "192.168.1.70"
    assert infer_artifact_pc_ip(from_source_notes) == "192.168.88.254"
    assert infer_artifact_pc_ip(without_ip) == ""


def test_node_options_surface_runtime_summary_and_sorting() -> None:
    snapshots = [
        SimpleNamespace(
            node_id=2,
            status="degraded",
            status_reason="recovering",
            health_summary="recovering",
            ota_state_key="downloading",
            ota_error_key="none",
            resolved_ip="192.168.88.202",
        ),
        SimpleNamespace(
            node_id=1,
            status="online",
            status_reason="healthy traffic",
            health_summary="healthy traffic",
            ota_state_key="idle",
            ota_error_key="none",
            resolved_ip="192.168.88.201",
        ),
    ]

    options = build_ota_node_options(snapshots)

    assert [item.node_id for item in options] == [1, 2]
    assert "En línea" in options[0].summary
    assert "OTA descargando firmware" in options[1].summary
    assert options[1].node_ip == "192.168.88.202"


def test_result_rows_and_summary_are_clear() -> None:
    statuses = (
        OtaNodeDeployStatus(
            node_id=1,
            node_label="EB1",
            phase=OtaNodeDeployPhase.ACKNOWLEDGED,
            ack_received=True,
            rollout_token="20260328",
            artifact_id="sha256:aaa",
            last_message="trigger OTA reconocido por el nodo",
        ),
        OtaNodeDeployStatus(
            node_id=2,
            node_label="EC1",
            phase=OtaNodeDeployPhase.FAILED,
            ack_received=False,
            ota_state_key="error",
            ota_error_key="download_http",
            rollout_token="20260328",
            artifact_id="sha256:aaa",
            last_message="OTA error: download_http",
        ),
    )
    result = OtaDeployResult(
        success=True,
        artifact_id="sha256:aaa",
        rollout_token="20260328",
        rollout_id="plant-eb1-20260328",
        rollout_channel="stable",
        node_statuses=statuses,
        manifest_url="http://192.168.88.254:8080/ota/rollouts/20260328/manifest.json",
        download_url="http://192.168.88.254:8080/ota/rollouts/20260328/firmware.bin",
        published_dir="C:/tmp/ota/rollouts/20260328",
        warnings=("Advertencia de prueba",),
        errors=("Nodo EC1 sin progreso OTA",),
        message="Nodos: 2 | confirmados: 0 | en progreso: 1 | fallidos/timeout: 1",
    )

    rows = build_ota_node_result_rows(result.node_statuses)
    summary = build_ota_deploy_result_summary(result)
    details = build_ota_deploy_result_details(result)

    assert rows[0].phase_label == "ACK recibido"
    assert build_ota_ack_label(statuses[1]) == "No"
    assert format_ota_deploy_phase(OtaNodeDeployPhase.BOOT_VALIDATING) == "Validando boot"
    assert "rollout=20260328" in summary
    assert "Warnings:" in details
    assert "Errors:" in details
