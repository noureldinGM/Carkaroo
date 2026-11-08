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


def list_factories() -> list[dict]:
    out = []
    if FACTORIES_DIR.exists():
        for p in sorted(FACTORIES_DIR.iterdir()):
            if exists(p.name):
                f = load(p.name)
                out.append({"id": f["id"], "name": f["name"]})
    return out
