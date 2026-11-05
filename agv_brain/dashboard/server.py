"""Live dashboard: a small web server that shows what the AI sees and decides.

It only listens to the message bus (factory/ai/state and factory/ai/decision),
so it works the same for the simulation and for the real car over MQTT.

    GET  /                 the dashboard page
    GET  /api/snapshot     {"state", "decision", "layout", "sim"} as JSON
    POST /api/request      {"material": "B", "station": "S3"}  manual request
    POST /api/refill       {"material": "A"}  the warehouse rack was restocked
    POST /api/sim          simulation controls (obstacle, stock), simulation only

With an `app` (agv_brain.app.App) it also serves the Setup page:
    GET  /api/setup                mode, track, devices (keys only for the laptop itself)
    GET  /api/track/<id>           a track, for the editor
    POST /api/mode                 {"mode": "real_car", "track": "my-track", "speed": 8}
    POST /api/device/<id>/key      a new key for a device
    POST /api/track/validate       {"track": {...}} -> problems
    POST /api/track/save           {"name": "My track", "track": {...}}
Changes are only accepted from the laptop itself, never from another device on the Wi-Fi.

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
                        data.update(layout=app.layout, layout_version=app.layout_version,
                                    sim=parts["car"] or parts["stations"], sim_parts=parts,
                                    mode={"id": app.mode, "name": app.mode_name}, setup=True)
                    else:
                        data.update(layout=server.layout, layout_version=0, sim=server.sim_controls,
                                    sim_parts={"car": server.sim_controls, "stations": server.sim_controls},
                                    mode=None, setup=False)
                    return self._json(200, data)
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
                if self.path == "/api/request":
                    server.bus.publish(P.AI_REQUEST, {"material": body.get("material"),
                                                      "station": body.get("station")}, qos=1)
                    return self._send(200, b'{"ok": true}')
                if self.path == "/api/refill":
                    msg = {"material": body.get("material")}
                    if body.get("units") is not None:
                        msg["units"] = body["units"]
                    server.bus.publish(P.WAREHOUSE_REFILL, msg, qos=1)
                    return self._send(200, b'{"ok": true}')
                if server.app and self.path.startswith(("/api/mode", "/api/device/", "/api/track/")):
                    return self._setup_post(body)
                if self.path == "/api/sim":
                    if not (server.app.sim_parts["car"] or server.app.sim_parts["stations"]
                            if server.app else server.sim_controls):
                        return self._send(403, b'{"error": "simulation controls are off"}')
                    server.bus.publish(P.SIM_CONTROL, body)
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
                    if self.path == "/api/mode":
                        app.switch(body.get("mode"), body.get("track"), body.get("speed"))
                        return self._json(200, {"ok": True, "mode": app.mode, "track": app.track})
                    if self.path.startswith("/api/device/") and self.path.endswith("/key"):
                        device = self.path.split("/")[3]
                        return self._json(200, {"ok": True, "key": app.new_key(device)})
                    if self.path == "/api/track/save":
                        raw = body.get("track") or {}
                        problems = tracks.validate(raw, app.settings)
                        if problems["errors"]:
                            return self._json(400, {"error": "Fix the problems first.", **problems})
                        return self._json(200, {"ok": True, "id": tracks.save(body.get("name") or "", raw)})
                except (ValueError, KeyError, FileNotFoundError) as exc:
                    return self._json(400, {"error": str(exc).strip("'")})
                except Exception as exc:
                    traceback.print_exc()
                    return self._json(500, {"error": f"Something went wrong: {exc}"})
                return self._json(404, {"error": "not found"})

        self.httpd = ThreadingHTTPServer((host, port), Handler)
        self.url = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}"
        threading.Thread(target=self.httpd.serve_forever, name="dashboard", daemon=True).start()

    def _on_state(self, topic: str, msg: dict) -> None:
        with self._lock:
            self.state = msg

    def _on_decision(self, topic: str, msg: dict) -> None:
        with self._lock:
            self.decision = msg

    def stop(self) -> None:
        self.httpd.shutdown()
