"""The controller: runs the AI brain on live messages from the factory.

    station stock readings ──> forecaster ──> need detector ──> requests
    car status / events    ──> where the car is, what it is doing
    car idle + requests    ──> Dispatcher.decide() ──> task sent to the car
    obstacle               ──> wait ──> block the line and re-route
    every half second      ──> publish the AI's view (factory/ai/state) for the dashboard

The same controller runs with simulated devices (MemoryBus) or real hardware
(MqttBus + Mosquitto). It only uses messages, so it cannot tell the difference.
"""

from __future__ import annotations

import itertools
import threading
import time
from collections import deque
from dataclasses import dataclass, replace

from agv_brain import protocol as P
from agv_brain.bus import Clock
from agv_brain.dispatcher import Dispatcher
from agv_brain.eventlog import EventLog
from agv_brain.factory_map import Route
from agv_brain.forecaster import ConsumptionForecaster
from agv_brain.models import CarState, FactoryState, Job, Request, initial_state
from agv_brain.need_detector import detect_needs, fmt_s


@dataclass
class ActiveTask:
    task_id: int
    kind: str                     # "delivery" or "charge"
    request: Request | None
    job: Job | None
    legs: list[Route]
    leg: int = 0
    node_index: int = 0           # index in legs[leg].path of the last node reached
    node_time: float = 0.0        # sim time the last node was reached
    sent_s: float = 0.0
    blocked_since: float | None = None
    waiting_action: bool = False  # at the end of a leg, lifting / lowering


class Controller:
    def __init__(self, bus, dispatcher: Dispatcher, clock: Clock, car_id: str = "AGV-1",
                 log: EventLog | None = None, period_s: float = 0.5, preview_every_s: float = 1.5):
        self.bus, self.dispatcher, self.clock = bus, dispatcher, clock
        self.ctx = dispatcher.ctx
        self.car_id, self.log, self.period_s = car_id, log, period_s
        self.preview_every_s = preview_every_s
        s = self.ctx.settings
        self.state: FactoryState = initial_state(s, CarState(s.car.dock, s.car.start_heading, 100.0))
        self.forecaster = ConsumptionForecaster()
        self.requests: dict[str, Request] = {}
        self.active: ActiveTask | None = None
        self.car_mode, self.car_seen = "OFFLINE", -1e9
        self._ids = itertools.count(1)
        self.stats = dict(deliveries=0, decisions=0, reroutes=0, obstacles=0, charges=0,
                          optimizer_agrees=0, regret=0.0, best_cost=0.0)
        self.stopped_s: dict[tuple[str, str], float] = {}
        self._last_reading: dict[tuple[str, str], tuple[float, float]] = {}
        self.blocked_at: dict[frozenset, float] = {}
        self.alerts: deque = deque(maxlen=10)
        self._alert_seen: dict[str, float] = {}
        self.events: deque = deque(maxlen=25)
        self.decision: dict | None = None
        self._last_preview = 0.0
        self._lock = threading.RLock()
        self._stop = threading.Event()

        bus.subscribe(P.station_stock("+"), self.on_stock)
        bus.subscribe(P.car_status(car_id), self.on_status)
        bus.subscribe(P.car_event(car_id), self.on_event)
        bus.subscribe(P.AI_REQUEST, self.on_manual_request)
        bus.subscribe(P.WAREHOUSE_REFILL, self.on_refill)
        self._thread = threading.Thread(target=self._loop, name="controller", daemon=True)
        self._thread.start()

    # -- helpers ---------------------------------------------------------------

    def _event(self, text: str, type_: str = "info", **details) -> None:
        now = self.clock.now()
        self.events.appendleft({"ts": round(now, 1), "type": type_, "text": text})
        if self.log:
            self.log.event(now, "controller", type_, {"text": text, **details})

    def _alert(self, text: str) -> None:
        now = self.clock.now()
        if now - self._alert_seen.get(text, -1e9) < 60:   # same alert at most once a minute
            return
        self._alert_seen[text] = now
        self.alerts.appendleft({"ts": round(now, 1), "text": text})
        self.bus.publish(P.AI_ALERTS, {"ts": round(now, 1), "text": text}, qos=1)
        if self.log:
            self.log.event(now, "controller", "alert", {"text": text})

    def _label(self, material: str, station: str) -> str:
        return f"{material} -> {station} ({self.ctx.settings.stations[station].name})"

    # -- incoming messages -----------------------------------------------------

    def on_stock(self, topic: str, msg: dict) -> None:
        station = topic.split("/")[2]
        material = msg.get("material")
        with self._lock:
            st = self.state.stations.get(station)
            if st is None or material not in st.materials:
                return
            now = self.clock.now()
            stock = float(msg["stock"])
            key = (station, material)
            last = self._last_reading.get(key)
            if last and last[1] <= 0:
                self.stopped_s[key] = self.stopped_s.get(key, 0.0) + (now - last[0])
            self._last_reading[key] = (now, stock)
            sm = st.materials[material]
            sm.stock = stock
            self.forecaster.update(station, material, now, stock)
            base = self.ctx.settings.stations[station].materials[material].rate_per_min
            sm.rate_per_min = self.forecaster.rate_per_min(station, material, base)
            if self.log:
                self.log.reading(now, station, material, stock)

    def on_status(self, topic: str, msg: dict) -> None:
        with self._lock:
            self.car_mode = msg.get("state", "IDLE")
            self.car_seen = self.clock.now()
            if "battery" in msg:
                self.state.car = replace(self.state.car, battery_pct=float(msg["battery"]))

    def on_event(self, topic: str, msg: dict) -> None:
        with self._lock:
            now = self.clock.now()
            a = self.active
            kind = msg.get("type")
            if a is None or msg.get("task_id") != a.task_id:
                if kind == "error":
                    self._alert(f"Car error: {msg.get('reason', 'unknown')}")
                return
            if kind == "node":
                leg = int(msg.get("leg", a.leg))
                route = a.legs[leg]
                idx = int(msg["node_index"])
                if not 0 < idx < len(route.path):
                    self._alert(f"Car reported node {idx}, but the route has {len(route.path) - 1}. "
                                "Stopping it to check its position.")
                    self.bus.publish(P.car_cmd(self.car_id), {"type": "stop"}, qos=1)
                    return
                node, prev = route.path[idx], route.path[idx - 1]
                heading = self.ctx.fmap.neighbors(prev)[node][0]
                self.state.car = CarState(node, heading, self.state.car.battery_pct)
                a.leg, a.node_index, a.node_time = leg, idx, now
                a.waiting_action = idx == len(route.path) - 1
            elif kind == "done":
                action = msg.get("action")
                # MQTT QoS 1 is "at least once": ignore a repeated done for a leg already finished
                if action in ("LIFT", "LOWER") and int(msg.get("leg", a.leg)) != a.leg:
                    return
                if action == "LIFT":
                    qty = self.ctx.settings.materials[a.job.material].delivery_qty
                    self.state.warehouse[a.job.material] -= qty
                    a.leg, a.node_index, a.node_time, a.waiting_action = 1, 0, now, False
                    self._event(f"Picked up {a.job.material} at {a.job.rack}", "pickup")
                elif action == "LOWER":
                    qty = self.ctx.settings.materials[a.job.material].delivery_qty
                    sm = self.state.stations[a.job.station].materials[a.job.material]
                    sm.stock += qty  # the load cell will confirm it with its next reading
                    self.stats["deliveries"] += 1
                    took = now - a.sent_s
                    self._event(f"Delivered {qty} {a.job.material} to {a.job.station} "
                                f"({fmt_s(took)} after the order)", "delivered", took_s=round(took, 1))
                    self.active = None
                elif action == "CHARGE":
                    self._event("At the dock: charging", "charging")
                    self.active = None
            elif kind == "obstacle":
                a.blocked_since = now
                self.stats["obstacles"] += 1
                route = a.legs[a.leg]
                edge = route.path[a.node_index:a.node_index + 2]
                self._event(f"Obstacle between {' and '.join(edge)}: car stopped", "obstacle")
                self._alert(f"Obstacle on the line {'-'.join(edge)}. Waiting "
                            f"{fmt_s(self.ctx.settings.automation.obstacle_wait_s)} before re-routing.")
            elif kind == "clear":
                if a.blocked_since is not None:
                    a.blocked_since = None
                    self.bus.publish(P.car_cmd(self.car_id), {"type": "resume", "task_id": a.task_id}, qos=1)
                    self._event("Obstacle cleared: car continues", "clear")
            elif kind == "error":
                self._alert(f"Car error: {msg.get('reason', 'unknown')}")

    def on_manual_request(self, topic: str, msg: dict) -> None:
        with self._lock:
            material, station = msg.get("material"), msg.get("station")
            st = self.state.stations.get(station)
            if st is None or material not in st.materials:
                self._alert(f"Manual request ignored: {station} does not use {material}.")
                return
            if self._is_open(station, material):
                self._alert(f"{material} for {station} is already requested.")
                return
            now = self.clock.now()
            r = Request(f"manual-{material}@{station}-{now:.0f}", material, station, now)
            self.requests[r.id] = r
            self._event(f"Manual request: {self._label(material, station)}", "request")

    def on_refill(self, topic: str, msg: dict) -> None:
        """The warehouse has no sensor: a person reports a refill (the dashboard button).
        Without "units" the rack goes back to its full stock from config/materials.yaml."""
        with self._lock:
            m = msg.get("material")
            material = self.ctx.settings.materials.get(m)
            if material is None:
                self._alert(f"Refill ignored: unknown material {m}.")
                return
            try:
                units = int(msg.get("units", material.warehouse_stock))
            except (TypeError, ValueError):
                self._alert(f"Refill ignored: bad number of units for {m}.")
                return
            self.state.warehouse[m] = max(0, units)
            box = material.delivery_qty
            self._event(f"Warehouse refilled: {units} {m} ({units // box} boxes)", "refill")

    def _is_open(self, station: str, material: str) -> bool:
        if any(r.station == station and r.material == material for r in self.requests.values()):
            return True
        a = self.active
        return bool(a and a.job and a.job.station == station and a.job.material == material)

    # -- the loop --------------------------------------------------------------

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as exc:
                print(f"[controller] tick error: {exc!r}")
            time.sleep(self.period_s)

    def tick(self) -> None:
        with self._lock:
            now = self.clock.now()
            self.state.now_s = now
            self._expire_blocks(now)
            self._handle_obstacle(now)
            self._detect(now)
            if self.active is None and self.car_mode == "IDLE" and now - self.car_seen < 5:
                self._dispatch(now)
            elif self.requests and time.monotonic() - self._last_preview > self.preview_every_s:
                self._preview(now)
            self.bus.publish(P.AI_STATE, self.snapshot(now), retain=True)

    def _expire_blocks(self, now: float) -> None:
        for edge, t in list(self.blocked_at.items()):
            if now - t > self.ctx.settings.automation.block_expiry_s:
                self.ctx.fmap.unblock_edge(*edge)
                del self.blocked_at[edge]
                self._event(f"Line {'-'.join(sorted(edge))} will be tried again", "unblock")

    def _handle_obstacle(self, now: float) -> None:
        a = self.active
        if a is None or a.blocked_since is None:
            return
        if now - a.blocked_since < self.ctx.settings.automation.obstacle_wait_s:
            return
        route = a.legs[a.leg]
        last, nxt = route.path[a.node_index], route.path[a.node_index + 1]
        try:
            new = self.ctx.fmap.reroute_from_edge(last, nxt, route.path[-1])
        except ValueError:
            # no way around: forget the block (the car is still on that line) and keep waiting
            self.ctx.fmap.unblock_edge(last, nxt)
            a.blocked_since = now
            self._alert(f"No way around the obstacle on {last}-{nxt}. Please clear the line.")
            return
        self.blocked_at[frozenset((last, nxt))] = now
        a.legs[a.leg] = new
        a.node_index, a.node_time, a.blocked_since = 0, now, None
        self.stats["reroutes"] += 1
        self.bus.publish(P.car_cmd(self.car_id), P.reroute_message(a.task_id, a.leg, new), qos=1)
        self._event(f"Re-routed around {last}-{nxt}: {' > '.join(new.path[1:])}", "reroute")

    def _detect(self, now: float) -> None:
        open_reqs = list(self.requests.values())
        if self.active and self.active.request:
            open_reqs.append(self.active.request)
        report = detect_needs(self.ctx, self.state, open_reqs)
        for need in report.needs:
            r = need.request
            if not self._is_open(r.station, r.material):
                self.requests[r.id] = r
                self._event(f"Needs {self._label(r.material, r.station)}: {need.reason}", "request")
        for text in report.alerts:
            self._alert(text)

    def _decide(self, now: float):
        reqs = list(self.requests.values())
        decision = self.dispatcher.decide(self.state, reqs)
        jobs = [t.job for t in decision.tasks]
        msg = P.decision_message(self.ctx, decision, self.state.car, now, jobs, self.requests)
        return decision, msg

    def _preview(self, now: float) -> None:
        """While the car is busy: show what the AI would choose next."""
        self._last_preview = time.monotonic()
        _, msg = self._decide(now)
        msg["preview"] = True
        self.decision = msg
        self.bus.publish(P.AI_DECISION, msg, retain=True)

    def _dispatch(self, now: float) -> None:
        if not self.requests:
            return
        decision, msg = self._decide(now)
        for text in decision.alerts:
            self._alert(text)
        if not decision.tasks and not decision.charge_first:
            # nothing can be served (e.g. the warehouse is empty): still show the dashboard why
            if time.monotonic() - self._last_preview > self.preview_every_s:
                self._last_preview = time.monotonic()
                msg["preview"] = True
                self.decision = msg
                self.bus.publish(P.AI_DECISION, msg, retain=True)
            return
        msg["preview"] = False
        self.decision = msg
        self.stats["decisions"] += 1
        self.stats["optimizer_agrees"] += int(msg["optimizer_agrees"])
        self.stats["regret"] = round(self.stats["regret"] + msg["regret"], 2)
        self.stats["best_cost"] = round(self.stats["best_cost"] + (msg["best_cost"] or 0.0), 2)
        self.bus.publish(P.AI_DECISION, msg, retain=True)
        if self.log:
            self.log.decision(now, msg)
        task_id = next(self._ids)
        if decision.charge_first:
            route = decision.charge_route
            self.active = ActiveTask(task_id, "charge", None, None, [route], sent_s=now, node_time=now)
            self.stats["charges"] += 1
            self.bus.publish(P.car_cmd(self.car_id), P.charge_message(task_id, route), qos=1)
            self._event(f"Battery low: going to {route.path[-1]} to charge", "charge")
            return
        t = decision.first
        request = self.requests.pop(t.job.id)
        self.active = ActiveTask(task_id, "delivery", request, t.job, [t.to_rack, t.to_station],
                                 sent_s=now, node_time=now)
        self.bus.publish(P.car_cmd(self.car_id), P.task_message(task_id, t.job, t.to_rack, t.to_station), qos=1)
        why = decision.reasons[0] if decision.reasons else ""
        self._event(f"Task {task_id}: {self._label(t.job.material, t.job.station)} first. {why}", "task",
                    task_id=task_id)

    # -- what the dashboard sees -------------------------------------------------

    def snapshot(self, now: float | None = None) -> dict:
        with self._lock:
            now = self.clock.now() if now is None else now
            car = self.state.car
            task = None
            a = self.active
            if a:
                route = a.legs[a.leg]
                edge, progress = None, 0.0
                if a.node_index < len(route.path) - 1 and not a.waiting_action:
                    frm, to = route.path[a.node_index], route.path[a.node_index + 1]
                    if a.blocked_since is None:
                        heading, length = self.ctx.fmap.neighbors(frm)[to]
                        edge_s = (self.ctx.fmap.turn_cost(route.commands[a.node_index])
                                  + length / self.ctx.settings.car.speed_cm_s)
                        progress = min(0.97, max(0.0, (now - a.node_time) / max(edge_s, 0.1)))
                    else:
                        progress = 0.5
                    edge = [frm, to]
                task = {"task_id": a.task_id, "kind": a.kind,
                        "material": a.job.material if a.job else None,
                        "station": a.job.station if a.job else None,
                        "leg": a.leg, "node_index": a.node_index,
                        "legs": [P.route_dict(r) for r in a.legs],
                        "edge": edge, "edge_progress": round(progress, 3),
                        "blocked": a.blocked_since is not None, "waiting_action": a.waiting_action,
                        "age_s": round(now - a.sent_s, 1)}
            stations = {}
            for sid, st in self.state.stations.items():
                mats = {}
                for mid, sm in st.materials.items():
                    rate = sm.rate_per_min / 60.0
                    mats[mid] = {"stock": round(sm.stock, 1), "rate_per_min": round(sm.rate_per_min, 2),
                                 "safety_stock": sm.safety_stock, "capacity": sm.capacity,
                                 "stockout_s": round(sm.stock / rate, 1) if rate > 0 else None,
                                 "stopped_s": round(self.stopped_s.get((sid, mid), 0.0), 1),
                                 "requested": self._is_open(sid, mid)}
                stations[sid] = {"name": st.name, "criticality": st.criticality, "materials": mats}
            return {
                "ts": round(now, 1), "scale": self.clock.scale, "policy": self.dispatcher.policy,
                "car": {"node": car.node, "heading": car.heading, "battery": round(car.battery_pct, 1),
                        "mode": self.car_mode, "online": now - self.car_seen < 5, "task": task},
                "stations": stations, "warehouse": dict(self.state.warehouse),
                "requests": [{"id": r.id, "material": r.material, "station": r.station,
                              "waiting_s": round(now - r.created_s, 1), "auto": r.id.startswith("auto-")}
                             for r in self.requests.values()],
                "blocked": [sorted(e) for e in self.blocked_at],
                "stats": dict(self.stats), "alerts": list(self.alerts), "events": list(self.events),
            }

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
