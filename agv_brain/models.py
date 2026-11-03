"""Core data types shared by every part of the AI dispatcher.

Units used everywhere inside the package:
    time      -> seconds
    distance  -> cm
    rates     -> units per second (config files use units per minute)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"


# ---------------------------------------------------------------------------
# Settings loaded from config/materials.yaml
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CarParams:
    id: str = "AGV-1"
    speed_cm_s: float = 15.0
    turn_s: float = 2.0
    uturn_s: float = 4.0
    pickup_s: float = 4.0
    drop_s: float = 4.0
    battery_pct_per_m: float = 0.5
    min_battery_pct: float = 20.0
    dock: str = "HOME"
    start_heading: str = "N"


@dataclass(frozen=True)
class CostParams:
    stop_weight: float = 1.0
    below_safety_weight: float = 0.2
    flow_weight: float = 0.02
    aging_s: float = 300.0
    travel_weight: float = 0.05


@dataclass(frozen=True)
class AutomationParams:
    horizon_s: float = 120.0         # look-ahead: request this early before the safety level
    warehouse_low_boxes: int = 3     # warn when the warehouse has fewer boxes than this
    obstacle_wait_s: float = 10.0    # wait this long for an obstacle to clear before re-routing


@dataclass(frozen=True)
class Material:
    id: str
    name: str
    rack: str
    warehouse_stock: int
    delivery_qty: int


@dataclass
class StationMaterial:
    stock: float
    rate_per_min: float
    safety_stock: float
    capacity: float


@dataclass
class Station:
    id: str
    name: str
    criticality: int
    materials: dict[str, StationMaterial]


@dataclass
class Settings:
    car: CarParams
    cost: CostParams
    automation: AutomationParams
    materials: dict[str, Material]
    stations: dict[str, Station]


def load_settings(path: str | Path | None = None) -> Settings:
    path = Path(path) if path else CONFIG_DIR / "materials.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    materials = {
        mid: Material(id=mid, name=m["name"], rack=m["rack"],
                      warehouse_stock=int(m["warehouse_stock"]),
                      delivery_qty=int(m["delivery_qty"]))
        for mid, m in raw["materials"].items()
    }
    stations = {
        sid: Station(
            id=sid, name=s["name"], criticality=int(s["criticality"]),
            materials={mid: StationMaterial(**vals) for mid, vals in s["materials"].items()},
        )
        for sid, s in raw["stations"].items()
    }
    return Settings(car=CarParams(**raw.get("car", {})), cost=CostParams(**raw.get("cost", {})),
                    automation=AutomationParams(**raw.get("automation", {})),
                    materials=materials, stations=stations)


def initial_state(settings: Settings, car: "CarState | None" = None) -> "FactoryState":
    """Factory state using the stock levels written in the config (simulated sensors)."""
    import copy
    car = car or CarState(settings.car.dock, settings.car.start_heading)
    return FactoryState(now_s=0.0, car=car, stations=copy.deepcopy(settings.stations),
                        warehouse={m.id: m.warehouse_stock for m in settings.materials.values()})


# ---------------------------------------------------------------------------
# Runtime state
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CarState:
    node: str
    heading: str            # N / E / S / W, direction the car is facing
    battery_pct: float = 100.0


@dataclass(frozen=True)
class Request:
    """What an operator asks for: 'bring material X to station Y'."""
    id: str
    material: str
    station: str
    created_s: float = 0.0  # when the request was made (same clock as FactoryState.now_s)


@dataclass(frozen=True)
class Job:
    """A request resolved into the numbers the AI reasons about.

    All times are absolute on the planning clock, where t=0 is the moment the
    decision is made, so a schedule can be scored without mutating state.
    """
    id: str
    material: str
    station: str
    rack: str
    stock: float            # units at the station right now
    rate_per_s: float       # consumption rate
    safety_stock: float
    criticality: int
    wait_s: float           # how long the request has already waited

    @property
    def stockout_s(self) -> float:
        """Time until the station runs out of this material."""
        if self.rate_per_s <= 0:
            return float("inf")
        return self.stock / self.rate_per_s

    @property
    def below_safety_s(self) -> float:
        """Time until the stock drops below the safety level."""
        if self.rate_per_s <= 0:
            return float("inf")
        return max(0.0, (self.stock - self.safety_stock) / self.rate_per_s)


@dataclass
class FactoryState:
    now_s: float
    car: CarState
    stations: dict[str, Station]
    warehouse: dict[str, int]   # material id -> units left in the warehouse


@dataclass
class PlannedTask:
    job: Job
    to_rack: "Route"
    to_station: "Route"
    start_s: float
    finish_s: float
    stop_s: float           # predicted seconds the station is stopped before delivery
    score: float | None = None  # policy score (higher = earlier), if the policy has one


@dataclass
class Decision:
    policy: str
    tasks: list[PlannedTask] = field(default_factory=list)
    charge_first: bool = False
    charge_route: "Route | None" = None
    alerts: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def first(self) -> PlannedTask | None:
        return self.tasks[0] if self.tasks else None


if TYPE_CHECKING:
    from agv_brain.factory_map import Route
