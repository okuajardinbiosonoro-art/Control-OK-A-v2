from __future__ import annotations

from typing import Any


def _mode_label(cfg: dict[str, Any]) -> str:
    mode_value = cfg.get("mode")
    if mode_value == "serial":
        return "Serial"
    if mode_value == "udp":
        return "Ethernet/UDP"
    return "No seleccionado"


def build_mode_summary(cfg: dict[str, Any]) -> str:
    return f"Modo actual: {_mode_label(cfg)}"


def build_transport_summary(cfg: dict[str, Any]) -> str:
    mode_value = cfg.get("mode")
    if mode_value == "serial":
        serial_cfg = cfg.get("serial") if isinstance(cfg.get("serial"), dict) else {}
        baudrate = serial_cfg.get("baudrate", "-")
        port = serial_cfg.get("port")
        port_text = port if isinstance(port, str) and port.strip() else "sin puerto asignado"
        return f"Transporte configurado: Serial ({port_text}, {baudrate} baudios)"

    if mode_value == "udp":
        udp_cfg = cfg.get("udp") if isinstance(cfg.get("udp"), dict) else {}
        bind_ip = udp_cfg.get("bind_ip", "0.0.0.0")
        evt_port = udp_cfg.get("evt_port", "-")
        stat_port = udp_cfg.get("stat_port", "-")
        cmd_port = udp_cfg.get("cmd_port", "-")
        return (
            "Transporte configurado: "
            f"UDP ({bind_ip} | evt:{evt_port} stat:{stat_port} cmd:{cmd_port})"
        )

    return "Transporte configurado: No disponible aún"


def build_midi_summary(cfg: dict[str, Any]) -> str:
    midi_cfg = cfg.get("midi") if isinstance(cfg.get("midi"), dict) else {}
    outputs = midi_cfg.get("outputs")
    backend = midi_cfg.get("backend")

    buses = 0
    if isinstance(outputs, dict):
        buses = len(outputs)

    backend_text = str(backend) if isinstance(backend, str) and backend.strip() else "desconocido"
    if buses <= 0:
        return f"MIDI configurado: sin buses definidos (backend: {backend_text})"

    bus_word = "bus" if buses == 1 else "buses"
    return f"MIDI configurado: {buses} {bus_word} (backend: {backend_text})"


def build_logging_summary(cfg: dict[str, Any]) -> str:
    logging_cfg = cfg.get("logging") if isinstance(cfg.get("logging"), dict) else {}
    enabled = logging_cfg.get("enabled")

    if isinstance(enabled, bool):
        if enabled:
            return "Logging: habilitado"
        return "Logging: deshabilitado"

    return "Logging: No disponible aún"


def build_general_status_summary(cfg: dict[str, Any], warnings: list[str] | None) -> str:
    mode_value = cfg.get("mode")
    warnings_count = len(warnings or [])

    if warnings_count > 0:
        return (
            "Estado general: aplicación lista con advertencias "
            f"({warnings_count}) / sesión no iniciada"
        )

    if mode_value not in {"serial", "udp"}:
        return "Estado general: modo pendiente / sesión no iniciada"

    return "Estado general: aplicación lista / sesión no iniciada"
