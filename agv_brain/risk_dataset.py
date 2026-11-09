"""Dataset for the shortage-risk model: "will this station run out before the car can get there?"

One row = one (station, material) at one moment t of a simulated factory timeline
(demand.py). Every input is something the real system knows at time t:

  - from the load cell, readings up to t only: stock, usage over the last 1, 5
    and 15 minutes, the forecaster's rate, the trend, the last delivery;
  - from the production plan, known in advance: the shift and the next shift,
    production orders that are running or announced, planned downtime;
  - from the track: the car's trip to bring a box now, plus the trips queued ahead.

The label looks into the FUTURE of the same timeline, which the inputs never see:

    shortage_before_delivery = 1  if the station's real usage between t and
                                  t + ETA is at least the stock it has at t
                                  (it runs out before a box sent now arrives)

The future usage includes surges nobody announced, orders announced later and
the moment-to-moment noise, so the label is not a formula of the inputs. The
plain formula "stock / rate < ETA" is kept as the baseline the model must beat.

Split by timeline (split_by_timeline), never by row: rows from the same
timeline are almost copies of each other a minute apart.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from agv_brain.demand import SHIFT_NAMES, StationTrace, random_plan, simulate_station
from agv_brain.forecaster import estimate_rate
from agv_brain.models import CarState, Job
from agv_brain.simulator import Context, job_leg, random_car

CAP_S = 3600.0
LABEL = "shortage_before_delivery"

RISK_FEATURES = [
    "stock",                # load-cell reading (units)
    "capacity",
    "safety_stock",
    "fill_frac",            # stock / capacity
    "nominal_rate_per_min", # the station's configured usage rate
    "rate_est_per_min",     # forecaster (last 2 minutes of readings)
    "rate_1m", "rate_5m", "rate_15m",   # usage measured over the last 1 / 5 / 15 min
    "rate_trend",           # rate_1m - rate_15m (> 0: speeding up)
    "tte_naive_s",          # stock / rate_est: time to empty if nothing changes
    "trip_s",               # car: rack -> station trip if sent now
    "queue_s",              # trips already waiting before this one
    "eta_s",                # trip_s + queue_s
    "margin_naive_s",       # tte_naive - eta (< 0: the plain formula says shortage)
    "since_delivery_s",
    "last_delivery_qty",
    "criticality",
    "shift_mult",           # planned usage multiplier of the current shift
    "next_shift_mult",
    "to_shift_change_s",
    "orders_active",        # production orders running now
    "orders_boost",         # their extra usage (sum of boosts)
    "orders_coming_boost",  # announced orders that start before the box arrives
    "downtime_now",         # 1 = planned maintenance right now
    "downtime_in_eta_s",    # planned downtime between now and the arrival
    "planned_use_eta",      # nominal rate x the plan (shifts, known orders, downtime) until arrival
    "planned_margin",       # stock - planned_use_eta
]


def _cap(x: float) -> float:
    return float(np.clip(x, -CAP_S, CAP_S))


def usage_rate(t: np.ndarray, reading: np.ndarray, k: int, window_s: float) -> float:
    """Units/min used over the last window_s seconds, from readings 0..k only.
    Only drops count: a jump up is a delivery, not negative usage."""
    dt = float(t[1] - t[0])
    lo = max(0, k - int(window_s / dt))
    if k <= lo:
        return 0.0
    drops = np.clip(-np.diff(reading[lo:k + 1]), 0, None).sum()
    return float(drops) / (t[k] - t[lo]) * 60.0


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def planned_factor(tr: StationTrace, t_s: float, u: np.ndarray) -> np.ndarray:
    """What the PLAN (known at t_s) says the rate multiplier will be at times u."""
    f = tr.plan.multiplier(u).astype(float)
    boost = np.zeros_like(f)
    for o in tr.orders:
        if o.announce_s <= t_s:
            boost[(u >= o.start_s) & (u < o.end_s)] += o.boost
    f *= 1 + boost
    for w in tr.downtime:
        f[(u >= w.start_s) & (u < w.end_s)] = 0.0
    return f


def features_at(tr: StationTrace, k: int, trip_s: float, queue_s: float) -> dict:
    """Inputs at step k. Reads readings[0..k] and the plan as known at t; nothing later."""
    t, r = tr.t, tr.reading
    t_s = float(t[k])
    stock = float(r[k])
    hist = [(float(t[i]), float(r[i])) for i in range(max(0, k - int(120 / tr.dt)), k + 1)]
    nominal = tr.base_rate_per_s * 60.0
    rate_est = estimate_rate(hist, fallback=nominal)
    r1, r5, r15 = (usage_rate(t, r, k, w) for w in (60, 300, 900))
    eta = trip_s + queue_s
    tte = stock / (rate_est / 60.0) if rate_est > 0 else CAP_S

    past = [(d, q) for d, q in tr.deliveries if d <= t_s]
    since = t_s - past[-1][0] if past else CAP_S
    last_qty = past[-1][1] if past else 0.0

    idx = int(tr.plan.index(t_s))
    active = [o for o in tr.orders if o.start_s <= t_s < o.end_s]
    coming = [o for o in tr.orders if o.announce_s <= t_s < o.start_s < t_s + eta]
    down_now = any(w.start_s <= t_s < w.end_s for w in tr.downtime)
    down_eta = sum(_overlap(t_s, t_s + eta, w.start_s, w.end_s) for w in tr.downtime)
    u = t_s + np.arange(0, eta, tr.dt)
    planned_use = tr.base_rate_per_s * float(planned_factor(tr, t_s, u).sum()) * tr.dt if len(u) else 0.0

    return {
        "stock": stock,
        "capacity": tr.capacity,
        "safety_stock": tr.safety_stock,
        "fill_frac": stock / tr.capacity,
        "nominal_rate_per_min": nominal,
        "rate_est_per_min": rate_est,
        "rate_1m": r1, "rate_5m": r5, "rate_15m": r15,
        "rate_trend": r1 - r15,
        "tte_naive_s": _cap(tte),
        "trip_s": trip_s,
        "queue_s": queue_s,
        "eta_s": eta,
        "margin_naive_s": _cap(tte - eta),
        "since_delivery_s": _cap(since),
        "last_delivery_qty": last_qty,
        "criticality": float(tr.criticality),
        "shift_mult": tr.plan.mult[idx],
        "next_shift_mult": tr.plan.mult[(idx + 1) % 3],
        "to_shift_change_s": tr.plan.to_change_s(t_s),
        "orders_active": float(len(active)),
        "orders_boost": float(sum(o.boost for o in active)),
        "orders_coming_boost": float(sum(o.boost for o in coming)),
        "downtime_now": float(down_now),
        "downtime_in_eta_s": down_eta,
        "planned_use_eta": planned_use,
        "planned_margin": stock - planned_use,
    }


def manual_features(*, stock: float, rate_per_min: float, trip_s: float, capacity: float = 60.0,
                    safety_stock: float = 5.0, nominal_rate_per_min: float | None = None,
                    rate_1m: float | None = None, rate_5m: float | None = None,
                    rate_15m: float | None = None, queue_s: float = 0.0,
                    since_delivery_s: float = 600.0, last_delivery_qty: float = 10.0,
                    criticality: int = 2, shift_mult: float = 1.0, next_shift_mult: float | None = None,
                    to_shift_change_s: float = CAP_S, orders_active: int = 0, orders_boost: float = 0.0,
                    orders_coming_boost: float = 0.0, downtime_now: bool = False,
                    downtime_in_eta_s: float = 0.0) -> dict:
    """Model inputs from values typed in by hand (notebook demo, website), not from a timeline.

    Rates not given are taken as `rate_per_min` (steady usage). The planned usage
    until the box arrives is estimated from the shift change and the orders:
    nominal rate x shift multiplier x (1 + orders) over the time the line runs."""
    nominal = rate_per_min if nominal_rate_per_min is None else nominal_rate_per_min
    r1 = rate_per_min if rate_1m is None else rate_1m
    r5 = rate_per_min if rate_5m is None else rate_5m
    r15 = rate_per_min if rate_15m is None else rate_15m
    nxt = shift_mult if next_shift_mult is None else next_shift_mult
    eta = trip_s + queue_s
    tte = stock / (rate_per_min / 60.0) if rate_per_min > 0 else CAP_S
    now_part = min(eta, to_shift_change_s)
    running = max(0.0, 1 - downtime_in_eta_s / eta) if eta > 0 else 1.0
    planned = (nominal / 60.0 * (now_part * shift_mult + (eta - now_part) * nxt)
               * (1 + orders_boost + orders_coming_boost / 2) * running)
    return {
        "stock": float(stock), "capacity": float(capacity), "safety_stock": float(safety_stock),
        "fill_frac": stock / capacity, "nominal_rate_per_min": float(nominal),
        "rate_est_per_min": float(rate_per_min), "rate_1m": float(r1), "rate_5m": float(r5),
        "rate_15m": float(r15), "rate_trend": float(r1 - r15), "tte_naive_s": _cap(tte),
        "trip_s": float(trip_s), "queue_s": float(queue_s), "eta_s": float(eta),
        "margin_naive_s": _cap(tte - eta), "since_delivery_s": _cap(since_delivery_s),
        "last_delivery_qty": float(last_delivery_qty), "criticality": float(criticality),
        "shift_mult": float(shift_mult), "next_shift_mult": float(nxt),
        "to_shift_change_s": float(to_shift_change_s), "orders_active": float(orders_active),
        "orders_boost": float(orders_boost), "orders_coming_boost": float(orders_coming_boost),
        "downtime_now": float(downtime_now), "downtime_in_eta_s": float(downtime_in_eta_s),
        "planned_use_eta": planned, "planned_margin": stock - planned,
    }


def label_at(tr: StationTrace, k: int, eta_s: float) -> tuple[int, float]:
    """(label, seconds until the station would run out with no delivery), from the future.

    Uses the TRUE stock and the TRUE future usage of this timeline, which the
    inputs never see."""
    stock = float(tr.stock[k])
    used = np.cumsum(tr.rate[k:] * tr.dt)
    hit = int(np.searchsorted(used, stock))      # first step where usage >= stock
    empty_in = (hit + 1) * tr.dt if hit < len(used) else math.inf
    return int(empty_in <= eta_s), min(empty_in, CAP_S)


def _queue(rng: np.random.Generator, trip_s: float) -> float:
    ahead = int(rng.choice(4, p=[0.4, 0.3, 0.2, 0.1]))
    return float(sum(trip_s * rng.uniform(0.5, 1.5) for _ in range(ahead)))


def timeline_rows(rng: np.random.Generator, ctx: Context, timeline: int, layout: str,
                  duration_s: float = 3600.0, warmup_s: float = 900.0,
                  obs_every_s: float = 45.0, max_eta_s: float = 900.0) -> list[dict]:
    """Simulate one factory timeline (all its station-materials) and return its rows."""
    s = ctx.settings
    plan = random_plan(rng)
    dock = CarState(s.car.dock, s.car.start_heading)
    rows = []
    for st_id, st in s.stations.items():
        for m, sm in st.materials.items():
            mat = s.materials[m]
            probe = Job(f"{m}@{st_id}", m, st_id, mat.rack, sm.stock, sm.rate_per_min / 60,
                        sm.safety_stock, st.criticality, 0.0)
            tr = simulate_station(rng, plan, station=st_id, material=m, criticality=st.criticality,
                                  capacity=sm.capacity, safety_stock=sm.safety_stock,
                                  base_rate_per_min=sm.rate_per_min * rng.uniform(0.7, 1.3),
                                  delivery_qty=mat.delivery_qty,
                                  trip_s=job_leg(ctx, dock, probe).duration_s,
                                  duration_s=duration_s)
            obs = warmup_s + rng.uniform(0, obs_every_s)
            while obs < duration_s - max_eta_s:
                k = tr.step(obs)
                obs += obs_every_s * rng.uniform(0.6, 1.4)
                if tr.reading[k] <= 0:
                    continue        # already stopped: nothing left to predict
                car = random_car(rng, ctx.fmap)
                trip = job_leg(ctx, car, probe).duration_s
                queue = min(_queue(rng, trip), max_eta_s - trip) if trip < max_eta_s else 0.0
                f = features_at(tr, k, trip, max(queue, 0.0))
                y, empty_in = label_at(tr, k, f["eta_s"])
                rows.append({"timeline": timeline, "layout": layout, "station": st_id,
                             "material": m, "t_s": float(tr.t[k]),
                             "shift": _shift_name(tr, float(tr.t[k])),
                             **f, "empty_in_s": empty_in, LABEL: y})
    return rows


def _shift_name(tr: StationTrace, t_s: float) -> str:
    """Name the shifts of this timeline by their planned multiplier: the busiest is
    'day', the quietest 'night'."""
    rank = np.argsort(np.argsort(-np.asarray(tr.plan.mult)))
    return SHIFT_NAMES[int(rank[int(tr.plan.index(t_s))])]


def training_layouts(ctx: Context, n_random: int = 200, seed: int = 1011) -> list[tuple[str, Context]]:
    """Our track plus `n_random` random factories (layouts.py) to draw timelines from."""
    from agv_brain.layouts import layout_pool
    return [("ours", ctx)] + [(f"random-{i}", c) for i, c in enumerate(layout_pool(n_random, seed, ctx.settings))]


def unseen_layouts(ctx: Context, n_random: int = 60, seed: int = 5055) -> list[tuple[str, Context]]:
    """Random factories built from another seed: never used for training."""
    from agv_brain.layouts import layout_pool
    return [(f"unseen-{i}", c) for i, c in enumerate(layout_pool(n_random, seed, ctx.settings))]


def generate_risk(layouts: list[tuple[str, Context]], n_timelines: int, seed: int = 11,
                  **kwargs) -> pd.DataFrame:
    """`layouts`: (name, context) pairs to draw factories from, uniformly."""
    rng = np.random.default_rng(seed)
    rows = []
    for tl in range(n_timelines):
        name, ctx = layouts[int(rng.integers(len(layouts)))]
        rows += timeline_rows(rng, ctx, tl, name, **kwargs)
    return pd.DataFrame(rows)


def split_by_timeline(df: pd.DataFrame, seed: int = 0,
                      fractions: tuple[float, float] = (0.70, 0.15)) -> tuple[np.ndarray, ...]:
    """Boolean masks (train, validation, test). A timeline is in exactly one of them."""
    rng = np.random.default_rng(seed)
    ids = rng.permutation(df["timeline"].unique())
    n_tr = int(len(ids) * fractions[0])
    n_va = int(len(ids) * fractions[1])
    tr, va = set(ids[:n_tr]), set(ids[n_tr:n_tr + n_va])
    tl = df["timeline"]
    train, val = tl.isin(tr).to_numpy(), tl.isin(va).to_numpy()
    return train, val, ~(train | val)


def naive_rule(df: pd.DataFrame) -> np.ndarray:
    """Baseline: 'it runs out if stock / rate is shorter than the trip'."""
    return (df["margin_naive_s"].to_numpy() < 0).astype(int)


def plan_rule(df: pd.DataFrame) -> np.ndarray:
    """Stronger baseline: 'it runs out if the planned usage until arrival is at least the stock'."""
    return (df["planned_margin"].to_numpy() <= 0).astype(int)


__all__ = ["RISK_FEATURES", "LABEL", "features_at", "manual_features", "label_at", "timeline_rows", "generate_risk",
           "split_by_timeline", "training_layouts", "unseen_layouts", "naive_rule", "plan_rule", "usage_rate"]
