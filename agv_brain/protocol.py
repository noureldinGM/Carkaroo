"""Topic names and message builders (see docs/protocol.md)."""

from __future__ import annotations

from agv_brain.factory_map import Route
from agv_brain.features import job_matrix
from agv_brain.models import CarState, Decision, Job
from agv_brain.optimizer import MAX_EXACT, first_choice_costs
from agv_brain.simulator import Context

PREFIX = "factory"


def station_stock(station: str = "+") -> str:
    return f"{PREFIX}/station/{station}/stock"


def car_status(car: str = "+") -> str:
    return f"{PREFIX}/car/{car}/status"


def car_event(car: str = "+") -> str:
    return f"{PREFIX}/car/{car}/event"


def car_cmd(car: str = "+") -> str:
    return f"{PREFIX}/car/{car}/cmd"


AI_DECISION = f"{PREFIX}/ai/decision"   # latest decision with reasons (retained)
AI_STATE = f"{PREFIX}/ai/state"         # what the AI believes about the factory (retained)
AI_ALERTS = f"{PREFIX}/ai/alerts"
AI_REQUEST = f"{PREFIX}/ai/request"     # manual request, e.g. from the dashboard
SIM_CONTROL = f"{PREFIX}/sim/control"   # simulation only: obstacles, stock changes


def set_prefix(prefix: str) -> None:
    """Use another topic root. Tests use their own, so they never disturb a running factory."""
    global PREFIX, AI_DECISION, AI_STATE, AI_ALERTS, AI_REQUEST, SIM_CONTROL
    PREFIX = prefix
    AI_DECISION = f"{PREFIX}/ai/decision"
    AI_STATE = f"{PREFIX}/ai/state"
    AI_ALERTS = f"{PREFIX}/ai/alerts"
    AI_REQUEST = f"{PREFIX}/ai/request"
    SIM_CONTROL = f"{PREFIX}/sim/control"


def route_dict(route: Route) -> dict:
    return {"path": list(route.path), "commands": list(route.commands),
            "distance_cm": round(route.distance_cm, 1), "time_s": round(route.time_s, 1)}


def task_message(task_id: int, job: Job, to_rack: Route, to_station: Route) -> dict:
    return {"type": "task", "task_id": task_id, "material": job.material,
            "legs": [{"to": job.rack, "commands": list(to_rack.commands), "action": "LIFT"},
                     {"to": job.station, "commands": list(to_station.commands), "action": "LOWER"}]}


def charge_message(task_id: int, route: Route) -> dict:
    return {"type": "charge", "task_id": task_id, "to": route.path[-1],
            "commands": list(route.commands)}


def reroute_message(task_id: int, leg: int, route: Route) -> dict:
    return {"type": "reroute", "task_id": task_id, "leg": leg, "commands": list(route.commands)}


def decision_message(ctx: Context, decision: Decision, car: CarState, now_s: float,
                     jobs: list[Job], requests: dict) -> dict:
    """Everything the dashboard needs to show *why* the AI chose this order."""
    stations = ctx.settings.stations
    factors = {}
    if jobs:
        F, legs = job_matrix(ctx, jobs, car)
        costs = first_choice_costs(ctx, jobs, car) if len(jobs) <= MAX_EXACT else [None] * len(jobs)
        for j, f, leg, c in zip(jobs, F, legs, costs):
            factors[j.id] = {"stock": round(max(j.stock, 0), 1), "rate_per_min": round(f[1], 2),
                             "stockout_s": round(f[2], 1), "below_safety_s": round(f[3], 1),
                             "trip_s": round(leg.duration_s, 1), "slack_s": round(f[6], 1),
                             "criticality": j.criticality, "wait_s": round(j.wait_s, 1),
                             "cost_if_first": None if c is None else round(c, 2)}
    best = None
    known = {k: v["cost_if_first"] for k, v in factors.items() if v["cost_if_first"] is not None}
    if known:
        best = min(known, key=known.get)
    queue = []
    for rank, t in enumerate(decision.tasks, 1):
        r = requests.get(t.job.id)
        queue.append({
            "rank": rank, "request_id": t.job.id, "material": t.job.material,
            "station": t.job.station, "station_name": stations[t.job.station].name,
            "auto": bool(r and r.id.startswith("auto-")), "score": None if t.score is None else round(t.score, 3),
            "eta_s": round(t.finish_s, 1), "stop_s": round(t.stop_s, 1),
            "to_rack": route_dict(t.to_rack), "to_station": route_dict(t.to_station),
            **factors.get(t.job.id, {}),
        })
    first = decision.tasks[0].job.id if decision.tasks else None
    regret = (known[first] - known[best]) if best is not None and first in known else 0.0
    return {"ts": round(now_s, 1), "policy": decision.policy, "queue": queue,
            "reasons": decision.reasons, "alerts": decision.alerts,
            "charge_first": decision.charge_first,
            "optimizer_best": best, "optimizer_agrees": regret < 0.5,
            "regret": round(regret, 2),            # extra cost of this choice vs the best first choice
            "best_cost": round(known[best], 2) if best is not None else None}
