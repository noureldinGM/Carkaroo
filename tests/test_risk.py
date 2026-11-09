"""Tests for the shortage-risk model: demand simulation, labels, leakage, split, model, notebook."""

import ast
import copy
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from agv_brain.demand import Order, ShiftPlan, StationTrace, random_plan, simulate_station
from agv_brain.risk_dataset import (LABEL, RISK_FEATURES, features_at, generate_risk, label_at,
                                    manual_features, split_by_timeline, training_layouts)
from agv_brain.risk_model import RiskModel
from agv_brain.simulator import load_context

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def ctx():
    return load_context()


@pytest.fixture(scope="module")
def small(ctx):
    return generate_risk(training_layouts(ctx, n_random=10), 12, seed=3)


def trace(seed=0):
    rng = np.random.default_rng(seed)
    return simulate_station(rng, random_plan(rng), station="S1", material="A", criticality=3, capacity=60,
                            safety_stock=6, base_rate_per_min=4.0, delivery_qty=20, trip_s=60)


def constant_trace(stock=10.0, rate_per_s=0.1):
    t = np.arange(0, 600, 2.0)
    n = len(t)
    return StationTrace("S1", "A", 2, 60, 5, rate_per_s, 20, ShiftPlan(600, 0, (1.0, 1.0, 1.0)), [], [], [],
                        t, np.full(n, rate_per_s), np.full(n, stock), np.full(n, np.floor(stock)))


def test_stock_never_negative_and_reading_is_whole_units():
    for seed in range(5):
        tr = trace(seed)
        assert (tr.stock >= 0).all()
        assert (tr.stock <= tr.capacity + 1e-9).all()
        assert np.array_equal(tr.reading, np.floor(tr.reading))
        assert (tr.reading <= tr.stock + 1e-9).all()
        assert tr.deliveries, "the replenishment loop should deliver within an hour"


def test_label_on_constant_usage():
    tr = constant_trace(stock=10.0, rate_per_s=0.1)   # runs out in 100 s
    y, empty_in = label_at(tr, 0, eta_s=50)
    assert y == 0 and empty_in == pytest.approx(100, abs=2)
    assert label_at(tr, 0, eta_s=120)[0] == 1


def test_features_do_not_see_the_future():
    tr = trace(1)
    k = tr.step(1800)
    before = features_at(tr, k, trip_s=60, queue_s=30)
    later = copy.deepcopy(tr)
    later.rate[k + 1:] *= 3                          # a surge after t
    later.stock[k + 1:] = 0
    later.reading[k + 1:] = 0
    later.deliveries.append((float(tr.t[k]) + 10, 20.0))
    later.orders.append(Order(announce_s=float(tr.t[k]) + 5, start_s=float(tr.t[k]) + 20,
                              end_s=float(tr.t[k]) + 200, boost=1.0))   # announced after t
    assert features_at(later, k, trip_s=60, queue_s=30) == before


def test_dataset_quality(small):
    assert set(RISK_FEATURES) <= set(small.columns)
    assert not small[RISK_FEATURES].isna().any().any()
    assert (small["stock"] > 0).all()
    assert 0.1 < small[LABEL].mean() < 0.6
    assert "empty_in_s" not in RISK_FEATURES and LABEL not in RISK_FEATURES


def test_split_keeps_timelines_together(small):
    tr, va, te = split_by_timeline(small, seed=0)
    assert (tr.astype(int) + va.astype(int) + te.astype(int) == 1).all()
    sets = [set(small[m].timeline) for m in (tr, va, te)]
    assert not (sets[0] & sets[1]) and not (sets[0] & sets[2]) and not (sets[1] & sets[2])


def test_model_round_trip(small, tmp_path):
    tr, va, te = split_by_timeline(small, seed=0)
    y = small[LABEL].to_numpy()
    model = RiskModel.train(small[tr], y[tr], small[va], y[va])
    p = model.predict_proba(small[te])
    assert ((p >= 0) & (p <= 1)).all()
    loaded = RiskModel.load(model.save(tmp_path / "risk.joblib"))
    assert np.allclose(loaded.predict_proba(small[te]), p)
    assert loaded.threshold == model.threshold


def test_manual_features_match_the_model_inputs():
    f = manual_features(stock=10, rate_per_min=2, trip_s=60)
    assert list(f) == RISK_FEATURES
    assert f["tte_naive_s"] == pytest.approx(300)
    assert f["planned_use_eta"] == pytest.approx(2.0)


def test_notebook_code_compiles():
    nb = json.loads((ROOT / "notebooks" / "carkaroo_ai_colab.ipynb").read_text(encoding="utf-8"))
    code = [c for c in nb["cells"] if c["cell_type"] == "code"]
    assert len(code) > 15
    for c in code:
        ast.parse("".join(c["source"]))


def test_colab_bundle_has_no_secrets():
    spec = importlib.util.spec_from_file_location("bundle", ROOT / "scripts" / "make_colab_bundle.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    names = [p.relative_to(ROOT).as_posix() for p in mod.files()]
    assert "agv_brain/risk_model.py" in names and "config/materials.yaml" in names
    assert not any(n.endswith((".local.yaml", ".env", ".key", ".pem")) or "mqtt" in n for n in names)
