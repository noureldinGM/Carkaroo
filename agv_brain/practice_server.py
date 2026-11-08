"""The Carkaroo Simulator's website (http://localhost:8060): a separate site from the
Carkaroo website, for the pretend car and stations of agv_brain/practice.py.

    GET  /                  the simulator page
    GET  /api/state         the factory, the pretend devices and their state (never the keys)
    POST /api/choose        {"factory": "exhibit-factory"}  the factory floor to pretend
    POST /api/connect       {"device": "AGV-1", "key": "...", "host": "localhost", "port": 1883}
    POST /api/connect-all   {"text": "<Copy all for the simulator>"}
    POST /api/disconnect    {"device": "AGV-1"}  (like pulling its plug)
    POST /api/control       {"cmd": "set_battery", "value": 15} ... the play controls

It keeps the protections of the Carkaroo website (docs/security.md): POSTs only as JSON from
this same site, the Host check against DNS rebinding, the CSP and the other headers, a size
cap, and only web files from its own folder and design/. Every POST is for the laptop only,
because it carries device keys; the keys are never sent back to the page.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agv_brain.dashboard.server import DESIGN, HEADERS, MAX_BODY, TYPES, _names, csp, host_ok
from agv_brain.practice import Practice, parse_paste

STATIC = Path(__file__).resolve().parent / "practice_static"


class PracticeServer:
    def __init__(self, practice: Practice | None = None, host: str = "127.0.0.1", port: int = 8060):
        self.practice = practice or Practice()
        sim = self.practice
        names = _names()

        class Handler(BaseHTTPRequestHandler):
            timeout = 15
            server_version, sys_version = "Carkaroo-Simulator", ""

            def log_message(self, *args):
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

            def do_GET(self):
                if not host_ok(self.headers.get("Host"), names):
                    return self._send(421, b'{"error": "unknown host name; open the simulator by IP address or localhost"}')
                path = self.path.split("?")[0]
                if path == "/api/state":
                    return self._json(200, {**sim.snapshot(), "local": self.local})
                root, name = STATIC, "index.html" if path in ("/", "/index.html") else path.removeprefix("/static/")
                if path.startswith("/design/"):
                    root, name = DESIGN, path.removeprefix("/design").strip("/")
                file = (root / name).resolve()
                if root not in file.parents or not file.is_file() or file.suffix.lower() not in TYPES:
                    return self._send(404, b'{"error": "not found"}')
                self._send(200, file.read_bytes(), TYPES[file.suffix.lower()])

            def do_POST(self):
                if not host_ok(self.headers.get("Host"), names):
                    return self._send(421, b'{"error": "unknown host name"}')
                origin = self.headers.get("Origin")
                if origin is not None and origin.split("://", 1)[-1].lower() != (self.headers.get("Host") or "").lower():
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
                if not self.local:
                    return self._json(403, {"error": "The simulator can only be used on the laptop itself."})
                try:
                    if self.path == "/api/choose":
                        sim.choose(body.get("factory"))
                    elif self.path == "/api/connect":
                        sim.connect(body.get("device"), body.get("key"), body.get("host"), body.get("port"))
                    elif self.path == "/api/connect-all":
                        pasted = parse_paste(body.get("text"))
                        if not sim.factory:
                            raise ValueError("Choose a factory first.")
                        known = [d for d in pasted["keys"] if d in sim.devices]
                        if not known:
                            raise ValueError("None of these devices is in this factory: choose the factory you copied from.")
                        for d in known:
                            sim.connect(d, pasted["keys"][d], pasted.get("host"), pasted.get("port"))
                    elif self.path == "/api/disconnect":
                        sim.disconnect(body.get("device"))
                    elif self.path == "/api/control":
                        sim.control(body)
                    else:
                        return self._json(404, {"error": "not found"})
                except ValueError as exc:
                    return self._json(400, {"error": str(exc)})
                return self._json(200, {"ok": True, **sim.snapshot()})

        self.httpd = ThreadingHTTPServer((host, port), Handler)
        self.url = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}"
        threading.Thread(target=self.httpd.serve_forever, name="simulator", daemon=True).start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.practice.stop()
