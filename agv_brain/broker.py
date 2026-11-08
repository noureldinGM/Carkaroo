"""The laptop's MQTT broker (Mosquitto) with a login for every device.

Real IoT platforms give each device its own credentials. Here every device gets a
key: the car logs in as `AGV-1`, a station node as `S1`, the AI as `brain`. The
broker refuses anyone without a valid key, and each device may only use its own
topics (the ACL below), so a visitor's phone on the same Wi-Fi cannot drive the car.

Keys live in config/devices.local.yaml, which git ignores. The website's Setup page
shows them (on the laptop only) and can make a new one.
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
KEYS_FILE = ROOT / "config" / "devices.local.yaml"
BRAIN = "brain"   # the AI's own login
DEVICE_ID = re.compile(r"[A-Za-z0-9_-]{1,32}")   # ids go into the ACL and password files
MOSQUITTO_DIRS =(r"C:\Program Files\mosquitto", r"C:\Program Files (x86)\mosquitto")


def find_tool(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for d in MOSQUITTO_DIRS:
        p = Path(d) / f"{name}.exe"
        if p.exists():
            return str(p)
    return None


def port_free(port: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """True if something already answers on this port. (The website's server may share a
    port on Windows, so trying to bind is not enough: try to connect instead.)"""
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


# -- leftovers from an earlier run -------------------------------------------------
# The app starts Mosquitto as a child. If the app is killed instead of stopped with Ctrl+C,
# that broker keeps running on its own and holds the port, so the next start gets no broker.

def _processes() -> list[dict]:
    """Running processes as {pid, ppid, cmd}. Empty if they cannot be listed."""
    try:
        if os.name == "nt":
            ps = ("Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,CommandLine"
                  " | ConvertTo-Json -Compress")
            out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                                 capture_output=True, text=True, timeout=20).stdout
            rows = yaml.safe_load(out) or []         # JSON is valid YAML
            rows = rows if isinstance(rows, list) else [rows]
            return [{"pid": r["ProcessId"], "ppid": r["ParentProcessId"], "cmd": r.get("CommandLine") or ""}
                    for r in rows]
        out = subprocess.run(["ps", "-eo", "pid=,ppid=,args="], capture_output=True, text=True, timeout=10).stdout
        procs = []
        for line in out.splitlines():
            parts = line.split(None, 2)
            if len(parts) >= 2:
                procs.append({"pid": int(parts[0]), "ppid": int(parts[1]), "cmd": parts[2] if len(parts) > 2 else ""})
        return procs
    except (OSError, subprocess.SubprocessError, yaml.YAMLError, KeyError, TypeError, ValueError):
        return []


def is_carkaroo_app(cmd: str) -> bool:
    """A Carkaroo program that starts its own broker (the website app or a dev script)."""
    return "python" in cmd.lower() and ("run_app.py" in cmd or "agv_brain" in cmd)


def our_brokers(folder: Path, procs: list[dict] | None = None) -> tuple[list[int], list[int]]:
    """The Mosquitto processes started by a Carkaroo app with the config in `folder`:
    (orphans whose app is gone, brokers whose app still runs)."""
    procs = _processes() if procs is None else procs
    by_pid = {p["pid"]: p for p in procs}
    conf = str(folder / "mosquitto.conf").lower()
    orphans, owned = [], []
    for p in procs:
        if "mosquitto" not in p["cmd"].lower() or conf not in p["cmd"].lower():
            continue
        parent = by_pid.get(p["ppid"])
        (owned if parent and is_carkaroo_app(parent["cmd"]) else orphans).append(p["pid"])
    return orphans, owned


def stop_process(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    else:
        try:
            os.kill(pid, 15)
        except OSError:
            pass


def lan_addresses() -> list[str]:
    try:
        return [a for a in socket.gethostbyname_ex(socket.gethostname())[2] if not a.startswith("127.")]
    except OSError:
        return []


# -- keys ------------------------------------------------------------------------

def load_keys(devices: list[str], path: Path = KEYS_FILE) -> dict[str, str]:
    """Keys for `devices` plus the AI; missing ones are created and saved."""
    keys = {}
    if path.exists():
        keys = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    changed = False
    for d in [BRAIN, *devices]:
        if not keys.get(d):
            keys[d] = secrets.token_urlsafe(12)
            changed = True
    if changed:
        save_keys(keys, path)
    return keys


def save_keys(keys: dict[str, str], path: Path = KEYS_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Device keys for the MQTT broker. Secret: never commit this file.\n"
                    + yaml.safe_dump(keys, sort_keys=False), encoding="utf-8")


def acl_text(car_ids: list[str], stations: list[str]) -> str:
    lines = [f"user {BRAIN}", "topic readwrite factory/#", ""]
    for c in car_ids:
        lines += [f"user {c}", f"topic write factory/car/{c}/status", f"topic write factory/car/{c}/event",
                  f"topic read factory/car/{c}/cmd", ""]
    for s in stations:
        # a station recognizes its own delivery from the car's "done" event
        lines += [f"user {s}", f"topic write factory/station/{s}/stock", "topic read factory/car/+/event", ""]
    return "\n".join(lines)


# -- configuration -----------------------------------------------------------------

def build_config(port: int, cloud: dict, folder: Path, secure: bool = True) -> tuple[str, bool]:
    """Mosquitto configuration: listen on every network card, logins + ACL when
    `secure`, and a bridge to the cloud broker when it is configured."""
    lines = [
        f"listener {port} 0.0.0.0",
        "persistence false",
        "log_dest stdout",
        "log_type error",
        "log_type warning",
        "log_type notice",
        "log_type information",
    ]
    if secure:
        lines += ["allow_anonymous false", f"password_file {folder / 'passwords'}", f"acl_file {folder / 'acl'}"]
    else:
        lines += ["allow_anonymous true"]
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
            "topic factory/warehouse/refill in 1",
        ]
    return "\n".join(lines) + "\n", bridged


def default_folder(port: int = 1883) -> Path:
    """One folder per broker port, so two apps on different ports never share (or overwrite)
    each other's files, and a leftover broker can be told apart by its config path."""
    folder = Path(tempfile.gettempdir()) / ("capstone-mosquitto" if port == 1883 else f"capstone-mosquitto-{port}")
    folder.mkdir(exist_ok=True)
    return folder


class Broker:
    """Runs Mosquitto as a child process with device logins.

    `error` explains in plain words why it could not start (not installed, port
    busy because of the Mosquitto Windows service, ...)."""

    def __init__(self, port: int, cloud: dict, car_ids: list[str], stations: list[str],
                 keys_file: Path = KEYS_FILE, folder: Path | None = None):
        self.port, self.cloud = port, cloud
        self.car_ids, self.stations = car_ids, stations
        self.keys_file = keys_file
        self.folder = folder or default_folder(port)
        self.keys = load_keys([*car_ids, *stations], keys_file)
        self.proc: subprocess.Popen | None = None
        self.bridged = False
        self.error: str | None = None
        self.cleared: list[int] = []      # leftover brokers from an earlier run that start() stopped

    @property
    def devices(self) -> list[str]:
        return [*self.car_ids, *self.stations]

    def set_stations(self, ids: list[str]) -> None:
        """Use a new list of station nodes while running (the Setup page can add or remove
        stations). New stations get a key; existing keys stay. A removed station keeps its
        key in the file (so it works again if the station comes back) but can no longer log in."""
        ids = list(dict.fromkeys(ids))
        bad = [s for s in ids if not DEVICE_ID.fullmatch(s) or s == BRAIN or s in self.car_ids]
        if bad:
            raise ValueError(f"Not a valid station id: {', '.join(map(repr, bad))}")
        if ids == self.stations:
            return
        self.stations = ids
        self.keys = load_keys(self.devices, self.keys_file)
        if self.proc:
            self.reload()

    def _write_files(self) -> None:
        pw = self.folder / "passwords"
        allowed = [BRAIN, *self.devices]     # only current devices may log in
        pw.write_text("".join(f"{u}:{self.keys[u]}\n" for u in allowed if self.keys.get(u)), encoding="utf-8")
        tool = find_tool("mosquitto_passwd")
        if not tool:
            raise RuntimeError("mosquitto_passwd was not found next to Mosquitto")
        subprocess.run([tool, "-U", str(pw)], check=True, capture_output=True)   # hash the keys in place
        (self.folder / "acl").write_text(acl_text(self.car_ids, self.stations), encoding="utf-8")
        text, self.bridged = build_config(self.port, self.cloud, self.folder)
        (self.folder / "mosquitto.conf").write_text(text, encoding="utf-8")

    def start(self, timeout: float = 5.0) -> bool:
        exe = find_tool("mosquitto")
        if not exe:
            self.error = ("Mosquitto is not installed. Install it with: "
                          "winget install --id EclipseFoundation.Mosquitto -e")
            return False
        owned: list[int] = []
        if not port_free(self.port):
            # a broker left over from an earlier run (its app is gone): stop it and take the port
            orphans, owned = our_brokers(self.folder)
            for pid in orphans:
                stop_process(pid)
            end = time.monotonic() + 3
            while orphans and not port_free(self.port) and time.monotonic() < end:
                time.sleep(0.1)
            if orphans and port_free(self.port):
                self.cleared = orphans
        if not port_free(self.port):
            if owned:
                self.error = (f"Port {self.port} is used by another copy of the Carkaroo app that is still running. "
                              "Use that one, or stop it with Ctrl+C in its window, then start the app again.")
            else:
                self.error = (f"Port {self.port} is already used, probably by the Mosquitto Windows service, which "
                              "only listens on this laptop. In an administrator PowerShell run "
                              "'Stop-Service mosquitto' and 'Set-Service mosquitto -StartupType Manual', "
                              "then start the app again.")
            return False
        try:
            self._write_files()
        except (RuntimeError, subprocess.CalledProcessError, OSError) as exc:
            self.error = f"Could not prepare the broker files: {exc}"
            return False
        log = open(self.folder / "mosquitto.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen([exe, "-c", str(self.folder / "mosquitto.conf")], stdout=log,
                                     stderr=subprocess.STDOUT)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.proc.poll() is not None:
                self.error = f"Mosquitto stopped right away; see {self.folder / 'mosquitto.log'}"
                return False
            if not port_free(self.port):
                self.error = None
                return True
            time.sleep(0.1)
        self.error = "Mosquitto did not open its port in time"
        return False

    def new_key(self, device: str) -> str:
        """Give `device` a new key; the old one stops working at once."""
        if device not in self.devices:
            raise KeyError(device)
        self.keys[device] = secrets.token_urlsafe(12)
        save_keys(self.keys, self.keys_file)
        self.reload()
        return self.keys[device]

    def reload(self) -> None:
        """Make the running broker read the passwords and ACL again."""
        self._write_files()
        signal = find_tool("mosquitto_signal")
        if self.proc and signal:
            r = subprocess.run([signal, "-p", str(self.proc.pid), "config-reload"], capture_output=True)
            if r.returncode == 0:
                return
        self.stop()          # no reload signal: restart it (clients reconnect by themselves)
        self.start()

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
