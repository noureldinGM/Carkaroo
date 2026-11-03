"""CSV logs of everything that happens: for the logbook, R3/R8 measurements and retraining."""

from __future__ import annotations

import csv
import json
import threading
import time
from datetime import datetime
from pathlib import Path

from agv_brain.models import ROOT


class EventLog:
    FILES = {
        "readings": ["wall_time", "sim_s", "station", "material", "stock"],
        "decisions": ["wall_time", "sim_s", "policy", "order", "scores", "optimizer_agrees", "reasons"],
        "events": ["wall_time", "sim_s", "source", "type", "details"],
    }

    def __init__(self, folder: str | Path | None = None):
        self.folder = Path(folder) if folder else ROOT / "logs" / datetime.now().strftime("%Y%m%d-%H%M%S")
        self.folder.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._files = {}
        self._writers = {}
        for name, header in self.FILES.items():
            f = open(self.folder / f"{name}.csv", "w", newline="", encoding="utf-8")
            w = csv.writer(f)
            w.writerow(header)
            self._files[name], self._writers[name] = f, w

    def _write(self, name: str, row: list) -> None:
        with self._lock:
            self._writers[name].writerow([f"{time.time():.3f}", *row])
            self._files[name].flush()

    def reading(self, sim_s, station, material, stock):
        self._write("readings", [f"{sim_s:.1f}", station, material, stock])

    def decision(self, sim_s, msg: dict):
        self._write("decisions", [f"{sim_s:.1f}", msg["policy"],
                                  " > ".join(q["request_id"] for q in msg["queue"]),
                                  json.dumps({q["request_id"]: q["score"] for q in msg["queue"]}),
                                  msg["optimizer_agrees"], " | ".join(msg["reasons"])])

    def event(self, sim_s, source, type_, details: dict | None = None):
        self._write("events", [f"{sim_s:.1f}", source, type_, json.dumps(details or {})])

    def close(self) -> None:
        with self._lock:
            for f in self._files.values():
                f.close()
