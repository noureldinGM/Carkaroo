import json
import socket
import time
import urllib.error
import urllib.request

import pytest

from agv_brain import protocol as P
from agv_brain.bus import Clock, MemoryBus, topic_matches
from agv_brain.factory_sim import FactorySim
from agv_brain.models import CarState
from agv_brain.sim_devices import SimulatedCar
from agv_brain.simulator import load_context


def wait_until(cond, timeout=20.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_topic_matching():
    assert topic_matches("factory/station/+/stock", "factory/station/S3/stock")
    assert topic_matches("factory/#", "factory/car/AGV-1/event")
    assert not topic_matches("factory/station/+/stock", "factory/station/S3/stock/x")
    assert not topic_matches("factory/car/+/cmd", "factory/car/AGV-1/event")


def test_memory_bus_delivers_and_retains():
    bus = MemoryBus()
    got = []
    bus.publish("a/b", {"x": 1}, retain=True)
    bus.subscribe("a/+", lambda t, p: got.append((t, p)))
    bus.publish("a/c", {"x": 2})
    bus.flush()
    assert ("a/b", {"x": 1}) in got and ("a/c", {"x": 2}) in got


def test_simulated_car_follows_junction_commands():
    ctx = load_context()
    bus, clock = MemoryBus(), Clock(300)
    car = SimulatedCar(bus, clock, ctx.fmap, ctx.settings, start=CarState("HOME", "N", 90), speed_noise=0)
    events = []
    bus.subscribe(P.car_event("AGV-1"), lambda t, p: events.append(p))
    to_rack = ctx.fmap.route("HOME", "W-B", "N")
    to_station = ctx.fmap.route("W-B", "S3", to_rack.end_heading)
    job = type("J", (), {"material": "B", "rack": "W-B", "station": "S3"})
    bus.publish(P.car_cmd("AGV-1"), P.task_message(1, job, to_rack, to_station))
    assert wait_until(lambda: any(e.get("action") == "LOWER" for e in events))
    assert car.node == "S3"                                    # it really ended up at S3
    nodes = [e for e in events if e["type"] == "node"]
    assert len(nodes) == (len(to_rack.path) - 1) + (len(to_station.path) - 1)
    assert not [e for e in events if e["type"] == "error"]
    car.stop()


@pytest.fixture
def sim():
    s = FactorySim(policy="ml", speed=150, log=False)
    yield s
    s.stop()


def test_factory_runs_and_delivers(sim):
    assert wait_until(lambda: sim.controller.stats["deliveries"] >= 3, timeout=30)
    snap = sim.controller.snapshot()
    assert snap["car"]["online"]
    assert not [a for a in snap["alerts"] if "error" in a["text"].lower()]


def test_obstacle_is_rerouted(sim):
    sim.control({"cmd": "obstacle", "edge": ["J2", "J5"], "duration_s": 5000})
    sim.control({"cmd": "set_stock", "station": "S3", "material": "B", "stock": 1})
    assert wait_until(lambda: sim.controller.stats["reroutes"] >= 1, timeout=40)
    assert wait_until(lambda: any("to S3" in e["text"] for e in sim.controller.events
                                  if e["type"] == "delivered"), timeout=40)


def test_obstacle_with_no_way_around_waits_then_continues(sim):
    # W-B is a line end: an obstacle on its only line cannot be driven around
    sim.control({"cmd": "obstacle", "edge": ["J2", "W-B"], "duration_s": 5000})
    sim.control({"cmd": "set_stock", "station": "S3", "material": "B", "stock": 1})
    c = sim.controller
    assert wait_until(lambda: any("No way around" in a["text"] for a in c.alerts), timeout=40)
    assert frozenset(("J2", "W-B")) not in c.ctx.fmap.blocked      # not left blocked by mistake
    assert not [a for a in c.alerts if "cannot be reached" in a["text"]]
    sim.control({"cmd": "clear_obstacles"})
    assert wait_until(lambda: any(e["type"] == "clear" for e in c.events), timeout=40)
    assert wait_until(lambda: any("B to S3" in e["text"] for e in c.events if e["type"] == "delivered"), timeout=40)


def test_empty_warehouse_waits_until_refilled(sim):
    c = sim.controller
    with c._lock:
        c.state.warehouse["B"] = 3          # less than one box of B
    sim.control({"cmd": "set_stock", "station": "S3", "material": "B", "stock": 1})
    assert wait_until(lambda: any("out of B" in a["text"] for a in c.alerts), timeout=30)
    assert not any("B to S3" in e["text"] for e in c.events if e["type"] == "delivered")
    sim.bus.publish(P.WAREHOUSE_REFILL, {"material": "B"}, qos=1)
    full = c.ctx.settings.materials["B"].warehouse_stock
    assert wait_until(lambda: any(e["type"] == "refill" for e in c.events), timeout=10)
    assert wait_until(lambda: any("B to S3" in e["text"] for e in c.events if e["type"] == "delivered"), timeout=40)
    assert c.state.warehouse["B"] == full - c.ctx.settings.materials["B"].delivery_qty


def test_low_battery_goes_to_charge(sim):
    assert wait_until(lambda: sim.controller.stats["deliveries"] >= 1, timeout=30)
    sim.control({"cmd": "set_battery", "value": 10})
    assert wait_until(lambda: sim.controller.stats["charges"] >= 1, timeout=30)
    assert wait_until(lambda: sim.car.battery > 50, timeout=30)


def test_dashboard_serves_state_and_requests():
    from agv_brain.dashboard import DashboardServer
    bus = MemoryBus()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    dash = DashboardServer(bus, load_context(), port=port, sim_controls=False)
    got = []
    bus.subscribe(P.AI_REQUEST, lambda t, p: got.append(p))
    bus.publish(P.AI_STATE, {"ts": 1.0, "hello": "world"}, retain=True)
    bus.flush()
    base = f"http://127.0.0.1:{port}"
    snap = json.loads(urllib.request.urlopen(f"{base}/api/snapshot").read())
    assert snap["state"]["hello"] == "world"
    assert {n["id"] for n in snap["layout"]["nodes"]} >= {"HOME", "S1", "W-A", "J1"}
    assert b"Carkaroo" in urllib.request.urlopen(base).read()
    # the design system is served next to the website, and nothing outside design/ leaks through
    assert b"--signal" in urllib.request.urlopen(f"{base}/design/tokens.css").read()
    assert b"Design system" in urllib.request.urlopen(f"{base}/design").read()
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(f"{base}/design/../README.md")
    req = urllib.request.Request(f"{base}/api/request", data=json.dumps({"material": "B", "station": "S3"}).encode(),
                                 method="POST", headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req).read()
    bus.flush()
    assert got == [{"material": "B", "station": "S3"}]
    refills = []
    bus.subscribe(P.WAREHOUSE_REFILL, lambda t, p: refills.append(p))
    urllib.request.urlopen(urllib.request.Request(f"{base}/api/refill", data=b'{"material": "A"}',
                                                  method="POST", headers={"Content-Type": "application/json"})).read()
    bus.flush()
    assert refills == [{"material": "A"}]
    sim_req = urllib.request.Request(f"{base}/api/sim", data=b"{}", method="POST", headers={"Content-Type": "application/json"})
    with pytest.raises(urllib.error.HTTPError):  # simulation controls are off
        urllib.request.urlopen(sim_req)

    # security: other websites cannot send commands, DNS rebinding is refused, headers are set
    def post(headers, data=b'{"material": "A"}'):
        try:
            return urllib.request.urlopen(urllib.request.Request(f"{base}/api/refill", data=data, method="POST",
                                                                 headers=headers)).status
        except urllib.error.HTTPError as exc:
            return exc.code
    assert post({"Content-Type": "text/plain"}) == 415                       # a form or no-cors fetch
    assert post({"Content-Type": "application/json", "Origin": "http://evil.example"}) == 403
    assert post({"Content-Type": "application/json", "Host": "evil.example:8050"}) == 421
    assert post({"Content-Type": "application/json"}, b"[1]") == 400
    assert post({"Content-Type": "application/json", "Origin": base}) == 200  # the page itself
    page = urllib.request.urlopen(base)
    assert "frame-ancestors 'none'" in page.headers["Content-Security-Policy"]
    assert "'sha256-" in page.headers["Content-Security-Policy"]             # the inline theme script
    assert page.headers["X-Content-Type-Options"] == "nosniff"
    with pytest.raises(urllib.error.HTTPError):                              # scripts are not served
        urllib.request.urlopen(f"{base}/design/print/make_print_assets.py")
    dash.stop()
