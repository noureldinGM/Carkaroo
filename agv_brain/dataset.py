"""Builds the training dataset: random factory situations labelled by the teacher.

The ranker only sees numbers (stock, usage rate, time to empty, trip time,
criticality, waiting time), never material or node names, so it works for any
number of materials and any track. To make it robust ("domain randomization"):
  - situations on our track use a random car speed, 0.6x to 1.5x the configured one,
    so the model keeps working after the real car is calibrated;
  - most situations come from random factory layouts (layouts.py), so a new track
    needs no retraining.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from agv_brain.features import JOB_FEATURES, PAIR_FEATURES, job_matrix
from agv_brain.layouts import layout_pool, plant_pool
from agv_brain.models import Settings
from agv_brain.optimizer import first_choice_costs
from agv_brain.ranker import TIE_EPS, pair_examples
from agv_brain.real_layouts import real_scenario
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


def _label(vctx, car, jobs, sid, layout, Xs, ys, ws, gs, rows) -> None:
    """Label one situation with the teacher and append its pair rows and readable rows."""
    costs = first_choice_costs(vctx, jobs, car)
    X, y, w = pair_examples(vctx, jobs, car, costs)
    Xs.append(X), ys.append(y), ws.append(w), gs.append(np.full(len(y), sid))

    F, _ = job_matrix(vctx, jobs, car)
    best = min(costs)
    for job, f, c in zip(jobs, F, costs):
        row = {"scenario": sid, "layout": layout, "request": job.id, "car_node": car.node,
               "car_heading": car.heading, "car_speed_cm_s": vctx.settings.car.speed_cm_s,
               "material": job.material, "station": job.station}
        row.update({name: round(float(v), 3) for name, v in zip(JOB_FEATURES, f)})
        row["teacher_cost_if_first"] = round(c, 3)
        row["teacher_best_first"] = int(c <= best + TIE_EPS)
        rows.append(row)


def generate_plants(n_scenarios: int, base: Settings, seed: int = 2, n_plants: int = 300,
                    n_range: tuple[int, int] = (2, 6)) -> Dataset:
    """Situations in random large factories (layouts.random_plant), at real-factory scale."""
    rng = np.random.default_rng(seed)
    pool = plant_pool(n_plants, seed + 1000, base)
    Xs, ys, ws, gs, rows = [], [], [], [], []
    for sid in range(n_scenarios):
        k = int(rng.integers(len(pool)))
        car, jobs = real_scenario(rng, pool[k], n_range)
        _label(pool[k], car, jobs, sid, f"plant-{k}", Xs, ys, ws, gs, rows)
    return Dataset(np.vstack(Xs), np.concatenate(ys), np.concatenate(ws),
                   np.concatenate(gs), rows)


def generate(ctx: Context, n_scenarios: int, seed: int = 1,
             n_range: tuple[int, int] = (2, 6), randomize_speed: bool = True,
             random_layouts: int = 0, layout_share: float = 0.6) -> Dataset:
    """`random_layouts` > 0 adds that many random factories; `layout_share` of the
    situations then come from them and the rest from our track."""
    rng = np.random.default_rng(seed)
    variants = speed_variants(ctx) if randomize_speed else [ctx]
    pool = layout_pool(random_layouts, seed + 1000, ctx.settings) if random_layouts else []
    Xs, ys, ws, gs, rows = [], [], [], [], []
    for sid in range(n_scenarios):
        if pool and rng.random() < layout_share:
            k = int(rng.integers(len(pool)))
            vctx, layout = pool[k], f"random-{k}"
        else:
            vctx, layout = variants[int(rng.integers(len(variants)))], "ours"
        car, jobs = random_scenario(rng, vctx, n_range)
        _label(vctx, car, jobs, sid, layout, Xs, ys, ws, gs, rows)
    return Dataset(np.vstack(Xs), np.concatenate(ys), np.concatenate(ws),
                   np.concatenate(gs), rows)


__all__ = ["Dataset", "generate", "generate_plants", "speed_variants", "PAIR_FEATURES"]
