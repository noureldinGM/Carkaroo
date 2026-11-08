"""Live dashboard: a small web server that shows what the AI sees and decides.

It only listens to the message bus (factory/ai/state and factory/ai/decision),
so it works the same for the simulation and for the real car over MQTT.

    GET  /                 the dashboard page
    GET  /api/snapshot     {"state", "decision", "layout", "sim"} as JSON
    POST /api/request      {"material": "B", "station": "S3"}  manual request
    POST /api/refill       {"material": "A"}  the warehouse rack was restocked
    POST /api/sim          simulation controls (obstacle, stock), simulation only

With an `app` (agv_brain.app.App) it also serves the login, Start and Setup pages:
    GET  /api/factories            the factories made so far (names only)
    POST /api/login                {"name": "Exhibit Factory"}  open or make a factory
    POST /api/logout               back to the login page (stops the factory)
    POST /api/run                  {"mode": "sim", "speed": 8}  start the factory
    POST /api/stop                 stop it
    GET  /api/factory/settings     the factory's materials and stations, for the Setup page
    POST /api/factory/settings     {"materials": [...], "stations": [...]}  save them
    GET  /api/setup                mode, track, devices (keys only for the laptop itself)
    GET  /api/track/<id>           a track, for the editor
    POST /api/mode                 {"mode": "real_car", "track": "my-track", "speed": 8}  (restarts it if running)
    POST /api/device/<id>/key      a new key for a device
    POST /api/track/validate       {"track": {...}} -> problems
    POST /api/track/save           {"name": "My track", "track": {...}}
Changes are only accepted from the laptop itself, never from another device on the Wi-Fi.
Requests, refills and simulation controls are checked against the factory (known station,
material and line; numbers in range) and refused with a reason in plain words.

Security (see docs/security.md):
  * POSTs must be JSON (Content-Type: application/json) and, when the browser sends an
    Origin, come from this same site, so another web page open in the browser cannot
    send commands (CSRF).
  * The Host header must be an IP address, localhost or this laptop's name, which stops
    DNS-rebinding pages from reading the keys.
  * Bodies are capped at 1 MB; slow clients time out.
  * Every response carries security headers (CSP, no framing, nosniff, no referrer).
  * Only web file types are served from static/ and design/.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import re
import socket
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agv_brain import protocol as P
from agv_brain.simulator import Context

STATIC = Path(__file__).resolve().parent / "static"
DESIGN = Path(__file__).resolve().parents[2] / "design"   # the Carkaroo design system (tokens, logos, style guide)
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml",
         ".json": "application/json", ".png": "image/png", ".jpg": "image/jpeg",
         ".md": "text/plain; charset=utf-8"}
MAX_BODY = 1_000_000   # bytes; a track is a few kB
FONTS_CSS, FONTS_FILES = "https://fonts.googleapis.com", "https://fonts.gstatic.com"
HEADERS = {"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
           "Referrer-Policy": "no-referrer", "Cross-Origin-Opener-Policy": "same-origin",
           "Permissions-Policy": "camera=(), microphone=(), geolocation=()"}


def csp(html: bytes = b"") -> str:
    """Content-Security-Policy; inline <script> blocks of `html` are allowed by their hash."""
    html = html.replace(b"\r\n", b"\n").replace(b"\r", b"\n")   # browsers hash the text with \n line ends
    hashes = " ".join("'sha256-%s'" % base64.b64encode(hashlib.sha256(m).digest()).decode()
                      for m in re.findall(rb"<script>(.*?)</script>", html, re.S))
    return ("default-src 'self'; script-src 'self' " + hashes + "; "
            f"style-src 'self' 'unsafe-inline' {FONTS_CSS}; font-src 'self' {FONTS_FILES}; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; "
            "form-action 'self'; frame-ancestors 'none'")


def _names() -> set[str]:
    n = socket.gethostname().lower()
    return {"localhost", n, n + ".local", n + ".lan"}


def host_ok(host: str | None, names: set[str]) -> bool:
    """True for an IP address, localhost or this laptop's name (blocks DNS rebinding)."""
    if not host:
        return False
    h = host.strip().lower()
    if h.startswith("["):                       # [::1]:8050
        h = h[1:h.find("]")] if "]" in h else h
    elif h.count(":") == 1:                     # name:8050
        h = h.rsplit(":", 1)[0]
    if h in names or h.endswith(".localhost"):
        return True
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        return False


def layout_json(ctx: Context) -> dict:
    fmap, s = ctx.fmap, ctx.settings
    nodes = []
    for n in fmap.nodes.values():
        out = None
        if len(fmap.neighbors(n.id)) == 1:   # dead end: which way is "outside"
            out = fmap.arrival_heading(n.id)
        nodes.append({"id": n.id, "x": n.x, "y": n.y, "type": n.type, "out": out})
    edges = sorted({tuple(sorted((a, b))) for a in fmap.nodes for b in fmap.neighbors(a)})
    return {"nodes": nodes, "edges": [list(e) for e in edges],
            "materials": {m.id: {"name": m.name, "rack": m.rack, "box": m.delivery_qty, "full": m.warehouse_stock}
                          for m in s.materials.values()},
            "stations": {st.id: {"name": st.name, "criticality": st.criticality,
                                 "materials": list(st.materials)} for st in s.stations.values()},
            "dock": s.car.dock, "warehouse_low_boxes": s.automation.warehouse_low_boxes}


def _num(v, lo: float, hi: float, what: str) -> float:
    """A number from a request, or ValueError with a reason in plain words."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        raise ValueError(f"{what} must be a number.")
    if not lo <= v <= hi:
        raise ValueError(f"{what} must be from {lo:g} to {hi:g}.")
    return float(v)


def check_request(body: dict, layout: dict, state: dict | None) -> dict:
    """A manual delivery request: a station that uses the material, not already asked for."""
    st, m = body.get("station"), body.get("material")
    station = layout["stations"].get(st) if isinstance(st, str) else None
    if station is None:
        raise ValueError("Choose a station of this factory.")
    if not isinstance(m, str) or m not in station["materials"]:
        raise ValueError(f"{station['name']} does not use that material.")
    for r in (state or {}).get("requests") or []:
        if r.get("station") == st and r.get("material") == m:
            raise ValueError(f"{m} for {station['name']} is already asked for: the AI has it in its list.")
    return {"material": m, "station": st}


def check_refill(body: dict, layout: dict) -> dict:
    m = body.get("material")
    if not isinstance(m, str) or m not in layout["materials"]:
        raise ValueError("Choose a material of this factory.")
    msg = {"material": m}
    if body.get("units") is not None:
        msg["units"] = int(_num(body["units"], 0, 100_000, "The number of units"))
    return msg


def check_sim(body: dict, layout: dict, state: dict | None) -> dict:
    """Simulation controls (see agv_brain/sim_devices.py), with every value checked."""
    cmd = body.get("cmd")
    if cmd == "clear_obstacles":
        return {"cmd": cmd}
    if cmd == "set_battery":
        return {"cmd": cmd, "value": _num(body.get("value"), 0, 100, "The battery")}
    if cmd == "obstacle":
        edge = body.get("edge")
        lines = {tuple(sorted(e)) for e in layout["edges"]}
        if not (isinstance(edge, list) and len(edge) == 2 and all(isinstance(x, str) for x in edge)
                and tuple(sorted(edge)) in lines):
            raise ValueError("Choose a line of the track.")
        return {"cmd": cmd, "edge": edge, "duration_s": _num(body.get("duration_s", 60), 1, 600, "The time")}
    if cmd == "set_stock":
        st, m = body.get("station"), body.get("material")
        station = layout["stations"].get(st) if isinstance(st, str) else None
        if station is None or not isinstance(m, str) or m not in station["materials"]:
            raise ValueError("Choose a station and one of its materials.")
        mats = (((state or {}).get("stations") or {}).get(st) or {}).get("materials") or {}
        cap = (mats.get(m) or {}).get("capacity", 1000)
        return {"cmd": cmd, "station": st, "material": m,
                "stock": _num(body.get("stock"), 0, cap, f"The stock (it holds {cap:g})")}
    raise ValueError("Unknown simulation control.")


class DashboardServer:
    def __init__(self, bus, ctx: Context, host: str = "127.0.0.1", port: int = 8050,
                 sim_controls: bool = False, app=None):
        self.bus, self.sim_controls, self.app = bus, sim_controls, app
        self.ctx = ctx
        self.layout = layout_json(ctx)
        self.state: dict | None = None
        self.decision: dict | None = None
        self._lock = threading.Lock()
        bus.subscribe(P.AI_STATE, self._on_state)
        bus.subscribe(P.AI_DECISION, self._on_decision)
        server = self
        names = _names()

        class Handler(BaseHTTPRequestHandler):
            timeout = 15   # seconds; a client that stops sending is dropped
            server_version, sys_version = "Carkaroo", ""

            def log_message(self, *args):  # keep the terminal quiet
                pass

            def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                for k, v in HEADERS.items():
                    self.send_header(k, v)
                self.send_header("Content-Security-Policy", csp(body if ctype.startswith("text/html") else b""))
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _json(self, code: int, data) -> None:
                self._send(code, json.dumps(data).encode())

            @property
            def local(self) -> bool:
                return self.client_address[0] in ("127.0.0.1", "::1", "::ffff:127.0.0.1")

            def _host_ok(self) -> bool:
                if host_ok(self.headers.get("Host"), names):
                    return True
                self._send(421, b'{"error": "unknown host name; open the website by IP address or localhost"}')
                return False

            def _same_origin(self) -> bool:
                origin = self.headers.get("Origin")
                if origin is None:            # not from a browser page (curl, tests): the Host check is enough
                    return True
                return origin.split("://", 1)[-1].lower() == (self.headers.get("Host") or "").lower()

            def do_GET(self):
                if not self._host_ok():
                    return
                path = self.path.split("?")[0]
                app = server.app
                if path == "/api/snapshot":
                    with server._lock:
                        data = {"state": server.state, "decision": server.decision}
                    if app:
                        parts = app.sim_parts
                        if not app.running:          # idle: the page shows Start, never an old state
                            data.update(state=None, decision=None)
                        data.update(layout=app.layout, layout_version=app.layout_version,
                                    sim=parts["car"] or parts["stations"], sim_parts=parts,
                                    mode={"id": app.mode, "name": app.mode_name}, setup=True,
                                    running=app.running, factory=app.factory_info(), local=self.local)
                    else:
                        data.update(layout=server.layout, layout_version=0, sim=server.sim_controls,
                                    sim_parts={"car": server.sim_controls, "stations": server.sim_controls},
                                    mode=None, setup=False, running=True, factory=None, local=self.local)
                    return self._json(200, data)
                if app and path == "/api/factories":
                    from agv_brain import factories
                    return self._json(200, {"factories": factories.list_factories(), "current": app.factory_info()})
                if app and path == "/api/factory/settings":
                    from agv_brain import factories
                    if not app.factory:
                        return self._json(409, {"error": "Open a factory on the login page first."})
                    return self._json(200, factories.editable(app.factory["id"]))
                if app and path == "/api/setup":
                    return self._json(200, app.setup(self.local))
                if app and path.startswith("/api/track/"):
                    from agv_brain import tracks
                    try:
                        return self._json(200, tracks.load_raw(path.removeprefix("/api/track/")))
                    except (ValueError, FileNotFoundError) as exc:
                        return self._json(404, {"error": str(exc)})
                root, name = STATIC, "index.html" if path in ("/", "/index.html") else path.removeprefix("/static/")
                if path == "/design":  # the style guide uses relative links, so it needs the slash
                    self.send_response(301); self.send_header("Location", "/design/"); self.end_headers()
                    return
                if path.startswith("/design/"):
                    root, name = DESIGN, path.removeprefix("/design").strip("/") or "index.html"
                file = (root / name).resolve()
                if root not in file.parents or not file.is_file() or file.suffix.lower() not in TYPES:
                    return self._send(404, b'{"error": "not found"}')
                self._send(200, file.read_bytes(), TYPES[file.suffix.lower()])

            def do_POST(self):
                if not self._host_ok():
                    return
                if not self._same_origin():
                    return self._send(403, b'{"error": "requests from other websites are refused"}')
                if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
                    return self._send(415, b'{"error": "send JSON (Content-Type: application/json)"}')
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    return self._send(400, b'{"error": "bad Content-Length"}')
                if not 0 <= length <= MAX_BODY:
                    return self._send(413, b'{"error": "request too large"}')
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return self._send(400, b'{"error": "bad JSON"}')
                if not isinstance(body, dict):
                    return self._send(400, b'{"error": "send a JSON object"}')
                app = server.app
                if app and (self.path in ("/api/login", "/api/logout", "/api/run", "/api/stop", "/api/mode",
                                          "/api/factory/settings")
                            or self.path.startswith(("/api/device/", "/api/track/"))):
                    return self._setup_post(body)
                if self.path in ("/api/request", "/api/refill", "/api/sim"):
                    if app and not app.running:
                        return self._json(409, {"error": "The factory is not running. Press Start first."})
                    layout = app.layout if app else server.layout
                    parts = app.sim_parts if app else {"car": server.sim_controls, "stations": server.sim_controls}
                    with server._lock:
                        state = server.state
                    try:
                        if self.path == "/api/request":
                            server.bus.publish(P.AI_REQUEST, check_request(body, layout, state), qos=1)
                        elif self.path == "/api/refill":
                            server.bus.publish(P.WAREHOUSE_REFILL, check_refill(body, layout), qos=1)
                        else:
                            if not (parts["car"] or parts["stations"]):
                                return self._json(403, {"error": "simulation controls are off"})
                            msg = check_sim(body, layout, state)
                            if not parts["stations" if msg["cmd"] == "set_stock" else "car"]:
                                return self._json(403, {"error": "That part is real, not simulated."})
                            server.bus.publish(P.SIM_CONTROL, msg)
                    except ValueError as exc:
                        return self._json(400, {"error": str(exc)})
                    return self._send(200, b'{"ok": true}')
                self._send(404, b'{"error": "not found"}')

            def _setup_post(self, body: dict):
                from agv_brain import tracks
                app = server.app
                if self.path == "/api/track/validate":
                    try:
                        return self._json(200, tracks.validate(body.get("track") or {}, app.settings))
                    except Exception as exc:  # a half-drawn track must never crash the page
                        return self._json(200, {"errors": [f"Cannot read this track: {exc}"], "warnings": []})
                if not self.local:
                    return self._json(403, {"error": "Changes can only be made on the laptop itself."})
                try:
                    if self.path == "/api/login":
                        return self._json(200, {"ok": True, "factory": app.login(body.get("name"))})
                    if self.path == "/api/logout":
                        app.logout()
                        return self._json(200, {"ok": True})
                    if not app.factory and self.path in ("/api/run", "/api/mode", "/api/track/save",
                                                         "/api/factory/settings"):
                        return self._json(409, {"error": "Open a factory on the login page first."})
                    if self.path == "/api/run":
                        app.run(body.get("mode"), body.get("speed"))
                        return self._json(200, {"ok": True, "mode": app.mode, "running": app.running})
                    if self.path == "/api/factory/settings":
                        problems = app.save_factory_settings(body)
                        return self._json(200, {"ok": True, "running": app.running, "track_problems": problems})
                    if self.path == "/api/stop":
                        app.stop_session()
                        return self._json(200, {"ok": True, "running": False})
                    if self.path == "/api/mode":
                        app.configure(body.get("mode"), body.get("track"), body.get("speed"))
                        return self._json(200, {"ok": True, "mode": app.mode, "track": app.track,
                                                "running": app.running})
                    if self.path.startswith("/api/device/") and self.path.endswith("/key"):
                        device = self.path.split("/")[3]
                        return self._json(200, {"ok": True, "key": app.new_key(device)})
                    if self.path == "/api/track/save":
                        raw = body.get("track") or {}
                        problems = tracks.validate(raw, app.settings)
                        if problems["errors"]:
                            return self._json(400, {"error": "Fix the problems first.", **problems})
                        name = body.get("name") or ""
                        if tracks.taken(name) and not body.get("overwrite"):
                            return self._json(409, {"error": f'A track named "{name}" already exists.', "exists": True})
                        return self._json(200, {"ok": True, "id": tracks.save(body.get("name") or "", raw)})
                except KeyError as exc:
                    return self._json(400, {"error": f"Unknown device {exc}."})
                except (ValueError, FileNotFoundError) as exc:
                    return self._json(400, {"error": str(exc)})
                except Exception as exc:
                    traceback.print_exc()
                    return self._json(500, {"error": f"Something went wrong: {exc}"})
                return self._json(404, {"error": "not found"})

        self.httpd = ThreadingHTTPServer((host, port), Handler)
        self.url = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}"
        threading.Thread(target=self.httpd.serve_forever, name="dashboard", daemon=True).start()

    def clear(self) -> None:
        """Forget the last state and decision (a factory stopped or is starting)."""
        with self._lock:
            self.state = self.decision = None

    def _on_state(self, topic: str, msg: dict) -> None:
        with self._lock:
            self.state = msg

    def _on_decision(self, topic: str, msg: dict) -> None:
        with self._lock:
            self.decision = msg

    def stop(self) -> None:
        self.httpd.shutdown()
