from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.firmware import (  # noqa: E402
    OtaCampaignHealthGate,
    OtaCampaignPlan,
    OtaCampaignStatus,
    OtaCampaignValidationError,
    OtaCampaignWave,
    OtaDeployResult,
    OtaNodeDeployPhase,
    OtaNodeDeployStatus,
)
from control_okua.services.ota_campaign_service import (  # noqa: E402
    OtaCampaignService,
    OtaCampaignServiceError,
)


class _FakeOrchestrator:
    def __init__(
        self,
        *,
        deploy_results: list[OtaDeployResult],
        refresh_results: list[OtaDeployResult] | None = None,
    ) -> None:
        self._deploy_results = list(deploy_results)
        self._refresh_results = list(refresh_results or [])
        self.deploy_requests = []
        self.refresh_calls = 0

    def deploy(self, request):
        self.deploy_requests.append(request)
        if not self._deploy_results:
            raise AssertionError("No deploy result prepared for fake orchestrator")
        return self._deploy_results.pop(0)

    def refresh_deploy_statuses(self, result):
        self.refresh_calls += 1
        if not self._refresh_results:
            return result
        return self._refresh_results.pop(0)


def _deploy_result(
    tmp_path: Path,
    *,
    node_statuses: tuple[OtaNodeDeployStatus, ...],
    rollout_token: str = "20260328",
    rollout_id: str = "plant-eb1-20260328",
    rollout_channel: str = "stable",
    artifact_id: str = "sha256:artifact",
) -> OtaDeployResult:
    published_dir = tmp_path / "ota" / "rollouts" / rollout_token
    published_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = published_dir / "manifest.json"
    firmware_path = published_dir / "firmware.bin"
    manifest_path.write_text("{}", encoding="utf-8")
    firmware_path.write_bytes(b"firmware")
    return OtaDeployResult(
        success=True,
        artifact_id=artifact_id,
        rollout_token=rollout_token,
        rollout_id=rollout_id,
        rollout_channel=rollout_channel,
        node_statuses=node_statuses,
        published_dir=str(published_dir),
        manifest_path=str(manifest_path),
        firmware_path=str(firmware_path),
        manifest_url=f"http://192.168.88.254:18080/ota/rollouts/{rollout_token}/manifest.json",
        download_url=f"http://192.168.88.254:18080/ota/rollouts/{rollout_token}/firmware.bin",
        message="deploy fake",
    )


def _status(
    node_id: int,
    *,
    phase: OtaNodeDeployPhase | str,
    runtime_status: str = "online",
    ota_state_key: str = "boot_confirmed",
    ota_error_key: str = "none",
    last_message: str = "ok",
) -> OtaNodeDeployStatus:
    return OtaNodeDeployStatus(
        node_id=node_id,
        node_label=f"N{node_id}",
        phase=phase,
        ack_received=phase is not OtaNodeDeployPhase.TIMEOUT,
        runtime_status=runtime_status,
        ota_state_key=ota_state_key,
        ota_error_key=ota_error_key,
        rollout_token="20260328",
        artifact_id="sha256:artifact",
        last_message=last_message,
    )


def _plan() -> OtaCampaignPlan:
    return OtaCampaignPlan(
        artifact_id="sha256:artifact",
        node_ids=[1, 2, 3],
        canary_nodes=[1],
        waves=(
            OtaCampaignWave(wave_index=1, label="wave_1", node_ids=[2]),
            OtaCampaignWave(wave_index=2, label="wave_2", node_ids=[3]),
        ),
        advertise_host="192.168.88.254",
        bind_host="0.0.0.0",
        port=18080,
        rollout_token="20260328",
        rollout_channel="stable",
    )


def test_campaign_plan_rejects_duplicates_and_missing_wave_coverage() -> None:
    with pytest.raises(OtaCampaignValidationError):
        OtaCampaignPlan(
            artifact_id="sha256:artifact",
            node_ids=[1, 2, 3],
            canary_nodes=[1, 4],
            waves=(OtaCampaignWave(wave_index=1, label="wave_1", node_ids=[2]),),
            advertise_host="192.168.88.254",
        )

    with pytest.raises(OtaCampaignValidationError):
        OtaCampaignPlan(
            artifact_id="sha256:artifact",
            node_ids=[1, 2, 3],
            canary_nodes=[1],
            waves=(OtaCampaignWave(wave_index=1, label="wave_1", node_ids=[2, 2]),),
            advertise_host="192.168.88.254",
        )

    with pytest.raises(OtaCampaignValidationError):
        OtaCampaignPlan(
            artifact_id="sha256:artifact",
            node_ids=[1, 2, 3],
            canary_nodes=[1],
            waves=(OtaCampaignWave(wave_index=1, label="wave_1", node_ids=[2]),),
            advertise_host="192.168.88.254",
        )


def test_campaign_service_starts_canary_and_writes_audit(tmp_path: Path) -> None:
    orchestrator = _FakeOrchestrator(
        deploy_results=[
            _deploy_result(
                tmp_path,
                node_statuses=(
                    _status(1, phase=OtaNodeDeployPhase.CONFIRMED),
                ),
            )
        ]
    )
    service = OtaCampaignService(orchestrator_service=orchestrator)

    result = service.start_campaign(_plan())

    assert result.campaign_status is OtaCampaignStatus.PAUSED
    assert result.health_gate is OtaCampaignHealthGate.PASSED
    assert result.continue_allowed is True
    assert result.current_phase == "awaiting_wave_1"
    assert Path(result.audit_path).exists()
    assert orchestrator.deploy_requests[0].node_ids == (1,)


def test_campaign_service_refreshes_pending_canary_until_gate_passes(tmp_path: Path) -> None:
    initial = _deploy_result(
        tmp_path,
        node_statuses=(
            _status(
                1,
                phase=OtaNodeDeployPhase.ACKNOWLEDGED,
                runtime_status="calibrating",
                ota_state_key="triggered",
                last_message="trigger enviado",
            ),
        ),
    )
    refreshed = _deploy_result(
        tmp_path,
        node_statuses=(
            _status(1, phase=OtaNodeDeployPhase.CONFIRMED),
        ),
    )
    orchestrator = _FakeOrchestrator(
        deploy_results=[initial],
        refresh_results=[refreshed],
    )
    service = OtaCampaignService(orchestrator_service=orchestrator)

    result = service.start_campaign(_plan())
    assert result.campaign_status is OtaCampaignStatus.CANARY_RUNNING
    assert result.health_gate is OtaCampaignHealthGate.PENDING

    refreshed_result = service.refresh_campaign(result)

    assert refreshed_result.campaign_status is OtaCampaignStatus.PAUSED
    assert refreshed_result.health_gate is OtaCampaignHealthGate.PASSED
    assert refreshed_result.continue_allowed is True
    assert orchestrator.refresh_calls == 1


def test_campaign_service_continues_manual_waves_and_abort_blocks_more_progress(tmp_path: Path) -> None:
    orchestrator = _FakeOrchestrator(
        deploy_results=[
            _deploy_result(
                tmp_path,
                node_statuses=(
                    _status(1, phase=OtaNodeDeployPhase.CONFIRMED),
                ),
            ),
            _deploy_result(
                tmp_path,
                node_statuses=(
                    _status(2, phase=OtaNodeDeployPhase.CONFIRMED),
                ),
            ),
        ]
    )
    service = OtaCampaignService(orchestrator_service=orchestrator)

    result = service.start_campaign(_plan())
    result = service.continue_campaign(result)

    assert result.campaign_status is OtaCampaignStatus.PAUSED
    assert result.continue_allowed is True
    assert result.current_phase == "awaiting_wave_2"
    assert orchestrator.deploy_requests[1].node_ids == (2,)

    aborted = service.abort_campaign(result, reason="Abortada tras ola 1.")

    assert aborted.campaign_status is OtaCampaignStatus.ABORTED
    assert aborted.abort_reason == "Abortada tras ola 1."
    with pytest.raises(OtaCampaignServiceError):
        service.continue_campaign(aborted)


def test_campaign_service_marks_failed_gate_for_timeout_canary(tmp_path: Path) -> None:
    orchestrator = _FakeOrchestrator(
        deploy_results=[
            _deploy_result(
                tmp_path,
                node_statuses=(
                    _status(
                        1,
                        phase=OtaNodeDeployPhase.TIMEOUT,
                        runtime_status="offline",
                        ota_state_key="idle",
                        last_message="timeout ACK",
                    ),
                ),
            )
        ]
    )
    service = OtaCampaignService(orchestrator_service=orchestrator)

    result = service.start_campaign(_plan())

    assert result.campaign_status is OtaCampaignStatus.FAILED
    assert result.health_gate is OtaCampaignHealthGate.FAILED
    assert result.continue_allowed is False
