from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from control_okua.core.profiles.profile_service import (
    infer_profile_from_config,
    is_known_profile_id,
    resolve_profile_to_mode,
)

DEFAULT_OUTPUTS: dict[str, str] = {
    "0": "loopMIDI Port 1",
    "1": "loopMIDI Port 2",
    "2": "loopMIDI Port 3",
}


def timestamp_tag() -> str:
    return time.strftime("%Y%m%d_%H%M%S", time.localtime())


def get_config_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "config.json"

    repo_root = Path(__file__).resolve().parents[4]
    return repo_root / "config.json"


def default_config() -> dict[str, Any]:
    return {
        "version": 2,
        "mode": None,
        "profile": {
            "active": None,
        },
        "serial": {
            "baudrate": 115200,
            "running_status": True,
            "flush_ms": 5,
            "max_silence_s": 3.0,
            "auto_reconnect": True,
            "port": None,
        },
        "udp": {
            "bind_ip": "0.0.0.0",
            "evt_port": 5005,
            "stat_port": 5006,
            "cmd_port": 5007,
            "rcvbuf_bytes": 262144,
        },
        "midi": {
            "backend": "rtmidi",
            "send_noteoff_on_vel0": True,
            "outputs": DEFAULT_OUTPUTS.copy(),
        },
        "logging": {
            "enabled": True,
            "folder": "logs",
            "format": "jsonl",
            "level": "INFO",
        },
        "ui": {
            "refresh_hz": 10,
        },
        "thresholds": {
            "online_ms": 1500,
            "degraded_ms": 4000,
            "offline_ms": 8000,
        },
    }


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key, base_val in base.items():
        if key in override:
            override_val = override[key]
            if isinstance(base_val, dict) and isinstance(override_val, dict):
                merged[key] = deep_merge(base_val, override_val)
            else:
                merged[key] = override_val
        else:
            merged[key] = base_val
    for key, override_val in override.items():
        if key not in base:
            merged[key] = override_val
    return merged


def detect_version(cfg: dict[str, Any]) -> str:
    if not isinstance(cfg, dict):
        return "unknown"

    if cfg.get("version") == 2:
        return "v2"

    v1_keys = {
        "baudrate",
        "flush_ms",
        "running_status",
        "max_silence_s",
        "midi_outputs_prefix",
        "midi_outputs",
        "com_port",
    }
    if any(key in cfg for key in v1_keys):
        return "v1"
    return "unknown"


def migrate_v1_to_v2(cfg_v1: dict[str, Any]) -> dict[str, Any]:
    cfg = default_config()
    if not isinstance(cfg_v1, dict):
        return cfg

    if "baudrate" in cfg_v1:
        cfg["serial"]["baudrate"] = cfg_v1["baudrate"]
    if "flush_ms" in cfg_v1:
        cfg["serial"]["flush_ms"] = cfg_v1["flush_ms"]
    if "running_status" in cfg_v1:
        cfg["serial"]["running_status"] = cfg_v1["running_status"]
    if "max_silence_s" in cfg_v1:
        cfg["serial"]["max_silence_s"] = cfg_v1["max_silence_s"]
    if isinstance(cfg_v1.get("com_port"), str):
        cfg["serial"]["port"] = cfg_v1["com_port"]

    if cfg_v1.get("mode") in {"serial", "udp"}:
        cfg["mode"] = cfg_v1["mode"]

    return cfg


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _safe_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _safe_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def validate_and_fix(cfg: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    defaults = default_config()
    raw_cfg = cfg if isinstance(cfg, dict) else {}
    candidate = deep_merge(defaults, raw_cfg)
    warnings: list[str] = []

    if candidate.get("version") != 2:
        candidate["version"] = 2
        warnings.append("version corregida a 2.")

    mode_value = candidate.get("mode")
    if mode_value is None:
        candidate["mode"] = None
        warnings.append("mode no definido; requiere seleccion.")
    elif isinstance(mode_value, str) and mode_value in {"serial", "udp"}:
        candidate["mode"] = mode_value
    else:
        candidate["mode"] = None
        warnings.append("mode invalido; requiere seleccion.")

    profile_cfg = candidate.get("profile")
    if not isinstance(profile_cfg, dict):
        candidate["profile"] = defaults["profile"].copy()
        profile_cfg = candidate["profile"]
        warnings.append("profile invalido; se restauro default.")

    active_profile = profile_cfg.get("active")
    if active_profile is None:
        profile_cfg["active"] = infer_profile_from_config(candidate)
    elif not is_known_profile_id(active_profile):
        profile_cfg["active"] = infer_profile_from_config(
            {
                "mode": candidate.get("mode"),
                "profile": {"active": None},
            }
        )
        warnings.append("profile.active invalido; se infirio desde mode o se uso null.")

    resolved_mode = resolve_profile_to_mode(profile_cfg.get("active"))
    if resolved_mode in {"serial", "udp"} and candidate.get("mode") != resolved_mode:
        candidate["mode"] = resolved_mode
        warnings.append(
            f"mode ajustado a '{resolved_mode}' por profile.active='{profile_cfg.get('active')}'."
        )

    serial_cfg = candidate.get("serial")
    if not isinstance(serial_cfg, dict):
        candidate["serial"] = defaults["serial"].copy()
        serial_cfg = candidate["serial"]
        warnings.append("serial invalido; se restauraron defaults.")

    baudrate = _safe_int(serial_cfg.get("baudrate"), defaults["serial"]["baudrate"])
    if baudrate <= 0:
        baudrate = defaults["serial"]["baudrate"]
        warnings.append("serial.baudrate invalido; se restauro default.")
    serial_cfg["baudrate"] = baudrate

    if not _is_bool(serial_cfg.get("running_status")):
        serial_cfg["running_status"] = defaults["serial"]["running_status"]
        warnings.append("serial.running_status invalido; se restauro default.")

    flush_ms = _safe_int(serial_cfg.get("flush_ms"), defaults["serial"]["flush_ms"])
    if flush_ms < 1:
        flush_ms = defaults["serial"]["flush_ms"]
        warnings.append("serial.flush_ms invalido; se restauro default.")
    serial_cfg["flush_ms"] = flush_ms

    max_silence_s = _safe_float(
        serial_cfg.get("max_silence_s"), defaults["serial"]["max_silence_s"]
    )
    if max_silence_s <= 0:
        max_silence_s = defaults["serial"]["max_silence_s"]
        warnings.append("serial.max_silence_s invalido; se restauro default.")
    serial_cfg["max_silence_s"] = max_silence_s

    if not _is_bool(serial_cfg.get("auto_reconnect")):
        serial_cfg["auto_reconnect"] = defaults["serial"]["auto_reconnect"]
        warnings.append("serial.auto_reconnect invalido; se restauro default.")

    serial_port = serial_cfg.get("port")
    if serial_port is not None and not isinstance(serial_port, str):
        serial_cfg["port"] = None
        warnings.append("serial.port invalido; se uso null.")

    udp_cfg = candidate.get("udp")
    if not isinstance(udp_cfg, dict):
        candidate["udp"] = defaults["udp"].copy()
        udp_cfg = candidate["udp"]
        warnings.append("udp invalido; se restauraron defaults.")

    if not isinstance(udp_cfg.get("bind_ip"), str):
        udp_cfg["bind_ip"] = defaults["udp"]["bind_ip"]
        warnings.append("udp.bind_ip invalido; se restauro default.")

    for port_key in ("evt_port", "stat_port", "cmd_port"):
        port_val = _safe_int(udp_cfg.get(port_key), defaults["udp"][port_key])
        if port_val < 1 or port_val > 65535:
            port_val = defaults["udp"][port_key]
            warnings.append(f"udp.{port_key} invalido; se restauro default.")
        udp_cfg[port_key] = port_val

    rcvbuf = _safe_int(udp_cfg.get("rcvbuf_bytes"), defaults["udp"]["rcvbuf_bytes"])
    if rcvbuf < 1:
        rcvbuf = defaults["udp"]["rcvbuf_bytes"]
        warnings.append("udp.rcvbuf_bytes invalido; se restauro default.")
    udp_cfg["rcvbuf_bytes"] = rcvbuf

    midi_cfg = candidate.get("midi")
    raw_midi_cfg = raw_cfg.get("midi")
    if not isinstance(raw_midi_cfg, dict):
        candidate["midi"] = deep_merge(defaults["midi"], {})
        midi_cfg = candidate["midi"]
        warnings.append("midi invalido; se restauraron defaults.")
        raw_midi_cfg = {}
    elif not isinstance(midi_cfg, dict):
        candidate["midi"] = deep_merge(defaults["midi"], raw_midi_cfg)
        midi_cfg = candidate["midi"]
        warnings.append("midi invalido; se restauraron defaults.")

    if not isinstance(midi_cfg.get("backend"), str):
        midi_cfg["backend"] = defaults["midi"]["backend"]
        warnings.append("midi.backend invalido; se restauro default.")

    if not _is_bool(midi_cfg.get("send_noteoff_on_vel0")):
        midi_cfg["send_noteoff_on_vel0"] = defaults["midi"]["send_noteoff_on_vel0"]
        warnings.append("midi.send_noteoff_on_vel0 invalido; se restauro default.")

    raw_outputs = raw_midi_cfg.get("outputs")
    if not isinstance(raw_outputs, dict):
        midi_cfg["outputs"] = DEFAULT_OUTPUTS.copy()
        warnings.append("midi.outputs invalido o ausente; se restauraron defaults.")
    else:
        filtered_outputs: dict[str, str] = {}
        invalid_entries = 0
        for key, value in raw_outputs.items():
            if isinstance(key, bool):
                invalid_entries += 1
                continue
            try:
                bus_id = int(key)
            except (TypeError, ValueError):
                invalid_entries += 1
                continue
            if bus_id < 0 or bus_id > 255:
                invalid_entries += 1
                continue
            if not isinstance(value, str) or not value.strip():
                invalid_entries += 1
                continue

            filtered_outputs[str(bus_id)] = value

        if invalid_entries:
            warnings.append("midi.outputs tenia entradas invalidas; fueron descartadas.")

        if not filtered_outputs:
            midi_cfg["outputs"] = DEFAULT_OUTPUTS.copy()
            warnings.append("midi.outputs vacio; se restauraron defaults.")
        else:
            midi_cfg["outputs"] = filtered_outputs

    log_cfg = candidate.get("logging")
    if not isinstance(log_cfg, dict):
        candidate["logging"] = defaults["logging"].copy()
        log_cfg = candidate["logging"]
        warnings.append("logging invalido; se restauraron defaults.")

    if not _is_bool(log_cfg.get("enabled")):
        log_cfg["enabled"] = defaults["logging"]["enabled"]
        warnings.append("logging.enabled invalido; se restauro default.")

    if not isinstance(log_cfg.get("folder"), str):
        log_cfg["folder"] = defaults["logging"]["folder"]
        warnings.append("logging.folder invalido; se restauro default.")

    if log_cfg.get("format") not in {"jsonl", "csv"}:
        log_cfg["format"] = defaults["logging"]["format"]
        warnings.append("logging.format invalido; se restauro default.")

    if not isinstance(log_cfg.get("level"), str):
        log_cfg["level"] = defaults["logging"]["level"]
        warnings.append("logging.level invalido; se restauro default.")

    ui_cfg = candidate.get("ui")
    if not isinstance(ui_cfg, dict):
        candidate["ui"] = defaults["ui"].copy()
        ui_cfg = candidate["ui"]
        warnings.append("ui invalido; se restauraron defaults.")

    refresh_hz = _safe_int(ui_cfg.get("refresh_hz"), defaults["ui"]["refresh_hz"])
    if refresh_hz < 1:
        refresh_hz = defaults["ui"]["refresh_hz"]
        warnings.append("ui.refresh_hz invalido; se restauro default.")
    ui_cfg["refresh_hz"] = refresh_hz

    thresholds_cfg = candidate.get("thresholds")
    if not isinstance(thresholds_cfg, dict):
        candidate["thresholds"] = defaults["thresholds"].copy()
        thresholds_cfg = candidate["thresholds"]
        warnings.append("thresholds invalido; se restauraron defaults.")

    online_ms = _safe_int(
        thresholds_cfg.get("online_ms"), defaults["thresholds"]["online_ms"]
    )
    degraded_ms = _safe_int(
        thresholds_cfg.get("degraded_ms"), defaults["thresholds"]["degraded_ms"]
    )
    offline_ms = _safe_int(
        thresholds_cfg.get("offline_ms"), defaults["thresholds"]["offline_ms"]
    )

    if not (online_ms < degraded_ms < offline_ms):
        candidate["thresholds"] = defaults["thresholds"].copy()
        warnings.append(
            "thresholds invalidos (online<degraded<offline); se restauraron defaults."
        )
    else:
        thresholds_cfg["online_ms"] = online_ms
        thresholds_cfg["degraded_ms"] = degraded_ms
        thresholds_cfg["offline_ms"] = offline_ms

    return candidate, warnings


def save_config(cfg: dict[str, Any], path: Path | None = None) -> None:
    target = path or get_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fobj:
        json.dump(cfg, fobj, indent=2, ensure_ascii=False, sort_keys=False)
        fobj.write("\n")


def _build_backup_path(path: Path, prefix: str) -> Path:
    base_tag = timestamp_tag()
    candidate = path.with_name(f"{prefix}.{base_tag}.json")
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{prefix}.{base_tag}_{counter:02d}.json")
        counter += 1
    return candidate


def load_config() -> tuple[dict[str, Any], list[str], Path]:
    warnings: list[str] = []
    cfg_path = get_config_path()

    if not cfg_path.exists():
        cfg = default_config()
        save_config(cfg, cfg_path)
        warnings.append(f"config no existia; se creo v2 en '{cfg_path}'.")
        return cfg, warnings, cfg_path

    try:
        with cfg_path.open("r", encoding="utf-8") as fobj:
            raw_cfg = json.load(fobj)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        corrupt_backup = _build_backup_path(cfg_path, "config.corrupt")
        try:
            cfg_path.replace(corrupt_backup)
            warnings.append(
                f"config corrupto movido a '{corrupt_backup.name}' ({exc.__class__.__name__})."
            )
        except OSError as move_exc:
            warnings.append(
                "config corrupto detectado, pero no se pudo renombrar a backup "
                f"({move_exc.__class__.__name__})."
            )
        cfg = default_config()
        save_config(cfg, cfg_path)
        warnings.append("se creo config v2 por defecto.")
        return cfg, warnings, cfg_path

    if not isinstance(raw_cfg, dict):
        raw_cfg = {}
        warnings.append("config con raiz no-dict; se trato como v1/unknown.")

    version = detect_version(raw_cfg)

    if version == "v2":
        fixed_cfg, fix_warnings = validate_and_fix(raw_cfg)
        warnings.extend(fix_warnings)
        if fixed_cfg != raw_cfg:
            save_config(fixed_cfg, cfg_path)
            warnings.append("config v2 actualizado y guardado (merge/fixes).")
        return fixed_cfg, warnings, cfg_path

    v1_backup = _build_backup_path(cfg_path, "config.v1.backup")
    try:
        v1_backup.write_text(cfg_path.read_text(encoding="utf-8"), encoding="utf-8")
        warnings.append(f"backup v1 creado en '{v1_backup.name}'.")
    except OSError as exc:
        warnings.append(
            f"no se pudo crear backup v1 ({exc.__class__.__name__}); se continua migracion."
        )

    migrated_cfg = migrate_v1_to_v2(raw_cfg)
    fixed_cfg, fix_warnings = validate_and_fix(migrated_cfg)
    warnings.extend(fix_warnings)
    if version == "v1":
        warnings.append("config migrado de v1 a v2.")
    else:
        warnings.append("config de version desconocida migrado a v2.")

    save_config(fixed_cfg, cfg_path)
    return fixed_cfg, warnings, cfg_path
