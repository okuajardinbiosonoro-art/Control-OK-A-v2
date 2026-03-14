from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class PreflightSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ReadinessLevel(str, Enum):
    READY = "ready"
    READY_WITH_WARNINGS = "ready_with_warnings"
    BLOCKED = "blocked"


class PreflightCheckCode(str, Enum):
    PROFILE_MISSING = "profile_missing"
    PROFILE_INVALID = "profile_invalid"
    SESSION_SPEC_INVALID = "session_spec_invalid"
    BACKEND_MISSING = "backend_missing"
    MODE_PROFILE_MISMATCH_CORRECTED = "mode_profile_mismatch_corrected"
    SERIAL_CONFIG_INCOMPLETE = "serial_config_incomplete"
    UDP_CONFIG_INCOMPLETE = "udp_config_incomplete"
    MIDI_OUTPUTS_MISSING = "midi_outputs_missing"
    MIDI_OUTPUTS_INVALID = "midi_outputs_invalid"
    LOGGING_CONFIG_INVALID = "logging_config_invalid"
    LOGGING_FOLDER_MISSING = "logging_folder_missing"
    LOGGING_DISABLED = "logging_disabled"


@dataclass(frozen=True)
class PreflightFinding:
    code: PreflightCheckCode
    severity: PreflightSeverity
    message: str
    details: dict[str, Any] | None = None
    is_blocking: bool = False


@dataclass(frozen=True)
class PreflightReport:
    readiness: ReadinessLevel
    findings: tuple[PreflightFinding, ...]
    blocking_count: int
    warning_count: int
    info_count: int
    summary: str
    can_start: bool
    profile_id: str | None
    derived_mode: str | None
    backend_kind: str | None
    session_spec_valid: bool
