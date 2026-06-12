from __future__ import annotations

from dataclasses import dataclass

from control_okua.app_qt.viewmodels.ota_deploy_vm import (
    OtaDeployArtifactOption,
    OtaDeployNodeOption,
    build_ota_ack_label,
    build_ota_artifact_options,
    build_ota_node_options,
    build_ota_runtime_label,
    format_ota_deploy_phase,
)
from control_okua.core.firmware import (
    FirmwareArtifact,
    OtaCampaignHealthGate,
    OtaCampaignNodeOutcome,
    OtaCampaignNodeStatus,
    OtaCampaignPlan,
    OtaCampaignResult,
    OtaCampaignStatus,
    build_campaign_waves,
)
from control_okua.core.node_identity_policy import resolve_node_identity


@dataclass(frozen=True)
class OtaCampaignNodeRow:
    node_id: int
    node_label: str
    wave_label: str
    phase_label: str
    outcome_label: str
    ack_label: str
    runtime_label: str
    message: str
    observed_at_utc: str


def build_ota_campaign_artifact_options(
    artifacts: list[FirmwareArtifact] | tuple[FirmwareArtifact, ...],
) -> list[OtaDeployArtifactOption]:
    return build_ota_artifact_options(artifacts)


def build_ota_campaign_node_options(
    snapshots: list[object] | tuple[object, ...],
) -> list[OtaDeployNodeOption]:
    return build_ota_node_options(snapshots)


def build_ota_campaign_wave_preview(
    *,
    node_ids: tuple[int, ...] | list[int],
    canary_nodes: tuple[int, ...] | list[int],
    wave_size: int,
) -> str:
    preview_lines: list[str] = []
    if canary_nodes:
        canary_labels = ", ".join(
            resolve_node_identity(node_id).node_label for node_id in canary_nodes
        )
        preview_lines.append(f"Canary: {canary_labels}")
    waves = build_campaign_waves(
        node_ids,
        canary_nodes=canary_nodes,
        wave_size=wave_size,
    )
    if not waves:
        if preview_lines:
            preview_lines.append("Sin olas manuales restantes.")
        else:
            return "Sin canary ni olas definidas todavía."
    for wave in waves:
        labels = ", ".join(
            resolve_node_identity(node_id).node_label for node_id in wave.node_ids
        )
        preview_lines.append(f"{wave.label}: {labels}")
    return "\n".join(preview_lines)


def build_ota_campaign_node_rows(
    node_statuses: tuple[OtaCampaignNodeStatus, ...] | list[OtaCampaignNodeStatus],
) -> list[OtaCampaignNodeRow]:
    return [
        OtaCampaignNodeRow(
            node_id=status.node_id,
            node_label=status.node_label,
            wave_label="Canary" if status.is_canary else status.wave_label,
            phase_label=format_ota_deploy_phase(status.phase),
            outcome_label=format_ota_campaign_node_outcome(status.outcome),
            ack_label=build_ota_ack_label(status),
            runtime_label=build_ota_runtime_label(status),
            message=status.last_message or "—",
            observed_at_utc=status.observed_at_utc,
        )
        for status in node_statuses
    ]


def format_ota_campaign_status(value: OtaCampaignStatus | str) -> str:
    raw = value.value if isinstance(value, OtaCampaignStatus) else str(value).strip().lower()
    mapping = {
        "planned": "Planificada",
        "canary_running": "Canary en curso",
        "wave_running": "Ola en curso",
        "paused": "Pausada",
        "failed": "Bloqueada",
        "completed": "Completada",
        "aborted": "Abortada",
    }
    return mapping.get(raw, raw or "—")


def format_ota_campaign_health_gate(value: OtaCampaignHealthGate | str) -> str:
    raw = value.value if isinstance(value, OtaCampaignHealthGate) else str(value).strip().lower()
    mapping = {
        "not_evaluated": "No evaluado",
        "pending": "Pendiente",
        "passed": "Aprobado",
        "failed": "Falló",
        "inconclusive": "Inconcluso",
    }
    return mapping.get(raw, raw or "—")


def format_ota_campaign_node_outcome(value: OtaCampaignNodeOutcome | str) -> str:
    raw = value.value if isinstance(value, OtaCampaignNodeOutcome) else str(value).strip().lower()
    mapping = {
        "pending": "Pendiente",
        "in_progress": "En progreso",
        "confirmed": "Confirmado",
        "failed": "Falló",
        "timeout": "Timeout",
        "aborted": "Abortado",
    }
    return mapping.get(raw, raw or "—")


def build_ota_campaign_result_summary(result: OtaCampaignResult | None) -> str:
    if result is None:
        return "Aún no hay campaña OTA en curso."

    confirmed = sum(
        1 for status in result.node_statuses if status.outcome is OtaCampaignNodeOutcome.CONFIRMED
    )
    failed = sum(
        1
        for status in result.node_statuses
        if status.outcome
        in {
            OtaCampaignNodeOutcome.FAILED,
            OtaCampaignNodeOutcome.TIMEOUT,
            OtaCampaignNodeOutcome.ABORTED,
        }
    )
    executed_waves = sum(1 for item in result.wave_results if item.is_executed)
    return (
        f"Campaña={result.campaign_id} | estado={format_ota_campaign_status(result.campaign_status)} | "
        f"gate={format_ota_campaign_health_gate(result.health_gate)} | "
        f"olas ejecutadas={executed_waves} | confirmados={confirmed} | fallidos/abortados={failed}"
    )


def build_ota_campaign_result_details(result: OtaCampaignResult | None) -> str:
    if result is None:
        return "Sin campaña OTA todavía."

    lines = [
        result.message or "Sin mensaje general.",
        f"Artifact: {result.artifact_id}",
        f"Rollout: {result.rollout_token}",
        f"Manifest URL: {result.manifest_url or '—'}",
        f"Download URL: {result.download_url or '—'}",
        f"Directorio publicado: {result.published_dir or '—'}",
    ]
    if result.audit_path:
        lines.append(f"Audit campaña: {result.audit_path}")
    if result.canary_nodes:
        canary_labels = ", ".join(
            resolve_node_identity(node_id).node_label for node_id in result.canary_nodes
        )
        lines.append(f"Canary: {canary_labels}")
    if result.waves:
        lines.append("Olas manuales:")
        for wave in result.waves:
            labels = ", ".join(
                resolve_node_identity(node_id).node_label for node_id in wave.node_ids
            )
            lines.append(f"- {wave.label}: {labels}")
    if result.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {item}" for item in result.warnings)
    if result.errors:
        lines.append("Errors:")
        lines.extend(f"- {item}" for item in result.errors)
    return "\n".join(lines)


def build_ota_campaign_continue_hint(result: OtaCampaignResult | None) -> str:
    if result is None:
        return "Configura una campaña OTA para iniciar el canary."
    if result.continue_allowed:
        return "El health gate está aprobado. Puedes continuar manualmente a la siguiente ola."
    if result.campaign_status is OtaCampaignStatus.FAILED:
        return "La campaña quedó bloqueada. Revisa el canary y aborta si corresponde."
    if result.campaign_status is OtaCampaignStatus.ABORTED:
        return "La campaña fue abortada y ya no admite nuevas olas."
    return "La siguiente ola aún no está habilitada."
