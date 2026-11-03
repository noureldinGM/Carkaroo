"""Live dashboard: a small web server that shows what the AI sees and decides.

It only listens to the message bus (factory/ai/state and factory/ai/decision),
so it works the same for the simulation and for the real car over MQTT.

    GET  /                 the dashboard page
    GET  /api/snapshot     {"state", "decision", "layout", "sim"} as JSON
    POST /api/request      {"material": "B", "station": "S3"}  manual request
    POST /api/sim          simulation controls (obstacle, stock), simulation only
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agv_brain import protocol as P
from agv_brain.simulator import Context

STATIC = Path(__file__).resolve().parent / "static"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}


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
            "materials": {m.id: {"name": m.name, "rack": m.rack, "box": m.delivery_qty}
                          for m in s.materials.values()},
            "stations": {st.id: {"name": st.name, "criticality": st.criticality,
                                 "materials": list(st.materials)} for st in s.stations.values()},
            "dock": s.car.dock, "warehouse_low_boxes": s.automation.warehouse_low_boxes}


class DashboardServer:
    def __init__(self, bus, ctx: Context, host: str = "127.0.0.1", port: int = 8050,
                 sim_controls: bool = False):
        self.bus, self.sim_controls = bus, sim_controls
        self.layout = layout_json(ctx)
        self.state: dict | None = None
        self.decision: dict | None = None
        self._lock = threading.Lock()
        bus.subscribe(P.AI_STATE, self._on_state)
        bus.subscribe(P.AI_DECISION, self._on_decision)
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep the terminal quiet
                pass

            def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = self.path.split("?")[0]
                if path == "/api/snapshot":
                    with server._lock:
                        data = {"state": server.state, "decision": server.decision,
                                "layout": server.layout, "sim": server.sim_controls}
                    return self._send(200, json.dumps(data).encode())
                name = "index.html" if path in ("/", "/index.html") else path.removeprefix("/static/")
                file = (STATIC / name).resolve()
                if STATIC not in file.parents or not file.is_file():
                    return self._send(404, b'{"error": "not found"}')
                self._send(200, file.read_bytes(), TYPES.get(file.suffix, "application/octet-stream"))

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                except json.JSONDecodeError:
                    return self._send(400, b'{"error": "bad JSON"}')
                if self.path == "/api/request":
                    server.bus.publish(P.AI_REQUEST, {"material": body.get("material"),
                                                      "station": body.get("station")}, qos=1)
                    return self._send(200, b'{"ok": true}')
                if self.path == "/api/sim":
                    if not server.sim_controls:
                        return self._send(403, b'{"error": "simulation controls are off"}')
                    server.bus.publish(P.SIM_CONTROL, body)
                    return self._send(200, b'{"ok": true}')
                self._send(404, b'{"error": "not found"}')

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
