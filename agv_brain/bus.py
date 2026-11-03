"""Message bus: how the AI, the car, the stations and the dashboard talk.

Two implementations with the same interface:
    MemoryBus   everything in one Python process (simulation, tests, demos)
    MqttBus     a real MQTT broker (Mosquitto on the laptop), for real hardware
plus ScopedBus, one session's removable view of either.

Messages are JSON objects. Topics follow docs/protocol.md, e.g.
    factory/station/S3/stock      factory/car/AGV-1/cmd
"""

from __future__ import annotations

import json
import queue
import threading
import time
from collections.abc import Callable

Handler = Callable[[str, dict], None]


def filter_covers(a: str, b: str) -> bool:
    """True if every topic matched by filter `b` is also matched by filter `a`."""
    pa, pb = a.split("/"), b.split("/")
    for i, part in enumerate(pa):
        if part == "#":
            return True
        if i >= len(pb):
            return False
        if part == "+":
            if pb[i] == "#":
                return False
        elif part != pb[i]:
            return False
    return len(pa) == len(pb)


def topic_matches(pattern: str, topic: str) -> bool:
    """MQTT wildcard matching: '+' is one level, '#' is everything below."""
    p, t = pattern.split("/"), topic.split("/")
    for i, part in enumerate(p):
        if part == "#":
            return True
        if i >= len(t) or (part != "+" and part != t[i]):
            return False
    return len(p) == len(t)


class Clock:
    """Simulation clock: `scale` sim-seconds pass per real second (1 = real time)."""

    def __init__(self, scale: float = 1.0):
        self.scale = scale
        self._t0 = time.monotonic()

    def now(self) -> float:
        return (time.monotonic() - self._t0) * self.scale

    def sleep(self, sim_s: float) -> None:
        if sim_s > 0:
            time.sleep(sim_s / self.scale)


class MemoryBus:
    """In-process broker. Delivery happens on one worker thread, like a real broker,
    so a handler can publish without re-entering other handlers."""

    def __init__(self):
        self._subs: list[tuple[str, Handler]] = []
        self._retained: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._queue: queue.Queue = queue.Queue()
        self._worker = threading.Thread(target=self._run, name="memory-bus", daemon=True)
        self._worker.start()

    def publish(self, topic: str, payload: dict, qos: int = 0, retain: bool = False) -> None:
        payload = json.loads(json.dumps(payload))  # same as going over the wire
        if retain:
            with self._lock:
                self._retained[topic] = payload
        self._queue.put((topic, payload))

    def subscribe(self, pattern: str, handler: Handler) -> None:
        with self._lock:
            self._subs.append((pattern, handler))
            retained = [(t, p) for t, p in self._retained.items() if topic_matches(pattern, t)]
        for t, p in retained:
            self._queue.put((t, p, handler))

    def unsubscribe(self, handler: Handler) -> None:
        with self._lock:
            self._subs = [(p, h) for p, h in self._subs if h is not handler]

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            if len(item) == 3:
                topic, payload, only = item
                targets = [only]
            else:
                topic, payload = item
                with self._lock:
                    targets = [h for pat, h in self._subs if topic_matches(pat, topic)]
            for handler in targets:
                try:
                    handler(topic, payload)
                except Exception as exc:  # a broken handler must not stop the bus
                    print(f"[bus] handler error on {topic}: {exc!r}")
            self._queue.task_done()

    def flush(self, timeout: float = 5.0) -> None:
        """Wait until every queued message has been delivered (for tests)."""
        end = time.monotonic() + timeout
        while self._queue.unfinished_tasks and time.monotonic() < end:
            time.sleep(0.005)

    def close(self) -> None:
        self._queue.put(None)


class MqttBus:
    """Same interface over a real MQTT broker (paho-mqtt).

    A broker sends one copy of a message for every subscription of a client that
    matches it, so overlapping subscriptions (e.g. factory/car/AGV-1/event and
    factory/car/+/event) would deliver everything twice. This class therefore
    subscribes the broker only to filters that don't overlap, and hands each
    message to the right handlers itself.
    """

    def __init__(self, host: str = "localhost", port: int = 1883, client_id: str = "",
                 username: str | None = None, password: str | None = None, tls: bool = False,
                 connect_timeout: float = 5.0):
        import paho.mqtt.client as mqtt

        self._subs: list[tuple[str, Handler]] = []
        self._broker_filters: set[str] = set()   # what the broker is asked for, never overlapping
        self._lock = threading.Lock()
        self._connected = threading.Event()
        self._answered = threading.Event()
        self._refused: str | None = None
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        if username:
            self.client.username_pw_set(username, password)
        if tls:
            self.client.tls_set()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = lambda *a: self._connected.clear()
        self.client.connect(host, port, keepalive=30)
        self.client.loop_start()
        if not self._answered.wait(connect_timeout) or self._refused:
            self.client.loop_stop()
            self.client.disconnect()
            if self._refused:
                raise ConnectionError(f"the MQTT broker at {host}:{port} refused the login ({self._refused})")
            raise ConnectionError(f"no MQTT broker answered at {host}:{port}")

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:          # e.g. a wrong or missing device key
            self._refused = str(reason_code)
            self._answered.set()
            return
        self._answered.set()
        with self._lock:
            filters = set(self._broker_filters)
        for f in filters:  # re-subscribe after a reconnect
            client.subscribe(f, qos=1)
        self._connected.set()

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            print(f"[mqtt] ignored a non-JSON message on {msg.topic}")
            return
        with self._lock:
            targets = [h for pat, h in self._subs if topic_matches(pat, msg.topic)]
        for handler in targets:
            try:
                handler(msg.topic, payload)
            except Exception as exc:
                print(f"[mqtt] handler error on {msg.topic}: {exc!r}")

    def publish(self, topic: str, payload: dict, qos: int = 0, retain: bool = False) -> None:
        self.client.publish(topic, json.dumps(payload), qos=qos, retain=retain)

    def subscribe(self, pattern: str, handler: Handler) -> None:
        with self._lock:
            self._subs.append((pattern, handler))
            if any(filter_covers(f, pattern) for f in self._broker_filters):
                return  # already receiving these messages
            replaced = {f for f in self._broker_filters if filter_covers(pattern, f)}
            self._broker_filters -= replaced
            self._broker_filters.add(pattern)
        self.client.subscribe(pattern, qos=1)
        for f in replaced:
            self.client.unsubscribe(f)

    def unsubscribe(self, handler: Handler) -> None:
        with self._lock:
            self._subs = [(p, h) for p, h in self._subs if h is not handler]

    def flush(self, timeout: float = 5.0) -> None:
        time.sleep(0.2)

    def close(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()


class ScopedBus:
    """One session's view of a shared bus. close() removes every handler the session
    added and drops anything it still publishes, so a stopped session (its controller,
    a simulated car still finishing a move) can never disturb the next one."""

    def __init__(self, bus):
        self.inner = bus
        self._handlers: list[Handler] = []
        self._closed = False

    def publish(self, topic: str, payload: dict, qos: int = 0, retain: bool = False) -> None:
        if not self._closed:
            self.inner.publish(topic, payload, qos=qos, retain=retain)

    def subscribe(self, pattern: str, handler: Handler) -> None:
        if self._closed:
            return

        def scoped(topic: str, payload: dict) -> None:
            if not self._closed:
                handler(topic, payload)

        self._handlers.append(scoped)
        self.inner.subscribe(pattern, scoped)

    def flush(self, timeout: float = 5.0) -> None:
        self.inner.flush(timeout)

    def close(self) -> None:
        self._closed = True
        for h in self._handlers:
            self.inner.unsubscribe(h)
        self._handlers.clear()
