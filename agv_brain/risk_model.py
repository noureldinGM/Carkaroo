"""The shortage-risk model: for each station, the chance it runs out before a box sent now arrives.

    risk = P(shortage_before_delivery = 1 | what the factory knows now)

It is a gradient-boosted tree classifier (HistGradientBoosting) trained on the
simulated timelines of risk_dataset.py, then CALIBRATED on separate validation
timelines (isotonic regression), so "risk 0.80" means: of all the moments the
model said 0.80, about 80 % really ran out. A risk is a probability of one
future event, not a priority score.

How it fits with the rest of the AI:
  - the risk model says how much danger each station is in (and why);
  - the ranker (ranker.py), checked by the exact optimizer, still decides which
    delivery goes first, because "highest risk first" can be the wrong order
    (a slightly less risky station on the way may be served first at no cost).
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.frozen import FrozenEstimator

from agv_brain.models import ROOT
from agv_brain.risk_dataset import RISK_FEATURES

DEFAULT_RISK_PATH = ROOT / "models" / "risk_model.joblib"

FEATURE_LABELS = {
    "stock": "Stock left",
    "capacity": "Bin capacity",
    "safety_stock": "Safety stock",
    "fill_frac": "How full the bin is",
    "nominal_rate_per_min": "Planned usage rate",
    "rate_est_per_min": "Measured usage rate (2 min)",
    "rate_1m": "Usage in the last minute",
    "rate_5m": "Usage in the last 5 minutes",
    "rate_15m": "Usage in the last 15 minutes",
    "rate_trend": "Usage speeding up / slowing down",
    "tte_naive_s": "Time to empty at today's rate",
    "trip_s": "Car trip time",
    "queue_s": "Trips waiting ahead",
    "eta_s": "Time until a box arrives",
    "margin_naive_s": "Time to empty minus arrival time",
    "since_delivery_s": "Time since the last delivery",
    "last_delivery_qty": "Size of the last delivery",
    "criticality": "Station criticality",
    "shift_mult": "Current shift's workload",
    "next_shift_mult": "Next shift's workload",
    "to_shift_change_s": "Time to the shift change",
    "orders_active": "Production orders running",
    "orders_boost": "Extra usage from running orders",
    "orders_coming_boost": "Announced orders starting soon",
    "downtime_now": "Planned downtime now",
    "downtime_in_eta_s": "Planned downtime before arrival",
    "planned_use_eta": "Planned usage until arrival",
    "planned_margin": "Stock minus planned usage",
}


def make_hgb(seed: int = 0) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(max_iter=400, learning_rate=0.06, max_leaf_nodes=31,
                                          min_samples_leaf=40, l2_regularization=1.0,
                                          early_stopping=True, validation_fraction=0.1,
                                          random_state=seed)


def threshold_for_recall(y: np.ndarray, p: np.ndarray, recall: float = 0.95) -> float:
    """Highest threshold that still catches at least `recall` of the real shortages."""
    pos = np.sort(p[y == 1])
    if len(pos) == 0:
        return 0.5
    k = int(np.floor((1 - recall) * len(pos)))
    return float(min(0.5, pos[k]))


class RiskModel:
    def __init__(self, model=None, meta: dict | None = None):
        self.model = model
        self.meta = meta or {}
        self.threshold = float(self.meta.get("threshold", 0.5))

    # -- training --------------------------------------------------------------
    @classmethod
    def train(cls, X_train: pd.DataFrame, y_train: np.ndarray, X_val: pd.DataFrame, y_val: np.ndarray,
              seed: int = 0, recall: float = 0.95) -> "RiskModel":
        """Fit the trees on the training timelines, then calibrate the probabilities and
        pick the alarm threshold on the validation timelines (never on the test set)."""
        base = make_hgb(seed).fit(X_train[RISK_FEATURES], y_train)
        cal = CalibratedClassifierCV(FrozenEstimator(base), method="isotonic")
        cal.fit(X_val[RISK_FEATURES], y_val)
        p_val = cal.predict_proba(X_val[RISK_FEATURES])[:, 1]
        meta = {"features": RISK_FEATURES, "sklearn": sklearn.__version__,
                "threshold": threshold_for_recall(np.asarray(y_val), p_val, recall),
                "target_recall": recall, "trees": int(base.n_iter_)}
        return cls(cal, meta)

    # -- using it --------------------------------------------------------------
    def predict_proba(self, X: pd.DataFrame | dict | list[dict]) -> np.ndarray:
        if isinstance(X, dict):
            X = [X]
        if not isinstance(X, pd.DataFrame):
            X = pd.DataFrame(X)
        return self.model.predict_proba(X[RISK_FEATURES])[:, 1]

    def predict(self, X) -> np.ndarray:
        """1 = alarm (risk at or above the threshold chosen for 95 % recall)."""
        return (self.predict_proba(X) >= self.threshold).astype(int)

    @property
    def trees(self) -> HistGradientBoostingClassifier:
        return self.model.estimator.estimator

    def explain(self, row: dict, reference: pd.DataFrame, top: int = 3) -> list[tuple[str, float]]:
        """Which inputs push this station's risk up or down the most.

        For each input: replace it with typical values from `reference` (e.g. the
        training rows) and see how much the risk changes. Positive = this input
        makes the risk higher than usual."""
        base = float(self.predict_proba(row)[0])
        sample = reference.sample(min(50, len(reference)), random_state=0)
        out = []
        for f in RISK_FEATURES:
            alt = pd.DataFrame([row] * len(sample))
            alt[f] = sample[f].to_numpy()
            out.append((f, base - float(self.predict_proba(alt).mean())))
        out.sort(key=lambda x: -abs(x[1]))
        return out[:top]

    def save(self, path: str | Path = DEFAULT_RISK_PATH) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": self.model, "meta": self.meta}, path)
        return path

    @classmethod
    def load(cls, path: str | Path = DEFAULT_RISK_PATH) -> "RiskModel":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"{path} not found. Run scripts/train_risk.py")
        d = joblib.load(path)
        if d["meta"].get("features") != RISK_FEATURES:
            raise ValueError(f"{path} was trained with other features. Retrain it.")
        return cls(d["model"], d["meta"])


__all__ = ["RiskModel", "DEFAULT_RISK_PATH", "FEATURE_LABELS", "make_hgb", "threshold_for_recall"]
