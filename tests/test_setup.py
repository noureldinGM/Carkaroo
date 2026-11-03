"""Setup page back end: tracks, mode switching, device keys."""

import copy
import socket
import time
from types import SimpleNamespace

import pytest

from agv_brain import protocol as P
from agv_brain import tracks
from agv_brain.app import App
from agv_brain.broker import BRAIN, Broker, find_tool, port_free
from agv_brain.bus import MemoryBus, MqttBus, ScopedBus
from agv_brain.models import load_settings


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# -- tracks ------------------------------------------------------------------------

@pytest.fixture
def sample():
    return tracks.load_raw("sample")


def test_sample_track_is_valid(sample):
    assert tracks.validate(sample, load_settings()) == {"errors": [], "warnings": []}


def test_track_problems_are_explained(sample):
    s = load_settings()
    bad = copy.deepcopy(sample)
    del bad["nodes"]["W-C"]
    bad["edges"] = [e for e in bad["edges"] if "W-C" not in e]
    assert any("Rack W-C for C" in p for p in tracks.validate(bad, s)["errors"])

    bent = copy.deepcopy(sample)
    bent["nodes"]["S4"]["x"] = 320          # J7-S4 is no longer straight
    assert any("not straight" in p for p in tracks.validate(bent, s)["errors"])

    cut = copy.deepcopy(sample)
    cut["edges"] = [e for e in cut["edges"] if e != ["J7", "S4"]]
    errors = tracks.validate(cut, s)["errors"]
    assert any("S4 is a station" in p for p in errors)

    over = copy.deepcopy(sample)
    over["nodes"]["X"] = {"x": 50, "y": 50, "type": "junction"}   # sits on line J1-J2
    assert any("passes over X" in p for p in tracks.validate(over, s)["errors"])


def test_unreachable_station(sample):
    s = load_settings()
    t = copy.deepcopy(sample)
    # move S4 onto its own island: a separate line with a junction-free stub
    t["nodes"]["S4"] = {"x": 600, "y": 300, "type": "station"}
    t["nodes"]["Z"] = {"x": 600, "y": 250, "type": "dock"}
    t["edges"] = [e for e in t["edges"] if e != ["J7", "S4"]] + [["Z", "S4"]]
    t["nodes"]["J7"]["type"] = "junction"
    res = tracks.validate(t, s)
    assert res["errors"]   # J7 now has 2 lines -> fine, but S4 cannot be reached / extra dock
    assert any("S4" in p for p in res["errors"])


def test_save_and_load_track(sample, tmp_path, monkeypatch):
    monkeypatch.setattr(tracks, "TRACKS_DIR", tmp_path)
    tid = tracks.save("My Track 1", sample)
    assert tid == "my-track-1"
    assert {t["id"] for t in tracks.list_tracks()} == {"sample", "my-track-1"}
    assert tracks.validate(tracks.load_raw(tid), load_settings())["errors"] == []


# -- buses and sessions --------------------------------------------------------------

def test_scoped_bus_drops_its_handlers():
    bus = MemoryBus()
    scope = ScopedBus(bus)
    got = []
    scope.subscribe("a/#", lambda t, p: got.append(p))
    bus.publish("a/b", {"n": 1})
    bus.flush()
    scope.close()
    bus.publish("a/b", {"n": 2})
    scope.publish("a/b", {"n": 3})      # a closed scope publishes nothing
    bus.flush()
    assert got == [{"n": 1}]


@pytest.fixture
def app():
    fake_broker = SimpleNamespace(keys={BRAIN: "k0", "AGV-1": "k1", "S1": "k2"}, port=1883, bridged=False,
                                  stop=lambda: None)
    a = App(MemoryBus(), fake_broker, port=free_port(), state_file=None, log=False)
    yield a
    a.stop()


def test_switch_to_real_car_stops_the_simulated_car(app):
    assert app.mode == "sim" and app.session.car is not None
    app.switch("real_car")
    assert app.session.car is None and app.session.stations      # stations stay simulated
    assert app.session.clock.scale == 1.0
    time.sleep(1.5)
    devices = {d["id"]: d for d in app.devices()}
    assert devices["AGV-1"]["simulated"] is False
    assert app.session.controller.snapshot()["car"]["online"] is False   # waits for the real car
    app.switch("sim")
    assert app.session.car is not None


def test_setup_hides_keys_from_other_devices(app):
    assert all("key" not in d for d in app.setup(local=False)["devices"])
    assert {d["id"]: d.get("key") for d in app.setup(local=True)["devices"]}["AGV-1"] == "k1"


def test_real_modes_need_a_broker():
    a = App(MemoryBus(), None, port=free_port(), state_file=None, log=False, broker_error="no broker here")
    try:
        with pytest.raises(ValueError, match="needs the MQTT broker"):
            a.switch("real")
        assert a.mode == "sim"
    finally:
        a.stop()


# -- the secure broker ----------------------------------------------------------------

@pytest.mark.skipif(not find_tool("mosquitto"), reason="Mosquitto is not installed")
def test_broker_checks_device_keys_and_topics(tmp_path):
    port = free_port()
    assert port_free(port)
    b = Broker(port, {}, ["AGV-1"], ["S1"], keys_file=tmp_path / "keys.yaml", folder=tmp_path)
    assert b.start(), b.error
    try:
        conf = (tmp_path / "mosquitto.conf").read_text()
        assert "allow_anonymous false" in conf and "password_file" in conf and "acl_file" in conf
        with pytest.raises(ConnectionError):
            MqttBus("localhost", port, connect_timeout=2)                      # no key
        brain = MqttBus("localhost", port, username=BRAIN, password=b.keys[BRAIN])
        got = []
        brain.subscribe(P.car_status("AGV-1"), lambda t, p: got.append(p))
        car = MqttBus("localhost", port, username="AGV-1", password=b.keys["AGV-1"])
        station = MqttBus("localhost", port, username="S1", password=b.keys["S1"])
        time.sleep(0.3)
        car.publish(P.car_status("AGV-1"), {"state": "IDLE", "from": "car"}, qos=1)
        station.publish(P.car_status("AGV-1"), {"state": "IDLE", "from": "station"}, qos=1)  # not its topic
        time.sleep(0.8)
        assert [p["from"] for p in got] == ["car"]
        for bus in (car, station):
            bus.close()

        old = b.keys["AGV-1"]
        b.new_key("AGV-1")
        time.sleep(0.5)
        with pytest.raises(ConnectionError):
            MqttBus("localhost", port, username="AGV-1", password=old, connect_timeout=2)
        MqttBus("localhost", port, username="AGV-1", password=b.keys["AGV-1"]).close()
        brain.close()
    finally:
        b.stop()
