"""Builds the training dataset: random factory situations labelled by the teacher.

The ranker only sees numbers (stock, usage rate, time to empty, trip time,
criticality, waiting time), never material names, so it works for any number of
materials. To make it robust to the real car, each scenario also uses a random
car speed between 0.6x and 1.5x the configured speed ("domain randomization"):
the model keeps working after the real car is calibrated.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from agv_brain.features import JOB_FEATURES, PAIR_FEATURES, job_matrix
from agv_brain.optimizer import first_choice_costs
from agv_brain.ranker import TIE_EPS, pair_examples
from agv_brain.simulator import Context, random_scenario

SPEED_FACTORS = (0.6, 0.8, 1.0, 1.2, 1.5)


@dataclass
class Dataset:
    X: np.ndarray
    y: np.ndarray
    w: np.ndarray
    groups: np.ndarray                   # scenario id of every pair row
    job_rows: list[dict] = field(default_factory=list)  # one readable row per request


def speed_variants(ctx: Context, factors=SPEED_FACTORS) -> list[Context]:
    out = []
    for f in factors:
        car = replace(ctx.settings.car, speed_cm_s=ctx.settings.car.speed_cm_s * f)
        out.append(Context(ctx.fmap.with_car(car), replace(ctx.settings, car=car)))
    return out


def generate(ctx: Context, n_scenarios: int, seed: int = 1,
             n_range: tuple[int, int] = (2, 6), randomize_speed: bool = True) -> Dataset:
    rng = np.random.default_rng(seed)
    variants = speed_variants(ctx) if randomize_speed else [ctx]
    Xs, ys, ws, gs, rows = [], [], [], [], []
    for sid in range(n_scenarios):
        vctx = variants[int(rng.integers(len(variants)))]
        car, jobs = random_scenario(rng, vctx, n_range)
        costs = first_choice_costs(vctx, jobs, car)
        X, y, w = pair_examples(vctx, jobs, car, costs)
        Xs.append(X), ys.append(y), ws.append(w), gs.append(np.full(len(y), sid))

        F, _ = job_matrix(vctx, jobs, car)
        best = min(costs)
        for job, f, c in zip(jobs, F, costs):
            row = {"scenario": sid, "request": job.id, "car_node": car.node,
                   "car_heading": car.heading, "car_speed_cm_s": vctx.settings.car.speed_cm_s,
                   "material": job.material, "station": job.station}
            row.update({name: round(float(v), 3) for name, v in zip(JOB_FEATURES, f)})
            row["teacher_cost_if_first"] = round(c, 3)
            row["teacher_best_first"] = int(c <= best + TIE_EPS)
            rows.append(row)
    return Dataset(np.vstack(Xs), np.concatenate(ys), np.concatenate(ws),
                   np.concatenate(gs), rows)


__all__ = ["Dataset", "generate", "speed_variants", "PAIR_FEATURES"]
