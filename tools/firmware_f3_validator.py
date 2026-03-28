from __future__ import annotations

import argparse
import hmac
import hashlib
import os
import socket
import struct
import sys
import time
from dataclasses import dataclass
from pathlib import Path


OKUA_MAGIC = 0x4B4F
OKUA_VER = 1

OKUA_TYPE_CMD = 3
OKUA_TYPE_ACK = 4
OKUA_TYPE_STAT = 2

OKUA_CMD_PORT = 5007
OKUA_ACK_PORT = 5008
OKUA_STAT_PORT = 5006

OKUA_CMD_PING = 0x01
OKUA_CMD_REBOOT_SOFT = 0x02
OKUA_CMD_REQUEST_STAT_NOW = 0x07
OKUA_CMD_OTA_CHECK_NOW = 0x08

OKUA_ACK_STAGE_ACCEPTED = 1
OKUA_STATUS_OK = 0x00

ACK_STRUCT = struct.Struct("<HBBHHBBBBHHQI")
CMD_STRUCT = struct.Struct("<HBBHHBBHHQ2sI")
STAT_STRUCT = struct.Struct("<HBBHHIbBHHIBBB3s")

ACK_FLAG_DUPLICATE = 0x01
ACK_FLAG_BROADCAST_RESPONSE = 0x02

CMD_NAME_TO_ID = {
    "ping": OKUA_CMD_PING,
    "request_stat_now": OKUA_CMD_REQUEST_STAT_NOW,
    "reboot_soft": OKUA_CMD_REBOOT_SOFT,
    "ota_check_now": OKUA_CMD_OTA_CHECK_NOW,
}

ACK_STAGE_NAME = {
    1: "ACCEPTED",
    2: "EXECUTED",
    3: "REJECTED",
}

STATUS_NAME = {
    0x00: "OK",
    0x01: "RESERVED",
    0x02: "INVALID_AUTH",
    0x03: "INVALID_ARG",
    0x04: "UNSUPPORTED_CMD",
    0x05: "RATE_LIMITED",
    0x06: "REPLAY_REJECTED",
    0x07: "BUSY",
    0x08: "INTERNAL_ERROR",
}

ERR_NAME = {
    0x0000: "NONE",
    0x0001: "ARG0_OUT_OF_RANGE",
    0x0002: "ARG1_OUT_OF_RANGE",
    0x0003: "PROFILE_ID_UNKNOWN",
    0x0004: "THROTTLE_INVALID",
    0x0005: "STAT_RATE_INVALID",
    0x0006: "DEBUG_LEVEL_INVALID",
    0x0007: "BROADCAST_NOT_ALLOWED",
    0x0008: "NONCE_REUSED",
    0x0009: "NONCE_OUT_OF_WINDOW",
    0x000A: "AUTH_TAG_MISMATCH",
    0x000B: "RATE_LIMIT_EXCEEDED",
    0x000C: "NODE_STATE_BLOCKED",
    0x000D: "CMD_IN_PROGRESS",
    0x000E: "MALFORMED_PACKET",
}


@dataclass(frozen=True)
class AckFrame:
    src_ip: str
    src_port: int
    node_id: int
    seq: int
    cmd_id: int
    ack_stage: int
    status_code: int
    ack_flags: int
    err_detail: int
    retry_after_ms: int
    nonce_echo: int
    auth_tag32: int
    auth_valid: bool
    rtt_ms: float


@dataclass(frozen=True)
class StatFrame:
    src_ip: str
    src_port: int
    node_id: int
    seq: int
    uptime_s: int
    state_flags: int
    pps_x10: int
    fw_major: int
    fw_minor: int


def parse_u32(value: str) -> int:
    return int(value, 0) & 0xFFFFFFFF


def parse_u16(value: str) -> int:
    return int(value, 0) & 0xFFFF


def parse_u64(value: str) -> int:
    return int(value, 0) & 0xFFFFFFFFFFFFFFFF


def resolve_secret(args: argparse.Namespace) -> bytes:
    if args.secret:
        return args.secret.encode("utf-8")

    if args.secret_file:
        text = Path(args.secret_file).read_text(encoding="utf-8").strip()
        if not text:
            raise ValueError("El archivo --secret-file esta vacio.")
        return text.encode("utf-8")

    env_val = os.environ.get(args.secret_env, "").strip()
    if env_val:
        return env_val.encode("utf-8")

    raise ValueError(
        "No hay secreto configurado. Usa --secret, --secret-file o la variable "
        f"de entorno {args.secret_env}."
    )


def auth_tag32(secret: bytes, payload_first_24: bytes) -> int:
    digest = hmac.new(secret, payload_first_24, hashlib.sha256).digest()
    return int.from_bytes(digest[:4], byteorder="little", signed=False)


def resolve_target(args: argparse.Namespace, cmd_id: int) -> tuple[str, int, bool]:
    if args.broadcast:
        if cmd_id not in (OKUA_CMD_PING, OKUA_CMD_REQUEST_STAT_NOW):
            raise ValueError("Broadcast solo esta permitido para PING y REQUEST_STAT_NOW.")
        return args.broadcast_ip, 0, True

    if not args.target_ip:
        raise ValueError("En unicast debes indicar --target-ip.")
    if args.node_id <= 0:
        raise ValueError("En unicast --node-id debe ser > 0.")
    return args.target_ip, args.node_id, False


def resolve_seq(args: argparse.Namespace) -> int:
    if args.seq is not None:
        return args.seq & 0xFFFF
    return int(time.time_ns() & 0xFFFF)


def resolve_nonce(args: argparse.Namespace) -> int:
    if args.nonce is not None:
        return args.nonce & 0xFFFFFFFFFFFFFFFF

    epoch_s = int(time.time()) if args.epoch_s is None else int(args.epoch_s)
    if args.counter is None:
        counter = int((time.time_ns() // 1_000_000) & 0xFFFFFFFF)
    else:
        counter = int(args.counter) & 0xFFFFFFFF
    return ((epoch_s & 0xFFFFFFFF) << 32) | counter


def resolve_args_for_command(args: argparse.Namespace, cmd_id: int) -> tuple[int, int]:
    if cmd_id == OKUA_CMD_REBOOT_SOFT:
        delay = int(args.reboot_delay_ms)
        if delay != 0 and not (50 <= delay <= 5000):
            raise ValueError("--reboot-delay-ms debe ser 0 o estar en 50..5000.")
        return delay & 0xFFFF, 0
    if cmd_id == OKUA_CMD_OTA_CHECK_NOW:
        rollout_token = parse_u32(args.rollout_token)
        if rollout_token == 0:
            raise ValueError("--rollout-token debe ser > 0 para ota_check_now.")
        return rollout_token & 0xFFFF, (rollout_token >> 16) & 0xFFFF
    return 0, 0


def build_cmd_packet(
    *,
    secret: bytes,
    seq: int,
    node_id: int,
    cmd_id: int,
    nonce: int,
    arg0: int,
    arg1: int,
    is_retry: bool,
    is_broadcast: bool,
) -> bytes:
    cmd_flags = 0x01
    if is_retry:
        cmd_flags |= 0x02
    if is_broadcast:
        cmd_flags |= 0x04

    packet_wo_auth = CMD_STRUCT.pack(
        OKUA_MAGIC,
        OKUA_VER,
        OKUA_TYPE_CMD,
        node_id & 0xFFFF,
        seq & 0xFFFF,
        cmd_id & 0xFF,
        cmd_flags & 0xFF,
        arg0 & 0xFFFF,
        arg1 & 0xFFFF,
        nonce & 0xFFFFFFFFFFFFFFFF,
        b"\x00\x00",
        0,
    )
    tag = auth_tag32(secret, packet_wo_auth[:24])
    return CMD_STRUCT.pack(
        OKUA_MAGIC,
        OKUA_VER,
        OKUA_TYPE_CMD,
        node_id & 0xFFFF,
        seq & 0xFFFF,
        cmd_id & 0xFF,
        cmd_flags & 0xFF,
        arg0 & 0xFFFF,
        arg1 & 0xFFFF,
        nonce & 0xFFFFFFFFFFFFFFFF,
        b"\x00\x00",
        tag,
    )


def parse_ack(data: bytes, *, src_ip: str, src_port: int, send_started_ns: int, secret: bytes) -> AckFrame | None:
    if len(data) != ACK_STRUCT.size:
        return None

    (
        magic,
        ver,
        pkt_type,
        node_id,
        seq,
        cmd_id,
        ack_stage,
        status_code,
        ack_flags,
        err_detail,
        retry_after_ms,
        nonce_echo,
        auth_tag,
    ) = ACK_STRUCT.unpack(data)

    if magic != OKUA_MAGIC or ver != OKUA_VER or pkt_type != OKUA_TYPE_ACK:
        return None

    expected = auth_tag32(secret, data[:24])
    auth_valid = hmac.compare_digest(expected.to_bytes(4, "little"), auth_tag.to_bytes(4, "little"))
    rtt_ms = (time.time_ns() - send_started_ns) / 1_000_000.0

    return AckFrame(
        src_ip=src_ip,
        src_port=src_port,
        node_id=node_id,
        seq=seq,
        cmd_id=cmd_id,
        ack_stage=ack_stage,
        status_code=status_code,
        ack_flags=ack_flags,
        err_detail=err_detail,
        retry_after_ms=retry_after_ms,
        nonce_echo=nonce_echo,
        auth_tag32=auth_tag,
        auth_valid=auth_valid,
        rtt_ms=rtt_ms,
    )


def parse_stat(data: bytes, *, src_ip: str, src_port: int) -> StatFrame | None:
    if len(data) != STAT_STRUCT.size:
        return None

    (
        magic,
        ver,
        pkt_type,
        node_id,
        seq,
        uptime_s,
        _rssi_dbm,
        state_flags,
        pps_x10,
        _vbat_mv,
        _free_heap,
        fw_major,
        fw_minor,
        _reset_reason,
        _rsv,
    ) = STAT_STRUCT.unpack(data)

    if magic != OKUA_MAGIC or ver != OKUA_VER or pkt_type != OKUA_TYPE_STAT:
        return None

    return StatFrame(
        src_ip=src_ip,
        src_port=src_port,
        node_id=node_id,
        seq=seq,
        uptime_s=uptime_s,
        state_flags=state_flags,
        pps_x10=pps_x10,
        fw_major=fw_major,
        fw_minor=fw_minor,
    )


def recv_matching_acks(
    *,
    sock: socket.socket,
    expected_seq: int,
    expected_cmd_id: int,
    expected_nonce: int,
    send_started_ns: int,
    timeout_ms: int,
    broadcast_collect_ms: int,
    expect_multiple: bool,
    secret: bytes,
) -> list[AckFrame]:
    results: list[AckFrame] = []
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    collect_deadline: float | None = None

    while True:
        now = time.monotonic()
        active_deadline = deadline
        if collect_deadline is not None:
            active_deadline = min(active_deadline, collect_deadline)
        remaining = active_deadline - now
        if remaining <= 0:
            break

        sock.settimeout(remaining)
        try:
            data, (src_ip, src_port) = sock.recvfrom(512)
        except socket.timeout:
            break

        ack = parse_ack(
            data,
            src_ip=src_ip,
            src_port=src_port,
            send_started_ns=send_started_ns,
            secret=secret,
        )
        if ack is None:
            continue
        if ack.seq != expected_seq or ack.cmd_id != expected_cmd_id or ack.nonce_echo != expected_nonce:
            continue

        results.append(ack)
        if not expect_multiple:
            break
        if collect_deadline is None:
            collect_deadline = time.monotonic() + (broadcast_collect_ms / 1000.0)

    return results


def recv_first_stat(
    *,
    sock: socket.socket,
    timeout_ms: int,
    expected_node_id: int | None,
) -> StatFrame | None:
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        sock.settimeout(remaining)
        try:
            data, (src_ip, src_port) = sock.recvfrom(512)
        except socket.timeout:
            return None
        stat = parse_stat(data, src_ip=src_ip, src_port=src_port)
        if stat is None:
            continue
        if expected_node_id is not None and stat.node_id != expected_node_id:
            continue
        return stat


def format_cmd_name(cmd_id: int) -> str:
    for name, value in CMD_NAME_TO_ID.items():
        if value == cmd_id:
            return name
    return f"0x{cmd_id:02X}"


def print_ack(ack: AckFrame) -> None:
    stage_name = ACK_STAGE_NAME.get(ack.ack_stage, f"0x{ack.ack_stage:02X}")
    status_name = STATUS_NAME.get(ack.status_code, f"0x{ack.status_code:02X}")
    err_name = ERR_NAME.get(ack.err_detail, f"0x{ack.err_detail:04X}")
    duplicate = "yes" if (ack.ack_flags & ACK_FLAG_DUPLICATE) else "no"
    bcast = "yes" if (ack.ack_flags & ACK_FLAG_BROADCAST_RESPONSE) else "no"
    print(
        "[ACK] "
        f"from={ack.src_ip}:{ack.src_port} node_id={ack.node_id} seq={ack.seq} "
        f"cmd_id={format_cmd_name(ack.cmd_id)} stage={stage_name} "
        f"status={status_name} err={err_name} retry_after_ms={ack.retry_after_ms} "
        f"duplicate={duplicate} broadcast_response={bcast} auth_valid={ack.auth_valid} "
        f"rtt_ms={ack.rtt_ms:.2f}"
    )


def print_stat(stat: StatFrame) -> None:
    print(
        "[STAT] "
        f"from={stat.src_ip}:{stat.src_port} node_id={stat.node_id} seq={stat.seq} "
        f"uptime_s={stat.uptime_s} state_flags=0x{stat.state_flags:02X} "
        f"pps_x10={stat.pps_x10} fw={stat.fw_major}.{stat.fw_minor}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Host-side validator for OKUA F3 CMD/ACK minimal firmware block.",
    )
    parser.add_argument(
        "command",
        choices=sorted(CMD_NAME_TO_ID.keys()),
        help="Command to send (ping, request_stat_now, reboot_soft).",
    )
    parser.add_argument("--target-ip", help="Unicast target IP (required unless --broadcast).")
    parser.add_argument("--node-id", type=parse_u16, default=1, help="Target node_id for unicast.")
    parser.add_argument("--broadcast", action="store_true", help="Send broadcast command (node_id=0).")
    parser.add_argument("--broadcast-ip", default="255.255.255.255", help="Broadcast destination IP.")
    parser.add_argument("--allow-reboot", action="store_true", help="Required to send reboot_soft.")

    parser.add_argument("--listen-host", default="0.0.0.0", help="Local bind host for ACK/STAT sockets.")
    parser.add_argument("--cmd-port", type=parse_u16, default=OKUA_CMD_PORT, help="CMD destination UDP port.")
    parser.add_argument("--ack-port", type=parse_u16, default=OKUA_ACK_PORT, help="ACK listen UDP port.")
    parser.add_argument("--stat-port", type=parse_u16, default=OKUA_STAT_PORT, help="STAT listen UDP port.")

    parser.add_argument("--seq", type=parse_u16, default=None, help="Explicit cmd_seq (uint16).")
    parser.add_argument("--nonce", type=parse_u64, default=None, help="Explicit nonce (uint64).")
    parser.add_argument("--epoch-s", type=parse_u32, default=None, help="Nonce epoch high 32 bits.")
    parser.add_argument("--counter", type=parse_u32, default=None, help="Nonce counter low 32 bits.")
    parser.add_argument("--retry", action="store_true", help="Set cmd_flags.is_retry=1.")
    parser.add_argument(
        "--reboot-delay-ms",
        type=parse_u16,
        default=200,
        help="arg0 for reboot_soft (0 or 50..5000).",
    )
    parser.add_argument(
        "--rollout-token",
        default="0x1",
        help="Token uint32 para OTA_CHECK_NOW (ej. 0x20260328).",
    )

    parser.add_argument("--ack-timeout-ms", type=int, default=1200, help="ACK wait timeout.")
    parser.add_argument(
        "--broadcast-collect-ms",
        type=int,
        default=1000,
        help="Extra collect window after first ACK in broadcast mode.",
    )
    parser.add_argument("--stat-timeout-ms", type=int, default=1200, help="STAT wait timeout.")
    parser.add_argument(
        "--expect-stat",
        action="store_true",
        help="Wait for one STAT frame after ACK (auto-enabled for request_stat_now unless --no-expect-stat).",
    )
    parser.add_argument("--no-expect-stat", action="store_true", help="Disable STAT wait.")
    parser.add_argument(
        "--allow-non-ok-ack",
        action="store_true",
        help="Do not fail when ACK is not ACCEPTED+OK.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Build packet and print info without sending.")

    parser.add_argument("--secret", default=None, help="Control secret string.")
    parser.add_argument("--secret-file", default=None, help="Path to file containing control secret.")
    parser.add_argument(
        "--secret-env",
        default="OKUA_CONTROL_SECRET",
        help="Environment variable for control secret (default: OKUA_CONTROL_SECRET).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.expect_stat and args.no_expect_stat:
        parser.error("No puedes usar --expect-stat y --no-expect-stat al mismo tiempo.")

    cmd_id = CMD_NAME_TO_ID[args.command]
    if cmd_id == OKUA_CMD_REBOOT_SOFT and not args.allow_reboot:
        parser.error("reboot_soft requiere --allow-reboot para evitar reinicios accidentales.")

    try:
        secret = resolve_secret(args)
        dst_ip, node_id, is_broadcast = resolve_target(args, cmd_id)
        seq = resolve_seq(args)
        nonce = resolve_nonce(args)
        arg0, arg1 = resolve_args_for_command(args, cmd_id)
    except Exception as exc:  # noqa: BLE001
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    expect_stat = args.expect_stat
    if not args.no_expect_stat and cmd_id == OKUA_CMD_REQUEST_STAT_NOW:
        expect_stat = True

    cmd_packet = build_cmd_packet(
        secret=secret,
        seq=seq,
        node_id=node_id,
        cmd_id=cmd_id,
        nonce=nonce,
        arg0=arg0,
        arg1=arg1,
        is_retry=args.retry,
        is_broadcast=is_broadcast,
    )

    print(
        "[CMD] "
        f"name={args.command} dst={dst_ip}:{args.cmd_port} node_id={node_id} "
        f"seq={seq} nonce=0x{nonce:016X} arg0={arg0} arg1={arg1} "
        f"broadcast={is_broadcast} retry={args.retry}"
    )
    print(f"[CMD] packet_len={len(cmd_packet)} auth_tag32=0x{int.from_bytes(cmd_packet[24:28], 'little'):08X}")

    if args.dry_run:
        print(f"[dry-run] hex={cmd_packet.hex()}")
        return 0

    ack_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ack_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ack_sock.bind((args.listen_host, args.ack_port))

    stat_sock: socket.socket | None = None
    if expect_stat:
        stat_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        stat_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        stat_sock.bind((args.listen_host, args.stat_port))

    send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if is_broadcast:
        send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    try:
        send_started_ns = time.time_ns()
        send_sock.sendto(cmd_packet, (dst_ip, args.cmd_port))

        acks = recv_matching_acks(
            sock=ack_sock,
            expected_seq=seq,
            expected_cmd_id=cmd_id,
            expected_nonce=nonce,
            send_started_ns=send_started_ns,
            timeout_ms=args.ack_timeout_ms,
            broadcast_collect_ms=args.broadcast_collect_ms,
            expect_multiple=is_broadcast,
            secret=secret,
        )

        if not acks:
            print("[result] No se recibio ACK correlacionado.", file=sys.stderr)
            return 3

        for ack in acks:
            print_ack(ack)

        if not args.allow_non_ok_ack:
            bad = [
                ack
                for ack in acks
                if ack.ack_stage != OKUA_ACK_STAGE_ACCEPTED
                or ack.status_code != OKUA_STATUS_OK
                or not ack.auth_valid
            ]
            if bad:
                print(
                    "[result] Se recibio ACK pero no cumple EXPECTED=ACCEPTED+OK+auth_valid.",
                    file=sys.stderr,
                )
                return 4

        if expect_stat and stat_sock is not None:
            expected_node_id = None if is_broadcast else node_id
            stat = recv_first_stat(
                sock=stat_sock,
                timeout_ms=args.stat_timeout_ms,
                expected_node_id=expected_node_id,
            )
            if stat is None:
                print("[result] No se recibio STAT dentro del timeout esperado.", file=sys.stderr)
                return 5
            print_stat(stat)

        print("[result] OK")
        return 0
    finally:
        send_sock.close()
        ack_sock.close()
        if stat_sock is not None:
            stat_sock.close()


if __name__ == "__main__":
    raise SystemExit(main())
