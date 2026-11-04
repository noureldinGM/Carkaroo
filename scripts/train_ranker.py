"""Train the ML ranker on the generated dataset.

    python scripts/generate_dataset.py      (first, if data/generated/pairs.npz is missing)
    python scripts/train_ranker.py

Holds out 20 % of the scenarios (whole scenarios, never split in the middle) to
report pairwise accuracy, then saves models/ranker.joblib.

--extra adds more pair files (live operation, large factories) to the training
rows; --holdout 0 trains on everything, as the final model does:

    python scripts/train_ranker.py --extra data/generated/live_pairs.npz data/generated/plant_pairs.npz --holdout 0
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
    ap.add_argument("--max-iter", type=int, default=800, help="most boosting rounds (early stopping may use fewer)")
    ap.add_argument("--extra", type=Path, nargs="*", default=[],
                    help="more pair files to train on (always used in full)")
    ap.add_argument("--holdout", type=float, default=0.2,
                    help="share of --data scenarios kept for validation (0 = train on all)")
    args = ap.parse_args()

    if not args.data.exists():
        sys.exit(f"{args.data} not found. Run: python scripts/generate_dataset.py")
    d = np.load(args.data)
    if list(d["features"]) != PAIR_FEATURES:
        sys.exit("The dataset was built with different features. Regenerate it.")
    X, y, w, groups = d["X"], d["y"], d["w"], d["groups"]

    rng = np.random.default_rng(args.seed)
    scen = np.unique(groups)
    val_scen = rng.choice(scen, size=int(len(scen) * args.holdout), replace=False)
    val = np.isin(groups, val_scen)
    layouts = str(d["layouts"]) if "layouts" in d else "our track only"
    trX, trY, trW = [X[~val]], [y[~val]], [w[~val]]
    for path in args.extra:
        e = np.load(path)
        if list(e["features"]) != PAIR_FEATURES:
            sys.exit(f"{path} was built with different features. Regenerate it.")
        trX.append(e["X"]), trY.append(e["y"]), trW.append(e["w"])
        layouts += f" + {e['layouts'] if 'layouts' in e else path.stem} ({len(e['y'])} pairs)"
    trX, trY, trW = np.vstack(trX), np.concatenate(trY), np.concatenate(trW)

    t0 = time.perf_counter()
    ranker = PairwiseRanker(max_iter=args.max_iter).fit(trX, trY, trW)
    took = time.perf_counter() - t0
    acc_train = ((ranker.predict_proba(trX) > 0.5) == trY).mean()
    acc_val = ((ranker.predict_proba(X[val]) > 0.5) == y[val]).mean() if val.any() else float("nan")
    ranker.meta.update(pairwise_accuracy_train=float(acc_train), pairwise_accuracy_val=float(acc_val),
                       train_scenarios=int(len(scen) - len(val_scen)), layouts=layouts)
    path = ranker.save(args.out)

    print(f"trained on {len(trY)} pair rows ({len(scen) - len(val_scen)} scenarios of --data + extras) "
          f"in {took:.1f} s ({ranker.model.n_iter_} boosting rounds)")
    print(f"pairwise accuracy  train {acc_train:.3f}   validation {acc_val:.3f}")
    print(f"saved {path} ({path.stat().st_size / 1024:.0f} KB)")
    print("next: python scripts/evaluate.py")


if __name__ == "__main__":
    main()
