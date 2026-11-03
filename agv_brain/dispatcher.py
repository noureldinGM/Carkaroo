"""Main entry point of the AI brain.

    sensors -> FactoryState -> detect_needs -> requests
    requests -> jobs -> safety rules -> ranker (ML) -> ordered plan + routes + reasons

Example:
    from agv_brain.dispatcher import Dispatcher
    from agv_brain.models import initial_state

    d = Dispatcher.from_config()
    state = initial_state(d.ctx.settings)
    decision = d.decide(state, d.detect(state).requests)
"""

from __future__ import annotations

from pathlib import Path

from agv_brain.baselines import BASELINES, rollout
from agv_brain.explain import explain
from agv_brain.factory_map import FactoryMap
from agv_brain.models import Decision, FactoryState, Job, PlannedTask, Request, load_settings
from agv_brain.need_detector import NeedReport, detect_needs
from agv_brain.optimizer import MAX_EXACT, best_order
from agv_brain.ranker import DEFAULT_MODEL_PATH, PairwiseRanker
from agv_brain.safety import filter_jobs, needs_charge
from agv_brain.simulator import Context, fit_start_heading, simulate

POLICIES = ["ml", "optimal", *BASELINES]


class Dispatcher:
    def __init__(self, ctx: Context, policy: str = "ml", ranker: PairwiseRanker | None = None):
        if policy not in POLICIES:
            raise ValueError(f"policy must be one of {POLICIES}")
        self.ctx = ctx
        self.policy = policy
        self.ranker = ranker
        self.notes: list[str] = []
        if policy == "ml" and ranker is None:
            try:
                self.ranker = PairwiseRanker.load(DEFAULT_MODEL_PATH)
            except FileNotFoundError:
                self.policy = "weighted_rules"
                self.notes.append("No trained model found (run scripts/train_ranker.py); "
                                  "using the weighted rules instead.")

    @classmethod
    def from_config(cls, policy: str = "ml", model_path: str | Path | None = None,
                    layout: str | Path | None = None, materials: str | Path | None = None) -> "Dispatcher":
        settings = load_settings(materials)
        fmap = FactoryMap.from_yaml(layout, settings.car)
        fit_start_heading(settings, fmap)
        ctx = Context(fmap, settings)
        ranker = PairwiseRanker.load(model_path) if model_path else None
        return cls(ctx, policy, ranker)

    # -- steps ----------------------------------------------------------------

    def detect(self, state: FactoryState, open_requests: list[Request] | None = None) -> NeedReport:
        return detect_needs(self.ctx, state, open_requests)

    def jobs_from_requests(self, state: FactoryState, requests: list[Request]) -> tuple[list[Job], list[str]]:
        jobs, alerts = [], []
        for r in requests:
            station = state.stations.get(r.station)
            material = self.ctx.settings.materials.get(r.material)
            if station is None or material is None or r.material not in station.materials:
                alerts.append(f"Request {r.id}: station {r.station} does not use material {r.material}.")
                continue
            sm = station.materials[r.material]
            jobs.append(Job(id=r.id, material=r.material, station=r.station, rack=material.rack,
                            stock=sm.stock, rate_per_s=sm.rate_per_min / 60.0,
                            safety_stock=sm.safety_stock, criticality=station.criticality,
                            wait_s=max(0.0, state.now_s - r.created_s)))
        return jobs, alerts

    def order(self, jobs: list[Job], state: FactoryState) -> list[Job]:
        car = state.car
        if self.policy == "optimal" and len(jobs) <= MAX_EXACT:
            return best_order(self.ctx, jobs, car)[0]
        score_fn = self.ranker if self.policy == "ml" else BASELINES.get(self.policy, BASELINES["weighted_rules"])
        return rollout(score_fn, self.ctx, jobs, car)

    def decide(self, state: FactoryState, requests: list[Request]) -> Decision:
        decision = Decision(policy=self.policy, alerts=list(self.notes))
        jobs, alerts = self.jobs_from_requests(state, requests)
        decision.alerts += alerts
        safe = filter_jobs(self.ctx, state, jobs)
        decision.alerts += safe.alerts
        jobs = safe.jobs
        if not jobs:
            decision.reasons = ["Nothing to deliver right now."]
            return decision

        ordered = self.order(jobs, state)
        plan = simulate(self.ctx, ordered, state.car)
        scores = {}
        if self.policy == "ml":
            scores = dict(zip((j.id for j in jobs), self.ranker.score(self.ctx, jobs, state.car)))
        for t in plan.tasks:
            decision.tasks.append(PlannedTask(
                job=t.job, to_rack=t.leg.to_rack, to_station=t.leg.to_station,
                start_s=t.start_s, finish_s=t.finish_s, stop_s=t.stop_s,
                score=scores.get(t.job.id)))

        first = plan.tasks[0]
        trip_cm = first.leg.to_rack.distance_cm + first.leg.to_station.distance_cm
        charge, why = needs_charge(self.ctx, state.car, trip_cm, first.job.station)
        if charge:
            decision.charge_first = True
            decision.charge_route = self.ctx.fmap.route(state.car.node, self.ctx.settings.car.dock,
                                                        state.car.heading)
            decision.alerts.append(why)
        decision.reasons = explain(self.ctx, jobs, state.car, plan)
        return decision
