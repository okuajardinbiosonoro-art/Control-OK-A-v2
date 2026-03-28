from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.models import NodeTableModel  # noqa: E402
from control_okua.app_qt.viewmodels import sort_node_snapshots_by_id  # noqa: E402
from control_okua.core.registry import NodeSnapshot, NodeStatus  # noqa: E402


def _node_snapshot(
    *,
    node_id: int,
    status: NodeStatus,
    last_seen_pc_ts: float,
    note: int | None = None,
    vel: int | None = None,
    status_reason: str = "healthy traffic",
) -> NodeSnapshot:
    return NodeSnapshot(
        node_id=node_id,
        label=None,
        node_type=None,
        last_seen_pc_ts=last_seen_pc_ts,
        last_seq_evt=1,
        last_seq_stat=1,
        pps_evt=1.0,
        pps_stat=2.0,
        loss_evt_pct=0.0,
        loss_stat_pct=1.0,
        rssi_dbm=-60,
        last_note=note,
        last_velocity=vel,
        last_evt_ts_ms=1,
        last_evt_flags=1,
        last_state_flags=1,
        last_uptime_s=10,
        reported_pps_x10=10,
        status=status,
        status_reason=status_reason,
    )


def test_node_table_model_renders_expected_columns_and_values() -> None:
    model = NodeTableModel()
    snapshots = [
        _node_snapshot(node_id=20, status=NodeStatus.DEGRADED, last_seen_pc_ts=100.0),
        _node_snapshot(node_id=10, status=NodeStatus.ONLINE, last_seen_pc_ts=100.0, note=64, vel=100),
    ]
    model.set_snapshots(sort_node_snapshots_by_id(snapshots), now_monotonic=100.5)

    assert model.rowCount() == 2
    assert model.columnCount() == 9
    assert model.headerData(0, Qt.Horizontal, Qt.DisplayRole) == "node_id"
    assert model.headerData(3, Qt.Horizontal, Qt.DisplayRole) == "estado"

    assert model.data(model.index(0, 0), Qt.DisplayRole) == "10"
    assert model.data(model.index(0, 3), Qt.DisplayRole) == "En línea"
    assert model.data(model.index(0, 8), Qt.DisplayRole) == "64 / 100"
    assert model.data(model.index(1, 0), Qt.DisplayRole) == "20"
    assert model.data(model.index(1, 3), Qt.DisplayRole) == "Degradado"


def test_node_table_model_exposes_status_reason_as_tooltip() -> None:
    model = NodeTableModel()
    snapshots = [
        _node_snapshot(
            node_id=10,
            status=NodeStatus.CALIBRATING,
            last_seen_pc_ts=100.0,
            status_reason="calibrating",
        ),
    ]
    model.set_snapshots(snapshots, now_monotonic=100.5)

    assert model.data(model.index(0, 3), Qt.DisplayRole) == "En calibración"
    tooltip = str(
        model.data(model.index(0, 3), Qt.ToolTipRole)
    ).lower()
    assert "estado: en calibración" in tooltip
    assert "motivo: en calibración" in tooltip
    assert "último paquete" in tooltip
