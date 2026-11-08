"""The Carkaroo Simulator: a pretend car and pretend stations, on their own website.

It is a separate program from the Carkaroo website. Start the website first
(scripts/run_app.py), then this one, and open http://localhost:8060:

    python scripts/run_simulator.py              simulator at http://localhost:8060

On the simulator, choose your factory, paste the keys from the website's
Setup -> Devices -> "Copy all for the simulator", and connect. Each pretend device logs in
to the broker with its own key, exactly like the real car and stations will.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agv_brain.practice_server import PracticeServer  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8060)
    args = ap.parse_args()
    server = PracticeServer(port=args.port)
    print(f"Carkaroo Simulator: {server.url}  (the Carkaroo website runs separately, scripts/run_app.py)")
    print("Press Ctrl+C to stop.", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()


if __name__ == "__main__":
    main()
