"""Show how the AI's output changes as an input changes (capstone requirement).

Both A (for S1) and B (for S3) are requested. We sweep how much B is left at S3
and record which one the ML ranker sends first, and how long stations stop.

    python scripts/sensitivity.py
    python scripts/sensitivity.py --station S3 --material B --max 30
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from agv_brain.dispatcher import Dispatcher  # noqa: E402
from agv_brain.models import Request, initial_state  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--station", default="S3")
    ap.add_argument("--material", default="B")
    ap.add_argument("--other", default="A:S1", help="the competing request, MATERIAL:STATION")
    ap.add_argument("--max", type=int, default=12)
    ap.add_argument("--out", type=Path, default=ROOT / "reports" / "sensitivity.png")
    args = ap.parse_args()

    om, os_ = args.other.split(":")
    reqs = [Request("this", args.material, args.station), Request("other", om, os_)]
    ml, fifo = Dispatcher.from_config("ml"), Dispatcher.from_config("fifo")
    # FIFO serves the oldest first: make the competing request the older one
    reqs_fifo = [Request("this", args.material, args.station, created_s=0.0),
                 Request("other", om, os_, created_s=-5.0)]

    stocks = np.arange(0, args.max + 1)
    first, stop_ml, stop_fifo = [], [], []
    print(f"{args.material} at {args.station} vs {om} at {os_}")
    print(f"{'stock':>5}  {'ML sends first':<16}{'ML line stop':>13}{'FIFO line stop':>16}")
    for units in stocks:
        state = initial_state(ml.ctx.settings)
        state.stations[args.station].materials[args.material].stock = float(units)
        d_ml = ml.decide(state, reqs)
        fifo_state = initial_state(ml.ctx.settings)
        fifo_state.stations[args.station].materials[args.material].stock = float(units)
        d_fifo = fifo.decide(fifo_state, reqs_fifo)
        f = d_ml.first.job
        first.append(f.id == "this")
        stop_ml.append(sum(t.stop_s for t in d_ml.tasks))
        stop_fifo.append(sum(t.stop_s for t in d_fifo.tasks))
        print(f"{units:>5}  {f.material + ' -> ' + f.station:<16}{stop_ml[-1]:>12.0f}s{stop_fifo[-1]:>15.0f}s")

    from plot_style import ML, SERIES, finish, plt

    fig, (top, ax) = plt.subplots(2, 1, figsize=(7, 4.4), sharex=True,
                                  gridspec_kw={"height_ratios": [1, 4]})
    this_label = f"{args.material} -> {args.station} first"
    other_label = f"{om} -> {os_} first"
    for x, is_this in zip(stocks, first):
        top.barh(0, 1, left=x - 0.5, color=ML if is_this else SERIES[1], height=0.8,
                 edgecolor="#fcfcfb", linewidth=1)
    top.set_yticks([])
    top.grid(False)
    top.set_title(f"ML decision as {args.station}'s stock of {args.material} changes", pad=24)
    top.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=ML), plt.Rectangle((0, 0), 1, 1, color=SERIES[1])],
               labels=[this_label, other_label], loc="lower left", bbox_to_anchor=(0, 1.0),
               ncol=2, fontsize=9)
    ax.plot(stocks, stop_ml, color=ML, label="ML ranker")
    ax.plot(stocks, stop_fifo, color=SERIES[3], label="First come first served")
    ax.set_xlabel(f"Units of {args.material} left at {args.station} (load-cell reading)")
    ax.set_ylabel("Line-stop time (s)")
    ax.legend(loc="upper right", fontsize=9)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    finish(fig, args.out)
    print(f"chart: {args.out}")


if __name__ == "__main__":
    main()
