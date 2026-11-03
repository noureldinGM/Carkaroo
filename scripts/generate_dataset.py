"""Generate the training dataset.

    python scripts/generate_dataset.py --scenarios 20000

Writes:
    data/generated/pairs.npz       pair rows used to train the ranker
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

from agv_brain.dataset import PAIR_FEATURES, generate  # noqa: E402
from agv_brain.simulator import load_context  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenarios", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--min-n", type=int, default=2, help="fewest requests per scenario")
    ap.add_argument("--max-n", type=int, default=6, help="most requests per scenario")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "generated")
    args = ap.parse_args()

    ctx = load_context()
    t0 = time.perf_counter()
    ds = generate(ctx, args.scenarios, args.seed, (args.min_n, args.max_n))
    took = time.perf_counter() - t0

    args.out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out / "pairs.npz", X=ds.X, y=ds.y.astype(int), w=ds.w,
                        groups=ds.groups, features=np.array(PAIR_FEATURES))
    df = pd.DataFrame(ds.job_rows)
    df.to_csv(args.out / "requests.csv", index=False)
    sample_dir = ROOT / "data" / "sample"
    sample_dir.mkdir(parents=True, exist_ok=True)
    df[df.scenario < 300].to_csv(sample_dir / "requests_sample.csv", index=False)

    print(f"{args.scenarios} scenarios, {len(df)} requests, {len(ds.y)} pair rows "
          f"({ds.X.shape[1]} features) in {took:.1f} s")
    print(f"label balance: {ds.y.mean():.3f} (should be ~0.5)")
    print(f"saved to {args.out}")


if __name__ == "__main__":
    main()
