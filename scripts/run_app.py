"""Run everything with one command: the MQTT broker (with device keys), the AI and
the website. Switch between the simulation and the real factory on the Setup page.

    python scripts/run_app.py               website at http://localhost:8050
    python scripts/run_app.py --host 0.0.0.0    also open it from a phone (read-only there)

The real car needs the broker on port 1883. If the Mosquitto Windows service holds
that port, the app runs the simulation only and the Setup page explains the fix.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agv_brain.app import App  # noqa: E402
from agv_brain.dispatcher import POLICIES  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8050)
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to also open the website from other devices")
    ap.add_argument("--policy", default="ml", choices=POLICIES)
    args = ap.parse_args()

    app = App.start(host=args.host, port=args.port, policy=args.policy)
    b = app.broker
    if b:
        where = ", ".join(f"{a}:{b.port}" for a in app.setup(True)["broker"]["addresses"]) or f"port {b.port}"
        print(f"MQTT broker with device keys on {where}" + (" (cloud bridge on)" if b.bridged else ""))
    else:
        print(f"No MQTT broker, so only the simulation can run:\n  {app.broker_error}")
    print(f"Mode: {app.mode_name}, track: {app.track}")
    print(f"Website: {app.dash.url}  (Setup page: {app.dash.url}/#setup)")
    print("Press Ctrl+C to stop.", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        app.stop()


if __name__ == "__main__":
    main()
