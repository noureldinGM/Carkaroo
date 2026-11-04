import numpy as np
import pytest

from agv_brain.models import CarState, load_settings
from agv_brain.optimizer import first_choice_costs
from agv_brain.real_layouts import KIT_DIR, industry_layouts, load_layout, real_context, real_scenario
from agv_brain.simulator import job_leg, load_context, random_scenario

pytestmark = pytest.mark.skipif(not KIT_DIR.exists(), reason="KIT data set not downloaded")


def test_industry01_reads_as_in_the_file():
    lay = load_layout(KIT_DIR / "Industry01")
    assert lay.stations == ("A", "B", "C", "D", "E", "F", "G")
    assert lay.distance_m["A", "B"] == 68 and lay.distance_m["B", "A"] == 47  # one-way lines
    assert ("A", "C", 5.0) in lay.routes and len(lay.routes) == 5


def test_only_layouts_with_a_choice_are_used():
    layouts = industry_layouts()
    assert len(layouts) == 14
    assert all(len(lay.routes) >= 2 for lay in layouts)


def test_trip_time_is_real_distance_over_speed():
    lay = load_layout(KIT_DIR / "Industry01")
    ctx = real_context(lay, load_settings(), speed_cm_s=100.0)  # 1 m/s: meters = seconds
    _, jobs = real_scenario(np.random.default_rng(0), ctx, (2, 2))
    job = jobs[0]
    leg = job_leg(ctx, CarState("G", "N"), job)
    car = ctx.settings.car
    expected = (lay.distance_m.get(("G", job.rack), 0.0) + lay.distance_m[job.rack, job.station]
                + car.pickup_s + car.drop_s)
    assert leg.duration_s == pytest.approx(expected)


def test_requests_use_only_real_routes_and_can_be_labelled():
    base = load_settings()
    rng = np.random.default_rng(3)
    for lay in industry_layouts():
        ctx = real_context(lay, base)
        routes = {(f"M-{s}", d) for s, d, _ in lay.routes}
        car, jobs = real_scenario(rng, ctx, (2, 7))
        assert 2 <= len(jobs) <= min(7, len(routes))
        assert all((j.material, j.station) in routes for j in jobs)
        assert len({j.id for j in jobs}) == len(jobs)
        assert car.node in lay.stations
        assert len(first_choice_costs(ctx, jobs, car)) == len(jobs)


def test_large_plants_have_real_factory_scale_and_label():
    from agv_brain.dataset import generate_plants
    from agv_brain.layouts import plant_pool
    pool = plant_pool(30, seed=4, base=load_settings())
    for ctx in pool:
        lay = ctx.fmap.layout
        assert len(lay.routes) >= 2 and 4 <= len(lay.stations) <= 25
        assert all(2.0 <= lay.distance_m[s, d] <= 500 for s, d, _ in lay.routes)
        assert 50 <= ctx.settings.car.speed_cm_s <= 200
    ds = generate_plants(40, load_settings(), seed=5, n_plants=10)
    assert len(ds.y) == len(ds.X) > 0 and abs(ds.y.mean() - 0.5) < 0.01  # (i, j) and (j, i)


def test_training_situations_on_our_track_are_unchanged():
    # random_jobs gained options for real layouts; the default must give the same
    # situations as before, so existing datasets can still be regenerated exactly
    car, jobs = random_scenario(np.random.default_rng(7), load_context(), (2, 6))
    assert (car.node, car.heading) == ("J5", "S")
    assert [(j.id, round(j.stock, 2), j.criticality) for j in jobs] == [
        ("B@S4", 5.64, 3), ("A@S1", 45.08, 2), ("C@S4", 1.56, 1),
        ("A@S4", 14.1, 2), ("C@S1", 0.39, 3), ("C@S2", 1.36, 2)]
