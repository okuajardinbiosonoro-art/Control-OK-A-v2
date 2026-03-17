from __future__ import annotations

from typing import Any

from control_okua.core.config.config_schema import validate_and_fix
from control_okua.core.preflight.preflight_models import (
    PreflightCheckCode,
    PreflightFinding,
    PreflightReport,
    PreflightSeverity,
    ReadinessLevel,
)
from control_okua.core.profiles.profile_service import is_known_profile_id
from control_okua.core.session.session_models import SessionSpec, build_session_request_from_profile


def _finding(
    code: PreflightCheckCode,
    severity: PreflightSeverity,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    is_blocking: bool = False,
) -> PreflightFinding:
    return PreflightFinding(
        code=code,
        severity=severity,
        message=message,
        details=details,
        is_blocking=is_blocking,
    )


def _validate_midi_outputs(outputs: Any) -> tuple[bool, str | None]:
    if not isinstance(outputs, dict):
        return False, "midi.outputs debe ser un dict."
    if not outputs:
        return False, "midi.outputs no puede quedar vacio."

    for key, value in outputs.items():
        if isinstance(key, bool):
            return False, "midi.outputs tiene bus invalido."
        try:
            bus = int(key)
        except (TypeError, ValueError):
            return False, "midi.outputs tiene llaves no numericas."
        if bus < 0 or bus > 255:
            return False, "midi.outputs tiene buses fuera de rango."
        if not isinstance(value, str) or not value.strip():
            return False, "midi.outputs tiene puertos vacios o invalidos."

    return True, None


def collect_profile_checks(
    raw_cfg: dict[str, Any],
    normalize_warnings: list[str],
    spec: SessionSpec,
) -> list[PreflightFinding]:
    findings: list[PreflightFinding] = []

    profile_cfg = raw_cfg.get("profile")
    if not isinstance(profile_cfg, dict):
        findings.append(
            _finding(
                PreflightCheckCode.PROFILE_MISSING,
                PreflightSeverity.ERROR,
                "Falta la seccion profile.active en la configuracion.",
                is_blocking=True,
            )
        )
    else:
        active_profile = profile_cfg.get("active")
        if active_profile is None:
            findings.append(
                _finding(
                    PreflightCheckCode.PROFILE_MISSING,
                    PreflightSeverity.ERROR,
                    "profile.active no esta definido.",
                    is_blocking=True,
                )
            )
        elif not is_known_profile_id(active_profile):
            findings.append(
                _finding(
                    PreflightCheckCode.PROFILE_INVALID,
                    PreflightSeverity.ERROR,
                    f"profile.active invalido: '{active_profile}'.",
                    details={"profile_active": active_profile},
                    is_blocking=True,
                )
            )

    for warning in normalize_warnings:
        normalized_warning = warning.lower()
        if "se normalizó mode" in normalized_warning:
            findings.append(
                _finding(
                    PreflightCheckCode.MODE_PROFILE_MISMATCH_CORRECTED,
                    PreflightSeverity.WARNING,
                    "mode fue corregido automaticamente para coincidir con profile.active.",
                    details={"source_warning": warning},
                )
            )
            break

    if not spec.is_valid:
        findings.append(
            _finding(
                PreflightCheckCode.SESSION_SPEC_INVALID,
                PreflightSeverity.ERROR,
                f"SessionSpec invalido: {spec.reason}",
                is_blocking=True,
            )
        )

    if spec.backend is None:
        findings.append(
            _finding(
                PreflightCheckCode.BACKEND_MISSING,
                PreflightSeverity.ERROR,
                "No se pudo determinar el backend esperado para la sesion.",
                is_blocking=True,
            )
        )

    return findings


def collect_transport_checks(
    cfg: dict[str, Any],
    spec: SessionSpec,
) -> list[PreflightFinding]:
    findings: list[PreflightFinding] = []
    if not spec.is_valid:
        return findings

    if spec.mode == "serial":
        serial_cfg = cfg.get("serial")
        issues: list[str] = []
        if not isinstance(serial_cfg, dict):
            issues.append("serial debe ser dict.")
        else:
            baudrate = serial_cfg.get("baudrate")
            flush_ms = serial_cfg.get("flush_ms")
            max_silence_s = serial_cfg.get("max_silence_s")
            port = serial_cfg.get("port")

            if not isinstance(baudrate, int) or baudrate <= 0:
                issues.append("serial.baudrate invalido.")
            if not isinstance(flush_ms, int) or flush_ms < 1:
                issues.append("serial.flush_ms invalido.")
            if not isinstance(max_silence_s, (int, float)) or float(max_silence_s) <= 0:
                issues.append("serial.max_silence_s invalido.")
            if port is not None and not isinstance(port, str):
                issues.append("serial.port invalido.")

        if issues:
            findings.append(
                _finding(
                    PreflightCheckCode.SERIAL_CONFIG_INCOMPLETE,
                    PreflightSeverity.ERROR,
                    "Configuracion serial incompleta o incoherente.",
                    details={"issues": issues},
                    is_blocking=True,
                )
            )

    elif spec.mode == "udp":
        udp_cfg = cfg.get("udp")
        issues = []
        if not isinstance(udp_cfg, dict):
            issues.append("udp debe ser dict.")
        else:
            bind_ip = udp_cfg.get("bind_ip")
            evt_port = udp_cfg.get("evt_port")
            stat_port = udp_cfg.get("stat_port")
            cmd_port = udp_cfg.get("cmd_port")

            if not isinstance(bind_ip, str) or not bind_ip.strip():
                issues.append("udp.bind_ip invalido.")
            for key, value in (
                ("evt_port", evt_port),
                ("stat_port", stat_port),
                ("cmd_port", cmd_port),
            ):
                if not isinstance(value, int) or value < 1 or value > 65535:
                    issues.append(f"udp.{key} invalido.")

        if issues:
            findings.append(
                _finding(
                    PreflightCheckCode.UDP_CONFIG_INCOMPLETE,
                    PreflightSeverity.ERROR,
                    "Configuracion UDP incompleta o incoherente.",
                    details={"issues": issues},
                    is_blocking=True,
                )
            )

    return findings


def collect_midi_checks(raw_cfg: dict[str, Any], effective_cfg: dict[str, Any]) -> list[PreflightFinding]:
    findings: list[PreflightFinding] = []

    raw_midi_cfg = raw_cfg.get("midi")
    raw_outputs = raw_midi_cfg.get("outputs") if isinstance(raw_midi_cfg, dict) else None
    raw_valid, raw_issue = _validate_midi_outputs(raw_outputs)
    if not raw_valid:
        code = (
            PreflightCheckCode.MIDI_OUTPUTS_MISSING
            if raw_outputs is None or (isinstance(raw_outputs, dict) and not raw_outputs)
            else PreflightCheckCode.MIDI_OUTPUTS_INVALID
        )
        findings.append(
            _finding(
                code,
                PreflightSeverity.WARNING,
                "midi.outputs incompleto en config original; se usara configuracion efectiva.",
                details={"issue": raw_issue},
            )
        )

    midi_cfg = effective_cfg.get("midi")
    if not isinstance(midi_cfg, dict):
        findings.append(
            _finding(
                PreflightCheckCode.MIDI_OUTPUTS_INVALID,
                PreflightSeverity.ERROR,
                "Seccion midi invalida en configuracion efectiva.",
                is_blocking=True,
            )
        )
        return findings

    outputs = midi_cfg.get("outputs")
    outputs_valid, outputs_issue = _validate_midi_outputs(outputs)
    if not outputs_valid:
        code = (
            PreflightCheckCode.MIDI_OUTPUTS_MISSING
            if outputs is None or (isinstance(outputs, dict) and not outputs)
            else PreflightCheckCode.MIDI_OUTPUTS_INVALID
        )
        findings.append(
            _finding(
                code,
                PreflightSeverity.ERROR,
                "midi.outputs invalido en configuracion efectiva.",
                details={"issue": outputs_issue},
                is_blocking=True,
            )
        )

    return findings


def collect_logging_checks(raw_cfg: dict[str, Any], effective_cfg: dict[str, Any]) -> list[PreflightFinding]:
    findings: list[PreflightFinding] = []

    raw_logging_cfg = raw_cfg.get("logging")
    if not isinstance(raw_logging_cfg, dict):
        findings.append(
            _finding(
                PreflightCheckCode.LOGGING_CONFIG_INVALID,
                PreflightSeverity.WARNING,
                "Seccion logging ausente o invalida en config original; se aplicaron defaults.",
            )
        )

    logging_cfg = effective_cfg.get("logging")
    if not isinstance(logging_cfg, dict):
        findings.append(
            _finding(
                PreflightCheckCode.LOGGING_CONFIG_INVALID,
                PreflightSeverity.ERROR,
                "Seccion logging invalida en configuracion efectiva.",
                is_blocking=True,
            )
        )
        return findings

    enabled = logging_cfg.get("enabled")
    if not isinstance(enabled, bool):
        findings.append(
            _finding(
                PreflightCheckCode.LOGGING_CONFIG_INVALID,
                PreflightSeverity.ERROR,
                "logging.enabled invalido en configuracion efectiva.",
                is_blocking=True,
            )
        )
        return findings

    if not enabled:
        findings.append(
            _finding(
                PreflightCheckCode.LOGGING_DISABLED,
                PreflightSeverity.INFO,
                "Logging deshabilitado por configuracion.",
            )
        )
        return findings

    folder = logging_cfg.get("folder")
    if not isinstance(folder, str) or not folder.strip():
        findings.append(
            _finding(
                PreflightCheckCode.LOGGING_FOLDER_MISSING,
                PreflightSeverity.WARNING,
                "Logging habilitado, pero logging.folder esta vacio o invalido.",
            )
        )

    return findings


def evaluate_readiness(findings: list[PreflightFinding]) -> ReadinessLevel:
    has_blocking = any(
        finding.is_blocking or finding.severity is PreflightSeverity.ERROR for finding in findings
    )
    if has_blocking:
        return ReadinessLevel.BLOCKED

    has_warning = any(finding.severity is PreflightSeverity.WARNING for finding in findings)
    if has_warning:
        return ReadinessLevel.READY_WITH_WARNINGS

    return ReadinessLevel.READY


def build_preflight_summary(report: PreflightReport) -> str:
    return (
        f"Readiness: {report.readiness.value}; "
        f"blocking={report.blocking_count}; "
        f"warnings={report.warning_count}; "
        f"info={report.info_count}; "
        f"profile={report.profile_id or 'none'}; "
        f"mode={report.derived_mode or 'none'}; "
        f"backend={report.backend_kind or 'none'}; "
        f"can_start={'yes' if report.can_start else 'no'}."
    )


def run_preflight_checks(cfg: dict[str, Any]) -> PreflightReport:
    raw_cfg: dict[str, Any] = cfg if isinstance(cfg, dict) else {}
    effective_cfg, normalize_warnings = validate_and_fix(raw_cfg)
    spec = build_session_request_from_profile(effective_cfg)

    findings: list[PreflightFinding] = []
    findings.extend(collect_profile_checks(raw_cfg, normalize_warnings, spec))
    findings.extend(collect_transport_checks(effective_cfg, spec))
    findings.extend(collect_midi_checks(raw_cfg, effective_cfg))
    findings.extend(collect_logging_checks(raw_cfg, effective_cfg))

    readiness = evaluate_readiness(findings)
    blocking_count = sum(1 for finding in findings if finding.is_blocking)
    warning_count = sum(1 for finding in findings if finding.severity is PreflightSeverity.WARNING)
    info_count = sum(1 for finding in findings if finding.severity is PreflightSeverity.INFO)
    backend_kind = spec.backend.value if spec.backend is not None else None
    can_start = readiness is not ReadinessLevel.BLOCKED and spec.is_valid and backend_kind is not None

    report = PreflightReport(
        readiness=readiness,
        findings=tuple(findings),
        blocking_count=blocking_count,
        warning_count=warning_count,
        info_count=info_count,
        summary="",
        can_start=can_start,
        profile_id=spec.profile_id,
        derived_mode=spec.mode,
        backend_kind=backend_kind,
        session_spec_valid=spec.is_valid,
    )
    return PreflightReport(
        readiness=report.readiness,
        findings=report.findings,
        blocking_count=report.blocking_count,
        warning_count=report.warning_count,
        info_count=report.info_count,
        summary=build_preflight_summary(report),
        can_start=report.can_start,
        profile_id=report.profile_id,
        derived_mode=report.derived_mode,
        backend_kind=report.backend_kind,
        session_spec_valid=report.session_spec_valid,
    )
