from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from control_okua.core.registry.node_runtime_events import NodeRuntimeEvent


class NodeStatus(str, Enum):
    ONLINE = "online"
    CALIBRATING = "calibrating"
    DEGRADED = "degraded"
    OFFLINE = "offline"


@dataclass(frozen=True)
class NodeRegistryConfig:
    t_green_s: float = 4.0
    t_red_s: float = 8.0
    pps_min_yellow: float = 0.0
    pps_window_s: float = 5.0
    stat_loss_yellow_pct: float = 25.0
    t_recover_s: float = 1.5
    calibrating_hold_s: float = 6.0
    calibrating_uptime_s: int = 20
    stat_recovery_packets_online: int = 3
    evt_recovery_packets_online: int = 4
    max_runtime_events_per_node: int = 10

    def __post_init__(self) -> None:
        if self.t_green_s <= 0:
            raise ValueError("t_green_s must be > 0")
        if self.t_red_s <= self.t_green_s:
            raise ValueError("t_red_s must be > t_green_s")
        if self.pps_window_s <= 0:
            raise ValueError("pps_window_s must be > 0")
        if self.pps_min_yellow < 0:
            raise ValueError("pps_min_yellow must be >= 0")
        if self.stat_loss_yellow_pct < 0:
            raise ValueError("stat_loss_yellow_pct must be >= 0")
        if self.t_recover_s <= 0:
            raise ValueError("t_recover_s must be > 0")
        if self.t_recover_s > self.t_green_s:
            raise ValueError("t_recover_s must be <= t_green_s")
        if self.calibrating_hold_s <= 0:
            raise ValueError("calibrating_hold_s must be > 0")
        if self.calibrating_uptime_s < 0:
            raise ValueError("calibrating_uptime_s must be >= 0")
        if self.stat_recovery_packets_online < 1:
            raise ValueError("stat_recovery_packets_online must be >= 1")
        if self.evt_recovery_packets_online < 1:
            raise ValueError("evt_recovery_packets_online must be >= 1")
        if self.max_runtime_events_per_node < 1:
            raise ValueError("max_runtime_events_per_node must be >= 1")


@dataclass
class NodeState:
    node_id: int
    label: str | None = None
    node_type: str | None = None
    last_seen_pc_ts: float | None = None
    last_seq_evt: int | None = None
    last_seq_stat: int | None = None
    pps_evt: float = 0.0
    pps_stat: float = 0.0
    loss_evt_pct: float = 0.0
    loss_stat_pct: float = 0.0
    rssi_dbm: int | None = None
    last_note: int | None = None
    last_velocity: int | None = None
    last_evt_ts_ms: int | None = None
    last_evt_flags: int | None = None
    last_state_flags: int | None = None
    last_uptime_s: int | None = None
    reported_pps_x10: int | None = None
    status: NodeStatus = NodeStatus.OFFLINE
    vbat_mv: int | None = None
    free_heap: int | None = None
    fw_major: int | None = None
    fw_minor: int | None = None
    reset_reason: int | None = None
    last_stat_pc_ts: float | None = None
    status_reason: str = "no recent packets"
    health_summary: str = "no recent packets"
    ota_state_code: int | None = None
    ota_error_code: int | None = None
    ota_flags: int | None = None
    ota_state_key: str = "idle"
    ota_error_key: str = "none"
    ota_check_pending: bool = False
    ota_pending_reboot: bool = False
    ota_pending_verify: bool = False
    ota_health_confirmed: bool = False
    last_status_change_pc_ts: float | None = None
    last_reboot_detected_pc_ts: float | None = None
    last_boot_marker: int | None = None
    recovering: bool = False
    _evt_seen_forward: int = 0
    _evt_missing_packets: int = 0
    _stat_seen_forward: int = 0
    _stat_missing_packets: int = 0
    _evt_recovery_streak: int = 0
    _stat_recovery_streak: int = 0
    _evt_timestamps: deque[float] = field(default_factory=deque, repr=False)
    _stat_timestamps: deque[float] = field(default_factory=deque, repr=False)
    _recent_events: deque[NodeRuntimeEvent] = field(default_factory=deque, repr=False)


@dataclass(frozen=True)
class NodeSnapshot:
    node_id: int
    label: str | None
    node_type: str | None
    last_seen_pc_ts: float | None
    last_seq_evt: int | None
    last_seq_stat: int | None
    pps_evt: float
    pps_stat: float
    loss_evt_pct: float
    loss_stat_pct: float
    rssi_dbm: int | None
    last_note: int | None
    last_velocity: int | None
    last_evt_ts_ms: int | None
    last_evt_flags: int | None
    last_state_flags: int | None
    last_uptime_s: int | None
    reported_pps_x10: int | None
    status: NodeStatus
    vbat_mv: int | None = None
    free_heap: int | None = None
    fw_major: int | None = None
    fw_minor: int | None = None
    reset_reason: int | None = None
    status_reason: str = ""
    health_summary: str = ""
    ota_state_code: int | None = None
    ota_error_code: int | None = None
    ota_flags: int | None = None
    ota_state_key: str = "idle"
    ota_error_key: str = "none"
    ota_check_pending: bool = False
    ota_pending_reboot: bool = False
    ota_pending_verify: bool = False
    ota_health_confirmed: bool = False
    last_status_change_pc_ts: float | None = None
    last_reboot_detected_pc_ts: float | None = None
    last_seen_age_s: float | None = None
    last_stat_age_s: float | None = None
    status_age_s: float | None = None
    reboot_age_s: float | None = None
    reboot_recent: bool = False
    recovering: bool = False
    last_transition_summary: str = ""
    recent_events: tuple[NodeRuntimeEvent, ...] = ()


@dataclass(frozen=True)
class NodeRegistrySummary:
    total_nodes: int
    online_count: int
    degraded_count: int
    offline_count: int
    total_pps_evt: float
    total_pps_stat: float
    calibrating_count: int = 0
