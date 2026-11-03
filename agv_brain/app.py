"""The whole program behind the website: broker, AI and dashboard, in one place.

    app = App.start()          # what scripts/run_app.py does
    app.switch("real_car")     # what the Setup page does

One factory session runs at a time (agv_brain.factory_sim.FactorySim: the AI plus
whichever devices are simulated). Switching the mode or the track stops it and
starts a new one; the broker and the website keep running. The last mode and track
are saved in config/app.local.yaml, so the app comes back the same way.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import yaml

from agv_brain import protocol as P
from agv_brain import tracks
from agv_brain.broker import BRAIN, Broker, lan_addresses
from agv_brain.bus import MemoryBus, MqttBus
from agv_brain.dashboard.server import DashboardServer, layout_json
from agv_brain.factory_sim import FactorySim
from agv_brain.models import CONFIG_DIR, load_settings

STATE_FILE = CONFIG_DIR / "app.local.yaml"
MODES = {   # mode -> (simulated car, simulated stations)
    "sim": (True, True),
    "real_car": (False, True),
    "real": (False, False),
}
MODE_NAMES = {"sim": "Simulation", "real_car": "Real car + simulated stations", "real": "Real factory"}
ONLINE_S = {"car": 5.0, "station": 15.0}   # no message for this long = offline


class App:
    def __init__(self, bus, broker: Broker | None = None, car_id: str = "AGV-1", policy: str = "ml",
                 host: str = "127.0.0.1", port: int = 8050, state_file: Path | None = STATE_FILE,
                 broker_error: str | None = None, log: bool = True):
        self.bus, self.broker, self.car_id, self.policy = bus, broker, car_id, policy
        self.broker_error = broker_error
        self.state_file, self.log = state_file, log
        self.settings = load_settings()
        saved = {}
        if state_file and state_file.exists():
            saved = yaml.safe_load(state_file.read_text(encoding="utf-8")) or {}
        self.mode = saved.get("mode", "sim")
        if self.mode not in MODES or (self.mode != "sim" and not self.real_ok):
            self.mode = "sim"    # no broker: only the simulation can run
        self.track = saved.get("track", "sample")
        self.speed = float(saved.get("speed", 8))
        self.session: FactorySim | None = None
        self.layout: dict = {}
        self.layout_version = 0
        self.seen: dict[str, float] = {}     # device id -> wall time of its last message
        self._lock = threading.RLock()
        bus.subscribe(P.car_status("+"), self._on_device)
        bus.subscribe(P.station_stock("+"), self._on_device)
        try:
            self._start_session()
        except (ValueError, FileNotFoundError):
            self.track = "sample"            # a saved track that no longer works: fall back
            self._start_session()
        self.dash = DashboardServer(bus, self.session.controller.ctx, host=host, port=port, app=self)

    @classmethod
    def start(cls, host: str = "127.0.0.1", port: int = 8050, policy: str = "ml") -> "App":
        """Start Mosquitto with device logins and connect the AI to it. If the broker
        cannot start, run the simulation in memory and tell the Setup page why."""
        cfg = yaml.safe_load((CONFIG_DIR / "mqtt.yaml").read_text(encoding="utf-8"))
        car_id = cfg.get("car_id", "AGV-1")
        settings = load_settings()
        broker = Broker(int(cfg["local"]["port"]), cfg.get("cloud") or {}, [car_id], list(settings.stations))
        if broker.start():
            bus = MqttBus("localhost", broker.port, client_id="capstone-brain",
                          username=BRAIN, password=broker.keys[BRAIN])
            return cls(bus, broker, car_id=car_id, policy=policy, host=host, port=port)
        return cls(MemoryBus(), None, car_id=car_id, policy=policy, host=host, port=port,
                   broker_error=broker.error)

    # -- sessions --------------------------------------------------------------

    @property
    def real_ok(self) -> bool:
        return self.broker is not None

    @property
    def mode_name(self) -> str:
        return MODE_NAMES[self.mode]

    @property
    def sim_parts(self) -> dict:
        car, stations = MODES[self.mode]
        return {"car": car, "stations": stations}

    def _start_session(self) -> None:
        path = tracks.track_path(self.track)
        problems = tracks.validate(tracks.load_raw(self.track), self.settings)
        if problems["errors"]:
            raise ValueError("This track has problems: " + " ".join(problems["errors"][:3]))
        sim_car, sim_stations = MODES[self.mode]
        self.session = FactorySim(policy=self.policy, speed=self.speed, bus=self.bus, log=self.log,
                                  layout=path, sim_car=sim_car, sim_stations=sim_stations, car_id=self.car_id)
        self.layout = layout_json(self.session.controller.ctx)
        self.layout_version += 1
        # clear the last session's decision so the page never shows an old one
        self.bus.publish(P.AI_DECISION, {"ts": 0, "policy": self.policy, "queue": [], "reasons": [], "alerts": [],
                                         "preview": True}, retain=True)

    def switch(self, mode: str | None = None, track: str | None = None, speed: float | None = None) -> None:
        """Stop the running session and start one with the new mode, track or speed."""
        with self._lock:
            mode = mode or self.mode
            if mode not in MODES:
                raise ValueError(f"mode must be one of {list(MODES)}")
            if mode != "sim" and not self.real_ok:
                raise ValueError("The real car needs the MQTT broker. " + (self.broker_error or ""))
            if track is not None:
                tracks.track_path(track)        # raises if it does not exist
            old = (self.mode, self.track, self.speed)
            self.mode, self.track = mode, track if track is not None else self.track
            if speed is not None:
                self.speed = max(1.0, min(20.0, float(speed)))
            previous = self.session
            previous.stop()
            try:
                self._start_session()
            except (ValueError, FileNotFoundError):
                self.mode, self.track, self.speed = old
                self._start_session()
                raise
            self.dash.ctx = self.session.controller.ctx
            self._save()

    def _save(self) -> None:
        if self.state_file:
            self.state_file.write_text("# Last mode and track chosen on the Setup page (this laptop only).\n"
                                       + yaml.safe_dump({"mode": self.mode, "track": self.track, "speed": self.speed}),
                                       encoding="utf-8")

    # -- devices -----------------------------------------------------------------

    def _on_device(self, topic: str, msg: dict) -> None:
        self.seen[topic.split("/")[2]] = time.time()

    def devices(self) -> list[dict]:
        sim_car, sim_stations = MODES[self.mode]
        now = time.time()
        out = []
        rows = [(self.car_id, "car", sim_car, "Car")] + \
            [(sid, "station", sim_stations, st.name) for sid, st in self.settings.stations.items()]
        for did, kind, simulated, name in rows:
            last = self.seen.get(did)
            ago = None if last is None else round(now - last, 1)
            topics = ([f"factory/car/{did}/status", f"factory/car/{did}/event", f"factory/car/{did}/cmd"]
                      if kind == "car" else [f"factory/station/{did}/stock"])
            out.append({"id": did, "kind": kind, "name": name, "simulated": simulated,
                        "online": ago is not None and ago < ONLINE_S[kind], "last_seen_s": ago, "topics": topics})
        return out

    def setup(self, local: bool) -> dict:
        """What the Setup page shows. Keys only for the laptop itself (`local`)."""
        b = self.broker
        addrs = lan_addresses()
        devices = self.devices()
        if local and b:
            for d in devices:
                d["key"] = b.keys.get(d["id"])
        return {"mode": self.mode, "mode_name": MODE_NAMES[self.mode], "modes": MODE_NAMES,
                "track": self.track, "speed": self.speed, "tracks": tracks.list_tracks(),
                "local": local, "broker": {"ok": b is not None, "error": self.broker_error,
                                           "port": b.port if b else None, "addresses": addrs,
                                           "secure": b is not None, "bridged": bool(b and b.bridged)},
                "devices": devices}

    def new_key(self, device: str) -> str:
        if not self.broker:
            raise ValueError("The broker is not running.")
        return self.broker.new_key(device)

    def stop(self) -> None:
        self.dash.stop()
        if self.session:
            self.session.stop()
        self.bus.close()
        if self.broker:
            self.broker.stop()
