from __future__ import annotations

from typing import Callable
import time

from control_okua.core.registry.node_models import (
    NodeRegistryConfig,
    NodeRegistrySummary,
    NodeSnapshot,
    NodeState,
    NodeStatus,
)
from control_okua.core.udp import OkuaEvtPacket, OkuaStatPacket


class NodeRegistry:
    """Pure node runtime registry for parsed OKUA EVT/STAT packets."""

    def __init__(
        self,
        config: NodeRegistryConfig | None = None,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._config = config or NodeRegistryConfig()
        self._clock = clock or time.monotonic
        self._nodes: dict[int, NodeState] = {}

    def observe_evt(self, packet: OkuaEvtPacket, received_at: float | None = None) -> None:
        now = self._resolve_ts(received_at)
        node = self._get_or_create_node(packet.header.node_id)

        node.last_seen_pc_ts = now
        node.rssi_dbm = packet.rssi_dbm
        node.last_note = packet.note
        node.last_velocity = packet.vel
        node.last_evt_ts_ms = packet.ts_ms
        node.last_evt_flags = packet.flags

        self._update_seq_loss(node=node, seq=packet.header.seq, stream="evt")
        node.pps_evt = self._record_pps_sample(node._evt_timestamps, now)
        node.pps_stat = self._compute_pps(node._stat_timestamps, now)
        node.status = self._compute_status(node, now)

    def observe_stat(self, packet: OkuaStatPacket, received_at: float | None = None) -> None:
        now = self._resolve_ts(received_at)
        node = self._get_or_create_node(packet.header.node_id)

        node.last_seen_pc_ts = now
        node.last_stat_pc_ts = now
        node.rssi_dbm = packet.rssi_dbm
        node.last_state_flags = packet.state_flags
        node.last_uptime_s = packet.uptime_s
        node.reported_pps_x10 = packet.pps_x10
        node.vbat_mv = packet.vbat_mv
        node.free_heap = packet.free_heap
        node.fw_major = packet.fw_major
        node.fw_minor = packet.fw_minor
        node.reset_reason = packet.reset_reason

        self._update_seq_loss(node=node, seq=packet.header.seq, stream="stat")
        node.pps_stat = self._record_pps_sample(node._stat_timestamps, now)
        node.pps_evt = self._compute_pps(node._evt_timestamps, now)
        node.status = self._compute_status(node, now)

    def get_node_snapshot(self, node_id: int, now: float | None = None) -> NodeSnapshot | None:
        node = self._nodes.get(int(node_id))
        if node is None:
            return None
        resolved_now = self._resolve_ts(now)
        self._refresh_node(node, resolved_now)
        return self._to_snapshot(node)

    def get_all_node_snapshots(self, now: float | None = None) -> list[NodeSnapshot]:
        resolved_now = self._resolve_ts(now)
        snapshots: list[NodeSnapshot] = []
        for node_id in sorted(self._nodes):
            node = self._nodes[node_id]
            self._refresh_node(node, resolved_now)
            snapshots.append(self._to_snapshot(node))
        return snapshots

    def get_summary(self, now: float | None = None) -> NodeRegistrySummary:
        resolved_now = self._resolve_ts(now)
        online_count = 0
        degraded_count = 0
        offline_count = 0
        total_pps_evt = 0.0
        total_pps_stat = 0.0

        for node in self._nodes.values():
            self._refresh_node(node, resolved_now)
            total_pps_evt += node.pps_evt
            total_pps_stat += node.pps_stat
            if node.status is NodeStatus.ONLINE:
                online_count += 1
            elif node.status is NodeStatus.DEGRADED:
                degraded_count += 1
            else:
                offline_count += 1

        return NodeRegistrySummary(
            total_nodes=len(self._nodes),
            online_count=online_count,
            degraded_count=degraded_count,
            offline_count=offline_count,
            total_pps_evt=total_pps_evt,
            total_pps_stat=total_pps_stat,
        )

    def recompute_statuses(self, now: float | None = None) -> None:
        resolved_now = self._resolve_ts(now)
        for node in self._nodes.values():
            self._refresh_node(node, resolved_now)

    def clear(self) -> None:
        self._nodes.clear()

    def _resolve_ts(self, supplied: float | None) -> float:
        if supplied is not None:
            return float(supplied)
        return float(self._clock())

    def _get_or_create_node(self, node_id: int) -> NodeState:
        resolved_node_id = int(node_id)
        node = self._nodes.get(resolved_node_id)
        if node is None:
            node = NodeState(node_id=resolved_node_id)
            self._nodes[resolved_node_id] = node
        return node

    def _refresh_node(self, node: NodeState, now: float) -> None:
        node.pps_evt = self._compute_pps(node._evt_timestamps, now)
        node.pps_stat = self._compute_pps(node._stat_timestamps, now)
        node.status = self._compute_status(node, now)

    def _record_pps_sample(self, queue: "deque[float]", sample_ts: float) -> float:
        queue.append(float(sample_ts))
        return self._compute_pps(queue, sample_ts)

    def _compute_pps(self, queue: "deque[float]", now: float) -> float:
        cutoff = float(now) - self._config.pps_window_s
        while queue and queue[0] < cutoff:
            queue.popleft()
        return float(len(queue)) / self._config.pps_window_s

    def _compute_status(self, node: NodeState, now: float) -> NodeStatus:
        last_seen = node.last_seen_pc_ts
        if last_seen is None:
            return NodeStatus.OFFLINE

        age_s = max(0.0, float(now) - float(last_seen))
        if age_s >= self._config.t_red_s:
            return NodeStatus.OFFLINE
        if age_s >= self._config.t_green_s:
            return NodeStatus.DEGRADED
        if self._has_metric_degradation(node, now):
            return NodeStatus.DEGRADED
        return NodeStatus.ONLINE

    def _has_metric_degradation(self, node: NodeState, now: float) -> bool:
        if node.last_seq_stat is not None and node.loss_stat_pct >= self._config.stat_loss_yellow_pct:
            return True

        # If STAT is recent, do not degrade solely by sparse EVT traffic.
        if node.last_stat_pc_ts is not None:
            if max(0.0, float(now) - float(node.last_stat_pc_ts)) < self._config.t_green_s:
                return False

        if self._config.pps_min_yellow <= 0:
            return False

        # EVT-only nodes can be marked degraded only when both pps and seq loss suggest trouble.
        if node.last_seq_evt is None:
            return False
        return node.pps_evt < self._config.pps_min_yellow and node.loss_evt_pct >= 50.0

    def _update_seq_loss(self, *, node: NodeState, seq: int, stream: str) -> None:
        resolved_seq = int(seq) & 0xFFFF
        if stream == "evt":
            last_seq = node.last_seq_evt
            seen_forward = node._evt_seen_forward
            missing_packets = node._evt_missing_packets
        else:
            last_seq = node.last_seq_stat
            seen_forward = node._stat_seen_forward
            missing_packets = node._stat_missing_packets

        if last_seq is None:
            last_seq = resolved_seq
            seen_forward += 1
        else:
            delta = (resolved_seq - last_seq) & 0xFFFF
            if delta == 0:
                pass
            elif delta < 0x8000:
                if delta > 1:
                    missing_packets += delta - 1
                seen_forward += 1
                last_seq = resolved_seq
            else:
                # Out-of-order/backward packet: keep baseline untouched.
                pass

        denominator = seen_forward + missing_packets
        loss_pct = (100.0 * float(missing_packets) / float(denominator)) if denominator > 0 else 0.0

        if stream == "evt":
            node.last_seq_evt = last_seq
            node._evt_seen_forward = seen_forward
            node._evt_missing_packets = missing_packets
            node.loss_evt_pct = loss_pct
        else:
            node.last_seq_stat = last_seq
            node._stat_seen_forward = seen_forward
            node._stat_missing_packets = missing_packets
            node.loss_stat_pct = loss_pct

    def _to_snapshot(self, node: NodeState) -> NodeSnapshot:
        return NodeSnapshot(
            node_id=node.node_id,
            label=node.label,
            node_type=node.node_type,
            last_seen_pc_ts=node.last_seen_pc_ts,
            last_seq_evt=node.last_seq_evt,
            last_seq_stat=node.last_seq_stat,
            pps_evt=node.pps_evt,
            pps_stat=node.pps_stat,
            loss_evt_pct=node.loss_evt_pct,
            loss_stat_pct=node.loss_stat_pct,
            rssi_dbm=node.rssi_dbm,
            last_note=node.last_note,
            last_velocity=node.last_velocity,
            last_evt_ts_ms=node.last_evt_ts_ms,
            last_evt_flags=node.last_evt_flags,
            last_state_flags=node.last_state_flags,
            last_uptime_s=node.last_uptime_s,
            reported_pps_x10=node.reported_pps_x10,
            status=node.status,
            vbat_mv=node.vbat_mv,
            free_heap=node.free_heap,
            fw_major=node.fw_major,
            fw_minor=node.fw_minor,
            reset_reason=node.reset_reason,
        )
