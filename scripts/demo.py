"""Show the AI brain deciding where the car goes first.

Fully automatic (reads the station stock sensors - simulated from config):
    python scripts/demo.py

Change what the sensors read, or where the car is:
    python scripts/demo.py --stock S3:B=12 --stock S2:C=1 --car S1 --battery 60

Manual requests (an operator asks for A and B at the same time):
    python scripts/demo.py --request A:S1 --request B:S3

Simulate an obstacle (ultrasonic sensor) blocking a line, so the car re-routes:
    python scripts/demo.py --block J2-J5
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agv_brain.dispatcher import POLICIES, Dispatcher  # noqa: E402
from agv_brain.models import CarState, Request, initial_state  # noqa: E402
from agv_brain.need_detector import fmt_s  # noqa: E402


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--request", action="append", default=[], metavar="MATERIAL:STATION",
                    help="manual request, e.g. A:S1 (repeatable). Without it the system decides itself.")
    ap.add_argument("--stock", action="append", default=[], metavar="STATION:MATERIAL=UNITS",
                    help="override a sensor reading, e.g. S3:B=2 (repeatable)")
    ap.add_argument("--car", default=None, help="node where the car is (default: the dock)")
    ap.add_argument("--heading", default=None, help="N/E/S/W the car faces (default: from the map)")
    ap.add_argument("--battery", type=float, default=90.0)
    ap.add_argument("--block", action="append", default=[], metavar="NODE-NODE",
                    help="mark a line as blocked by an obstacle, e.g. J2-J5")
    ap.add_argument("--policy", default="ml", choices=POLICIES)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    d = Dispatcher.from_config(policy=args.policy)
    ctx = d.ctx
    s = ctx.settings

    node = args.car or s.car.dock
    if args.heading:
        heading = args.heading
    elif len(ctx.fmap.neighbors(node)) == 1:
        heading = ctx.fmap.arrival_heading(node) if node != s.car.dock else s.car.start_heading
    else:
        heading = "N"
    state = initial_state(s, CarState(node, heading, args.battery))
    for item in args.stock:
        key, units = item.split("=")
        sid, mid = key.split(":")
        state.stations[sid].materials[mid].stock = float(units)
    for item in args.block:
        a, b = item.split("-", 1)
        ctx.fmap.block_edge(a, b)

    print(f"\n=== Station sensors (load cells) - car at {node} facing {heading}, "
          f"battery {args.battery:.0f}% ===")
    print(f"{'Station':<22}{'Mat':<5}{'Stock':>6}{'Use/min':>9}{'Safety':>8}{'Empty in':>10}")
    for sid, st in state.stations.items():
        for mid, sm in st.materials.items():
            empty = sm.stock / (sm.rate_per_min / 60) if sm.rate_per_min > 0 else float("inf")
            print(f"{sid + ' ' + st.name:<22}{mid:<5}{sm.stock:>6.0f}{sm.rate_per_min:>9.1f}"
                  f"{sm.safety_stock:>8.0f}{fmt_s(empty):>10}")
    if ctx.fmap.blocked:
        print("Blocked lines: " + ", ".join("-".join(sorted(e)) for e in ctx.fmap.blocked))

    if args.request:
        requests = []
        for k, item in enumerate(args.request):
            mid, sid = item.split(":")
            requests.append(Request(id=f"manual-{k + 1}-{mid}@{sid}", material=mid, station=sid))
        print("\n=== Manual requests ===")
        for r in requests:
            print(f"- {r.material} -> {r.station}")
    else:
        report = d.detect(state)
        requests = report.requests
        print("\n=== Needs detected automatically ===")
        for n in report.needs:
            print(f"- {n.request.material} -> {n.request.station}: {n.reason}")
        if not report.needs:
            print("- none: every station has enough stock for now")
        for a in report.alerts:
            print(f"! {a}")

    dec = d.decide(state, requests)
    print(f"\n=== AI decision (policy: {dec.policy}) ===")
    for a in dec.alerts:
        print(f"! {a}")
    if dec.charge_first:
        print(f"0. CHARGE at {s.car.dock}: {', '.join(dec.charge_route.commands)}")
    for k, t in enumerate(dec.tasks, 1):
        score = f"   score {t.score:.2f}" if t.score is not None else ""
        stop = f"   station stops {fmt_s(t.stop_s)}" if t.stop_s > 0.5 else ""
        print(f"{k}. {t.job.material} -> {t.job.station} ({s.stations[t.job.station].name})"
              f"   done in {fmt_s(t.finish_s)}{stop}{score}")
    print("\nWhy:")
    for r in dec.reasons:
        print(f" * {r}")

    if dec.tasks:
        t = dec.first
        print("\n=== Commands sent to the car for task 1 (one per junction) ===")
        print(f"to rack {t.job.rack:<6} path {' > '.join(t.to_rack.path)}")
        print(f"            commands {', '.join(t.to_rack.commands)}, then LIFT (servo fork up)")
        print(f"to {t.job.station:<10} path {' > '.join(t.to_station.path)}")
        print(f"            commands {', '.join(t.to_station.commands)}, then LOWER (servo fork down)")
    print()


if __name__ == "__main__":
    main()
