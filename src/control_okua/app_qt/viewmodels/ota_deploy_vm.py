from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import re
from typing import Iterable

from control_okua.app_qt.viewmodels.firmware_manager_vm import (
    build_file_size_text,
    build_sha256_short,
)
from control_okua.app_qt.viewmodels.main_window_vm import (
    format_node_health_summary,
    format_node_ota_error,
    format_node_ota_flags,
    format_node_ota_state,
    format_node_status,
)
from control_okua.core.firmware import (
    FirmwareArtifact,
    FirmwareStatus,
    FirmwareTargetKind,
    OtaDeployResult,
    OtaNodeDeployPhase,
    OtaNodeDeployStatus,
    derive_version_code,
    normalize_target_kind,
)
from control_okua.core.firmware.catalog_models import normalize_text
from control_okua.core.node_identity_policy import resolve_node_identity


@dataclass(frozen=True)
class OtaDeployArtifactOption:
    artifact_id: str
    label: str
    summary: str
    is_eligible: bool
    ineligibility_reason: str
    recommended_host: str
    artifact: FirmwareArtifact


@dataclass(frozen=True)
class OtaDeployNodeOption:
    node_id: int
    label: str
    summary: str
    node_ip: str
    snapshot: object


@dataclass(frozen=True)
class OtaDeployNodeRow:
    node_id: int
    node_label: str
    phase_label: str
    ack_label: str
    runtime_label: str
    message: str
    observed_at_utc: str


def build_ota_artifact_options(
    artifacts: Iterable[FirmwareArtifact],
) -> list[OtaDeployArtifactOption]:
    options = [build_ota_artifact_option(artifact) for artifact in artifacts]
    return sorted(
        options,
        key=lambda item: (
            0 if item.is_eligible else 1,
            item.artifact.target_kind.value,
            item.artifact.target_variant,
            item.artifact.display_name.casefold(),
            item.artifact.version.casefold(),
        ),
    )


def build_ota_artifact_option(artifact: FirmwareArtifact) -> OtaDeployArtifactOption:
    target_kind = normalize_target_kind(artifact.target_kind)
    is_eligible, reason = evaluate_ota_artifact_eligibility(artifact)
    recommended_host = infer_artifact_pc_ip(artifact)
    target_text = f"{target_kind.value}/{artifact.target_variant}"
    label = f"{artifact.display_name} | {artifact.version} | {target_text}"
    summary = (
        f"Status={artifact.status.value} | SHA={build_sha256_short(artifact.sha256)} | "
        f"Tamaño={build_file_size_text(artifact.file_size)}"
    )
    if recommended_host:
        summary = f"{summary} | Host sugerido={recommended_host}"
    if not is_eligible:
        summary = f"{summary} | No elegible: {reason}"
    return OtaDeployArtifactOption(
        artifact_id=artifact.artifact_id,
        label=label,
        summary=summary,
        is_eligible=is_eligible,
        ineligibility_reason=reason,
        recommended_host=recommended_host,
        artifact=artifact,
    )


def evaluate_ota_artifact_eligibility(artifact: FirmwareArtifact) -> tuple[bool, str]:
    if normalize_target_kind(artifact.target_kind) is FirmwareTargetKind.UNKNOWN:
        return False, "target_kind unknown"
    if artifact.status is FirmwareStatus.OBSOLETE:
        return False, "status obsolete"
    if not normalize_text(artifact.file_path):
        return False, "file_path faltante"
    if not normalize_text(artifact.sha256):
        return False, "sha256 faltante"
    if int(artifact.file_size) <= 0:
        return False, "file_size inválido"
    try:
        derive_version_code(artifact.version)
    except Exception:
        return False, "version no compatible con version_code OTA"
    return True, "Apto para OTA"


def build_ota_node_options(snapshots: Iterable[object]) -> list[OtaDeployNodeOption]:
    options: list[OtaDeployNodeOption] = []
    seen: set[int] = set()
    for snapshot in snapshots:
        raw_node_id = getattr(snapshot, "node_id", None)
        try:
            node_id = int(raw_node_id)
        except (TypeError, ValueError):
            continue
        if node_id <= 0 or node_id in seen:
            continue
        seen.add(node_id)
        identity = resolve_node_identity(node_id)
        node_ip = _snapshot_ip(snapshot)
        summary_parts = [
            format_node_status(snapshot),
            format_node_health_summary(snapshot),
        ]
        ota_state = format_node_ota_state(snapshot)
        if ota_state != "inactiva":
            summary_parts.append(f"OTA {ota_state}")
        if node_ip:
            summary_parts.append(node_ip)
        options.append(
            OtaDeployNodeOption(
                node_id=node_id,
                label=f"{identity.node_label} (node_id={node_id})",
                summary=" | ".join(part for part in summary_parts if part and part != "—"),
                node_ip=node_ip,
                snapshot=snapshot,
            )
        )
    return sorted(options, key=lambda item: item.node_id)


def build_ota_node_result_rows(
    node_statuses: Iterable[OtaNodeDeployStatus],
) -> list[OtaDeployNodeRow]:
    return [
        OtaDeployNodeRow(
            node_id=status.node_id,
            node_label=status.node_label,
            phase_label=format_ota_deploy_phase(status.phase),
            ack_label=build_ota_ack_label(status),
            runtime_label=build_ota_runtime_label(status),
            message=status.last_message or "—",
            observed_at_utc=status.observed_at_utc,
        )
        for status in node_statuses
    ]


def build_ota_deploy_result_summary(result: OtaDeployResult | None) -> str:
    if result is None:
        return "Aún no hay despliegue OTA en curso."
    total = len(result.node_statuses)
    confirmed = sum(
        1 for status in result.node_statuses if status.phase is OtaNodeDeployPhase.CONFIRMED
    )
    failed = sum(
        1
        for status in result.node_statuses
        if status.phase in {OtaNodeDeployPhase.FAILED, OtaNodeDeployPhase.TIMEOUT}
    )
    return (
        f"Artifact={result.artifact_id} | rollout={result.rollout_token} | "
        f"nodos={total} | confirmados={confirmed} | fallidos/timeout={failed}"
    )


def build_ota_deploy_result_details(result: OtaDeployResult | None) -> str:
    if result is None:
        return "Sin resultados OTA todavía."
    lines = [
        result.message or "Sin mensaje general.",
        f"Manifest URL: {result.manifest_url or '—'}",
        f"Download URL: {result.download_url or '—'}",
        f"Directorio publicado: {result.published_dir or '—'}",
    ]
    if result.audit_path:
        lines.append(f"Audit local: {result.audit_path}")
    if result.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {item}" for item in result.warnings)
    if result.errors:
        lines.append("Errors:")
        lines.extend(f"- {item}" for item in result.errors)
    return "\n".join(lines)


def build_recommended_rollout_channel(artifact: FirmwareArtifact | None) -> str:
    if artifact is None:
        return "stable"
    if artifact.status is FirmwareStatus.BETA:
        return "beta"
    if artifact.status is FirmwareStatus.SITUATIONAL:
        return "situational"
    return "stable"


_PC_IP_PATTERN = re.compile(r"\bPC_IP\s*=\s*([0-9]{1,3}(?:\.[0-9]{1,3}){3})\b", re.IGNORECASE)


def infer_artifact_pc_ip(artifact: FirmwareArtifact | None) -> str:
    if artifact is None:
        return ""
    for field in (artifact.notes, artifact.source_notes):
        match = _PC_IP_PATTERN.search(normalize_text(field))
        if not match:
            continue
        candidate = match.group(1)
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            continue
        return candidate
    return ""


def format_ota_deploy_phase(phase: OtaNodeDeployPhase | str) -> str:
    raw = phase.value if isinstance(phase, OtaNodeDeployPhase) else str(phase).strip().lower()
    mapping = {
        "pending": "Pendiente",
        "triggered": "Trigger enviado",
        "acknowledged": "ACK recibido",
        "checking_manifest": "Consultando manifest",
        "downloading": "Descargando",
        "installing": "Instalando",
        "boot_validating": "Validando boot",
        "confirmed": "Confirmado",
        "failed": "Falló",
        "timeout": "Timeout",
    }
    return mapping.get(raw, raw or "—")


def build_ota_ack_label(status: OtaNodeDeployStatus) -> str:
    if status.ack_received:
        return "Sí"
    if status.phase is OtaNodeDeployPhase.TIMEOUT:
        return "Timeout"
    if status.control_final_status:
        return status.control_final_status
    return "No"


def build_ota_runtime_label(status: OtaNodeDeployStatus) -> str:
    if status.ota_error_key and status.ota_error_key != "none":
        fake_snapshot = _DeploySnapshot(
            ota_state_key=status.ota_state_key,
            ota_error_key=status.ota_error_key,
            ota_check_pending=False,
            ota_pending_reboot=False,
            ota_pending_verify=False,
            ota_health_confirmed=False,
        )
        return f"{format_ota_state_for_status(status)} | {format_node_ota_error(fake_snapshot)}"
    if status.ota_state_key and status.ota_state_key != "idle":
        fake_snapshot = _DeploySnapshot(
            ota_state_key=status.ota_state_key,
            ota_error_key=status.ota_error_key,
            ota_check_pending=False,
            ota_pending_reboot=False,
            ota_pending_verify=False,
            ota_health_confirmed=False,
        )
        return format_ota_state_for_status(status)
    if status.runtime_status:
        return status.runtime_status
    return "—"


def format_ota_state_for_status(status: OtaNodeDeployStatus) -> str:
    fake_snapshot = _DeploySnapshot(
        ota_state_key=status.ota_state_key,
        ota_error_key=status.ota_error_key,
        ota_check_pending=False,
        ota_pending_reboot=False,
        ota_pending_verify=False,
        ota_health_confirmed=False,
    )
    flags_text = format_node_ota_flags(fake_snapshot)
    state_text = format_node_ota_state(fake_snapshot)
    if flags_text != "sin flags":
        return f"{state_text} ({flags_text})"
    return state_text


@dataclass(frozen=True)
class _DeploySnapshot:
    ota_state_key: str
    ota_error_key: str
    ota_check_pending: bool
    ota_pending_reboot: bool
    ota_pending_verify: bool
    ota_health_confirmed: bool


def _snapshot_ip(snapshot: object) -> str:
    for attribute in ("resolved_ip", "node_ip", "source_ip", "last_source_ip"):
        candidate = getattr(snapshot, attribute, None)
        text = normalize_text(candidate)
        if text:
            return text
    return ""
