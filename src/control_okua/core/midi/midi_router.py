from __future__ import annotations

from collections import deque
from collections.abc import Sequence
import re
import threading
import time
from typing import Any

import mido

DEFAULT_OUTPUTS: dict[str, str] = {
    "0": "loopMIDI Port 1",
    "1": "loopMIDI Port 2",
    "2": "loopMIDI Port 3",
}


class MidiRouter:
    def __init__(
        self,
        outputs: dict[int, str],
        flush_ms: int = 5,
        backend: str = "rtmidi",
        send_noteoff_on_vel0: bool = True,
        strict_ports: bool = False,
    ) -> None:
        self.outputs = dict(outputs)
        self.flush_ms = max(1, int(flush_ms))
        self.backend = backend
        self.send_noteoff_on_vel0 = bool(send_noteoff_on_vel0)
        self.strict_ports = bool(strict_ports)

        self._ports: dict[int, Any] = {}
        self._resolved_outputs: dict[int, str] = {}
        self._queue: deque[tuple[int, mido.Message]] = deque()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @staticmethod
    def from_config(cfg: dict[str, Any]) -> "MidiRouter":
        midi_cfg = cfg.get("midi") if isinstance(cfg.get("midi"), dict) else {}
        serial_cfg = cfg.get("serial") if isinstance(cfg.get("serial"), dict) else {}

        outputs_raw = midi_cfg.get("outputs")
        if not isinstance(outputs_raw, dict) or not outputs_raw:
            print("[midi] warning: cfg.midi.outputs vacio; usando defaults")
            outputs_raw = DEFAULT_OUTPUTS.copy()

        outputs: dict[int, str] = {}
        for raw_bus, raw_port_name in outputs_raw.items():
            if isinstance(raw_bus, bool):
                print(f"[midi] warning: bus invalido '{raw_bus}' ignorado.")
                continue

            try:
                bus = int(raw_bus)
            except (TypeError, ValueError):
                print(f"[midi] warning: bus invalido '{raw_bus}' ignorado.")
                continue

            if bus < 0 or bus > 255:
                print(f"[midi] warning: bus fuera de rango '{bus}' ignorado.")
                continue

            if not isinstance(raw_port_name, str) or not raw_port_name.strip():
                print(f"[midi] warning: puerto invalido para bus {bus}; ignorado.")
                continue

            outputs[bus] = raw_port_name

        if not outputs:
            print("[midi] warning: cfg.midi.outputs vacio; usando defaults")
            outputs = {int(bus): name for bus, name in DEFAULT_OUTPUTS.items()}

        backend = midi_cfg.get("backend", "rtmidi")
        if not isinstance(backend, str) or not backend.strip():
            backend = "rtmidi"

        send_noteoff_on_vel0 = midi_cfg.get("send_noteoff_on_vel0", True)
        if not isinstance(send_noteoff_on_vel0, bool):
            send_noteoff_on_vel0 = True

        flush_candidate = midi_cfg.get("flush_ms")
        if flush_candidate is None:
            flush_candidate = serial_cfg.get("flush_ms", 5)
        try:
            flush_ms = int(flush_candidate)
        except (TypeError, ValueError):
            flush_ms = 5
        if flush_ms < 1:
            flush_ms = 1

        strict_ports = midi_cfg.get("strict_ports", False)
        if not isinstance(strict_ports, bool):
            strict_ports = False

        return MidiRouter(
            outputs=outputs,
            flush_ms=flush_ms,
            backend=backend,
            send_noteoff_on_vel0=send_noteoff_on_vel0,
            strict_ports=strict_ports,
        )

    def open(self) -> None:
        if self._ports:
            return

        backend_label = self.backend
        if self.backend == "rtmidi":
            mido.set_backend("mido.backends.rtmidi")
            backend_label = "rtmidi"
        elif self.backend:
            mido.set_backend(self.backend)
            backend_label = self.backend

        available_outputs = mido.get_output_names()
        output_mapping = {str(bus): name for bus, name in sorted(self.outputs.items())}
        print(f"[midi] backend={backend_label}")
        print(f"[midi] outputs={output_mapping}")
        print(f"[midi] available_outputs={available_outputs}")
        self._resolved_outputs = {}

        for bus, requested_name in sorted(self.outputs.items()):
            resolved_name, reason = self.resolve_output_name(
                requested=requested_name,
                available=available_outputs,
            )
            if resolved_name is None:
                msg = (
                    f"[midi] resolve bus {bus}: '{requested_name}' -> <none> ({reason}). "
                    f"available_outputs={available_outputs}"
                )
                if self.strict_ports:
                    raise RuntimeError(msg)
                print(msg)
                continue

            print(
                f"[midi] resolve bus {bus}: '{requested_name}' -> "
                f"'{resolved_name}' ({reason})"
            )
            try:
                port = mido.open_output(resolved_name)
            except Exception as exc:
                msg = (
                    f"[midi] no se pudo abrir bus {bus} "
                    f"(requested='{requested_name}', resolved='{resolved_name}'): {exc}. "
                    "Compara con mido.get_output_names()."
                )
                if self.strict_ports:
                    raise RuntimeError(msg) from exc
                print(msg)
                continue

            self._ports[bus] = port
            self._resolved_outputs[bus] = resolved_name
            print(f"[midi] bus {bus} abierto -> {resolved_name}")

        if not self._ports:
            raise RuntimeError(
                "No se pudo abrir ningun puerto MIDI. Verifica loopMIDI y nombres de puertos."
            )

        self.start()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self) -> None:
        period_s = self.flush_ms / 1000.0
        while not self._stop_event.wait(period_s):
            try:
                self.flush()
            except Exception as exc:
                print(f"[midi] warning: error en flush periodico: {exc}")

    def close(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

        try:
            self.flush()
        except Exception as exc:
            print(f"[midi] warning: flush final fallo: {exc}")

        for bus, port in list(self._ports.items()):
            try:
                port.close()
            except Exception as exc:
                print(f"[midi] warning: no se pudo cerrar bus {bus}: {exc}")
            finally:
                self._ports.pop(bus, None)
                self._resolved_outputs.pop(bus, None)

    def enqueue(self, bus: int, msg: mido.Message) -> None:
        if bus not in self._ports:
            print(f"[midi] warning: bus {bus} no abierto; mensaje descartado.")
            return

        with self._lock:
            self._queue.append((bus, msg))

    def flush(self) -> int:
        with self._lock:
            if not self._queue:
                return 0
            pending = list(self._queue)
            self._queue.clear()

        sent = 0
        for bus, msg in pending:
            port = self._ports.get(bus)
            if port is None:
                print(f"[midi] warning: bus {bus} no abierto durante flush.")
                continue
            try:
                port.send(msg)
                sent += 1
            except Exception as exc:
                print(f"[midi] warning: error enviando en bus {bus}: {exc}")
        return sent

    def send_note_on(self, bus: int, ch: int, note: int, vel: int) -> None:
        self._validate_note_msg(ch, note, vel)
        if vel == 0 and self.send_noteoff_on_vel0:
            self.send_note_off(bus=bus, ch=ch, note=note, vel=0)
            return

        msg = mido.Message("note_on", channel=ch, note=note, velocity=vel)
        self.enqueue(bus, msg)

    def send_note_off(self, bus: int, ch: int, note: int, vel: int = 0) -> None:
        self._validate_note_msg(ch, note, vel)
        msg = mido.Message("note_off", channel=ch, note=note, velocity=vel)
        self.enqueue(bus, msg)

    def send_raw_midi(self, bus: int, data: bytes | Sequence[int]) -> None:
        if isinstance(data, bytes):
            payload = list(data)
        else:
            payload = [int(v) for v in data]

        if not payload:
            raise ValueError("data MIDI vacio.")
        for value in payload:
            if value < 0 or value > 255:
                raise ValueError(f"byte MIDI fuera de rango: {value}")

        msg = mido.Message.from_bytes(payload)
        self.enqueue(bus, msg)

    def panic_all_notes_off(self) -> None:
        for bus in self.opened_buses():
            for ch in range(16):
                msg = mido.Message(
                    "control_change", channel=ch, control=123, value=0
                )
                self.enqueue(bus, msg)

    def opened_buses(self) -> list[int]:
        return sorted(self._ports.keys())

    def resolved_outputs(self) -> dict[int, str]:
        return dict(self._resolved_outputs)

    @staticmethod
    def _parse_trailing_number(value: str) -> int | None:
        match = re.search(r"(\d+)\s*$", value)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    @staticmethod
    def _best_prefix_candidate(candidates: list[str]) -> str:
        if not candidates:
            raise ValueError("candidates vacio.")

        trailing_numbers = [
            MidiRouter._parse_trailing_number(candidate) for candidate in candidates
        ]
        if all(number is not None for number in trailing_numbers):
            numbered_candidates = [
                (
                    int(number) if number is not None else 10**9,
                    len(candidate),
                    candidate.casefold(),
                    candidate,
                )
                for candidate, number in zip(candidates, trailing_numbers)
            ]
            numbered_candidates.sort()
            return numbered_candidates[0][3]

        plain_candidates = sorted(candidates, key=lambda item: (len(item), item.casefold()))
        return plain_candidates[0]

    @staticmethod
    def resolve_output_name(requested: str, available: list[str]) -> tuple[str | None, str]:
        if requested in available:
            return requested, "exact"

        requested_cf = requested.casefold()
        casefold_matches = [
            candidate for candidate in available if candidate.casefold() == requested_cf
        ]
        if len(casefold_matches) == 1:
            return casefold_matches[0], "casefold"
        if len(casefold_matches) > 1:
            return MidiRouter._best_prefix_candidate(casefold_matches), "prefix_best"

        prefix_matches = [
            candidate
            for candidate in available
            if candidate.casefold().startswith(requested_cf)
        ]
        if not prefix_matches:
            return None, "none"
        if len(prefix_matches) == 1:
            return prefix_matches[0], "prefix_unique"
        return MidiRouter._best_prefix_candidate(prefix_matches), "prefix_best"

    @staticmethod
    def _validate_note_msg(ch: int, note: int, vel: int) -> None:
        if ch < 0 or ch > 15:
            raise ValueError(f"canal fuera de rango (0..15): {ch}")
        if note < 0 or note > 127:
            raise ValueError(f"nota fuera de rango (0..127): {note}")
        if vel < 0 or vel > 127:
            raise ValueError(f"velocidad fuera de rango (0..127): {vel}")
