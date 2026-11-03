"""Train the ML ranker on the generated dataset.

    python scripts/generate_dataset.py      (first, if data/generated/pairs.npz is missing)
    python scripts/train_ranker.py

Holds out 20 % of the scenarios (whole scenarios, never split in the middle) to
report pairwise accuracy, then saves models/ranker.joblib.
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from agv_brain.features import PAIR_FEATURES  # noqa: E402
from agv_brain.ranker import DEFAULT_MODEL_PATH, PairwiseRanker  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "generated" / "pairs.npz")
    ap.add_argument("--out", type=Path, default=DEFAULT_MODEL_PATH)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    if not args.data.exists():
        sys.exit(f"{args.data} not found. Run: python scripts/generate_dataset.py")
    d = np.load(args.data)
    if list(d["features"]) != PAIR_FEATURES:
        sys.exit("The dataset was built with different features. Regenerate it.")
    X, y, w, groups = d["X"], d["y"], d["w"], d["groups"]

    rng = np.random.default_rng(args.seed)
    scen = np.unique(groups)
    val_scen = rng.choice(scen, size=len(scen) // 5, replace=False)
    val = np.isin(groups, val_scen)

    t0 = time.perf_counter()
    ranker = PairwiseRanker().fit(X[~val], y[~val], w[~val])
    took = time.perf_counter() - t0
    acc_train = ((ranker.predict_proba(X[~val]) > 0.5) == y[~val]).mean()
    acc_val = ((ranker.predict_proba(X[val]) > 0.5) == y[val]).mean()
    ranker.meta.update(pairwise_accuracy_train=float(acc_train), pairwise_accuracy_val=float(acc_val),
                       train_scenarios=int(len(scen) - len(val_scen)))
    path = ranker.save(args.out)

    print(f"trained on {(~val).sum()} pair rows from {len(scen) - len(val_scen)} scenarios "
          f"in {took:.1f} s ({ranker.model.n_iter_} boosting rounds)")
    print(f"pairwise accuracy  train {acc_train:.3f}   validation {acc_val:.3f}")
    print(f"saved {path} ({path.stat().st_size / 1024:.0f} KB)")
    print("next: python scripts/evaluate.py")


if __name__ == "__main__":
    main()
