"""Evaluate the shortage-risk model on timelines it never saw.

    python scripts/evaluate_risk.py

Uses the test timelines of data/generated/risk.csv (the same split as
train_risk.py, never used for training or calibration) and the unseen-layout
timelines of data/generated/risk_unseen.csv.

Compares the model with:
    plain formula   "runs out if stock / measured rate < time until a box arrives"
    plan formula    "runs out if the planned usage until the box arrives >= stock"
                    (uses the shift plan, announced orders and downtime)
    logistic regression and random forest, trained on the same rows

Writes reports/risk_model.md, reports/risk_model.csv and charts in reports/.
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.calibration import calibration_curve  # noqa: E402
from sklearn.ensemble import RandomForestClassifier  # noqa: E402
from sklearn.inspection import permutation_importance  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import (accuracy_score, average_precision_score, brier_score_loss,  # noqa: E402
                             confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score)
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from agv_brain.risk_dataset import LABEL, RISK_FEATURES, naive_rule, plan_rule, split_by_timeline  # noqa: E402
from agv_brain.risk_model import DEFAULT_RISK_PATH, FEATURE_LABELS, RiskModel, make_hgb  # noqa: E402

TARGET = 0.80
PLAN_FEATURES = ["shift_mult", "next_shift_mult", "to_shift_change_s", "orders_active", "orders_boost",
                 "orders_coming_boost", "downtime_now", "downtime_in_eta_s", "planned_use_eta", "planned_margin"]
ENGINEERED_PLAN = ["planned_use_eta", "planned_margin"]
BASIC_FEATURES = ["stock", "rate_est_per_min", "eta_s"]


def metrics(y, p, pred) -> dict:
    return {"accuracy": accuracy_score(y, pred), "precision": precision_score(y, pred, zero_division=0),
            "recall": recall_score(y, pred), "f1": f1_score(y, pred),
            "roc_auc": roc_auc_score(y, p), "pr_auc": average_precision_score(y, p),
            "brier": brier_score_loss(y, p)}


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def charts(table, cal, importance, out: Path) -> None:
    from plot_style import ML, MUTED, SERIES, TEXT_2, finish, plt

    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    names = list(table.index)
    x = np.arange(len(names))
    colors = [ML if n.startswith("Risk model") else MUTED for n in names]
    ax.bar(x - 0.2, table["accuracy"] * 100, 0.4, color=colors, label="accuracy")
    ax.bar(x + 0.2, table["recall"] * 100, 0.4, color=colors, alpha=0.55, label="recall (shortages caught)")
    ax.axhline(TARGET * 100, color=SERIES[3], lw=1, ls="--")
    ax.set_xticks(x, [n.replace(" (", "\n(") for n in names], fontsize=8)
    ax.set_ylim(50, 100)
    ax.set_ylabel("%")
    ax.set_title("Shortage-risk model vs formulas and other models (test timelines)")
    ax.legend(loc="lower left", fontsize=8)
    finish(fig, out / "risk_comparison.png")

    fig, ax = plt.subplots(figsize=(4.6, 4.2))
    ax.plot([0, 1], [0, 1], color=MUTED, lw=1, ls="--", label="perfect")
    ax.plot(cal[1], cal[0], color=ML, marker="o", label="risk model")  # (predicted, real share)
    ax.set_xlabel("predicted risk")
    ax.set_ylabel("share that really ran out")
    ax.set_title("Are the probabilities honest?")
    ax.legend(fontsize=8)
    finish(fig, out / "risk_calibration.png")

    top = importance.head(10)[::-1]
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    ax.barh([FEATURE_LABELS[f] for f in top.index], top.values, color=ML)
    ax.set_xlabel("drop in ROC-AUC when this input is shuffled", color=TEXT_2)
    ax.set_title("What the risk model looks at most")
    finish(fig, out / "risk_importance.png")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "generated" / "risk.csv")
    ap.add_argument("--unseen", type=Path, default=ROOT / "data" / "generated" / "risk_unseen.csv")
    ap.add_argument("--model", type=Path, default=DEFAULT_RISK_PATH)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=ROOT / "reports")
    args = ap.parse_args()

    df = pd.read_csv(args.data)
    unseen = pd.read_csv(args.unseen)
    model = RiskModel.load(args.model)
    tr, va, te = split_by_timeline(df, args.seed)
    y = df[LABEL].to_numpy()
    test, yt = df[te], y[te]
    X = df[RISK_FEATURES]

    rows = {}
    rows["Plain formula"] = metrics(yt, naive_rule(test).astype(float), naive_rule(test))
    rows["Plan formula"] = metrics(yt, plan_rule(test).astype(float), plan_rule(test))
    lr = make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000)).fit(X[tr], y[tr])
    p = lr.predict_proba(X[te])[:, 1]
    rows["Logistic regression"] = metrics(yt, p, p >= 0.5)
    rf = RandomForestClassifier(300, min_samples_leaf=5, n_jobs=-1, random_state=args.seed).fit(X[tr], y[tr])
    p = rf.predict_proba(X[te])[:, 1]
    rows["Random forest"] = metrics(yt, p, p >= 0.5)
    p_risk = model.predict_proba(test)
    rows["Risk model (risk >= 0.5)"] = metrics(yt, p_risk, p_risk >= 0.5)
    rows[f"Risk model (alarm >= {model.threshold:.2f})"] = metrics(yt, p_risk, p_risk >= model.threshold)
    table = pd.DataFrame(rows).T

    # feature sets (same trees, no calibration, risk >= 0.5)
    sets = {"all inputs": RISK_FEATURES,
            "raw inputs only (no planned_use_eta / planned_margin)":
                [f for f in RISK_FEATURES if f not in ENGINEERED_PLAN],
            "without the production plan": [f for f in RISK_FEATURES if f not in PLAN_FEATURES],
            "only stock, rate and arrival time": BASIC_FEATURES}
    feature_sets = {}
    for name, cols in sets.items():
        m = make_hgb(args.seed).fit(X.loc[tr, cols], y[tr])
        q = m.predict_proba(X.loc[te, cols])[:, 1]
        feature_sets[name] = (accuracy_score(yt, q >= 0.5), roc_auc_score(yt, q))

    # unseen layouts, close calls, situations
    yu = unseen[LABEL].to_numpy()
    pu = model.predict_proba(unseen)
    unseen_rows = {"Plain formula": accuracy_score(yu, naive_rule(unseen)),
                   "Plan formula": accuracy_score(yu, plan_rule(unseen)),
                   "Risk model": accuracy_score(yu, pu >= 0.5)}
    unseen_auc = roc_auc_score(yu, pu)
    close = (np.abs(test["margin_naive_s"]) < 120).to_numpy()
    groups = {
        "close calls (plain formula within 2 min of the line)": close,
        "clear cases": ~close,
        "day shift (busiest)": (test["shift"] == "day").to_numpy(),
        "evening shift": (test["shift"] == "evening").to_numpy(),
        "night shift (quietest)": (test["shift"] == "night").to_numpy(),
        "production orders running": (test["orders_active"] > 0).to_numpy(),
        "no production orders": (test["orders_active"] == 0).to_numpy(),
    }
    by_group = {g: (int(m.sum()), yt[m].mean(), accuracy_score(yt[m], naive_rule(test[m])),
                    accuracy_score(yt[m], plan_rule(test[m])), accuracy_score(yt[m], p_risk[m] >= 0.5))
                for g, m in groups.items()}

    cm = confusion_matrix(yt, p_risk >= 0.5)
    cal = calibration_curve(yt, p_risk, n_bins=10, strategy="quantile")
    sample = test.sample(min(8000, len(test)), random_state=0)
    imp = permutation_importance(model.model, sample[RISK_FEATURES], sample[LABEL], scoring="roc_auc",
                                 n_repeats=3, random_state=0, n_jobs=-1)
    importance = pd.Series(imp.importances_mean, index=RISK_FEATURES).sort_values(ascending=False)

    six = test.head(6)
    model.predict_proba(six)
    times = []
    for _ in range(200):
        t0 = time.perf_counter()
        model.predict_proba(six)
        times.append((time.perf_counter() - t0) * 1000)
    t_mean, t_p95 = float(np.mean(times)), float(np.percentile(times, 95))

    args.out.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.out / "risk_model.csv")
    charts(table, cal, importance, args.out)

    acc = table.loc["Risk model (risk >= 0.5)", "accuracy"]
    lines = [
        "# Shortage-risk model: evaluation",
        "",
        "Generated by `python scripts/evaluate_risk.py`. Data: `scripts/generate_risk_dataset.py` "
        f"({len(df)} rows from {df.timeline.nunique()} simulated factory timelines, "
        f"plus {len(unseen)} rows on {unseen.timeline.nunique()} timelines in factories never used for training).",
        "",
        f"**Accuracy on test timelines it never saw: {pct(acc)} - target 80 %: "
        f"{'PASS' if acc >= TARGET else 'FAIL'}**",
        "",
        f"**Accuracy in factories it never saw: {pct(unseen_rows['Risk model'])} - target 80 %: "
        f"{'PASS' if unseen_rows['Risk model'] >= TARGET else 'FAIL'}**",
        "",
        "## What it predicts",
        "",
        "For one station and one material: the probability that the station runs out **before a box sent now "
        "could arrive** (`shortage_before_delivery`). The answer comes from the future of the simulated timeline: "
        "real usage changes with shifts, production orders, surges nobody announced, downtime and noise. "
        "The inputs only see the past readings and the production plan. All data is simulated.",
        "",
        f"Test set: {te.sum()} rows from {test.timeline.nunique()} timelines (15 %), never used for training "
        f"or calibration. {pct(yt.mean())} of them are real shortages.",
        "",
        "## Compared with formulas and other models (test timelines)",
        "",
        "| Method | Accuracy | Precision | Recall | F1 | ROC-AUC | PR-AUC | Brier (lower = better) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, r in table.iterrows():
        lines.append(f"| {name} | {pct(r.accuracy)} | {pct(r.precision)} | {pct(r.recall)} | {pct(r.f1)} | "
                     f"{r.roc_auc:.3f} | {r.pr_auc:.3f} | {r.brier:.4f} |")
    pf = table.loc["Plan formula"]
    alarm = table.loc[f"Risk model (alarm >= {model.threshold:.2f})"]
    lines += [
        "",
        "- **Accuracy** = share of all moments judged right. **Recall** = share of real shortages caught. "
        "**Precision** = share of alarms that were real. Accuracy alone can hide missed shortages, because most "
        "moments are safe: a model that always said \"safe\" would score "
        f"{pct(1 - yt.mean())} accuracy and catch nothing.",
        "- **ROC-AUC / Brier** judge the probability itself. The formulas only answer yes or no, so their "
        "scores here are much weaker: they cannot say *how* risky a station is.",
        f"- The alarm threshold ({model.threshold:.2f}) was chosen on the validation timelines to catch at least "
        f"95 % of the shortages there; on the test timelines it catches {pct(alarm.recall)}. It raises more "
        "alarms than 0.5 but misses fewer shortages.",
        f"- Honest reading: the plan formula is already strong ({pct(pf.accuracy)}), because most moments are "
        "clearly safe or clearly not. The model's gain is on the close calls (below) and in giving a "
        "calibrated probability.",
        "",
        "## Confusion matrix (risk model, risk >= 0.5)",
        "",
        "| | predicted: safe | predicted: shortage |",
        "|---|---|---|",
        f"| **really safe** | {cm[0, 0]} | {cm[0, 1]} |",
        f"| **really ran out** | {cm[1, 0]} | {cm[1, 1]} |",
        "",
        "## Where it helps (accuracy, test timelines)",
        "",
        "| Situations | Rows | Shortage rate | Plain formula | Plan formula | Risk model |",
        "|---|---|---|---|---|---|",
    ]
    for g, (n, rate, a_n, a_p, a_m) in by_group.items():
        lines.append(f"| {g} | {n} | {pct(rate)} | {pct(a_n)} | {pct(a_p)} | **{pct(a_m)}** |")
    lines += [
        "",
        "## Factories it never saw",
        "",
        f"{len(unseen)} rows on {unseen.timeline.nunique()} timelines in random factories built from another seed.",
        "",
        "| Method | Accuracy |",
        "|---|---|",
        *[f"| {k} | {pct(v)} |" for k, v in unseen_rows.items()],
        "",
        f"Risk model ROC-AUC on these factories: {unseen_auc:.3f}.",
        "",
        "## Which inputs matter (feature sets)",
        "",
        "The same tree model, trained with fewer inputs (risk >= 0.5, test timelines). "
        "`planned_use_eta` and `planned_margin` are calculated before the model (nominal rate x the plan "
        "until the box arrives); the second row shows how well the trees do when they must work that out "
        "from the raw inputs themselves.",
        "",
        "| Inputs | Accuracy | ROC-AUC |",
        "|---|---|---|",
        *[f"| {k} | {pct(a)} | {auc:.3f} |" for k, (a, auc) in feature_sets.items()],
        "",
        "## Most important inputs",
        "",
        "Permutation importance: how much the ROC-AUC drops when one input is shuffled. Inputs that carry "
        "the same information share the credit, so when `planned_margin` is there, the raw inputs it is made "
        "from look unimportant; the feature-set table above is the fairer view.",
        "",
        "| Input | Importance |",
        "|---|---|",
        *[f"| {FEATURE_LABELS[f]} (`{f}`) | {v:.4f} |" for f, v in importance.head(10).items()],
        "",
        "## Calibration",
        "",
        "Rows grouped by predicted risk, against the share that really ran out:",
        "",
        "| Predicted risk (mean) | Really ran out |",
        "|---|---|",
        *[f"| {a:.2f} | {b:.2f} |" for b, a in zip(*cal)],
        "",
        "## Speed",
        "",
        f"Risk for 6 stations at once: {t_mean:.2f} ms mean, {t_p95:.2f} ms p95 on this laptop.",
        "",
        "## Charts",
        "",
        "![Comparison](risk_comparison.png)",
        "",
        "![Calibration](risk_calibration.png)",
        "",
        "![Importance](risk_importance.png)",
        "",
    ]
    (args.out / "risk_model.md").write_text("\n".join(lines), encoding="utf-8")
    print(table.round(4).to_string())
    print(f"unseen layouts: {unseen_rows}")
    print(f"written to {args.out / 'risk_model.md'}")


if __name__ == "__main__":
    main()
