from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Iterable

from control_okua.core.firmware.catalog_models import normalize_text, utc_now_iso
from control_okua.core.firmware.ota_deploy_models import (
    OtaDeployResult,
    OtaDeployValidationError,
    OtaNodeDeployPhase,
    OtaNodeDeployStatus,
    build_default_rollout_token,
    coerce_ota_deploy_phase,
    normalize_node_ids,
)
from control_okua.core.firmware.ota_manifest_models import (
    DEFAULT_OTA_HTTP_PORT,
    OtaManifestValidationError,
    normalize_http_host,
    normalize_http_port,
    normalize_rollout_channel,
    normalize_rollout_token_hex,
)


class OtaCampaignValidationError(ValueError):
    """Raised when an OTA campaign plan or result is invalid."""


class OtaCampaignStatus(str, Enum):
    PLANNED = "planned"
    CANARY_RUNNING = "canary_running"
    WAVE_RUNNING = "wave_running"
    PAUSED = "paused"
    FAILED = "failed"
    COMPLETED = "completed"
    ABORTED = "aborted"


class OtaCampaignHealthGate(str, Enum):
    NOT_EVALUATED = "not_evaluated"
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class OtaCampaignNodeOutcome(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    ABORTED = "aborted"


def build_default_campaign_id(now_utc: str | None = None) -> str:
    timestamp = normalize_text(now_utc, fallback=utc_now_iso())
    digits = "".join(ch for ch in timestamp if ch.isdigit())
    if len(digits) < 14:
        digits = digits.ljust(14, "0")
    return f"campaign-{digits[:14]}"


def normalize_campaign_id(value: str | None, *, fallback: str | None = None) -> str:
    text = normalize_text(value, fallback=fallback or "")
    if not text:
        text = build_default_campaign_id()
    allowed = []
    for char in text.lower():
        if char.isalnum() or char in {"-", "_"}:
            allowed.append(char)
        else:
            allowed.append("-")
    normalized = "".join(allowed).strip("-_")
    if not normalized:
        raise OtaCampaignValidationError("campaign_id inválido")
    return normalized


def normalize_optional_node_ids(values: Iterable[int] | None) -> tuple[int, ...]:
    if values is None:
        return ()
    normalized: list[int] = []
    seen: set[int] = set()
    for value in values:
        try:
            node_id = int(value)
        except (TypeError, ValueError) as exc:
            raise OtaCampaignValidationError(
                f"node_id inválido en campaña OTA: {value!r}"
            ) from exc
        if node_id <= 0 or node_id > 0xFFFF:
            raise OtaCampaignValidationError(
                f"node_id fuera de rango unicast para campaña OTA: {value!r}"
            )
        if node_id in seen:
            raise OtaCampaignValidationError(
                f"node_id duplicado en campaña OTA: {node_id}"
            )
        seen.add(node_id)
        normalized.append(node_id)
    return tuple(normalized)


def coerce_ota_campaign_status(value: OtaCampaignStatus | str) -> OtaCampaignStatus:
    if isinstance(value, OtaCampaignStatus):
        return value
    raw = normalize_text(value).lower()
    try:
        return OtaCampaignStatus(raw)
    except ValueError as exc:
        raise OtaCampaignValidationError(
            f"campaign_status inválido: {value!r}"
        ) from exc


def coerce_ota_campaign_health_gate(
    value: OtaCampaignHealthGate | str,
) -> OtaCampaignHealthGate:
    if isinstance(value, OtaCampaignHealthGate):
        return value
    raw = normalize_text(value).lower()
    try:
        return OtaCampaignHealthGate(raw)
    except ValueError as exc:
        raise OtaCampaignValidationError(
            f"health_gate inválido: {value!r}"
        ) from exc


def coerce_ota_campaign_node_outcome(
    value: OtaCampaignNodeOutcome | str,
) -> OtaCampaignNodeOutcome:
    if isinstance(value, OtaCampaignNodeOutcome):
        return value
    raw = normalize_text(value).lower()
    try:
        return OtaCampaignNodeOutcome(raw)
    except ValueError as exc:
        raise OtaCampaignValidationError(
            f"node_outcome inválido: {value!r}"
        ) from exc


@dataclass(frozen=True)
class OtaCampaignWave:
    wave_index: int
    label: str
    node_ids: tuple[int, ...] | list[int]
    is_canary: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "wave_index", int(self.wave_index))
        if self.wave_index < 0:
            raise OtaCampaignValidationError("wave_index debe ser >= 0")
        normalized_label = normalize_text(
            self.label,
            fallback="canary" if self.is_canary else f"wave_{self.wave_index}",
        ).lower()
        object.__setattr__(self, "label", normalized_label)
        object.__setattr__(self, "node_ids", normalize_node_ids(self.node_ids))


@dataclass(frozen=True)
class OtaCampaignNodeStatus:
    node_id: int
    node_label: str
    wave_index: int
    wave_label: str
    is_canary: bool = False
    phase: OtaNodeDeployPhase | str = OtaNodeDeployPhase.PENDING
    outcome: OtaCampaignNodeOutcome | str = OtaCampaignNodeOutcome.PENDING
    ack_received: bool = False
    control_final_status: str = ""
    runtime_status: str = ""
    ota_state_key: str = "idle"
    ota_error_key: str = "none"
    rollout_token: str = ""
    artifact_id: str = ""
    last_message: str = ""
    observed_at_utc: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", int(self.node_id))
        if self.node_id <= 0 or self.node_id > 0xFFFF:
            raise OtaCampaignValidationError(
                f"node_id fuera de rango para OtaCampaignNodeStatus: {self.node_id!r}"
            )
        if not normalize_text(self.node_label):
            raise OtaCampaignValidationError("node_label es obligatorio")
        object.__setattr__(self, "wave_index", int(self.wave_index))
        if self.wave_index < 0:
            raise OtaCampaignValidationError("wave_index debe ser >= 0")
        object.__setattr__(self, "wave_label", normalize_text(self.wave_label))
        if not self.wave_label:
            raise OtaCampaignValidationError("wave_label es obligatorio")
        object.__setattr__(self, "phase", coerce_ota_deploy_phase(self.phase))
        object.__setattr__(self, "outcome", coerce_ota_campaign_node_outcome(self.outcome))
        object.__setattr__(self, "control_final_status", normalize_text(self.control_final_status))
        object.__setattr__(self, "runtime_status", normalize_text(self.runtime_status))
        object.__setattr__(self, "ota_state_key", normalize_text(self.ota_state_key, fallback="idle").lower())
        object.__setattr__(self, "ota_error_key", normalize_text(self.ota_error_key, fallback="none").lower())
        object.__setattr__(self, "rollout_token", normalize_text(self.rollout_token))
        object.__setattr__(self, "artifact_id", normalize_text(self.artifact_id))
        object.__setattr__(self, "last_message", normalize_text(self.last_message))
        object.__setattr__(self, "observed_at_utc", normalize_text(self.observed_at_utc, fallback=utc_now_iso()))


@dataclass(frozen=True)
class OtaCampaignWaveResult:
    wave: OtaCampaignWave
    deploy_result: OtaDeployResult | None = None
    health_gate: OtaCampaignHealthGate | str = OtaCampaignHealthGate.NOT_EVALUATED
    started_at_utc: str = ""
    finished_at_utc: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.wave, OtaCampaignWave):
            raise OtaCampaignValidationError("wave_result requiere OtaCampaignWave válido")
        object.__setattr__(self, "health_gate", coerce_ota_campaign_health_gate(self.health_gate))
        object.__setattr__(self, "started_at_utc", normalize_text(self.started_at_utc))
        object.__setattr__(self, "finished_at_utc", normalize_text(self.finished_at_utc))

    @property
    def is_executed(self) -> bool:
        return self.deploy_result is not None


def build_campaign_waves(
    node_ids: Iterable[int],
    *,
    canary_nodes: Iterable[int] | None = None,
    wave_size: int = 1,
) -> tuple[OtaCampaignWave, ...]:
    normalized_node_ids = normalize_node_ids(node_ids)
    normalized_canary = normalize_optional_node_ids(canary_nodes)
    remaining = [node_id for node_id in normalized_node_ids if node_id not in normalized_canary]
    try:
        resolved_wave_size = int(wave_size)
    except (TypeError, ValueError) as exc:
        raise OtaCampaignValidationError(
            f"wave_size inválido: {wave_size!r}"
        ) from exc
    if resolved_wave_size <= 0:
        raise OtaCampaignValidationError("wave_size debe ser > 0")

    waves: list[OtaCampaignWave] = []
    wave_index = 1
    for start in range(0, len(remaining), resolved_wave_size):
        chunk = tuple(remaining[start : start + resolved_wave_size])
        if not chunk:
            continue
        waves.append(
            OtaCampaignWave(
                wave_index=wave_index,
                label=f"wave_{wave_index}",
                node_ids=chunk,
                is_canary=False,
            )
        )
        wave_index += 1
    return tuple(waves)


@dataclass(frozen=True)
class OtaCampaignPlan:
    artifact_id: str
    node_ids: tuple[int, ...] | list[int]
    canary_nodes: tuple[int, ...] | list[int] = field(default_factory=tuple)
    waves: tuple[OtaCampaignWave, ...] | list[OtaCampaignWave] = field(default_factory=tuple)
    advertise_host: str = "127.0.0.1"
    rollout_token: int | str = field(default_factory=build_default_rollout_token)
    rollout_id: str = ""
    rollout_channel: str = ""
    bind_host: str = "0.0.0.0"
    port: int = DEFAULT_OTA_HTTP_PORT
    ack_timeout_ms: int = 600
    max_retries: int = 0
    campaign_id: str = field(default_factory=build_default_campaign_id)
    require_canary: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_id", normalize_text(self.artifact_id))
        if not self.artifact_id:
            raise OtaCampaignValidationError("artifact_id es obligatorio para OTA campaign")
        object.__setattr__(self, "node_ids", normalize_node_ids(self.node_ids))
        object.__setattr__(self, "canary_nodes", normalize_optional_node_ids(self.canary_nodes))
        if self.require_canary and not self.canary_nodes:
            raise OtaCampaignValidationError(
                "canary_nodes debe contener al menos un nodo cuando require_canary=True"
            )
        unknown_canary = [node_id for node_id in self.canary_nodes if node_id not in self.node_ids]
        if unknown_canary:
            raise OtaCampaignValidationError(
                "canary_nodes debe ser subconjunto de node_ids"
            )

        normalized_waves: list[OtaCampaignWave] = []
        seen_wave_indexes: set[int] = set()
        assigned_manual_nodes: set[int] = set()
        for raw_wave in self.waves:
            wave = raw_wave if isinstance(raw_wave, OtaCampaignWave) else OtaCampaignWave(**raw_wave)
            if wave.is_canary:
                raise OtaCampaignValidationError(
                    "waves manuales no debe incluir entradas is_canary=True"
                )
            if wave.wave_index in seen_wave_indexes:
                raise OtaCampaignValidationError(
                    f"wave_index duplicado en campaña OTA: {wave.wave_index}"
                )
            seen_wave_indexes.add(wave.wave_index)
            for node_id in wave.node_ids:
                if node_id not in self.node_ids:
                    raise OtaCampaignValidationError(
                        f"El nodo {node_id} de la ola {wave.label} no pertenece a node_ids"
                    )
                if node_id in self.canary_nodes:
                    raise OtaCampaignValidationError(
                        f"El nodo {node_id} no puede repetirse entre canary y olas"
                    )
                if node_id in assigned_manual_nodes:
                    raise OtaCampaignValidationError(
                        f"El nodo {node_id} está repetido entre olas manuales"
                    )
                assigned_manual_nodes.add(node_id)
            normalized_waves.append(wave)

        remaining_nodes = tuple(
            node_id for node_id in self.node_ids if node_id not in self.canary_nodes
        )
        if set(remaining_nodes) != assigned_manual_nodes:
            missing = sorted(set(remaining_nodes) - assigned_manual_nodes)
            extra = sorted(assigned_manual_nodes - set(remaining_nodes))
            if missing:
                raise OtaCampaignValidationError(
                    f"Hay nodos sin ola manual asignada: {missing}"
                )
            if extra:
                raise OtaCampaignValidationError(
                    f"Hay nodos en olas que no pertenecen al plan restante: {extra}"
                )

        try:
            advertise_host = normalize_http_host(self.advertise_host)
            port = normalize_http_port(self.port)
            rollout_token = normalize_rollout_token_hex(self.rollout_token)
            rollout_channel = normalize_text(self.rollout_channel).lower()
            if rollout_channel:
                rollout_channel = normalize_rollout_channel(rollout_channel)
        except OtaManifestValidationError as exc:
            raise OtaCampaignValidationError(str(exc)) from exc

        bind_host = normalize_text(self.bind_host)
        if not bind_host:
            raise OtaCampaignValidationError("bind_host es obligatorio")

        object.__setattr__(self, "advertise_host", advertise_host)
        object.__setattr__(self, "bind_host", bind_host)
        object.__setattr__(self, "port", port)
        object.__setattr__(self, "rollout_token", rollout_token)
        object.__setattr__(self, "rollout_id", normalize_text(self.rollout_id))
        object.__setattr__(self, "rollout_channel", rollout_channel)
        object.__setattr__(self, "ack_timeout_ms", int(self.ack_timeout_ms))
        object.__setattr__(self, "max_retries", int(self.max_retries))
        if self.ack_timeout_ms <= 0:
            raise OtaCampaignValidationError("ack_timeout_ms debe ser > 0")
        if self.max_retries < 0:
            raise OtaCampaignValidationError("max_retries debe ser >= 0")
        object.__setattr__(self, "campaign_id", normalize_campaign_id(self.campaign_id))
        object.__setattr__(self, "waves", tuple(sorted(normalized_waves, key=lambda item: item.wave_index)))


@dataclass(frozen=True)
class OtaCampaignResult:
    success: bool
    campaign_id: str
    artifact_id: str
    rollout_token: str
    rollout_id: str
    rollout_channel: str
    node_ids: tuple[int, ...]
    canary_nodes: tuple[int, ...]
    waves: tuple[OtaCampaignWave, ...]
    wave_results: tuple[OtaCampaignWaveResult, ...]
    node_statuses: tuple[OtaCampaignNodeStatus, ...]
    current_phase: str
    campaign_status: OtaCampaignStatus | str
    health_gate: OtaCampaignHealthGate | str
    continue_allowed: bool = False
    paused_by_operator: bool = False
    abort_reason: str = ""
    advertise_host: str = ""
    bind_host: str = ""
    port: int = DEFAULT_OTA_HTTP_PORT
    ack_timeout_ms: int = 600
    max_retries: int = 0
    published_dir: str = ""
    manifest_path: str = ""
    firmware_path: str = ""
    manifest_url: str = ""
    download_url: str = ""
    audit_path: str = ""
    started_at_utc: str = field(default_factory=utc_now_iso)
    finished_at_utc: str = ""
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    message: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "campaign_id", normalize_campaign_id(self.campaign_id))
        object.__setattr__(self, "artifact_id", normalize_text(self.artifact_id))
        if not self.artifact_id:
            raise OtaCampaignValidationError("artifact_id es obligatorio en OtaCampaignResult")
        object.__setattr__(self, "rollout_token", normalize_rollout_token_hex(self.rollout_token))
        object.__setattr__(self, "rollout_id", normalize_text(self.rollout_id))
        object.__setattr__(self, "rollout_channel", normalize_text(self.rollout_channel).lower())
        object.__setattr__(self, "node_ids", normalize_node_ids(self.node_ids))
        object.__setattr__(self, "canary_nodes", normalize_optional_node_ids(self.canary_nodes))
        object.__setattr__(self, "waves", tuple(self.waves))
        object.__setattr__(self, "wave_results", tuple(self.wave_results))
        object.__setattr__(self, "node_statuses", tuple(self.node_statuses))
        object.__setattr__(self, "current_phase", normalize_text(self.current_phase, fallback="planned"))
        object.__setattr__(self, "campaign_status", coerce_ota_campaign_status(self.campaign_status))
        object.__setattr__(self, "health_gate", coerce_ota_campaign_health_gate(self.health_gate))
        object.__setattr__(self, "abort_reason", normalize_text(self.abort_reason))
        object.__setattr__(self, "advertise_host", normalize_text(self.advertise_host))
        object.__setattr__(self, "bind_host", normalize_text(self.bind_host))
        object.__setattr__(self, "port", int(self.port))
        object.__setattr__(self, "ack_timeout_ms", int(self.ack_timeout_ms))
        object.__setattr__(self, "max_retries", int(self.max_retries))
        if self.port < 1 or self.port > 65535:
            raise OtaCampaignValidationError("port inválido en OtaCampaignResult")
        if self.ack_timeout_ms <= 0:
            raise OtaCampaignValidationError("ack_timeout_ms inválido en OtaCampaignResult")
        if self.max_retries < 0:
            raise OtaCampaignValidationError("max_retries inválido en OtaCampaignResult")
        object.__setattr__(self, "published_dir", normalize_text(self.published_dir))
        object.__setattr__(self, "manifest_path", normalize_text(self.manifest_path))
        object.__setattr__(self, "firmware_path", normalize_text(self.firmware_path))
        object.__setattr__(self, "manifest_url", normalize_text(self.manifest_url))
        object.__setattr__(self, "download_url", normalize_text(self.download_url))
        object.__setattr__(self, "audit_path", normalize_text(self.audit_path))
        object.__setattr__(self, "started_at_utc", normalize_text(self.started_at_utc, fallback=utc_now_iso()))
        object.__setattr__(self, "finished_at_utc", normalize_text(self.finished_at_utc))
        object.__setattr__(self, "warnings", tuple(normalize_text(item) for item in self.warnings if normalize_text(item)))
        object.__setattr__(self, "errors", tuple(normalize_text(item) for item in self.errors if normalize_text(item)))
        object.__setattr__(self, "message", normalize_text(self.message))

    def with_node_statuses(self, node_statuses: Iterable[OtaCampaignNodeStatus]) -> "OtaCampaignResult":
        return replace(self, node_statuses=tuple(node_statuses))
