"""Improve the ranker with situations from live operation (DAgger).

    python scripts/generate_dataset.py     (the random situations, once)
    python scripts/train_live.py --rounds 2 --episodes 300

Each round:
  1. run the factory loop fast with the current model (20 % random choices),
     on our track and on random layouts;
  2. label every decision situation with the exact optimizer;
  3. retrain on the random situations + all live situations collected so far;
  4. measure live accuracy on separate test episodes, with the new model driving.
The best model is saved to models/ranker.joblib.
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from agv_brain.features import JOB_FEATURES, PAIR_FEATURES, job_matrix  # noqa: E402
from agv_brain import live_dataset  # noqa: E402
from agv_brain.live_dataset import collect, usable  # noqa: E402
from agv_brain.optimizer import first_choice_costs  # noqa: E402
from agv_brain.ranker import DEFAULT_MODEL_PATH, TIE_EPS, PairwiseRanker, pair_examples  # noqa: E402
from agv_brain.simulator import load_context  # noqa: E402


def label(situations):
    Xs, ys, ws, rows = [], [], [], []
    for sid, x in enumerate(situations):
        costs = first_choice_costs(x.ctx, x.jobs, x.car)
        X, y, w = pair_examples(x.ctx, x.jobs, x.car, costs)
        Xs.append(X), ys.append(y), ws.append(w)
        F, _ = job_matrix(x.ctx, x.jobs, x.car)
        best = min(costs)
        for job, f, c in zip(x.jobs, F, costs):
            row = {"situation": sid, "layout": x.layout, "request": job.id, "car_node": x.car.node}
            row.update({k: round(float(v), 3) for k, v in zip(JOB_FEATURES, f)})
            row["teacher_cost_if_first"] = round(c, 3)
            row["teacher_best_first"] = int(c <= best + TIE_EPS)
            rows.append(row)
    return np.vstack(Xs), np.concatenate(ys).astype(int), np.concatenate(ws), rows


def live_accuracy(ctx, model, episodes, seed):
    r = live_dataset.live_accuracy(ctx, model, episodes, seed)
    return r["top1"], r["regret_pct"], r["decisions"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--episodes", type=int, default=300, help="60-minute factory runs per round")
    ap.add_argument("--test-episodes", type=int, default=40)
    ap.add_argument("--live-weight", type=float, default=2.0, help="weight of live examples vs random ones")
    ap.add_argument("--base", type=Path, default=ROOT / "data" / "generated" / "pairs.npz")
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH, help="model to start from")
    ap.add_argument("--out", type=Path, default=DEFAULT_MODEL_PATH)
    ap.add_argument("--max-iter", type=int, default=800)
    args = ap.parse_args()

    ctx = load_context()
    base = np.load(args.base)
    if list(base["features"]) != PAIR_FEATURES:
        sys.exit("The base dataset was built with different features. Regenerate it.")
    model = PairwiseRanker.load(args.model)
    acc, reg, n = live_accuracy(ctx, model, args.test_episodes, seed=999)
    print(f"start: live top-1 {acc:.1%}, regret {reg:.2f}% ({n} test decisions)")
    best = (acc, model, 0)

    live_X, live_y, live_w, live_rows = [], [], [], []
    for r in range(1, args.rounds + 1):
        t0 = time.perf_counter()
        sits = usable(collect(ctx, model, args.episodes, seed=100 + r, random_layouts=200,
                              layout_share=0.5, epsilon=0.2))
        X, y, w, rows = label(sits)
        for row in rows:
            row["round"] = r
        live_X.append(X)
        live_y.append(y)
        live_w.append(w * args.live_weight)
        live_rows += rows
        allX = np.vstack([base["X"], *live_X])
        ally = np.concatenate([base["y"], *live_y])
        allw = np.concatenate([base["w"], *live_w])
        model = PairwiseRanker(max_iter=args.max_iter).fit(allX, ally, allw)
        model.meta.update(layouts=f"{base['layouts']} + live operation ({sum(len(v) for v in live_y)} "
                                  f"pairs, {r} DAgger rounds)" if "layouts" in base else "live")
        acc, reg, n = live_accuracy(ctx, model, args.test_episodes, seed=999)
        print(f"round {r}: {len(sits)} new live situations, {len(ally)} pair rows, "
              f"live top-1 {acc:.1%}, regret {reg:.2f}% ({n} test decisions), {time.perf_counter() - t0:.0f} s")
        if acc > best[0]:
            best = (acc, model, r)

    acc, model, r = best
    model.meta.update(live_accuracy=acc)
    path = model.save(args.out)
    out = ROOT / "data" / "generated"
    np.savez_compressed(out / "live_pairs.npz", X=np.vstack(live_X), y=np.concatenate(live_y),
                        w=np.concatenate(live_w), features=np.array(PAIR_FEATURES))
    df = pd.DataFrame(live_rows)
    df.to_csv(out / "live_requests.csv", index=False)
    df[df.situation < 300].to_csv(ROOT / "data" / "sample" / "live_requests_sample.csv", index=False)
    print(f"kept round {r}: live top-1 {acc:.1%} -> saved {path}")


if __name__ == "__main__":
    main()
