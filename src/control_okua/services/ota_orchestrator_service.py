from __future__ import annotations

import json
import logging
from pathlib import Path
import tempfile
from typing import Protocol

from control_okua.core.node_identity_policy import resolve_node_identity
from control_okua.core.firmware import (
    OtaManifestService,
    OtaRolloutPublishRequest,
)
from control_okua.core.firmware.ota_deploy_models import (
    OtaDeployRequest,
    OtaDeployResult,
    OtaDeployValidationError,
    OtaNodeDeployPhase,
    OtaNodeDeployStatus,
)
from control_okua.services.control_transaction_service import (
    ControlTransactionFinalStatus,
    ControlTransactionResult,
)
from control_okua.services.ota_server_service import OtaServerService


class OtaOrchestratorServiceError(RuntimeError):
    """Base error for OTA deploy orchestration."""


class OtaDeployRuntimeClient(Protocol):
    def is_control_plane_available(self) -> bool:
        ...

    def get_node_snapshots(self, now: float | None = None) -> list[object]:
        ...

    def get_node_snapshot(self, node_id: int, now: float | None = None) -> object | None:
        ...

    def send_control_ota_check_now(
        self,
        *,
        node_id: int,
        rollout_token: int,
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
        source: str = "ota_manual_ui",
    ) -> ControlTransactionResult:
        ...


class OtaOrchestratorService:
    def __init__(
        self,
        *,
        runtime_client: OtaDeployRuntimeClient,
        manifest_service: OtaManifestService | None = None,
        ota_server_service: OtaServerService | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._runtime_client = runtime_client
        self._manifest_service = manifest_service or OtaManifestService()
        self._ota_server_service = ota_server_service
        self._logger = logger or logging.getLogger(__name__)

    @property
    def manifest_service(self) -> OtaManifestService:
        return self._manifest_service

    @property
    def ota_server_service(self) -> OtaServerService | None:
        return self._ota_server_service

    def deploy(self, request: OtaDeployRequest) -> OtaDeployResult:
        resolved_request = self._coerce_request(request)
        runtime_error = self._validate_request_against_runtime(resolved_request)
        if runtime_error is not None:
            return self._build_failure_result(
                resolved_request,
                errors=(runtime_error,),
                message=runtime_error,
            )

        if not self._runtime_client.is_control_plane_available():
            return self._build_failure_result(
                resolved_request,
                errors=("El control-plane F3 no está disponible para este deploy OTA.",),
                message=(
                    "No se pudo iniciar el deploy OTA porque la sesión/control-plane "
                    "no están disponibles."
                ),
            )

        try:
            publish_result = self._manifest_service.publish_rollout(
                OtaRolloutPublishRequest(
                    rollout_token=resolved_request.rollout_token,
                    rollout_id=resolved_request.rollout_id,
                    artifact_id=resolved_request.artifact_id,
                    rollout_channel=resolved_request.rollout_channel,
                    host=resolved_request.advertise_host,
                    port=resolved_request.port,
                )
            )
        except Exception as exc:
            return self._build_failure_result(
                resolved_request,
                errors=(str(exc),),
                message=f"No se pudo publicar el rollout OTA: {exc}",
            )

        try:
            server_started, server_reused = self._ensure_server(
                bind_host=resolved_request.bind_host,
                port=resolved_request.port,
            )
        except Exception as exc:
            return self._build_failure_result(
                resolved_request,
                errors=(str(exc),),
                message=f"No se pudo iniciar o reutilizar el servidor OTA local: {exc}",
                published_dir=publish_result.published_dir,
                manifest_path=publish_result.manifest_path,
                firmware_path=publish_result.firmware_path,
                manifest_url=publish_result.manifest_url,
                download_url=publish_result.download_url,
            )

        node_statuses: list[OtaNodeDeployStatus] = []
        warnings = list(publish_result.warnings)
        errors: list[str] = []
        for node_id in resolved_request.node_ids:
            node_status = self._dispatch_to_node(
                node_id=node_id,
                request=resolved_request,
                artifact_id=publish_result.artifact_id,
            )
            node_statuses.append(node_status)
            if node_status.phase in {OtaNodeDeployPhase.FAILED, OtaNodeDeployPhase.TIMEOUT}:
                errors.append(
                    f"Nodo {node_status.node_label}: "
                    f"{node_status.last_message or 'falló dispatch OTA'}"
                )

        result = OtaDeployResult(
            success=_derive_success(node_statuses),
            artifact_id=publish_result.artifact_id,
            rollout_token=publish_result.rollout_token,
            rollout_id=publish_result.rollout_id,
            rollout_channel=(
                publish_result.manifest.rollout_channel
                if publish_result.manifest is not None
                else ""
            ),
            node_statuses=tuple(node_statuses),
            published_dir=publish_result.published_dir,
            manifest_path=publish_result.manifest_path,
            firmware_path=publish_result.firmware_path,
            manifest_url=publish_result.manifest_url,
            download_url=publish_result.download_url,
            server_started=server_started,
            server_reused=server_reused,
            warnings=tuple(warnings),
            errors=tuple(errors),
            message=self._build_result_message(node_statuses),
        )
        return self._write_deploy_audit(result)

    def refresh_deploy_statuses(self, result: OtaDeployResult) -> OtaDeployResult:
        updated_statuses = [
            self._status_from_runtime_snapshot(
                node_id=status.node_id,
                artifact_id=result.artifact_id,
                rollout_token=result.rollout_token,
                previous=status,
            )
            for status in result.node_statuses
        ]
        refreshed = OtaDeployResult(
            success=_derive_success(updated_statuses),
            artifact_id=result.artifact_id,
            rollout_token=result.rollout_token,
            rollout_id=result.rollout_id,
            rollout_channel=result.rollout_channel,
            node_statuses=tuple(updated_statuses),
            published_dir=result.published_dir,
            manifest_path=result.manifest_path,
            firmware_path=result.firmware_path,
            manifest_url=result.manifest_url,
            download_url=result.download_url,
            server_started=result.server_started,
            server_reused=result.server_reused,
            audit_path=result.audit_path,
            warnings=result.warnings,
            errors=result.errors,
            message=self._build_result_message(updated_statuses),
            created_at_utc=result.created_at_utc,
        )
        return self._write_deploy_audit(refreshed)

    def _coerce_request(self, request: OtaDeployRequest) -> OtaDeployRequest:
        if not isinstance(request, OtaDeployRequest):
            raise OtaDeployValidationError("request invalido: se esperaba OtaDeployRequest")
        return request

    def _validate_request_against_runtime(self, request: OtaDeployRequest) -> str | None:
        if _is_loopback_host(request.advertise_host):
            remote_nodes: list[str] = []
            for node_id in request.node_ids:
                snapshot = self._runtime_client.get_node_snapshot(node_id)
                node_ip = _snapshot_ip(snapshot)
                if node_ip and not _is_loopback_host(node_ip):
                    remote_nodes.append(resolve_node_identity(node_id).node_label)
            if remote_nodes:
                joined = ", ".join(remote_nodes)
                return (
                    "advertise_host no puede ser loopback para nodos remotos "
                    f"({joined}). Usa la IP alcanzable del PC del sitio."
                )
        return None

    def _ensure_server(self, *, bind_host: str, port: int) -> tuple[bool, bool]:
        expected_root = self._manifest_service.publish_root_dir
        current = self._ota_server_service
        if current is not None and current.is_running:
            if (
                current.root_dir.resolve() == expected_root.resolve()
                and current.bind_host == bind_host
                and current.port == port
            ):
                return False, True
            current.stop()

        if (
            current is None
            or current.root_dir.resolve() != expected_root.resolve()
            or current.bind_host != bind_host
            or current.port != port
        ):
            self._ota_server_service = OtaServerService(
                root_dir=expected_root,
                bind_host=bind_host,
                port=port,
            )

        assert self._ota_server_service is not None
        self._ota_server_service.start()
        return True, False

    def _dispatch_to_node(
        self,
        *,
        node_id: int,
        request: OtaDeployRequest,
        artifact_id: str,
    ) -> OtaNodeDeployStatus:
        try:
            control_result = self._runtime_client.send_control_ota_check_now(
                node_id=node_id,
                rollout_token=int(request.rollout_token, 16),
                ack_timeout_ms=request.ack_timeout_ms,
                max_retries=request.max_retries,
                source="ota_deploy",
            )
        except Exception as exc:
            self._logger.warning(
                "Dispatch OTA_CHECK_NOW falló para node_id=%s: %s",
                node_id,
                exc,
            )
            return self._status_from_exception(
                node_id=node_id,
                artifact_id=artifact_id,
                rollout_token=request.rollout_token,
                exc=exc,
            )

        return self._status_from_control_result(
            control_result=control_result,
            artifact_id=artifact_id,
            rollout_token=request.rollout_token,
        )

    def _status_from_exception(
        self,
        *,
        node_id: int,
        artifact_id: str,
        rollout_token: str,
        exc: Exception,
    ) -> OtaNodeDeployStatus:
        identity = resolve_node_identity(node_id)
        snapshot = self._runtime_client.get_node_snapshot(node_id)
        return self._merge_runtime_snapshot(
            OtaNodeDeployStatus(
                node_id=node_id,
                node_label=identity.node_label,
                node_ip=_snapshot_ip(snapshot) or "",
                phase=OtaNodeDeployPhase.FAILED,
                ack_received=False,
                rollout_token=rollout_token,
                artifact_id=artifact_id,
                last_message=str(exc),
            ),
            snapshot,
        )

    def _status_from_control_result(
        self,
        *,
        control_result: ControlTransactionResult,
        artifact_id: str,
        rollout_token: str,
    ) -> OtaNodeDeployStatus:
        snapshot = self._runtime_client.get_node_snapshot(control_result.node_id)
        phase = _phase_from_control_result(control_result)
        base = OtaNodeDeployStatus(
            node_id=int(control_result.node_id),
            node_label=resolve_node_identity(control_result.node_id).node_label,
            node_ip=str(control_result.node_ip),
            phase=phase,
            ack_received=(
                control_result.final_status
                is ControlTransactionFinalStatus.ACK_MATCHED
            ),
            control_final_status=control_result.final_status.value,
            attempt_count=int(control_result.attempt_count),
            ack_stage=None if control_result.ack is None else control_result.ack.ack_stage,
            status_code=None if control_result.ack is None else control_result.ack.status_code,
            rollout_token=rollout_token,
            artifact_id=artifact_id,
            last_message=self._control_result_message(control_result),
        )
        return self._merge_runtime_snapshot(base, snapshot)

    def _status_from_runtime_snapshot(
        self,
        *,
        node_id: int,
        artifact_id: str,
        rollout_token: str,
        previous: OtaNodeDeployStatus,
    ) -> OtaNodeDeployStatus:
        snapshot = self._runtime_client.get_node_snapshot(node_id)
        base = OtaNodeDeployStatus(
            node_id=previous.node_id,
            node_label=previous.node_label,
            node_ip=previous.node_ip,
            phase=previous.phase,
            ack_received=previous.ack_received,
            control_final_status=previous.control_final_status,
            runtime_status=previous.runtime_status,
            ota_state_key=previous.ota_state_key,
            ota_error_key=previous.ota_error_key,
            attempt_count=previous.attempt_count,
            ack_stage=previous.ack_stage,
            status_code=previous.status_code,
            rollout_token=rollout_token,
            artifact_id=artifact_id,
            last_message=previous.last_message,
            observed_at_utc=previous.observed_at_utc,
        )
        return self._merge_runtime_snapshot(base, snapshot)

    def _merge_runtime_snapshot(
        self,
        base: OtaNodeDeployStatus,
        snapshot: object | None,
    ) -> OtaNodeDeployStatus:
        if snapshot is None:
            return base

        runtime_status = _safe_text(getattr(snapshot, "status", None))
        ota_state_key = _safe_text(
            getattr(snapshot, "ota_state_key", None),
            fallback="idle",
        ).lower()
        ota_error_key = _safe_text(
            getattr(snapshot, "ota_error_key", None),
            fallback="none",
        ).lower()
        phase = _phase_from_runtime(snapshot, fallback=base.phase)
        message = _runtime_message(snapshot, fallback=base.last_message)
        node_ip = _snapshot_ip(snapshot) or base.node_ip
        return OtaNodeDeployStatus(
            node_id=base.node_id,
            node_label=base.node_label,
            node_ip=node_ip,
            phase=phase,
            ack_received=base.ack_received,
            control_final_status=base.control_final_status,
            runtime_status=runtime_status,
            ota_state_key=ota_state_key,
            ota_error_key=ota_error_key,
            attempt_count=base.attempt_count,
            ack_stage=base.ack_stage,
            status_code=base.status_code,
            rollout_token=base.rollout_token,
            artifact_id=base.artifact_id,
            last_message=message,
        )

    def _control_result_message(self, result: ControlTransactionResult) -> str:
        if result.final_status is ControlTransactionFinalStatus.ACK_MATCHED:
            return "trigger OTA reconocido por el nodo"
        if result.final_status is ControlTransactionFinalStatus.TIMEOUT:
            return "timeout esperando ACK OTA"
        if result.last_error:
            return result.last_error
        return result.final_status.value

    def _build_result_message(
        self,
        node_statuses: list[OtaNodeDeployStatus] | tuple[OtaNodeDeployStatus, ...],
    ) -> str:
        total = len(node_statuses)
        confirmed = sum(
            1 for item in node_statuses if item.phase is OtaNodeDeployPhase.CONFIRMED
        )
        progressing = sum(
            1
            for item in node_statuses
            if item.phase
            in {
                OtaNodeDeployPhase.TRIGGERED,
                OtaNodeDeployPhase.ACKNOWLEDGED,
                OtaNodeDeployPhase.CHECKING_MANIFEST,
                OtaNodeDeployPhase.DOWNLOADING,
                OtaNodeDeployPhase.INSTALLING,
                OtaNodeDeployPhase.BOOT_VALIDATING,
            }
        )
        failed = sum(
            1
            for item in node_statuses
            if item.phase in {OtaNodeDeployPhase.FAILED, OtaNodeDeployPhase.TIMEOUT}
        )
        return (
            f"Nodos: {total} | confirmados: {confirmed} | "
            f"en progreso: {progressing} | fallidos/timeout: {failed}"
        )

    def _build_failure_result(
        self,
        request: OtaDeployRequest,
        *,
        errors: tuple[str, ...],
        message: str,
        published_dir: str = "",
        manifest_path: str = "",
        firmware_path: str = "",
        manifest_url: str = "",
        download_url: str = "",
    ) -> OtaDeployResult:
        return OtaDeployResult(
            success=False,
            artifact_id=request.artifact_id,
            rollout_token=request.rollout_token,
            rollout_id=request.rollout_id,
            rollout_channel=request.rollout_channel,
            node_statuses=tuple(
                OtaNodeDeployStatus(
                    node_id=node_id,
                    node_label=resolve_node_identity(node_id).node_label,
                    node_ip=_snapshot_ip(self._runtime_client.get_node_snapshot(node_id)) or "",
                    phase=OtaNodeDeployPhase.FAILED,
                    rollout_token=request.rollout_token,
                    artifact_id=request.artifact_id,
                    last_message=message,
                )
                for node_id in request.node_ids
            ),
            published_dir=published_dir,
            manifest_path=manifest_path,
            firmware_path=firmware_path,
            manifest_url=manifest_url,
            download_url=download_url,
            errors=errors,
            message=message,
        )

    def _write_deploy_audit(self, result: OtaDeployResult) -> OtaDeployResult:
        if not result.published_dir:
            return result

        audit_path = Path(result.published_dir) / "deploy_status.json"
        payload = {
            "artifact_id": result.artifact_id,
            "rollout_token": result.rollout_token,
            "rollout_id": result.rollout_id,
            "rollout_channel": result.rollout_channel,
            "published_dir": result.published_dir,
            "manifest_path": result.manifest_path,
            "firmware_path": result.firmware_path,
            "manifest_url": result.manifest_url,
            "download_url": result.download_url,
            "server_started": result.server_started,
            "server_reused": result.server_reused,
            "warnings": list(result.warnings),
            "errors": list(result.errors),
            "message": result.message,
            "created_at_utc": result.created_at_utc,
            "node_statuses": [
                {
                    "node_id": status.node_id,
                    "node_label": status.node_label,
                    "node_ip": status.node_ip,
                    "phase": status.phase.value,
                    "ack_received": status.ack_received,
                    "control_final_status": status.control_final_status,
                    "runtime_status": status.runtime_status,
                    "ota_state_key": status.ota_state_key,
                    "ota_error_key": status.ota_error_key,
                    "attempt_count": status.attempt_count,
                    "ack_stage": status.ack_stage,
                    "status_code": status.status_code,
                    "rollout_token": status.rollout_token,
                    "artifact_id": status.artifact_id,
                    "last_message": status.last_message,
                    "observed_at_utc": status.observed_at_utc,
                }
                for status in result.node_statuses
            ],
        }
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=audit_path.parent,
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
                "No se pudo escribir audit OTA en '%s': %s",
                audit_path,
                exc,
            )
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            return result

        return OtaDeployResult(
            success=result.success,
            artifact_id=result.artifact_id,
            rollout_token=result.rollout_token,
            rollout_id=result.rollout_id,
            rollout_channel=result.rollout_channel,
            node_statuses=result.node_statuses,
            published_dir=result.published_dir,
            manifest_path=result.manifest_path,
            firmware_path=result.firmware_path,
            manifest_url=result.manifest_url,
            download_url=result.download_url,
            server_started=result.server_started,
            server_reused=result.server_reused,
            audit_path=str(audit_path),
            warnings=result.warnings,
            errors=result.errors,
            message=result.message,
            created_at_utc=result.created_at_utc,
        )


def _derive_success(node_statuses: list[OtaNodeDeployStatus] | tuple[OtaNodeDeployStatus, ...]) -> bool:
    return any(
        status.phase not in {OtaNodeDeployPhase.FAILED, OtaNodeDeployPhase.TIMEOUT}
        for status in node_statuses
    )


def _phase_from_control_result(result: ControlTransactionResult) -> OtaNodeDeployPhase:
    if result.final_status is ControlTransactionFinalStatus.ACK_MATCHED:
        return OtaNodeDeployPhase.ACKNOWLEDGED
    if result.final_status is ControlTransactionFinalStatus.TIMEOUT:
        return OtaNodeDeployPhase.TIMEOUT
    return OtaNodeDeployPhase.FAILED


def _phase_from_runtime(snapshot: object, *, fallback: OtaNodeDeployPhase) -> OtaNodeDeployPhase:
    ota_state_key = _safe_text(getattr(snapshot, "ota_state_key", None), fallback="idle").lower()
    ota_error_key = _safe_text(getattr(snapshot, "ota_error_key", None), fallback="none").lower()
    if ota_error_key != "none" or ota_state_key == "error":
        return OtaNodeDeployPhase.FAILED
    if ota_state_key == "boot_confirmed":
        return OtaNodeDeployPhase.CONFIRMED
    if ota_state_key == "boot_validating":
        return OtaNodeDeployPhase.BOOT_VALIDATING
    if ota_state_key == "ready_reboot":
        return OtaNodeDeployPhase.INSTALLING
    if ota_state_key == "downloading":
        return OtaNodeDeployPhase.DOWNLOADING
    if ota_state_key in {"fetching_manifest", "validating_manifest"}:
        return OtaNodeDeployPhase.CHECKING_MANIFEST
    if ota_state_key == "triggered":
        return OtaNodeDeployPhase.TRIGGERED
    return fallback


def _runtime_message(snapshot: object, *, fallback: str) -> str:
    ota_error = _safe_text(getattr(snapshot, "ota_error_key", None), fallback="none").lower()
    ota_state = _safe_text(getattr(snapshot, "ota_state_key", None), fallback="idle").lower()
    status_reason = _safe_text(getattr(snapshot, "status_reason", None))
    if ota_error != "none":
        return f"OTA error: {ota_error}"
    if ota_state and ota_state != "idle":
        return f"OTA observable: {ota_state}"
    if fallback:
        return fallback
    if status_reason:
        return status_reason
    return ""


def _snapshot_ip(snapshot: object | None) -> str | None:
    if snapshot is None:
        return None
    for attribute in ("resolved_ip", "node_ip", "source_ip", "last_source_ip"):
        candidate = getattr(snapshot, attribute, None)
        text = _safe_text(candidate)
        if text:
            return text
    return None


def _is_loopback_host(value: str) -> bool:
    text = _safe_text(value).lower()
    return text in {"127.0.0.1", "localhost", "::1"}


def _safe_text(value: object, *, fallback: str = "") -> str:
    if value is None:
        return fallback
    if hasattr(value, "value"):
        text = str(getattr(value, "value")).strip()
    else:
        text = str(value).strip()
    return text if text else fallback
