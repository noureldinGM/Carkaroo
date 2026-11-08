"""The Carkaroo Simulator: a pretend car and pretend stations for practice.

It is a separate program from the Carkaroo website (scripts/run_simulator.py, its own
website at http://localhost:8060). Each pretend device logs in to the broker on its own,
with its own device ID and key, exactly like the real car and the real station nodes will:
the website cannot tell the difference. So connecting the simulator is a rehearsal for
connecting the real hardware.

    p = Practice()
    p.choose("exhibit-factory")                     # the factory floor to pretend
    p.connect("AGV-1", key, host="localhost", port=1883)
    p.control({"cmd": "set_battery", "value": 15})  # change the pretend world

The pretend devices are agv_brain.sim_devices.SimulatedCar / SimulatedStation, which speak
the protocol in docs/protocol.md. The play controls (battery, obstacles, stock) reach them
through a small bus inside this program, never through MQTT: the real devices' keys only
allow their own topics, and the simulator needs nothing more.
"""

from __future__ import annotations

import threading

import yaml

from agv_brain import factories, tracks
from agv_brain import protocol as P
from agv_brain.bus import Clock, MemoryBus, MqttBus
from agv_brain.models import CONFIG_DIR, CarState, load_settings
from agv_brain.sim_devices import SimulatedCar, SimulatedStation
from agv_brain.simulator import load_context


class DeviceBus:
    """One device's view: its MQTT login for the protocol, the local bus for the play controls."""

    def __init__(self, mqtt, local: MemoryBus):
        self.mqtt, self.local = mqtt, local

    def _bus(self, topic: str):
        return self.local if topic == P.SIM_CONTROL else self.mqtt

    def publish(self, topic: str, payload: dict, qos: int = 0, retain: bool = False) -> None:
        self._bus(topic).publish(topic, payload, qos=qos, retain=retain)

    def subscribe(self, pattern: str, handler) -> None:
        self._bus(pattern).subscribe(pattern, handler)

    def unsubscribe(self, handler) -> None:
        self.mqtt.unsubscribe(handler)
        self.local.unsubscribe(handler)


def car_id() -> str:
    cfg = yaml.safe_load((CONFIG_DIR / "mqtt.yaml").read_text(encoding="utf-8")) or {}
    return cfg.get("car_id", "AGV-1")


def explain(exc: Exception, host: str, port: int) -> str:
    """Why a device could not log in, in plain words."""
    text = str(exc)
    if "refused the login" in text:
        return "Refused: wrong key (or this device is not in the factory). Copy the key again from Setup → Devices."
    return f"No broker answered at {host}:{port}. Is the Carkaroo website running, and are the address and port right?"


class Practice:
    def __init__(self, connect=MqttBus):
        self._connect = connect             # tests pass a fake
        self._lock = threading.RLock()
        self.clock = Clock(1.0)             # real time, like the real devices
        self.local = MemoryBus()            # the play controls
        self.factory: dict | None = None
        self.settings = None
        self.fmap = None
        self.layout: dict = {}
        self.host, self.port = "localhost", 1883
        self.devices: dict[str, dict] = {}  # id -> {"kind", "state", "error", "bus", "sim"}

    # -- the factory floor ---------------------------------------------------------

    def choose(self, factory_id: str) -> None:
        """Pretend this factory: its track and its stations (from config/factories/)."""
        with self._lock:
            if not factories.exists(factory_id):
                raise ValueError("Choose a factory made on the Carkaroo website.")
            f = factories.load(factory_id)
            settings = load_settings(factories.materials_path(factory_id))
            problems = tracks.validate(tracks.load_raw(f["track"]), settings)["errors"]
            if problems:
                raise ValueError("This factory's track is not ready yet (see Setup on the Carkaroo website): "
                                 + problems[0])
            self.disconnect_all()
            ctx = load_context(tracks.track_path(f["track"]), factories.materials_path(factory_id))
            from agv_brain.dashboard.server import layout_json
            self.factory, self.settings, self.fmap = f, ctx.settings, ctx.fmap
            self.layout = layout_json(ctx)
            cid = car_id()
            self.devices = {cid: {"kind": "car", "name": "Car", "state": "off", "error": None}}
            for sid, st in ctx.settings.stations.items():
                self.devices[sid] = {"kind": "station", "name": st.name, "state": "off", "error": None}

    # -- logging in, like the real devices --------------------------------------------

    def connect(self, device: str, key, host=None, port=None) -> str:
        """Log `device` in with its key and start pretending to be it. Returns its state."""
        with self._lock:
            if not self.factory:
                raise ValueError("Choose a factory first.")
            d = self.devices.get(device)
            if d is None:
                raise ValueError("That device is not in this factory.")
            if not isinstance(key, str) or not key.strip() or len(key) > 200:
                raise ValueError("Paste the device's key (Setup → Devices on the Carkaroo website).")
            host = self.host if host is None else host
            host = host.strip() if isinstance(host, str) else ""
            if not host or len(host) > 100 or any(c in host for c in " /\\@"):
                raise ValueError("Type the broker's address, for example localhost or 192.168.1.14.")
            try:
                port = int(port if port is not None else self.port)
            except (TypeError, ValueError):
                raise ValueError("The port must be a number, usually 1883.") from None
            if not 1 <= port <= 65535:
                raise ValueError("The port must be a number, usually 1883.")
            self.host, self.port = host, port
            self.disconnect(device)
            try:
                mqtt = self._connect(host, port, client_id=f"carkaroo-sim-{device}", username=device,
                                     password=key.strip(), connect_timeout=4)
            except (ConnectionError, OSError) as exc:
                d.update(state="error", error=explain(exc, host, port))
                return d["state"]
            bus = DeviceBus(mqtt, self.local)
            s = self.settings
            if d["kind"] == "car":
                sim = SimulatedCar(bus, self.clock, self.fmap, s, car_id=device,
                                   start=CarState(s.car.dock, s.car.start_heading, 90.0))
            else:
                sim = SimulatedStation(bus, self.clock, s, device, seed=sorted(self.devices).index(device))
            d.update(state="on", error=None, bus=bus, sim=sim)
            return d["state"]

    def disconnect(self, device: str) -> None:
        """Stop pretending to be `device` and log it out (like pulling its plug)."""
        with self._lock:
            d = self.devices.get(device)
            if not d or "sim" not in d:
                if d:
                    d.update(state="off", error=None)
                return
            d["sim"].stop()
            if d["kind"] == "car":   # what the real car's last will says when it drops
                d["bus"].mqtt.publish(P.car_status(device), {"state": "OFFLINE"}, qos=1, retain=True)
            d["bus"].mqtt.close()
            for k in ("bus", "sim"):
                d.pop(k, None)
            d.update(state="off", error=None)

    def disconnect_all(self) -> None:
        for device in list(self.devices):
            self.disconnect(device)

    # -- the play controls ---------------------------------------------------------------

    def control(self, msg: dict) -> None:
        """Change the pretend world (checked like the website's old controls)."""
        from agv_brain.dashboard.server import check_sim
        with self._lock:
            if not self.factory:
                raise ValueError("Choose a factory first.")
            state = {"stations": {sid: {"materials": {m: {"capacity": v.capacity} for m, v in st.materials.items()}}
                                  for sid, st in self.settings.stations.items()}}
            msg = check_sim(msg, self.layout, state)
            kind = "station" if msg["cmd"] == "set_stock" else "car"
            target = msg.get("station") if kind == "station" else next(
                (i for i, d in self.devices.items() if d["kind"] == "car"), None)
            if self.devices.get(target, {}).get("state") != "on":
                raise ValueError(f"Connect {target} first: the controls change the pretend devices.")
            self.local.publish(P.SIM_CONTROL, msg)

    # -- what the page shows ----------------------------------------------------------------

    def snapshot(self) -> dict:
        with self._lock:
            out = []
            for did, d in self.devices.items():
                row = {"id": did, "kind": d["kind"], "name": d["name"], "state": d["state"], "error": d["error"]}
                sim = d.get("sim")
                if sim is not None and d["kind"] == "car":
                    row.update(node=sim.node, heading=sim.heading, battery=round(sim.battery, 1), mode=sim.mode,
                               obstacles=[sorted(e) for e in sim.obstacles])
                elif sim is not None:
                    row.update(stock={m: round(v, 1) for m, v in sim.stock.items()})
                out.append(row)
            return {"factory": {"id": self.factory["id"], "name": self.factory["name"]} if self.factory else None,
                    "factories": factories.list_factories(), "host": self.host, "port": self.port,
                    "layout": self.layout, "devices": out}

    def stop(self) -> None:
        self.disconnect_all()


def parse_paste(text: str) -> dict:
    """The block from "Copy all for the simulator": broker, port and one "ID: key" per line."""
    out: dict = {"keys": {}}
    if not isinstance(text, str) or len(text) > 5000:
        raise ValueError("Paste the text from Setup → Devices → Copy all for the simulator.")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, v = (x.strip() for x in line.split(":", 1))
        if k.lower() == "broker":
            out["host"] = v
        elif k.lower() == "port":
            out["port"] = v
        elif k and v:
            out["keys"][k] = v
    if not out["keys"]:
        raise ValueError("No keys found: paste the text from Setup → Devices → Copy all for the simulator.")
    return out

