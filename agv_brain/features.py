"""Turns jobs into the numbers the ML ranker learns from.

Per job (relative to where the car is now):
    stock, rate, time to stockout, time to safety level, trip time, slack,
    criticality, waiting time, ...
Per pair (i, j), "should i go before j?":
    [features of i, features of j, i - j, how late each would be if served second]
"""

from __future__ import annotations

import numpy as np

from agv_brain.models import CarState, Job
from agv_brain.simulator import Context, job_leg

CAP_S = 3600.0  # time features are capped at one hour

JOB_FEATURES = [
    "stock",
    "rate_per_min",
    "stockout_s",
    "below_safety_s",
    "trip_s",
    "to_rack_s",
    "slack_s",          # stockout - trip: negative means the line stops even if served now
    "safety_slack_s",   # below_safety - trip
    "criticality",
    "wait_s",
    "safety_gap",       # how far below the safety stock (0 = at or above it, 1 = empty)
    "n_jobs",
    "slack_rank",       # 0 = smallest slack of all open requests, 1 = largest
    "min_other_slack_s",
]

PAIR_EXTRA = [
    "chain_ij_s",           # time to finish j if i goes first
    "chain_ji_s",           # time to finish i if j goes first
    "j_late_if_i_first_s",  # how long j's station stops if i goes first
    "i_late_if_j_first_s",
    "late_diff_crit",       # criticality-weighted difference of the two above
]

PAIR_FEATURES = ([f"i_{f}" for f in JOB_FEATURES] + [f"j_{f}" for f in JOB_FEATURES]
                 + [f"d_{f}" for f in JOB_FEATURES] + PAIR_EXTRA)


def _cap(x: float) -> float:
    return float(np.clip(x, -CAP_S, CAP_S))


def job_matrix(ctx: Context, jobs: list[Job], car: CarState) -> tuple[np.ndarray, list]:
    """Feature matrix (n_jobs x len(JOB_FEATURES)) and each job's leg from the car."""
    legs = [job_leg(ctx, car, j) for j in jobs]
    slack = np.array([j.stockout_s - lg.duration_s for j, lg in zip(jobs, legs)])
    slack = np.clip(slack, -CAP_S, CAP_S)
    n = len(jobs)
    order = slack.argsort().argsort()
    rows = []
    for k, (j, lg) in enumerate(zip(jobs, legs)):
        others = np.delete(slack, k)
        safety_gap = 0.0
        if j.safety_stock > 0:
            safety_gap = float(np.clip((j.safety_stock - j.stock) / j.safety_stock, 0, 1))
        rows.append([
            j.stock,
            j.rate_per_s * 60.0,
            _cap(j.stockout_s),
            _cap(j.below_safety_s),
            lg.duration_s,
            lg.to_rack.time_s,
            slack[k],
            _cap(j.below_safety_s - lg.duration_s),
            j.criticality,
            j.wait_s,
            safety_gap,
            n,
            order[k] / (n - 1) if n > 1 else 0.0,
            others.min() if len(others) else CAP_S,
        ])
    return np.array(rows, dtype=float), legs


def pair_matrix(ctx: Context, jobs: list[Job], car: CarState,
                pairs: list[tuple[int, int]] | None = None) -> tuple[np.ndarray, list[tuple[int, int]]]:
    """One row per ordered pair (i, j), i != j."""
    n = len(jobs)
    if pairs is None:
        pairs = [(i, j) for i in range(n) for j in range(n) if i != j]
    F, legs = job_matrix(ctx, jobs, car)
    # finish time of b when a goes first: a's trip, then from a's station to b
    follow: dict[tuple[int, int], float] = {}
    for a in range(n):
        for b in range(n):
            if a != b:
                follow[a, b] = legs[a].duration_s + job_leg(ctx, legs[a].end, jobs[b]).duration_s
    rows = []
    for i, j in pairs:
        chain_ij, chain_ji = follow[i, j], follow[j, i]
        late_j = max(0.0, chain_ij - jobs[j].stockout_s)
        late_i = max(0.0, chain_ji - jobs[i].stockout_s)
        late_diff = late_j * jobs[j].criticality - late_i * jobs[i].criticality
        rows.append(np.concatenate([F[i], F[j], F[i] - F[j],
                                    [chain_ij, chain_ji, _cap(late_j), _cap(late_i), _cap(late_diff)]]))
    return np.array(rows, dtype=float), pairs
