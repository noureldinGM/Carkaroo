"""Factories: the name typed on the website's login page, with that factory's own setup.

Each factory has a folder in config/factories/<id>/:
    factory.yaml     name, track, how it runs (mode) and the simulation speed
    materials.yaml   its stations and materials, in the same format as config/materials.yaml

A new factory starts as a copy of the sample (config/materials.yaml), so it can run at once;
the Setup page then changes it. Git ignores config/factories/ (it belongs to this laptop).
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import yaml

from agv_brain.models import CONFIG_DIR

FACTORIES_DIR = CONFIG_DIR / "factories"
SAMPLE_MATERIALS = CONFIG_DIR / "materials.yaml"
MODES = ("sim", "real_car", "real")
NAME_MAX = 40


def clean_name(name) -> str:
    """The factory name as typed, tidied; raises ValueError if it cannot be used."""
    if not isinstance(name, str):
        raise ValueError("Type the factory's name.")
    name = " ".join(name.split())
    if not name:
        raise ValueError("Type the factory's name.")
    if len(name) > NAME_MAX:
        raise ValueError(f"Keep the name under {NAME_MAX} letters.")
    if not re.search(r"[A-Za-z0-9]", name):
        raise ValueError("Use some letters or numbers in the name.")
    return name


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:NAME_MAX]
    if not s:
        raise ValueError("Use some letters or numbers in the name.")
    return s


def folder(factory_id: str) -> Path:
    if not isinstance(factory_id, str) or not re.fullmatch(r"[a-z0-9-]+", factory_id):
        raise ValueError(f"bad factory id {factory_id!r}")
    return FACTORIES_DIR / factory_id


def exists(factory_id: str | None) -> bool:
    try:
        return bool(factory_id) and (folder(factory_id) / "factory.yaml").is_file()
    except ValueError:
        return False


def _read(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}


def load(factory_id: str) -> dict:
    """{"id", "name", "track", "mode", "speed"} with safe defaults."""
    raw = _read(folder(factory_id) / "factory.yaml")
    if not raw:
        raise FileNotFoundError(f"no factory named {factory_id!r}")
    mode = raw.get("mode") if raw.get("mode") in MODES else "sim"
    try:
        speed = max(1.0, min(20.0, float(raw.get("speed", 8))))
    except (TypeError, ValueError):
        speed = 8.0
    return {"id": factory_id, "name": str(raw.get("name") or factory_id), "track": str(raw.get("track") or "sample"),
            "mode": mode, "speed": speed}


def save(factory: dict) -> None:
    data = {k: factory[k] for k in ("name", "track", "mode", "speed")}
    (folder(factory["id"]) / "factory.yaml").write_text(
        "# A factory made on the website's login page (this laptop only).\n" + yaml.safe_dump(data, sort_keys=False),
        encoding="utf-8")


def materials_path(factory_id: str) -> Path:
    return folder(factory_id) / "materials.yaml"


def open_or_create(name) -> dict:
    """Open the factory with this name, or make it (a copy of the sample factory)."""
    name = clean_name(name)
    fid = slug(name)
    if exists(fid):
        return load(fid)
    d = folder(fid)
    d.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SAMPLE_MATERIALS, d / "materials.yaml")
    factory = {"id": fid, "name": name, "track": "sample", "mode": "sim", "speed": 8.0}
    save(factory)
    return factory


# -- stations and materials (the Setup page's "Your factory" card) -------------------

MATERIAL_IDS = "ABCDE"                       # up to 5 materials, rack W-<id>
STATION_IDS = [f"S{i}" for i in range(1, 9)]  # up to 8 stations
TEXT_MAX = 30


def _text(v, what: str) -> str:
    if not isinstance(v, str) or not " ".join(v.split()):
        raise ValueError(f"{what} needs a name.")
    v = " ".join(v.split())
    if len(v) > TEXT_MAX:
        raise ValueError(f"{what}: keep the name under {TEXT_MAX} letters.")
    return v


def _number(v, lo: float, hi: float, what: str, whole: bool = False) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        raise ValueError(f"{what} must be a number.")
    if not lo <= v <= hi:
        raise ValueError(f"{what} must be from {lo:g} to {hi:g}.")
    if whole and v != int(v):
        raise ValueError(f"{what} must be a whole number.")
    return int(v) if whole else round(float(v), 2)


def settings_raw(factory_id: str) -> dict:
    return _read(materials_path(factory_id))


def editable(factory_id: str) -> dict:
    """What the Setup page edits: the materials and the stations, as lists in order."""
    raw = settings_raw(factory_id)
    return {
        "materials": [{"id": mid, "name": m["name"], "box": m["delivery_qty"], "warehouse": m["warehouse_stock"]}
                      for mid, m in (raw.get("materials") or {}).items()],
        "stations": [{"id": sid, "name": s["name"], "priority": s["criticality"],
                      "materials": {mid: {"stock": v["stock"], "capacity": v["capacity"],
                                          "safety": v["safety_stock"], "use_per_min": v["rate_per_min"]}
                                    for mid, v in (s.get("materials") or {}).items()}}
                     for sid, s in (raw.get("stations") or {}).items()],
        "limits": {"materials": len(MATERIAL_IDS), "stations": len(STATION_IDS), "name": TEXT_MAX},
    }


def check_settings(data) -> dict:
    """Check what the Setup page sent; returns the materials and stations sections of
    materials.yaml, or raises ValueError with the first problem in plain words."""
    if not isinstance(data, dict):
        raise ValueError("Send the materials and the stations.")
    mats, stations = data.get("materials"), data.get("stations")
    if not isinstance(mats, list) or not mats:
        raise ValueError("Add at least one material.")
    if not isinstance(stations, list) or not stations:
        raise ValueError("Add at least one station.")
    if len(mats) > len(MATERIAL_IDS):
        raise ValueError(f"At most {len(MATERIAL_IDS)} materials.")
    if len(stations) > len(STATION_IDS):
        raise ValueError(f"At most {len(STATION_IDS)} stations.")

    out_m: dict = {}
    for m in mats:
        if not isinstance(m, dict) or m.get("id") not in MATERIAL_IDS or m["id"] in out_m:
            raise ValueError("Each material needs its own letter, A to E.")
        mid = m["id"]
        name = _text(m.get("name"), f"Material {mid}")
        out_m[mid] = {"name": name, "rack": f"W-{mid}",
                      "warehouse_stock": _number(m.get("warehouse"), 0, 100_000, f"{name}: the warehouse stock", True),
                      "delivery_qty": _number(m.get("box"), 1, 1000, f"{name}: the box size", True)}

    out_s: dict = {}
    names = set()
    for s in stations:
        if not isinstance(s, dict) or s.get("id") not in STATION_IDS or s["id"] in out_s:
            raise ValueError("Each station needs its own number, S1 to S8.")
        sid = s["id"]
        name = _text(s.get("name"), f"Station {sid}")
        if name.lower() in names:
            raise ValueError(f'Two stations are called "{name}": give each its own name.')
        names.add(name.lower())
        used = s.get("materials")
        if not isinstance(used, dict) or not used:
            raise ValueError(f"{name} must use at least one material.")
        rows = {}
        for mid, v in used.items():
            if mid not in out_m:
                raise ValueError(f"{name} uses material {mid}, which is not in the list.")
            if not isinstance(v, dict):
                raise ValueError(f"{name}: send the numbers for {mid}.")
            what = f"{name} / {out_m[mid]['name']}"
            cap = _number(v.get("capacity"), 1, 10_000, f"{what}: the capacity")
            rows[mid] = {"stock": _number(v.get("stock"), 0, cap, f"{what}: the starting stock"),
                         "rate_per_min": _number(v.get("use_per_min"), 0, 1000, f"{what}: the use per minute"),
                         "safety_stock": _number(v.get("safety"), 0, cap, f"{what}: the safety level"),
                         "capacity": cap}
        out_s[sid] = {"name": name, "criticality": int(_number(s.get("priority"), 1, 3, f"{name}: the priority", True)),
                      "materials": rows}
    for mid, m in out_m.items():
        if not any(mid in s["materials"] for s in out_s.values()):
            raise ValueError(f"No station uses {m['name']} ({mid}): tick it at a station or remove it.")
    return {"materials": out_m, "stations": out_s}


def save_settings(factory_id: str, data) -> None:
    """Save the Setup page's materials and stations; the car, cost and automation
    settings stay as they are (copied from the sample factory)."""
    checked = check_settings(data)
    raw = settings_raw(factory_id) or _read(SAMPLE_MATERIALS)
    raw.update(checked)
    materials_path(factory_id).write_text(
        "# Stations and materials of this factory, from the website's Setup page.\n"
        "# Rates are in units per minute, times in seconds, distances in cm.\n"
        + yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")


def list_factories() -> list[dict]:
    out = []
    if FACTORIES_DIR.exists():
        for p in sorted(FACTORIES_DIR.iterdir()):
            if exists(p.name):
                f = load(p.name)
                out.append({"id": f["id"], "name": f["name"]})
    return out
