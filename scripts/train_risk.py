"""Train the shortage-risk model.

    python scripts/generate_risk_dataset.py   (first, if data/generated/risk.csv is missing)
    python scripts/train_risk.py

Splits by timeline: 70 % train, 15 % validation, 15 % test (the same split as
scripts/evaluate_risk.py). The trees learn on the training timelines; the
probabilities are calibrated and the alarm threshold (95 % of shortages caught)
is chosen on the validation timelines. The test timelines are not touched here.

Saves models/risk_model.joblib.
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
from sklearn.metrics import accuracy_score, recall_score, roc_auc_score  # noqa: E402

from agv_brain.risk_dataset import LABEL, split_by_timeline  # noqa: E402
from agv_brain.risk_model import DEFAULT_RISK_PATH, RiskModel  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "generated" / "risk.csv")
    ap.add_argument("--out", type=Path, default=DEFAULT_RISK_PATH)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    if not args.data.exists():
        sys.exit(f"{args.data} not found. Run: python scripts/generate_risk_dataset.py")
    df = pd.read_csv(args.data)
    tr, va, te = split_by_timeline(df, args.seed)
    y = df[LABEL].to_numpy()
    print(f"timelines: {df[tr].timeline.nunique()} train, {df[va].timeline.nunique()} validation, "
          f"{df[te].timeline.nunique()} test (rows {tr.sum()} / {va.sum()} / {te.sum()})")

    t0 = time.perf_counter()
    model = RiskModel.train(df[tr], y[tr], df[va], y[va], seed=args.seed)
    print(f"trained in {time.perf_counter() - t0:.1f} s ({model.meta['trees']} trees)")

    p = model.predict_proba(df[va])
    print(f"validation: accuracy {accuracy_score(y[va], p >= 0.5):.3f}, ROC-AUC {roc_auc_score(y[va], p):.4f}, "
          f"alarm threshold {model.threshold:.3f} -> recall {recall_score(y[va], p >= model.threshold):.3f}")
    print(f"saved to {model.save(args.out)}. Test it with: python scripts/evaluate_risk.py")


if __name__ == "__main__":
    main()
