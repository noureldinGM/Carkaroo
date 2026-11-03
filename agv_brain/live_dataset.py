"""Training data from live operation (DAgger-style imitation learning).

Random situations (dataset.py) are not shaped like the queues the AI meets when
the factory actually runs. There, the need detector creates many requests at
once, most of them with moderate slack, and a choice often affects the
next ones. A model trained only on random situations matches the optimizer less
often live than in the offline tests ("distribution shift").

The fix is to run the factory loop fast (no threads, no bus), let the current
model make the decisions, record every situation it faces, and have the exact
optimizer label it. Training on those situations teaches the model exactly
where it goes wrong. Some choices are random (epsilon) so that it also sees
situations its own mistakes lead to.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace

import numpy as np

from agv_brain.dispatcher import Dispatcher
from agv_brain.layouts import layout_pool
from agv_brain.models import CarState, Job, Request, initial_state
from agv_brain.need_detector import detect_needs
from agv_brain.optimizer import MAX_EXACT
from agv_brain.safety import filter_jobs
from agv_brain.simulator import Context, job_leg


@dataclass
class Situation:
    ctx: Context        # the track, car speed and settings of that episode
    car: CarState
    jobs: list[Job]
    layout: str


def _randomize(ctx: Context, rng: np.random.Generator) -> Context:
    """Same track, different production: rates, stocks, criticalities, capacities."""
    s = copy.deepcopy(ctx.settings)
    for st in s.stations.values():
        st.criticality = int(rng.integers(1, 4))
        for sm in st.materials.values():
            sm.rate_per_min = float(sm.rate_per_min * rng.uniform(0.6, 1.5))
            sm.capacity = float(rng.integers(30, 70))
            sm.safety_stock = float(max(2, round(sm.rate_per_min * rng.uniform(1, 3))))
            sm.stock = float(rng.uniform(0.1, 0.8) * sm.capacity)
    for m in s.materials:
        s.materials[m] = replace(s.materials[m], warehouse_stock=10_000)
    return Context(ctx.fmap, s)


def run_episode(ctx: Context, score_fn, rng: np.random.Generator, minutes: float = 60,
                step_s: float = 5.0, epsilon: float = 0.2, layout: str = "ours") -> list[Situation]:
    """Fast factory loop; returns every decision situation it met."""
    ctx = _randomize(ctx, rng)
    s = ctx.settings
    d = Dispatcher(ctx, policy="weighted_rules")  # only used to turn requests into jobs
    state = initial_state(s, CarState(s.car.dock, s.car.start_heading, 100.0))
    true_rate = {(sid, m): sm.rate_per_min / 60 for sid, st in state.stations.items()
                 for m, sm in st.materials.items()}
    requests: dict[str, Request] = {}
    active = None  # (request, job, finish time, end car state)
    out: list[Situation] = []
    t = 0.0
    while t < minutes * 60:
        for (sid, m), rate in true_rate.items():
            sm = state.stations[sid].materials[m]
            sm.stock = max(0.0, sm.stock - rate * step_s * max(0.0, 1 + 0.25 * rng.standard_normal()))
        if active and t >= active[2]:
            req, job, _, end = active
            state.stations[job.station].materials[job.material].stock += s.materials[job.material].delivery_qty
            state.car = end
            active = None
        state.now_s = t
        open_reqs = list(requests.values()) + ([active[0]] if active else [])
        taken = {(r.station, r.material) for r in open_reqs}
        for need in detect_needs(ctx, state, open_reqs).needs:
            r = need.request
            if (r.station, r.material) not in taken:
                requests[r.id] = r
                taken.add((r.station, r.material))
        if active is None and requests:
            jobs, _ = d.jobs_from_requests(state, list(requests.values()))
            jobs = filter_jobs(ctx, state, jobs).jobs
            if jobs:
                out.append(Situation(ctx, state.car, list(jobs), layout))
                if rng.random() < epsilon:
                    k = int(rng.integers(len(jobs)))
                else:
                    k = int(np.argmax(score_fn(ctx, jobs, state.car)))
                job = jobs[k]
                leg = job_leg(ctx, state.car, job)
                active = (requests.pop(job.id), job, t + leg.duration_s, leg.end)
        t += step_s
    return out


def collect(ctx: Context, score_fn, episodes: int, seed: int = 7, minutes: float = 60,
            random_layouts: int = 0, layout_share: float = 0.5, epsilon: float = 0.2) -> list[Situation]:
    rng = np.random.default_rng(seed)
    pool = layout_pool(random_layouts, seed + 5000, ctx.settings) if random_layouts else []
    out = []
    for e in range(episodes):
        if pool and rng.random() < layout_share:
            k = int(rng.integers(len(pool)))
            out += run_episode(pool[k], score_fn, rng, minutes, epsilon=epsilon, layout=f"random-{k}")
        else:
            speed = ctx.settings.car.speed_cm_s * float(rng.uniform(0.6, 1.5))
            car = replace(ctx.settings.car, speed_cm_s=speed)
            vctx = Context(ctx.fmap.with_car(car), replace(ctx.settings, car=car))
            out += run_episode(vctx, score_fn, rng, minutes, epsilon=epsilon)
    return out


def usable(situations: list[Situation]) -> list[Situation]:
    """Situations the exact teacher can label (2..MAX_EXACT requests)."""
    return [x for x in situations if 2 <= len(x.jobs) <= MAX_EXACT]


def live_accuracy(ctx: Context, score_fn, episodes: int = 40, seed: int = 999) -> dict:
    """Top-1 accuracy and extra cost when `score_fn` makes every decision of the
    factory runs (no random choices), checked against the exact optimizer."""
    from agv_brain.optimizer import first_choice_costs

    sits = usable(collect(ctx, score_fn, episodes, seed=seed, random_layouts=60, layout_share=0.5,
                          epsilon=0.0))
    hits, regrets = [], []
    for x in sits:
        costs = first_choice_costs(x.ctx, x.jobs, x.car)
        best = min(costs)
        k = int(np.argmax(score_fn(x.ctx, x.jobs, x.car)))
        hits.append(costs[k] <= best + 1e-6 * max(1.0, abs(best)))
        regrets.append((costs[k] - best) / max(best, 1e-9))
    return {"top1": float(np.mean(hits)), "regret_pct": 100 * float(np.mean(regrets)), "decisions": len(sits)}
