"""Tests against a real MQTT broker on localhost:1883 (Mosquitto).

Skipped when no broker is running, so the rest of the suite works anywhere.
"""

import socket
import time
import uuid

import pytest

from agv_brain.bus import MqttBus, filter_covers


def _broker_up() -> bool:
    try:
        with socket.create_connection(("localhost", 1883), timeout=0.5):
            return True
    except OSError:
        return False


needs_broker = pytest.mark.skipif(not _broker_up(), reason="no MQTT broker on localhost:1883")


def test_filter_covers():
    assert filter_covers("factory/car/+/event", "factory/car/AGV-1/event")
    assert filter_covers("factory/#", "factory/car/+/event")
    assert not filter_covers("factory/car/AGV-1/event", "factory/car/+/event")
    assert not filter_covers("factory/car/+/event", "factory/car/#")
    assert filter_covers("a/b", "a/b")


@needs_broker
def test_overlapping_subscriptions_deliver_once():
    root = f"test-{uuid.uuid4().hex[:8]}"
    sub = MqttBus(client_id=f"{root}-sub")
    pub = MqttBus(client_id=f"{root}-pub")
    got_exact, got_wild = [], []
    sub.subscribe(f"{root}/car/AGV-1/event", lambda t, p: got_exact.append(p))
    sub.subscribe(f"{root}/car/+/event", lambda t, p: got_wild.append(p))
    time.sleep(0.5)
    for i in range(5):
        pub.publish(f"{root}/car/AGV-1/event", {"i": i}, qos=1)
    time.sleep(1.0)
    sub.close()
    pub.close()
    assert [p["i"] for p in got_exact] == [0, 1, 2, 3, 4]
    assert [p["i"] for p in got_wild] == [0, 1, 2, 3, 4]


@needs_broker
def test_factory_over_mqtt_counts_each_box_once():
    from agv_brain import protocol
    from agv_brain.factory_sim import FactorySim

    root = f"test-{uuid.uuid4().hex[:8]}"
    protocol.set_prefix(root)  # its own topics: a factory running on the same broker is not disturbed
    bus = MqttBus(client_id=f"{root}-sim")
    sim = FactorySim(policy="ml", speed=60, bus=bus, log=False)
    try:
        end = time.monotonic() + 40
        while sim.controller.stats["deliveries"] < 3 and time.monotonic() < end:
            time.sleep(0.1)
        c = sim.controller
        assert c.stats["deliveries"] >= 3
        pickups = sum(e["type"] == "pickup" for e in c.events)
        delivered = sum(e["type"] == "delivered" for e in c.events)
        assert pickups <= delivered + 1          # never two pick-ups for one delivery
        for st in sim.stations:                  # boxes received = boxes delivered by the car
            for m, qty in st.received.items():
                box = sim.controller.ctx.settings.materials[m].delivery_qty
                assert qty % box == 0
    finally:
        sim.stop()
        bus.close()
        protocol.set_prefix("factory")


def test_set_stations_adds_keys_and_limits_logins(tmp_path, monkeypatch):
    from agv_brain import broker as B

    keys_file = tmp_path / "devices.local.yaml"
    b = B.Broker(1883, {}, ["AGV-1"], ["S1", "S2"], keys_file=keys_file, folder=tmp_path)
    old = dict(b.keys)
    b.set_stations(["S1", "S2", "S5"])
    assert b.stations == ["S1", "S2", "S5"]
    assert b.keys["S5"] and all(b.keys[k] == v for k, v in old.items())   # existing keys kept
    assert "user S5" in B.acl_text(b.car_ids, b.stations)

    b.set_stations(["S1", "S5"])          # S2 removed: its key stays in the file, but it cannot log in
    assert "S2" in B.load_keys([], keys_file)
    monkeypatch.setattr(B, "find_tool", lambda name: "mosquitto_passwd")
    monkeypatch.setattr(B.subprocess, "run", lambda *a, **k: None)
    b._write_files()
    users = [line.split(":")[0] for line in (tmp_path / "passwords").read_text().splitlines()]
    assert users == ["brain", "AGV-1", "S1", "S5"]
    assert "user S2" not in (tmp_path / "acl").read_text()

    for bad in ("S9\ntopic readwrite #", "a/b", "brain", "AGV-1", ""):
        with pytest.raises(ValueError):
            b.set_stations(["S1", bad])
    assert b.stations == ["S1", "S5"]
