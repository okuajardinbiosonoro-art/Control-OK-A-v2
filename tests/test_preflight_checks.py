from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.config.config_schema import default_config  # noqa: E402
from control_okua.core.preflight import (  # noqa: E402
    PreflightCheckCode,
    PreflightSeverity,
    ReadinessLevel,
    run_preflight_checks,
)


def _base_cfg(profile_id: str, mode: str) -> dict[str, object]:
    cfg = default_config()
    cfg["profile"]["active"] = profile_id
    cfg["mode"] = mode
    return cfg


def _get_finding(report, code: PreflightCheckCode):
    for finding in report.findings:
        if finding.code is code:
            return finding
    return None


def test_serial_local_valid_config_reports_ready() -> None:
    report = run_preflight_checks(_base_cfg("serial_local", "serial"))

    assert report.readiness is ReadinessLevel.READY
    assert report.can_start is True
    assert report.profile_id == "serial_local"
    assert report.derived_mode == "serial"
    assert report.backend_kind == "serial"
    assert report.blocking_count == 0


def test_udp_jardin_valid_config_reports_ready() -> None:
    report = run_preflight_checks(_base_cfg("udp_jardin", "udp"))

    assert report.readiness is ReadinessLevel.READY
    assert report.can_start is True
    assert report.profile_id == "udp_jardin"
    assert report.derived_mode == "udp"
    assert report.backend_kind == "udp"


def test_lab_sim_valid_config_is_not_blocked() -> None:
    report = run_preflight_checks(_base_cfg("lab_sim", "udp"))

    assert report.readiness in {ReadinessLevel.READY, ReadinessLevel.READY_WITH_WARNINGS}
    assert report.profile_id == "lab_sim"
    assert report.backend_kind == "lab"
    assert report.blocking_count == 0
    assert report.can_start is True

def test_missing_active_profile_blocks_readiness() -> None:
    cfg = _base_cfg("serial_local", "serial")
    cfg["profile"]["active"] = None
    report = run_preflight_checks(cfg)

    finding = _get_finding(report, PreflightCheckCode.PROFILE_MISSING)
    assert report.readiness is ReadinessLevel.BLOCKED
    assert report.can_start is False
    assert finding is not None
    assert finding.is_blocking is True


def test_invalid_session_spec_blocks_readiness() -> None:
    cfg = default_config()
    cfg["profile"]["active"] = None
    cfg["mode"] = "invalid_mode"
    report = run_preflight_checks(cfg)

    finding = _get_finding(report, PreflightCheckCode.SESSION_SPEC_INVALID)
    assert report.readiness is ReadinessLevel.BLOCKED
    assert report.session_spec_valid is False
    assert finding is not None
    assert finding.is_blocking is True


def test_midi_outputs_empty_creates_stable_finding() -> None:
    cfg = _base_cfg("serial_local", "serial")
    cfg["midi"]["outputs"] = {}
    report = run_preflight_checks(cfg)

    missing_finding = _get_finding(report, PreflightCheckCode.MIDI_OUTPUTS_MISSING)
    invalid_finding = _get_finding(report, PreflightCheckCode.MIDI_OUTPUTS_INVALID)
    assert report.readiness is ReadinessLevel.READY_WITH_WARNINGS
    assert (missing_finding is not None) or (invalid_finding is not None)


def test_logging_disabled_is_warning_and_does_not_block() -> None:
    cfg = _base_cfg("serial_local", "serial")
    cfg["logging"]["enabled"] = False
    report = run_preflight_checks(cfg)

    finding = _get_finding(report, PreflightCheckCode.LOGGING_DISABLED)
    assert report.readiness is ReadinessLevel.READY
    assert report.can_start is True
    assert finding is not None
    assert finding.severity is PreflightSeverity.INFO
    assert finding.is_blocking is False


def test_can_start_reflects_readiness() -> None:
    ready_report = run_preflight_checks(_base_cfg("serial_local", "serial"))
    blocked_cfg = _base_cfg("serial_local", "serial")
    blocked_cfg["profile"]["active"] = None
    blocked_report = run_preflight_checks(blocked_cfg)

    assert ready_report.can_start is True
    assert blocked_report.can_start is False


def test_summary_is_legible_and_stable() -> None:
    report = run_preflight_checks(_base_cfg("udp_jardin", "udp"))

    assert report.summary.startswith("Readiness: ready;")
    assert "blocking=0" in report.summary
    assert "warnings=0" in report.summary
    assert "can_start=yes" in report.summary


def test_stable_codes_and_severities_for_primary_findings() -> None:
    cfg = _base_cfg("serial_local", "serial")
    cfg["profile"]["active"] = None
    cfg["logging"]["enabled"] = False
    report = run_preflight_checks(cfg)

    profile_finding = _get_finding(report, PreflightCheckCode.PROFILE_MISSING)
    logging_finding = _get_finding(report, PreflightCheckCode.LOGGING_DISABLED)

    assert profile_finding is not None
    assert profile_finding.severity is PreflightSeverity.ERROR
    assert profile_finding.is_blocking is True

    assert logging_finding is not None
    assert logging_finding.severity is PreflightSeverity.INFO
    assert logging_finding.is_blocking is False
