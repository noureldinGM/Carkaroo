"""The "teacher": finds the best delivery order by trying every order.

Exhaustive search with pruning is exact and fast for the handful of requests a
single car has at once (7 requests = 5040 orders). It is used to label training
data for the ML ranker, to measure how close the ranker gets, and to explain
decisions ("what if the other request went first?").
"""

from __future__ import annotations

import math

from agv_brain.models import CarState, Job
from agv_brain.simulator import Context, job_cost, job_leg

MAX_EXACT = 7


def _search(ctx: Context, jobs: list[Job], car: CarState, t0: float, acc0: float,
            bound: float = math.inf) -> tuple[float, list[int]]:
    """Best (total cost, order of indices) for `jobs` starting at time t0."""
    travel_w = ctx.settings.cost.travel_weight
    legs: dict[tuple[CarState, int], tuple[float, CarState]] = {}
    best_cost = bound
    best_seq: list[int] = []

    def leg(state: CarState, i: int) -> tuple[float, CarState]:
        key = (state, i)
        if key not in legs:
            lg = job_leg(ctx, state, jobs[i])
            legs[key] = (lg.duration_s, lg.end)
        return legs[key]

    def dfs(state: CarState, t: float, remaining: tuple[int, ...], acc: float, seq: list[int]):
        nonlocal best_cost, best_seq
        if acc + travel_w * t >= best_cost:
            return  # every cost term is >= 0, so this branch cannot win
        if not remaining:
            best_cost, best_seq = acc + travel_w * t, list(seq)
            return
        for i in remaining:
            dur, end = leg(state, i)
            finish = t + dur
            cost, _, _ = job_cost(ctx, jobs[i], finish)
            seq.append(i)
            dfs(end, finish, tuple(r for r in remaining if r != i), acc + cost, seq)
            seq.pop()

    dfs(car, t0, tuple(range(len(jobs))), acc0, [])
    return best_cost, best_seq


def best_order(ctx: Context, jobs: list[Job], car: CarState) -> tuple[list[Job], float]:
    if len(jobs) > MAX_EXACT:
        raise ValueError(f"exact search is limited to {MAX_EXACT} requests, got {len(jobs)}")
    if not jobs:
        return [], 0.0
    cost, seq = _search(ctx, jobs, car, 0.0, 0.0)
    return [jobs[i] for i in seq], cost


def first_choice_costs(ctx: Context, jobs: list[Job], car: CarState) -> list[float]:
    """For each job: the best total cost achievable if that job is served first."""
    if len(jobs) > MAX_EXACT:
        raise ValueError(f"exact search is limited to {MAX_EXACT} requests, got {len(jobs)}")
    out = []
    for i, job in enumerate(jobs):
        lg = job_leg(ctx, car, job)
        cost, _, _ = job_cost(ctx, job, lg.duration_s)
        rest = jobs[:i] + jobs[i + 1:]
        if rest:
            total, _ = _search(ctx, rest, lg.end, lg.duration_s, cost)
        else:
            total = cost + ctx.settings.cost.travel_weight * lg.duration_s
        out.append(total)
    return out


def best_order_starting_with(ctx: Context, jobs: list[Job], car: CarState, first: int) -> list[Job]:
    """Best full order given that jobs[first] is served first."""
    lg = job_leg(ctx, car, jobs[first])
    cost, _, _ = job_cost(ctx, jobs[first], lg.duration_s)
    rest = jobs[:first] + jobs[first + 1:]
    if not rest:
        return [jobs[first]]
    _, seq = _search(ctx, rest, lg.end, lg.duration_s, cost)
    return [jobs[first]] + [rest[i] for i in seq]
