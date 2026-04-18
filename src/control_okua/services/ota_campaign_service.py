from __future__ import annotations

import json
import logging
from pathlib import Path
import tempfile
from typing import Protocol

from control_okua.core.firmware import OtaDeployRequest
from control_okua.core.firmware.catalog_models import normalize_text, utc_now_iso
from control_okua.core.firmware.ota_campaign_models import (
    OtaCampaignHealthGate,
    OtaCampaignNodeOutcome,
    OtaCampaignNodeStatus,
    OtaCampaignPlan,
    OtaCampaignResult,
    OtaCampaignStatus,
    OtaCampaignValidationError,
    OtaCampaignWave,
    OtaCampaignWaveResult,
)
from control_okua.core.firmware.ota_manifest_models import DEFAULT_OTA_HTTP_PORT
from control_okua.core.firmware.ota_deploy_models import (
    OtaDeployResult,
    OtaNodeDeployPhase,
    OtaNodeDeployStatus,
)
from control_okua.core.node_identity_policy import resolve_node_identity


class OtaCampaignServiceError(RuntimeError):
    """Base error for controlled OTA campaign orchestration."""


class OtaCampaignOrchestrator(Protocol):
    def deploy(self, request: OtaDeployRequest) -> OtaDeployResult:
        ...

    def refresh_deploy_statuses(self, result: OtaDeployResult) -> OtaDeployResult:
        ...


class OtaCampaignService:
    def __init__(
        self,
        *,
        orchestrator_service: OtaCampaignOrchestrator,
        logger: logging.Logger | None = None,
    ) -> None:
        self._orchestrator = orchestrator_service
        self._logger = logger or logging.getLogger(__name__)

    def start_campaign(self, plan: OtaCampaignPlan) -> OtaCampaignResult:
        resolved_plan = self._coerce_plan(plan)
        waves = self._all_waves(resolved_plan)
        if not waves:
            raise OtaCampaignValidationError(
                "La campaña OTA no tiene canary ni olas manuales para ejecutar."
            )

        first_wave = waves[0]
        deploy_result = self._orchestrator.deploy(
            self._build_wave_request(resolved_plan, first_wave)
        )
        initial_wave_results = self._build_initial_wave_results(
            plan=resolved_plan,
            first_wave=first_wave,
            deploy_result=deploy_result,
        )
        return self._rebuild_campaign_result(
            plan=resolved_plan,
            wave_results=initial_wave_results,
            started_at_utc=utc_now_iso(),
            paused_by_operator=False,
        )

    def refresh_campaign(self, result: OtaCampaignResult) -> OtaCampaignResult:
        resolved_result = self._coerce_result(result)
        refreshed_wave_results: list[OtaCampaignWaveResult] = []
        for wave_result in resolved_result.wave_results:
            deploy_result = wave_result.deploy_result
            if deploy_result is None:
                refreshed_wave_results.append(wave_result)
                continue

            refreshed_deploy = self._orchestrator.refresh_deploy_statuses(deploy_result)
            refreshed_gate = self._evaluate_wave_gate(refreshed_deploy.node_statuses)
            refreshed_wave_results.append(
                OtaCampaignWaveResult(
                    wave=wave_result.wave,
                    deploy_result=refreshed_deploy,
                    health_gate=refreshed_gate,
                    started_at_utc=wave_result.started_at_utc or refreshed_deploy.created_at_utc,
                    finished_at_utc=self._resolve_wave_finished_at(
                        health_gate=refreshed_gate,
                        fallback=wave_result.finished_at_utc,
                    ),
                )
            )

        return self._rebuild_campaign_result(
            plan=self._plan_from_result(resolved_result),
            wave_results=tuple(refreshed_wave_results),
            started_at_utc=resolved_result.started_at_utc,
            paused_by_operator=resolved_result.paused_by_operator,
            abort_reason=resolved_result.abort_reason,
        )

    def continue_campaign(self, result: OtaCampaignResult) -> OtaCampaignResult:
        resolved_result = self._coerce_result(result)
        if resolved_result.campaign_status is OtaCampaignStatus.ABORTED:
            raise OtaCampaignServiceError(
                "La campaña OTA está abortada y no puede continuar."
            )
        if resolved_result.campaign_status is OtaCampaignStatus.COMPLETED:
            raise OtaCampaignServiceError("La campaña OTA ya fue completada.")
        if resolved_result.campaign_status is OtaCampaignStatus.FAILED:
            raise OtaCampaignServiceError(
                "La campaña OTA quedó bloqueada por health gate fallido o inconcluso."
            )
        if not resolved_result.continue_allowed:
            raise OtaCampaignServiceError(
                "La campaña OTA todavía no está habilitada para continuar a la siguiente ola."
            )

        next_wave = self._next_pending_wave(resolved_result.wave_results)
        if next_wave is None:
            raise OtaCampaignServiceError(
                "No quedan olas pendientes en esta campaña OTA."
            )

        plan = self._plan_from_result(resolved_result)
        deploy_result = self._orchestrator.deploy(
            self._build_wave_request(plan, next_wave.wave)
        )
        updated_wave_results = self._replace_wave_result(
            resolved_result.wave_results,
            OtaCampaignWaveResult(
                wave=next_wave.wave,
                deploy_result=deploy_result,
                health_gate=self._evaluate_wave_gate(deploy_result.node_statuses),
                started_at_utc=deploy_result.created_at_utc,
                finished_at_utc=self._resolve_wave_finished_at(
                    health_gate=self._evaluate_wave_gate(deploy_result.node_statuses)
                ),
            ),
        )
        return self._rebuild_campaign_result(
            plan=plan,
            wave_results=updated_wave_results,
            started_at_utc=resolved_result.started_at_utc,
            paused_by_operator=False,
        )

    def pause_campaign(
        self,
        result: OtaCampaignResult,
        *,
        reason: str = "Campaña pausada por operador técnico.",
    ) -> OtaCampaignResult:
        resolved_result = self._coerce_result(result)
        if resolved_result.campaign_status in {
            OtaCampaignStatus.ABORTED,
            OtaCampaignStatus.COMPLETED,
        }:
            return resolved_result

        paused = self._rebuild_campaign_result(
            plan=self._plan_from_result(resolved_result),
            wave_results=resolved_result.wave_results,
            started_at_utc=resolved_result.started_at_utc,
            paused_by_operator=True,
            abort_reason=resolved_result.abort_reason,
        )
        warning_text = normalize_text(reason)
        if not warning_text:
            return paused

        enriched = OtaCampaignResult(
            success=paused.success,
            campaign_id=paused.campaign_id,
            artifact_id=paused.artifact_id,
            rollout_token=paused.rollout_token,
            rollout_id=paused.rollout_id,
            rollout_channel=paused.rollout_channel,
            node_ids=paused.node_ids,
            canary_nodes=paused.canary_nodes,
            waves=paused.waves,
            wave_results=paused.wave_results,
            node_statuses=paused.node_statuses,
            current_phase=paused.current_phase,
            campaign_status=paused.campaign_status,
            health_gate=paused.health_gate,
            continue_allowed=paused.continue_allowed,
            paused_by_operator=True,
            abort_reason=paused.abort_reason,
            advertise_host=paused.advertise_host,
            bind_host=paused.bind_host,
            port=paused.port,
            ack_timeout_ms=paused.ack_timeout_ms,
            max_retries=paused.max_retries,
            published_dir=paused.published_dir,
            manifest_path=paused.manifest_path,
            firmware_path=paused.firmware_path,
            manifest_url=paused.manifest_url,
            download_url=paused.download_url,
            audit_path=paused.audit_path,
            started_at_utc=paused.started_at_utc,
            finished_at_utc=paused.finished_at_utc,
            warnings=tuple(list(paused.warnings) + [warning_text]),
            errors=paused.errors,
            message="Campaña OTA pausada manualmente.",
        )
        return self._write_campaign_audit(enriched)

    def abort_campaign(
        self,
        result: OtaCampaignResult,
        *,
        reason: str = "Campaña abortada por operador técnico.",
    ) -> OtaCampaignResult:
        resolved_result = self._coerce_result(result)
        return self._rebuild_campaign_result(
            plan=self._plan_from_result(resolved_result),
            wave_results=resolved_result.wave_results,
            started_at_utc=resolved_result.started_at_utc,
            paused_by_operator=False,
            abort_reason=normalize_text(reason, fallback="Campaña abortada."),
        )

    def _coerce_plan(self, plan: OtaCampaignPlan) -> OtaCampaignPlan:
        if not isinstance(plan, OtaCampaignPlan):
            raise OtaCampaignValidationError(
                "plan inválido: se esperaba OtaCampaignPlan"
            )
        return plan

    def _coerce_result(self, result: OtaCampaignResult) -> OtaCampaignResult:
        if not isinstance(result, OtaCampaignResult):
            raise OtaCampaignValidationError(
                "result inválido: se esperaba OtaCampaignResult"
            )
        return result

    def _all_waves(self, plan: OtaCampaignPlan) -> tuple[OtaCampaignWave, ...]:
        waves: list[OtaCampaignWave] = []
        if plan.canary_nodes:
            waves.append(
                OtaCampaignWave(
                    wave_index=0,
                    label="canary",
                    node_ids=plan.canary_nodes,
                    is_canary=True,
                )
            )
        waves.extend(plan.waves)
        return tuple(waves)

    def _build_wave_request(
        self,
        plan: OtaCampaignPlan,
        wave: OtaCampaignWave,
    ) -> OtaDeployRequest:
        return OtaDeployRequest(
            artifact_id=plan.artifact_id,
            node_ids=wave.node_ids,
            advertise_host=plan.advertise_host,
            bind_host=plan.bind_host,
            port=plan.port,
            rollout_token=plan.rollout_token,
            rollout_id=plan.rollout_id,
            rollout_channel=plan.rollout_channel,
            ack_timeout_ms=plan.ack_timeout_ms,
            max_retries=plan.max_retries,
        )

    def _build_initial_wave_results(
        self,
        *,
        plan: OtaCampaignPlan,
        first_wave: OtaCampaignWave,
        deploy_result: OtaDeployResult,
    ) -> tuple[OtaCampaignWaveResult, ...]:
        wave_results: list[OtaCampaignWaveResult] = []
        started_at_utc = deploy_result.created_at_utc
        health_gate = self._evaluate_wave_gate(deploy_result.node_statuses)
        finished_at_utc = self._resolve_wave_finished_at(health_gate=health_gate)
        for wave in self._all_waves(plan):
            if wave.wave_index == first_wave.wave_index:
                wave_results.append(
                    OtaCampaignWaveResult(
                        wave=wave,
                        deploy_result=deploy_result,
                        health_gate=health_gate,
                        started_at_utc=started_at_utc,
                        finished_at_utc=finished_at_utc,
                    )
                )
            else:
                wave_results.append(OtaCampaignWaveResult(wave=wave))
        return tuple(wave_results)

    def _plan_from_result(self, result: OtaCampaignResult) -> OtaCampaignPlan:
        return OtaCampaignPlan(
            artifact_id=result.artifact_id,
            node_ids=result.node_ids,
            canary_nodes=result.canary_nodes,
            waves=result.waves,
            advertise_host=result.advertise_host or self._host_from_url(result.manifest_url),
            bind_host=result.bind_host or "0.0.0.0",
            port=result.port or self._port_from_url(result.manifest_url),
            rollout_token=result.rollout_token,
            rollout_id=result.rollout_id,
            rollout_channel=result.rollout_channel,
            ack_timeout_ms=result.ack_timeout_ms,
            max_retries=result.max_retries,
            campaign_id=result.campaign_id,
            require_canary=bool(result.canary_nodes),
        )

    def _rebuild_campaign_result(
        self,
        *,
        plan: OtaCampaignPlan,
        wave_results: tuple[OtaCampaignWaveResult, ...],
        started_at_utc: str,
        paused_by_operator: bool,
        abort_reason: str = "",
    ) -> OtaCampaignResult:
        aggregate = self._collect_campaign_details(
            plan=plan,
            wave_results=wave_results,
            abort_reason=abort_reason,
            paused_by_operator=paused_by_operator,
        )
        result = OtaCampaignResult(
            success=aggregate["success"],
            campaign_id=plan.campaign_id,
            artifact_id=plan.artifact_id,
            rollout_token=plan.rollout_token,
            rollout_id=aggregate["rollout_id"],
            rollout_channel=aggregate["rollout_channel"],
            node_ids=plan.node_ids,
            canary_nodes=plan.canary_nodes,
            waves=plan.waves,
            wave_results=wave_results,
            node_statuses=aggregate["node_statuses"],
            current_phase=aggregate["current_phase"],
            campaign_status=aggregate["campaign_status"],
            health_gate=aggregate["health_gate"],
            continue_allowed=aggregate["continue_allowed"],
            paused_by_operator=paused_by_operator,
            abort_reason=abort_reason,
            advertise_host=plan.advertise_host,
            bind_host=plan.bind_host,
            port=plan.port,
            ack_timeout_ms=plan.ack_timeout_ms,
            max_retries=plan.max_retries,
            published_dir=aggregate["published_dir"],
            manifest_path=aggregate["manifest_path"],
            firmware_path=aggregate["firmware_path"],
            manifest_url=aggregate["manifest_url"],
            download_url=aggregate["download_url"],
            started_at_utc=started_at_utc,
            finished_at_utc=aggregate["finished_at_utc"],
            warnings=aggregate["warnings"],
            errors=aggregate["errors"],
            message=aggregate["message"],
        )
        return self._write_campaign_audit(result)

    def _collect_campaign_details(
        self,
        *,
        plan: OtaCampaignPlan,
        wave_results: tuple[OtaCampaignWaveResult, ...],
        abort_reason: str,
        paused_by_operator: bool,
    ) -> dict[str, object]:
        node_statuses = self._build_campaign_node_statuses(
            plan=plan,
            wave_results=wave_results,
            abort_reason=abort_reason,
        )
        last_executed = self._last_executed_wave(wave_results)
        next_pending = self._next_pending_wave(wave_results)
        health_gate = (
            OtaCampaignHealthGate.NOT_EVALUATED
            if last_executed is None
            else last_executed.health_gate
        )
        warnings: list[str] = []
        errors: list[str] = []
        published_dir = ""
        manifest_path = ""
        firmware_path = ""
        manifest_url = ""
        download_url = ""
        rollout_id = plan.rollout_id
        rollout_channel = plan.rollout_channel
        if last_executed is not None and last_executed.deploy_result is not None:
            deploy_result = last_executed.deploy_result
            warnings.extend(deploy_result.warnings)
            errors.extend(deploy_result.errors)
            published_dir = deploy_result.published_dir
            manifest_path = deploy_result.manifest_path
            firmware_path = deploy_result.firmware_path
            manifest_url = deploy_result.manifest_url
            download_url = deploy_result.download_url
            rollout_id = deploy_result.rollout_id or plan.rollout_id
            rollout_channel = deploy_result.rollout_channel or plan.rollout_channel

        campaign_status = OtaCampaignStatus.PLANNED
        current_phase = "planned"
        continue_allowed = False
        finished_at_utc = ""
        success = True

        if abort_reason:
            campaign_status = OtaCampaignStatus.ABORTED
            current_phase = "aborted"
            finished_at_utc = utc_now_iso()
            success = False
            warnings.append(abort_reason)
        elif last_executed is None:
            campaign_status = OtaCampaignStatus.PLANNED
            current_phase = "planned"
        elif health_gate is OtaCampaignHealthGate.PENDING:
            current_phase = last_executed.wave.label
            if paused_by_operator:
                campaign_status = OtaCampaignStatus.PAUSED
                warnings.append(
                    "Campaña OTA pausada manualmente mientras la ola sigue observándose."
                )
            elif last_executed.wave.is_canary:
                campaign_status = OtaCampaignStatus.CANARY_RUNNING
            else:
                campaign_status = OtaCampaignStatus.WAVE_RUNNING
        elif next_pending is None:
            current_phase = "completed"
            finished_at_utc = utc_now_iso()
            if health_gate is OtaCampaignHealthGate.PASSED:
                campaign_status = OtaCampaignStatus.COMPLETED
            else:
                campaign_status = OtaCampaignStatus.FAILED
                success = False
        else:
            current_phase = f"awaiting_{next_pending.wave.label}"
            if health_gate is OtaCampaignHealthGate.PASSED:
                campaign_status = OtaCampaignStatus.PAUSED
                continue_allowed = True
            else:
                campaign_status = OtaCampaignStatus.FAILED
                success = False

        message = self._build_campaign_message(
            campaign_status=campaign_status,
            health_gate=health_gate,
            last_executed=last_executed,
            next_pending=next_pending,
            node_statuses=node_statuses,
            paused_by_operator=paused_by_operator,
            abort_reason=abort_reason,
        )
        return {
            "success": success,
            "node_statuses": node_statuses,
            "health_gate": health_gate,
            "campaign_status": campaign_status,
            "current_phase": current_phase,
            "continue_allowed": continue_allowed,
            "finished_at_utc": finished_at_utc,
            "warnings": tuple(warnings),
            "errors": tuple(errors),
            "published_dir": published_dir,
            "manifest_path": manifest_path,
            "firmware_path": firmware_path,
            "manifest_url": manifest_url,
            "download_url": download_url,
            "rollout_id": rollout_id,
            "rollout_channel": rollout_channel,
            "message": message,
        }

    def _build_campaign_node_statuses(
        self,
        *,
        plan: OtaCampaignPlan,
        wave_results: tuple[OtaCampaignWaveResult, ...],
        abort_reason: str,
    ) -> tuple[OtaCampaignNodeStatus, ...]:
        by_node_id: dict[int, OtaCampaignNodeStatus] = {}
        for wave_result in wave_results:
            if wave_result.deploy_result is None:
                for node_id in wave_result.wave.node_ids:
                    by_node_id[node_id] = self._pending_node_status(
                        wave=wave_result.wave,
                        node_id=node_id,
                        artifact_id=plan.artifact_id,
                        rollout_token=plan.rollout_token,
                        abort_reason=abort_reason,
                    )
                continue

            for deploy_status in wave_result.deploy_result.node_statuses:
                by_node_id[deploy_status.node_id] = self._campaign_node_status_from_deploy(
                    wave=wave_result.wave,
                    deploy_status=deploy_status,
                )

        ordered = sorted(by_node_id.values(), key=lambda item: (item.wave_index, item.node_id))
        return tuple(ordered)

    def _pending_node_status(
        self,
        *,
        wave: OtaCampaignWave,
        node_id: int,
        artifact_id: str,
        rollout_token: str,
        abort_reason: str,
    ) -> OtaCampaignNodeStatus:
        identity = resolve_node_identity(node_id)
        if abort_reason:
            message = normalize_text(
                abort_reason,
                fallback="Campaña abortada antes de ejecutar esta ola.",
            )
            outcome = OtaCampaignNodeOutcome.ABORTED
        else:
            message = "Pendiente de ola manual."
            outcome = OtaCampaignNodeOutcome.PENDING
        return OtaCampaignNodeStatus(
            node_id=node_id,
            node_label=identity.node_label,
            wave_index=wave.wave_index,
            wave_label=wave.label,
            is_canary=wave.is_canary,
            phase=OtaNodeDeployPhase.PENDING,
            outcome=outcome,
            rollout_token=rollout_token,
            artifact_id=artifact_id,
            last_message=message,
        )

    def _campaign_node_status_from_deploy(
        self,
        *,
        wave: OtaCampaignWave,
        deploy_status: OtaNodeDeployStatus,
    ) -> OtaCampaignNodeStatus:
        return OtaCampaignNodeStatus(
            node_id=deploy_status.node_id,
            node_label=deploy_status.node_label,
            wave_index=wave.wave_index,
            wave_label=wave.label,
            is_canary=wave.is_canary,
            phase=deploy_status.phase,
            outcome=self._outcome_from_phase(deploy_status.phase),
            ack_received=deploy_status.ack_received,
            control_final_status=deploy_status.control_final_status,
            runtime_status=deploy_status.runtime_status,
            ota_state_key=deploy_status.ota_state_key,
            ota_error_key=deploy_status.ota_error_key,
            rollout_token=deploy_status.rollout_token,
            artifact_id=deploy_status.artifact_id,
            last_message=deploy_status.last_message,
            observed_at_utc=deploy_status.observed_at_utc,
        )

    def _evaluate_wave_gate(
        self,
        node_statuses: tuple[OtaNodeDeployStatus, ...] | list[OtaNodeDeployStatus],
    ) -> OtaCampaignHealthGate:
        statuses = tuple(node_statuses)
        if not statuses:
            return OtaCampaignHealthGate.NOT_EVALUATED
        if any(
            status.phase in {OtaNodeDeployPhase.FAILED, OtaNodeDeployPhase.TIMEOUT}
            or status.ota_error_key != "none"
            for status in statuses
        ):
            return OtaCampaignHealthGate.FAILED
        if any(
            status.phase
            in {
                OtaNodeDeployPhase.PENDING,
                OtaNodeDeployPhase.TRIGGERED,
                OtaNodeDeployPhase.ACKNOWLEDGED,
                OtaNodeDeployPhase.CHECKING_MANIFEST,
                OtaNodeDeployPhase.DOWNLOADING,
                OtaNodeDeployPhase.INSTALLING,
                OtaNodeDeployPhase.BOOT_VALIDATING,
            }
            or normalize_text(status.runtime_status).lower() == "calibrating"
            for status in statuses
        ):
            return OtaCampaignHealthGate.PENDING

        runtime_statuses = {
            normalize_text(status.runtime_status).lower()
            for status in statuses
            if normalize_text(status.runtime_status)
        }
        if "offline" in runtime_statuses:
            return OtaCampaignHealthGate.FAILED
        if "degraded" in runtime_statuses:
            return OtaCampaignHealthGate.INCONCLUSIVE
        if all(status.phase is OtaNodeDeployPhase.CONFIRMED for status in statuses):
            return OtaCampaignHealthGate.PASSED
        return OtaCampaignHealthGate.INCONCLUSIVE

    def _outcome_from_phase(
        self,
        phase: OtaNodeDeployPhase,
    ) -> OtaCampaignNodeOutcome:
        if phase is OtaNodeDeployPhase.CONFIRMED:
            return OtaCampaignNodeOutcome.CONFIRMED
        if phase is OtaNodeDeployPhase.FAILED:
            return OtaCampaignNodeOutcome.FAILED
        if phase is OtaNodeDeployPhase.TIMEOUT:
            return OtaCampaignNodeOutcome.TIMEOUT
        if phase is OtaNodeDeployPhase.PENDING:
            return OtaCampaignNodeOutcome.PENDING
        return OtaCampaignNodeOutcome.IN_PROGRESS

    def _replace_wave_result(
        self,
        wave_results: tuple[OtaCampaignWaveResult, ...],
        replacement: OtaCampaignWaveResult,
    ) -> tuple[OtaCampaignWaveResult, ...]:
        updated: list[OtaCampaignWaveResult] = []
        for item in wave_results:
            if item.wave.wave_index == replacement.wave.wave_index:
                updated.append(replacement)
            else:
                updated.append(item)
        return tuple(updated)

    def _last_executed_wave(
        self,
        wave_results: tuple[OtaCampaignWaveResult, ...],
    ) -> OtaCampaignWaveResult | None:
        executed = [item for item in wave_results if item.deploy_result is not None]
        if not executed:
            return None
        return max(executed, key=lambda item: item.wave.wave_index)

    def _next_pending_wave(
        self,
        wave_results: tuple[OtaCampaignWaveResult, ...],
    ) -> OtaCampaignWaveResult | None:
        pending = [item for item in wave_results if item.deploy_result is None]
        if not pending:
            return None
        return min(pending, key=lambda item: item.wave.wave_index)

    def _resolve_wave_finished_at(
        self,
        *,
        health_gate: OtaCampaignHealthGate,
        fallback: str = "",
    ) -> str:
        if health_gate in {
            OtaCampaignHealthGate.PASSED,
            OtaCampaignHealthGate.FAILED,
            OtaCampaignHealthGate.INCONCLUSIVE,
        }:
            return utc_now_iso()
        return normalize_text(fallback)

    def _build_campaign_message(
        self,
        *,
        campaign_status: OtaCampaignStatus,
        health_gate: OtaCampaignHealthGate,
        last_executed: OtaCampaignWaveResult | None,
        next_pending: OtaCampaignWaveResult | None,
        node_statuses: tuple[OtaCampaignNodeStatus, ...],
        paused_by_operator: bool,
        abort_reason: str,
    ) -> str:
        confirmed = sum(
            1
            for status in node_statuses
            if status.outcome is OtaCampaignNodeOutcome.CONFIRMED
        )
        failed = sum(
            1
            for status in node_statuses
            if status.outcome
            in {
                OtaCampaignNodeOutcome.FAILED,
                OtaCampaignNodeOutcome.TIMEOUT,
                OtaCampaignNodeOutcome.ABORTED,
            }
        )
        if abort_reason:
            return f"Campaña abortada. Confirmados={confirmed} | fallidos/abortados={failed}"
        if last_executed is None:
            return "Campaña OTA planificada; aún no se ejecutó ninguna ola."

        base = (
            f"Última ola={last_executed.wave.label} | gate={health_gate.value} | "
            f"confirmados={confirmed} | fallidos/timeout={failed}"
        )
        if campaign_status is OtaCampaignStatus.COMPLETED:
            return f"Campaña OTA completada. {base}"
        if campaign_status is OtaCampaignStatus.FAILED:
            return f"Campaña OTA bloqueada. {base}"
        if campaign_status is OtaCampaignStatus.PAUSED and paused_by_operator:
            return f"Campaña OTA pausada manualmente. {base}"
        if next_pending is not None and health_gate is OtaCampaignHealthGate.PASSED:
            return (
                f"Health gate aprobado para {last_executed.wave.label}. "
                f"Lista para continuar con {next_pending.wave.label}. {base}"
            )
        return base

    def _write_campaign_audit(self, result: OtaCampaignResult) -> OtaCampaignResult:
        if not result.published_dir:
            return result

        audit_dir = Path(result.published_dir) / "campaigns"
        audit_path = audit_dir / f"{result.campaign_id}.json"
        payload = {
            "campaign_id": result.campaign_id,
            "artifact_id": result.artifact_id,
            "rollout_token": result.rollout_token,
            "rollout_id": result.rollout_id,
            "rollout_channel": result.rollout_channel,
            "node_ids": list(result.node_ids),
            "canary_nodes": list(result.canary_nodes),
            "current_phase": result.current_phase,
            "campaign_status": result.campaign_status.value,
            "health_gate": result.health_gate.value,
            "continue_allowed": bool(result.continue_allowed),
            "paused_by_operator": bool(result.paused_by_operator),
            "abort_reason": result.abort_reason,
            "advertise_host": result.advertise_host,
            "bind_host": result.bind_host,
            "port": result.port,
            "ack_timeout_ms": result.ack_timeout_ms,
            "max_retries": result.max_retries,
            "published_dir": result.published_dir,
            "manifest_path": result.manifest_path,
            "firmware_path": result.firmware_path,
            "manifest_url": result.manifest_url,
            "download_url": result.download_url,
            "started_at_utc": result.started_at_utc,
            "finished_at_utc": result.finished_at_utc,
            "warnings": list(result.warnings),
            "errors": list(result.errors),
            "message": result.message,
            "waves": [
                {
                    "wave_index": wave.wave_index,
                    "label": wave.label,
                    "node_ids": list(wave.node_ids),
                    "is_canary": wave.is_canary,
                }
                for wave in result.waves
            ],
            "wave_results": [
                {
                    "wave_index": wave_result.wave.wave_index,
                    "label": wave_result.wave.label,
                    "node_ids": list(wave_result.wave.node_ids),
                    "is_canary": wave_result.wave.is_canary,
                    "executed": wave_result.is_executed,
                    "health_gate": wave_result.health_gate.value,
                    "started_at_utc": wave_result.started_at_utc,
                    "finished_at_utc": wave_result.finished_at_utc,
                }
                for wave_result in result.wave_results
            ],
            "node_statuses": [
                {
                    "node_id": status.node_id,
                    "node_label": status.node_label,
                    "wave_index": status.wave_index,
                    "wave_label": status.wave_label,
                    "is_canary": status.is_canary,
                    "phase": status.phase.value,
                    "outcome": status.outcome.value,
                    "ack_received": status.ack_received,
                    "control_final_status": status.control_final_status,
                    "runtime_status": status.runtime_status,
                    "ota_state_key": status.ota_state_key,
                    "ota_error_key": status.ota_error_key,
                    "rollout_token": status.rollout_token,
                    "artifact_id": status.artifact_id,
                    "last_message": status.last_message,
                    "observed_at_utc": status.observed_at_utc,
                }
                for status in result.node_statuses
            ],
        }
        audit_dir.mkdir(parents=True, exist_ok=True)
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=audit_dir,
                prefix=f"{audit_path.stem}.",
                suffix=".tmp",
                delete=False,
            ) as tmp_file:
                json.dump(payload, tmp_file, ensure_ascii=False, indent=2)
                tmp_file.write("\n")
                tmp_path = Path(tmp_file.name)
            tmp_path.replace(audit_path)
        except OSError as exc:
            self._logger.warning(
                "No se pudo escribir audit de campaña OTA en '%s': %s",
                audit_path,
                exc,
            )
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            return result

        return OtaCampaignResult(
            success=result.success,
            campaign_id=result.campaign_id,
            artifact_id=result.artifact_id,
            rollout_token=result.rollout_token,
            rollout_id=result.rollout_id,
            rollout_channel=result.rollout_channel,
            node_ids=result.node_ids,
            canary_nodes=result.canary_nodes,
            waves=result.waves,
            wave_results=result.wave_results,
            node_statuses=result.node_statuses,
            current_phase=result.current_phase,
            campaign_status=result.campaign_status,
            health_gate=result.health_gate,
            continue_allowed=result.continue_allowed,
            paused_by_operator=result.paused_by_operator,
            abort_reason=result.abort_reason,
            advertise_host=result.advertise_host,
            bind_host=result.bind_host,
            port=result.port,
            ack_timeout_ms=result.ack_timeout_ms,
            max_retries=result.max_retries,
            published_dir=result.published_dir,
            manifest_path=result.manifest_path,
            firmware_path=result.firmware_path,
            manifest_url=result.manifest_url,
            download_url=result.download_url,
            audit_path=str(audit_path),
            started_at_utc=result.started_at_utc,
            finished_at_utc=result.finished_at_utc,
            warnings=result.warnings,
            errors=result.errors,
            message=result.message,
        )

    def _host_from_url(self, manifest_url: str) -> str:
        text = normalize_text(manifest_url)
        if "://" not in text:
            return "127.0.0.1"
        netloc = text.split("://", 1)[1].split("/", 1)[0]
        host = netloc.split(":", 1)[0].strip()
        return host or "127.0.0.1"

    def _port_from_url(self, manifest_url: str) -> int:
        text = normalize_text(manifest_url)
        if "://" not in text:
            return DEFAULT_OTA_HTTP_PORT
        netloc = text.split("://", 1)[1].split("/", 1)[0]
        if ":" not in netloc:
            return DEFAULT_OTA_HTTP_PORT
        raw_port = netloc.rsplit(":", 1)[1].strip()
        try:
            return int(raw_port)
        except (TypeError, ValueError):
            return DEFAULT_OTA_HTTP_PORT
