"""The website's login page, Start and Stop, and the checks on what the pages send."""

import json
import socket
import time
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from agv_brain import factories
from agv_brain.app import App
from agv_brain.broker import BRAIN
from agv_brain.bus import MemoryBus
from agv_brain.dashboard.server import check_refill, check_request, check_sim


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(autouse=True)
def factories_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(factories, "FACTORIES_DIR", tmp_path / "factories")


@pytest.fixture
def web():
    fake_broker = SimpleNamespace(keys={BRAIN: "k0", "AGV-1": "k1"}, port=1883, bridged=False, stop=lambda: None)
    port = free_port()
    app = App(MemoryBus(), fake_broker, port=port, state_file=None, log=False)
    base = f"http://127.0.0.1:{port}"

    def post(path, body, headers=None):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                     headers=headers or {"Content-Type": "application/json"})
        try:
            r = urllib.request.urlopen(req)
            return r.status, json.loads(r.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"{}")

    def snap():
        return json.loads(urllib.request.urlopen(base + "/api/snapshot").read())

    yield SimpleNamespace(app=app, post=post, snap=snap, base=base)
    app.stop()


# -- factories ---------------------------------------------------------------------

def test_names_are_checked():
    for bad in ["", "   ", None, 7, "x" * 41, "!!!"]:
        with pytest.raises(ValueError):
            factories.clean_name(bad)
    assert factories.clean_name("  Exhibit   Factory ") == "Exhibit Factory"


def test_login_makes_a_factory_once():
    f = factories.open_or_create("Exhibit Factory")
    assert f["id"] == "exhibit-factory" and f["mode"] == "sim" and f["track"] == "sample"
    assert factories.materials_path(f["id"]).exists()          # a copy of the sample factory
    f["mode"] = "real_car"
    factories.save(f)
    assert factories.open_or_create("exhibit factory")["mode"] == "real_car"   # same name: same factory
    assert [x["name"] for x in factories.list_factories()] == ["Exhibit Factory"]
    with pytest.raises(ValueError):
        factories.folder("../config")


# -- the app is idle until Start ---------------------------------------------------

def test_idle_until_start_then_stop(web):
    d = web.snap()
    assert d["running"] is False and d["factory"] is None and d["state"] is None
    assert web.post("/api/run", {})[0] == 409                    # log in first
    assert web.post("/api/request", {"material": "A", "station": "S1"})[0] == 409
    code, body = web.post("/api/login", {"name": "Exhibit Factory"})
    assert code == 200 and body["factory"] == {"id": "exhibit-factory", "name": "Exhibit Factory"}
    assert web.snap()["running"] is False
    assert web.post("/api/run", {"mode": "sim", "speed": "fast"}) == \
        (400, {"error": "The speed must be a number from 1 to 20."})
    assert web.post("/api/run", {"mode": "sim", "speed": 10})[0] == 200
    deadline = time.time() + 10
    while web.snap()["state"] is None and time.time() < deadline:
        time.sleep(0.1)
    d = web.snap()
    assert d["running"] is True and d["state"] is not None
    assert factories.load("exhibit-factory")["speed"] == 10       # remembered for this factory
    assert web.post("/api/stop", {})[0] == 200
    d = web.snap()
    assert d["running"] is False and d["state"] is None and web.app.session is None
    assert web.post("/api/logout", {})[0] == 200
    assert web.snap()["factory"] is None


def test_new_posts_keep_the_protections(web):
    for path in ["/api/login", "/api/logout", "/api/run", "/api/stop"]:
        assert web.post(path, {}, {"Content-Type": "text/plain"})[0] == 415
        assert web.post(path, {}, {"Content-Type": "application/json", "Origin": "http://evil.example"})[0] == 403
    web.app.dash.httpd.RequestHandlerClass.local = property(lambda self: False)   # as if from a phone
    assert web.post("/api/login", {"name": "Phone Factory"})[0] == 403
    assert web.post("/api/run", {})[0] == 403
    assert factories.list_factories() == []


# -- what the pages send is checked -------------------------------------------------

LAYOUT = {"stations": {"S1": {"name": "Assembly line 1", "materials": ["A", "B"]}},
          "materials": {"A": {}, "B": {}}, "edges": [["J1", "J2"], ["J2", "S1"]]}
STATE = {"requests": [{"station": "S1", "material": "B"}],
         "stations": {"S1": {"materials": {"A": {"capacity": 60}, "B": {"capacity": 40}}}}}


def test_requests_are_checked():
    assert check_request({"station": "S1", "material": "A"}, LAYOUT, STATE) == {"material": "A", "station": "S1"}
    with pytest.raises(ValueError, match="does not use"):
        check_request({"station": "S1", "material": "C"}, LAYOUT, STATE)
    with pytest.raises(ValueError, match="already asked for"):
        check_request({"station": "S1", "material": "B"}, LAYOUT, STATE)
    with pytest.raises(ValueError):
        check_request({"station": "S9", "material": "A"}, LAYOUT, STATE)


def test_refills_and_sim_controls_are_checked():
    assert check_refill({"material": "A"}, LAYOUT) == {"material": "A"}
    for bad in [{"material": "Z"}, {"material": "A", "units": -500}, {"material": "A", "units": "lots"}]:
        with pytest.raises(ValueError):
            check_refill(bad, LAYOUT)
    assert check_sim({"cmd": "set_stock", "station": "S1", "material": "A", "stock": 60}, LAYOUT, STATE)["stock"] == 60
    assert check_sim({"cmd": "obstacle", "edge": ["J2", "J1"]}, LAYOUT, STATE)["duration_s"] == 60
    for bad in [{"cmd": "set_stock", "station": "S1", "material": "A", "stock": 99999},
                {"cmd": "set_stock", "station": "S1", "material": "A", "stock": -1},
                {"cmd": "set_battery", "value": -40}, {"cmd": "set_battery", "value": True},
                {"cmd": "obstacle", "edge": ["X", "Y"]}, {"cmd": "obstacle", "edge": ["J1", "J2"], "duration_s": 1e9},
                {"cmd": "explode"}]:
        with pytest.raises(ValueError):
            check_sim(bad, LAYOUT, STATE)
