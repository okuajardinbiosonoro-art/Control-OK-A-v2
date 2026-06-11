from __future__ import annotations

import argparse
import csv
import socket
import sys
import time
from pathlib import Path


DEFAULT_BIND_IP = "0.0.0.0"
DEFAULT_PORT = 5010
DEFAULT_CSV_FIELDNAMES = [
    "node",
    "id",
    "fw",
    "variant",
    "mode",
    "phase",
    "state",
    "fsm",
    "entry_reason",
    "exit_reason",
    "block_reason",
    "t_ms",
    "raw",
    "filt",
    "base",
    "prev",
    "dv",
    "raw_delta",
    "slope",
    "sigma",
    "th_up",
    "th_down",
    "cand",
    "ref",
    "exit",
    "raw_rail",
    "quiet_idle",
    "entry_armed",
    "entry_relaxed",
    "entry_rescue",
    "touch_sign",
    "pending_sign",
    "cal_fast",
    "cal_refine",
    "vmin",
    "vmax",
    "hold_up_ms",
    "hold_down_ms",
    "recovery_ms",
    "energy_age_ms",
    "contact_age_ms",
    "release_age_ms",
    "idle_stable_ms",
    "fsm_age_ms",
    "poss_touch_ms",
    "poss_release_ms",
    "peak_dv",
    "peak_raw",
    "out_req",
    "out_on",
    "out_ok",
    "out_fail",
    "out_age_ms",
    "alive",
    "note",
    "plant_active",
    "plant_state",
    "plant_delta",
    "plant_abs_delta",
    "selected_pin",
    "adc32",
    "adc33",
    "adc34",
    "adc35",
    "adc36",
    "adc39",
]


def parse_diag_line(raw: bytes) -> dict[str, str] | None:
    try:
        text = raw.decode("utf-8", errors="replace").strip()
    except Exception:
        return None
    if not text.startswith("FRUITDIAG"):
        return None

    fields: dict[str, str] = {"_raw": text}
    for token in text.split()[1:]:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        fields[key.strip()] = value.strip()
    return fields


def format_summary(fields: dict[str, str]) -> str:
    node = fields.get("node", "?")
    node_id = fields.get("id", "?")
    fw = fields.get("fw", "")
    phase = fields.get("phase", "?")
    state = fields.get("state", "?")
    fsm = fields.get("fsm", "")
    raw = fields.get("raw", "?")
    filt = fields.get("filt", "?")
    base = fields.get("base", "?")
    dv = fields.get("dv", "?")
    slope = fields.get("slope", "?")
    sigma = fields.get("sigma", "?")
    th_up = fields.get("th_up", "?")
    th_down = fields.get("th_down", "?")
    block = fields.get("block_reason", "")
    entry = fields.get("entry_reason", "")
    armed = fields.get("entry_armed", "")
    rescue = fields.get("entry_rescue", "")
    note = fields.get("note", "")
    out_req = fields.get("out_req", "")
    out_ok = fields.get("out_ok", "")
    prefix = f"{node}#{node_id}"
    if fw:
        prefix = f"{prefix} fw={fw}"
    state_label = f"{phase}/{state}"
    if fsm:
        state_label = f"{state_label} fsm={fsm}"
    suffix_parts: list[str] = []
    if block:
        suffix_parts.append(f"block={block}")
    if entry:
        suffix_parts.append(f"entry={entry}")
    if armed:
        suffix_parts.append(f"armed={armed}")
    if rescue:
        suffix_parts.append(f"rescue={rescue}")
    if note:
        suffix_parts.append(f"note={note}")
    if out_req:
        suffix_parts.append(f"out_req={out_req}")
    if out_ok:
        suffix_parts.append(f"out_ok={out_ok}")
    for scan_key in ("selected_pin", "adc32", "adc33", "adc34", "adc35", "adc36", "adc39"):
        scan_value = fields.get(scan_key, "")
        if scan_value:
            suffix_parts.append(f"{scan_key}={scan_value}")
    suffix = (" " + " ".join(suffix_parts)) if suffix_parts else ""
    return (
        f"{prefix} {state_label} "
        f"raw={raw} filt={filt} base={base} dv={dv} slope={slope} "
        f"sigma={sigma} th_up={th_up} th_down={th_down}{suffix}"
    )


def write_csv_row(writer: csv.DictWriter, fields: dict[str, str]) -> None:
    row = {key: value for key, value in fields.items() if not key.startswith("_")}
    writer.writerow(row)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Receptor UDP para diagnostico de fruta OKUA (texto FRUITDIAG).",
    )
    parser.add_argument("--bind", default=DEFAULT_BIND_IP, help="IP de escucha UDP.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Puerto UDP de diagnostico.")
    parser.add_argument("--csv", type=Path, default=None, help="Archivo CSV opcional para guardar las tramas.")
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Imprime la trama completa en vez del resumen compacto.",
    )
    parser.add_argument(
        "--touch-events",
        action="store_true",
        help="Imprime solo transiciones de toque: inicio y fin.",
    )
    parser.add_argument(
        "--forward-host",
        default="",
        help="Host/IP UDP adicional al que se replica la trama FRUITDIAG.",
    )
    parser.add_argument(
        "--forward-port",
        type=int,
        default=0,
        help="Puerto UDP del receptor remoto al que se replica FRUITDIAG.",
    )
    parser.add_argument(
        "--forward-host-2",
        default="",
        help="Segundo host/IP UDP al que se replica FRUITDIAG.",
    )
    parser.add_argument(
        "--forward-port-2",
        type=int,
        default=0,
        help="Segundo puerto UDP del receptor remoto al que se replica FRUITDIAG.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    bind_ip = str(args.bind).strip() or DEFAULT_BIND_IP
    port = int(args.port)
    forward_host = str(args.forward_host).strip()
    forward_port = int(args.forward_port)
    forward_host_2 = str(args.forward_host_2).strip()
    forward_port_2 = int(args.forward_port_2)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((bind_ip, port))
    sock.settimeout(0.5)

    forward_sock: socket.socket | None = None
    forward_target: tuple[str, int] | None = None
    if forward_host and forward_port > 0:
        forward_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        forward_target = (forward_host, forward_port)
    forward_sock_2: socket.socket | None = None
    forward_target_2: tuple[str, int] | None = None
    if forward_host_2 and forward_port_2 > 0:
        forward_sock_2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        forward_target_2 = (forward_host_2, forward_port_2)

    csv_writer = None
    csv_file = None
    csv_fieldnames: list[str] | None = None
    if args.csv is not None:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        csv_file = args.csv.open("a", newline="", encoding="utf-8")
        csv_writer = None

    print(f"[fruit-diag] escuchando en {bind_ip}:{port}")
    if forward_target is not None:
        print(f"[fruit-diag] replicando tramas a {forward_target[0]}:{forward_target[1]}")
    if forward_target_2 is not None:
        print(f"[fruit-diag] replicando tramas a {forward_target_2[0]}:{forward_target_2[1]}")
    if args.csv is not None:
        print(f"[fruit-diag] guardando CSV en {args.csv}")
    print("[fruit-diag] Ctrl+C para salir")

    last_state_by_node: dict[tuple[str, str, str], str] = {}

    try:
        while True:
            try:
                payload, address = sock.recvfrom(4096)
            except socket.timeout:
                continue

            fields = parse_diag_line(payload)
            if fields is None:
                continue

            if forward_sock is not None and forward_target is not None:
                try:
                    forward_sock.sendto(payload, forward_target)
                except OSError as exc:
                    print(f"[fruit-diag] aviso: no se pudo reenviar FRUITDIAG: {exc}")
                    forward_sock.close()
                    forward_sock = None
                    forward_target = None
            if forward_sock_2 is not None and forward_target_2 is not None:
                try:
                    forward_sock_2.sendto(payload, forward_target_2)
                except OSError as exc:
                    print(f"[fruit-diag] aviso: no se pudo reenviar FRUITDIAG (2): {exc}")
                    forward_sock_2.close()
                    forward_sock_2 = None
                    forward_target_2 = None

            stamp = time.strftime("%H:%M:%S", time.localtime())
            millis = int((time.time() % 1) * 1000)
            source = f"{address[0]}:{address[1]}"
            state = fields.get("state", "?")

            if args.touch_events:
                node = fields.get("node", "?")
                node_id = fields.get("id", "?")
                node_key = (source, node, node_id)
                dv = fields.get("dv", "?")
                raw_v = fields.get("raw", "?")
                filt = fields.get("filt", "?")
                last_state = last_state_by_node.get(node_key)
                if state != last_state:
                    if state == "contact":
                        print(
                            f"[{stamp}.{millis:03d}] {source} {node}#{node_id} TOQUE INICIO "
                            f"raw={raw_v} filt={filt} dv={dv}"
                        )
                    elif last_state == "contact" and state == "idle":
                        print(
                            f"[{stamp}.{millis:03d}] {source} {node}#{node_id} TOQUE FIN "
                            f"raw={raw_v} filt={filt} dv={dv}"
                        )
                    last_state_by_node[node_key] = state
            elif args.raw:
                print(f"[{stamp}.{millis:03d}] {source} {fields['_raw']}")
            else:
                print(f"[{stamp}.{millis:03d}] {source} {format_summary(fields)}")

            if csv_file is not None:
                row = {key: value for key, value in fields.items() if not key.startswith("_")}
                if csv_writer is None:
                    csv_fieldnames = list(DEFAULT_CSV_FIELDNAMES)
                    for key in sorted(row.keys()):
                        if key.startswith("_") or key in csv_fieldnames:
                            continue
                        csv_fieldnames.append(key)
                    csv_writer = csv.DictWriter(csv_file, fieldnames=csv_fieldnames, extrasaction="ignore")
                    if csv_file.tell() == 0:
                        csv_writer.writeheader()
                if csv_writer is not None:
                    csv_writer.writerow(row)
                    csv_file.flush()
    except KeyboardInterrupt:
        print("\n[fruit-diag] detenido por el operador")
        return 0
    finally:
        sock.close()
        if forward_sock is not None:
            forward_sock.close()
        if forward_sock_2 is not None:
            forward_sock_2.close()
        if csv_file is not None:
            csv_file.close()


if __name__ == "__main__":
    raise SystemExit(main())
