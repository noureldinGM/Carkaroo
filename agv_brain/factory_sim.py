"""A factory session: the controller (AI) plus whichever devices are simulated.

    sim = FactorySim(policy="ml", speed=20)
    sim.run_for(sim_minutes=10)
    print(sim.summary())

`speed` = how many simulated seconds pass per real second (1 with real devices).
With `sim_car=False` and/or `sim_stations=False` the real car or station nodes take
their place over MQTT; the website's Setup page switches between these modes.
"""

from __future__ import annotations

import time

from agv_brain.bus import Clock, MemoryBus, ScopedBus
from agv_brain.controller import Controller
from agv_brain.dispatcher import Dispatcher
from agv_brain.eventlog import EventLog
from agv_brain.models import CarState
from agv_brain.sim_devices import SimulatedCar, SimulatedStation
from agv_brain.simulator import load_context


class FactorySim:
    def __init__(self, policy: str = "ml", speed: float = 20.0, seed: int = 0, bus=None,
                 log: bool = True, battery: float = 90.0, period_s: float | None = None,
                 layout=None, sim_car: bool = True, sim_stations: bool = True, car_id: str = "AGV-1"):
        if not (sim_car and sim_stations):
            speed = 1.0   # real devices live in real time
        self.clock = Clock(speed)
        # on a shared bus, a scoped view lets stop() remove everything this session added
        self.bus = ScopedBus(bus) if bus is not None else MemoryBus()
        dispatcher = Dispatcher.from_config(policy=policy, layout=layout)
        self.log = EventLog() if log else None
        # the controller plans on its own map; the car drives on a separate copy (the "real" track)
        self.controller = Controller(self.bus, dispatcher, self.clock, car_id=car_id, log=self.log,
                                     period_s=period_s or min(0.5, max(0.05, 5.0 / speed)))
        truth = load_context(layout)
        s = truth.settings
        self.car = SimulatedCar(self.bus, self.clock, truth.fmap, s, car_id=car_id,
                                start=CarState(s.car.dock, s.car.start_heading, battery), seed=seed) if sim_car else None
        self.stations = [SimulatedStation(self.bus, self.clock, s, sid, seed=seed + k)
                         for k, sid in enumerate(s.stations)] if sim_stations else []

    def control(self, msg: dict) -> None:
        """Simulation-only commands: obstacles, stock changes, battery."""
        from agv_brain.protocol import SIM_CONTROL
        self.bus.publish(SIM_CONTROL, msg)

    def run_for(self, sim_minutes: float) -> None:
        end = self.clock.now() + sim_minutes * 60
        while self.clock.now() < end:
            time.sleep(0.05)

    def summary(self) -> dict:
        snap = self.controller.snapshot()
        stopped = {f"{st.station}:{m}": round(v, 1) for st in self.stations for m, v in st.stopped_s.items()}
        return {
            "sim_minutes": round(self.clock.now() / 60, 1),
            "policy": snap["policy"],
            "deliveries": snap["stats"]["deliveries"],
            "line_stop_s": round(sum(stopped.values()), 1),
            "line_stop_by_station": {k: v for k, v in stopped.items() if v > 0},
            "decisions": snap["stats"]["decisions"],
            "optimizer_agrees": snap["stats"]["optimizer_agrees"],
            "regret_pct": round(100 * snap["stats"]["regret"] / max(snap["stats"]["best_cost"], 1e-9), 2),
            "obstacles": snap["stats"]["obstacles"],
            "reroutes": snap["stats"]["reroutes"],
            "charges": snap["stats"]["charges"],
            "distance_m": round(self.car.distance_cm / 100, 1) if self.car else None,
            "battery": round(self.car.battery, 1) if self.car else snap["car"]["battery"],
            "log_folder": str(self.log.folder) if self.log else None,
        }

    def stop(self) -> None:
        self.controller.stop()
        if self.car:
            self.car.stop()
        for st in self.stations:
            st.stop()
        self.bus.close()
        if self.car and isinstance(self.bus, ScopedBus):
            # replace the simulated car's retained status, so the next session (maybe the
            # real car) does not see a car that is not there
            from agv_brain.protocol import car_status
            self.bus.inner.publish(car_status(self.car.car_id), {"state": "OFFLINE"}, qos=1, retain=True)
        if self.log:
            self.log.close()
