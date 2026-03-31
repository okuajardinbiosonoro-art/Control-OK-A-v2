from __future__ import annotations

from pathlib import Path
import sys

import pytest

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.firmware import (
    ArtifactAgentService,
    ArtifactAgentValidationError,
    ArtifactIntent,
    ArtifactPlanRequest,
    FirmwareCatalogStore,
    FirmwareIngestService,
    FirmwareStatus,
    FirmwareTargetKind,
    resolve_artifact_agent_output_root,
)


def test_audit_current_firmware_detects_node_specific_identity() -> None:
    service = ArtifactAgentService()

    audit = service.audit_current_firmware()

    assert audit.platformio_env == "okua_node_esp32dev"
    assert audit.default_version == "1.0.0-dev"
    assert audit.default_version_code == 10000
    assert audit.default_build_profile == "test"
    assert audit.default_target_kind is FirmwareTargetKind.PLANT
    assert audit.identity_scope == "per_node_variant"


def test_current_clone_plan_forces_situational_and_uses_baseline_defaults() -> None:
    service = ArtifactAgentService()

    plan = service.build_plan(
        ArtifactPlanRequest(
            intent=ArtifactIntent.CURRENT_CLONE,
            node_label="EB1",
            node_id=1,
        )
    )

    assert plan.status is FirmwareStatus.SITUATIONAL
    assert plan.version == "1.0.0-dev"
    assert plan.version_code == 10000
    assert plan.target_kind is FirmwareTargetKind.PLANT
    assert plan.target_variant == "eb1"
    assert "planta prueba actual" in plan.display_name.lower()


def test_comparative_plan_defaults_to_fruit_and_warns_about_current_plant_baseline() -> None:
    service = ArtifactAgentService()

    plan = service.build_plan(
        ArtifactPlanRequest(
            intent=ArtifactIntent.COMPARATIVE,
            node_label="ED1",
            node_id=3,
        )
    )

    assert plan.status is FirmwareStatus.SITUATIONAL
    assert plan.version == "1.0.1-dev"
    assert plan.version_code == 10001
    assert plan.target_kind is FirmwareTargetKind.FRUIT
    assert plan.target_variant == "ed1"
    assert any("no será ota-compatible" in item.lower() for item in plan.warnings)


def test_rejects_non_situational_status_for_test_artifact() -> None:
    service = ArtifactAgentService()

    with pytest.raises(ArtifactAgentValidationError):
        service.build_plan(
            ArtifactPlanRequest(
                intent="current_clone",
                node_label="EB1",
                node_id=1,
                status="beta",
            )
        )


def test_rejects_invalid_semver_version() -> None:
    service = ArtifactAgentService()

    with pytest.raises(ArtifactAgentValidationError):
        service.build_plan(
            ArtifactPlanRequest(
                intent="comparative",
                node_label="ED1",
                node_id=3,
                version="fruit-test",
            )
        )


def test_build_default_situational_plans_returns_three_plant_and_one_fruit() -> None:
    service = ArtifactAgentService()

    plans = service.build_default_situational_plans()

    assert len(plans) == 4
    assert [plan.target_variant for plan in plans[:3]] == ["eb1", "ec1", "ed1"]
    assert all(plan.target_kind is FirmwareTargetKind.PLANT for plan in plans[:3])
    assert plans[3].target_kind is FirmwareTargetKind.FRUIT
    assert plans[3].target_variant == "ed1"


def test_generated_plan_can_be_turned_into_import_request() -> None:
    service = ArtifactAgentService()
    plan = service.build_plan(
        ArtifactPlanRequest(
            intent="current_clone",
            node_label="EC1",
            node_id=2,
        )
    )
    result = plan
    dummy = Path("C:/temp/example.bin")

    from control_okua.core.firmware.artifact_agent_service import ArtifactBuildResult

    build_result = ArtifactBuildResult(
        plan=result,
        output_dir=str(dummy.parent),
        binary_path=str(dummy),
        override_header_path=str(dummy.parent / "artifact_build_overrides.h"),
        metadata_path=str(dummy.parent / "artifact_plan.json"),
        sha256="a" * 64,
        file_size=123,
        artifact_id=f"sha256:{'a' * 64}",
    )

    request = build_result.to_import_request()

    assert request.status is FirmwareStatus.SITUATIONAL
    assert request.target_kind is FirmwareTargetKind.PLANT
    assert request.target_variant == "ec1"
    assert request.display_name == plan.display_name


def test_import_artifact_is_compatible_with_catalog_and_ingest(tmp_path: Path) -> None:
    service = ArtifactAgentService()
    plan = service.build_plan(
        ArtifactPlanRequest(
            intent="comparative",
            node_label="ED1",
            node_id=3,
        )
    )
    binary_path = tmp_path / "artifact.bin"
    binary_path.write_bytes(b"OTA-A-test-payload")

    from control_okua.core.firmware.artifact_agent_service import ArtifactBuildResult

    build_result = ArtifactBuildResult(
        plan=plan,
        output_dir=str(tmp_path),
        binary_path=str(binary_path),
        override_header_path=str(tmp_path / "artifact_build_overrides.h"),
        metadata_path=str(tmp_path / "artifact_plan.json"),
        sha256="b" * 64,
        file_size=binary_path.stat().st_size,
        artifact_id=f"sha256:{'b' * 64}",
    )
    catalog_store = FirmwareCatalogStore(tmp_path / "firmware_catalog.json")
    ingest = FirmwareIngestService(catalog_store, managed_store_dir=tmp_path / "firmware_store")

    import_result = service.import_artifact(
        build_result,
        catalog_store=catalog_store,
        ingest_service=ingest,
    )

    assert import_result.success is True
    assert import_result.was_duplicate is False
    assert import_result.imported_artifact is not None
    assert import_result.imported_artifact.target_kind is FirmwareTargetKind.FRUIT
    assert import_result.imported_artifact.status is FirmwareStatus.SITUATIONAL


def test_resolve_artifact_agent_output_root_points_to_artifacts_directory() -> None:
    root = resolve_artifact_agent_output_root()

    assert root.name == "ota_artifact_agent"
    assert root.parent.name == "artifacts"
