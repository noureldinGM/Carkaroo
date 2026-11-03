"""Run the AI controller and the dashboard against a real MQTT broker, in real time.

    python scripts/start_broker.py                    (first, in another terminal)
    python scripts/run_controller.py                  real car + real stations
    python scripts/run_controller.py --sim-stations   real car, simulated stations
    python scripts/run_controller.py --sim-car --sim-stations
                                                      everything simulated, but over MQTT
                                                      (checks the broker and the cloud bridge)

Dashboard at http://localhost:8050. Logs in logs/<date-time>/.
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from agv_brain.bus import Clock, MqttBus  # noqa: E402
from agv_brain.controller import Controller  # noqa: E402
from agv_brain.dashboard import DashboardServer  # noqa: E402
from agv_brain.dispatcher import POLICIES, Dispatcher  # noqa: E402
from agv_brain.eventlog import EventLog  # noqa: E402
from agv_brain.models import CarState  # noqa: E402
from agv_brain.sim_devices import SimulatedCar, SimulatedStation  # noqa: E402
from agv_brain.simulator import load_context  # noqa: E402


def main() -> None:
    cfg = yaml.safe_load((ROOT / "config" / "mqtt.yaml").read_text(encoding="utf-8"))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--broker", default=f"{cfg['local']['host']}:{cfg['local']['port']}", metavar="HOST:PORT")
    ap.add_argument("--policy", default="ml", choices=POLICIES)
    ap.add_argument("--sim-stations", action="store_true", help="simulate the station load cells")
    ap.add_argument("--sim-car", action="store_true", help="simulate the car")
    ap.add_argument("--port", type=int, default=8050)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    host, _, port = args.broker.partition(":")
    try:
        bus = MqttBus(host, int(port or 1883), client_id="capstone-controller")
    except (ConnectionError, OSError) as exc:
        sys.exit(f"{exc}. Start the broker first: python scripts/start_broker.py")
    clock = Clock(1.0)
    dispatcher = Dispatcher.from_config(policy=args.policy)
    log = EventLog()
    controller = Controller(bus, dispatcher, clock, car_id=cfg.get("car_id", "AGV-1"), log=log)
    devices = []
    if args.sim_car or args.sim_stations:
        truth = load_context()
        s = truth.settings
        if args.sim_car:
            devices.append(SimulatedCar(bus, clock, truth.fmap, s, car_id=cfg.get("car_id", "AGV-1"),
                                        start=CarState(s.car.dock, s.car.start_heading, 90.0)))
        if args.sim_stations:
            devices += [SimulatedStation(bus, clock, s, sid, seed=k) for k, sid in enumerate(s.stations)]
    dash = DashboardServer(bus, dispatcher.ctx, host=args.host, port=args.port,
                           sim_controls=args.sim_car or args.sim_stations)
    print(f"Controller connected to {args.broker}, policy '{args.policy}'.")
    print(f"Dashboard: {dash.url}\nLogs: {log.folder}\nPress Ctrl+C to stop.", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        dash.stop()
        controller.stop()
        for d in devices:
            d.stop()
        log.close()
        bus.close()


if __name__ == "__main__":
    main()
