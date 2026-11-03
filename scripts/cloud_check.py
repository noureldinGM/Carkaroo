"""Measure requirement R8: do messages reach the cloud, and how fast?

    python scripts/start_broker.py        (with the cloud bridge on, in another terminal)
    python scripts/cloud_check.py --count 300 --interval 0.5

Publishes numbered, time-stamped messages to the local broker and listens for
them on the cloud broker directly, so every message travels laptop -> bridge ->
cloud. Prints the delivery rate and the delay, and appends the result to
logs/cloud_check.csv for your logbook.
"""

import argparse
import csv
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import yaml  # noqa: E402

from agv_brain.bus import MqttBus  # noqa: E402

TOPIC = "factory/test/ping"


def main() -> None:
    cfg = yaml.safe_load((ROOT / "config" / "mqtt.yaml").read_text(encoding="utf-8"))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=300)
    ap.add_argument("--interval", type=float, default=0.5, help="seconds between messages")
    args = ap.parse_args()

    host = (cfg.get("cloud") or {}).get("host")
    user, password = os.environ.get("HIVEMQ_USERNAME"), os.environ.get("HIVEMQ_PASSWORD")
    if not (host and user and password):
        sys.exit("Set cloud.host in config/mqtt.yaml and the HIVEMQ_USERNAME / HIVEMQ_PASSWORD "
                 "environment variables first.")
    local = MqttBus(cfg["local"]["host"], int(cfg["local"]["port"]), client_id="capstone-cloud-check-pub")
    cloud = MqttBus(host, int(cfg["cloud"].get("port", 8883)), client_id="capstone-cloud-check-sub",
                    username=user, password=password, tls=True)
    arrived: dict[int, float] = {}
    lock = threading.Lock()

    def on_ping(topic, msg):
        with lock:
            arrived.setdefault(int(msg["i"]), time.time() - float(msg["t"]))

    cloud.subscribe(TOPIC, on_ping)
    time.sleep(1.0)
    print(f"Sending {args.count} messages, one every {args.interval} s ...", flush=True)
    for i in range(args.count):
        local.publish(TOPIC, {"i": i, "t": time.time()}, qos=1)
        time.sleep(args.interval)
    time.sleep(5.0)
    local.close()
    cloud.close()

    delays = np.array(list(arrived.values())) * 1000
    rate = len(arrived) / args.count
    print(f"delivered {len(arrived)}/{args.count} = {rate:.1%} (target >= 99 %)")
    if len(delays):
        print(f"delay: mean {delays.mean():.0f} ms, p95 {np.percentile(delays, 95):.0f} ms, "
              f"max {delays.max():.0f} ms (target <= 5000 ms)")
    out = ROOT / "logs" / "cloud_check.csv"
    out.parent.mkdir(exist_ok=True)
    new = not out.exists()
    with open(out, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "sent", "delivered", "rate", "mean_ms", "p95_ms", "max_ms"])
        w.writerow([datetime.now().isoformat(timespec="seconds"), args.count, len(arrived), f"{rate:.4f}",
                    f"{delays.mean():.0f}" if len(delays) else "", f"{np.percentile(delays, 95):.0f}" if len(delays) else "",
                    f"{delays.max():.0f}" if len(delays) else ""])
    print(f"saved to {out}")


if __name__ == "__main__":
    main()
