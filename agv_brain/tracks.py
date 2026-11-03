"""Factory tracks: the sample one and the ones drawn on the website's Setup page.

A track is the same YAML as config/factory_layout.yaml (nodes with x/y in cm and
a type, straight edges). Tracks drawn in the editor are saved in config/tracks/.
`validate` explains in plain words what would stop the car on a track, so a
mistake is found on the screen instead of on the floor.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from agv_brain.factory_map import NODE_TYPES, FactoryMap, Node, opposite
from agv_brain.models import CONFIG_DIR, Settings

SAMPLE = CONFIG_DIR / "factory_layout.yaml"
TRACKS_DIR = CONFIG_DIR / "tracks"


def list_tracks() -> list[dict]:
    out = [{"id": "sample", "name": "Sample track"}]
    if TRACKS_DIR.exists():
        for p in sorted(TRACKS_DIR.glob("*.yaml")):
            raw = _read(p)
            out.append({"id": p.stem, "name": (raw or {}).get("name") or p.stem})
    return out


def track_path(track_id: str | None) -> Path:
    if not track_id or track_id == "sample":
        return SAMPLE
    if not re.fullmatch(r"[a-z0-9-]+", track_id):
        raise ValueError(f"bad track id {track_id!r}")
    p = TRACKS_DIR / f"{track_id}.yaml"
    if not p.exists():
        raise FileNotFoundError(f"no track named {track_id!r}")
    return p


def _read(path: Path) -> dict | None:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None


def load_raw(track_id: str | None) -> dict:
    raw = _read(track_path(track_id))
    if not raw:
        raise ValueError(f"track {track_id!r} could not be read")
    return raw


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    if not s or s == "sample":
        raise ValueError("give the track another name")
    return s


def save(name: str, raw: dict) -> str:
    """Write a track drawn on the website; returns its id."""
    track_id = slug(name)
    nodes = {nid: {"x": float(n["x"]), "y": float(n["y"]), "type": n["type"]} for nid, n in raw["nodes"].items()}
    edges = [[e[0], e[1], float(e[2])] if len(e) > 2 and e[2] else [e[0], e[1]] for e in raw["edges"]]
    TRACKS_DIR.mkdir(parents=True, exist_ok=True)
    text = (f"# Track drawn on the website (Setup page). Coordinates in cm, y grows downward.\n"
            + yaml.safe_dump({"name": name, "units": "cm", "nodes": nodes, "edges": edges},
                             sort_keys=False, default_flow_style=None))
    (TRACKS_DIR / f"{track_id}.yaml").write_text(text, encoding="utf-8")
    return track_id


# -- checks ------------------------------------------------------------------------

def _between(p: float, a: float, b: float) -> bool:
    return min(a, b) < p < max(a, b)


def validate(raw: dict, settings: Settings) -> dict:
    """{"errors": [...], "warnings": [...]}: errors stop the track from being used."""
    errors: list[str] = []
    warnings: list[str] = []
    nodes = raw.get("nodes") or {}
    edges = raw.get("edges") or []
    if not nodes:
        return {"errors": ["The track is empty."], "warnings": []}

    pts = {}
    for nid, n in nodes.items():
        if n.get("type") not in NODE_TYPES:
            errors.append(f"{nid}: unknown type {n.get('type')!r}.")
        try:
            pts[nid] = (float(n["x"]), float(n["y"]))
        except (KeyError, TypeError, ValueError):
            errors.append(f"{nid}: needs x and y in cm.")
    seen_at = {}
    for nid, p in pts.items():
        if p in seen_at:
            errors.append(f"{nid} and {seen_at[p]} are on the same spot.")
        seen_at[p] = nid

    lines, degree = [], {n: 0 for n in nodes}
    for e in edges:
        a, b = e[0], e[1]
        if a not in pts or b not in pts:
            errors.append(f"Line {a}–{b} uses a point that does not exist.")
            continue
        (ax, ay), (bx, by) = pts[a], pts[b]
        if (ax != bx) == (ay != by):
            errors.append(f"Line {a}–{b} is not straight: lines must go straight across or straight up/down.")
            continue
        for nid, (px, py) in pts.items():
            if nid in (a, b):
                continue
            if (ax == bx == px and _between(py, ay, by)) or (ay == by == py and _between(px, ax, bx)):
                errors.append(f"Line {a}–{b} passes over {nid}: split it into two lines at {nid}.")
        lines.append((a, b, (ax, ay), (bx, by)))
        degree[a] += 1
        degree[b] += 1

    for i, (a, b, pa, pb) in enumerate(lines):           # lines that cross with no junction there
        for c, d, pc, pd in lines[i + 1:]:
            if {a, b} & {c, d}:
                continue
            h1, h2 = pa[1] == pb[1], pc[1] == pd[1]
            if h1 == h2:
                continue
            (h, hp, hq), (v, vp, vq) = ((a + "–" + b, pa, pb), (c + "–" + d, pc, pd)) if h1 else \
                ((c + "–" + d, pc, pd), (a + "–" + b, pa, pb))
            if _between(vp[0], hp[0], hq[0]) and _between(hp[1], vp[1], vq[1]):
                errors.append(f"Lines {h} and {v} cross without a junction: put a junction where they meet.")

    for nid, n in nodes.items():
        t, k = n.get("type"), degree.get(nid, 0)
        if t == "junction":
            if k <= 1:
                errors.append(f"{nid} is a junction with {k} line{'s' if k != 1 else ''}: a line end must be a "
                              "rack, a station or the dock.")
            elif k == 2:
                warnings.append(f"{nid} is a corner (2 lines). The car counts it as a junction, so it must be "
                                "able to detect it (for example a black cross marker).")
        elif t in ("rack", "station", "dock") and k != 1:
            errors.append(f"{nid} is a {t}: it must be the end of exactly one line (it has {k}).")

    # names the factory settings expect
    for m in settings.materials.values():
        if nodes.get(m.rack, {}).get("type") != "rack":
            errors.append(f"Rack {m.rack} for {m.id} ({m.name}) is missing.")
    for sid, st in settings.stations.items():
        if nodes.get(sid, {}).get("type") != "station":
            errors.append(f"Station {sid} ({st.name}) is missing.")
    dock = settings.car.dock
    if nodes.get(dock, {}).get("type") != "dock":
        errors.append(f"The dock {dock} (where the car charges and starts) is missing.")
    racks = {m.rack for m in settings.materials.values()}
    for nid, n in nodes.items():
        if n.get("type") == "rack" and nid not in racks:
            warnings.append(f"Rack {nid} is not used by any material.")
        if n.get("type") == "station" and nid not in settings.stations:
            warnings.append(f"Station {nid} is not in config/materials.yaml, so it gets no deliveries.")

    if errors:
        return {"errors": errors, "warnings": warnings}

    # can the car actually drive every trip?
    try:
        fmap = FactoryMap({nid: _node(nid, n) for nid, n in nodes.items()},
                          [(e[0], e[1], float(e[2]) if len(e) > 2 and e[2] else None) for e in edges],
                          settings.car)
    except ValueError as exc:
        return {"errors": [str(exc)], "warnings": warnings}
    heading = opposite(fmap.arrival_heading(dock))   # parked at the dock, facing out
    for m in settings.materials.values():
        try:
            fmap.route(dock, m.rack, heading)
        except ValueError:
            errors.append(f"The car cannot drive from {dock} to rack {m.rack}.")
            continue
        for sid, st in settings.stations.items():
            if m.id in st.materials:
                try:
                    fmap.route(m.rack, sid, fmap.arrival_heading(m.rack))
                except ValueError:
                    errors.append(f"{sid} cannot be reached from rack {m.rack}.")
    return {"errors": errors, "warnings": warnings}


def _node(nid: str, n: dict) -> Node:
    return Node(nid, float(n["x"]), float(n["y"]), n["type"])
