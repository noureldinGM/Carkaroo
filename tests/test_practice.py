"""The Carkaroo Simulator: pretend devices that log in with their own keys, like the real ones."""

import json
import socket
import time
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from agv_brain import factories
from agv_brain import protocol as P
from agv_brain.broker import BRAIN, Broker, find_tool, port_free
from agv_brain.bus import MemoryBus, MqttBus
from agv_brain.practice import Practice, parse_paste
from agv_brain.practice_server import PracticeServer


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(autouse=True)
def a_factory(tmp_path, monkeypatch):
    monkeypatch.setattr(factories, "FACTORIES_DIR", tmp_path / "factories")
    return factories.open_or_create("Exhibit Factory")["id"]


class FakeBroker:
    """Logins checked against keys; every device shares one memory bus (like one broker)."""

    def __init__(self, keys):
        self.keys, self.bus, self.logins = keys, MemoryBus(), []

    def __call__(self, host, port, client_id="", username=None, password=None, connect_timeout=5):
        if host != "localhost":
            raise ConnectionError(f"no MQTT broker answered at {host}:{port}")
        if self.keys.get(username) != password:
            raise ConnectionError(f"the MQTT broker at {host}:{port} refused the login (Not authorized)")
        self.logins.append(username)
        return SimpleNamespace(publish=self.bus.publish, subscribe=self.bus.subscribe,
                               unsubscribe=self.bus.unsubscribe, close=lambda: None)


def test_paste_from_the_website():
    p = parse_paste("# Carkaroo devices\nbroker: localhost\nport: 1886\nAGV-1: k1\nS1: k2\n")
    assert p == {"host": "localhost", "port": "1886", "keys": {"AGV-1": "k1", "S1": "k2"}}
    with pytest.raises(ValueError):
        parse_paste("hello")


def test_devices_need_their_keys(a_factory):
    broker = FakeBroker({"AGV-1": "k1", "S1": "k2"})
    p = Practice(connect=broker)
    with pytest.raises(ValueError):
        p.connect("S1", "k2")                               # choose a factory first
    p.choose(a_factory)
    assert set(p.devices) == {"AGV-1", "S1", "S2", "S3", "S4"}
    assert p.connect("S1", "wrong") == "error" and "wrong key" in p.devices["S1"]["error"]
    assert p.connect("S1", "k2", host="elsewhere") == "error" and "No broker" in p.devices["S1"]["error"]
    with pytest.raises(ValueError):
        p.connect("S1", "k2", host="bad host/")
    stock = []
    broker.bus.subscribe(P.station_stock("S1"), lambda t, m: stock.append(m))
    assert p.connect("S1", "k2", host="localhost") == "on" and broker.logins == ["S1"]
    broker.bus.flush()
    assert stock                                            # S1 reports its stock with its own login
    with pytest.raises(ValueError, match="Connect AGV-1"):
        p.control({"cmd": "set_battery", "value": 15})      # the car is not connected
    with pytest.raises(ValueError):
        p.control({"cmd": "set_stock", "station": "S1", "material": "A", "stock": 9999})
    controls = []
    broker.bus.subscribe(P.SIM_CONTROL, lambda t, m: controls.append(m))
    stock.clear()
    p.control({"cmd": "set_stock", "station": "S1", "material": "A", "stock": 3})
    time.sleep(0.3)
    broker.bus.flush()
    assert controls == []                                   # the play controls never go through the broker
    assert {"material": "A", "stock": 3}.items() <= stock[-1].items()
    p.disconnect("S1")
    assert p.devices["S1"]["state"] == "off"
    p.stop()


def test_simulator_website_protections():
    srv = PracticeServer(Practice(connect=FakeBroker({})), port=free_port())
    base = srv.url.replace("localhost", "127.0.0.1")

    def post(path, headers, data=b"{}"):
        try:
            return urllib.request.urlopen(urllib.request.Request(base + path, data=data, method="POST",
                                                                 headers=headers)).status
        except urllib.error.HTTPError as exc:
            return exc.code
    try:
        state = json.loads(urllib.request.urlopen(base + "/api/state").read())
        assert state["factory"] is None and [f["name"] for f in state["factories"]] == ["Exhibit Factory"]
        assert post("/api/choose", {"Content-Type": "text/plain"}) == 415
        assert post("/api/choose", {"Content-Type": "application/json", "Origin": "http://evil.example"}) == 403
        assert post("/api/choose", {"Content-Type": "application/json", "Host": "evil.example:8060"}) == 421
        assert post("/api/choose", {"Content-Type": "application/json"}, b'{"factory": "exhibit-factory"}') == 200
        page = urllib.request.urlopen(base)
        assert b"Carkaroo Simulator" in page.read() and "frame-ancestors 'none'" in page.headers["Content-Security-Policy"]
        assert b"--signal" in urllib.request.urlopen(base + "/design/tokens.css").read()
        srv.httpd.RequestHandlerClass.local = property(lambda self: False)        # as if from a phone
        assert post("/api/connect", {"Content-Type": "application/json"}, b'{"device": "S1", "key": "k"}') == 403
        assert "key" not in json.dumps(json.loads(urllib.request.urlopen(base + "/api/state").read())["devices"])
    finally:
        srv.stop()


@pytest.mark.skipif(not find_tool("mosquitto"), reason="Mosquitto is not installed")
def test_simulator_logs_in_to_the_real_broker(tmp_path, a_factory):
    port = free_port()
    assert port_free(port)
    b = Broker(port, {}, ["AGV-1"], ["S1", "S2", "S3", "S4"], keys_file=tmp_path / "keys.yaml", folder=tmp_path)
    assert b.start(), b.error
    brain = None
    p = Practice()
    try:
        brain = MqttBus("localhost", port, username=BRAIN, password=b.keys[BRAIN])
        seen = []
        brain.subscribe(P.station_stock("+"), lambda t, m: seen.append(t.split("/")[2]))
        p.choose(a_factory)
        assert p.connect("S2", "not-the-key", port=port) == "error"
        assert p.connect("S2", b.keys["S2"], port=port) == "on"
        deadline = time.time() + 5
        while "S2" not in seen and time.time() < deadline:
            time.sleep(0.1)
        assert "S2" in seen                                 # the AI hears the pretend station
    finally:
        p.stop()
        if brain:
            brain.close()
        b.stop()
