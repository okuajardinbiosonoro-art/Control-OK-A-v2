from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import mido
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QListWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


def _mido_set_backend(backend_path: str) -> None:
    setter = getattr(mido, "set_backend", None)
    if not callable(setter):
        raise RuntimeError("mido.set_backend no esta disponible en el backend actual.")
    setter(backend_path)


def _mido_get_output_names() -> list[str]:
    getter = getattr(mido, "get_output_names", None)
    if not callable(getter):
        raise RuntimeError("mido.get_output_names no esta disponible en el backend actual.")
    names = getter()
    if not isinstance(names, Iterable):
        return []
    return [str(name) for name in names]


class MidiOutputsWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)

        self.info_label = QLabel("Sin datos MIDI.")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.outputs_table = QTableWidget(0, 3, self)
        self.outputs_table.setHorizontalHeaderLabels(
            ["Bus", "Salida configurada", "Disponible"]
        )
        self.outputs_table.horizontalHeader().setStretchLastSection(True)
        self.outputs_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.outputs_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.outputs_table.verticalHeader().setVisible(False)
        layout.addWidget(self.outputs_table)

        self.available_label = QLabel("Puertos MIDI disponibles")
        layout.addWidget(self.available_label)

        self.available_list = QListWidget(self)
        layout.addWidget(self.available_list)

    def refresh_from_config(self, cfg: dict[str, Any]) -> None:
        raw_midi_cfg = cfg.get("midi")
        midi_cfg: dict[str, Any] = raw_midi_cfg if isinstance(raw_midi_cfg, dict) else {}
        outputs_raw = midi_cfg.get("outputs", {})
        backend = midi_cfg.get("backend", "rtmidi")

        available_names: list[str] = []
        error_text = ""

        try:
            if backend == "rtmidi":
                _mido_set_backend("mido.backends.rtmidi")
            elif isinstance(backend, str) and backend.strip():
                _mido_set_backend(backend)
            available_names = _mido_get_output_names()
        except Exception as exc:
            error_text = f"Error consultando salidas MIDI: {exc}"

        available_set = set(available_names)
        rows: list[tuple[int, str, str]] = []
        if isinstance(outputs_raw, dict):
            for raw_bus, port_name in outputs_raw.items():
                bus_str = str(raw_bus)
                if not bus_str.isdigit():
                    continue
                if not isinstance(port_name, str):
                    continue
                bus = int(bus_str)
                rows.append(
                    (
                        bus,
                        port_name,
                        "Si" if port_name in available_set else "No",
                    )
                )

        rows.sort(key=lambda item: item[0])
        self.outputs_table.setRowCount(len(rows))
        for row_index, (bus, port_name, available_text) in enumerate(rows):
            self.outputs_table.setItem(row_index, 0, QTableWidgetItem(str(bus)))
            self.outputs_table.setItem(row_index, 1, QTableWidgetItem(port_name))
            self.outputs_table.setItem(
                row_index, 2, QTableWidgetItem(available_text)
            )

        self.available_list.clear()
        if error_text:
            self.info_label.setText(error_text)
            self.available_list.addItem("No se pudo consultar la lista de puertos.")
        else:
            configured = len(rows)
            discovered = len(available_names)
            self.info_label.setText(
                f"Outputs configurados: {configured} | Puertos detectados: {discovered}"
            )
            if available_names:
                self.available_list.addItems(available_names)
            else:
                self.available_list.addItem("No se detectaron puertos MIDI.")
