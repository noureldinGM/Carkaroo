"""Simulated hardware that speaks exactly the MQTT messages of docs/protocol.md.

SimulatedCar      follows the junction commands on its own copy of the track (it
                  does not know the planned path, like the real car), lifts and
                  lowers its fork, reports nodes, stops at obstacles, charges.
SimulatedStation  uses material at its rate with some randomness, reports whole
                  units like a load cell, and receives the car's deliveries.

Simulation-only commands arrive on factory/sim/control:
    {"cmd": "obstacle", "edge": ["J2", "J5"], "duration_s": 60}
    {"cmd": "clear_obstacles"}
    {"cmd": "set_stock", "station": "S3", "material": "B", "stock": 2}
    {"cmd": "set_battery", "value": 15}
"""

from __future__ import annotations

import queue
import threading

import numpy as np

from agv_brain import protocol as P
from agv_brain.bus import Clock
from agv_brain.factory_map import HEADINGS, FactoryMap
from agv_brain.models import CarState, Settings

_TURN = {"STRAIGHT": 0, "RIGHT": 1, "UTURN": 2, "LEFT": 3}


def _turn(heading: str, command: str) -> str:
    return HEADINGS[(HEADINGS.index(heading) + _TURN[command]) % 4]


class SimulatedCar:
    CHARGE_PCT_PER_S = 2.0

    def __init__(self, bus, clock: Clock, fmap: FactoryMap, settings: Settings, car_id: str = "AGV-1",
                 start: CarState | None = None, speed_noise: float = 0.1, seed: int = 0,
                 status_period_s: float = 1.0):
        self.bus, self.clock, self.fmap, self.settings = bus, clock, fmap, settings
        self.car_id, self.speed_noise, self.status_period_s = car_id, speed_noise, status_period_s
        p = settings.car
        start = start or CarState(p.dock, p.start_heading, 90.0)
        self.node, self.heading, self.battery = start.node, start.heading, start.battery_pct
        self.mode, self.fork = "IDLE", "DOWN"
        self.task_id, self.leg, self.node_index = None, None, 0
        self.obstacles: dict[frozenset, float] = {}     # edge -> sim time it disappears
        self.distance_cm = 0.0
        self._rng = np.random.default_rng(seed)
        self._jobs: queue.Queue = queue.Queue()
        self._reroute: dict | None = None
        self._resume = threading.Event()
        self._halt = threading.Event()
        self._lock = threading.Lock()
        bus.subscribe(P.car_cmd(car_id), self._on_cmd)
        bus.subscribe(P.SIM_CONTROL, self._on_sim)
        for target in (self._work, self._status_loop):
            threading.Thread(target=target, daemon=True).start()

    # -- messages ---------------------------------------------------------------

    def _on_cmd(self, topic: str, msg: dict) -> None:
        kind = msg.get("type")
        if kind in ("task", "charge"):
            self._jobs.put(msg)
        elif kind == "reroute":
            self._reroute = msg
        elif kind == "resume":
            self._resume.set()

    def _on_sim(self, topic: str, msg: dict) -> None:
        cmd = msg.get("cmd")
        if cmd == "obstacle":
            edge = frozenset(msg["edge"])
            self.obstacles[edge] = self.clock.now() + float(msg.get("duration_s", 60))
        elif cmd == "clear_obstacles":
            self.obstacles.clear()
        elif cmd == "set_battery":
            self.battery = float(msg["value"])

    def _emit(self, payload: dict) -> None:
        self.bus.publish(P.car_event(self.car_id), payload, qos=1)

    def _status(self) -> None:
        self.bus.publish(P.car_status(self.car_id), {
            "state": self.mode, "battery": round(self.battery, 1), "task_id": self.task_id,
            "fork": self.fork, "leg": self.leg, "node_index": self.node_index}, retain=True)

    def _status_loop(self) -> None:
        while not self._halt.is_set():
            self._status()
            self.clock.sleep(self.status_period_s)

    # -- driving -----------------------------------------------------------------

    def _obstacle_on(self, a: str, b: str) -> bool:
        until = self.obstacles.get(frozenset((a, b)))
        if until is None:
            return False
        if self.clock.now() >= until:
            del self.obstacles[frozenset((a, b))]
            return False
        return True

    def _travel(self, length_cm: float, extra_s: float) -> None:
        speed = self.settings.car.speed_cm_s * (1 + self.speed_noise * float(self._rng.uniform(-1, 1)))
        self.clock.sleep(extra_s + length_cm / speed)
        self.distance_cm += length_cm
        self.battery = max(0.0, self.battery - length_cm / 100 * self.settings.car.battery_pct_per_m)

    def _drive(self, commands: list[str], leg: int | None) -> bool:
        """Run junction commands. Returns False on an error (no line where it should be)."""
        self.mode, self.leg, self.node_index = "DRIVING", leg, 0
        cmds, i = list(commands), 0
        while True:
            cmd = cmds[i]
            if cmd == "STOP":
                return True
            new_heading = _turn(self.heading, cmd)
            nbr = next((n for n, (h, _) in self.fmap.neighbors(self.node).items() if h == new_heading), None)
            if nbr is None:
                self.mode = "ERROR"
                self._emit({"type": "error", "task_id": self.task_id,
                            "reason": f"no line to the {new_heading} after {cmd} at node {self.node_index}"})
                return False
            length = self.fmap.neighbors(self.node)[nbr][1]
            if self._obstacle_on(self.node, nbr):
                self._travel(length / 2, self.fmap.turn_cost(cmd))
                self.mode = "BLOCKED"
                self._reroute = None
                self._resume.clear()
                self._emit({"type": "obstacle", "task_id": self.task_id, "leg": leg,
                            "distance_cm": 12, "after_node_index": self.node_index})
                cleared_sent = False
                while True:
                    if self._reroute is not None:
                        cmds, i = list(self._reroute["commands"]), 0
                        self._reroute = None
                        # UTURN on the spot, drive back to the node we came from
                        self.heading = _turn(new_heading, cmds[0])
                        self.mode = "DRIVING"
                        self._travel(length / 2, self.fmap.turn_cost(cmds[0]))
                        self.node_index = 1
                        self._emit({"type": "node", "task_id": self.task_id, "leg": leg, "node_index": 1})
                        i = 1
                        break
                    if not cleared_sent and not self._obstacle_on(self.node, nbr):
                        self._emit({"type": "clear", "task_id": self.task_id})
                        cleared_sent = True
                    if cleared_sent and self._resume.is_set():
                        self.mode = "DRIVING"
                        self._travel(length / 2, 0)
                        self.node, self.heading = nbr, new_heading
                        self.node_index += 1
                        self._emit({"type": "node", "task_id": self.task_id, "leg": leg,
                                    "node_index": self.node_index})
                        i += 1
                        break
                    self.clock.sleep(0.5)
                continue
            self._travel(length, self.fmap.turn_cost(cmd))
            self.node, self.heading = nbr, new_heading
            self.node_index += 1
            self._emit({"type": "node", "task_id": self.task_id, "leg": leg, "node_index": self.node_index})
            i += 1

    def _work(self) -> None:
        p = self.settings.car
        while not self._halt.is_set():
            msg = self._jobs.get()
            if msg is None:
                return
            self.task_id = msg["task_id"]
            if msg["type"] == "charge":
                if self._drive(msg["commands"], 0):
                    self._emit({"type": "done", "task_id": self.task_id, "leg": 0,
                                "node": self.node, "action": "CHARGE"})
                    self.mode = "CHARGING"
                    while self.battery < 100:
                        self.clock.sleep(1.0)
                        self.battery = min(100.0, self.battery + self.CHARGE_PCT_PER_S)
                    self.mode = "IDLE"
                self.task_id = None
                continue
            ok = True
            for leg, spec in enumerate(msg["legs"]):
                if not self._drive(spec["commands"], leg):
                    ok = False
                    break
                self.mode = "LIFTING" if spec["action"] == "LIFT" else "LOWERING"
                self.clock.sleep(p.pickup_s if spec["action"] == "LIFT" else p.drop_s)
                self.fork = "UP" if spec["action"] == "LIFT" else "DOWN"
                self._emit({"type": "done", "task_id": self.task_id, "leg": leg, "node": self.node,
                            "action": spec["action"], "material": msg.get("material")})
            self.task_id, self.leg = None, None
            if ok:
                self.mode = "IDLE"

    def stop(self) -> None:
        self._halt.set()
        self._jobs.put(None)


class SimulatedStation:
    def __init__(self, bus, clock: Clock, settings: Settings, station: str, seed: int = 0,
                 period_s: float = 5.0, noise: float = 0.25):
        self.bus, self.clock, self.settings, self.station = bus, clock, settings, station
        self.period_s, self.noise = period_s, noise
        st = settings.stations[station]
        self.stock = {m: float(sm.stock) for m, sm in st.materials.items()}
        self.rate = {m: sm.rate_per_min / 60.0 for m, sm in st.materials.items()}
        self.stopped_s = {m: 0.0 for m in st.materials}
        self.received = {m: 0 for m in st.materials}
        self._delivered_tasks: set = set()   # MQTT may repeat a message: count each box once
        self._rng = np.random.default_rng(seed)
        self._halt = threading.Event()
        self._lock = threading.Lock()
        bus.subscribe(P.car_event("+"), self._on_car)
        bus.subscribe(P.SIM_CONTROL, self._on_sim)
        threading.Thread(target=self._loop, daemon=True).start()

    def _on_car(self, topic: str, msg: dict) -> None:
        if msg.get("type") == "done" and msg.get("action") == "LOWER" and msg.get("node") == self.station:
            m = msg.get("material")
            if m in self.stock and msg.get("task_id") not in self._delivered_tasks:
                self._delivered_tasks.add(msg.get("task_id"))
                with self._lock:
                    qty = self.settings.materials[m].delivery_qty
                    self.stock[m] += qty
                    self.received[m] += qty
                self._publish(m)

    def _on_sim(self, topic: str, msg: dict) -> None:
        if msg.get("cmd") == "set_stock" and msg.get("station") == self.station and msg.get("material") in self.stock:
            with self._lock:
                self.stock[msg["material"]] = float(msg["stock"])
            self._publish(msg["material"])

    def _publish(self, m: str) -> None:
        self.bus.publish(P.station_stock(self.station),
                         {"material": m, "stock": int(round(self.stock[m])), "ts": round(self.clock.now(), 1)},
                         retain=False)

    def _loop(self) -> None:
        for m in self.stock:
            self._publish(m)
        while not self._halt.is_set():
            self.clock.sleep(self.period_s)
            with self._lock:
                for m in self.stock:
                    if self.stock[m] <= 0:
                        self.stopped_s[m] += self.period_s
                        continue
                    use = self.rate[m] * self.period_s * max(0.0, 1 + self.noise * self._rng.standard_normal())
                    if use >= self.stock[m]:  # ran out part way through this period
                        self.stopped_s[m] += self.period_s * (1 - self.stock[m] / use)
                    self.stock[m] = max(0.0, self.stock[m] - use)
            for m in self.stock:
                self._publish(m)

    def stop(self) -> None:
        self._halt.set()
