"""Evaluate the ML ranker against the optimizer and simple rules on unseen data.

    python scripts/evaluate.py --scenarios 1000 --random-layouts 200

Two test sets, both from random seeds never used in training:
    our track         config/factory_layout.yaml, random car position and speed
    unseen layouts    random factories the model has never seen (other grid
                      sizes, line lengths, numbers of materials and stations)
Both use up to 7 requests per situation (training only went up to 6).

Metrics per policy:
    top-1 accuracy   the first delivery chosen is the best one (same as the exact
                     optimizer; ties count as correct). This is the "AI accuracy"
                     the capstone asks for (target >= 80 %).
    line stop        seconds the stations are stopped while waiting for material
    extra cost       how much worse the whole plan is than the optimal plan (%)
    decision time    how long choosing the next delivery takes on this laptop

Writes reports/evaluation.md, reports/evaluation.csv and charts in reports/.
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.inspection import permutation_importance  # noqa: E402
from sklearn.metrics import confusion_matrix  # noqa: E402

from agv_brain.baselines import BASELINES, rollout  # noqa: E402
from agv_brain.dataset import speed_variants  # noqa: E402
from agv_brain.features import JOB_FEATURES, PAIR_EXTRA, PAIR_FEATURES  # noqa: E402
from agv_brain.layouts import layout_pool  # noqa: E402
from agv_brain.live_dataset import live_accuracy  # noqa: E402
from agv_brain.optimizer import best_order, first_choice_costs  # noqa: E402
from agv_brain.ranker import DEFAULT_MODEL_PATH, PairwiseRanker, pair_examples  # noqa: E402
from agv_brain.simulator import load_context, random_scenario, simulate  # noqa: E402

TARGET = 0.80
POLICY_LABELS = {
    "ml": "ML ranker",
    "weighted_rules": "Weighted rules",
    "earliest_stockout": "Earliest stockout",
    "nearest": "Nearest first",
    "fifo": "First come first served",
    "optimal": "Exact optimizer",
}
FEATURE_LABELS = {
    "stock": "Stock left",
    "rate_per_min": "Usage rate",
    "stockout_s": "Time until empty",
    "below_safety_s": "Time until safety level",
    "trip_s": "Trip time",
    "to_rack_s": "Time to reach the rack",
    "slack_s": "Slack (empty time - trip)",
    "safety_slack_s": "Safety slack",
    "criticality": "Station criticality",
    "wait_s": "Waiting time",
    "safety_gap": "Below safety stock by",
    "n_jobs": "Requests waiting",
    "slack_rank": "Slack rank",
    "min_other_slack_s": "Tightest other slack",
    "chain_ij_s": "Other's finish if this goes first",
    "chain_ji_s": "This one's finish if other goes first",
    "j_late_if_i_first_s": "Other's stop if this goes first",
    "i_late_if_j_first_s": "This one's stop if other goes first",
    "late_diff_crit": "Who would stop longer (x criticality)",
}
ORDER = ["ml", "weighted_rules", "earliest_stockout", "nearest", "fifo", "optimal"]


def run(sample_ctx, ranker, scenarios, seed, n_range, scenario=random_scenario):
    """Score every policy on `scenarios` random situations. sample_ctx(rng) -> Context,
    scenario(rng, ctx, n_range) -> (car, jobs)."""
    policies = {"ml": ranker, **BASELINES}
    rng = np.random.default_rng(seed)
    rows, pair_X, pair_y = [], [], []
    for sid in range(scenarios):
        vctx = sample_ctx(rng)
        car, jobs = scenario(rng, vctx, n_range)
        costs = first_choice_costs(vctx, jobs, car)
        best_first = min(costs)
        opt_jobs, opt_cost = best_order(vctx, jobs, car)
        opt = simulate(vctx, opt_jobs, car)
        rows.append(dict(scenario=sid, n=len(jobs), policy="optimal", top1=1, cost=opt.total_cost,
                         stop_s=opt.stop_s, weighted_stop_s=opt.weighted_stop_s,
                         time_s=opt.total_time_s, extra_cost_pct=0.0, decision_ms=np.nan))
        for name, fn in policies.items():
            t0 = time.perf_counter()
            k = int(np.argmax(fn(vctx, jobs, car)))
            ms = (time.perf_counter() - t0) * 1000
            plan = simulate(vctx, rollout(fn, vctx, jobs, car), car)
            rows.append(dict(scenario=sid, n=len(jobs), policy=name,
                             top1=int(costs[k] <= best_first + 1e-6 * max(1.0, abs(best_first))),
                             cost=plan.total_cost, stop_s=plan.stop_s,
                             weighted_stop_s=plan.weighted_stop_s, time_s=plan.total_time_s,
                             extra_cost_pct=100 * (plan.total_cost - opt_cost) / max(opt_cost, 1e-9),
                             decision_ms=ms))
        X, y, _ = pair_examples(vctx, jobs, car, costs)
        pair_X.append(X), pair_y.append(y)
    return pd.DataFrame(rows), np.vstack(pair_X), np.concatenate(pair_y).astype(int)


def summarize(df):
    g = df.groupby("policy")
    s = pd.DataFrame({
        "top1_accuracy": g.top1.mean(),
        "mean_line_stop_s": g.stop_s.mean(),
        "scenarios_with_a_stop": g.stop_s.apply(lambda x: (x > 0.5).mean()),
        "mean_extra_cost_pct": g.extra_cost_pct.mean(),
        "decision_ms_mean": g.decision_ms.mean(),
        "decision_ms_p95": g.decision_ms.quantile(0.95),
    })
    return s.loc[[p for p in ORDER if p in s.index]]


def charts(df, summary, df_new, importance, out):
    from plot_style import ML, MUTED, SERIES, TEXT_2, finish, plt

    # 1. line stop per policy (our track)
    s = summary.drop(index="optimal").sort_values("mean_line_stop_s")
    fig, ax = plt.subplots(figsize=(7, 3.6))
    labels = [POLICY_LABELS[p] for p in s.index]
    colors = [ML if p == "ml" else MUTED for p in s.index]
    bars = ax.barh(labels, s.mean_line_stop_s, color=colors, height=0.6)
    opt_stop = summary.loc["optimal", "mean_line_stop_s"]
    ax.axvline(opt_stop, color=TEXT_2, linestyle="--", linewidth=1)
    for b, v in zip(bars, s.mean_line_stop_s):
        ax.text(b.get_width(), b.get_y() + b.get_height() / 2, f" {v:.0f} s", va="center",
                color=TEXT_2, fontsize=9)
    ax.set_ylim(len(s) - 0.5, -1.1)
    ax.text(opt_stop, -0.75, f"exact optimizer {opt_stop:.0f} s ", color=TEXT_2, fontsize=9,
            va="center", ha="right")
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Average line-stop time per situation (seconds, lower is better)")
    ax.set_title("Production stopped while waiting for material")
    finish(fig, out / "line_stop_by_policy.png")

    # 2. top-1 accuracy by number of requests
    acc = df[df.policy != "optimal"].groupby(["policy", "n"]).top1.mean().unstack(0)
    series = [(p, acc[p], SERIES[k], "-", POLICY_LABELS[p])
              for k, p in enumerate(["ml", "weighted_rules", "earliest_stockout", "fifo"])]
    if df_new is not None:
        acc_new = df_new[df_new.policy == "ml"].groupby("n").top1.mean().reindex(acc.index)
        series.insert(1, ("ml_new", acc_new, ML, "--", "ML ranker, unseen layouts"))
    fig, ax = plt.subplots(figsize=(7.4, 4.0))
    ends = sorted((v.iloc[-1] * 100, key) for key, v, *_ in series)
    label_y, prev = {}, None
    for y, key in ends:  # end labels pushed up so they never overlap each other
        y = y if prev is None else max(y, prev + 6)
        if abs(y - TARGET * 100) < 3:  # or the 80 % target line
            y = TARGET * 100 + 3
        label_y[key], prev = y, y
    for key, v, color, style, label in series:
        ax.plot(acc.index, v * 100, color=color, linestyle=style, marker="o", markersize=5, label=label)
        ax.text(acc.index[-1] + 0.1, label_y[key], label, color=TEXT_2, fontsize=9, va="center")
    ax.axhline(TARGET * 100, color=TEXT_2, linestyle=":", linewidth=1)
    mid = acc.index[len(acc.index) // 2]
    ax.text(mid, TARGET * 100 - 2, "80 % target", color=TEXT_2, fontsize=9, va="top")
    ax.set_xlim(acc.index[0] - 0.2, acc.index[-1] + 2.4)
    ax.set_ylim(0, 105)
    ax.set_xticks(acc.index)
    ax.set_xlabel("Requests waiting at the same time")
    ax.set_ylabel("Chose the best delivery (%)")
    ax.set_title("Top-1 accuracy vs the exact optimizer", pad=46)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, fontsize=9, handlelength=2)
    finish(fig, out / "accuracy_by_requests.png")

    # 3. feature importance
    imp = importance.sort_values()[-12:]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.barh([FEATURE_LABELS.get(f, f) for f in imp.index], imp.values, color=ML, height=0.6)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Accuracy lost when the factor is shuffled")
    ax.set_title("What the ML ranker relies on")
    finish(fig, out / "feature_importance.png")


def grouped_importance(ranker, X, y, rng_seed=0, max_rows=20000):
    idx = np.random.default_rng(rng_seed).choice(len(y), size=min(max_rows, len(y)), replace=False)
    r = permutation_importance(ranker.model, X[idx], y[idx], n_repeats=3, random_state=0,
                               scoring="accuracy")
    imp = pd.Series(r.importances_mean, index=PAIR_FEATURES)
    grouped = {f: imp[[f"i_{f}", f"j_{f}", f"d_{f}"]].sum() for f in JOB_FEATURES}
    grouped.update({f: imp[f] for f in PAIR_EXTRA})
    return pd.Series(grouped)


def policy_table(summary):
    lines = ["| Policy | Top-1 accuracy | Avg line stop | Situations with a stop | Extra cost vs optimal | Decision time (mean / p95) |",
             "|---|---|---|---|---|---|"]
    for p, r in summary.iterrows():
        ms = "-" if np.isnan(r.decision_ms_mean) else f"{r.decision_ms_mean:.2f} / {r.decision_ms_p95:.2f} ms"
        lines.append(f"| {POLICY_LABELS[p]} | {r.top1_accuracy:.1%} | {r.mean_line_stop_s:.1f} s | "
                     f"{r.scenarios_with_a_stop:.1%} | {r.mean_extra_cost_pct:.1f} % | {ms} |")
    return lines


def write_markdown(df, summary, pair_acc, cm, importance, df_new, summary_new, pair_acc_new,
                   ranker, args, out, live=None):
    ml_acc = summary.loc["ml", "top1_accuracy"]
    verdict = "PASS" if ml_acc >= TARGET else "FAIL"
    by_n = df[df.policy == "ml"].groupby("n").top1.agg(["mean", "count"])
    trained_on = ranker.meta.get("layouts", "our track only")
    lines = [
        "# Evaluation report",
        "",
        f"Generated by `python scripts/evaluate.py --scenarios {args.scenarios} --seed {args.seed} "
        f"--random-layouts {args.random_layouts}`. Model trained on: {trained_on}.",
        "",
        f"**AI accuracy on our track (top-1 vs exact optimizer): {ml_acc:.1%} - target 80 %: {verdict}**",
        "",
    ]
    if summary_new is not None:
        new_acc = summary_new.loc["ml", "top1_accuracy"]
        lines += [f"**AI accuracy on {args.random_layouts} factory layouts it has never seen: {new_acc:.1%} - "
                  f"target 80 %: {'PASS' if new_acc >= TARGET else 'FAIL'}**", ""]
    if live:
        lv = live["ml"]["top1"]
        lines += [f"**AI accuracy in live operation (the model running the factory): {lv:.1%} - "
                  f"target 80 %: {'PASS' if lv >= TARGET else 'FAIL'}**", ""]
    lines += [
        f"## Our track ({args.scenarios} unseen situations)",
        "",
        f"{args.min_n}-{args.max_n} requests each (training used 2-6), random car position and speed. "
        f"Pairwise accuracy (\"should i go before j?\"): {pair_acc:.1%}.",
        "",
        *policy_table(summary),
    ]
    fifo_stop = summary.loc["fifo", "mean_line_stop_s"]
    ml_stop = summary.loc["ml", "mean_line_stop_s"]
    if fifo_stop > 0:
        lines += ["", f"The ML ranker cuts line-stop time by {(1 - ml_stop / fifo_stop):.0%} "
                      "compared with first come, first served."]
    lines += ["", "The test situations are deliberately overloaded (many urgent requests at once, "
                  "one car), so even the exact optimizer cannot avoid every stop. What matters is "
                  "how close each policy gets to the optimizer."]
    if summary_new is not None:
        lines += ["", f"## Unseen factory layouts ({args.scenarios_random} situations on "
                      f"{args.random_layouts} random factories)", "",
                  "Grids of 2-4 x 3-6 junctions, lines 50-150 cm, 2-5 materials, 2-6 stations, "
                  f"random car speed. Pairwise accuracy: {pair_acc_new:.1%}.", "",
                  *policy_table(summary_new)]
        fifo_new = summary_new.loc["fifo", "mean_line_stop_s"]
        if fifo_new > 0:
            lines += ["", f"On these new factories the ML ranker cuts line-stop time by "
                          f"{(1 - summary_new.loc['ml', 'mean_line_stop_s'] / fifo_new):.0%} "
                          "compared with first come, first served."]
    if live:
        lines += ["", f"## Live operation ({args.live_episodes} one-hour factory runs)", "",
                  "Each policy runs the factory itself (half on our track, half on unseen random "
                  "layouts): the need detector creates the requests, the policy picks every delivery, "
                  "and every situation it meets is checked against the exact optimizer. These queues "
                  "look different from the random test situations above (more requests at once, "
                  "more near-ties), which is why the model was also trained on live operation "
                  "(`scripts/train_live.py`).", "",
                  "| Policy | Top-1 accuracy | Extra cost vs optimal | Decisions checked |", "|---|---|---|---|"]
        for p, r in live.items():
            lines.append(f"| {POLICY_LABELS[p]} | {r['top1']:.1%} | {r['regret_pct']:.2f} % | {r['decisions']} |")
    lines += ["", "## ML accuracy by number of requests", "",
              "| Requests | Our track | Unseen layouts |", "|---|---|---|"]
    by_n_new = (df_new[df_new.policy == "ml"].groupby("n").top1.mean()
                if df_new is not None else pd.Series(dtype=float))
    for n, r in by_n.iterrows():
        note = " (more than in training)" if n > 6 else ""
        new = f"{by_n_new[n]:.1%}" if n in by_n_new.index else "-"
        lines.append(f"| {n}{note} | {r['mean']:.1%} | {new} |")
    lines += ["", "## Pairwise confusion matrix (ML, our track)", "",
              "| | predicted: j first | predicted: i first |", "|---|---|---|",
              f"| **actual: j first** | {cm[0, 0]} | {cm[0, 1]} |",
              f"| **actual: i first** | {cm[1, 0]} | {cm[1, 1]} |",
              "", "## Most important factors", "",
              "| Factor | Importance |", "|---|---|"]
    for f, v in importance.sort_values(ascending=False).head(10).items():
        lines.append(f"| {FEATURE_LABELS.get(f, f)} (`{f}`) | {v:.4f} |")
    lines += ["", "## Charts", "",
              "![Line stop by policy](line_stop_by_policy.png)", "",
              "![Accuracy by requests](accuracy_by_requests.png)", "",
              "![Feature importance](feature_importance.png)", ""]
    (out / "evaluation.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenarios", type=int, default=1000, help="situations on our track")
    ap.add_argument("--seed", type=int, default=20261103)
    ap.add_argument("--random-layouts", type=int, default=200,
                    help="unseen random factories to test on (0 = skip)")
    ap.add_argument("--scenarios-random", type=int, default=1000, help="situations on those factories")
    ap.add_argument("--layout-seed", type=int, default=424242)
    ap.add_argument("--live-episodes", type=int, default=40, help="one-hour live factory runs per policy (0 = skip)")
    ap.add_argument("--min-n", type=int, default=2)
    ap.add_argument("--max-n", type=int, default=7)
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    ap.add_argument("--out", type=Path, default=ROOT / "reports")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    ctx = load_context()
    ranker = PairwiseRanker.load(args.model)
    n_range = (args.min_n, args.max_n)

    variants = speed_variants(ctx)
    df, X, y = run(lambda rng: variants[int(rng.integers(len(variants)))], ranker,
                   args.scenarios, args.seed, n_range)
    summary = summarize(df)
    pred = (ranker.predict_proba(X) > 0.5).astype(int)
    pair_acc = (pred == y).mean()
    cm = confusion_matrix(y, pred, labels=[0, 1])
    importance = grouped_importance(ranker, X, y)

    df_new = summary_new = pair_acc_new = None
    if args.random_layouts > 0:
        pool = layout_pool(args.random_layouts, args.layout_seed, ctx.settings)
        df_new, Xn, yn = run(lambda rng: pool[int(rng.integers(len(pool)))], ranker,
                             args.scenarios_random, args.seed + 1, n_range)
        summary_new = summarize(df_new)
        pair_acc_new = ((ranker.predict_proba(Xn) > 0.5).astype(int) == yn).mean()

    live = None
    if args.live_episodes > 0:
        live = {p: live_accuracy(ctx, fn, args.live_episodes, seed=999)
                for p, fn in (("ml", ranker), ("weighted_rules", BASELINES["weighted_rules"]),
                              ("earliest_stockout", BASELINES["earliest_stockout"]), ("fifo", BASELINES["fifo"]))}

    df.assign(test_set="our_track").pipe(
        lambda d: pd.concat([d, df_new.assign(test_set="unseen_layouts")]) if df_new is not None else d
    ).to_csv(args.out / "evaluation.csv", index=False)
    charts(df, summary, df_new, importance, args.out)
    write_markdown(df, summary, pair_acc, cm, importance, df_new, summary_new, pair_acc_new,
                   ranker, args, args.out, live)

    pd.set_option("display.width", 160)
    print("our track\n" + summary.round(3).to_string())
    print(f"pairwise accuracy {pair_acc:.3f}")
    if summary_new is not None:
        print("\nunseen layouts\n" + summary_new.round(3).to_string())
        print(f"pairwise accuracy {pair_acc_new:.3f}")
    print(f"\nML top-1 accuracy: our track {summary.loc['ml', 'top1_accuracy']:.1%}"
          + (f", unseen layouts {summary_new.loc['ml', 'top1_accuracy']:.1%}" if summary_new is not None else "")
          + (f", live operation {live['ml']['top1']:.1%}" if live else "")
          + f" (target {TARGET:.0%})")
    print(f"done in {time.perf_counter() - t0:.0f} s -> {args.out / 'evaluation.md'}")


if __name__ == "__main__":
    main()
