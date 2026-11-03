import itertools
from dataclasses import replace

import numpy as np
import pytest

from agv_brain.baselines import BASELINES, rollout
from agv_brain.dataset import generate
from agv_brain.dispatcher import Dispatcher
from agv_brain.forecaster import ConsumptionForecaster, ewma_rate
from agv_brain.models import CarState, Job, Request, initial_state
from agv_brain.need_detector import detect_needs
from agv_brain.optimizer import best_order, first_choice_costs
from agv_brain.ranker import PairwiseRanker
from agv_brain.simulator import load_context, random_scenario, simulate


@pytest.fixture(scope="module")
def ctx():
    return load_context()


def job(ctx, material, station, stock, rate_per_min, crit=2, wait=0.0, safety=2.0):
    return Job(id=f"{material}@{station}", material=material, station=station,
               rack=ctx.settings.materials[material].rack, stock=stock,
               rate_per_s=rate_per_min / 60, safety_stock=safety, criticality=crit, wait_s=wait)


DOCK = CarState("HOME", "N", 90)


# -- forecaster -------------------------------------------------------------

def test_ewma_rate_follows_consumption():
    readings = [(t, 100 - 2 * t / 60) for t in range(0, 600, 30)]   # 2 units / min
    assert ewma_rate(readings) == pytest.approx(2.0, rel=1e-6)


def test_refill_is_not_negative_usage():
    f = ConsumptionForecaster(alpha=1.0)
    f.update("S1", "A", 0, 10)
    f.update("S1", "A", 60, 8)      # used 2 in a minute
    f.update("S1", "A", 70, 28)     # a box of 20 delivered
    f.update("S1", "A", 130, 26)    # used 2 in a minute
    assert f.rate_per_min("S1", "A", fallback=99) == pytest.approx(2.0)
    assert f.rate_per_min("S2", "B", fallback=1.5) == 1.5


# -- teacher optimizer --------------------------------------------------------

def test_urgent_station_goes_first(ctx):
    a = job(ctx, "A", "S1", stock=10, rate_per_min=3, crit=3)   # empty in 200 s
    b = job(ctx, "B", "S3", stock=2, rate_per_min=2, crit=2)    # empty in 60 s
    order, _ = best_order(ctx, [a, b], DOCK)
    assert [j.material for j in order] == ["B", "A"]
    assert simulate(ctx, order, DOCK).stop_s == 0
    assert simulate(ctx, [a, b], DOCK).stop_s > 30


def test_search_matches_brute_force(ctx):
    rng = np.random.default_rng(3)
    for _ in range(20):
        car, jobs = random_scenario(rng, ctx, (2, 5))
        brute = min(simulate(ctx, list(p), car).total_cost for p in itertools.permutations(jobs))
        _, cost = best_order(ctx, jobs, car)
        assert cost == pytest.approx(brute)
        assert min(first_choice_costs(ctx, jobs, car)) == pytest.approx(brute)


# -- automatic needs & safety -------------------------------------------------

def test_needs_detected_from_sensor_data(ctx):
    state = initial_state(ctx.settings)
    found = {(r.material, r.station) for r in detect_needs(ctx, state).requests}
    assert found == {("A", "S1"), ("B", "S3")}   # the two low stations in the config
    state.stations["S3"].materials["B"].stock = 35
    found = {(r.material, r.station) for r in detect_needs(ctx, state).requests}
    assert ("B", "S3") not in found


def test_open_request_is_not_duplicated(ctx):
    state = initial_state(ctx.settings)
    open_reqs = [Request("x", "B", "S3")]
    found = {(r.material, r.station) for r in detect_needs(ctx, state, open_reqs).requests}
    assert ("B", "S3") not in found


def test_empty_warehouse_and_low_battery(ctx):
    d = Dispatcher(ctx, policy="optimal")
    state = initial_state(ctx.settings, CarState("HOME", "N", battery_pct=10))
    state.warehouse["A"] = 0
    dec = d.decide(state, [Request("1", "A", "S1"), Request("2", "B", "S3")])
    assert [t.job.material for t in dec.tasks] == ["B"]
    assert dec.charge_first
    assert any("out of A" in a for a in dec.alerts)


# -- ML ranker ----------------------------------------------------------------

def test_small_ranker_beats_fifo(ctx):
    ds = generate(ctx, 600, seed=7, randomize_speed=False)
    ranker = PairwiseRanker().fit(ds.X, ds.y, ds.w)
    rng = np.random.default_rng(99)
    ml_cost = fifo_cost = 0.0
    for _ in range(80):
        car, jobs = random_scenario(rng, ctx, (2, 5))
        ml_cost += simulate(ctx, rollout(ranker, ctx, jobs, car), car).total_cost
        fifo_cost += simulate(ctx, rollout(BASELINES["fifo"], ctx, jobs, car), car).total_cost
    assert ml_cost < fifo_cost


def test_trained_model_on_demo_case():
    d = Dispatcher.from_config(policy="ml")
    if d.policy != "ml":
        pytest.skip("models/ranker.joblib not trained yet")
    state = initial_state(d.ctx.settings)
    dec = d.decide(state, d.detect(state).requests)
    assert dec.first.job.material == "B"
    assert dec.first.to_rack.commands[-1] == "STOP"
    assert dec.first.to_station.path[-1] == "S3"
    assert any("optimizer agrees" in r for r in dec.reasons)


def test_dispatcher_handles_unknown_material(ctx):
    d = Dispatcher(ctx, policy="weighted_rules")
    state = initial_state(ctx.settings)
    dec = d.decide(state, [Request("1", "C", "S1")])   # S1 does not use C
    assert not dec.tasks and dec.alerts


def test_speed_does_not_break_routes(ctx):
    slow = replace(ctx.settings.car, speed_cm_s=5)
    fmap = ctx.fmap.with_car(slow)
    assert fmap.route("HOME", "S4", "N").path == ctx.fmap.route("HOME", "S4", "N").path
