from __future__ import annotations

from dataclasses import dataclass

from control_okua.core.registry.node_models import NodeRegistryConfig, NodeStatus


@dataclass(frozen=True)
class NodeStatusInputs:
    last_seen_pc_ts: float | None
    last_stat_pc_ts: float | None
    pps_evt: float
    pps_stat: float
    loss_evt_pct: float
    loss_stat_pct: float
    last_seq_evt: int | None
    last_seq_stat: int | None
    last_uptime_s: int | None
    last_reboot_detected_pc_ts: float | None
    evt_recovery_streak: int
    stat_recovery_streak: int


@dataclass(frozen=True)
class NodeStatusEvaluation:
    status: NodeStatus
    reason: str
    health_summary: str
    age_s: float | None
    last_stat_age_s: float | None
    is_recent_reboot: bool
    is_recovering: bool


def evaluate_node_status(
    inputs: NodeStatusInputs,
    config: NodeRegistryConfig,
    *,
    now: float,
) -> NodeStatusEvaluation:
    last_seen = inputs.last_seen_pc_ts
    if last_seen is None:
        return NodeStatusEvaluation(
            status=NodeStatus.OFFLINE,
            reason="no recent packets",
            health_summary="no recent packets",
            age_s=None,
            last_stat_age_s=None,
            is_recent_reboot=False,
            is_recovering=False,
        )

    age_s = max(0.0, float(now) - float(last_seen))
    last_stat_age_s = _age_or_none(inputs.last_stat_pc_ts, now=now)
    is_recent_reboot = _is_recent_reboot(inputs, config, age_s=age_s, now=now)
    if age_s >= config.t_red_s:
        return NodeStatusEvaluation(
            status=NodeStatus.OFFLINE,
            reason="no recent packets",
            health_summary="no recent packets",
            age_s=age_s,
            last_stat_age_s=last_stat_age_s,
            is_recent_reboot=is_recent_reboot,
            is_recovering=False,
        )

    if is_recent_reboot:
        return NodeStatusEvaluation(
            status=NodeStatus.CALIBRATING,
            reason="calibrating",
            health_summary="reboot recent",
            age_s=age_s,
            last_stat_age_s=last_stat_age_s,
            is_recent_reboot=True,
            is_recovering=False,
        )

    if age_s >= config.t_green_s:
        return NodeStatusEvaluation(
            status=NodeStatus.DEGRADED,
            reason="partial traffic",
            health_summary="activity partial",
            age_s=age_s,
            last_stat_age_s=last_stat_age_s,
            is_recent_reboot=False,
            is_recovering=False,
        )

    stat_loss_active = (
        inputs.last_seq_stat is not None
        and inputs.loss_stat_pct >= config.stat_loss_yellow_pct
    )
    has_recent_stat = last_stat_age_s is not None and last_stat_age_s <= config.t_recover_s
    if stat_loss_active:
        stat_recovered = has_recent_stat and (
            inputs.stat_recovery_streak >= config.stat_recovery_packets_online
        )
        if stat_recovered:
            return NodeStatusEvaluation(
                status=NodeStatus.ONLINE,
                reason="healthy traffic",
                health_summary="healthy traffic",
                age_s=age_s,
                last_stat_age_s=last_stat_age_s,
                is_recent_reboot=False,
                is_recovering=False,
            )
        return NodeStatusEvaluation(
            status=NodeStatus.DEGRADED,
            reason="recovering" if inputs.stat_recovery_streak > 0 else "elevated loss",
            health_summary="recovering" if inputs.stat_recovery_streak > 0 else "elevated loss",
            age_s=age_s,
            last_stat_age_s=last_stat_age_s,
            is_recent_reboot=False,
            is_recovering=inputs.stat_recovery_streak > 0,
        )

    if has_recent_stat:
        return NodeStatusEvaluation(
            status=NodeStatus.ONLINE,
            reason="healthy traffic",
            health_summary="healthy traffic",
            age_s=age_s,
            last_stat_age_s=last_stat_age_s,
            is_recent_reboot=False,
            is_recovering=False,
        )

    evt_degraded = _is_evt_only_degraded(inputs, config)
    if evt_degraded:
        evt_recovered = (
            age_s <= config.t_recover_s
            and inputs.evt_recovery_streak >= config.evt_recovery_packets_online
        )
        if evt_recovered:
            return NodeStatusEvaluation(
                status=NodeStatus.ONLINE,
                reason="healthy traffic",
                health_summary="healthy traffic",
                age_s=age_s,
                last_stat_age_s=last_stat_age_s,
                is_recent_reboot=False,
                is_recovering=False,
            )
        return NodeStatusEvaluation(
            status=NodeStatus.DEGRADED,
            reason="recovering" if inputs.evt_recovery_streak > 0 else "partial traffic",
            health_summary="recovering" if inputs.evt_recovery_streak > 0 else "activity partial",
            age_s=age_s,
            last_stat_age_s=last_stat_age_s,
            is_recent_reboot=False,
            is_recovering=inputs.evt_recovery_streak > 0,
        )

    return NodeStatusEvaluation(
        status=NodeStatus.ONLINE,
        reason="healthy traffic",
        health_summary="healthy traffic",
        age_s=age_s,
        last_stat_age_s=last_stat_age_s,
        is_recent_reboot=False,
        is_recovering=False,
    )


def _age_or_none(timestamp: float | None, *, now: float) -> float | None:
    if timestamp is None:
        return None
    return max(0.0, float(now) - float(timestamp))


def _is_recent_reboot(
    inputs: NodeStatusInputs,
    config: NodeRegistryConfig,
    *,
    age_s: float,
    now: float,
) -> bool:
    if age_s > config.t_green_s:
        return False
    if inputs.last_reboot_detected_pc_ts is not None:
        reboot_age_s = max(0.0, float(now) - float(inputs.last_reboot_detected_pc_ts))
        if reboot_age_s <= config.calibrating_hold_s:
            return True
    if inputs.last_uptime_s is not None and int(inputs.last_uptime_s) <= config.calibrating_uptime_s:
        return True
    return False


def _is_evt_only_degraded(inputs: NodeStatusInputs, config: NodeRegistryConfig) -> bool:
    if config.pps_min_yellow <= 0:
        return False
    if inputs.last_seq_evt is None:
        return False
    if inputs.pps_evt >= config.pps_min_yellow:
        return False
    return inputs.loss_evt_pct >= 50.0
