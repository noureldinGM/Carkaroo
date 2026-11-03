"""Factory track as a graph, plus routing that the line-follower car can execute.

The car only knows how to follow a line and what to do at the next node it
detects, so a route is turned into one command per node:

    commands[0]      how to leave the start node (STRAIGHT / LEFT / RIGHT / UTURN)
    commands[1..-2]  what to do at each node passed on the way
    commands[-1]     STOP at the goal

Routing is a Dijkstra search over (node, heading) states, so the time cost of
turning and turning around is counted, not just the distance.
"""

from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass
from pathlib import Path

import yaml

from agv_brain.models import CONFIG_DIR, CarParams

HEADINGS = ("N", "E", "S", "W")  # clockwise; y grows downward so N is "up"
_VECTORS = {(0, -1): "N", (1, 0): "E", (0, 1): "S", (-1, 0): "W"}
_TURNS = ("STRAIGHT", "RIGHT", "UTURN", "LEFT")
NODE_TYPES = ("junction", "rack", "station", "dock")


def relative_turn(current: str, new: str) -> str:
    """Command that changes the car's heading from `current` to `new`."""
    return _TURNS[(HEADINGS.index(new) - HEADINGS.index(current)) % 4]


def opposite(heading: str) -> str:
    return HEADINGS[(HEADINGS.index(heading) + 2) % 4]


@dataclass(frozen=True)
class Node:
    id: str
    x: float
    y: float
    type: str


@dataclass(frozen=True)
class Route:
    path: tuple[str, ...]
    commands: tuple[str, ...]
    distance_cm: float
    time_s: float
    end_heading: str

    @property
    def turns(self) -> int:
        return sum(c in ("LEFT", "RIGHT", "UTURN") for c in self.commands)


class FactoryMap:
    def __init__(self, nodes: dict[str, Node], edges: list[tuple[str, str, float]],
                 car: CarParams | None = None):
        self.nodes = nodes
        self.car = car or CarParams()
        self._adj: dict[str, dict[str, tuple[str, float]]] = {n: {} for n in nodes}
        self._cache: dict[tuple[str, str, str], Route] = {}
        self.blocked: set[frozenset[str]] = set()
        self._edges = list(edges)
        for a, b, length in edges:
            self._add_edge(a, b, length)

    def with_car(self, car: CarParams) -> "FactoryMap":
        """Same track for a car with different speed / turn times."""
        return FactoryMap(self.nodes, self._edges, car)

    # -- construction -------------------------------------------------------

    @classmethod
    def from_yaml(cls, path: str | Path | None = None, car: CarParams | None = None) -> "FactoryMap":
        path = Path(path) if path else CONFIG_DIR / "factory_layout.yaml"
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        nodes = {}
        for nid, n in raw["nodes"].items():
            if n["type"] not in NODE_TYPES:
                raise ValueError(f"node {nid}: type must be one of {NODE_TYPES}, got {n['type']!r}")
            nodes[nid] = Node(nid, float(n["x"]), float(n["y"]), n["type"])
        edges = []
        for e in raw["edges"]:
            a, b = e[0], e[1]
            length = float(e[2]) if len(e) > 2 else None
            edges.append((a, b, length))
        return cls(nodes, edges, car)

    def _add_edge(self, a: str, b: str, length: float | None) -> None:
        for n in (a, b):
            if n not in self.nodes:
                raise ValueError(f"edge {a}-{b}: unknown node {n!r}")
        na, nb = self.nodes[a], self.nodes[b]
        dx, dy = nb.x - na.x, nb.y - na.y
        if (dx != 0) == (dy != 0):
            raise ValueError(f"edge {a}-{b} must be a straight horizontal or vertical line")
        heading_ab = _VECTORS[(int(dx > 0) - int(dx < 0), int(dy > 0) - int(dy < 0))]
        heading_ba = opposite(heading_ab)
        if length is None:
            length = abs(dx) + abs(dy)
        for src, dst, h in ((a, b, heading_ab), (b, a, heading_ba)):
            taken = [n for n, (hh, _) in self._adj[src].items() if hh == h]
            if taken:
                raise ValueError(f"node {src} has two lines leaving towards {h}: {taken[0]} and {dst}")
            self._adj[src][dst] = (h, float(length))

    # -- queries ------------------------------------------------------------

    def neighbors(self, node: str) -> dict[str, tuple[str, float]]:
        """neighbor id -> (heading to drive towards it, length cm)."""
        return self._adj[node]

    def of_type(self, node_type: str) -> list[str]:
        return [n.id for n in self.nodes.values() if n.type == node_type]

    def arrival_heading(self, node: str) -> str:
        """Heading of a car parked at a dead end (facing into it)."""
        nbrs = self._adj[node]
        if len(nbrs) != 1:
            raise ValueError(f"{node} is not a dead end")
        (heading_out, _), = nbrs.values()
        return opposite(heading_out)

    def block_edge(self, a: str, b: str) -> None:
        """Mark a line as blocked (the car's ultrasonic sensor saw an obstacle on it)."""
        if b not in self._adj.get(a, {}):
            raise ValueError(f"there is no line between {a} and {b}")
        self.blocked.add(frozenset((a, b)))
        self._cache.clear()

    def reroute_from_edge(self, last_node: str, next_node: str, goal: str) -> Route:
        """New route for a car stopped by an obstacle between last_node and next_node.

        The line is blocked, the car turns around (UTURN), drives back to last_node,
        and continues from there. commands[0] is the UTURN done on the spot.
        """
        self.block_edge(last_node, next_node)
        h_forward, length = self._adj[last_node][next_node]
        back = self.route(last_node, goal, opposite(h_forward))
        return Route((next_node,) + back.path, ("UTURN",) + back.commands,
                     back.distance_cm + length / 2, back.time_s + self.car.uturn_s
                     + length / 2 / self.car.speed_cm_s, back.end_heading)

    def unblock_edge(self, a: str, b: str) -> None:
        self.blocked.discard(frozenset((a, b)))
        self._cache.clear()

    def turn_cost(self, command: str) -> float:
        if command == "STRAIGHT":
            return 0.0
        if command == "UTURN":
            return self.car.uturn_s
        return self.car.turn_s

    def route(self, start: str, goal: str, heading: str) -> Route:
        """Fastest route from `start` (car facing `heading`) to `goal`."""
        key = (start, goal, heading)
        if key not in self._cache:
            self._cache[key] = self._search(start, goal, heading)
        return self._cache[key]

    def _search(self, start: str, goal: str, heading: str) -> Route:
        if start == goal:
            return Route((start,), ("STOP",), 0.0, 0.0, heading)
        speed = self.car.speed_cm_s
        tie = itertools.count()
        frontier = [(0.0, next(tie), start, heading)]
        best = {(start, heading): 0.0}
        parent: dict[tuple[str, str], tuple[str, str, float]] = {}
        while frontier:
            t, _, node, h = heapq.heappop(frontier)
            if t > best.get((node, h), float("inf")):
                continue
            if node == goal:
                return self._build(start, heading, (node, h), parent, t)
            for nbr, (h_out, length) in self._adj[node].items():
                if frozenset((node, nbr)) in self.blocked:
                    continue
                nt = t + self.turn_cost(relative_turn(h, h_out)) + length / speed
                state = (nbr, h_out)
                if nt < best.get(state, float("inf")):
                    best[state] = nt
                    parent[state] = (node, h, length)
                    heapq.heappush(frontier, (nt, next(tie), nbr, h_out))
        raise ValueError(f"no route from {start} to {goal}")

    def _build(self, start, heading, end_state, parent, time_s) -> Route:
        states = [end_state]
        distance = 0.0
        while states[-1] != (start, heading):
            node, h, length = parent[states[-1]]
            distance += length
            states.append((node, h))
        states.reverse()
        path = tuple(n for n, _ in states)
        headings = [h for _, h in states]  # headings[i] = facing when arriving at path[i]
        commands = [relative_turn(headings[i], headings[i + 1]) for i in range(len(path) - 1)]
        commands.append("STOP")
        return Route(path, tuple(commands), distance, time_s, headings[-1])
