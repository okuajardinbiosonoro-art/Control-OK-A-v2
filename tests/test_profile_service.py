from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.profiles.profile_service import (  # noqa: E402
    build_profile_ui_summary,
    infer_profile_from_config,
    list_available_profiles,
    resolve_profile_to_mode,
    set_active_profile,
)
from control_okua.core.config.config_schema import validate_and_fix  # noqa: E402


def test_list_available_profiles_contains_required_ids() -> None:
    profile_ids = {profile.profile_id for profile in list_available_profiles()}
    assert {"serial_local", "udp_jardin", "lab_sim"}.issubset(profile_ids)


def test_resolve_serial_local_profile_mode() -> None:
    assert resolve_profile_to_mode("serial_local") == "serial"


def test_resolve_udp_jardin_profile_mode() -> None:
    assert resolve_profile_to_mode("udp_jardin") == "udp"


def test_set_active_profile_persists_profile_id() -> None:
    cfg = {"version": 2, "mode": None}
    updated_cfg = set_active_profile(cfg, "serial_local")

    assert updated_cfg["profile"]["active"] == "serial_local"
    assert updated_cfg["mode"] == "serial"
    assert "profile" not in cfg


def test_infer_profile_from_config_without_profile_section() -> None:
    cfg = {"version": 2, "mode": "udp"}
    inferred = infer_profile_from_config(cfg)
    assert inferred == "udp_jardin"


def test_infer_profile_prefers_valid_explicit_active_profile() -> None:
    cfg = {
        "version": 2,
        "mode": "serial",
        "profile": {"active": "lab_sim"},
    }
    inferred = infer_profile_from_config(cfg)
    assert inferred == "lab_sim"


def test_build_profile_ui_summary_for_lab_sim() -> None:
    summary = build_profile_ui_summary("lab_sim", {"mode": "udp"})

    assert summary["short_name"] == "LAB / simulación"
    assert summary["mode"] == "udp"
    assert "laboratorio" in summary["operation_summary"].lower()


def test_build_profile_ui_summary_for_unknown_profile() -> None:
    summary = build_profile_ui_summary("invalid_profile", {"mode": "serial"})

    assert summary["short_name"] == "Perfil no definido"
    assert summary["effective_mode"] == "serial"


def test_validate_and_fix_keeps_profile_none_when_missing_section() -> None:
    cfg = {"version": 2, "mode": "serial"}
    fixed_cfg, _warnings = validate_and_fix(cfg)

    assert fixed_cfg["profile"]["active"] is None
    assert fixed_cfg["mode"] == "serial"


def test_validate_and_fix_aligns_mode_from_profile() -> None:
    cfg = {
        "version": 2,
        "mode": "serial",
        "profile": {"active": "udp_jardin"},
    }
    fixed_cfg, warnings = validate_and_fix(cfg)

    assert fixed_cfg["mode"] == "udp"
    assert any("mode ajustado" in warning for warning in warnings)
