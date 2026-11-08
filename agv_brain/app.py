"""The whole program behind the website: broker, AI and dashboard, in one place.

    app = App.start()            # what scripts/run_app.py does: nothing runs yet
    app.login("Exhibit Factory") # the website's login page: open or make a factory
    app.run("sim")               # "Try a simulation" / Start on the Setup page
    app.stop_session()           # Stop

The website opens on the login page and the factory stays idle until someone presses
Start. One factory session runs at a time (agv_brain.factory_sim.FactorySim: the AI plus
whichever devices are simulated). Changing the mode or the track of a running factory
stops it and starts a new one; the broker and the website keep running. The factory that
was open last is saved in config/app.local.yaml, its setup in config/factories/<id>/.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import yaml

from agv_brain import factories
from agv_brain import protocol as P
from agv_brain import tracks
from agv_brain.broker import BRAIN, Broker, lan_addresses
from agv_brain.bus import MemoryBus, MqttBus
from agv_brain.dashboard.server import DashboardServer, layout_json
from agv_brain.factory_sim import FactorySim
from agv_brain.models import CONFIG_DIR, load_settings
from agv_brain.simulator import load_context

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
        self.mode, self.track, self.speed = "sim", "sample", 8.0
        self.factory: dict | None = None     # {"id", "name", ...} after the login page
        self.session: FactorySim | None = None
        self.layout: dict = {}
        self.layout_version = 0
        self.seen: dict[str, float] = {}     # device id -> wall time of its last message
        self._lock = threading.RLock()
        bus.subscribe(P.car_status("+"), self._on_device)
        bus.subscribe(P.station_stock("+"), self._on_device)
        saved = {}
        if state_file and state_file.exists():
            saved = yaml.safe_load(state_file.read_text(encoding="utf-8")) or {}
        if factories.exists(saved.get("factory")):
            self._open(factories.load(saved["factory"]))
        self._preview()
        self.dash = DashboardServer(bus, load_context(tracks.track_path(self.track)), host=host, port=port, app=self)

    @classmethod
    def start(cls, host: str = "127.0.0.1", port: int = 8050, policy: str = "ml",
              mqtt_port: int | None = None) -> "App":
        """Start Mosquitto with device logins and connect the AI to it. If the broker
        cannot start, run the simulation in memory and tell the Setup page why."""
        cfg = yaml.safe_load((CONFIG_DIR / "mqtt.yaml").read_text(encoding="utf-8"))
        car_id = cfg.get("car_id", "AGV-1")
        settings = load_settings()
        broker = Broker(mqtt_port or int(cfg["local"]["port"]), cfg.get("cloud") or {}, [car_id], list(settings.stations))
        if broker.start():
            bus = MqttBus("localhost", broker.port, client_id="capstone-brain",
                          username=BRAIN, password=broker.keys[BRAIN])
            return cls(bus, broker, car_id=car_id, policy=policy, host=host, port=port)
        return cls(MemoryBus(), None, car_id=car_id, policy=policy, host=host, port=port,
                   broker_error=broker.error)

    # -- the factory (login page) ---------------------------------------------------

    @property
    def real_ok(self) -> bool:
        return self.broker is not None

    @property
    def running(self) -> bool:
        return self.session is not None

    @property
    def mode_name(self) -> str:
        return MODE_NAMES[self.mode]

    @property
    def sim_parts(self) -> dict:
        car, stations = MODES[self.mode]
        return {"car": car, "stations": stations}

    def _open(self, factory: dict) -> None:
        self.factory = factory
        self.mode = factory["mode"] if factory["mode"] == "sim" or self.real_ok else "sim"
        self.speed = factory["speed"]
        try:
            self._check_track(factory["track"])
            self.track = factory["track"]
        except (ValueError, FileNotFoundError):
            self.track = "sample"            # a saved track that no longer works: fall back

    def login(self, name) -> dict:
        """Open the factory with this name (or make it). Whatever ran before stops."""
        with self._lock:
            factory = factories.open_or_create(name)
            self.stop_session()
            self._open(factory)
            self._preview()
            self._save()
            return self.factory_info()

    def logout(self) -> None:
        with self._lock:
            self.stop_session()
            self.factory = None
            self._save()

    def factory_info(self) -> dict | None:
        return {"id": self.factory["id"], "name": self.factory["name"]} if self.factory else None

    # -- running -----------------------------------------------------------------

    def _check_track(self, track: str) -> None:
        problems = tracks.validate(tracks.load_raw(track), self.settings)
        if problems["errors"]:
            raise ValueError("This track has problems: " + " ".join(problems["errors"][:3]))

    def _preview(self) -> None:
        """The map of the chosen track, shown while nothing runs."""
        self.layout = layout_json(load_context(tracks.track_path(self.track)))
        self.layout_version += 1

    def _start_session(self) -> None:
        self._check_track(self.track)
        sim_car, sim_stations = MODES[self.mode]
        if hasattr(self, "dash"):
            self.dash.clear()
        self.session = FactorySim(policy=self.policy, speed=self.speed, bus=self.bus, log=self.log,
                                  layout=tracks.track_path(self.track), sim_car=sim_car, sim_stations=sim_stations,
                                  car_id=self.car_id)
        self.layout = layout_json(self.session.controller.ctx)
        self.layout_version += 1
        # clear the last session's decision so the page never shows an old one
        self.bus.publish(P.AI_DECISION, {"ts": 0, "policy": self.policy, "queue": [], "reasons": [], "alerts": [],
                                         "preview": True}, retain=True)
        if hasattr(self, "dash"):
            self.dash.ctx = self.session.controller.ctx

    def stop_session(self) -> None:
        """Stop the running factory (the website and the broker keep running)."""
        with self._lock:
            if self.session:
                self.session.stop()
                self.session = None
                if hasattr(self, "dash"):
                    self.dash.clear()

    def configure(self, mode: str | None = None, track: str | None = None, speed=None) -> None:
        """Change how the factory runs. A running factory restarts with the change."""
        with self._lock:
            mode = mode or self.mode
            if mode not in MODES:
                raise ValueError(f"mode must be one of {list(MODES)}")
            if mode != "sim" and not self.real_ok:
                raise ValueError("The real car needs the MQTT broker. " + (self.broker_error or ""))
            if track is not None:
                tracks.track_path(track)        # raises if it does not exist
                self._check_track(track)
            if speed is not None:
                try:
                    speed = max(1.0, min(20.0, float(speed)))
                except (TypeError, ValueError):
                    raise ValueError("The speed must be a number from 1 to 20.") from None
            old = (self.mode, self.track, self.speed)
            self.mode = mode
            self.track = track if track is not None else self.track
            self.speed = speed if speed is not None else self.speed
            if self.session:
                self.session.stop()
                self.session = None
                try:
                    self._start_session()
                except (ValueError, FileNotFoundError):
                    self.mode, self.track, self.speed = old
                    self._start_session()
                    raise
            elif self.track != old[1]:
                self._preview()
            self._save()

    def run(self, mode: str | None = None, speed=None, track: str | None = None) -> None:
        """Start the factory (Start / "Try a simulation"), or restart it with the change."""
        with self._lock:
            self.configure(mode, track, speed)
            if not self.session:
                self._start_session()

    def switch(self, mode: str | None = None, track: str | None = None, speed=None) -> None:
        """Older name for run(): start or restart with the new mode, track or speed."""
        self.run(mode, speed, track)

    def _save(self) -> None:
        if self.factory:
            self.factory.update(mode=self.mode, track=self.track, speed=self.speed)
            factories.save(self.factory)
        if self.state_file:
            self.state_file.write_text("# The factory last opened on the website (this laptop only).\n"
                                       + yaml.safe_dump({"factory": self.factory["id"] if self.factory else None}),
                                       encoding="utf-8")

    # -- devices -----------------------------------------------------------------

    def _on_device(self, topic: str, msg: dict) -> None:
        device = topic.split("/")[2]
        if msg.get("state") == "OFFLINE":      # the car's last will, or a stopped simulation
            self.seen.pop(device, None)
        else:
            self.seen[device] = time.time()

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
                "running": self.running, "factory": self.factory_info(),
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
