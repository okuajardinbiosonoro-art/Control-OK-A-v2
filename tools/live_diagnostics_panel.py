from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import matplotlib

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_ROOT = REPO_ROOT / "artifacts"
DEFAULT_WINDOW_SECONDS = 60
DEFAULT_REFRESH_MS = 1000
DEFAULT_MAX_SAMPLES = 25000
DEFAULT_EVENT_TAIL = 240
DEFAULT_TEXT_TAIL = 80
DEFAULT_STALE_WARN_SEC = 12.0
DEMO_FOLDER_NAME = "fruit_soak_demo"


@dataclass(frozen=True)
class PanelTheme:
    app_bg: str = "#F7F4EC"
    surface: str = "#FFFEFC"
    surface_alt: str = "#FFFDFC"
    surface_soft: str = "#FBF8F1"
    border: str = "#DCCFB8"
    border_soft: str = "#E1D5C2"
    text: str = "#0B3B27"
    text_soft: str = "#5B6F66"
    muted: str = "#7A877E"
    accent: str = "#2FAC66"
    accent_dark: str = "#1F8F51"
    info: str = "#2F7ED8"
    warning: str = "#DD8A12"
    danger: str = "#C45245"
    idle: str = "#6B7280"
    possible: str = "#D97706"
    active: str = "#2FAC66"
    release: str = "#8B5CF6"
    recovery: str = "#A855F7"
    raw: str = "#2F7ED8"
    filt: str = "#0F766E"
    base: str = "#2FAC66"
    dv: str = "#D97706"
    slope: str = "#DB2777"
    sigma: str = "#6D28D9"
    white: str = "#FFFFFF"
    black: str = "#08110D"


THEME = PanelTheme()


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_int(value: object) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _norm_text(value: object, default: str = "") -> str:
    text = "" if value is None else str(value).strip()
    return text if text else default


def _lower(value: object, default: str = "") -> str:
    return _norm_text(value, default).lower()


def _fmt_float(value: float | None, digits: int = 4) -> str:
    if value is None or math.isnan(value):
        return "?"
    return f"{value:.{digits}f}"


def _fmt_int(value: int | None) -> str:
    return "?" if value is None else str(value)


def _fmt_ms(value: int | None) -> str:
    if value is None:
        return "?"
    if value < 1000:
        return f"{value} ms"
    return f"{value / 1000.0:.1f} s"


def _fmt_ts_from_log(text: str | None) -> str:
    return text or "?"


@dataclass
class SessionPaths:
    folder: Path
    diag_csv: Path
    diag_log: Path
    touch_csv: Path
    touch_log: Path


@dataclass
class DiagSample:
    t_ms: int | None
    raw: float | None
    filt: float | None
    base: float | None
    dv: float | None
    slope: float | None
    sigma: float | None
    th_up: float | None
    th_down: float | None
    hold_down_ms: int | None
    hold_up_ms: int | None
    energy_age_ms: int | None
    recovery_ms: int | None
    state: str
    phase: str
    mode: str
    cand: int | None
    exit_flag: int | None
    pending_sign: int | None
    touch_sign: int | None
    prev: str
    vmax: float | None
    vmin: float | None
    raw_fields: dict[str, str] = field(default_factory=dict)

    @property
    def rail(self) -> bool:
        if self.raw is not None and (self.raw <= 0.02 or self.raw >= 3.28):
            return True
        if self.vmax is not None and self.vmax >= 3.28:
            return True
        if self.vmin is not None and self.vmin <= 0.02:
            return True
        return False

    @property
    def abs_dv(self) -> float | None:
        return None if self.dv is None else abs(self.dv)

    def summary_reason(self) -> str:
        parts: list[str] = []
        for key in ("fw", "fsm", "entry_reason", "block_reason"):
            value = self.raw_fields.get(key, "")
            if value:
                parts.append(f"{key}={value}")
        if self.phase:
            parts.append(f"phase={self.phase}")
        if self.mode:
            parts.append(f"mode={self.mode}")
        if self.cand is not None:
            parts.append(f"cand={self.cand}")
        for key in ("entry_armed", "entry_rescue", "raw_rail", "out_req", "out_ok"):
            value = self.raw_fields.get(key, "")
            if value not in ("", None):
                parts.append(f"{key}={value}")
        if self.exit_flag is not None:
            parts.append(f"exit={self.exit_flag}")
        if self.pending_sign is not None:
            parts.append(f"pending={self.pending_sign}")
        if self.touch_sign is not None:
            parts.append(f"touch={self.touch_sign}")
        if self.recovery_ms is not None and self.recovery_ms > 0:
            parts.append(f"recovery={self.recovery_ms}")
        if self.hold_down_ms is not None and self.hold_down_ms > 0:
            parts.append(f"hold_down={self.hold_down_ms}")
        if self.hold_up_ms is not None and self.hold_up_ms > 0:
            parts.append(f"hold_up={self.hold_up_ms}")
        if self.prev:
            parts.append(f"prev={self.prev}")
        return ", ".join(parts) if parts else "n/a"


@dataclass
class TouchEvent:
    stamp: str
    kind: str
    state_before: str
    state_after: str
    raw: float | None
    filt: float | None
    dv: float | None
    duration_ms: int | None
    source: str
    note: str = ""


@dataclass
class PanelSnapshot:
    label: str
    folder: str
    diag_source: str
    touch_source: str
    diag_age_s: float | None
    touch_age_s: float | None
    latest_state: str
    latest_phase: str
    latest_mode: str
    state_age_ms: int | None
    events_per_min: float
    touch_starts: int
    touch_ends: int
    rejected: int
    total_diag_rows: int
    total_touch_rows: int
    invalid_rows: int
    current_raw: float | None
    current_filt: float | None
    current_base: float | None
    current_dv: float | None
    current_sigma: float | None
    current_slope: float | None
    current_th_up: float | None
    current_th_down: float | None
    current_hold_down_ms: int | None
    current_hold_up_ms: int | None
    current_energy_age_ms: int | None
    current_recovery_ms: int | None
    current_reason: str
    rail: bool
    capture_health: str
    contact_ratio_pct: float
    idle_ratio_pct: float


class CsvTailReader:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.offset = 0
        self.partial = ""
        self.header: list[str] | None = None

    def reset(self) -> None:
        self.offset = 0
        self.partial = ""
        self.header = None

    def read_new_rows(self) -> list[dict[str, str]]:
        if not self.path.exists():
            return []

        try:
            size = self.path.stat().st_size
        except OSError:
            return []

        if size < self.offset:
            self.reset()

        try:
            with self.path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
                handle.seek(self.offset)
                chunk = handle.read()
                self.offset = handle.tell()
        except OSError:
            return []

        if not chunk:
            return []

        text = self.partial + chunk
        lines = text.splitlines()
        if text and not text.endswith(("\n", "\r")) and lines:
            self.partial = lines.pop()
        else:
            self.partial = ""

        if not lines:
            return []

        if self.header is None:
            header_line = lines.pop(0)
            try:
                self.header = [cell.strip() for cell in next(csv.reader([header_line]))]
            except Exception:
                self.header = [part.strip() for part in header_line.split(",")]

        rows: list[dict[str, str]] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                values = next(csv.reader([line]))
            except Exception:
                values = [part.strip() for part in line.split(",")]
            row: dict[str, str] = {}
            assert self.header is not None
            for index, key in enumerate(self.header):
                row[key] = values[index].strip() if index < len(values) else ""
            rows.append(row)
        return rows


class TextTailReader:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.offset = 0
        self.partial = ""

    def reset(self) -> None:
        self.offset = 0
        self.partial = ""

    def read_new_lines(self) -> list[str]:
        if not self.path.exists():
            return []

        try:
            size = self.path.stat().st_size
        except OSError:
            return []

        if size < self.offset:
            self.reset()

        try:
            with self.path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(self.offset)
                chunk = handle.read()
                self.offset = handle.tell()
        except OSError:
            return []

        if not chunk:
            return []

        text = self.partial + chunk
        lines = text.splitlines()
        if text and not text.endswith(("\n", "\r")) and lines:
            self.partial = lines.pop()
        else:
            self.partial = ""

        return [line for line in lines if line.strip()]


_DIAG_TEXT_RE = re.compile(
    r"^\[(?P<stamp>[^\]]+)\]\s+(?P<source>\S+)\s+"
    r"(?P<node>\S+#\d+)\s+(?:(?P<phase>[A-Za-z0-9_]+)/(?P<state>[A-Za-z0-9_]+)|(?P<fsm>[A-Za-z0-9_]+))"
    r"\s+(?P<body>.*)$"
)
_TOUCH_TEXT_RE = re.compile(
    r"^\[(?P<stamp>[^\]]+)\]\s+(?P<source>\S+)\s+(?P<node>\S+#\d+)\s+"
    r"(?P<kind>TOQUE INICIO|TOQUE FIN)\s+raw=(?P<raw>\S+)\s+filt=(?P<filt>\S+)\s+dv=(?P<dv>\S+)"
)


def _parse_key_values(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for token in body.split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        fields[key.strip()] = value.strip()
    return fields


def _row_to_text(row: dict[str, str]) -> str:
    parts = [f"{key}={value}" for key, value in row.items() if _norm_text(value, "")]
    return " ".join(parts)


def parse_diag_csv_row(row: dict[str, str]) -> DiagSample:
    return DiagSample(
        t_ms=_to_int(row.get("t_ms")),
        raw=_to_float(row.get("raw")),
        filt=_to_float(row.get("filt")),
        base=_to_float(row.get("base")),
        dv=_to_float(row.get("dv")),
        slope=_to_float(row.get("slope")),
        sigma=_to_float(row.get("sigma")),
        th_up=_to_float(row.get("th_up")),
        th_down=_to_float(row.get("th_down")),
        hold_down_ms=_to_int(row.get("hold_down_ms")),
        hold_up_ms=_to_int(row.get("hold_up_ms")),
        energy_age_ms=_to_int(row.get("energy_age_ms")),
        recovery_ms=_to_int(row.get("recovery_ms")),
        state=_lower(row.get("state"), "unknown"),
        phase=_lower(row.get("phase"), ""),
        mode=_lower(row.get("mode"), ""),
        cand=_to_int(row.get("cand")),
        exit_flag=_to_int(row.get("exit")),
        pending_sign=_to_int(row.get("pending_sign")),
        touch_sign=_to_int(row.get("touch_sign")),
        prev=_lower(row.get("prev"), ""),
        vmax=_to_float(row.get("vmax")),
        vmin=_to_float(row.get("vmin")),
        raw_fields=dict(row),
    )


def parse_diag_text_line(line: str) -> DiagSample | None:
    match = _DIAG_TEXT_RE.match(line.strip())
    if not match:
        return None

    body = _parse_key_values(match.group("body"))
    phase = _lower(match.group("phase"), "")
    state = _lower(match.group("state"), "")
    fsm = _lower(match.group("fsm"), "")
    if not state and fsm:
        state = fsm
    return DiagSample(
        t_ms=None,
        raw=_to_float(body.get("raw")),
        filt=_to_float(body.get("filt")),
        base=_to_float(body.get("base")),
        dv=_to_float(body.get("dv")),
        slope=_to_float(body.get("slope")),
        sigma=_to_float(body.get("sigma")),
        th_up=_to_float(body.get("th_up")),
        th_down=_to_float(body.get("th_down")),
        hold_down_ms=_to_int(body.get("hold_down_ms")),
        hold_up_ms=_to_int(body.get("hold_up_ms")),
        energy_age_ms=_to_int(body.get("energy_age_ms")),
        recovery_ms=_to_int(body.get("recovery_ms")),
        state=state or "unknown",
        phase=phase,
        mode=_lower(body.get("mode"), ""),
        cand=_to_int(body.get("cand")),
        exit_flag=_to_int(body.get("exit")),
        pending_sign=_to_int(body.get("pending_sign")),
        touch_sign=_to_int(body.get("touch_sign")),
        prev=_lower(body.get("prev"), ""),
        vmax=_to_float(body.get("vmax")),
        vmin=_to_float(body.get("vmin")),
        raw_fields=body,
    )


def parse_touch_text_line(line: str) -> TouchEvent | None:
    match = _TOUCH_TEXT_RE.match(line.strip())
    if not match:
        return None
    kind = match.group("kind")
    state_after = "contact" if kind == "TOQUE INICIO" else "idle"
    state_before = "idle" if kind == "TOQUE INICIO" else "contact"
    return TouchEvent(
        stamp=match.group("stamp"),
        kind=kind,
        state_before=state_before,
        state_after=state_after,
        raw=_to_float(match.group("raw")),
        filt=_to_float(match.group("filt")),
        dv=_to_float(match.group("dv")),
        duration_ms=None,
        source=match.group("source"),
    )


def parse_touch_csv_row(row: dict[str, str], *, last_state: str | None) -> TouchEvent | None:
    sample = parse_diag_csv_row(row)
    kind = "TOQUE INICIO" if sample.state == "contact" else "TOQUE FIN" if sample.state == "idle" else "TOUCH"
    if kind == "TOUCH":
        return None
    before = last_state or ("idle" if kind == "TOQUE INICIO" else "contact")
    return TouchEvent(
        stamp=f"t+{sample.t_ms}ms" if sample.t_ms is not None else "?",
        kind=kind,
        state_before=before,
        state_after=sample.state,
        raw=sample.raw,
        filt=sample.filt,
        dv=sample.dv,
        duration_ms=None,
        source="touch_events.csv",
    )


def find_latest_soak_folder(artifacts_root: Path) -> Path | None:
    if not artifacts_root.exists():
        return None
    candidates = [
        path
        for path in artifacts_root.iterdir()
        if path.is_dir()
        and path.name.startswith("fruit_soak_")
        and path.name != "fruit_soak_live"
        and path.name != DEMO_FOLDER_NAME
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def guess_detector_label(repo_root: Path) -> str:
    catalog_path = repo_root / "artifacts" / "firmware_catalog.json"
    if not catalog_path.exists():
        return "unknown"
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except Exception:
        return "unknown"

    artifacts = catalog.get("artifacts", [])
    fruit_artifacts = [a for a in artifacts if a.get("target_kind") == "fruit"]
    if not fruit_artifacts:
        fruit_artifacts = artifacts
    current = [a for a in fruit_artifacts if a.get("is_current")]
    candidates = current or fruit_artifacts

    def _sort_key(entry: dict[str, object]) -> tuple[str, str]:
        return (
            _norm_text(entry.get("created_at_utc"), ""),
            _norm_text(entry.get("version"), ""),
        )

    best = max(candidates, key=_sort_key)
    version = _norm_text(best.get("version"), "")
    display = _norm_text(best.get("display_name"), "")
    if version and display:
        return f"{version} | {display}"
    return version or display or "unknown"


def _state_color(state: str) -> str:
    state = state.lower()
    if state in {"idle", "unknown", ""}:
        return THEME.idle
    if state in {"contact", "touch_active"}:
        return THEME.accent
    if "possible" in state:
        return THEME.possible
    if "recovery" in state:
        return THEME.recovery
    return THEME.info


def _status_color(status: str) -> str:
    if status == "ACTIVE":
        return THEME.accent
    if status == "DEGRADED":
        return THEME.warning
    return THEME.danger


def _event_tone(kind: str) -> str:
    normalized = kind.lower()
    if normalized in {"toque inicio", "touch_active"}:
        return THEME.accent
    if normalized in {"toque fin", "touch_release"}:
        return "#14919B"
    if normalized == "possible_touch":
        return THEME.warning
    if normalized == "rejected":
        return THEME.danger
    if normalized == "state_change":
        return THEME.info
    if normalized == "recovery":
        return THEME.recovery
    if normalized == "timeout":
        return THEME.possible
    if normalized == "error":
        return THEME.danger
    return THEME.text


class DiagnosticsModel:
    def __init__(
        self,
        *,
        session: SessionPaths,
        label: str,
        max_samples: int,
        max_events: int,
        text_tail: int,
        stale_warn_sec: float,
    ) -> None:
        self.session = session
        self.label = label
        self.max_samples = max_samples
        self.max_events = max_events
        self.text_tail = text_tail
        self.stale_warn_sec = stale_warn_sec

        self.samples: deque[DiagSample] = deque(maxlen=max_samples)
        self.events: deque[TouchEvent] = deque(maxlen=max_events)
        self.diag_text_tail: deque[str] = deque(maxlen=text_tail)
        self.touch_text_tail: deque[str] = deque(maxlen=text_tail)
        self.invalid_rows = 0

        self.total_diag_rows = 0
        self.total_touch_rows = 0
        self.touch_starts = 0
        self.touch_ends = 0
        self.rejected = 0

        self.latest_state = "unknown"
        self.latest_phase = ""
        self.latest_mode = ""
        self.state_since_t_ms: int | None = None
        self.latest_t_ms: int | None = None
        self.latest_reason = "n/a"

        self.current_raw: float | None = None
        self.current_filt: float | None = None
        self.current_base: float | None = None
        self.current_dv: float | None = None
        self.current_sigma: float | None = None
        self.current_slope: float | None = None
        self.current_th_up: float | None = None
        self.current_th_down: float | None = None
        self.current_hold_down_ms: int | None = None
        self.current_hold_up_ms: int | None = None
        self.current_energy_age_ms: int | None = None
        self.current_recovery_ms: int | None = None
        self.current_rail = False

        self._diag_csv_reader = CsvTailReader(session.diag_csv)
        self._diag_log_reader = TextTailReader(session.diag_log)
        self._touch_csv_reader = CsvTailReader(session.touch_csv)
        self._touch_log_reader = TextTailReader(session.touch_log)

        self._touch_active_start_ms: int | None = None
        self._touch_active_wall_start: float | None = None
        self._touch_start_wall_times: deque[float] = deque(maxlen=1024)
        self._last_touch_state: str | None = None
        self._pending_candidate_start_ms: int | None = None
        self._pending_candidate_promoted = False
        self._last_cand: int | None = None

    def reset_buffers(self) -> None:
        self.samples.clear()
        self.events.clear()
        self.diag_text_tail.clear()
        self.touch_text_tail.clear()
        self.invalid_rows = 0
        self.total_diag_rows = 0
        self.total_touch_rows = 0
        self.touch_starts = 0
        self.touch_ends = 0
        self.rejected = 0
        self.latest_state = "unknown"
        self.latest_phase = ""
        self.latest_mode = ""
        self.state_since_t_ms = None
        self.latest_t_ms = None
        self.latest_reason = "n/a"
        self.current_raw = None
        self.current_filt = None
        self.current_base = None
        self.current_dv = None
        self.current_sigma = None
        self.current_slope = None
        self.current_th_up = None
        self.current_th_down = None
        self.current_hold_down_ms = None
        self.current_hold_up_ms = None
        self.current_energy_age_ms = None
        self.current_recovery_ms = None
        self.current_rail = False
        self._touch_active_start_ms = None
        self._touch_active_wall_start = None
        self._touch_start_wall_times.clear()
        self._last_touch_state = None
        self._pending_candidate_start_ms = None
        self._pending_candidate_promoted = False
        self._last_cand = None
        self._diag_csv_reader.reset()
        self._diag_log_reader.reset()
        self._touch_csv_reader.reset()
        self._touch_log_reader.reset()

    def reload_source(self, session: SessionPaths) -> None:
        self.session = session
        self._diag_csv_reader = CsvTailReader(session.diag_csv)
        self._diag_log_reader = TextTailReader(session.diag_log)
        self._touch_csv_reader = CsvTailReader(session.touch_csv)
        self._touch_log_reader = TextTailReader(session.touch_log)
        self.reset_buffers()

    def _push_event(self, event: TouchEvent) -> None:
        self.events.append(event)

    def _push_sample(self, sample: DiagSample) -> None:
        prev_state = self.latest_state or "unknown"
        self.samples.append(sample)
        self.total_diag_rows += 1
        self.latest_t_ms = sample.t_ms if sample.t_ms is not None else self.latest_t_ms
        self.current_raw = sample.raw
        self.current_filt = sample.filt
        self.current_base = sample.base
        self.current_dv = sample.dv
        self.current_sigma = sample.sigma
        self.current_slope = sample.slope
        self.current_th_up = sample.th_up
        self.current_th_down = sample.th_down
        self.current_hold_down_ms = sample.hold_down_ms
        self.current_hold_up_ms = sample.hold_up_ms
        self.current_energy_age_ms = sample.energy_age_ms
        self.current_recovery_ms = sample.recovery_ms
        self.current_rail = sample.rail
        self.latest_state = sample.state or "unknown"
        self.latest_phase = sample.phase or ""
        self.latest_mode = sample.mode or ""
        self.latest_reason = sample.summary_reason()
        if self.state_since_t_ms is None and sample.t_ms is not None:
            self.state_since_t_ms = sample.t_ms

        if sample.state and sample.state != prev_state:
            self.state_since_t_ms = sample.t_ms if sample.t_ms is not None else self.state_since_t_ms
            reason = sample.summary_reason()
            self._push_event(
                TouchEvent(
                    stamp=f"t+{sample.t_ms}ms" if sample.t_ms is not None else "?",
                    kind="state_change",
                    state_before=prev_state,
                    state_after=sample.state,
                    raw=sample.raw,
                    filt=sample.filt,
                    dv=sample.dv,
                    duration_ms=None,
                    source="diagnostic_values.csv",
                    note=reason,
                )
            )
            if sample.state == "contact":
                self._push_event(
                    TouchEvent(
                        stamp=f"t+{sample.t_ms}ms" if sample.t_ms is not None else "?",
                        kind="touch_active",
                        state_before=prev_state,
                        state_after=sample.state,
                        raw=sample.raw,
                        filt=sample.filt,
                        dv=sample.dv,
                        duration_ms=None,
                        source="diagnostic_values.csv",
                        note=reason,
                    )
                )
            if prev_state == "contact" and sample.state == "idle":
                self._push_event(
                    TouchEvent(
                        stamp=f"t+{sample.t_ms}ms" if sample.t_ms is not None else "?",
                        kind="touch_release",
                        state_before=prev_state,
                        state_after=sample.state,
                        raw=sample.raw,
                        filt=sample.filt,
                        dv=sample.dv,
                        duration_ms=None,
                        source="diagnostic_values.csv",
                        note=reason,
                    )
                )

        cand = sample.cand
        if cand is not None:
            if self._last_cand != cand and cand == 1 and sample.state == "idle":
                self._pending_candidate_start_ms = sample.t_ms
                self._pending_candidate_promoted = False
                self._push_event(
                    TouchEvent(
                        stamp=f"t+{sample.t_ms}ms" if sample.t_ms is not None else "?",
                        kind="possible_touch",
                        state_before="idle",
                        state_after="idle",
                        raw=sample.raw,
                        filt=sample.filt,
                        dv=sample.dv,
                        duration_ms=None,
                        source="diagnostic_values.csv",
                        note=sample.summary_reason(),
                    )
                )
            if sample.state == "contact" and self._pending_candidate_start_ms is not None:
                self._pending_candidate_promoted = True
            if self._last_cand == 1 and cand == 0 and sample.state == "idle":
                if self._pending_candidate_start_ms is not None and not self._pending_candidate_promoted:
                    self.rejected += 1
                    self._push_event(
                        TouchEvent(
                            stamp=f"t+{sample.t_ms}ms" if sample.t_ms is not None else "?",
                            kind="rejected",
                            state_before="idle",
                            state_after="idle",
                            raw=sample.raw,
                            filt=sample.filt,
                            dv=sample.dv,
                            duration_ms=None,
                            source="diagnostic_values.csv",
                            note="candidate expired without touch",
                        )
                    )
                self._pending_candidate_start_ms = None
                self._pending_candidate_promoted = False
            self._last_cand = cand

        if sample.state == "contact" and self._touch_active_start_ms is None:
            self._touch_active_start_ms = sample.t_ms
        elif sample.state == "idle" and self._touch_active_start_ms is not None:
            self._touch_active_start_ms = None

    def _normalized_last_state(self) -> str:
        return self.latest_state or "unknown"

    def _push_touch_event(self, event: TouchEvent) -> None:
        self._push_event(event)
        if event.kind == "TOQUE INICIO":
            self.touch_starts += 1
        elif event.kind == "TOQUE FIN":
            self.touch_ends += 1

    def ingest(self) -> None:
        diag_csv_rows = self._diag_csv_reader.read_new_rows()
        diag_log_lines = self._diag_log_reader.read_new_lines()
        touch_csv_rows = self._touch_csv_reader.read_new_rows()
        touch_log_lines = self._touch_log_reader.read_new_lines()

        for row in diag_csv_rows:
            try:
                sample = parse_diag_csv_row(row)
            except Exception:
                self.invalid_rows += 1
                continue
            self._push_sample(sample)

        if not diag_csv_rows and diag_log_lines:
            for line in diag_log_lines:
                sample = parse_diag_text_line(line)
                if sample is None:
                    continue
                self._push_sample(sample)
        if diag_log_lines:
            self.diag_text_tail.extend(diag_log_lines)
        elif diag_csv_rows:
            self.diag_text_tail.extend(_row_to_text(row) for row in diag_csv_rows)

        if touch_log_lines:
            for line in touch_log_lines:
                event = parse_touch_text_line(line)
                if event is None:
                    continue
                self.total_touch_rows += 1
                if event.kind == "TOQUE INICIO":
                    self.touch_starts += 1
                    self._touch_active_start_ms = self.latest_t_ms
                    self._touch_active_wall_start = time.time()
                    self._touch_start_wall_times.append(self._touch_active_wall_start)
                elif event.kind == "TOQUE FIN":
                    self.touch_ends += 1
                    duration = None
                    if self._touch_active_wall_start is not None:
                        duration = max(0, int((time.time() - self._touch_active_wall_start) * 1000))
                    event.duration_ms = duration
                    self._touch_active_start_ms = None
                    self._touch_active_wall_start = None
                self._push_event(event)
        elif touch_csv_rows:
            last_touch_state = self._last_touch_state
            for row in touch_csv_rows:
                try:
                    sample = parse_diag_csv_row(row)
                except Exception:
                    self.invalid_rows += 1
                    continue
                event = parse_touch_csv_row(row, last_state=last_touch_state)
                if event is None:
                    continue
                self.total_touch_rows += 1
                if event.kind == "TOQUE INICIO":
                    self.touch_starts += 1
                    self._touch_active_start_ms = sample.t_ms
                    self._touch_active_wall_start = time.time()
                    self._touch_start_wall_times.append(self._touch_active_wall_start)
                elif event.kind == "TOQUE FIN":
                    self.touch_ends += 1
                    duration = None
                    if self._touch_active_wall_start is not None:
                        duration = max(0, int((time.time() - self._touch_active_wall_start) * 1000))
                    event.duration_ms = duration
                    self._touch_active_start_ms = None
                    self._touch_active_wall_start = None
                self._push_touch_event(event)
                last_touch_state = sample.state
            self._last_touch_state = last_touch_state
        if touch_log_lines:
            self.touch_text_tail.extend(touch_log_lines)
        elif touch_csv_rows:
            self.touch_text_tail.extend(_row_to_text(row) for row in touch_csv_rows)

    def _window_samples(self, window_ms: int) -> list[DiagSample]:
        if not self.samples:
            return []
        latest = self.latest_t_ms
        if latest is None:
            return list(self.samples)
        cutoff = latest - window_ms
        return [sample for sample in self.samples if sample.t_ms is None or sample.t_ms >= cutoff]

    def _window_touch_starts(self, window_ms: int) -> list[int]:
        cutoff = time.time() - (window_ms / 1000.0)
        while self._touch_start_wall_times and self._touch_start_wall_times[0] < cutoff:
            self._touch_start_wall_times.popleft()
        return [int((stamp - cutoff) * 1000) for stamp in self._touch_start_wall_times]

    def _compute_file_age(self, path: Path) -> float | None:
        if not path.exists():
            return None
        try:
            return round((datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)).total_seconds(), 1)
        except OSError:
            return None

    def snapshot(self, window_ms: int) -> PanelSnapshot:
        window = self._window_samples(window_ms)
        latest = self.samples[-1] if self.samples else None
        latest_t_ms = self.latest_t_ms or 0
        start_t = self.state_since_t_ms
        state_age_ms = None
        if start_t is not None and self.latest_t_ms is not None:
            state_age_ms = max(0, self.latest_t_ms - start_t)

        touch_start_times = self._window_touch_starts(60000)
        events_per_min = float(len(touch_start_times))

        idle_count = sum(1 for sample in window if sample.state == "idle")
        contact_count = sum(1 for sample in window if sample.state == "contact")
        total = max(1, idle_count + contact_count)
        idle_ratio = round(100.0 * idle_count / total, 1)
        contact_ratio = round(100.0 * contact_count / total, 1)

        capture_health = "ACTIVE"
        diag_age = self._compute_file_age(self.session.diag_csv if self.session.diag_csv.exists() else self.session.diag_log)
        touch_age = self._compute_file_age(self.session.touch_log if self.session.touch_log.exists() else self.session.touch_csv)
        if diag_age is None:
            capture_health = "OFFLINE"
        elif diag_age > self.stale_warn_sec:
            capture_health = "DEGRADED"
        elif touch_age is None:
            capture_health = "DEGRADED"

        return PanelSnapshot(
            label=self.label,
            folder=str(self.session.folder),
            diag_source=self.session.diag_csv.name if self.session.diag_csv.exists() else self.session.diag_log.name,
            touch_source=self.session.touch_log.name if self.session.touch_log.exists() else self.session.touch_csv.name,
            diag_age_s=diag_age,
            touch_age_s=touch_age,
            latest_state=self.latest_state,
            latest_phase=self.latest_phase,
            latest_mode=self.latest_mode,
            state_age_ms=state_age_ms,
            events_per_min=events_per_min,
            touch_starts=self.touch_starts,
            touch_ends=self.touch_ends,
            rejected=self.rejected,
            total_diag_rows=self.total_diag_rows,
            total_touch_rows=self.total_touch_rows,
            invalid_rows=self.invalid_rows,
            current_raw=self.current_raw,
            current_filt=self.current_filt,
            current_base=self.current_base,
            current_dv=self.current_dv,
            current_sigma=self.current_sigma,
            current_slope=self.current_slope,
            current_th_up=self.current_th_up,
            current_th_down=self.current_th_down,
            current_hold_down_ms=self.current_hold_down_ms,
            current_hold_up_ms=self.current_hold_up_ms,
            current_energy_age_ms=self.current_energy_age_ms,
            current_recovery_ms=self.current_recovery_ms,
            current_reason=self.latest_reason,
            rail=self.current_rail,
            capture_health=capture_health,
            contact_ratio_pct=contact_ratio,
            idle_ratio_pct=idle_ratio,
        )

    def export_snapshot(self, out_dir: Path, window_ms: int) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = out_dir / f"live_diagnostics_panel_{stamp}"
        folder.mkdir(parents=True, exist_ok=True)

        snapshot = self.snapshot(window_ms)
        (folder / "snapshot.json").write_text(json.dumps(asdict(snapshot), indent=2, ensure_ascii=False), encoding="utf-8")

        diag_lines = "\n".join(self.diag_text_tail)
        touch_lines = "\n".join(self.touch_text_tail)
        (folder / "diagnostic_tail.log").write_text(diag_lines + ("\n" if diag_lines else ""), encoding="utf-8")
        (folder / "touch_tail.log").write_text(touch_lines + ("\n" if touch_lines else ""), encoding="utf-8")

        events_path = folder / "events.csv"
        with events_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["stamp", "kind", "state_before", "state_after", "raw", "filt", "dv", "duration_ms", "source", "note"])
            for event in self.events:
                writer.writerow(
                    [
                        event.stamp,
                        event.kind,
                        event.state_before,
                        event.state_after,
                        _fmt_float(event.raw),
                        _fmt_float(event.filt),
                        _fmt_float(event.dv),
                        _fmt_int(event.duration_ms),
                        event.source,
                        event.note,
                    ]
                )
        return folder


def build_session_paths(folder: Path) -> SessionPaths:
    return SessionPaths(
        folder=folder,
        diag_csv=folder / "diagnostic_values.csv",
        diag_log=folder / "diagnostic_values.log",
        touch_csv=folder / "touch_events.csv",
        touch_log=folder / "touch_events.log",
    )


def tail_lines(path: Path, max_lines: int = 12) -> list[str]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [line for line in lines[-max_lines:] if line.strip()]


def generate_demo_session(root: Path) -> SessionPaths:
    folder = root / DEMO_FOLDER_NAME
    folder.mkdir(parents=True, exist_ok=True)
    diag_csv = folder / "diagnostic_values.csv"
    diag_log = folder / "diagnostic_values.log"
    touch_csv = folder / "touch_events.csv"
    touch_log = folder / "touch_events.log"

    if not diag_csv.exists():
        with diag_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "base",
                    "cand",
                    "dv",
                    "energy_age_ms",
                    "exit",
                    "filt",
                    "hold_down_ms",
                    "hold_up_ms",
                    "id",
                    "mode",
                    "node",
                    "pending_sign",
                    "phase",
                    "prev",
                    "raw",
                    "recovery_ms",
                    "ref",
                    "sigma",
                    "slope",
                    "state",
                    "t_ms",
                    "th_down",
                    "th_up",
                    "touch_sign",
                    "vmax",
                    "vmin",
                ]
            )
            t_ms = 0
            for index in range(800):
                state = "contact" if 220 <= index <= 340 or 540 <= index <= 580 else "idle"
                raw = 1.85 if state == "idle" else 1.74
                filt = raw + (0.02 * math.sin(index / 9.0))
                base = 1.86 + (0.005 * math.sin(index / 75.0))
                dv = filt - base
                hold_down = 0 if state == "idle" else (index % 33) * 10
                hold_up = 0 if state == "contact" else (index % 21) * 12
                writer.writerow(
                    [
                        f"{base:.4f}",
                        1 if state == "contact" else 0,
                        f"{dv:.4f}",
                        index * 75,
                        0,
                        f"{filt:.4f}",
                        hold_down,
                        hold_up,
                        1,
                        "fruit",
                        "EB1",
                        1 if state == "contact" else -1,
                        "track",
                        "idle" if index == 0 else ("contact" if state == "contact" else "contact" if index in (220, 540) else "idle"),
                        f"{raw:.4f}",
                        0,
                        0,
                        0.003 + 0.002 * math.sin(index / 11.0),
                        0.12 * math.sin(index / 6.0),
                        state,
                        t_ms,
                        0.0252,
                        0.0420,
                        1 if state == "contact" else 0,
                        1.9671,
                        1.6641,
                    ]
                )
                t_ms += 260
        diag_log.write_text("\n".join(tail_lines(diag_csv, 40)), encoding="utf-8")
        touch_log.write_text(
            "\n".join(
                [
                    "[09:31:10.133] 198.51.100.17:51374 EB1#1 TOQUE INICIO raw=1.7470 filt=1.8145 dv=0.0421",
                    "[09:31:22.833] 198.51.100.17:51374 EB1#1 TOQUE FIN raw=1.8654 filt=1.8521 dv=0.0102",
                    "[09:35:11.521] 198.51.100.17:51374 EB1#1 TOQUE INICIO raw=1.7392 filt=1.8112 dv=0.0487",
                    "[09:35:25.287] 198.51.100.17:51374 EB1#1 TOQUE FIN raw=1.8731 filt=1.8508 dv=0.0110",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    return build_session_paths(folder)


class LiveDiagnosticsPanel(tk.Tk):
    def __init__(
        self,
        *,
        session: SessionPaths,
        label: str,
        refresh_ms: int,
        window_seconds: int,
        max_samples: int,
        max_events: int,
        text_tail: int,
        stale_warn_sec: float,
        follow_latest: bool,
        demo_mode: bool,
    ) -> None:
        super().__init__()
        self.session = session
        self.label = label
        self.refresh_ms = refresh_ms
        self.window_seconds = window_seconds
        self.max_samples = max_samples
        self.max_events = max_events
        self.text_tail = text_tail
        self.stale_warn_sec = stale_warn_sec
        self.follow_latest = follow_latest
        self.demo_mode = demo_mode

        self.title("OKUA Fruit Live Diagnostics")
        self.geometry("1680x1020")
        try:
            self.state("zoomed")
        except tk.TclError:
            pass

        self.configure(bg=THEME.app_bg)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.model = DiagnosticsModel(
            session=session,
            label=label,
            max_samples=max_samples,
            max_events=max_events,
            text_tail=text_tail,
            stale_warn_sec=stale_warn_sec,
        )

        self._build_style()
        self._build_ui()
        self._last_folder = session.folder
        self._last_refresh = time.monotonic()
        self._paused = False
        self._boot_demo = demo_mode
        self.after(50, self.refresh_view)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            ".",
            background=THEME.app_bg,
            foreground=THEME.text,
            fieldbackground=THEME.surface,
        )
        style.configure("App.TFrame", background=THEME.app_bg)
        style.configure("Surface.TFrame", background=THEME.surface)
        style.configure("SurfaceAlt.TFrame", background=THEME.surface_alt)
        style.configure("Card.TFrame", background=THEME.surface, borderwidth=1, relief="solid")
        style.configure("Toolbar.TFrame", background=THEME.surface_soft)
        style.configure("TFrame", background=THEME.app_bg)
        style.configure("TLabel", background=THEME.app_bg, foreground=THEME.text)
        style.configure("AppTitle.TLabel", background=THEME.app_bg, foreground=THEME.text, font=("Segoe UI", 18, "bold"))
        style.configure("AppSub.TLabel", background=THEME.app_bg, foreground=THEME.text_soft, font=("Segoe UI", 9))
        style.configure("SectionTitle.TLabel", background=THEME.app_bg, foreground=THEME.text, font=("Segoe UI", 10, "bold"))
        style.configure("SectionHint.TLabel", background=THEME.app_bg, foreground=THEME.text_soft, font=("Segoe UI", 8))
        style.configure("CardTitle.TLabel", background=THEME.surface, foreground=THEME.text_soft, font=("Segoe UI", 8, "bold"))
        style.configure("CardValue.TLabel", background=THEME.surface, foreground=THEME.text, font=("Segoe UI", 11, "bold"))
        style.configure("CardHint.TLabel", background=THEME.surface, foreground=THEME.text_soft, font=("Segoe UI", 8))
        style.configure("TButton", background=THEME.surface, foreground=THEME.text, padding=(10, 5))
        style.map(
            "TButton",
            background=[("active", THEME.surface_soft), ("pressed", THEME.border_soft)],
            foreground=[("disabled", THEME.muted)],
        )
        style.configure("Accent.TButton", background=THEME.accent, foreground=THEME.white, padding=(12, 6))
        style.map("Accent.TButton", background=[("active", THEME.accent_dark), ("pressed", THEME.accent_dark)])
        style.configure("Danger.TButton", background=THEME.danger, foreground=THEME.white, padding=(12, 6))
        style.map("Danger.TButton", background=[("active", "#A63F34"), ("pressed", "#8F332B")])
        style.configure("Ghost.TButton", background=THEME.surface, foreground=THEME.text, padding=(10, 5))
        style.configure("TCheckbutton", background=THEME.app_bg, foreground=THEME.text)
        style.configure("TLabelframe", background=THEME.app_bg, foreground=THEME.text)
        style.configure("TLabelframe.Label", background=THEME.app_bg, foreground=THEME.text_soft)
        style.configure(
            "Treeview",
            background=THEME.surface,
            fieldbackground=THEME.surface,
            foreground=THEME.text,
            rowheight=24,
            bordercolor=THEME.border,
            lightcolor=THEME.border,
            darkcolor=THEME.border,
        )
        style.configure(
            "Treeview.Heading",
            background=THEME.surface_soft,
            foreground=THEME.text,
            font=("Segoe UI", 9, "bold"),
        )
        style.map("Treeview", background=[("selected", THEME.accent)], foreground=[("selected", THEME.white)])
        style.configure("TNotebook", background=THEME.app_bg, borderwidth=0)
        style.configure("TNotebook.Tab", background=THEME.surface_soft, foreground=THEME.text_soft, padding=(12, 5))
        style.map(
            "TNotebook.Tab",
            background=[("selected", THEME.surface), ("active", THEME.surface)],
            foreground=[("selected", THEME.text), ("active", THEME.text)],
        )
        style.configure("Horizontal.TSeparator", background=THEME.border)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(6, weight=1)

        self.toolbar = ttk.Frame(self, padding=(14, 12, 14, 8), style="App.TFrame")
        self.toolbar.grid(row=0, column=0, sticky="ew")
        self.toolbar.columnconfigure(0, weight=1)
        self.toolbar.columnconfigure(1, weight=0)

        self.title_stack = ttk.Frame(self.toolbar, style="App.TFrame")
        self.title_stack.grid(row=0, column=0, sticky="w")
        ttk.Label(self.title_stack, text="OKUA Fruit Live Diagnostics", style="AppTitle.TLabel").grid(row=0, column=0, sticky="w")
        subtitle = f"{self.label} | {self.session.folder.name}" if self.label else self.session.folder.name
        self.header_subtitle_label = ttk.Label(
            self.title_stack,
            text=f"Live signal, FSM, events and raw tails for field diagnosis | {subtitle}",
            style="AppSub.TLabel",
        )
        self.header_subtitle_label.grid(row=1, column=0, sticky="w", pady=(2, 0))

        self.info_strip = ttk.Frame(self.title_stack, style="App.TFrame")
        self.info_strip.grid(row=2, column=0, sticky="w", pady=(8, 0))
        self._info_strip_labels: dict[str, ttk.Label] = {}
        self.mode_badge = tk.Label(self.info_strip, text="LIVE", bg=THEME.accent, fg=THEME.white, padx=10, pady=3)
        self.mode_badge.grid(row=0, column=0, sticky="w", padx=(0, 14))
        for idx, (key, text) in enumerate(
            [
                ("session", f"Session: {self.session.folder.name}"),
                ("source", f"Source: {self.model.session.diag_csv.name}"),
                ("follow", "Follow latest: on" if self.follow_latest else "Follow latest: off"),
            ]
        ):
            chip = ttk.Label(self.info_strip, text=text, style="SectionHint.TLabel")
            chip.grid(row=0, column=idx + 1, sticky="w", padx=(0, 14))
            self._info_strip_labels[key] = chip

        self.controls_stack = ttk.Frame(self.toolbar, style="App.TFrame")
        self.controls_stack.grid(row=0, column=1, sticky="e")
        self.controls_stack.columnconfigure(0, weight=1)
        self.controls_stack.columnconfigure(1, weight=1)

        self.controls_row = ttk.Frame(self.controls_stack, style="App.TFrame")
        self.controls_row.grid(row=0, column=0, sticky="e")
        self.btn_pause = ttk.Button(self.controls_row, text="Pause", style="Accent.TButton", command=self.toggle_pause)
        self.btn_pause.grid(row=0, column=0, padx=(0, 8))
        self.btn_clear = ttk.Button(self.controls_row, text="Clear", command=self.clear_view)
        self.btn_clear.grid(row=0, column=1, padx=(0, 8))
        self.btn_save = ttk.Button(self.controls_row, text="Save Snapshot", command=self.save_snapshot)
        self.btn_save.grid(row=0, column=2, padx=(0, 8))
        self.btn_open = ttk.Button(self.controls_row, text="Open Folder", command=self.open_folder)
        self.btn_open.grid(row=0, column=3, padx=(0, 8))
        self.btn_follow = ttk.Button(self.controls_row, text="Follow Latest", command=self.enable_follow_latest)
        self.btn_follow.grid(row=0, column=4, padx=(0, 8))
        self.btn_demo = ttk.Button(self.controls_row, text="Demo", command=self.load_demo)
        self.btn_demo.grid(row=0, column=5, padx=(0, 8))
        self.btn_close = ttk.Button(self.controls_row, text="Stop", style="Danger.TButton", command=self.on_close)
        self.btn_close.grid(row=0, column=6)

        self.controls_meta = ttk.Frame(self.controls_stack, style="App.TFrame")
        self.controls_meta.grid(row=1, column=0, sticky="e", pady=(8, 0))
        ttk.Label(self.controls_meta, text="Window s", style="SectionHint.TLabel").grid(row=0, column=0, padx=(0, 4))
        self.window_var = tk.IntVar(value=self.window_seconds)
        self.window_combo = ttk.Combobox(
            self.controls_meta,
            width=8,
            values=[10, 30, 60, 300],
            textvariable=self.window_var,
            state="readonly",
        )
        self.window_combo.grid(row=0, column=1, sticky="w")
        self.window_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_window_changed())

        ttk.Label(self.controls_meta, text="Refresh ms", style="SectionHint.TLabel").grid(row=0, column=2, padx=(12, 4))
        self.refresh_var = tk.IntVar(value=self.refresh_ms)
        self.refresh_combo = ttk.Combobox(
            self.controls_meta,
            width=8,
            values=[250, 500, 1000, 1500],
            textvariable=self.refresh_var,
            state="readonly",
        )
        self.refresh_combo.grid(row=0, column=3, sticky="w")
        self.refresh_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_refresh_changed())

        self.follow_var = tk.BooleanVar(value=self.follow_latest)
        self.follow_check = ttk.Checkbutton(
            self.controls_meta,
            text="Auto follow latest",
            variable=self.follow_var,
            command=self._sync_header_context,
        )
        self.follow_check.grid(row=0, column=4, padx=(12, 0))

        ttk.Separator(self, orient=tk.HORIZONTAL).grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))

        self.overview_title = ttk.Label(self, text="Operational overview", style="SectionTitle.TLabel")
        self.overview_title.grid(row=2, column=0, sticky="w", padx=16, pady=(0, 4))

        self.summary_frame = ttk.Frame(self, padding=(12, 0, 12, 8), style="App.TFrame")
        self.summary_frame.grid(row=3, column=0, sticky="ew")
        for index in range(4):
            self.summary_frame.columnconfigure(index, weight=1)

        self._summary_labels: dict[str, ttk.Label] = {}
        self._summary_chips: dict[str, tk.Label] = {}
        summary_items = [
            ("label", "Detector"),
            ("state", "State"),
            ("phase", "Phase"),
            ("mode", "Mode"),
            ("diag", "Diag"),
            ("touch", "Touch"),
            ("events", "Events/min"),
            ("touches", "Touch count"),
            ("reject", "Rejected"),
            ("rail", "Rail"),
            ("reason", "Last reason"),
            ("health", "Health"),
        ]
        for column, (key, title) in enumerate(summary_items):
            row = column // 4
            col = column % 4
            box = ttk.Frame(self.summary_frame, style="Card.TFrame", padding=(10, 8))
            box.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
            box.columnconfigure(0, weight=1)
            ttk.Label(box, text=title, style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
            value = ttk.Label(box, text="?", style="CardValue.TLabel", wraplength=250, justify="left")
            value.grid(row=1, column=0, sticky="w")
            self._summary_labels[key] = value
            if key == "state":
                chip = tk.Label(box, text="UNKNOWN", bg=THEME.idle, fg=THEME.white, padx=8, pady=3)
                chip.grid(row=2, column=0, sticky="w", pady=(4, 0))
                self._summary_chips["state"] = chip
            if key == "health":
                chip = tk.Label(box, text="OFFLINE", bg=THEME.danger, fg=THEME.white, padx=8, pady=3)
                chip.grid(row=2, column=0, sticky="w", pady=(4, 0))
                self._summary_chips["health"] = chip

        self.metrics_title = ttk.Label(self, text="Signal metrics", style="SectionTitle.TLabel")
        self.metrics_title.grid(row=4, column=0, sticky="w", padx=16, pady=(0, 4))

        self.stats_frame = ttk.Frame(self, padding=(12, 0, 12, 8), style="App.TFrame")
        self.stats_frame.grid(row=5, column=0, sticky="ew")
        for index in range(4):
            self.stats_frame.columnconfigure(index, weight=1)
        self.metric_labels: dict[str, ttk.Label] = {}
        metrics = [
            ("raw", "Raw"),
            ("filt", "Filt"),
            ("base", "Base"),
            ("dv", "DV"),
            ("sigma", "Sigma"),
            ("slope", "Slope"),
            ("hold_down", "Hold down"),
            ("hold_up", "Hold up"),
        ]
        for idx, (key, title) in enumerate(metrics):
            row = idx // 4
            col = idx % 4
            box = ttk.Frame(self.stats_frame, style="Card.TFrame", padding=(10, 8))
            box.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
            box.columnconfigure(0, weight=1)
            ttk.Label(box, text=title, style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
            value = ttk.Label(box, text="?", style="CardValue.TLabel")
            value.grid(row=1, column=0, sticky="w")
            self.metric_labels[key] = value

        self.body = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        self.body.grid(row=6, column=0, sticky="nsew", padx=12, pady=(0, 10))
        self.left_panel = ttk.Frame(self.body, padding=(0, 0, 8, 0), style="App.TFrame")
        self.right_panel = ttk.Frame(self.body, padding=(8, 0, 0, 0), style="App.TFrame")
        self.body.add(self.left_panel, weight=3)
        self.body.add(self.right_panel, weight=2)
        self.left_panel.columnconfigure(0, weight=1)
        self.left_panel.rowconfigure(0, weight=1)

        self.figure = Figure(figsize=(8, 6), dpi=100, facecolor=THEME.app_bg)
        self.ax_signal = self.figure.add_subplot(211)
        self.ax_metrics = self.figure.add_subplot(212)
        for axis in (self.ax_signal, self.ax_metrics):
            axis.set_facecolor(THEME.surface)
            axis.tick_params(colors=THEME.text_soft, labelsize=8)
            for spine in axis.spines.values():
                spine.set_color(THEME.border)
            axis.grid(True, color=THEME.border_soft, alpha=0.7, linewidth=0.7)
        self.ax_signal.set_title("Signal vs baseline", color=THEME.text, fontsize=10, fontweight="bold")
        self.ax_metrics.set_title("Detection metrics", color=THEME.text, fontsize=10, fontweight="bold")
        self.ax_signal.set_ylabel("V", color=THEME.text)
        self.ax_metrics.set_ylabel("Value", color=THEME.text)
        self.ax_metrics.set_xlabel("Seconds in window", color=THEME.text)
        self.figure.tight_layout(pad=1.4)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.left_panel)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.grid(row=0, column=0, sticky="nsew")

        self.sidebar_notebook = ttk.Notebook(self.right_panel)
        self.sidebar_notebook.grid(row=0, column=0, sticky="nsew")
        self.right_panel.rowconfigure(0, weight=1)
        self.right_panel.columnconfigure(0, weight=1)

        self.events_tab = ttk.Frame(self.sidebar_notebook, style="App.TFrame")
        self.logs_tab = ttk.Frame(self.sidebar_notebook, style="App.TFrame")
        self.sidebar_notebook.add(self.events_tab, text="Events")
        self.sidebar_notebook.add(self.logs_tab, text="Logs")

        self.events_frame = ttk.Labelframe(self.events_tab, text="Recent events", padding=(8, 6))
        self.events_frame.grid(row=0, column=0, sticky="nsew")
        self.events_tab.columnconfigure(0, weight=1)
        self.events_tab.rowconfigure(0, weight=1)
        self.events_frame.columnconfigure(0, weight=1)
        self.events_tab.bind("<Map>", lambda _event: self.sidebar_notebook.select(self.events_tab))
        self.events_tree = ttk.Treeview(
            self.events_frame,
            columns=("stamp", "kind", "state", "reason", "dv", "raw", "base", "duration"),
            show="headings",
            height=16,
        )
        for col, text, width in [
            ("stamp", "Time", 92),
            ("kind", "Kind", 110),
            ("state", "State", 90),
            ("reason", "Reason", 240),
            ("dv", "DV", 70),
            ("raw", "Raw", 70),
            ("base", "Base", 70),
            ("duration", "Dur", 70),
        ]:
            self.events_tree.heading(col, text=text)
            self.events_tree.column(col, width=width, anchor="w", stretch=True)
        self.events_tree.grid(row=0, column=0, sticky="nsew")
        event_scroll = ttk.Scrollbar(self.events_frame, orient=tk.VERTICAL, command=self.events_tree.yview)
        event_scroll.grid(row=0, column=1, sticky="ns")
        self.events_tree.configure(yscrollcommand=event_scroll.set)
        self.events_tree.tag_configure("touch_start", foreground=THEME.accent)
        self.events_tree.tag_configure("touch_end", foreground="#14919B")
        self.events_tree.tag_configure("possible_touch", foreground=THEME.warning)
        self.events_tree.tag_configure("rejected", foreground=THEME.danger)
        self.events_tree.tag_configure("state_change", foreground=THEME.info)
        self.events_tree.tag_configure("recovery", foreground=THEME.recovery)

        self.raw_frame = ttk.Labelframe(self.logs_tab, text="Raw logs", padding=(10, 8))
        self.raw_frame.grid(row=0, column=0, sticky="nsew")
        self.logs_tab.columnconfigure(0, weight=1)
        self.logs_tab.rowconfigure(0, weight=1)
        self.raw_frame.columnconfigure(0, weight=1)
        self.raw_frame.rowconfigure(0, weight=1)
        self.raw_notebook = ttk.Notebook(self.raw_frame)
        self.raw_notebook.grid(row=0, column=0, sticky="nsew")
        self.diag_text = scrolledtext.ScrolledText(
            self.raw_notebook,
            height=10,
            bg=THEME.surface,
            fg=THEME.text,
            insertbackground=THEME.text,
            wrap=tk.NONE,
            font=("Consolas", 9),
        )
        self.touch_text = scrolledtext.ScrolledText(
            self.raw_notebook,
            height=10,
            bg=THEME.surface,
            fg=THEME.text,
            insertbackground=THEME.text,
            wrap=tk.NONE,
            font=("Consolas", 9),
        )
        self.diag_text.configure(state=tk.DISABLED)
        self.touch_text.configure(state=tk.DISABLED)
        self.raw_notebook.add(self.diag_text, text="Diagnostic")
        self.raw_notebook.add(self.touch_text, text="Touch")
        self._sync_header_context()

    def _on_window_changed(self) -> None:
        self.window_seconds = int(self.window_var.get())

    def _on_refresh_changed(self) -> None:
        self.refresh_ms = int(self.refresh_var.get())

    def _sync_header_context(self) -> None:
        subtitle = f"{self.label} | {self.session.folder.name}" if self.label else self.session.folder.name
        is_demo = self.demo_mode or self.session.folder.name == DEMO_FOLDER_NAME
        self.mode_badge.configure(
            text="DEMO" if is_demo else "LIVE",
            bg=THEME.warning if is_demo else THEME.accent,
        )
        self.header_subtitle_label.configure(
            text=f"Live signal, FSM, events and raw tails for field diagnosis | {subtitle}"
            + (" | DEMO SESSION" if is_demo else "")
        )
        if "session" in self._info_strip_labels:
            self._info_strip_labels["session"].configure(text=f"Session: {self.session.folder.name}")
        if "source" in self._info_strip_labels:
            self._info_strip_labels["source"].configure(text=f"Source: {self.model.session.diag_csv.name}")
        if "follow" in self._info_strip_labels:
            self._info_strip_labels["follow"].configure(
                text="Follow latest: on" if self.follow_var.get() else "Follow latest: off"
            )

    def toggle_pause(self) -> None:
        self._paused = not self._paused
        self.btn_pause.configure(text="Resume" if self._paused else "Pause")

    def clear_view(self) -> None:
        self.model.diag_text_tail.clear()
        self.model.touch_text_tail.clear()
        self.model.events.clear()
        self.events_tree.delete(*self.events_tree.get_children())
        self._render_text_widget(self.diag_text, [])
        self._render_text_widget(self.touch_text, [])

    def save_snapshot(self) -> None:
        out_dir = ARTIFACTS_ROOT / "live_diagnostics_panel"
        folder = self.model.export_snapshot(out_dir, self.window_seconds * 1000)
        messagebox.showinfo("Snapshot saved", f"Snapshot saved in:\n{folder}")

    def open_folder(self) -> None:
        folder = filedialog.askdirectory(initialdir=str(self.session.folder))
        if not folder:
            return
        self.follow_var.set(False)
        self.load_folder(Path(folder))

    def enable_follow_latest(self) -> None:
        self.follow_var.set(True)
        latest = find_latest_soak_folder(ARTIFACTS_ROOT)
        if latest is not None:
            self.load_folder(latest)

    def load_demo(self) -> None:
        self.follow_var.set(False)
        demo = generate_demo_session(ARTIFACTS_ROOT)
        self.demo_mode = True
        self.load_folder(demo.folder)

    def load_folder(self, folder: Path) -> None:
        session = build_session_paths(folder)
        self.session = session
        self.demo_mode = folder.name == DEMO_FOLDER_NAME
        self.model.reload_source(session)
        self._last_folder = folder
        self._boot_demo = False
        self.clear_view()
        self._sync_header_context()

    def on_close(self) -> None:
        self.destroy()

    def _maybe_refresh_source(self) -> None:
        if not self.follow_var.get():
            return
        latest = find_latest_soak_folder(ARTIFACTS_ROOT)
        if latest is None or latest == self._last_folder:
            return
        self.load_folder(latest)

    def _render_text_widget(self, widget: scrolledtext.ScrolledText, lines: Iterable[str]) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        for line in lines:
            widget.insert(tk.END, line + "\n")
        widget.see(tk.END)
        widget.configure(state=tk.DISABLED)

    def _render_events(self) -> None:
        rows = list(self.model.events)[-120:]
        self.events_tree.delete(*self.events_tree.get_children())
        for idx, event in enumerate(rows[::-1]):
            state = event.state_after or event.state_before or "?"
            kind_norm = event.kind.lower()
            if kind_norm in {"toque inicio", "touch_active"}:
                tags = ("touch_start",)
            elif kind_norm in {"toque fin", "touch_release"}:
                tags = ("touch_end",)
            elif kind_norm == "possible_touch":
                tags = ("possible_touch",)
            elif kind_norm == "rejected":
                tags = ("rejected",)
            elif kind_norm == "state_change":
                tags = ("state_change",)
            elif kind_norm in {"recovery", "baseline_reset"}:
                tags = ("recovery",)
            else:
                tags = ()
            self.events_tree.insert(
                "",
                tk.END,
                iid=str(idx),
                values=(
                    _fmt_ts_from_log(event.stamp),
                    event.kind,
                    state,
                    event.note[:70],
                    _fmt_float(event.dv),
                    _fmt_float(event.raw),
                    _fmt_float(event.filt),
                    _fmt_ms(event.duration_ms),
                ),
                tags=tags,
            )

    def _update_summary(self, snapshot: PanelSnapshot) -> None:
        self._summary_labels["label"].configure(text=snapshot.label)
        self._summary_labels["state"].configure(
            text=f"{snapshot.latest_state.upper()} | {_fmt_ms(snapshot.state_age_ms)}"
        )
        self._summary_labels["phase"].configure(text=snapshot.latest_phase.upper() if snapshot.latest_phase else "?")
        self._summary_labels["mode"].configure(text=snapshot.latest_mode.upper() if snapshot.latest_mode else "?")
        self._summary_labels["diag"].configure(
            text=f"{snapshot.diag_source} | age {_fmt_float(snapshot.diag_age_s, 1)} s"
        )
        self._summary_labels["touch"].configure(
            text=f"{snapshot.touch_source} | age {_fmt_float(snapshot.touch_age_s, 1)} s"
        )
        self._summary_labels["events"].configure(text=f"{snapshot.events_per_min:.1f}")
        self._summary_labels["touches"].configure(
            text=f"starts={snapshot.touch_starts} ends={snapshot.touch_ends} total={len(self.model.events)}"
        )
        self._summary_labels["reject"].configure(text=str(snapshot.rejected))
        self._summary_labels["rail"].configure(
            text="YES" if snapshot.rail else "NO",
            foreground=THEME.danger if snapshot.rail else THEME.accent,
        )
        self._summary_labels["reason"].configure(
            text=snapshot.current_reason[:72],
            foreground=THEME.recovery if "recovery" in snapshot.current_reason.lower() else THEME.text,
        )
        self._summary_labels["health"].configure(text=snapshot.capture_health)

        self._summary_chips["state"].configure(text=snapshot.latest_state.upper(), bg=_state_color(snapshot.latest_state))
        self._summary_chips["health"].configure(text=snapshot.capture_health, bg=_status_color(snapshot.capture_health))

        self.metric_labels["raw"].configure(text=_fmt_float(snapshot.current_raw), foreground=THEME.raw)
        self.metric_labels["filt"].configure(text=_fmt_float(snapshot.current_filt), foreground=THEME.filt)
        self.metric_labels["base"].configure(text=_fmt_float(snapshot.current_base), foreground=THEME.base)
        self.metric_labels["dv"].configure(text=_fmt_float(snapshot.current_dv), foreground=THEME.dv)
        self.metric_labels["sigma"].configure(text=_fmt_float(snapshot.current_sigma), foreground=THEME.sigma)
        self.metric_labels["slope"].configure(text=_fmt_float(snapshot.current_slope), foreground=THEME.slope)
        self.metric_labels["hold_down"].configure(text=_fmt_ms(snapshot.current_hold_down_ms))
        self.metric_labels["hold_up"].configure(text=_fmt_ms(snapshot.current_hold_up_ms))

        events_tone = THEME.accent
        if snapshot.events_per_min >= 10.0:
            events_tone = THEME.danger
        elif snapshot.events_per_min >= 5.0:
            events_tone = THEME.warning
        self._summary_labels["events"].configure(foreground=events_tone)
        self._summary_labels["diag"].configure(
            foreground=THEME.danger if snapshot.diag_age_s is not None and snapshot.diag_age_s > self.stale_warn_sec else THEME.text
        )
        self._summary_labels["touch"].configure(
            foreground=THEME.text_soft
        )

    def _render_plots(self, snapshot: PanelSnapshot) -> None:
        window_ms = self.window_seconds * 1000
        samples = self.model._window_samples(window_ms)
        if not samples:
            self.ax_signal.clear()
            self.ax_metrics.clear()
            self.figure.tight_layout(pad=1.4)
            self.canvas.draw_idle()
            return

        latest_t_ms = self.model.latest_t_ms or samples[-1].t_ms or 0
        xs = [
            ((sample.t_ms if sample.t_ms is not None else latest_t_ms) - latest_t_ms) / 1000.0
            for sample in samples
        ]
        raws = [sample.raw for sample in samples]
        filts = [sample.filt for sample in samples]
        bases = [sample.base for sample in samples]
        dvs = [sample.dv for sample in samples]
        slopes = [sample.slope for sample in samples]
        sigmas = [sample.sigma for sample in samples]
        th_up = snapshot.current_th_up
        th_down = snapshot.current_th_down

        self.ax_signal.clear()
        self.ax_metrics.clear()
        for axis in (self.ax_signal, self.ax_metrics):
            axis.set_facecolor(THEME.surface)
            axis.tick_params(colors=THEME.text_soft, labelsize=8)
            for spine in axis.spines.values():
                spine.set_color(THEME.border)
            axis.grid(True, color=THEME.border_soft, alpha=0.75, linewidth=0.7)

        self.ax_signal.plot(xs, raws, color=THEME.raw, linewidth=1.7, label="raw")
        self.ax_signal.plot(xs, filts, color=THEME.filt, linewidth=1.5, label="filt")
        self.ax_signal.plot(xs, bases, color=THEME.base, linewidth=1.3, label="base")
        if th_up is not None:
            self.ax_signal.axhline(th_up, color=THEME.danger, linestyle="--", linewidth=1.0, label="th_up")
        if th_down is not None:
            self.ax_signal.axhline(th_down, color=THEME.recovery, linestyle="--", linewidth=1.0, label="th_down")
        self.ax_signal.set_xlim(min(xs), 0.0)
        y_values = [value for value in raws + filts + bases if value is not None]
        if y_values:
            y_min = min(y_values) - 0.08
            y_max = max(y_values) + 0.08
            if math.isclose(y_min, y_max):
                y_min -= 0.1
                y_max += 0.1
            self.ax_signal.set_ylim(y_min, y_max)
        self.ax_signal.set_title("Signal vs baseline", color=THEME.text, fontsize=10, fontweight="bold")
        self.ax_signal.set_ylabel("V", color=THEME.text)
        self.ax_signal.legend(loc="upper left", fontsize=8, frameon=False, labelcolor=THEME.text)

        self.ax_metrics.plot(xs, dvs, color=THEME.dv, linewidth=1.2, label="dv")
        self.ax_metrics.plot(xs, slopes, color=THEME.slope, linewidth=1.1, label="slope")
        self.ax_metrics.plot(xs, sigmas, color=THEME.sigma, linewidth=1.1, label="sigma")
        self.ax_metrics.set_xlim(min(xs), 0.0)
        metric_values = [value for value in dvs + slopes + sigmas if value is not None]
        if metric_values:
            m_min = min(metric_values) - 0.05
            m_max = max(metric_values) + 0.05
            if math.isclose(m_min, m_max):
                m_min -= 0.1
                m_max += 0.1
            self.ax_metrics.set_ylim(m_min, m_max)
        self.ax_metrics.set_title("Detection metrics", color=THEME.text, fontsize=10, fontweight="bold")
        self.ax_metrics.set_ylabel("Value", color=THEME.text)
        self.ax_metrics.set_xlabel("Seconds in window", color=THEME.text)
        self.ax_metrics.legend(loc="upper left", fontsize=8, frameon=False, labelcolor=THEME.text)
        self.figure.tight_layout(pad=1.4)
        self.canvas.draw_idle()

    def _update_raw_tails(self) -> None:
        self._render_text_widget(self.diag_text, self.model.diag_text_tail)
        self._render_text_widget(self.touch_text, self.model.touch_text_tail)

    def refresh_view(self) -> None:
        if self._paused:
            self.after(self.refresh_ms, self.refresh_view)
            return

        self._maybe_refresh_source()
        self.model.ingest()
        snapshot = self.model.snapshot(self.window_seconds * 1000)
        self._update_summary(snapshot)
        self._render_plots(snapshot)
        self._render_events()
        self._update_raw_tails()

        self.after(self.refresh_ms, self.refresh_view)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Panel vivo de diagnostico de frutas OKUA.")
    parser.add_argument("--folder", type=Path, default=None, help="Carpeta fruit_soak_* a observar.")
    parser.add_argument("--no-follow-latest", action="store_true", help="No cambiar al ultimo soak detectado.")
    parser.add_argument("--window-seconds", type=int, default=DEFAULT_WINDOW_SECONDS, choices=[10, 30, 60, 300])
    parser.add_argument("--refresh-ms", type=int, default=DEFAULT_REFRESH_MS, choices=[250, 500, 1000, 1500])
    parser.add_argument("--max-samples", type=int, default=DEFAULT_MAX_SAMPLES)
    parser.add_argument("--max-events", type=int, default=DEFAULT_EVENT_TAIL)
    parser.add_argument("--tail-lines", type=int, default=DEFAULT_TEXT_TAIL)
    parser.add_argument("--stale-warn-sec", type=float, default=DEFAULT_STALE_WARN_SEC)
    parser.add_argument("--label", type=str, default="", help="Etiqueta manual de firmware/detector.")
    parser.add_argument("--demo", action="store_true", help="Arranca con una sesion demo sintetica.")
    parser.add_argument("--self-test", action="store_true", help="Ejecuta pruebas basicas y sale.")
    return parser


def run_self_test() -> None:
    sample_row = {
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
    sample = parse_diag_csv_row(sample_row)
    assert sample.state == "contact"
    assert sample.phase == "track"
    assert sample.raw is not None and sample.raw < 2.0
    assert sample.rail is False
    touch_line = "[12:08:40.693] 198.51.100.17:51374 EB1#1 TOQUE INICIO raw=1.9163 filt=2.0763 dv=0.3223"
    touch_event = parse_touch_text_line(touch_line)
    assert touch_event is not None
    assert touch_event.kind == "TOQUE INICIO"
    assert touch_event.raw == 1.9163

    temp_folder = ARTIFACTS_ROOT / "_panel_self_test"
    temp_folder.mkdir(parents=True, exist_ok=True)
    diag_csv = temp_folder / "diagnostic_values.csv"
    diag_csv.write_text(
        "base,cand,dv,energy_age_ms,exit,filt,hold_down_ms,hold_up_ms,id,mode,node,pending_sign,phase,prev,raw,recovery_ms,ref,sigma,slope,state,t_ms,th_down,th_up,touch_sign,vmax,vmin\n"
        "1.8644,1,0.0957,0,0,1.8363,0,513,1,fruit,EB1,1,track,idle,1.7406,0,0,0.0232,0.4859,contact,1050307,0.0252,0.0420,1,1.9671,1.6641\n",
        encoding="utf-8",
    )
    touch_log = temp_folder / "touch_events.log"
    touch_log.write_text(
        "[12:08:40.693] 198.51.100.17:51374 EB1#1 TOQUE INICIO raw=1.9163 filt=2.0763 dv=0.3223\n",
        encoding="utf-8",
    )
    diag_reader = CsvTailReader(diag_csv)
    assert diag_reader.read_new_rows()
    touch_reader = TextTailReader(touch_log)
    assert touch_reader.read_new_lines()

    print("SELF_TEST_OK")


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    if args.self_test:
        run_self_test()
        return 0

    if args.demo:
        session = generate_demo_session(ARTIFACTS_ROOT)
    else:
        folder = args.folder or find_latest_soak_folder(ARTIFACTS_ROOT)
        if folder is None:
            if messagebox is not None:
                # Tk will create the dialog once the app exists; here we only fail fast.
                print(f"[live-panel] no soak folder found under {ARTIFACTS_ROOT}")
            return 1
        session = build_session_paths(folder)

    label = args.label.strip() or guess_detector_label(REPO_ROOT)
    if args.demo:
        label = f"demo | {label}" if label and label != "unknown" else "demo"

    app = LiveDiagnosticsPanel(
        session=session,
        label=label,
        refresh_ms=args.refresh_ms,
        window_seconds=args.window_seconds,
        max_samples=args.max_samples,
        max_events=args.max_events,
        text_tail=args.tail_lines,
        stale_warn_sec=args.stale_warn_sec,
        follow_latest=not args.no_follow_latest and not args.folder and not args.demo,
        demo_mode=args.demo,
    )
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
