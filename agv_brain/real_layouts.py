"""Real factory layouts from the KIT AGV data set, to test the ML ranker on.

Source: Sperling et al., "Classified AGV Material Flow and Layout Data Set for
Multidisciplinary Investigation", IEEE Access 11 (2023), CC BY 4.0. The files are
in data/external/kit_agv_layouts (see the README there).

What comes from the real factory:
  - the stations and the driving distance between every pair of them (meters);
  - which source (a warehouse rack for us) supplies which sink (a station for us);
  - how many trips per hour each of those routes has. Busy routes get requests
    more often in the test situations.

What does not: the data set is a yearly plan, not a snapshot of one moment. So the
stock left, usage rate, criticality and waiting time of each request are drawn
exactly as in training (simulator.random_jobs).

The data set has no track drawing, only a distance matrix. A MatrixMap turns it
into trip times: distance / car speed, with no junction turns.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from agv_brain.factory_map import Route
from agv_brain.models import ROOT, CarParams, CarState, Job, Material, Settings, Station, StationMaterial
from agv_brain.simulator import Context, random_jobs

KIT_DIR = ROOT / "data" / "external" / "kit_agv_layouts"
REAL_AGV_SPEED_CM_S = 100.0  # a typical industrial AGV drives about 1 m/s


@dataclass(frozen=True)
class RealLayout:
    name: str
    stations: tuple[str, ...]
    distance_m: dict[tuple[str, str], float]   # (from, to) -> meters
    routes: tuple[tuple[str, str, float], ...]  # (source, sink, trips per hour)


def _read(folder: Path, kind: str) -> list[list[str]]:
    path = folder / f"{folder.name}_{kind}.csv"
    with path.open(encoding="cp1252", newline="") as f:  # the files are Windows-1252
        return [row for row in csv.reader(f, delimiter=";") if row]


def _number(text: str) -> float:
    return float(text.strip().replace(",", "."))


def load_layout(folder: str | Path) -> RealLayout:
    folder = Path(folder)
    matrix = _read(folder, "Distancematrix")
    cols = [c.strip() for c in matrix[0][1:]]
    distance = {}
    for row in matrix[1:]:
        src = row[0].strip()
        for dst, cell in zip(cols, row[1:]):
            if src != dst and cell.strip():
                distance[src, dst] = _number(cell)
    routes = tuple((r[1].strip(), r[2].strip(), _number(r[4]))
                   for r in _read(folder, "Joblist")[1:])
    return RealLayout(folder.name, tuple(cols), distance, routes)


def industry_layouts(root: str | Path = KIT_DIR, min_routes: int = 2) -> list[RealLayout]:
    """The real industry layouts with a choice to make (at least `min_routes` routes).
    Layouts with a single route are shuttles: there is never anything to order."""
    layouts = [load_layout(p) for p in sorted(Path(root).glob("Industry*")) if p.is_dir()]
    return [lay for lay in layouts if len(lay.routes) >= min_routes]


class MatrixMap:
    """Stands in for FactoryMap when a factory is known only by its distance matrix."""

    def __init__(self, layout: RealLayout, car: CarParams):
        self.layout = layout
        self.car = car
        self.nodes = {s: None for s in layout.stations}

    def with_car(self, car: CarParams) -> "MatrixMap":
        return MatrixMap(self.layout, car)

    def route(self, start: str, goal: str, heading: str) -> Route:
        if start == goal:
            return Route((start,), ("STOP",), 0.0, 0.0, heading)
        try:
            meters = self.layout.distance_m[start, goal]
        except KeyError:
            raise ValueError(f"{self.layout.name}: no distance from {start} to {goal}") from None
        cm = meters * 100.0
        return Route((start, goal), ("STRAIGHT", "STOP"), cm, cm / self.car.speed_cm_s, heading)


def real_context(layout: RealLayout, base: Settings,
                 speed_cm_s: float = REAL_AGV_SPEED_CM_S) -> Context:
    """One material per source (its rack is the source), one station per sink."""
    car = replace(base.car, speed_cm_s=speed_cm_s, dock=layout.stations[0])
    materials, stations = {}, {}
    for src, dst, _ in layout.routes:
        mid = f"M-{src}"
        materials.setdefault(mid, Material(mid, f"Material from {src}", src, 1000, 20))
        st = stations.setdefault(dst, Station(dst, f"Station {dst}", 2, {}))
        st.materials[mid] = StationMaterial(stock=10.0, rate_per_min=2.0, safety_stock=4.0,
                                            capacity=60.0)
    return Context(MatrixMap(layout, car), replace(base, car=car, materials=materials,
                                                   stations=stations))


def real_scenario(rng: np.random.Generator, ctx: Context,
                  n_range: tuple[int, int] = (2, 7)) -> tuple[CarState, list[Job]]:
    """A decision moment on a real layout: the car at a random station, and requests
    on the layout's real routes, busy routes more likely."""
    layout = ctx.fmap.layout
    combos = [(dst, f"M-{src}") for src, dst, _ in layout.routes]
    weights = np.array([f for _, _, f in layout.routes])
    n = min(int(rng.integers(n_range[0], n_range[1] + 1)), len(combos))
    car = CarState(str(rng.choice(layout.stations)), "N", float(rng.uniform(30, 100)))
    return car, random_jobs(rng, ctx, n, combos, weights)
