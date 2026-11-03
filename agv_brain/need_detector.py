"""Automatic requests: the system decides by itself that a station needs material.

Every station bin is weighed by a load cell, so the system always knows the stock
and (through the forecaster) how fast it is used. A delivery is requested when

    time until the stock reaches the safety level  <=  delivery lead time + horizon

where the lead time is how long the car needs to bring the box (its trip, plus
the trips already waiting in the queue). This way the car is sent *before* the
station gets low, not after. A station is only served if a full box fits.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agv_brain.models import FactoryState, Job, Request
from agv_brain.simulator import Context, job_leg


@dataclass
class Need:
    request: Request
    reason: str


@dataclass
class NeedReport:
    needs: list[Need] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)

    @property
    def requests(self) -> list[Request]:
        return [n.request for n in self.needs]


def fmt_s(seconds: float) -> str:
    if seconds == float("inf"):
        return "never"
    if abs(seconds) < 90:
        return f"{seconds:.0f} s"
    return f"{seconds / 60:.1f} min"


def detect_needs(ctx: Context, state: FactoryState,
                 open_requests: list[Request] | None = None) -> NeedReport:
    s = ctx.settings
    open_requests = open_requests or []
    already = {(r.station, r.material) for r in open_requests}
    report = NeedReport()

    queue_s = 0.0
    for r in open_requests:
        try:
            queue_s += job_leg(ctx, state.car, _probe(ctx, r.station, r.material)).duration_s
        except ValueError:
            pass

    for sid, station in state.stations.items():
        for mid, sm in station.materials.items():
            if (sid, mid) in already or sm.rate_per_min <= 0:
                continue
            material = s.materials[mid]
            job = Job(id=f"{mid}@{sid}", material=mid, station=sid, rack=material.rack,
                      stock=sm.stock, rate_per_s=sm.rate_per_min / 60.0,
                      safety_stock=sm.safety_stock, criticality=station.criticality, wait_s=0.0)
            try:
                trip = job_leg(ctx, state.car, job).duration_s
            except ValueError:
                report.alerts.append(f"{sid} cannot be reached right now (blocked line).")
                continue
            lead = queue_s + trip
            if job.below_safety_s > lead + s.automation.horizon_s:
                continue
            if sm.capacity - sm.stock < material.delivery_qty:
                continue
            reason = (f"{sid} ({station.name}) has {sm.stock:.0f} {mid} left, uses "
                      f"{sm.rate_per_min:.1f}/min: safety level in {fmt_s(job.below_safety_s)}, "
                      f"empty in {fmt_s(job.stockout_s)}; a delivery takes ~{fmt_s(lead)}.")
            req = Request(id=f"auto-{mid}@{sid}-{state.now_s:.0f}", material=mid, station=sid,
                          created_s=state.now_s)
            report.needs.append(Need(req, reason))

    for mid, units in state.warehouse.items():
        box = s.materials[mid].delivery_qty
        if units < s.automation.warehouse_low_boxes * box:
            report.alerts.append(f"Warehouse stock of {mid} ({s.materials[mid].name}) is low: "
                                 f"{units} units = {units // box} boxes. Reorder from the supplier.")
    return report


def _probe(ctx: Context, station: str, material: str) -> Job:
    return Job(id="probe", material=material, station=station,
               rack=ctx.settings.materials[material].rack, stock=0, rate_per_s=0,
               safety_stock=0, criticality=1, wait_s=0)
