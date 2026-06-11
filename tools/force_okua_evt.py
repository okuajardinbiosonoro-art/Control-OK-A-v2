from __future__ import annotations

import argparse
import socket
import struct
import time


OKUA_MAGIC = 0x4B4F
OKUA_PROTOCOL_VERSION = 1
OKUA_TYPE_EVT = 1
OKUA_EVT_PORT = 5005
EVT_FLAG_TOUCH = 0x01


def build_evt_packet(
    *,
    node_id: int,
    seq: int,
    midi_bus: int,
    midi_ch: int,
    note: int,
    vel: int,
    flags: int,
) -> bytes:
    return struct.pack(
        "<HBBHHBBBBIbB2s",
        OKUA_MAGIC,
        OKUA_PROTOCOL_VERSION,
        OKUA_TYPE_EVT,
        node_id & 0xFFFF,
        seq & 0xFFFF,
        midi_bus & 0xFF,
        midi_ch & 0xFF,
        note & 0xFF,
        vel & 0xFF,
        int(time.monotonic() * 1000) & 0xFFFFFFFF,
        -42,
        flags & 0xFF,
        b"\x00\x00",
    )


def send_evt(sock: socket.socket, target: tuple[str, int], packet: bytes, dry_run: bool) -> None:
    if dry_run:
        print(f"DRY_RUN would send {len(packet)} bytes to {target[0]}:{target[1]}")
        return
    sock.sendto(packet, target)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inject a controlled OKUA_EVT touch start/end pair to test the audio path without the sensor.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host running the OKUA event/audio listener.")
    parser.add_argument("--port", type=int, default=OKUA_EVT_PORT, help="OKUA_EVT UDP port.")
    parser.add_argument("--node-id", type=int, default=1, help="Node id to encode in the packet.")
    parser.add_argument("--note", type=int, default=57, help="MIDI note to send.")
    parser.add_argument("--duration-ms", type=int, default=450, help="Delay between touch start and end.")
    parser.add_argument(
        "--channels",
        default="0,2,4",
        help="Comma-separated zero-based MIDI channels. EB fanout uses 0,2,4.",
    )
    parser.add_argument("--midi-bus", type=int, default=0, help="MIDI bus to encode.")
    parser.add_argument("--dry-run", action="store_true", help="Print packets without sending them.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    channels = [int(part.strip()) for part in str(args.channels).split(",") if part.strip()]
    if not channels:
        raise SystemExit("At least one channel is required.")

    target = (str(args.host), int(args.port))
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        seq = 1
        for channel in channels:
            packet = build_evt_packet(
                node_id=args.node_id,
                seq=seq,
                midi_bus=args.midi_bus,
                midi_ch=channel,
                note=args.note,
                vel=100,
                flags=EVT_FLAG_TOUCH,
            )
            send_evt(sock, target, packet, args.dry_run)
            seq += 1
        if not args.dry_run:
            time.sleep(max(0, int(args.duration_ms)) / 1000.0)
        for channel in channels:
            packet = build_evt_packet(
                node_id=args.node_id,
                seq=seq,
                midi_bus=args.midi_bus,
                midi_ch=channel,
                note=args.note,
                vel=0,
                flags=EVT_FLAG_TOUCH,
            )
            send_evt(sock, target, packet, args.dry_run)
            seq += 1
    finally:
        sock.close()

    print(
        f"OKUA_EVT touch pair {'prepared' if args.dry_run else 'sent'} "
        f"host={target[0]} port={target[1]} node={args.node_id} note={args.note} channels={channels}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
