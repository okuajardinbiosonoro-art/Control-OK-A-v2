from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.contracts import DEFAULT_HOME_MAP_LAYOUT  # noqa: E402
from control_okua.app_qt.viewmodels.home_map_runtime_vm import (  # noqa: E402
    HOME_MAP_LEGEND_ITEMS,
    build_home_map_box_view_models,
    resolve_home_map_status_visual,
)
from control_okua.core.registry import NodeSnapshot, NodeStatus  # noqa: E402
from control_okua.core.session import BackendKind, SessionSnapshot, SessionState  # noqa: E402


def _session_snapshot(*, running: bool) -> SessionSnapshot:
    return SessionSnapshot(
        state=SessionState.RUNNING if running else SessionState.IDLE,
        active_profile="udp_jardin",
        mode="udp",
        backend=BackendKind.UDP,
        message="running" if running else "idle",
        error=None,
        can_start=not running,
        can_stop=running,
    )


def _node_snapshot(node_id: int, status: NodeStatus, *, reason: str = "healthy traffic") -> NodeSnapshot:
    return NodeSnapshot(
        node_id=node_id,
        label=None,
        node_type=None,
        last_seen_pc_ts=100.0,
        last_seq_evt=1,
        last_seq_stat=1,
        pps_evt=1.0,
        pps_stat=2.0,
        loss_evt_pct=0.0,
        loss_stat_pct=0.0,
        rssi_dbm=-50,
        last_note=64,
        last_velocity=100,
        last_evt_ts_ms=1,
        last_evt_flags=1,
        last_state_flags=1,
        last_uptime_s=10,
        reported_pps_x10=10,
        status=status,
        status_reason=reason,
    )


def test_runtime_vm_keeps_neutral_status_when_session_is_not_running() -> None:
    view_models = build_home_map_box_view_models(
        DEFAULT_HOME_MAP_LAYOUT,
        [_node_snapshot(1, NodeStatus.ONLINE)],
        _session_snapshot(running=False),
    )
    center_box = next(view for view in view_models if view.box_id == 1)
    assert center_box.aggregate_status is None
    assert center_box.status_label == "Sin estado en vivo"


def test_runtime_vm_marks_box_offline_when_running_but_no_nodes_are_visible() -> None:
    view_models = build_home_map_box_view_models(
        DEFAULT_HOME_MAP_LAYOUT,
        [],
        _session_snapshot(running=True),
    )
    center_box = next(view for view in view_models if view.box_id == 1)
    assert center_box.aggregate_status is NodeStatus.OFFLINE
    assert center_box.badge_text == "Fuera de línea"


def test_runtime_vm_marks_box_degraded_when_expected_nodes_are_missing() -> None:
    view_models = build_home_map_box_view_models(
        DEFAULT_HOME_MAP_LAYOUT,
        [_node_snapshot(1, NodeStatus.ONLINE)],
        _session_snapshot(running=True),
    )
    center_box = next(view for view in view_models if view.box_id == 1)
    assert center_box.aggregate_status is NodeStatus.DEGRADED
    assert "sin evidencia reciente" in center_box.status_summary.lower()


def test_runtime_vm_respects_priority_between_mixed_statuses() -> None:
    view_models = build_home_map_box_view_models(
        DEFAULT_HOME_MAP_LAYOUT,
        [
            _node_snapshot(6, NodeStatus.CALIBRATING, reason="calibrating"),
            _node_snapshot(7, NodeStatus.DEGRADED, reason="partial traffic"),
            _node_snapshot(8, NodeStatus.ONLINE),
            _node_snapshot(9, NodeStatus.ONLINE),
            _node_snapshot(10, NodeStatus.ONLINE),
        ],
        _session_snapshot(running=True),
    )
    box2 = next(view for view in view_models if view.box_id == 2)
    assert box2.aggregate_status is NodeStatus.DEGRADED
    assert box2.status_label == "Degradado"


def test_runtime_vm_exposes_calibrating_when_box_is_complete_and_rebooting() -> None:
    view_models = build_home_map_box_view_models(
        DEFAULT_HOME_MAP_LAYOUT,
        [
            _node_snapshot(1, NodeStatus.CALIBRATING, reason="calibrating"),
            _node_snapshot(2, NodeStatus.CALIBRATING, reason="calibrating"),
        ],
        _session_snapshot(running=True),
    )
    center_box = next(view for view in view_models if view.box_id == 1)
    assert center_box.aggregate_status is NodeStatus.CALIBRATING
    assert "calibrando" in center_box.badge_text.lower()


def test_runtime_vm_legend_and_visuals_stay_aligned() -> None:
    assert [item.label for item in HOME_MAP_LEGEND_ITEMS] == [
        "En línea",
        "En calibración",
        "Degradado",
        "Fuera de línea",
    ]
    visual = resolve_home_map_status_visual(NodeStatus.OFFLINE)
    assert visual.badge_text == "Fuera de línea"
    assert visual.border_hex == "#C92A2A"
