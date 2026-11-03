"""Start only the local MQTT broker (Mosquitto) with device keys, bridged to the cloud
if configured. Most of the time `python scripts/run_app.py` is easier: it starts the
broker, the AI and the website together.

    python scripts/start_broker.py              start it (keep this terminal open)
    python scripts/start_broker.py --dry-run    only print the configuration

The broker listens on port 1883 of every network card, so the car and the station
nodes can reach it over Wi-Fi. Every device logs in with its own key (username = its
ID, e.g. AGV-1); the keys are in config/devices.local.yaml and on the website's Setup
page. The first time, Windows asks whether Mosquitto may use the network: allow it on
private networks.

Cloud bridge: set `cloud.host` in config/mqtt.yaml, plus the environment variables
HIVEMQ_USERNAME and HIVEMQ_PASSWORD. Then every message under factory/# is copied to
the cloud, and manual requests and warehouse refills can come back from it.
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from agv_brain.broker import KEYS_FILE, Broker, build_config, lan_addresses  # noqa: E402
from agv_brain.models import load_settings  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="print the configuration and exit")
    args = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "config" / "mqtt.yaml").read_text(encoding="utf-8"))
    broker = Broker(int(cfg["local"]["port"]), cfg.get("cloud") or {}, [cfg.get("car_id", "AGV-1")],
                    list(load_settings().stations))
    if args.dry_run:
        text, _ = build_config(broker.port, broker.cloud, broker.folder)
        shown = "\n".join("remote_password ********" if line.startswith("remote_password") else line
                          for line in text.splitlines())
        print(f"# {broker.folder / 'mosquitto.conf'}\n{shown}")
        return
    if not broker.start():
        sys.exit(broker.error)
    print(f"MQTT broker on port {broker.port}, with device keys ({KEYS_FILE}).")
    addrs = lan_addresses()
    if addrs:
        print("The car and the stations connect to: " + ", ".join(f"{a}:{broker.port}" for a in addrs))
    print("Cloud bridge: " + (f"ON -> {cfg['cloud']['host']}" if broker.bridged else
                              "off (set cloud.host in config/mqtt.yaml and HIVEMQ_USERNAME / HIVEMQ_PASSWORD)"))
    print("Press Ctrl+C to stop.\n", flush=True)
    try:
        while broker.proc and broker.proc.poll() is None:
            time.sleep(1)
        print(f"Mosquitto stopped; see {broker.folder / 'mosquitto.log'}")
    except KeyboardInterrupt:
        pass
    finally:
        broker.stop()


if __name__ == "__main__":
    main()
