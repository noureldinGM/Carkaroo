"""Changing demand: how fast each station really uses material, minute by minute.

The ranker's simulator (simulator.py) assumes a constant usage rate, which is
right for choosing the next few deliveries. The shortage-risk model
(risk_model.py) predicts further ahead, so it needs demand that changes:

    rate(t) = base rate
              x shift multiplier       (planned: day / evening / night)
              x (1 + active orders)    (production orders; most are announced
                                        a little before they start)
              x surge                  (unplanned rush, nobody knows in advance)
              x 0 during downtime      (planned maintenance)
              x noise                  (+-15 % from moment to moment)

Stock follows   stock(t) = stock(t - dt) + deliveries - used,   never below 0,
and the load cell under the bin reports whole units, like the real sensor.
A simple replenishment loop (order when the reading reaches a reorder point,
the box arrives after a delay) keeps the stock looking like a running factory.

Everything here is SIMULATED. The shapes (shifts, orders, surges, downtime) are
common in real production, but no number comes from a real factory.

Time is compressed for the table-top factory: a "shift" lasts minutes, not hours.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

SHIFT_NAMES = ("day", "evening", "night")


@dataclass(frozen=True)
class Order:
    announce_s: float   # when the factory knows about it
    start_s: float
    end_s: float
    boost: float        # extra usage while it runs: rate x (1 + boost)


@dataclass(frozen=True)
class Window:
    start_s: float
    end_s: float
    factor: float = 0.0


@dataclass
class ShiftPlan:
    """Planned shift pattern, shared by every station of one factory timeline."""
    length_s: float
    offset_s: float                     # where in the cycle the timeline starts
    mult: tuple[float, float, float]    # planned usage multiplier per shift

    def index(self, t) -> np.ndarray:
        return (((np.asarray(t) + self.offset_s) // self.length_s) % 3).astype(int)

    def multiplier(self, t) -> np.ndarray:
        return np.asarray(self.mult)[self.index(t)]

    def to_change_s(self, t: float) -> float:
        return self.length_s - ((t + self.offset_s) % self.length_s)


@dataclass
class StationTrace:
    """One (station, material) over a whole timeline."""
    station: str
    material: str
    criticality: int
    capacity: float
    safety_stock: float
    base_rate_per_s: float
    delivery_qty: float
    plan: ShiftPlan
    orders: list[Order]
    surges: list[Window]
    downtime: list[Window]
    t: np.ndarray                 # time of each step (s)
    rate: np.ndarray              # TRUE usage rate during each step (units/s), ignoring empty bins
    stock: np.ndarray             # TRUE stock at each step, after deliveries
    reading: np.ndarray           # what the load cell reports (whole units)
    deliveries: list[tuple[float, float]] = field(default_factory=list)  # (time, qty)

    @property
    def dt(self) -> float:
        return float(self.t[1] - self.t[0])

    def step(self, t_s: float) -> int:
        return int(round(t_s / self.dt))


def _poisson_times(rng: np.random.Generator, rate_per_s: float, t0: float, t1: float) -> list[float]:
    out, t = [], t0
    if rate_per_s <= 0:
        return out
    while True:
        t += rng.exponential(1.0 / rate_per_s)
        if t >= t1:
            return out
        out.append(t)


def random_plan(rng: np.random.Generator) -> ShiftPlan:
    mult = [1.0, float(rng.uniform(0.6, 1.2)), float(rng.uniform(0.2, 0.6))]
    order = rng.permutation(3)              # the timeline can start in any shift
    return ShiftPlan(length_s=float(rng.uniform(300, 1200)),
                     offset_s=float(rng.uniform(0, 3 * 1200)),
                     mult=tuple(mult[i] for i in order))


def simulate_station(rng: np.random.Generator, plan: ShiftPlan, *, station: str, material: str,
                     criticality: int, capacity: float, safety_stock: float, base_rate_per_min: float,
                     delivery_qty: float, trip_s: float, duration_s: float = 3600.0,
                     dt: float = 2.0) -> StationTrace:
    """Simulate one station-material for `duration_s` seconds.

    `trip_s` is how long the car needs from the dock to this station (from the
    track), used for the delay of the replenishment loop.
    """
    n = int(duration_s / dt) + 1
    t = np.arange(n) * dt
    base = base_rate_per_min / 60.0

    # production orders: 0-12 per hour; most are announced 0-3 min before they start
    orders = []
    for start in _poisson_times(rng, rng.uniform(0, 12) / 3600.0, -300.0, duration_s):
        announced = rng.random() < 0.7
        lead = rng.uniform(0, 180) if announced else 0.0
        orders.append(Order(start - lead, start, start + rng.uniform(60, 400), float(rng.uniform(0.3, 1.0))))
    # unplanned surges: 0-4 per hour
    surges = [Window(s, s + rng.uniform(30, 150), float(rng.uniform(1.5, 2.5)))
              for s in _poisson_times(rng, rng.uniform(0, 4) / 3600.0, 0.0, duration_s)]
    # planned downtime: about half the timelines have one maintenance stop
    downtime = []
    if rng.random() < 0.5:
        s = rng.uniform(0, duration_s)
        downtime.append(Window(s, s + rng.uniform(60, 300)))

    mult = plan.multiplier(t)
    boost = np.zeros(n)
    for o in orders:
        boost[(t >= o.start_s) & (t < o.end_s)] += o.boost
    surge = np.ones(n)
    for w in surges:
        surge[(t >= w.start_s) & (t < w.end_s)] = w.factor
    running = np.ones(n)
    for w in downtime:
        running[(t >= w.start_s) & (t < w.end_s)] = 0.0
    noise = np.clip(1 + 0.15 * rng.standard_normal(n), 0.3, 1.7)
    rate = base * mult * (1 + boost) * surge * running * noise

    # stock with a simple replenishment loop
    reorder = safety_stock * rng.uniform(1.0, 2.5)
    stock = np.empty(n)
    s = float(rng.uniform(0.3, 1.0) * capacity)
    arrive_at = None
    deliveries = []
    for k in range(n):
        if arrive_at is not None and t[k] >= arrive_at:
            qty = min(delivery_qty, capacity - s)
            s += qty
            deliveries.append((float(t[k]), float(qty)))
            arrive_at = None
        stock[k] = s
        if arrive_at is None and np.floor(s) <= reorder:
            # the car may be busy: the box arrives after 1-4 trips
            arrive_at = t[k] + trip_s * rng.uniform(1.0, 4.0)
        s = max(0.0, s - rate[k] * dt)

    return StationTrace(station, material, criticality, capacity, safety_stock, base,
                        delivery_qty, plan, orders, surges, downtime, t, rate, stock,
                        np.floor(stock + 1e-9), deliveries)


__all__ = ["SHIFT_NAMES", "Order", "Window", "ShiftPlan", "StationTrace",
           "random_plan", "simulate_station"]
