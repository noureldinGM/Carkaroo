"""Simple dispatching rules to compare the ML ranker against.

Every policy is a score function: score(ctx, jobs, car) -> array, where a higher
score means "serve sooner". `rollout` applies a policy the way the real system
does: choose one delivery, drive it, look at the factory again, choose the next.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from agv_brain.models import CarState, Job
from agv_brain.simulator import Context, job_leg, shift

ScoreFn = Callable[[Context, list[Job], CarState], np.ndarray]


def fifo(ctx: Context, jobs: list[Job], car: CarState) -> np.ndarray:
    """First come, first served: the oldest request goes first."""
    return np.array([j.wait_s for j in jobs])


def nearest(ctx: Context, jobs: list[Job], car: CarState) -> np.ndarray:
    """Shortest trip first."""
    return np.array([-job_leg(ctx, car, j).duration_s for j in jobs])


def earliest_stockout(ctx: Context, jobs: list[Job], car: CarState) -> np.ndarray:
    """The station that runs out first goes first."""
    return np.array([-min(j.stockout_s, 1e6) for j in jobs])


def weighted_rules(ctx: Context, jobs: list[Job], car: CarState) -> np.ndarray:
    """Hand-tuned rule: least slack first, scaled by criticality, small bonus for waiting."""
    scores = []
    for j in jobs:
        slack = min(j.stockout_s, 1e6) - job_leg(ctx, car, j).duration_s
        key = slack / j.criticality if slack >= 0 else slack * j.criticality
        scores.append(-key + 0.05 * j.wait_s)
    return np.array(scores)


BASELINES: dict[str, ScoreFn] = {
    "fifo": fifo,
    "nearest": nearest,
    "earliest_stockout": earliest_stockout,
    "weighted_rules": weighted_rules,
}


def rollout(score_fn: ScoreFn, ctx: Context, jobs: list[Job], car: CarState) -> list[Job]:
    """Order produced by re-deciding after every delivery."""
    remaining = list(jobs)
    order: list[Job] = []
    t, state = 0.0, car
    while remaining:
        now_view = [shift(j, t) for j in remaining]
        k = int(np.argmax(score_fn(ctx, now_view, state)))
        job = remaining.pop(k)
        leg = job_leg(ctx, state, job)
        t += leg.duration_s
        state = leg.end
        order.append(job)
    return order
