"""The ML ranker: learns "which request should go first" from the teacher.

Training (scripts/train_ranker.py):
  1. The simulator makes thousands of random factory situations.
  2. The teacher (optimizer.py) computes, for every request, the best total cost
     reachable if that request is served first.
  3. For every pair (i, j) the label is 1 if starting with i is better than
     starting with j. A gradient-boosted tree classifier learns this from the
     pair features (features.py).

Using it: each request's score is the sum of its win probabilities against all
other requests. The highest score goes first.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier

from agv_brain.features import PAIR_FEATURES, pair_matrix
from agv_brain.models import ROOT, CarState, Job
from agv_brain.simulator import Context

DEFAULT_MODEL_PATH = ROOT / "models" / "ranker.joblib"
TIE_EPS = 1e-6


def pair_examples(ctx: Context, jobs: list[Job], car: CarState,
                  first_costs: list[float]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Training rows for one scenario: X, label, sample weight. Ties are skipped."""
    n = len(jobs)
    pairs = [(i, j) for i in range(n) for j in range(n)
             if i != j and abs(first_costs[i] - first_costs[j]) > TIE_EPS]
    if not pairs:
        return np.empty((0, len(PAIR_FEATURES))), np.empty(0), np.empty(0)
    X, pairs = pair_matrix(ctx, jobs, car, pairs)
    y = np.array([first_costs[i] < first_costs[j] for i, j in pairs], dtype=int)
    gap = np.array([abs(first_costs[i] - first_costs[j]) for i, j in pairs])
    w = 0.2 + np.minimum(gap / 20.0, 1.0)  # costly mistakes count more
    return X, y, w


class PairwiseRanker:
    def __init__(self, model: HistGradientBoostingClassifier | None = None, meta: dict | None = None,
                 max_iter: int = 400):
        self.model = model or HistGradientBoostingClassifier(
            max_iter=max_iter, learning_rate=0.08, max_leaf_nodes=31,
            l2_regularization=1.0, early_stopping=True, validation_fraction=0.1,
            random_state=0)
        self.meta = meta or {}

    def fit(self, X: np.ndarray, y: np.ndarray, w: np.ndarray | None = None) -> "PairwiseRanker":
        self.model.fit(X, y, sample_weight=w)
        self.meta.update(features=PAIR_FEATURES, sklearn=sklearn.__version__, rows=len(y))
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self.model.predict_proba(X)[:, 1]

    def score(self, ctx: Context, jobs: list[Job], car: CarState) -> np.ndarray:
        """Higher = serve sooner. Usable directly as a policy (see baselines.rollout)."""
        n = len(jobs)
        if n == 1:
            return np.ones(1)
        X, pairs = pair_matrix(ctx, jobs, car)
        p = self.predict_proba(X)
        scores = np.zeros(n)
        for (i, j), pij in zip(pairs, p):
            # both (i, j) and (j, i) are predicted; average them for a symmetric answer
            scores[i] += pij / 2
            scores[j] += (1 - pij) / 2
        return scores

    __call__ = score

    def save(self, path: str | Path = DEFAULT_MODEL_PATH) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": self.model, "meta": self.meta}, path, compress=3)
        return path

    @classmethod
    def load(cls, path: str | Path = DEFAULT_MODEL_PATH) -> "PairwiseRanker":
        data = joblib.load(path)
        if data["meta"].get("features") != PAIR_FEATURES:
            raise ValueError(f"{path} was trained with different features; retrain it "
                             "with scripts/train_ranker.py")
        return cls(data["model"], data["meta"])
