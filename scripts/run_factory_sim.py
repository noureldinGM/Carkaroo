"""Run the simulated factory with the live dashboard.

    python scripts/run_factory_sim.py                  dashboard at http://localhost:8050
    python scripts/run_factory_sim.py --speed 5        slower, easier to follow
    python scripts/run_factory_sim.py --policy fifo    watch a simple rule instead of the AI
    python scripts/run_factory_sim.py --compare 40     no dashboard: ML vs FIFO vs optimizer
                                                       for 40 simulated minutes each
    python scripts/run_factory_sim.py --mqtt localhost:1883
                                                       go through a real MQTT broker

Press Ctrl+C to stop. Logs are written to logs/<date-time>/.
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agv_brain.dispatcher import POLICIES  # noqa: E402
from agv_brain.factory_sim import FactorySim  # noqa: E402


def compare(minutes: float, speed: float, seed: int) -> None:
    rows = []
    for policy in ("ml", "weighted_rules", "fifo", "optimal"):
        sim = FactorySim(policy=policy, speed=speed, seed=seed, log=False)
        sim.run_for(minutes)
        s = sim.summary()
        sim.stop()
        agree = f"{100 * s['optimizer_agrees'] / max(s['decisions'], 1):.0f}%"
        rows.append((policy, s["deliveries"], s["line_stop_s"], agree, s["regret_pct"]))
        print(f"{policy:15} deliveries {s['deliveries']:3}  line stop {s['line_stop_s']:7.1f} s  "
              f"optimizer agrees {agree:>4}  extra cost {s['regret_pct']:.2f}%", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--policy", default="ml", choices=POLICIES)
    ap.add_argument("--speed", type=float, default=10, help="simulated seconds per real second")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--battery", type=float, default=90)
    ap.add_argument("--port", type=int, default=8050)
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to open the dashboard from a phone on the same Wi-Fi")
    ap.add_argument("--minutes", type=float, default=0, help="stop after this many simulated minutes (0 = run until Ctrl+C)")
    ap.add_argument("--mqtt", default=None, metavar="HOST:PORT", help="use a real MQTT broker instead of the in-memory bus")
    ap.add_argument("--compare", type=float, default=0, metavar="MINUTES", help="headless comparison of policies")
    args = ap.parse_args()

    if args.compare:
        compare(args.compare, max(args.speed, 60), args.seed)
        return

    bus = None
    if args.mqtt:
        from agv_brain.bus import MqttBus
        host, _, port = args.mqtt.partition(":")
        bus = MqttBus(host, int(port or 1883), client_id="capstone-sim")
    sim = FactorySim(policy=args.policy, speed=args.speed, seed=args.seed, bus=bus, battery=args.battery)

    from agv_brain.dashboard import DashboardServer
    dash = DashboardServer(sim.bus, sim.controller.ctx, host=args.host, port=args.port, sim_controls=True)
    print(f"Simulated factory running at x{args.speed:g} speed with policy '{args.policy}'.")
    print(f"Dashboard: {dash.url}")
    print(f"Logs: {sim.log.folder}")
    print("Press Ctrl+C to stop.", flush=True)
    try:
        while not args.minutes or sim.clock.now() < args.minutes * 60:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        s = sim.summary()
        print(f"\n{s['sim_minutes']} simulated minutes: {s['deliveries']} deliveries, "
              f"line stopped {s['line_stop_s']} s, optimizer agreed {s['optimizer_agrees']}/{s['decisions']}")
        dash.stop()
        sim.stop()


if __name__ == "__main__":
    main()
