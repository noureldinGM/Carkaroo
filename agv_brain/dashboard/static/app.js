// Capstone AVG live dashboard: polls /api/snapshot and draws what the AI sees and decides.
"use strict";

const $ = (s) => document.querySelector(s);
const SVGNS = "http://www.w3.org/2000/svg";
const OUT = { N: [0, -1], E: [1, 0], S: [0, 1], W: [-1, 0] };
const ANGLE = { N: -90, E: 0, S: 90, W: 180 };
const SPUR = 30;              // gap between a line end and its box, in map units

let layout = null;
let sim = false;
let nodes = {};
let map = {};                 // svg layers and per-node box elements
const obstacles = new Map();  // "A|B" -> sim time it disappears (obstacles this page placed)
let lastTs = 0;
let lastSnap = null;

// ---------- helpers ----------
function esc(t) {
  return String(t).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function fmtS(s) {
  if (s === null || s === undefined) return "–";
  if (!isFinite(s)) return "never";
  return Math.abs(s) < 90 ? `${Math.round(s)} s` : `${(s / 60).toFixed(1)} min`;
}
function clock(s) {
  const m = Math.floor(s / 60), sec = Math.floor(s % 60);
  return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}
function sv(tag, attrs = {}, parent = null) {
  const e = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}
function stationName(id) { return layout.stations[id] ? layout.stations[id].name : id; }
async function post(url, body) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  return r.ok;
}

// ---------- map (built once) ----------
// compact boxes: the stations panel below the map has the full details
function boxSize(n) {
  if (n.type === "station") return [128, 26 + 16 * layout.stations[n.id].materials.length];
  if (n.type === "rack") return [84, 40];
  return [76, 30];
}

// Place the boxes of line ends (racks, stations, dock) outside the track and push
// apart the ones that would overlap, so close line ends stay readable.
function placeBoxes() {
  const boxes = layout.nodes.filter((n) => n.type !== "junction").map((n) => {
    const [w, h] = boxSize(n);
    const [dx, dy] = OUT[n.out || "S"];
    const p = nodes[n.id];
    return { n, w, h, dx, dy, cx: p.x + dx * (SPUR + w / 2), cy: p.y + dy * (SPUR + h / 2) };
  });
  const GAP = 12;
  for (let it = 0; it < 80; it++) {
    let moved = false;
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i], b = boxes[j];
        const ox = (a.w + b.w) / 2 + GAP - Math.abs(a.cx - b.cx);
        const oy = (a.h + b.h) / 2 + GAP - Math.abs(a.cy - b.cy);
        if (ox <= 0 || oy <= 0) continue;
        moved = true;
        if (a.dy !== 0 && b.dy !== 0) {            // both above/below the track: spread sideways
          const s = (a.cx <= b.cx ? -1 : 1) * ox / 2;
          a.cx += s; b.cx -= s;
        } else if (a.dx !== 0 && b.dx !== 0) {     // both left/right of the track: spread up/down
          const s = (a.cy <= b.cy ? -1 : 1) * oy / 2;
          a.cy += s; b.cy -= s;
        } else {                                   // different sides: move the side box outward
          const m = a.dx !== 0 ? a : b;
          m.cx += m.dx * ox; m.cy += m.dy * oy;
        }
      }
    }
    if (!moved) break;
  }
  return boxes;
}

function buildMap() {
  const svg = $("#map");
  svg.innerHTML = "";
  // scale the track so a typical line is ~70 map units long (1 map unit ~ 1 screen pixel)
  const lengths = layout.edges.map(([a, b]) => {
    const A = layout.nodes.find((n) => n.id === a), B = layout.nodes.find((n) => n.id === b);
    return Math.abs(A.x - B.x) + Math.abs(A.y - B.y);
  }).sort((p, q) => p - q);
  const K = Math.min(4, Math.max(0.3, 70 / lengths[Math.floor(lengths.length / 2)]));
  for (const n of layout.nodes) nodes[n.id] = { ...n, x: n.x * K, y: n.y * K };
  const layer = (cls) => sv("g", { class: cls }, svg);
  map = { edges: layer("edges"), routes: layer("routes"), marks: layer("marks"), boxes: layer("boxes"), car: null, box: {} };
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  const grow = (x, y) => { minX = Math.min(minX, x); minY = Math.min(minY, y); maxX = Math.max(maxX, x); maxY = Math.max(maxY, y); };
  const placed = Object.fromEntries(placeBoxes().map((b) => [b.n.id, b]));

  for (const [a, b] of layout.edges) {
    const A = nodes[a], B = nodes[b];
    const g = sv("g", {}, map.edges);
    const hit = sv("line", { x1: A.x, y1: A.y, x2: B.x, y2: B.y, class: "hit" }, g);
    const line = sv("line", { x1: A.x, y1: A.y, x2: B.x, y2: B.y, class: "track" }, g);
    hit.addEventListener("click", () => placeObstacle(a, b));
    hit.addEventListener("mouseenter", () => sim && line.classList.add("hover"));
    hit.addEventListener("mouseleave", () => line.classList.remove("hover"));
    sv("title", {}, hit).textContent = sim ? `Line ${a}–${b}: click to put an obstacle here` : `Line ${a}–${b}`;
  }
  for (const raw of layout.nodes) {
    const n = nodes[raw.id];
    grow(n.x, n.y);
    if (n.type === "junction") {
      sv("circle", { cx: n.x, cy: n.y, r: 7, class: "junction" }, map.edges);
      sv("text", { x: n.x + 9, y: n.y - 9, class: "node-label" }, map.edges).textContent = n.id;
      continue;
    }
    const { w, h, dx, dy, cx, cy } = placed[n.id];
    const x = cx - w / 2, y = cy - h / 2;
    grow(x, y); grow(x + w, y + h);
    // connector: out from the line end, then across to the (possibly shifted) box
    const mx = n.x + dx * SPUR / 2, my = n.y + dy * SPUR / 2;
    const ex = dx !== 0 ? cx - dx * w / 2 : cx, ey = dy !== 0 ? cy - dy * h / 2 : cy;
    const elbow = dx !== 0 ? `${mx},${ey}` : `${ex},${my}`;
    sv("polyline", { points: `${n.x},${n.y} ${mx},${my} ${elbow} ${ex},${ey}`, class: "spur", fill: "none" }, map.boxes);
    sv("circle", { cx: n.x, cy: n.y, r: 5, class: "junction" }, map.boxes);
    const g = sv("g", { transform: `translate(${x},${y})` }, map.boxes);
    const rect = sv("rect", { width: w, height: h, rx: 8, class: "box" }, g);
    const title = sv("text", { x: 8, y: n.type === "dock" ? 20 : 17, class: "box-title" }, g);
    const sub = sv("text", { x: 8, y: 32, class: "box-sub" }, g);
    const entry = { rect, title, sub, bars: {} };
    if (n.type === "station") {
      const st = layout.stations[n.id];
      title.textContent = n.id;
      sv("text", { x: 30, y: 17, class: "box-sub" }, g).textContent = st.name.length > 15 ? st.name.slice(0, 14) + "…" : st.name;
      sv("title", {}, g).textContent = `${n.id} · ${st.name}`;
      st.materials.forEach((m, i) => {
        const yy = 24 + 16 * i;
        sv("text", { x: 8, y: yy + 10, class: "box-sub" }, g).textContent = m;
        sv("rect", { x: 22, y: yy + 2, width: 60, height: 8, rx: 4, class: "bar-bg" }, g);
        const bar = sv("rect", { x: 22, y: yy + 2, width: 0, height: 8, rx: 4, class: "bar ok" }, g);
        const safety = sv("line", { x1: 22, y1: yy, x2: 22, y2: yy + 12, class: "safety" }, g);
        const num = sv("text", { x: 88, y: yy + 10, class: "box-sub" }, g);
        entry.bars[m] = { bar, safety, num };
      });
    } else if (n.type === "rack") {
      const m = Object.keys(layout.materials).find((k) => layout.materials[k].rack === n.id);
      entry.material = m;
      title.textContent = n.id;
      sv("title", {}, g).textContent = m ? `Rack for ${m} · ${layout.materials[m].name}` : n.id;
    } else {
      title.textContent = `${n.id} ⚡`;
      sv("title", {}, g).textContent = "Charging dock";
    }
    map.box[n.id] = entry;
  }
  const pad = 24;
  svg.setAttribute("viewBox", `${minX - pad} ${minY - pad} ${maxX - minX + 2 * pad} ${maxY - minY + 2 * pad}`);

  // the car
  const car = sv("g", { class: "car" }, svg);
  const body = sv("g", {}, car);
  sv("rect", { x: -20, y: -14, width: 40, height: 28, rx: 7, class: "car-body" }, body);
  sv("path", { d: "M 22 -10 L 34 0 L 22 10 Z", class: "car-body" }, body);
  const cargo = sv("g", {}, car);
  sv("rect", { x: -10, y: -10, width: 20, height: 20, rx: 3, class: "cargo" }, cargo);
  const cargoText = sv("text", { x: 0, y: 4, "text-anchor": "middle", class: "cargo-text" }, cargo);
  const label = sv("text", { x: 0, y: 34, "text-anchor": "middle", class: "car-label" }, car);
  map.car = { g: car, body, cargo, cargoText, label };
  $("#map-hint").textContent = sim ? "Click a line to block it with an obstacle" : "";
}

function placeObstacle(a, b) {
  if (!sim) return;
  if (!confirm(`Put an obstacle on the line ${a}–${b} for 60 simulated seconds?\nThe car stops there; if it is still blocked, the AI re-routes.`)) return;
  post("/api/sim", { cmd: "obstacle", edge: [a, b], duration_s: 60 });
  obstacles.set(`${a}|${b}`, lastTs + 60);
}

const MODE_COLOR = { IDLE: "var(--surface-2)", DRIVING: "var(--accent)", LIFTING: "var(--leg1)", LOWERING: "var(--leg1)",
  BLOCKED: "var(--crit)", CHARGING: "var(--charge)", ERROR: "var(--crit)", OFFLINE: "var(--border)" };

function renderMap(state) {
  // stations & racks
  for (const [sid, st] of Object.entries(state.stations)) {
    const e = map.box[sid];
    if (!e) continue;
    let stopped = false, requested = false;
    for (const [m, v] of Object.entries(st.materials)) {
      const b = e.bars[m];
      if (!b) continue;
      const frac = Math.max(0, Math.min(1, v.stock / v.capacity));
      b.bar.setAttribute("width", (60 * frac).toFixed(1));
      b.bar.setAttribute("class", `bar ${v.stock <= 0 ? "out" : v.stock < v.safety_stock ? "low" : "ok"}`);
      const sx = 22 + 60 * Math.min(1, v.safety_stock / v.capacity);
      b.safety.setAttribute("x1", sx); b.safety.setAttribute("x2", sx);
      b.num.textContent = `${Math.round(v.stock)}/${v.capacity}`;
      stopped ||= v.stock <= 0; requested ||= v.requested;
    }
    e.rect.setAttribute("class", `box${stopped ? " stopped" : requested ? " requested" : ""}`);
  }
  for (const e of Object.values(map.box)) {
    if (e.material) e.sub.textContent = `${e.material} · ${state.warehouse[e.material]} left`;
  }

  // routes, blocked lines, obstacles
  map.routes.innerHTML = "";
  map.marks.innerHTML = "";
  const task = state.car.task;
  const pts = (path) => path.map((id) => `${nodes[id].x},${nodes[id].y}`).join(" ");
  if (task) {
    task.legs.forEach((leg, i) => {
      if (i < task.leg) return;
      const cls = task.kind === "charge" ? "charge" : `leg${i}`;
      sv("polyline", { points: pts(leg.path), class: `route ${cls}${i > task.leg ? " later" : ""}` }, map.routes);
    });
  }
  for (const [a, b] of state.blocked) {
    const A = nodes[a], B = nodes[b];
    sv("line", { x1: A.x, y1: A.y, x2: B.x, y2: B.y, class: "blocked" }, map.marks);
  }
  for (const [key, until] of obstacles) {
    if (until < state.ts) { obstacles.delete(key); continue; }
    const [a, b] = key.split("|"), A = nodes[a], B = nodes[b];
    const x = (A.x + B.x) / 2, y = (A.y + B.y) / 2;
    sv("path", { d: `M ${x} ${y - 16} L ${x + 15} ${y + 11} L ${x - 15} ${y + 11} Z`, class: "obstacle" }, map.marks);
    sv("text", { x, y: y + 7, "text-anchor": "middle", class: "obstacle-text" }, map.marks).textContent = "!";
  }

  // car position: along the current line, or at its node
  const car = state.car;
  let x = nodes[car.node].x, y = nodes[car.node].y, heading = car.heading;
  if (task && task.edge) {
    const A = nodes[task.edge[0]], B = nodes[task.edge[1]];
    const p = task.edge_progress;
    x = A.x + (B.x - A.x) * p; y = A.y + (B.y - A.y) * p;
    heading = B.x > A.x ? "E" : B.x < A.x ? "W" : B.y > A.y ? "S" : "N";
  }
  map.car.g.style.transform = `translate(${x}px, ${y}px)`;
  map.car.body.setAttribute("transform", `rotate(${ANGLE[heading] ?? 0})`);
  map.car.body.querySelectorAll(".car-body").forEach((e) => e.setAttribute("fill", MODE_COLOR[car.mode] || "var(--accent)"));
  const carrying = task && task.kind === "delivery" && task.leg === 1;
  map.car.cargo.style.display = carrying ? "" : "none";
  map.car.cargoText.textContent = carrying ? task.material : "";
  map.car.label.textContent = `${car.mode.toLowerCase()} · ${Math.round(car.battery)}%`;
}

// ---------- the big answer + simple queue ----------
const CAR_DOING = {
  IDLE: "is waiting for a task", DRIVING: "is driving", LIFTING: "is lifting a box", LOWERING: "is putting a box down",
  BLOCKED: "is stopped by an obstacle", CHARGING: "is charging", ERROR: "has a problem", OFFLINE: "is offline",
};

function carSentence(state) {
  const car = state.car, t = car.task;
  if (!car.online) return "The car is offline.";
  if (t && t.kind === "delivery") {
    const where = t.leg === 0 ? `to rack ${t.legs[0].path.at(-1)} to pick up ${t.material}` : `${t.material} to ${t.station}`;
    return t.blocked ? `The car is stopped by an obstacle while taking ${where}.` : `The car is ${t.leg === 0 ? "driving" : "carrying"} ${where}.`;
  }
  if (t && t.kind === "charge") return "The car is going to the dock to charge.";
  return `The car ${CAR_DOING[car.mode] || car.mode.toLowerCase()} at ${car.node}.`;
}

function renderAI(dec, state) {
  const now = $("#now"), list = $("#queue");
  if (!dec || !dec.queue || dec.queue.length === 0) {
    const waiting = state.requests.length;
    // requests are open but the safety rules let none through (empty warehouse, blocked line, ...)
    const reasons = [...new Set((dec && dec.alerts) || [])];
    now.innerHTML = waiting ? `<div class="now-label">${state.car.task ? "AI's next choice (when the car is free)" : "AI's choice"}</div>
      <div class="now-main">Can't serve the waiting request${waiting > 1 ? "s" : ""}</div>
      <p class="now-why">${waiting} request${waiting > 1 ? "s are" : " is"} waiting, but the safety rules stop the car:</p>
      <ul class="why now-blocked">${reasons.map((a) => `<li>${esc(a)}</li>`).join("") || "<li>Checking again…</li>"}</ul>
      <div class="now-car">${esc(carSentence(state))}</div>`
    : `<div class="now-label">AI's choice</div>
      <div class="now-main">Nothing to deliver right now</div>
      <p class="now-why">Every station has enough stock. The AI asks for a delivery by itself as soon as
        a station would run low before the car could get there.</p>
      <div class="now-car">${esc(carSentence(state))}</div>`;
    list.innerHTML = "";
    $("#ai-numbers").innerHTML = "";
    return;
  }
  // the AI score ranks every request for the *next* delivery; show them in that order
  const first = dec.queue[0];
  const q = first.score === null ? dec.queue : [...dec.queue].sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  const pct = dec.best_cost ? (100 * dec.regret / dec.best_cost) : 0;
  const badge = dec.optimizer_agrees
    ? `<span class="badge good">✓ Best possible choice</span>`
    : `<span class="badge warn">≈ Almost best (${pct.toFixed(1)}% more cost than the best)</span>`;
  const stopsAnyway = first.slack_s < 0;
  const costs = q.map((r) => r.cost_if_first).filter((c) => c !== null && c !== undefined);
  const bestEntry = costs.length ? q.find((r) => r.cost_if_first === Math.min(...costs)) : null;
  const verdict = q.length < 2 ? ""
    : dec.optimizer_agrees ? "Serving it first keeps the lines running at the lowest cost."
    : bestEntry ? `The exact optimizer would start with ${bestEntry.material} → ${bestEntry.station} instead.` : "";
  now.innerHTML = `
    <div class="now-label">${dec.preview ? "AI's next choice (when the car is free)" : "AI's choice"}</div>
    <div class="now-main"><span>Bring</span><span class="mat">${esc(first.material)}</span>
      <span>to ${esc(first.station)} · ${esc(first.station_name)}</span> ${badge}</div>
    <p class="now-why">Why: ${esc(first.station_name)} has ${Math.round(first.stock)} ${esc(first.material)} left and runs out in
      <b>${fmtS(first.stockout_s)}</b>; the trip takes ${fmtS(first.trip_s)}.
      ${stopsAnyway ? "It will stop for a short time even if served now, so it cannot wait. " : ""}${esc(verdict)}</p>
    ${dec.charge_first ? `<p class="badge crit">⚡ The battery is too low: the car charges first</p>` : ""}
    <div class="now-car">${esc(carSentence(state))}</div>`;
  list.innerHTML = q.length < 2 ? "" : q.map((r, i) => {
    const urgent = r.slack_s < 60;
    return `<li class="${r.request_id === first.request_id ? "first" : ""}">
      <span class="n">${i + 1}</span><span class="mat">${esc(r.material)}</span>
      <span><span class="q-main">${esc(r.station)} · ${esc(r.station_name)}</span>
        <span class="q-sub${urgent ? " urgent" : ""}">runs out in ${fmtS(r.stockout_s)}</span></span></li>`;
  }).join("");
  renderNumbers(dec, q, first);
}

// the detailed numbers, behind "Show the AI's numbers"
function renderNumbers(dec, q, first) {
  if (!$("#details").open) return;  // nothing to update while it is closed
  // a request's AI score = how many of the other requests it should go before (sum of pairwise wins)
  const others = q.length - 1;
  const costs = q.map((r) => r.cost_if_first).filter((c) => c !== null && c !== undefined);
  const maxCost = Math.max(1e-9, ...costs), minCost = Math.min(...costs);
  const rows = q.map((r, i) => {
    const score = r.score === null || others === 0 ? "–" : `<div class="mini"><div class="track-bar"><div class="fill" style="width:${(100 * r.score / others).toFixed(0)}%"></div></div>${r.score.toFixed(1)} of ${others}</div>`;
    const isBest = r.cost_if_first === minCost;
    const cost = r.cost_if_first === null || r.cost_if_first === undefined ? "–"
      : `<div class="mini"><div class="track-bar"><div class="fill cost${isBest ? " best" : ""}" style="width:${(100 * r.cost_if_first / maxCost).toFixed(0)}%"></div></div>${r.cost_if_first.toFixed(0)}${isBest ? " ★" : ""}</div>`;
    return `<tr class="${r.request_id === first.request_id ? "first" : ""}">
      <td class="rank">${i + 1}</td>
      <td><span class="mat">${esc(r.material)}</span><span class="req-name">${esc(r.station)}</span>
        <span class="req-sub">criticality ${r.criticality} · ${r.auto ? "automatic" : "manual"}, waited ${fmtS(r.wait_s)}</span></td>
      <td>${score}</td>
      <td class="num">${fmtS(r.stockout_s)}<span class="req-sub">trip ${fmtS(r.trip_s)}</span></td>
      <td class="num ${r.slack_s < 0 ? "neg" : ""}">${fmtS(r.slack_s)}</td>
      <td>${cost}</td></tr>`;
  }).join("");
  $("#ai-numbers").innerHTML = `
    <div class="table-wrap"><table class="queue">
      <thead><tr>
        <th>#</th><th>Request</th>
        <th title="ML ranker: how many of the other requests this one should go before (higher = sooner)">AI score</th>
        <th title="Time until the station runs out, and the trip time">Empty in</th>
        <th title="Empty-in minus trip time. Negative: the line stops even if served now">Slack</th>
        <th title="Exact optimizer: total cost of the best plan that starts with this request (lower is better, ★ = best)">Cost if first</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table></div>
    <ul class="why">${dec.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
    <p class="explain">AI score: the ML ranker compares every pair of requests; "3.8 of 4" means it should go
      before about 3.8 of the 4 others. The highest goes first, and the AI decides again after every delivery.
      Cost if first: the exact optimizer
      tries every possible order and counts line-stop time × criticality, time below safety stock, waiting and driving.
      Policy: ${dec.policy === "ml" ? "ML ranker" : esc(dec.policy)}, decided at ${clock(dec.ts)}.</p>`;
}

// ---------- stations, feed, header ----------
function renderStations(state) {
  const t = state.car.task;
  const onTheWay = t && t.kind === "delivery" ? `${t.station}:${t.material}` : null;
  $("#stations").innerHTML = Object.entries(state.stations).map(([sid, st]) => {
    const anyOut = Object.values(st.materials).some((v) => v.stock <= 0);
    const mats = Object.entries(st.materials).map(([m, v]) => {
      const frac = Math.max(0, Math.min(1, v.stock / v.capacity));
      const cls = v.stock <= 0 ? "out" : v.stock < v.safety_stock ? "low" : "ok";
      const note = v.stock <= 0 ? `<span class="tag out">✕ stopped</span>`
        : onTheWay === `${sid}:${m}` ? `<span class="tag req">on the way</span>` : "";
      return `<div class="mrow"><span class="mat">${esc(m)}</span>
          <div class="sbar" role="img" aria-label="${esc(m)}: ${Math.round(v.stock)} of ${v.capacity}">
            <div class="fill ${cls}" style="width:${(100 * frac).toFixed(1)}%"></div>
            <div class="safety" style="left:${(100 * Math.min(1, v.safety_stock / v.capacity)).toFixed(1)}%"></div></div>
          <span class="mnum">${Math.round(v.stock)}</span></div>
        <div class="mmeta"><span>empty in ${fmtS(v.stockout_s)}</span>${note}</div>`;
    }).join("");
    return `<div class="station${anyOut ? " stopped" : ""}"><h3><span>${esc(sid)} · ${esc(st.name)}</span></h3>${mats}</div>`;
  }).join("");
}

const ICON = { request: "＋", task: "→", pickup: "↑", delivered: "✓", obstacle: "⚠", reroute: "↺",
  clear: "✓", charge: "⚡", charging: "⚡", unblock: "↺", info: "•" };
function shortText(e) {
  // the long "why" is already shown at the top: keep the feed short
  return e.type === "task" ? e.text.split(" first.")[0] + " first" : e.type === "request" ? e.text.split(":")[0] : e.text;
}
function renderFeed(state) {
  $("#alerts").innerHTML = state.alerts.slice(0, 2).map((a) => `<div class="alert">⚠ ${esc(a.text)}</div>`).join("");
  $("#feed").innerHTML = state.events.slice(0, 10).map((e) =>
    `<li><span class="t">${clock(e.ts)}</span><span class="i" aria-hidden="true">${ICON[e.type] || "•"}</span><span>${esc(shortText(e))}</span></li>`).join("");
}

function renderHeader(state) {
  $("#clock").textContent = clock(state.ts);
  const s = state.stats;
  const stop = Object.values(state.stations).reduce((acc, st) =>
    acc + Object.values(st.materials).reduce((a, v) => a + v.stopped_s, 0), 0);
  const best = s.decisions ? `${Math.round(100 * s.optimizer_agrees / s.decisions)}%` : "–";
  const items = [["Deliveries", s.deliveries], ["Line stopped", fmtS(stop)],
    ["Best choices", best], ["Battery", `${Math.round(state.car.battery)}%`]];
  $("#stats").innerHTML = items.map(([k, v]) => `<div class="stat"><b>${v}</b><span>${k}</span></div>`).join("");
}

function setLink(ok, state) {
  const el = $("#link");
  const carOk = state && state.car.online;
  el.className = `pill ${ok && carOk ? "on" : "off"}`;
  el.textContent = !ok ? "AI offline" : carOk ? "car online" : "car offline";
}

// ---------- controls ----------
function buildControls() {
  $("#details").addEventListener("toggle", () => { if ($("#details").open && lastSnap) renderAI(lastSnap.decision, lastSnap.state); });
  const box = $("#controls");
  const stationOpts = Object.entries(layout.stations).map(([id, s]) => `<option value="${esc(id)}">${esc(id)} · ${esc(s.name)}</option>`).join("");
  box.innerHTML = `
    <div class="ctl"><label for="rq-st">Ask for a delivery</label>
      <select id="rq-st">${stationOpts}</select><select id="rq-m"></select>
      <button id="rq-go">Request</button></div>
    ${sim ? `
    <div class="ctl"><label for="sk-st">Change a stock reading</label>
      <select id="sk-st">${stationOpts}</select><select id="sk-m"></select>
      <input id="sk-v" type="number" min="0" value="2" aria-label="units">
      <button id="sk-go">Set</button></div>
    <div class="ctl"><label>Car and track</label>
      <button class="secondary" id="bat">Drain battery to 15%</button>
      <button class="secondary" id="clr">Remove obstacles</button></div>` : ""}
    <div class="toast" id="toast" role="status"></div>`;
  const fill = (stSel, mSel) => {
    const mats = layout.stations[$(stSel).value].materials;
    $(mSel).innerHTML = mats.map((m) => `<option value="${m}">${m} · ${esc(layout.materials[m].name)}</option>`).join("");
  };
  const toast = (t) => { $("#toast").textContent = t; setTimeout(() => ($("#toast").textContent = ""), 4000); };
  $("#rq-st").addEventListener("change", () => fill("#rq-st", "#rq-m"));
  fill("#rq-st", "#rq-m");
  $("#rq-go").addEventListener("click", async () => {
    const st = $("#rq-st").value, m = $("#rq-m").value;
    if (await post("/api/request", { material: m, station: st })) toast(`Requested ${m} for ${st}. Watch where the AI ranks it.`);
  });
  if (sim) {
    $("#sk-st").addEventListener("change", () => fill("#sk-st", "#sk-m"));
    fill("#sk-st", "#sk-m");
    $("#sk-go").addEventListener("click", async () => {
      const v = Number($("#sk-v").value);
      if (!Number.isFinite(v) || v < 0) { toast("Enter a stock of 0 or more."); return; }
      const st = $("#sk-st").value, m = $("#sk-m").value;
      if (await post("/api/sim", { cmd: "set_stock", station: st, material: m, stock: v })) toast(`${st} now reports ${v} × ${m}.`);
    });
    $("#bat").addEventListener("click", async () => { if (await post("/api/sim", { cmd: "set_battery", value: 15 })) toast("Battery set to 15%."); });
    $("#clr").addEventListener("click", async () => { if (await post("/api/sim", { cmd: "clear_obstacles" })) { obstacles.clear(); toast("Obstacles removed."); } });
  }
}

// ---------- main loop ----------
async function poll() {
  try {
    const r = await fetch("/api/snapshot", { cache: "no-store" });
    const d = await r.json();
    if (!layout) {
      layout = d.layout; sim = d.sim;
      buildMap(); buildControls();
    }
    if (d.state) {
      lastTs = d.state.ts;
      lastSnap = d;
      renderHeader(d.state); renderMap(d.state); renderStations(d.state); renderFeed(d.state);
      renderAI(d.decision, d.state);
    }
    setLink(true, d.state);
  } catch (e) {
    setLink(false, null);
  }
  setTimeout(poll, 300);
}
poll();
