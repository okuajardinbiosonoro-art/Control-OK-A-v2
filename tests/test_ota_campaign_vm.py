from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.viewmodels.ota_campaign_vm import (  # noqa: E402
    build_ota_campaign_continue_hint,
    build_ota_campaign_node_rows,
    build_ota_campaign_result_details,
    build_ota_campaign_result_summary,
    build_ota_campaign_wave_preview,
    format_ota_campaign_health_gate,
    format_ota_campaign_node_outcome,
    format_ota_campaign_status,
)
from control_okua.core.firmware import (  # noqa: E402
    OtaCampaignHealthGate,
    OtaCampaignNodeOutcome,
    OtaCampaignNodeStatus,
    OtaCampaignResult,
    OtaCampaignStatus,
    OtaCampaignWave,
    OtaCampaignWaveResult,
    OtaNodeDeployPhase,
)


def _campaign_result() -> OtaCampaignResult:
    node_statuses = (
        OtaCampaignNodeStatus(
            node_id=1,
            node_label="EB1",
            wave_index=0,
            wave_label="canary",
            is_canary=True,
            phase=OtaNodeDeployPhase.CONFIRMED,
            outcome=OtaCampaignNodeOutcome.CONFIRMED,
            ack_received=True,
            runtime_status="online",
            ota_state_key="boot_confirmed",
            ota_error_key="none",
            rollout_token="20260328",
            artifact_id="sha256:artifact",
            last_message="OTA observable: boot_confirmed",
        ),
        OtaCampaignNodeStatus(
            node_id=2,
            node_label="EC1",
            wave_index=1,
            wave_label="wave_1",
            is_canary=False,
            phase=OtaNodeDeployPhase.PENDING,
            outcome=OtaCampaignNodeOutcome.PENDING,
            ack_received=False,
            runtime_status="",
            ota_state_key="idle",
            ota_error_key="none",
            rollout_token="20260328",
            artifact_id="sha256:artifact",
            last_message="Pendiente de ola manual.",
        ),
    )
    wave_results = (
        OtaCampaignWaveResult(
            wave=OtaCampaignWave(wave_index=0, label="canary", node_ids=[1], is_canary=True),
            health_gate=OtaCampaignHealthGate.PASSED,
            started_at_utc="2026-03-28T12:00:00.000Z",
            finished_at_utc="2026-03-28T12:01:00.000Z",
        ),
        OtaCampaignWaveResult(
            wave=OtaCampaignWave(wave_index=1, label="wave_1", node_ids=[2]),
        ),
    )
    return OtaCampaignResult(
        success=True,
        campaign_id="campaign-20260328120000",
        artifact_id="sha256:artifact",
        rollout_token="20260328",
        rollout_id="plant-eb1-20260328",
        rollout_channel="stable",
        node_ids=(1, 2),
        canary_nodes=(1,),
        waves=(OtaCampaignWave(wave_index=1, label="wave_1", node_ids=[2]),),
        wave_results=wave_results,
        node_statuses=node_statuses,
        current_phase="awaiting_wave_1",
        campaign_status=OtaCampaignStatus.PAUSED,
        health_gate=OtaCampaignHealthGate.PASSED,
        continue_allowed=True,
        advertise_host="192.168.88.254",
        bind_host="0.0.0.0",
        port=8080,
        ack_timeout_ms=600,
        max_retries=0,
        published_dir="C:/tmp/ota/rollouts/20260328",
        manifest_url="http://192.168.88.254:8080/ota/rollouts/20260328/manifest.json",
        download_url="http://192.168.88.254:8080/ota/rollouts/20260328/firmware.bin",
        audit_path="C:/tmp/ota/rollouts/20260328/campaigns/campaign-20260328120000.json",
        message="Health gate aprobado para canary.",
    )


def test_wave_preview_and_formatters_are_clear() -> None:
    preview = build_ota_campaign_wave_preview(
        node_ids=[1, 2, 3],
        canary_nodes=[1],
        wave_size=1,
    )

    assert "Canary: EB1" in preview
    assert "wave_1: EC1" in preview
    assert format_ota_campaign_status(OtaCampaignStatus.CANARY_RUNNING) == "Canary en curso"
    assert format_ota_campaign_health_gate(OtaCampaignHealthGate.INCONCLUSIVE) == "Inconcluso"
    assert format_ota_campaign_node_outcome(OtaCampaignNodeOutcome.TIMEOUT) == "Timeout"


def test_campaign_result_rows_summary_and_details_are_useful() -> None:
    result = _campaign_result()

    rows = build_ota_campaign_node_rows(result.node_statuses)
    summary = build_ota_campaign_result_summary(result)
    details = build_ota_campaign_result_details(result)
    continue_hint = build_ota_campaign_continue_hint(result)

    assert rows[0].wave_label == "Canary"
    assert rows[0].outcome_label == "Confirmado"
    assert "gate=Aprobado" in summary
    assert "Olas manuales:" in details
    assert "Canary: EB1" in details
    assert "continuar manualmente" in continue_hint.lower()
