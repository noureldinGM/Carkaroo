"""A broker left over from an earlier run is found and told apart from a running app's broker,
and a second copy of the website is noticed before it shares the port."""

import socket
from pathlib import Path

from agv_brain.broker import default_folder, is_carkaroo_app, our_brokers, port_in_use

FOLDER = Path("Temp") / "capstone-mosquitto"            # paths built like the app builds them, on any OS
CONF = '"C:\\Program Files\\mosquitto\\mosquitto.exe" -c ' + str(FOLDER / "mosquitto.conf")
APP = r'"C:\Capstone AVG\.venv\Scripts\python.exe" scripts\run_app.py'


def test_orphan_and_owned_brokers_are_told_apart():
    procs = [
        {"pid": 10, "ppid": 1, "cmd": APP},                     # a running app ...
        {"pid": 11, "ppid": 10, "cmd": CONF},                   # ... and its broker
        {"pid": 21, "ppid": 20, "cmd": CONF},                   # its app (20) is gone: a leftover
        {"pid": 31, "ppid": 30, "cmd": CONF},                   # pid 30 was reused by something else
        {"pid": 30, "ppid": 1, "cmd": "notepad.exe"},
        {"pid": 41, "ppid": 1, "cmd": r'"C:\Program Files\mosquitto\mosquitto.exe" -c other.conf'},  # not ours
        {"pid": 51, "ppid": 1, "cmd": "mosquitto -c " + str(FOLDER.parent / (FOLDER.name + "-1887") / "mosquitto.conf")},  # another port
    ]
    orphans, owned = our_brokers(FOLDER, procs)
    assert sorted(orphans) == [21, 31]
    assert owned == [11]


def test_each_broker_port_has_its_own_folder():
    assert default_folder(1883).name == "capstone-mosquitto"      # the same as before, so old leftovers are found
    assert default_folder(1887).name == "capstone-mosquitto-1887"


def test_carkaroo_apps_are_recognised():
    assert is_carkaroo_app(APP)
    assert is_carkaroo_app("python -m agv_brain.app")
    assert not is_carkaroo_app("notepad.exe run_app.py")


def test_port_in_use_sees_a_listening_server():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        port = s.getsockname()[1]
        assert port_in_use(port)
    assert not port_in_use(port)
