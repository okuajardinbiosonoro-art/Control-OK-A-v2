from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.contracts import DEFAULT_HOME_MAP_LAYOUT  # noqa: E402
from control_okua.app_qt.viewmodels import (  # noqa: E402
    HOME_MAP_LEGEND_ITEMS,
    build_home_map_box_view_models,
    resolve_home_map_status_visual,
)
from control_okua.core.registry import NodeSnapshot, NodeStatus  # noqa: E402
from control_okua.core.session import BackendKind, SessionSnapshot, SessionState  # noqa: E402


def _session_snapshot(*, running: bool) -> SessionSnapshot:
    return SessionSnapshot(
        state=SessionState.RUNNING if running else SessionState.IDLE,
        active_profile="udp_jardin" if running else None,
        mode="udp" if running else None,
        backend=BackendKind.UDP if running else None,
        message="running" if running else "idle",
        error=None,
        can_start=not running,
        can_stop=running,
    )


def _node_snapshot(*, node_id: int, status: NodeStatus, reason: str = "") -> NodeSnapshot:
    return NodeSnapshot(
        node_id=node_id,
        label=f"Nodo {node_id}",
        node_type="sensor",
        last_seen_pc_ts=100.0,
        last_seq_evt=1,
        last_seq_stat=1,
        pps_evt=1.0,
        pps_stat=1.0,
        loss_evt_pct=0.0,
        loss_stat_pct=0.0,
        rssi_dbm=-50,
        last_note=None,
        last_velocity=None,
        last_evt_ts_ms=1,
        last_evt_flags=1,
        last_state_flags=1,
        last_uptime_s=30,
        reported_pps_x10=10,
        status=status,
        status_reason=reason,
    )


def test_home_map_runtime_vm_returns_neutral_state_when_session_is_not_running() -> None:
    view_models = build_home_map_box_view_models(
        DEFAULT_HOME_MAP_LAYOUT,
        [_node_snapshot(node_id=1, status=NodeStatus.ONLINE)],
        _session_snapshot(running=False),
    )
    assert view_models[1].aggregate_status is None
    assert view_models[1].status_label == "Sin estado en vivo"


def test_home_map_runtime_vm_marks_box_offline_when_runtime_is_running_without_nodes() -> None:
    view_models = build_home_map_box_view_models(
        DEFAULT_HOME_MAP_LAYOUT,
        [],
        _session_snapshot(running=True),
    )
    assert view_models[1].aggregate_status is NodeStatus.OFFLINE
    assert "sin evidencia reciente" in view_models[1].status_summary.lower()


def test_home_map_runtime_vm_marks_box_degraded_when_expected_nodes_are_missing() -> None:
    view_models = build_home_map_box_view_models(
        DEFAULT_HOME_MAP_LAYOUT,
        [_node_snapshot(node_id=6, status=NodeStatus.ONLINE)],
        _session_snapshot(running=True),
    )
    assert view_models[2].aggregate_status is NodeStatus.DEGRADED
    assert "faltan nodos esperados" in view_models[2].status_summary.lower()


def test_home_map_runtime_vm_uses_contract_priority_for_mixed_states() -> None:
    view_models = build_home_map_box_view_models(
        DEFAULT_HOME_MAP_LAYOUT,
        [
            _node_snapshot(node_id=11, status=NodeStatus.CALIBRATING),
            _node_snapshot(node_id=12, status=NodeStatus.DEGRADED),
            _node_snapshot(node_id=13, status=NodeStatus.ONLINE),
            _node_snapshot(node_id=14, status=NodeStatus.ONLINE),
            _node_snapshot(node_id=15, status=NodeStatus.ONLINE),
        ],
        _session_snapshot(running=True),
    )
    assert view_models[3].aggregate_status is NodeStatus.DEGRADED
    assert view_models[3].status_label == "Degradado"


def test_home_map_runtime_vm_marks_box_calibrating_when_all_visible_nodes_are_calibrating() -> None:
    view_models = build_home_map_box_view_models(
        DEFAULT_HOME_MAP_LAYOUT,
        [
            _node_snapshot(node_id=1, status=NodeStatus.CALIBRATING),
            _node_snapshot(node_id=2, status=NodeStatus.CALIBRATING),
        ],
        _session_snapshot(running=True),
    )
    assert view_models[1].aggregate_status is NodeStatus.CALIBRATING
    assert "calibración" in view_models[1].status_summary.lower()


def test_home_map_runtime_vm_exposes_visuals_and_legend_for_all_supported_statuses() -> None:
    assert [item.label for item in HOME_MAP_LEGEND_ITEMS] == [
        "En línea",
        "En calibración",
        "Degradado",
        "Fuera de línea",
    ]
    assert resolve_home_map_status_visual(NodeStatus.ONLINE).fill_hex
    assert resolve_home_map_status_visual(NodeStatus.CALIBRATING).fill_hex
    assert resolve_home_map_status_visual(NodeStatus.DEGRADED).fill_hex
    assert resolve_home_map_status_visual(NodeStatus.OFFLINE).fill_hex
