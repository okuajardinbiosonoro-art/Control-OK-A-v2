from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.main_window import MainWindow  # noqa: E402
from control_okua.core.registry import NodeSnapshot, NodeStatus  # noqa: E402
from control_okua.core.session import BackendKind, SessionSnapshot, SessionState  # noqa: E402


def _ensure_qapp() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _build_cfg() -> dict[str, object]:
    return {
        "version": 2,
        "mode": "udp",
        "profile": {"active": "udp_jardin"},
    }


def _node_snapshot(*, node_id: int, status: NodeStatus) -> NodeSnapshot:
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
    )


def test_nodes_tree_groups_logical_names_by_box() -> None:
    _ensure_qapp()
    window = MainWindow(cfg=_build_cfg(), config_path=Path("config.json"), warnings=[])
    try:
        window._session_snapshot = SessionSnapshot(
            state=SessionState.RUNNING,
            active_profile="udp_jardin",
            mode="udp",
            backend=BackendKind.UDP,
            message="running",
            error=None,
            can_start=False,
            can_stop=True,
        )
        snapshots = [
            _node_snapshot(node_id=1, status=NodeStatus.ONLINE),
            _node_snapshot(node_id=2, status=NodeStatus.DEGRADED),
            _node_snapshot(node_id=10, status=NodeStatus.OFFLINE),
        ]
        summary = SimpleNamespace(
            total_nodes=3,
            online_count=1,
            degraded_count=1,
            offline_count=1,
            total_pps_evt=3.0,
            total_pps_stat=6.0,
        )
        window.session_controller.get_node_snapshots = lambda now=None: snapshots  # type: ignore[method-assign]
        window.session_controller.get_node_registry_summary = lambda now=None: summary  # type: ignore[method-assign]

        window._refresh_nodes_views()

        assert window.nodes_tree.topLevelItemCount() >= 5
        box1 = window.nodes_tree.topLevelItem(0)
        box2 = window.nodes_tree.topLevelItem(1)
        assert box1.text(0).startswith("Caja 1")
        assert box2.text(0).startswith("Caja 2")
        assert box1.childCount() == 2
        assert box2.childCount() == 1
        assert box1.child(0).text(0) == "EB1"
        assert box1.child(1).text(0) == "EC1"
        assert box2.child(0).text(0) == "EF2"
        assert "node_id=10" in box2.child(0).toolTip(0)
        assert "Caja 2" in box2.child(0).toolTip(0)
        assert "bus MIDI=0" in box2.child(0).toolTip(0)
    finally:
        window.close()
