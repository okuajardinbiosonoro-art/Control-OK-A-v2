from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("matplotlib")

from tools.live_diagnostics_panel import (
    DiagnosticsModel,
    THEME,
    build_session_paths,
    _event_tone,
    _state_color,
    parse_diag_csv_row,
    parse_touch_text_line,
)


def _write_demo_session(folder: Path) -> None:
    diag_csv = folder / "diagnostic_values.csv"
    touch_log = folder / "touch_events.log"
    diag_log = folder / "diagnostic_values.log"
    folder.mkdir(parents=True, exist_ok=True)

    diag_csv.write_text(
        "\n".join(
            [
                "base,cand,dv,energy_age_ms,exit,filt,hold_down_ms,hold_up_ms,id,mode,node,pending_sign,phase,prev,raw,recovery_ms,ref,sigma,slope,state,t_ms,th_down,th_up,touch_sign,vmax,vmin",
                "1.8644,0,0.0049,177741,0,1.8693,175809,0,1,fruit,EB1,-1,track,1.8693,1.8680,0,0,0.0040,-0.0476,idle,506402,0.0252,0.0420,1,1.9671,1.7616",
                "1.7406,1,0.0957,0,0,1.8363,0,513,1,fruit,EB1,1,track,idle,1.7406,0,0,0.0232,0.4859,contact,1050307,0.0252,0.0420,1,1.9671,1.6641",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    touch_log.write_text(
        "\n".join(
            [
                "[12:08:40.693] 198.51.100.17:51374 EB1#1 TOQUE INICIO raw=1.9163 filt=2.0763 dv=0.3223",
                "[12:09:00.499] 198.51.100.17:51374 EB1#1 TOQUE FIN raw=2.2040 filt=2.1036 dv=0.2949",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    diag_log.write_text(
        "[12:15:15.984] 198.51.100.17:51374 EB1#1 track/idle raw=2.2661 filt=2.2073 base=2.2163 dv=-0.0090 slope=2.1768 sigma=0.0229 th_up=0.0420 th_down=0.0252\n",
        encoding="utf-8",
    )


def test_parse_diag_csv_row_supports_current_schema() -> None:
    sample = parse_diag_csv_row(
        {
            "base": "1.8644",
            "cand": "1",
            "dv": "0.0957",
            "energy_age_ms": "0",
            "exit": "0",
            "filt": "1.8363",
            "hold_down_ms": "0",
            "hold_up_ms": "513",
            "id": "1",
            "mode": "fruit",
            "node": "EB1",
            "pending_sign": "1",
            "phase": "track",
            "prev": "idle",
            "raw": "1.7406",
            "recovery_ms": "0",
            "ref": "0",
            "sigma": "0.0232",
            "slope": "0.4859",
            "state": "contact",
            "t_ms": "1050307",
            "th_down": "0.0252",
            "th_up": "0.0420",
            "touch_sign": "1",
            "vmax": "1.9671",
            "vmin": "1.6641",
        }
    )

    assert sample.state == "contact"
    assert sample.phase == "track"
    assert sample.raw == 1.7406
    assert sample.rail is False
    assert sample.summary_reason().startswith("phase=track")


def test_parse_diag_csv_row_surfaces_v23_gate_telemetry() -> None:
    sample = parse_diag_csv_row(
        {
            "fw": "1.0.23-dev",
            "fsm": "possible_touch",
            "entry_reason": "rescue_rail",
            "block_reason": "none",
            "entry_armed": "0",
            "entry_rescue": "1",
            "raw_rail": "1",
            "out_req": "1",
            "out_ok": "1",
            "base": "1.8732",
            "cand": "1",
            "dv": "0.2037",
            "filt": "1.6697",
            "raw": "0.0000",
            "phase": "track",
            "state": "idle",
            "t_ms": "1337000",
        }
    )

    reason = sample.summary_reason()

    assert sample.raw == 0.0
    assert sample.cand == 1
    assert "fw=1.0.23-dev" in reason
    assert "entry_reason=rescue_rail" in reason
    assert "entry_rescue=1" in reason
    assert "out_ok=1" in reason


def test_parse_touch_text_line_extracts_touch_fields() -> None:
    event = parse_touch_text_line(
        "[12:08:40.693] 198.51.100.17:51374 EB1#1 TOQUE INICIO raw=1.9163 filt=2.0763 dv=0.3223"
    )
    assert event is not None
    assert event.kind == "TOQUE INICIO"
    assert event.state_after == "contact"
    assert event.raw == 1.9163
    assert event.dv == 0.3223


def test_theme_helpers_map_states_and_events() -> None:
    assert _state_color("idle") == THEME.idle
    assert _state_color("contact") == THEME.accent
    assert _event_tone("TOQUE INICIO") == THEME.accent
    assert _event_tone("possible_touch") == THEME.warning
    assert _event_tone("rejected") == THEME.danger


def test_model_ingest_updates_counts_and_snapshot(tmp_path: Path) -> None:
    folder = tmp_path / "fruit_soak_20260426_120000"
    _write_demo_session(folder)

    model = DiagnosticsModel(
        session=build_session_paths(folder),
        label="1.0.21-dev",
        max_samples=100,
        max_events=100,
        text_tail=20,
        stale_warn_sec=999.0,
    )

    model.ingest()
    snapshot = model.snapshot(60000)

    assert model.total_diag_rows == 2
    assert model.touch_starts == 1
    assert model.touch_ends == 1
    assert snapshot.capture_health == "ACTIVE"
    assert snapshot.latest_state in {"idle", "contact"}
    assert snapshot.events_per_min >= 1.0
    assert model.diag_text_tail
    assert model.touch_text_tail
