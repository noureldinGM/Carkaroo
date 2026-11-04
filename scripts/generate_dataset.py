"""Generate the training dataset.

    python scripts/generate_dataset.py --scenarios 30000 --random-layouts 400

60 % of the situations come from random factory layouts and 40 % from our track
(change with --layout-share; --random-layouts 0 = our track only).

Large factories at real-factory scale (2-340 m, AGV at 0.5-2 m/s, see
agv_brain/layouts.py random_plant), as an extra training file:

    python scripts/generate_dataset.py --plants 12000

Writes:
    data/generated/pairs.npz       pair rows used to train the ranker
    data/generated/plant_pairs.npz, plant_requests.csv   (with --plants)
    data/generated/requests.csv    one readable row per request (all scenarios)
    data/sample/requests_sample.csv  the first 300 scenarios (committed, for the exhibition)
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from agv_brain.dataset import PAIR_FEATURES, generate, generate_plants  # noqa: E402
from agv_brain.simulator import load_context  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenarios", type=int, default=30000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--random-layouts", type=int, default=400, help="random factories to mix in")
    ap.add_argument("--layout-share", type=float, default=0.6,
                    help="share of situations taken from the random factories")
    ap.add_argument("--min-n", type=int, default=2, help="fewest requests per scenario")
    ap.add_argument("--max-n", type=int, default=6, help="most requests per scenario")
    ap.add_argument("--plants", type=int, default=0,
                    help="make only this many large-factory situations (plant_pairs.npz)")
    ap.add_argument("--n-plants", type=int, default=300, help="random large factories to use")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "generated")
    args = ap.parse_args()
    if args.plants:
        return plants(args)

    ctx = load_context()
    t0 = time.perf_counter()
    ds = generate(ctx, args.scenarios, args.seed, (args.min_n, args.max_n),
                  random_layouts=args.random_layouts, layout_share=args.layout_share)
    took = time.perf_counter() - t0
    if args.random_layouts:
        layouts = (f"our track + {args.random_layouts} random layouts "
                   f"({args.layout_share:.0%} of situations), {args.scenarios} situations")
    else:
        layouts = f"our track only, {args.scenarios} situations"

    args.out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out / "pairs.npz", X=ds.X, y=ds.y.astype(int), w=ds.w,
                        groups=ds.groups, features=np.array(PAIR_FEATURES), layouts=np.array(layouts))
    df = pd.DataFrame(ds.job_rows)
    df.to_csv(args.out / "requests.csv", index=False)
    sample_dir = ROOT / "data" / "sample"
    sample_dir.mkdir(parents=True, exist_ok=True)
    df[df.scenario < 300].to_csv(sample_dir / "requests_sample.csv", index=False)

    print(f"{args.scenarios} scenarios, {len(df)} requests, {len(ds.y)} pair rows "
          f"({ds.X.shape[1]} features) in {took:.1f} s")
    print(f"label balance: {ds.y.mean():.3f} (should be ~0.5)")
    print(f"data: {layouts}")
    print(f"saved to {args.out}")


def plants(args) -> None:
    ctx = load_context()
    t0 = time.perf_counter()
    ds = generate_plants(args.plants, ctx.settings, args.seed + 1, args.n_plants, (args.min_n, args.max_n))
    layouts = f"{args.n_plants} large random factories, {args.plants} situations"
    args.out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out / "plant_pairs.npz", X=ds.X, y=ds.y.astype(int), w=ds.w,
                        groups=ds.groups, features=np.array(PAIR_FEATURES), layouts=np.array(layouts))
    df = pd.DataFrame(ds.job_rows)
    df.to_csv(args.out / "plant_requests.csv", index=False)
    print(f"{args.plants} scenarios, {len(df)} requests, {len(ds.y)} pair rows in "
          f"{time.perf_counter() - t0:.1f} s, label balance {ds.y.mean():.3f}")
    print(f"saved to {args.out / 'plant_pairs.npz'}")


if __name__ == "__main__":
    main()
