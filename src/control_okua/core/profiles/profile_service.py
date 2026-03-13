from __future__ import annotations

from copy import deepcopy
from typing import Any

from control_okua.core.profiles.profile_schema import (
    PROFILE_DEFINITIONS,
    PROFILE_IDS,
    ProfileDefinition,
)


def list_available_profiles() -> list[ProfileDefinition]:
    return list(PROFILE_DEFINITIONS)


def get_profile_definition(profile_id: str | None) -> ProfileDefinition | None:
    if not isinstance(profile_id, str):
        return None

    for definition in PROFILE_DEFINITIONS:
        if definition.profile_id == profile_id:
            return definition
    return None


def is_known_profile_id(profile_id: str | None) -> bool:
    return isinstance(profile_id, str) and profile_id in PROFILE_IDS


def resolve_profile_to_mode(profile_id: str | None) -> str | None:
    definition = get_profile_definition(profile_id)
    if definition is None:
        return None
    return definition.mode


def build_profile_ui_summary(profile_id: str | None, cfg: dict[str, Any]) -> dict[str, str]:
    definition = get_profile_definition(profile_id)
    cfg_mode = cfg.get("mode")
    cfg_mode_text = cfg_mode if isinstance(cfg_mode, str) else "no definido"

    if definition is None:
        return {
            "profile_id": str(profile_id),
            "short_name": "Perfil no definido",
            "description": "No hay un perfil operativo válido seleccionado.",
            "mode": "No disponible aún",
            "usage_level": "No definido",
            "operation_summary": "Seleccione un perfil para continuar.",
            "effective_mode": cfg_mode_text,
        }

    return {
        "profile_id": definition.profile_id,
        "short_name": definition.short_name,
        "description": definition.description,
        "mode": definition.mode,
        "usage_level": definition.usage_level,
        "operation_summary": definition.operation_summary,
        "effective_mode": definition.mode,
    }


def infer_profile_from_config(cfg: dict[str, Any]) -> str | None:
    if not isinstance(cfg, dict):
        return None

    profile_cfg = cfg.get("profile")
    if isinstance(profile_cfg, dict):
        active_profile = profile_cfg.get("active")
        if is_known_profile_id(active_profile):
            return active_profile

    mode = cfg.get("mode")
    if mode == "serial":
        return "serial_local"
    if mode == "udp":
        return "udp_jardin"

    return None


def set_active_profile(cfg: dict[str, Any], profile_id: str) -> dict[str, Any]:
    if not isinstance(cfg, dict):
        raise TypeError("cfg debe ser dict")

    if not is_known_profile_id(profile_id):
        raise ValueError(f"profile_id desconocido: {profile_id}")

    updated_cfg = deepcopy(cfg)
    profile_cfg = updated_cfg.get("profile")
    if not isinstance(profile_cfg, dict):
        profile_cfg = {}
        updated_cfg["profile"] = profile_cfg

    profile_cfg["active"] = profile_id

    resolved_mode = resolve_profile_to_mode(profile_id)
    if resolved_mode in {"serial", "udp"}:
        updated_cfg["mode"] = resolved_mode

    return updated_cfg
