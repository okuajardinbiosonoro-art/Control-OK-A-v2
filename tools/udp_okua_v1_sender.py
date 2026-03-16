from __future__ import annotations

import argparse
import socket
import struct
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


REPO_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.udp import (  # noqa: E402
    OKUA_EVT_PACKET_SIZE,
    OKUA_MAGIC,
    OKUA_STAT_PACKET_SIZE,
    OKUA_VERSION,
    OkuaPacketType,
)


_EVT_STRUCT = struct.Struct("<HBBHHBBBBIbB2s")
_STAT_STRUCT = struct.Struct("<HBBHHIbBHHIBBB3s")


class DatagramSocketLike(Protocol):
    def sendto(self, data: bytes, address: tuple[str, int]) -> int:
        ...

    def close(self) -> None:
        ...


@dataclass(frozen=True)
class UdpSendStats:
    evt_sent: int
    stat_sent: int


def build_okua_evt_packet(
    *,
    node_id: int,
    seq: int,
    midi_bus: int = 0,
    midi_ch: int = 0,
    note: int = 60,
    vel: int = 100,
    ts_ms: int = 0,
    rssi_dbm: int = -50,
    flags: int = 0,
    rsv: bytes = b"\x00\x00",
) -> bytes:
    packet = _EVT_STRUCT.pack(
        OKUA_MAGIC,
        OKUA_VERSION,
        OkuaPacketType.EVT,
        int(node_id) & 0xFFFF,
        int(seq) & 0xFFFF,
        int(midi_bus) & 0xFF,
        int(midi_ch) & 0xFF,
        int(note) & 0xFF,
        int(vel) & 0xFF,
        int(ts_ms) & 0xFFFFFFFF,
        int(rssi_dbm),
        int(flags) & 0xFF,
        _normalize_bytes(rsv, size=2),
    )
    if len(packet) != OKUA_EVT_PACKET_SIZE:
        raise RuntimeError(
            f"EVT empaquetado con longitud invalida: {len(packet)} (esperada {OKUA_EVT_PACKET_SIZE})."
        )
    return packet


def build_okua_stat_packet(
    *,
    node_id: int,
    seq: int,
    uptime_s: int = 1,
    rssi_dbm: int = -50,
    state_flags: int = 0,
    pps_x10: int = 10,
    vbat_mv: int = 3700,
    free_heap: int = 256000,
    fw_major: int = 1,
    fw_minor: int = 0,
    reset_reason: int = 0,
    rsv: bytes = b"\x00\x00\x00",
) -> bytes:
    packet = _STAT_STRUCT.pack(
        OKUA_MAGIC,
        OKUA_VERSION,
        OkuaPacketType.STAT,
        int(node_id) & 0xFFFF,
        int(seq) & 0xFFFF,
        int(uptime_s) & 0xFFFFFFFF,
        int(rssi_dbm),
        int(state_flags) & 0xFF,
        int(pps_x10) & 0xFFFF,
        int(vbat_mv) & 0xFFFF,
        int(free_heap) & 0xFFFFFFFF,
        int(fw_major) & 0xFF,
        int(fw_minor) & 0xFF,
        int(reset_reason) & 0xFF,
        _normalize_bytes(rsv, size=3),
    )
    if len(packet) != OKUA_STAT_PACKET_SIZE:
        raise RuntimeError(
            f"STAT empaquetado con longitud invalida: {len(packet)} (esperada {OKUA_STAT_PACKET_SIZE})."
        )
    return packet


def send_okua_v1_packets(
    *,
    host: str,
    evt_port: int,
    stat_port: int,
    node_id: int,
    seq_start: int,
    count: int,
    mode: str = "both",
    interval_ms: int = 100,
    ts_ms_start: int | None = None,
    socket_factory: Callable[[], DatagramSocketLike] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> UdpSendStats:
    if count <= 0:
        raise ValueError("count debe ser mayor a 0.")
    mode_value = mode.strip().lower()
    if mode_value not in {"both", "evt", "stat"}:
        raise ValueError("mode debe ser 'both', 'evt' o 'stat'.")

    send_evt = mode_value in {"both", "evt"}
    send_stat = mode_value in {"both", "stat"}
    sleep = sleep_fn or time.sleep
    sock = (socket_factory or _default_socket_factory)()
    evt_sent = 0
    stat_sent = 0

    try:
        for index in range(count):
            seq = (int(seq_start) + index) & 0xFFFF
            ts_ms = _compute_ts_ms(ts_ms_start, index=index, interval_ms=interval_ms)

            if send_evt:
                evt_payload = build_okua_evt_packet(
                    node_id=node_id,
                    seq=seq,
                    midi_bus=0,
                    midi_ch=0,
                    note=60 + (index % 12),
                    vel=100,
                    ts_ms=ts_ms,
                    rssi_dbm=-48,
                    flags=0x01,
                )
                sock.sendto(evt_payload, (host, int(evt_port)))
                evt_sent += 1

            if send_stat:
                stat_payload = build_okua_stat_packet(
                    node_id=node_id,
                    seq=seq,
                    uptime_s=index + 1,
                    rssi_dbm=-48,
                    state_flags=0x01,
                    pps_x10=10,
                    vbat_mv=3710,
                    free_heap=250000 - index,
                    fw_major=1,
                    fw_minor=2,
                    reset_reason=0,
                )
                sock.sendto(stat_payload, (host, int(stat_port)))
                stat_sent += 1

            if index < (count - 1) and interval_ms > 0:
                sleep(interval_ms / 1000.0)
    finally:
        sock.close()

    return UdpSendStats(evt_sent=evt_sent, stat_sent=stat_sent)


def _normalize_bytes(value: bytes | bytearray, *, size: int) -> bytes:
    raw = bytes(value)
    if len(raw) != size:
        raise ValueError(f"Se esperaban {size} bytes de reserva y llegaron {len(raw)}.")
    return raw


def _compute_ts_ms(ts_ms_start: int | None, *, index: int, interval_ms: int) -> int:
    if ts_ms_start is None:
        return int(time.time() * 1000) & 0xFFFFFFFF
    step = max(1, int(interval_ms))
    return (int(ts_ms_start) + (index * step)) & 0xFFFFFFFF


def _default_socket_factory() -> DatagramSocketLike:
    return socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Emisor de laboratorio compatible con protocolo UDP OKUA v1 (CKv2).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="IP destino (default: 127.0.0.1).")
    parser.add_argument("--evt-port", type=int, default=5005, help="Puerto EVT (default: 5005).")
    parser.add_argument("--stat-port", type=int, default=5006, help="Puerto STAT (default: 5006).")
    parser.add_argument("--node-id", type=int, default=1, help="Node ID de prueba (uint16).")
    parser.add_argument("--seq-start", type=int, default=1, help="Secuencia inicial (uint16).")
    parser.add_argument("--count", type=int, default=10, help="Cantidad de iteraciones a enviar.")
    parser.add_argument(
        "--mode",
        choices=("both", "evt", "stat"),
        default="both",
        help="Tipo de envio: both (EVT+STAT), evt o stat.",
    )
    parser.add_argument(
        "--interval-ms",
        type=int,
        default=100,
        help="Pausa entre iteraciones en ms (default: 100).",
    )
    parser.add_argument(
        "--ts-ms-start",
        type=int,
        default=None,
        help="Timestamp base fijo para pruebas deterministas.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="No envia paquetes; solo imprime longitudes y ejemplos en hex.",
    )
    return parser


def _print_dry_run_examples(args: argparse.Namespace) -> None:
    evt_example = build_okua_evt_packet(
        node_id=args.node_id,
        seq=args.seq_start,
        note=60,
        vel=100,
        ts_ms=_compute_ts_ms(args.ts_ms_start, index=0, interval_ms=args.interval_ms),
    )
    stat_example = build_okua_stat_packet(
        node_id=args.node_id,
        seq=args.seq_start,
        uptime_s=1,
    )
    print(f"[dry-run] EVT len={len(evt_example)} hex={evt_example.hex()}")
    print(f"[dry-run] STAT len={len(stat_example)} hex={stat_example.hex()}")
    print(
        "[dry-run] Destinos: "
        f"EVT -> {args.host}:{args.evt_port} | STAT -> {args.host}:{args.stat_port}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = _build_cli_parser()
    args = parser.parse_args(argv)

    if args.dry_run:
        _print_dry_run_examples(args)
        return 0

    stats = send_okua_v1_packets(
        host=args.host,
        evt_port=args.evt_port,
        stat_port=args.stat_port,
        node_id=args.node_id,
        seq_start=args.seq_start,
        count=args.count,
        mode=args.mode,
        interval_ms=args.interval_ms,
        ts_ms_start=args.ts_ms_start,
    )
    print(
        "[udp-okua-v1] envio completado: "
        f"evt_sent={stats.evt_sent} stat_sent={stats.stat_sent} "
        f"dest={args.host} evt_port={args.evt_port} stat_port={args.stat_port}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
