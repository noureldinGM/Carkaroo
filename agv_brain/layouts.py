"""Random factory layouts, so the ML ranker learns to work on any track.

A layout is a grid of junctions with random line lengths, a few grid lines
removed, and dead-end lines on the outside for the warehouse racks, the stations
and the charging dock. Each one also gets random materials, stations,
criticalities and a random car speed.

The rules match what the car can physically detect:
  - every junction is a T or a cross (3-4 lines), or a 90-degree corner (L);
    never a straight pass-through, which the IR sensors could not see
  - racks, stations and the dock are line ends
  - everything is connected
"""

from __future__ import annotations

from collections import deque
from dataclasses import replace

import numpy as np

from agv_brain.factory_map import FactoryMap, Node, opposite
from agv_brain.models import Material, Settings, Station, StationMaterial
from agv_brain.simulator import Context

_DIRS = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
MATERIAL_IDS = "ABCDE"


def _connected(nodes: list[str], edges: set[frozenset]) -> bool:
    adj = {n: [] for n in nodes}
    for e in edges:
        a, b = tuple(e)
        adj[a].append(b)
        adj[b].append(a)
    seen, todo = {nodes[0]}, deque([nodes[0]])
    while todo:
        for nb in adj[todo.popleft()]:
            if nb not in seen:
                seen.add(nb)
                todo.append(nb)
    return len(seen) == len(nodes)


def _detectable(junction: str, edges: set[frozenset], pos: dict) -> bool:
    """A junction must be a T/cross, or an L corner (never a straight line)."""
    dirs = []
    for e in edges:
        if junction in e:
            (other,) = e - {junction}
            dx = pos[other][0] - pos[junction][0]
            dirs.append("H" if dx else "V")
    if len(dirs) >= 3:
        return True
    return len(dirs) == 2 and dirs[0] != dirs[1]


def random_layout(rng: np.random.Generator, base: Settings) -> Context:
    rows, cols = int(rng.integers(2, 5)), int(rng.integers(3, 7))
    xs = np.concatenate([[0.0], np.cumsum(rng.uniform(50, 150, cols - 1))]).round()
    ys = np.concatenate([[0.0], np.cumsum(rng.uniform(50, 150, rows - 1))]).round()
    pos: dict[str, tuple[float, float]] = {}
    for r in range(rows):
        for c in range(cols):
            pos[f"J{r}{c}"] = (xs[c], ys[r])
    junctions = list(pos)
    grid = set()
    for r in range(rows):
        for c in range(cols):
            if c + 1 < cols:
                grid.add(frozenset((f"J{r}{c}", f"J{r}{c + 1}")))
            if r + 1 < rows:
                grid.add(frozenset((f"J{r}{c}", f"J{r + 1}{c}")))

    # dead ends go on the outside of the grid
    slots = []
    for r in range(rows):
        for c in range(cols):
            j = f"J{r}{c}"
            if r == 0:
                slots.append((j, "N"))
            if r == rows - 1:
                slots.append((j, "S"))
            if c == 0:
                slots.append((j, "W"))
            if c == cols - 1:
                slots.append((j, "E"))
    n_mat = int(rng.integers(2, 6))
    n_st = int(rng.integers(2, 7))
    while n_mat + n_st + 1 > len(slots):
        if n_st > 2:
            n_st -= 1
        else:
            n_mat -= 1
    mats = list(MATERIAL_IDS[:n_mat])
    names = ["HOME"] + [f"W-{m}" for m in mats] + [f"S{k + 1}" for k in range(n_st)]
    picked = rng.choice(len(slots), size=len(names), replace=False)
    edges = set(grid)
    for name, k in zip(names, picked):
        j, d = slots[int(k)]
        length = round(float(rng.uniform(40, 100)))
        dx, dy = _DIRS[d]
        pos[name] = (pos[j][0] + dx * length, pos[j][1] + dy * length)
        edges.add(frozenset((j, name)))

    # remove a few grid lines, keeping the track connected and detectable
    all_nodes = list(pos)
    grid_list = sorted(grid, key=sorted)
    for idx in rng.permutation(len(grid_list))[: int(rng.integers(0, len(grid_list) // 4 + 1))]:
        e = grid_list[int(idx)]
        trial = edges - {e}
        if _connected(all_nodes, trial) and all(_detectable(j, trial, pos) for j in e):
            edges = trial
    # corners without an attached line could be a straight pass-through: re-check all
    for j in junctions:
        if not _detectable(j, edges, pos):
            raise RuntimeError("generated an undetectable junction")  # should not happen

    types = {n: "junction" for n in junctions}
    types.update({"HOME": "dock", **{f"W-{m}": "rack" for m in mats},
                  **{f"S{k + 1}": "station" for k in range(n_st)}})
    nodes = {n: Node(n, x, y, types[n]) for n, (x, y) in pos.items()}
    edge_list = sorted((*sorted(e), None) for e in edges)  # sorted: same layout every run

    speed = base.car.speed_cm_s * float(rng.uniform(0.6, 1.5))
    fmap = FactoryMap(nodes, edge_list, replace(base.car, speed_cm_s=speed, dock="HOME"))
    car = replace(fmap.car, start_heading=opposite(fmap.arrival_heading("HOME")))
    fmap = fmap.with_car(car)

    materials = {m: Material(m, f"Material {m}", f"W-{m}", 200, int(rng.integers(5, 25)))
                 for m in mats}
    stations = {}
    for k in range(n_st):
        used = rng.choice(mats, size=int(rng.integers(1, min(3, n_mat) + 1)), replace=False)
        stations[f"S{k + 1}"] = Station(
            f"S{k + 1}", f"Station {k + 1}", int(rng.integers(1, 4)),
            {str(m): StationMaterial(stock=float(rng.integers(0, 30)),
                                     rate_per_min=float(rng.uniform(0.5, 6)),
                                     safety_stock=float(rng.integers(2, 8)), capacity=60.0)
             for m in used})
    return Context(fmap, replace(base, car=car, materials=materials, stations=stations))


def layout_pool(n: int, seed: int, base: Settings) -> list[Context]:
    rng = np.random.default_rng(seed)
    return [random_layout(rng, base) for _ in range(n)]
