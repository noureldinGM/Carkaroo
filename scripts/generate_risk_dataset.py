"""Generate the dataset for the shortage-risk model.

    python scripts/generate_risk_dataset.py                    (180 timelines, about 43,000 rows)
    python scripts/generate_risk_dataset.py --timelines 40     (quick try)

Each timeline is one simulated hour of a factory (our track or one of 200 random
layouts) with changing demand: shifts, production orders, surges, downtime
(agv_brain/demand.py). Rows are taken every ~45 s after a 15-minute warm-up.
A second, smaller set on factories built from another seed is the "unseen
layouts" test.

Writes:
    data/generated/risk.csv           training / validation / test rows
    data/generated/risk_unseen.csv    unseen-layout test rows
    data/sample/risk_sample.csv       the first 20 timelines (committed, for the exhibition)
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agv_brain.risk_dataset import LABEL, RISK_FEATURES, generate_risk, training_layouts, unseen_layouts  # noqa: E402
from agv_brain.simulator import load_context  # noqa: E402


def quality(df, name: str) -> None:
    n_dup = int(df.duplicated(subset=RISK_FEATURES).sum())
    n_na = int(df[RISK_FEATURES].isna().sum().sum())
    neg = [f for f in ("stock", "eta_s", "trip_s", "rate_est_per_min") if (df[f] < 0).any()]
    print(f"{name}: {len(df)} rows, {df.timeline.nunique()} timelines, "
          f"shortage rate {df[LABEL].mean():.3f}, missing values {n_na}, duplicate rows {n_dup}, "
          f"negative values in {neg or 'none'}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--timelines", type=int, default=180)
    ap.add_argument("--unseen-timelines", type=int, default=40)
    ap.add_argument("--random-layouts", type=int, default=200)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "generated")
    args = ap.parse_args()

    ctx = load_context()
    t0 = time.perf_counter()
    df = generate_risk(training_layouts(ctx, args.random_layouts), args.timelines, seed=args.seed)
    unseen = generate_risk(unseen_layouts(ctx), args.unseen_timelines, seed=args.seed + 1000)
    took = time.perf_counter() - t0

    args.out.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out / "risk.csv", index=False)
    unseen.to_csv(args.out / "risk_unseen.csv", index=False)
    sample = ROOT / "data" / "sample"
    sample.mkdir(parents=True, exist_ok=True)
    df[df.timeline < 20].round(3).to_csv(sample / "risk_sample.csv", index=False)

    quality(df, "main")
    quality(unseen, "unseen layouts")
    print(f"{len(RISK_FEATURES)} features, made in {took:.0f} s, saved to {args.out}")


if __name__ == "__main__":
    main()
