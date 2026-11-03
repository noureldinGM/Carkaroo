"""Scores a delivery order, and generates random factory situations for training.

The car carries one box per trip: drive to the material's rack, pick up, drive to
the station, drop off. While it drives, every station keeps consuming, so the
finish time of each delivery decides whether that station stops.

Cost of one delivery finishing at time F (seconds from now):
    criticality * (stop_weight * stopped_s + below_safety_weight * below_safety_s)
  + flow_weight * (1 + wait_s / aging_s) * F
and the whole plan adds travel_weight * (finish time of the last delivery).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from agv_brain.factory_map import HEADINGS, FactoryMap, Route, opposite
from agv_brain.models import CarState, Job, Settings, load_settings


@dataclass(frozen=True)
class Context:
    fmap: FactoryMap
    settings: Settings


def load_context(layout=None, materials=None) -> Context:
    """Context from the config files (defaults: config/factory_layout.yaml, config/materials.yaml)."""
    settings = load_settings(materials)
    return Context(FactoryMap.from_yaml(layout, settings.car), settings)


@dataclass(frozen=True)
class Leg:
    to_rack: Route
    to_station: Route
    duration_s: float
    end: CarState


@dataclass
class TaskOutcome:
    job: Job
    leg: Leg
    start_s: float
    finish_s: float
    stop_s: float
    below_s: float
    cost: float


@dataclass
class Schedule:
    tasks: list[TaskOutcome]
    total_cost: float
    total_time_s: float
    distance_cm: float

    @property
    def stop_s(self) -> float:
        return sum(t.stop_s for t in self.tasks)

    @property
    def weighted_stop_s(self) -> float:
        return sum(t.stop_s * t.job.criticality for t in self.tasks)

    def stop_by_job(self) -> dict[str, float]:
        return {t.job.id: t.stop_s for t in self.tasks}


def job_leg(ctx: Context, car: CarState, job: Job) -> Leg:
    to_rack = ctx.fmap.route(car.node, job.rack, car.heading)
    to_station = ctx.fmap.route(job.rack, job.station, to_rack.end_heading)
    p = ctx.settings.car
    duration = to_rack.time_s + p.pickup_s + to_station.time_s + p.drop_s
    end = CarState(job.station, to_station.end_heading, car.battery_pct)
    return Leg(to_rack, to_station, duration, end)


def job_cost(ctx: Context, job: Job, finish_s: float) -> tuple[float, float, float]:
    """(cost, stopped seconds, seconds below safety stock) for a delivery at finish_s."""
    c = ctx.settings.cost
    stop = max(0.0, finish_s - job.stockout_s)
    below = max(0.0, finish_s - job.below_safety_s)
    flow = c.flow_weight * (1.0 + job.wait_s / c.aging_s) * finish_s
    cost = job.criticality * (c.stop_weight * stop + c.below_safety_weight * below) + flow
    return cost, stop, below


def simulate(ctx: Context, order: list[Job], car: CarState) -> Schedule:
    t = 0.0
    distance = 0.0
    state = car
    tasks = []
    for job in order:
        leg = job_leg(ctx, state, job)
        start, t = t, t + leg.duration_s
        cost, stop, below = job_cost(ctx, job, t)
        tasks.append(TaskOutcome(job, leg, start, t, stop, below, cost))
        distance += leg.to_rack.distance_cm + leg.to_station.distance_cm
        state = leg.end
    total = sum(x.cost for x in tasks) + ctx.settings.cost.travel_weight * t
    return Schedule(tasks, total, t, distance)


def shift(job: Job, dt_s: float) -> Job:
    """The same job seen dt_s seconds later (stock consumed, waited longer).

    Stock is clipped at 0: time a station was already stopped is in the past and
    cannot be changed by any decision made now.
    """
    return Job(job.id, job.material, job.station, job.rack,
               stock=max(0.0, job.stock - job.rate_per_s * dt_s),
               rate_per_s=job.rate_per_s, safety_stock=job.safety_stock,
               criticality=job.criticality, wait_s=job.wait_s + dt_s)


# ---------------------------------------------------------------------------
# Random scenarios (training and evaluation data)
# ---------------------------------------------------------------------------

def random_car(rng: np.random.Generator, fmap: FactoryMap) -> CarState:
    nodes = list(fmap.nodes)
    dead_ends = [n for n in nodes if len(fmap.neighbors(n)) == 1]
    node = rng.choice(dead_ends) if rng.random() < 0.7 else rng.choice(nodes)
    node = str(node)
    if len(fmap.neighbors(node)) == 1:
        heading = fmap.arrival_heading(node)
    else:
        came_from = [h for h, _ in fmap.neighbors(node).values()]
        heading = opposite(str(rng.choice(came_from)))
    assert heading in HEADINGS
    return CarState(node, heading, float(rng.uniform(30, 100)))


def random_jobs(rng: np.random.Generator, ctx: Context, n: int) -> list[Job]:
    s = ctx.settings
    combos = [(st, m) for st in s.stations for m in s.materials]
    picks = rng.choice(len(combos), size=n, replace=False)
    jobs = []
    for k in picks:
        station, material = combos[int(k)]
        rate_per_min = rng.uniform(0.5, 6.0)
        r = rng.random()
        if r < 0.3:
            stockout = rng.uniform(0, 60)
        elif r < 0.7:
            stockout = rng.uniform(60, 240)
        else:
            stockout = rng.uniform(240, 900)
        rate = rate_per_min / 60.0
        jobs.append(Job(
            id=f"{material}@{station}", material=material, station=station,
            rack=s.materials[material].rack,
            stock=round(stockout * rate, 2), rate_per_s=rate,
            safety_stock=round(rate * rng.uniform(30, 150), 2),
            criticality=int(rng.integers(1, 4)),
            wait_s=float(min(600.0, rng.exponential(60.0))),
        ))
    return jobs


def random_scenario(rng: np.random.Generator, ctx: Context,
                    n_range: tuple[int, int] = (2, 6)) -> tuple[CarState, list[Job]]:
    n = int(rng.integers(n_range[0], n_range[1] + 1))
    return random_car(rng, ctx.fmap), random_jobs(rng, ctx, n)
