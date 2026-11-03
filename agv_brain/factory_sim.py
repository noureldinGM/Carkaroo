"""A whole simulated factory: controller (AI) + simulated car + simulated stations.

    sim = FactorySim(policy="ml", speed=20)
    sim.run_for(sim_minutes=10)
    print(sim.summary())

`speed` = how many simulated seconds pass per real second.
"""

from __future__ import annotations

import time

from agv_brain.bus import Clock, MemoryBus
from agv_brain.controller import Controller
from agv_brain.dispatcher import Dispatcher
from agv_brain.eventlog import EventLog
from agv_brain.models import CarState
from agv_brain.sim_devices import SimulatedCar, SimulatedStation
from agv_brain.simulator import load_context


class FactorySim:
    def __init__(self, policy: str = "ml", speed: float = 20.0, seed: int = 0, bus=None,
                 log: bool = True, battery: float = 90.0, period_s: float | None = None):
        self.clock = Clock(speed)
        self.bus = bus or MemoryBus()
        dispatcher = Dispatcher.from_config(policy=policy)
        self.log = EventLog() if log else None
        # the controller plans on its own map; the car drives on a separate copy (the "real" track)
        self.controller = Controller(self.bus, dispatcher, self.clock, log=self.log,
                                     period_s=period_s or min(0.5, max(0.05, 5.0 / speed)))
        truth = load_context()
        s = truth.settings
        self.car = SimulatedCar(self.bus, self.clock, truth.fmap, s,
                                start=CarState(s.car.dock, s.car.start_heading, battery), seed=seed)
        self.stations = [SimulatedStation(self.bus, self.clock, s, sid, seed=seed + k)
                         for k, sid in enumerate(s.stations)]

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
            "distance_m": round(self.car.distance_cm / 100, 1),
            "battery": round(self.car.battery, 1),
            "log_folder": str(self.log.folder) if self.log else None,
        }

    def stop(self) -> None:
        self.controller.stop()
        self.car.stop()
        for st in self.stations:
            st.stop()
        if self.log:
            self.log.close()
