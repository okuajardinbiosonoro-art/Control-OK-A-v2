from __future__ import annotations

import socket
import sys
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.udp import (  # noqa: E402
    BenchV0MsgType,
    build_bench_v0_evt_packet,
    build_bench_v0_ping_packet,
    build_bench_v0_pong_packet,
    build_bench_v0_stat_packet,
    parse_bench_v0_packet,
)
from control_okua.transports.udp import (  # noqa: E402
    BenchV0TransportAdapter,
    BenchV0TransportConfig,
)


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until(predicate, timeout_s: float = 1.8) -> bool:
    start = time.monotonic()
    while (time.monotonic() - start) <= timeout_s:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def _build_cfg(*, auto_pong: bool = True) -> BenchV0TransportConfig:
    return BenchV0TransportConfig(
        bind_ip="127.0.0.1",
        bench_port=_get_free_port(),
        rcvbuf_bytes=262144,
        recv_size=2048,
        auto_pong=auto_pong,
    )


def test_transport_receives_evt_stat_ping_pong_on_single_bench_port() -> None:
    cfg = _build_cfg(auto_pong=False)
    adapter = BenchV0TransportAdapter(config=cfg)
    adapter.start()

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        sender.sendto(
            build_bench_v0_evt_packet(
                node_id=1,
                seq=10,
                midi_bus=0,
                midi_ch=0,
                note=60,
                vel=100,
                ts_ms=1000,
            ),
            (cfg.bind_ip, cfg.bench_port),
        )
        sender.sendto(
            build_bench_v0_stat_packet(node_id=1, seq=11, uptime_s=3, pps_x10=12),
            (cfg.bind_ip, cfg.bench_port),
        )
        sender.sendto(
            build_bench_v0_ping_packet(node_id=1, seq=12, ts_ms=1001),
            (cfg.bind_ip, cfg.bench_port),
        )
        sender.sendto(
            build_bench_v0_pong_packet(node_id=1, seq=13, ts_ms=1002),
            (cfg.bind_ip, cfg.bench_port),
        )

    observed = _wait_until(
        lambda: (
            adapter.snapshot().total_evt_packets >= 1
            and adapter.snapshot().total_stat_packets >= 1
            and adapter.snapshot().total_ping_packets >= 1
            and adapter.snapshot().total_pong_packets >= 1
        )
    )
    snapshot = adapter.snapshot()
    adapter.stop()

    assert observed is True
    assert snapshot.parse_errors == 0
    assert snapshot.total_evt_packets >= 1
    assert snapshot.total_stat_packets >= 1
    assert snapshot.total_ping_packets >= 1
    assert snapshot.total_pong_packets >= 1


def test_transport_auto_pong_replies_to_ping() -> None:
    cfg = _build_cfg(auto_pong=True)
    adapter = BenchV0TransportAdapter(config=cfg)
    adapter.start()

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        sender.bind((cfg.bind_ip, 0))
        sender.settimeout(1.5)
        sender.sendto(
            build_bench_v0_ping_packet(
                node_id=44,
                seq=99,
                ts_ms=2222,
                rtt_ms=5,
                aux16=7,
            ),
            (cfg.bind_ip, cfg.bench_port),
        )
        pong_raw, _address = sender.recvfrom(2048)

    snapshot = adapter.snapshot()
    adapter.stop()
    pong_packet = parse_bench_v0_packet(pong_raw)

    assert pong_packet.header.msg_type is BenchV0MsgType.PONG
    assert pong_packet.header.node_id == 44
    assert pong_packet.header.seq == 99
    assert snapshot.total_ping_packets >= 1
    assert snapshot.total_pong_sent >= 1


def test_transport_invalid_packet_increments_parse_error() -> None:
    cfg = _build_cfg(auto_pong=False)
    adapter = BenchV0TransportAdapter(config=cfg)
    adapter.start()

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        sender.sendto(b"\x00\x01\x02", (cfg.bind_ip, cfg.bench_port))

    observed = _wait_until(lambda: adapter.snapshot().parse_errors >= 1)
    snapshot = adapter.snapshot()
    adapter.stop()

    assert observed is True
    assert snapshot.parse_errors >= 1
