"""Hard rules that are checked before the ML ranker is asked anything.

The ML only orders deliveries that are actually possible and safe:
  - the warehouse must have at least one full box of the material,
  - the station must have room for a full box,
  - the station must be reachable (lines blocked by obstacles are avoided),
  - the car must have enough battery, otherwise it charges first.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agv_brain.models import CarState, FactoryState, Job
from agv_brain.simulator import Context, job_leg


@dataclass
class SafetyResult:
    jobs: list[Job]
    alerts: list[str] = field(default_factory=list)
    charge_first: bool = False


def filter_jobs(ctx: Context, state: FactoryState, jobs: list[Job]) -> SafetyResult:
    s = ctx.settings
    ok, alerts = [], []
    for job in jobs:
        material = s.materials[job.material]
        station = state.stations[job.station].materials[job.material]
        left = state.warehouse.get(job.material, 0)
        if left < material.delivery_qty:
            alerts.append(f"Warehouse is out of {job.material} ({material.name}): {left} left, "
                          f"less than one box of {material.delivery_qty}. Cannot serve {job.station}; "
                          "reorder from the supplier.")
            continue
        if station.capacity - job.stock < material.delivery_qty:
            alerts.append(f"{job.station} has no room for a full box of {job.material} "
                          f"({job.stock:.0f}/{station.capacity:.0f}); skipped for now.")
            continue
        try:
            job_leg(ctx, state.car, job)
        except ValueError:
            alerts.append(f"{job.station} or rack {job.rack} cannot be reached: a line is "
                          "blocked. Clear the obstacle.")
            continue
        ok.append(job)
    return SafetyResult(ok, alerts, charge_first=False)


def needs_charge(ctx: Context, car: CarState, first_trip_cm: float, end_node: str) -> tuple[bool, str]:
    """Charge first if the battery is low, or the next delivery plus the way back
    to the dock would take it below 5 %."""
    p = ctx.settings.car
    if car.battery_pct < p.min_battery_pct:
        return True, f"Battery {car.battery_pct:.0f}% is below {p.min_battery_pct:.0f}%: charging first."
    try:
        back = ctx.fmap.route(end_node, p.dock, ctx.fmap.arrival_heading(end_node)
                              if len(ctx.fmap.neighbors(end_node)) == 1 else car.heading)
    except ValueError:
        return False, ""
    use = (first_trip_cm + back.distance_cm) / 100.0 * p.battery_pct_per_m
    if car.battery_pct - use < 5.0:
        return True, (f"Battery {car.battery_pct:.0f}% is not enough for the next delivery and "
                      f"the way back to the dock (needs ~{use:.0f}%): charging first.")
    return False, ""
