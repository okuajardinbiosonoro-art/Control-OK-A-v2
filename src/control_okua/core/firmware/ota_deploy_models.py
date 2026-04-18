from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Iterable

from control_okua.core.firmware.catalog_models import normalize_text, utc_now_iso
from control_okua.core.firmware.ota_manifest_models import (
    DEFAULT_OTA_HTTP_PORT,
    OtaManifestValidationError,
    normalize_http_host,
    normalize_http_port,
    normalize_rollout_channel,
    normalize_rollout_token_hex,
)


class OtaDeployValidationError(ValueError):
    """Raised when an OTA deploy request is invalid."""


class OtaNodeDeployPhase(str, Enum):
    PENDING = "pending"
    TRIGGERED = "triggered"
    ACKNOWLEDGED = "acknowledged"
    CHECKING_MANIFEST = "checking_manifest"
    DOWNLOADING = "downloading"
    INSTALLING = "installing"
    BOOT_VALIDATING = "boot_validating"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    TIMEOUT = "timeout"


def build_default_rollout_token(now_utc: str | None = None) -> str:
    timestamp = normalize_text(now_utc, fallback=utc_now_iso())
    digits = "".join(ch for ch in timestamp if ch.isdigit())
    if len(digits) < 8:
        digits = digits.ljust(8, "0")
    return digits[:8].lower()


def normalize_node_ids(values: Iterable[int]) -> tuple[int, ...]:
    normalized: list[int] = []
    seen: set[int] = set()
    for value in values:
        try:
            node_id = int(value)
        except (TypeError, ValueError) as exc:
            raise OtaDeployValidationError(
                f"node_id invalido en request OTA: {value!r}"
            ) from exc
        if node_id <= 0 or node_id > 0xFFFF:
            raise OtaDeployValidationError(
                f"node_id fuera de rango unicast para OTA: {value!r}"
            )
        if node_id in seen:
            continue
        seen.add(node_id)
        normalized.append(node_id)
    if not normalized:
        raise OtaDeployValidationError(
            "node_ids debe contener al menos un nodo explícitamente seleccionado"
        )
    return tuple(normalized)


@dataclass(frozen=True)
class OtaNodeDeployStatus:
    node_id: int
    node_label: str
    node_ip: str = ""
    phase: OtaNodeDeployPhase | str = OtaNodeDeployPhase.PENDING
    ack_received: bool = False
    control_final_status: str = ""
    runtime_status: str = ""
    ota_state_key: str = "idle"
    ota_error_key: str = "none"
    attempt_count: int = 0
    ack_stage: int | None = None
    status_code: int | None = None
    rollout_token: str = ""
    artifact_id: str = ""
    last_message: str = ""
    baseline_uptime_s: int | None = None
    baseline_reset_reason: int | None = None
    baseline_boot_marker: int | None = None
    observed_at_utc: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", int(self.node_id))
        if self.node_id <= 0 or self.node_id > 0xFFFF:
            raise OtaDeployValidationError(
                f"node_id fuera de rango para OtaNodeDeployStatus: {self.node_id!r}"
            )
        if not normalize_text(self.node_label):
            raise OtaDeployValidationError("node_label es obligatorio")
        object.__setattr__(self, "node_ip", normalize_text(self.node_ip))
        object.__setattr__(self, "phase", coerce_ota_deploy_phase(self.phase))
        object.__setattr__(self, "control_final_status", normalize_text(self.control_final_status))
        object.__setattr__(self, "runtime_status", normalize_text(self.runtime_status))
        object.__setattr__(self, "ota_state_key", normalize_text(self.ota_state_key, fallback="idle").lower())
        object.__setattr__(self, "ota_error_key", normalize_text(self.ota_error_key, fallback="none").lower())
        object.__setattr__(self, "attempt_count", max(0, int(self.attempt_count)))
        object.__setattr__(self, "rollout_token", normalize_text(self.rollout_token))
        object.__setattr__(self, "artifact_id", normalize_text(self.artifact_id))
        object.__setattr__(self, "last_message", normalize_text(self.last_message))
        object.__setattr__(self, "baseline_uptime_s", _coerce_optional_non_negative_int(self.baseline_uptime_s))
        object.__setattr__(self, "baseline_reset_reason", _coerce_optional_non_negative_int(self.baseline_reset_reason))
        object.__setattr__(self, "baseline_boot_marker", _coerce_optional_boot_marker(self.baseline_boot_marker))
        object.__setattr__(self, "observed_at_utc", normalize_text(self.observed_at_utc, fallback=utc_now_iso()))


def coerce_ota_deploy_phase(value: OtaNodeDeployPhase | str) -> OtaNodeDeployPhase:
    if isinstance(value, OtaNodeDeployPhase):
        return value
    raw = normalize_text(value).lower()
    try:
        return OtaNodeDeployPhase(raw)
    except ValueError as exc:
        raise OtaDeployValidationError(f"fase OTA invalida: {value!r}") from exc


def _coerce_optional_non_negative_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return None
    if resolved < 0:
        return None
    return resolved


def _coerce_optional_boot_marker(value: object) -> int | None:
    resolved = _coerce_optional_non_negative_int(value)
    if resolved is None or resolved > 0x0F:
        return None
    return resolved


@dataclass(frozen=True)
class OtaDeployRequest:
    artifact_id: str
    node_ids: tuple[int, ...] | list[int]
    advertise_host: str
    rollout_token: int | str = field(default_factory=build_default_rollout_token)
    rollout_id: str = ""
    rollout_channel: str = ""
    bind_host: str = "0.0.0.0"
    port: int = DEFAULT_OTA_HTTP_PORT
    ack_timeout_ms: int = 600
    max_retries: int = 0
    allow_downgrade: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_id", normalize_text(self.artifact_id))
        if not self.artifact_id:
            raise OtaDeployValidationError("artifact_id es obligatorio para OTA deploy")
        object.__setattr__(self, "node_ids", normalize_node_ids(self.node_ids))
        try:
            advertise_host = normalize_http_host(self.advertise_host)
            port = normalize_http_port(self.port)
            rollout_token = normalize_rollout_token_hex(self.rollout_token)
            rollout_channel = normalize_text(self.rollout_channel).lower()
            if rollout_channel:
                rollout_channel = normalize_rollout_channel(rollout_channel)
        except OtaManifestValidationError as exc:
            raise OtaDeployValidationError(str(exc)) from exc

        object.__setattr__(self, "advertise_host", advertise_host)
        bind_host = normalize_text(self.bind_host)
        if not bind_host:
            raise OtaDeployValidationError("bind_host es obligatorio")
        object.__setattr__(self, "bind_host", bind_host)
        object.__setattr__(self, "port", port)
        object.__setattr__(self, "rollout_token", rollout_token)
        object.__setattr__(self, "rollout_id", normalize_text(self.rollout_id))
        object.__setattr__(self, "rollout_channel", rollout_channel)
        object.__setattr__(self, "ack_timeout_ms", int(self.ack_timeout_ms))
        object.__setattr__(self, "max_retries", int(self.max_retries))
        object.__setattr__(self, "allow_downgrade", bool(self.allow_downgrade))
        if self.ack_timeout_ms <= 0:
            raise OtaDeployValidationError("ack_timeout_ms debe ser > 0")
        if self.max_retries < 0:
            raise OtaDeployValidationError("max_retries debe ser >= 0")


@dataclass(frozen=True)
class OtaDeployResult:
    success: bool
    artifact_id: str
    rollout_token: str
    rollout_id: str
    rollout_channel: str
    node_statuses: tuple[OtaNodeDeployStatus, ...]
    published_dir: str = ""
    manifest_path: str = ""
    firmware_path: str = ""
    manifest_url: str = ""
    download_url: str = ""
    server_started: bool = False
    server_reused: bool = False
    audit_path: str = ""
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    message: str = ""
    created_at_utc: str = field(default_factory=utc_now_iso)

    def with_node_statuses(self, node_statuses: Iterable[OtaNodeDeployStatus]) -> "OtaDeployResult":
        return replace(self, node_statuses=tuple(node_statuses))
