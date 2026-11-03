import pytest

from agv_brain.factory_map import FactoryMap, Node, relative_turn
from agv_brain.models import CarParams


@pytest.fixture
def fmap():
    return FactoryMap.from_yaml()


def test_relative_turns():
    assert relative_turn("N", "N") == "STRAIGHT"
    assert relative_turn("N", "E") == "RIGHT"
    assert relative_turn("N", "W") == "LEFT"
    assert relative_turn("S", "E") == "LEFT"   # facing south, east is on the left
    assert relative_turn("E", "W") == "UTURN"


def test_route_from_dock_to_rack(fmap):
    r = fmap.route("HOME", "W-B", "N")
    assert r.path == ("HOME", "J1", "J2", "W-B")
    assert r.commands == ("STRAIGHT", "RIGHT", "LEFT", "STOP")
    assert r.distance_cm == 200


def test_leaving_a_dead_end_needs_a_uturn(fmap):
    r = fmap.route("W-A", "S1", fmap.arrival_heading("W-A"))
    assert r.commands[0] == "UTURN"
    assert r.commands[-1] == "STOP"
    assert len(r.commands) == len(r.path)


def test_turns_cost_time():
    car = CarParams(speed_cm_s=10, turn_s=5, uturn_s=7)
    fmap = FactoryMap.from_yaml(car=car)
    r = fmap.route("HOME", "W-B", "N")   # 200 cm, one right + one left
    assert r.time_s == pytest.approx(200 / 10 + 2 * 5)


def test_blocked_line_reroutes(fmap):
    direct = fmap.route("W-B", "S3", "N")
    assert "J5" in direct.path and direct.path[1:3] == ("J2", "J5")
    fmap.block_edge("J2", "J5")
    around = fmap.route("W-B", "S3", "N")
    assert ("J2", "J5") not in zip(around.path, around.path[1:])
    assert around.time_s > direct.time_s
    fmap.unblock_edge("J2", "J5")
    assert fmap.route("W-B", "S3", "N") == direct


def test_reroute_after_obstacle(fmap):
    # car drove W-B > J2 > J5 heading to S3 and the ultrasonic sensor sees an obstacle on J2-J5
    r = fmap.reroute_from_edge("J2", "J5", "S3")
    assert r.commands[0] == "UTURN"
    assert r.path[:2] == ("J5", "J2")          # back to J2 (the path starts on the blocked line)
    assert r.path[-1] == "S3" and r.commands[-1] == "STOP"
    assert len(r.commands) == len(r.path)
    assert frozenset(("J2", "J5")) in fmap.blocked


def test_unreachable_raises(fmap):
    fmap.block_edge("J5", "S3")
    with pytest.raises(ValueError):
        fmap.route("HOME", "S3", "N")


def test_diagonal_edge_rejected():
    nodes = {"a": Node("a", 0, 0, "junction"), "b": Node("b", 10, 10, "junction")}
    with pytest.raises(ValueError):
        FactoryMap(nodes, [("a", "b", None)])
