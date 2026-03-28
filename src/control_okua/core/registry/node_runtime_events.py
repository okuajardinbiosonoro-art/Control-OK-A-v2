from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class NodeRuntimeEventType(str, Enum):
    STATUS_CHANGED = "status_changed"
    REBOOT_DETECTED = "reboot_detected"
    CALIBRATING_ENTERED = "calibrating_entered"
    RECOVERED_ONLINE = "recovered_online"
    MOVED_DEGRADED = "moved_degraded"
    MOVED_OFFLINE = "moved_offline"


@dataclass(frozen=True)
class NodeRuntimeEvent:
    occurred_at_pc_ts: float
    event_type: NodeRuntimeEventType
    status_key: str = ""
    reason: str = ""
    details: str = ""
