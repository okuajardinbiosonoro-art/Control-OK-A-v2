from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Final

from control_okua.core.control_plane.auth import compute_auth_tag32
from control_okua.core.udp.packet_models import OKUA_MAGIC, OKUA_VERSION, OkuaPacketType

OKUA_CMD_PORT: Final[int] = 5007
OKUA_ACK_PORT: Final[int] = 5008
OKUA_CMD_PACKET_SIZE: Final[int] = 28
OKUA_ACK_PACKET_SIZE: Final[int] = 28

OKUA_TYPE_CMD: Final[int] = int(OkuaPacketType.CMD)
OKUA_TYPE_ACK: Final[int] = int(OkuaPacketType.ACK)

CMD_FLAG_ACK_REQUIRED: Final[int] = 0x01
CMD_FLAG_IS_RETRY: Final[int] = 0x02
CMD_FLAG_BROADCAST_INTENT: Final[int] = 0x04

_CMD_STRUCT = struct.Struct("<HBBHHBBHHQ2sI")
_ACK_STRUCT = struct.Struct("<HBBHHBBBBHHQI")


class OkuaCmdId(IntEnum):
    PING = 0x01
    REBOOT_SOFT = 0x02
    SET_STAT_RATE = 0x05
    REQUEST_STAT_NOW = 0x07


SET_STAT_RATE_ALLOWED_MS: Final[tuple[int, ...]] = (1000, 2000, 5000)


class CmdSequenceManager:
    """Monotonic cmd_seq generator for logical new commands."""

    def __init__(self, *, start_seq: int = 0) -> None:
        self._next_seq = _validate_u16("start_seq", start_seq)

    def next_cmd_seq(self) -> int:
        seq = self._next_seq
        self._next_seq = (seq + 1) & 0xFFFF
        return seq

    @property
    def next_value(self) -> int:
        return self._next_seq


class AckParseErrorCode(str, Enum):
    INVALID_SIZE = "invalid_size"
    INVALID_MAGIC = "invalid_magic"
    INVALID_VERSION = "invalid_version"
    INVALID_TYPE = "invalid_type"


class AckParseError(ValueError):
    """Strict parse error for malformed OKUA_ACK datagrams."""

    def __init__(self, code: AckParseErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ParsedOkuaAck:
    node_id_source: int
    cmd_seq: int
    cmd_id_echo: int
    nonce_echo: int
    ack_stage: int
    status_code: int
    ack_flags: int
    err_detail: int
    retry_after_ms: int
    auth_tag32: int


def build_okua_cmd_bytes(
    *,
    secret: bytes,
    node_id_target: int,
    cmd_seq: int,
    cmd_id: int,
    nonce: int,
    arg0: int = 0,
    arg1: int = 0,
    is_retry: bool = False,
    broadcast_intent: bool = False,
) -> bytes:
    """Builds a full 28-byte OKUA_CMD packet with auth_tag32."""
    resolved_node_id = _validate_u16("node_id_target", node_id_target)
    resolved_cmd_seq = _validate_u16("cmd_seq", cmd_seq)
    resolved_cmd_id = _validate_u8("cmd_id", cmd_id)
    resolved_arg0 = _validate_u16("arg0", arg0)
    resolved_arg1 = _validate_u16("arg1", arg1)
    resolved_nonce = _validate_u64("nonce", nonce)

    _validate_broadcast_flags(
        node_id_target=resolved_node_id,
        broadcast_intent=bool(broadcast_intent),
    )

    cmd_flags = build_cmd_flags(
        is_retry=bool(is_retry),
        broadcast_intent=bool(broadcast_intent),
    )

    packet_wo_auth = _CMD_STRUCT.pack(
        OKUA_MAGIC,
        OKUA_VERSION,
        OKUA_TYPE_CMD,
        resolved_node_id,
        resolved_cmd_seq,
        resolved_cmd_id,
        cmd_flags,
        resolved_arg0,
        resolved_arg1,
        resolved_nonce,
        b"\x00\x00",
        0,
    )
    auth_tag32 = compute_auth_tag32(secret, packet_wo_auth[:24])
    packet = _CMD_STRUCT.pack(
        OKUA_MAGIC,
        OKUA_VERSION,
        OKUA_TYPE_CMD,
        resolved_node_id,
        resolved_cmd_seq,
        resolved_cmd_id,
        cmd_flags,
        resolved_arg0,
        resolved_arg1,
        resolved_nonce,
        b"\x00\x00",
        auth_tag32,
    )
    if len(packet) != OKUA_CMD_PACKET_SIZE:
        raise RuntimeError(
            f"OKUA_CMD invalido: se esperaban {OKUA_CMD_PACKET_SIZE} bytes y se construyeron {len(packet)}."
        )
    return packet


def build_ping_command(
    *,
    secret: bytes,
    node_id_target: int,
    cmd_seq: int,
    nonce: int,
    is_retry: bool = False,
    broadcast_intent: bool = False,
) -> bytes:
    return build_okua_cmd_bytes(
        secret=secret,
        node_id_target=node_id_target,
        cmd_seq=cmd_seq,
        cmd_id=int(OkuaCmdId.PING),
        nonce=nonce,
        arg0=0,
        arg1=0,
        is_retry=is_retry,
        broadcast_intent=broadcast_intent,
    )


def build_request_stat_now_command(
    *,
    secret: bytes,
    node_id_target: int,
    cmd_seq: int,
    nonce: int,
    is_retry: bool = False,
    broadcast_intent: bool = False,
) -> bytes:
    return build_okua_cmd_bytes(
        secret=secret,
        node_id_target=node_id_target,
        cmd_seq=cmd_seq,
        cmd_id=int(OkuaCmdId.REQUEST_STAT_NOW),
        nonce=nonce,
        arg0=0,
        arg1=0,
        is_retry=is_retry,
        broadcast_intent=broadcast_intent,
    )


def build_reboot_soft_command(
    *,
    secret: bytes,
    node_id_target: int,
    cmd_seq: int,
    nonce: int,
    delay_ms: int = 0,
    is_retry: bool = False,
) -> bytes:
    resolved_node_id = _validate_u16("node_id_target", node_id_target)
    if resolved_node_id == 0:
        raise ValueError("REBOOT_SOFT solo permite unicast (node_id_target > 0).")

    resolved_delay = _validate_reboot_delay_ms(delay_ms)
    return build_okua_cmd_bytes(
        secret=secret,
        node_id_target=resolved_node_id,
        cmd_seq=cmd_seq,
        cmd_id=int(OkuaCmdId.REBOOT_SOFT),
        nonce=nonce,
        arg0=resolved_delay,
        arg1=0,
        is_retry=is_retry,
        broadcast_intent=False,
    )


def build_set_stat_rate_command(
    *,
    secret: bytes,
    node_id_target: int,
    cmd_seq: int,
    nonce: int,
    stat_rate_ms: int,
    is_retry: bool = False,
) -> bytes:
    resolved_node_id = _validate_u16("node_id_target", node_id_target)
    if resolved_node_id == 0:
        raise ValueError("SET_STAT_RATE solo permite unicast (node_id_target > 0).")

    resolved_stat_rate = _validate_set_stat_rate_ms(stat_rate_ms)
    return build_okua_cmd_bytes(
        secret=secret,
        node_id_target=resolved_node_id,
        cmd_seq=cmd_seq,
        cmd_id=int(OkuaCmdId.SET_STAT_RATE),
        nonce=nonce,
        arg0=resolved_stat_rate,
        arg1=0,
        is_retry=is_retry,
        broadcast_intent=False,
    )


def build_cmd_flags(*, is_retry: bool, broadcast_intent: bool) -> int:
    flags = CMD_FLAG_ACK_REQUIRED
    if is_retry:
        flags |= CMD_FLAG_IS_RETRY
    if broadcast_intent:
        flags |= CMD_FLAG_BROADCAST_INTENT
    return flags


def parse_okua_ack_bytes(data: bytes | bytearray | memoryview) -> ParsedOkuaAck:
    payload = bytes(data)
    if len(payload) != OKUA_ACK_PACKET_SIZE:
        raise AckParseError(
            AckParseErrorCode.INVALID_SIZE,
            (
                f"ACK invalido: longitud {len(payload)} bytes "
                f"(esperado {OKUA_ACK_PACKET_SIZE})."
            ),
        )

    (
        magic,
        version,
        packet_type,
        node_id_source,
        cmd_seq,
        cmd_id_echo,
        ack_stage,
        status_code,
        ack_flags,
        err_detail,
        retry_after_ms,
        nonce_echo,
        auth_tag32,
    ) = _ACK_STRUCT.unpack(payload)

    if magic != OKUA_MAGIC:
        raise AckParseError(
            AckParseErrorCode.INVALID_MAGIC,
            f"ACK invalido: magic 0x{magic:04X} (esperado 0x{OKUA_MAGIC:04X}).",
        )

    if version != OKUA_VERSION:
        raise AckParseError(
            AckParseErrorCode.INVALID_VERSION,
            f"ACK invalido: version {version} (esperada {OKUA_VERSION}).",
        )

    if packet_type != OKUA_TYPE_ACK:
        raise AckParseError(
            AckParseErrorCode.INVALID_TYPE,
            f"ACK invalido: type {packet_type} (esperado {OKUA_TYPE_ACK}).",
        )

    return ParsedOkuaAck(
        node_id_source=node_id_source,
        cmd_seq=cmd_seq,
        cmd_id_echo=cmd_id_echo,
        nonce_echo=nonce_echo,
        ack_stage=ack_stage,
        status_code=status_code,
        ack_flags=ack_flags,
        err_detail=err_detail,
        retry_after_ms=retry_after_ms,
        auth_tag32=auth_tag32,
    )


def _validate_reboot_delay_ms(delay_ms: int) -> int:
    resolved_delay = _validate_u16("delay_ms", delay_ms)
    if resolved_delay == 0:
        return 0
    if 50 <= resolved_delay <= 5000:
        return resolved_delay
    raise ValueError("delay_ms para REBOOT_SOFT debe ser 0 o estar en 50..5000.")


def _validate_broadcast_flags(*, node_id_target: int, broadcast_intent: bool) -> None:
    if node_id_target == 0 and not broadcast_intent:
        raise ValueError("node_id_target=0 requiere broadcast_intent=1.")
    if node_id_target != 0 and broadcast_intent:
        raise ValueError("broadcast_intent=1 solo es valido cuando node_id_target=0.")


def _validate_set_stat_rate_ms(stat_rate_ms: int) -> int:
    resolved = _validate_u16("stat_rate_ms", stat_rate_ms)
    if resolved in SET_STAT_RATE_ALLOWED_MS:
        return resolved
    allowed = ", ".join(str(value) for value in SET_STAT_RATE_ALLOWED_MS)
    raise ValueError(
        f"stat_rate_ms invalido para SET_STAT_RATE: {stat_rate_ms}. "
        f"Permitidos: {allowed}."
    )


def _validate_u8(field_name: str, value: int) -> int:
    resolved = int(value)
    if resolved < 0 or resolved > 0xFF:
        raise ValueError(f"{field_name} fuera de rango u8: {value}")
    return resolved


def _validate_u16(field_name: str, value: int) -> int:
    resolved = int(value)
    if resolved < 0 or resolved > 0xFFFF:
        raise ValueError(f"{field_name} fuera de rango u16: {value}")
    return resolved


def _validate_u64(field_name: str, value: int) -> int:
    resolved = int(value)
    if resolved < 0 or resolved > 0xFFFFFFFFFFFFFFFF:
        raise ValueError(f"{field_name} fuera de rango u64: {value}")
    return resolved
