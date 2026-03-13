from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import mido


REPO_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.config.config_schema import load_config, save_config
from control_okua.core.midi import MidiRouter


def main() -> int:
    cfg, warnings, config_path = load_config()
    for warning in warnings:
        print(f"[config] {warning}")

    sample_available = ["loopMIDI Port 1 1", "loopMIDI Port 2 2"]
    sample_requested = "loopMIDI Port 1"
    sample_resolved, sample_reason = MidiRouter.resolve_output_name(
        requested=sample_requested,
        available=sample_available,
    )
    print(
        "[smoke] resolver_sample requested="
        f"'{sample_requested}' available={sample_available} -> "
        f"resolved={sample_resolved!r} ({sample_reason})"
    )
    if sample_resolved != "loopMIDI Port 1 1":
        print("[smoke] resolver_sample fallo: se esperaba 'loopMIDI Port 1 1'.")
        return 1

    mido.set_backend("mido.backends.rtmidi")
    available_outputs = mido.get_output_names()
    config_outputs = {}
    if isinstance(cfg.get("midi"), dict):
        config_outputs = cfg["midi"].get("outputs", {})

    print(f"[smoke] available_outputs={available_outputs}")
    print(f"[smoke] config_outputs={config_outputs}")

    if not available_outputs:
        print(
            "[smoke] No hay puertos MIDI de salida disponibles. "
            "Abre loopMIDI y crea 'loopMIDI Port 1'."
        )
        return 1

    router = MidiRouter.from_config(cfg)
    try:
        router.open()
    except Exception as exc:
        print(
            f"[smoke] router.open() fallo: {exc}. "
            f"available_outputs={available_outputs}; config_outputs={config_outputs}"
        )
        return 1

    try:
        resolved_outputs = {str(bus): name for bus, name in router.resolved_outputs().items()}
        print(f"[smoke] resolved_outputs={resolved_outputs}")
        if not resolved_outputs:
            print("[smoke] no hubo resoluciones de salida; no se puede continuar.")
            return 1

        if os.getenv("CKV2_AUTOFIX_OUTPUTS") == "1":
            if not isinstance(cfg.get("midi"), dict):
                cfg["midi"] = {}
            cfg["midi"]["outputs"] = resolved_outputs
            save_config(cfg, config_path)
            print("[smoke] config actualizado con nombres MIDI resueltos.")

        buses = router.opened_buses()
        if not buses:
            print("[midi] no hay buses abiertos despues de open().")
            return 1

        bus = 0 if 0 in buses else buses[0]
        if bus != 0:
            print(f"[midi] bus 0 no abierto; usando bus {bus}.")

        notes = (60, 64, 67, 72)
        for note in notes:
            router.send_note_on(bus=bus, ch=0, note=note, vel=100)
            router.flush()
            time.sleep(0.2)

            router.send_note_off(bus=bus, ch=0, note=note, vel=0)
            router.flush()
            time.sleep(0.05)

        sent = router.flush()
        print(f"[smoke] smoke test finalizado. flush final envio {sent} mensajes.")
        return 0
    finally:
        router.close()


if __name__ == "__main__":
    raise SystemExit(main())
