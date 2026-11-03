"""Start the local MQTT broker (Mosquitto), bridged to the cloud if configured.

    python scripts/start_broker.py              start it (keep this terminal open)
    python scripts/start_broker.py --dry-run    only print the configuration

The broker listens on port 1883 of every network card, so the car and the
station nodes can reach it over Wi-Fi. The first time, Windows asks whether
Mosquitto may use the network: allow it on private networks.

Cloud bridge: set `cloud.host` in config/mqtt.yaml, plus the environment
variables HIVEMQ_USERNAME and HIVEMQ_PASSWORD. Then every message under
factory/# is copied to the cloud, and manual requests (factory/ai/request)
can come back from it.
"""

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def find_mosquitto() -> str | None:
    found = shutil.which("mosquitto")
    if found:
        return found
    for p in (r"C:\Program Files\mosquitto\mosquitto.exe", r"C:\Program Files (x86)\mosquitto\mosquitto.exe"):
        if Path(p).exists():
            return p
    return None


def port_free(port: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


def lan_addresses() -> list[str]:
    try:
        return [a for a in socket.gethostbyname_ex(socket.gethostname())[2] if not a.startswith("127.")]
    except OSError:
        return []


def build_config(port: int, cloud: dict, folder: Path) -> tuple[str, bool]:
    lines = [
        f"listener {port} 0.0.0.0",
        "allow_anonymous true",
        "persistence false",
        "log_dest stdout",
        "log_type error",
        "log_type warning",
        "log_type notice",
        "log_type information",
    ]
    user, password = os.environ.get("HIVEMQ_USERNAME"), os.environ.get("HIVEMQ_PASSWORD")
    bridged = bool(cloud.get("host") and user and password)
    if bridged:
        import certifi
        ca = folder / "ca.pem"
        shutil.copyfile(certifi.where(), ca)
        lines += [
            "",
            "connection capstone-cloud",
            f"address {cloud['host']}:{cloud.get('port', 8883)}",
            f"remote_username {user}",
            f"remote_password {password}",
            f"remote_clientid capstone-laptop-{socket.gethostname().lower()}",
            "bridge_protocol_version mqttv311",
            f"bridge_cafile {ca}",
            "bridge_insecure false",
            "try_private false",
            "cleansession true",
            "notifications false",
            "start_type automatic",
            "topic factory/# out 1",
            "topic factory/ai/request in 1",
        ]
    return "\n".join(lines) + "\n", bridged


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="print the configuration and exit")
    args = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "config" / "mqtt.yaml").read_text(encoding="utf-8"))
    port = int(cfg["local"]["port"])
    folder = Path(tempfile.gettempdir()) / "capstone-mosquitto"
    folder.mkdir(exist_ok=True)
    if " " in str(folder):
        print(f"Warning: {folder} contains a space; Mosquitto may not read files there.")
    text, bridged = build_config(port, cfg.get("cloud") or {}, folder)
    conf = folder / "mosquitto.conf"
    conf.write_text(text, encoding="utf-8")

    if args.dry_run:
        shown = "\n".join("remote_password ********" if line.startswith("remote_password") else line
                          for line in text.splitlines())
        print(f"# {conf}\n{shown}")
        return

    exe = find_mosquitto()
    if not exe:
        sys.exit("Mosquitto is not installed. Install it with:\n"
                 "    winget install --id EclipseFoundation.Mosquitto -e\n"
                 "(Windows asks for administrator permission.)")
    if not port_free(port):
        sys.exit(f"Port {port} is already in use, probably by the Mosquitto Windows service. "
                 "Stop it from an administrator terminal with:  Stop-Service mosquitto\n"
                 "(the service only listens on this laptop, so the car could not reach it).")

    print(f"MQTT broker on port {port}.")
    addrs = lan_addresses()
    if addrs:
        print("The car and the stations connect to: " + ", ".join(f"{a}:{port}" for a in addrs))
    print("Cloud bridge: " + (f"ON -> {cfg['cloud']['host']}" if bridged else
                              "off (set cloud.host in config/mqtt.yaml and HIVEMQ_USERNAME / HIVEMQ_PASSWORD)"))
    print("Press Ctrl+C to stop.\n", flush=True)
    try:
        subprocess.run([exe, "-c", str(conf)])
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
