// Carkaroo website: polls /api/snapshot and draws what the AI sees and decides.
// Login (the factory's name) -> Start (try a simulation, or set up my factory) -> Setup (home),
// Map, Stations (with the play controls), History, and the AI page under Extra.
// Nothing runs until Start; only the open page is redrawn.
"use strict";

const $ = (s) => document.querySelector(s);
const SVGNS = "http://www.w3.org/2000/svg";
const OUT = { N: [0, -1], E: [1, 0], S: [0, 1], W: [-1, 0] };
const ANGLE = { N: -90, E: 0, S: 90, W: 180 };
const SPUR = 26;              // gap between a line end and its box, in map units
const PAGES = ["login", "start", "setup", "map", "stations", "history", "ai"];
const LIVE = new Set(["map", "stations", "history", "ai"]);   // pages that need a running factory

let layout = null;
// the website never simulates: these are only true on the standalone dev dashboard of
// scripts/run_factory_sim.py, which shows its obstacle, battery and stock controls
let simCar = false;
let simStations = false;
let layoutVersion = -1;
let page = "";
let factory = null;            // {id, name} of the open factory, null before login
let running = false;           // a factory session is running (after Start)
let local = true;              // this browser is on the laptop itself (it may change the setup)
let nodes = {};
let map = {};                 // svg layers and per-node box elements
const obstacles = new Map();  // "A|B" -> sim time it disappears (obstacles this page placed)
let lastTs = 0;
let lastSnap = null;

// ---------- Roo: the logo's eyes and Roo the pet react to the live data (design/roo.js) ----------
// Roo lives in a lane along the bottom of every page, wanders, and says one line that fits the open page.
// The secret: click the checkered finish strip under the header 3 times and Roo takes a lap with a box.
const rooLogo = Roo.logo($("#logo"));
const rooLogin = Roo.buddy($("#roo-login"));
const rooMem = {};
function lapCargo() {                      // the box Roo carries on its lap: one of this factory's materials
  const mats = layout ? Object.keys(layout.materials) : ["A", "B", "C"];
  const m = mats[Math.floor(Math.random() * mats.length)];
  return { letter: m, name: layout && layout.materials[m] ? layout.materials[m].name : m };
}
const rooPet = Roo.pet($("#roo-pet"), { secret: ".top .finish", cargo: lapCargo });
let loginAt = 0;                         // a snapshot from before the login must not send Roo away again

// Roo's job on each page, in one short line (the Map page uses the live line from Roo.read)
function pageLine(d, r) {
  const st = d.state;
  if (page === "setup") {
    const off = setup && setup.devices ? setup.devices.filter((x) => !x.online) : [];
    if (!off.length) return "Everyone is online. I'm on the job!";
    const first = off[0].kind === "car" ? "me" : off[0].id;
    return off.length === 1 ? `Waiting for ${first} to log in.` : `Waiting for ${first} and ${off.length - 1} more to log in.`;
  }
  if (!st) return r.say;
  if (page === "stations") {
    let low = null;
    for (const [sid, s] of Object.entries(st.stations))
      for (const [m, v] of Object.entries(s.materials))
        if (v.stock > 0 && Number.isFinite(v.stockout_s) && (!low || v.stockout_s < low.t)) low = { t: v.stockout_s, name: s.name || sid, m };
    return low ? `${low.name} runs out of ${low.m} first, in ${fmtS(low.t)}.` : r.say;
  }
  if (page === "history") {
    const stop = Object.values(st.stations).reduce((acc, s) =>
      acc + Object.values(s.materials).reduce((x, v) => x + v.stopped_s, 0), 0);
    const n = st.stats ? st.stats.deliveries : 0;
    return `${n} ${n === 1 ? "delivery" : "deliveries"} so far, lines stopped ${fmtS(stop)}.`;
  }
  if (page === "ai") return "The examiner checks every choice I make, live.";
  return r.say;
}

function renderRoo(d) {
  if (!d.factory && d.setup) {               // the login page has the big Roo; the pet waits off-screen
    rooLogo.set("happy"); rooLogin.set("happy", "Hi! I'm Roo. What's your factory called?");
    if (Date.now() - loginAt > 3000) rooPet.hide();
    return;
  }
  rooPet.show();
  if (!d.running) { rooLogo.set("asleep"); rooPet.set("asleep", "Nothing is running. Press Start and I'll get going."); return; }
  const r = Roo.read(d, rooMem);
  rooLogo.set(r.mood);
  // in the serious moods Roo says what is wrong, on every page
  rooPet.set(r.mood, ["asleep", "shocked", "sad"].includes(r.mood) ? r.say : pageLine(d, r));
}
// changing page: Roo drives under the open tab
function rooVisit() {
  rooPet.fresh();
  if (lastSnap) renderRoo(lastSnap);
  const a = document.querySelector(".tabs a[aria-current='page']");
  if (a) rooPet.visit(a);
}

// the play controls: Roo gets curious when you change something
for (const id of ["#controls", "#map-controls"]) {
  $(id).addEventListener("click", (ev) => { if (ev.target.closest("button")) Roo.poke(rooMem); });
}

// ---------- light / dark ----------
// starts with the computer's setting; the choice is remembered (the page reads it before drawing)
function darkNow() {
  const t = document.documentElement.dataset.theme;
  return t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
}
function themeLabel() {
  const dark = darkNow(), b = $("#theme");
  b.innerHTML = `<span aria-hidden="true">${dark ? "&#9728;" : "&#9790;"}</span>`;
  b.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
  b.title = dark ? "Light mode" : "Dark mode";
}
$("#theme").addEventListener("click", () => {
  const next = darkNow() ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("carkaroo-theme", next); } catch (e) { /* private mode: not remembered */ }
  themeLabel();
});
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", themeLabel);
themeLabel();

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
// replace the contents only when they changed, so buttons inside are not swapped mid-click
function setHtml(el, html) {
  if (el.dataset.html !== html) { el.innerHTML = html; el.dataset.html = html; }
}
const chip = (m, cls = "") => `<span class="mat ${esc(m)} ${cls}" aria-label="material ${esc(m)}">${esc(m)}</span>`;
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
// POST JSON; on a refusal, show the server's reason and return false
async function post(url, body) {
  const r = await postJson(url, body);
  if (!r.ok) toast(r.data.error || "That did not work.");
  return r.ok;
}
async function postJson(url, body) {
  let r;
  try {
    r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  } catch (e) { return { ok: false, status: 0, data: { error: "Can't reach the AI. Is the app running?" } }; }
  let data = {};
  try { data = await r.json(); } catch (e) { /* empty answer */ }
  return { ok: r.ok, status: r.status, data };
}
let toastTimer = 0;
function toast(text) {
  const t = $("#toast");
  t.textContent = text;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 3500);
}

// the AI score ranks every request for the *next* delivery: show them in that order
function ordered(dec) {
  if (!dec || !dec.queue) return [];
  return dec.queue[0] && dec.queue[0].score === null ? dec.queue
    : [...dec.queue].sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
}

// ---------- pages ----------
// the tabs share one slanted asphalt plate with a yellow kerb that slides to the open page
const tabInk = document.createElement("span");
tabInk.className = "tab-ink";
tabInk.setAttribute("aria-hidden", "true");
$(".tabs").prepend(tabInk);
function moveTabInk() {
  const a = document.querySelector('.tabs a[aria-current="page"]');
  if (!a || a.hidden) { tabInk.style.opacity = "0"; return; }
  tabInk.style.opacity = "1";
  tabInk.style.width = `${a.offsetWidth}px`;
  tabInk.style.transform = `translateX(${a.offsetLeft}px) skewX(var(--skew))`;
  // a short squash-and-stretch on the way, like a car braking into its spot
  if ($(".tabs").classList.contains("ready")) { tabInk.classList.remove("hop"); void tabInk.offsetWidth; tabInk.classList.add("hop"); }
  // on a narrow phone the tab bar scrolls sideways: keep the open tab in view (never scrolls the page)
  const bar = $(".tabs");
  if (bar.scrollWidth > bar.clientWidth + 12) bar.scrollLeft = a.offsetLeft - (bar.clientWidth - a.offsetWidth) / 2;
}
window.addEventListener("resize", moveTabInk);
// widths change when the display font arrives; after that first placement the plate slides
(document.fonts ? document.fonts.ready : Promise.resolve()).then(() => {
  moveTabInk();
  requestAnimationFrame(() => requestAnimationFrame(() => $(".tabs").classList.add("ready")));
});

// which page to show: the login page until a factory is open, then the page in the address
// (Setup is home). Old links (#now, #try) go to the Map.
function wanted() {
  let want = location.hash.slice(1);
  if (want === "now" || want === "try") want = "map";
  if (!factory) return "login";
  return PAGES.includes(want) ? want : "setup";
}

function route() {
  if (!lastSnap) return;                    // the first snapshot decides (login or not)
  const before = page;
  page = wanted();
  if (`#${page}` !== location.hash && !(page === "setup" && !location.hash)) history.replaceState(null, "", `#${page}`);
  if (page !== before) window.scrollTo(0, 0);
  if (page !== before && before) setTimeout(rooVisit, 50);
  document.body.classList.remove("booting");
  document.body.classList.toggle("logged-out", !factory);
  document.querySelectorAll(".page").forEach((s) => { s.hidden = s.dataset.page !== page; });
  document.querySelectorAll(".tabs a, .extra-menu a").forEach((a) =>
    a.dataset.tab === page ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
  $("#extra").open = false;
  moveTabInk();
  placeMap();
  showIdle();
  if (page === "login") loadFactories();
  if (page === "start") renderStart();
  render(lastSnap);
  if (page === "setup") loadSetup();
}
window.addEventListener("hashchange", route);
// close the Extra menu when clicking anywhere else
// close the More and factory menus when clicking anywhere else
document.addEventListener("click", (ev) => {
  if (!ev.target.closest("#extra")) $("#extra").open = false;
  if (!ev.target.closest("#factory-chip")) $("#factory-chip").open = false;
});

function placeMap() {
  if (!layout) return;
  const svg = $("#map");
  if (svg.parentNode !== $("#slot-map")) $("#slot-map").appendChild(svg);
  svg.classList.add("placed");
  svg.classList.toggle("clickable", simCar && running);
  $("#floor-title").textContent = simCar && running ? "Factory floor · click a line to put an obstacle on it" : "Factory floor";
}

// a live page while nothing runs: say so, with the way to start
function showIdle() {
  const html = running ? "" : `<div class="idle"><svg viewBox="0 0 44 30" aria-hidden="true"><use href="#roo"/></svg>
    <div><b>The factory is stopped.</b><span>Start it to see Roo drive and the AI decide.</span></div>
    ${local ? `<button class="go" data-start type="button">Start</button>` : ""}
    <a href="#setup" class="ghost-link">Setup</a></div>`;
  document.querySelectorAll(".idle-slot").forEach((el) => setHtml(el, html));
  if (!running && map.car) {                 // the stopped factory: just the track, no car or route
    map.routes.innerHTML = ""; map.marks.innerHTML = "";
    map.car.g.style.display = "none";
    for (const e of Object.values(map.box)) {
      if (e.dot) e.dot.setAttribute("class", "dot ok");
      e.rect.setAttribute("class", "box");
    }
  }
  document.querySelectorAll(".page[data-page]").forEach((s) => s.classList.toggle("is-idle", !running && LIVE.has(s.dataset.page)));
}
document.addEventListener("click", async (ev) => {
  const b = ev.target.closest("[data-start]");
  if (!b) return;
  b.disabled = true;
  if (await post("/api/run", {})) {
    toast("Started. The AI is waiting for the car and the stations to log in.");
    running = true;
    if (page !== "map") location.hash = "#map";
  }
  b.disabled = false;
});

// ---------- Login and Start ----------
async function loadFactories() {
  let list = [];
  try { list = (await (await fetch("/api/factories", { cache: "no-store" })).json()).factories || []; } catch (e) { /* offline */ }
  setHtml($("#login-list"), !local ? `<p class="hint">Open the website on the laptop to choose a factory.</p>`
    : list.length ? `<p class="hint">Or open one you made before:</p><div class="row">${list.map((f) =>
      `<button class="ghost small" type="button" data-open="${esc(f.name)}">${esc(f.name)}</button>`).join("")}</div>` : "");
  $("#login-form").querySelectorAll("input, button").forEach((e) => { e.disabled = !local; });
}

async function login(name) {
  const r = await postJson("/api/login", { name });
  if (!r.ok) { $("#login-err").textContent = r.data.error || "Could not open the factory."; return; }
  $("#login-err").textContent = "";
  factory = r.data.factory;
  running = false;
  layout = null;              // the next snapshot rebuilds the map for this factory
  loginAt = Date.now();
  rooPet.arriveFrom($("#roo-login .car").getBoundingClientRect());   // the big Roo drives down into its lane
  rooPet.play("love", 1600, `Welcome to ${factory.name}!`);
  location.hash = "#start";
  route();
}
$("#login-form").addEventListener("submit", (ev) => { ev.preventDefault(); login($("#login-name").value); });
$("#login-name").addEventListener("input", () => { $("#login-err").textContent = ""; });
$("#login-list").addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-open]");
  if (b) login(b.dataset.open);
});
$("#switch-factory").addEventListener("click", async () => {
  if (running && !confirm(`Stop ${factory.name} and go back to the login page?`)) return;
  if (!(await post("/api/logout", {}))) return;
  factory = null; running = false;
  location.hash = "#login";
  route();
});

function renderStart() {
  $("#start-title").textContent = factory ? `Hello, ${factory.name}` : "Hello";
  const note = $("#start-running");
  note.hidden = !running;
  if (running) note.innerHTML = `The factory is already running. <a href="#map">Open the map</a>.`;
  $("#start-run").disabled = !local;
}
$("#start-run").addEventListener("click", async () => {
  $("#start-run").disabled = true;
  if (await post("/api/run", {})) {
    running = true;
    toast("Started. Now connect the car and the stations (or the simulator) with their keys.");
    location.hash = "#setup";
  }
  $("#start-run").disabled = !local;
});

// ---------- map (built once) ----------
function boxSize(n) {
  if (n.type === "station") return [156, 52];
  return [104, 52];
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
  // scale the track so a typical line is ~80 map units long (1 map unit ~ 1 screen pixel)
  const lengths = layout.edges.map(([a, b]) => {
    const A = layout.nodes.find((n) => n.id === a), B = layout.nodes.find((n) => n.id === b);
    return Math.abs(A.x - B.x) + Math.abs(A.y - B.y);
  }).sort((p, q) => p - q);
  const K = Math.min(4, Math.max(0.3, 80 / lengths[Math.floor(lengths.length / 2)]));
  for (const n of layout.nodes) nodes[n.id] = { ...n, x: n.x * K, y: n.y * K };
  const layer = (cls) => sv("g", { class: cls }, svg);
  map = { edges: layer("edges"), routes: layer("routes"), marks: layer("marks"), boxes: layer("boxes"), car: null, box: {} };
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  const grow = (x, y) => { minX = Math.min(minX, x); minY = Math.min(minY, y); maxX = Math.max(maxX, x); maxY = Math.max(maxY, y); };
  const placed = Object.fromEntries(placeBoxes().map((b) => [b.n.id, b]));

  for (const [a, b] of layout.edges) {
    const A = nodes[a], B = nodes[b];
    const g = sv("g", {}, map.edges);
    const line = sv("line", { x1: A.x, y1: A.y, x2: B.x, y2: B.y, class: "track" }, g);
    const hit = sv("line", { x1: A.x, y1: A.y, x2: B.x, y2: B.y, class: "hit" }, g);
    hit.addEventListener("click", () => placeObstacle(a, b));
    hit.addEventListener("mouseenter", () => simCar && running && line.classList.add("hover"));
    hit.addEventListener("mouseleave", () => line.classList.remove("hover"));
  }
  for (const raw of layout.nodes) {
    const n = nodes[raw.id];
    grow(n.x, n.y);
    if (n.type === "junction") {
      sv("circle", { cx: n.x, cy: n.y, r: 5, class: "junction" }, map.edges);
      continue;
    }
    const { w, h, dx, dy, cx, cy } = placed[n.id];
    const x = cx - w / 2, y = cy - h / 2;
    grow(x, y); grow(x + w, y + h);
    // connector: out from the line end, then across to the (possibly shifted) box
    const mx = n.x + dx * SPUR / 2, my = n.y + dy * SPUR / 2;
    const ex = dx !== 0 ? cx - dx * w / 2 : cx, ey = dy !== 0 ? cy - dy * h / 2 : cy;
    const elbow = dx !== 0 ? `${mx},${ey}` : `${ex},${my}`;
    sv("polyline", { points: `${n.x},${n.y} ${mx},${my} ${elbow} ${ex},${ey}`, class: "spur" }, map.boxes);
    const g = sv("g", { transform: `translate(${x},${y})` }, map.boxes);
    const rect = sv("rect", { width: w, height: h, rx: 9, class: "box" }, g);
    const entry = { rect };
    if (n.type === "station") {
      const st = layout.stations[n.id] || { name: "not used" };   // a station point the factory doesn't have
      sv("text", { x: 12, y: 22, class: "box-title" }, g).textContent = n.id;
      sv("text", { x: 12, y: 41, class: "box-sub" }, g).textContent = st.name.length > 17 ? st.name.slice(0, 16) + "…" : st.name;
      entry.dot = sv("circle", { cx: w - 15, cy: 16, r: 6.5, class: "dot ok" }, g);
      sv("title", {}, g).textContent = `${n.id} · ${st.name}`;
    } else if (n.type === "rack") {
      const m = Object.keys(layout.materials).find((k) => layout.materials[k].rack === n.id);
      if (m) {
        sv("rect", { x: 10, y: 12, width: 28, height: 28, rx: 6, class: `chip ${m}` }, g);
        sv("text", { x: 24, y: 32, "text-anchor": "middle", class: "chip-text" }, g).textContent = m;
      }
      sv("text", { x: 46, y: 22, class: "box-title" }, g).textContent = n.id;
      sv("text", { x: 46, y: 41, class: "box-sub" }, g).textContent = "rack";
      sv("title", {}, g).textContent = m ? `Rack ${n.id}: ${m} · ${layout.materials[m].name}` : n.id;
    } else {
      sv("text", { x: 12, y: 22, class: "box-title" }, g).textContent = n.id;
      sv("text", { x: 12, y: 41, class: "box-sub" }, g).textContent = "charger";
      sv("title", {}, g).textContent = "Charging dock";
    }
    map.box[n.id] = entry;
  }
  const pad = 22;
  svg.setAttribute("viewBox", `${minX - pad} ${minY - pad} ${maxX - minX + 2 * pad} ${maxY - minY + 2 * pad}`);

  // Roo seen from above, facing east before rotation: graphite body with a yellow racing stripe,
  // yellow motors, black tires and the ultrasonic sensor's two "eyes" in front
  const car = sv("g", { class: "car" }, svg);
  const body = sv("g", {}, car);
  for (const y of [-19, 12]) sv("rect", { x: -13, y, width: 15, height: 7, rx: 2, class: "car-tire" }, body);
  sv("rect", { x: -17, y: -12, width: 34, height: 24, rx: 6, class: "car-body" }, body);
  sv("rect", { x: -17, y: -2, width: 28, height: 4, class: "car-stripe" }, body);
  for (const y of [-13, 9]) sv("rect", { x: -11, y, width: 11, height: 4, rx: 1, class: "car-motor" }, body);
  for (const y of [-5, 5]) {
    sv("circle", { cx: 13, cy: y, r: 4, class: "car-eye" }, body);
    sv("circle", { cx: 14.5, cy: y, r: 1.7, class: "car-pupil" }, body);
  }
  const cargo = sv("g", { transform: "translate(0,-32)" }, car);
  const cargoRect = sv("rect", { x: -11, y: -11, width: 22, height: 22, rx: 5, class: "chip" }, cargo);
  const cargoText = sv("text", { x: 0, y: 4.5, "text-anchor": "middle", class: "chip-text" }, cargo);
  map.car = { g: car, body, cargo, cargoRect, cargoText };
}

function placeObstacle(a, b) {
  if (!simCar || !running || page !== "map") return;
  if (!confirm(`Put an obstacle on the line ${a}–${b} for 60 simulated seconds?\nThe car stops there; if it is still blocked, the AI finds another way.`)) return;
  post("/api/sim", { cmd: "obstacle", edge: [a, b], duration_s: 60 }).then((ok) => {
    if (!ok) return;
    obstacles.set(`${a}|${b}`, lastTs + 60);
    toast(`Obstacle on ${a}–${b}. Watch the car.`);
  });
}

function stationLevel(st) {
  const ms = Object.values(st.materials);
  if (ms.some((v) => v.stock <= 0)) return "out";
  if (ms.some((v) => v.stock < v.safety_stock)) return "low";
  return "ok";
}

function renderMap(state) {
  for (const [sid, st] of Object.entries(state.stations)) {
    const e = map.box[sid];
    if (!e) continue;
    const level = stationLevel(st);
    const requested = Object.values(st.materials).some((v) => v.requested);
    e.dot.setAttribute("class", `dot ${level}`);
    e.rect.setAttribute("class", `box${level === "out" ? " stopped" : requested ? " requested" : ""}`);
  }

  // routes, blocked lines, obstacles
  map.routes.innerHTML = "";
  map.marks.innerHTML = "";
  const task = state.car.task;
  const pts = (path) => path.map((id) => `${nodes[id].x},${nodes[id].y}`).join(" ");
  if (task && !task.legs.every((leg) => leg.path.every((id) => nodes[id]))) return;
  if (task) {
    task.legs.forEach((leg, i) => {
      if (i < task.leg) return;
      const cls = task.kind === "charge" ? " charge" : i > task.leg ? " later" : "";
      sv("polyline", { points: pts(leg.path), class: `route${cls}` }, map.routes);
    });
  }
  for (const [a, b] of state.blocked) {
    const A = nodes[a], B = nodes[b];
    if (!A || !B) continue;
    sv("line", { x1: A.x, y1: A.y, x2: B.x, y2: B.y, class: "blocked" }, map.marks);
  }
  for (const [key, until] of obstacles) {
    if (until < state.ts) { obstacles.delete(key); continue; }
    const [a, b] = key.split("|"), A = nodes[a], B = nodes[b];
    const x = (A.x + B.x) / 2, y = (A.y + B.y) / 2;
    sv("path", { d: `M ${x} ${y - 15} L ${x + 14} ${y + 10} L ${x - 14} ${y + 10} Z`, class: "obstacle" }, map.marks);
    sv("text", { x, y: y + 6, "text-anchor": "middle", class: "obstacle-text" }, map.marks).textContent = "!";
  }

  // car position: along the current line, or at its node
  const car = state.car;
  if (!nodes[car.node]) return;   // state from the previous track, the new one is on its way
  let x = nodes[car.node].x, y = nodes[car.node].y, heading = car.heading;
  if (task && task.edge) {
    const A = nodes[task.edge[0]], B = nodes[task.edge[1]];
    const p = task.edge_progress;
    x = A.x + (B.x - A.x) * p; y = A.y + (B.y - A.y) * p;
    heading = B.x > A.x ? "E" : B.x < A.x ? "W" : B.y > A.y ? "S" : "N";
  }
  map.car.g.style.display = "";
  map.car.g.style.transform = `translate(${x}px, ${y}px)`;
  map.car.body.setAttribute("transform", `rotate(${ANGLE[heading] ?? 0})`);
  const mode = !car.online ? "offline" : car.mode === "BLOCKED" || car.mode === "ERROR" ? "blocked"
    : car.mode === "CHARGING" ? "charging" : "";
  map.car.g.setAttribute("class", `car ${mode}`);
  const carrying = task && task.kind === "delivery" && task.leg === 1;
  map.car.cargo.style.display = carrying ? "" : "none";
  if (carrying) {
    map.car.cargoRect.setAttribute("class", `chip ${task.material}`);
    map.car.cargoText.textContent = task.material;
  }
}

// ---------- Now ----------
const CAR_DOING = {
  IDLE: "is waiting for a task", DRIVING: "is driving", LIFTING: "is lifting a box", LOWERING: "is putting a box down",
  BLOCKED: "is stopped by an obstacle", CHARGING: "is charging", ERROR: "has a problem", OFFLINE: "is offline",
};

function carSentence(state) {
  const car = state.car, t = car.task;
  if (!car.online) return "Roo (the car) is offline.";
  if (t && t.kind === "delivery") {
    const where = t.leg === 0 ? `to rack ${t.legs[0].path.at(-1)} to pick up ${t.material}` : `${t.material} to ${t.station}`;
    return t.blocked ? `Roo is stopped by an obstacle while taking ${where}.` : `Roo is ${t.leg === 0 ? "driving" : "carrying"} ${where}.`;
  }
  if (t && t.kind === "charge") return "Roo is going to the dock to charge.";
  return `Roo ${CAR_DOING[car.mode] || car.mode.toLowerCase()} at ${car.node}.`;
}

// an offline car's battery is not known
const batteryText = (state) => state.car.online ? `⚡ Battery ${Math.round(state.car.battery)}%` : "⚡ Battery –";

// what Roo is doing right now, as the big line on the Now page
function taskHero(state) {
  const car = state.car, t = car.task;
  if (t.kind === "charge") {
    return `<div class="label eyebrow">Roo now</div>
      <h1>${car.mode === "CHARGING" ? "Charging at the dock" : "Going to charge"}</h1>
      <p class="why">The battery is low, so Roo charges before the next delivery.</p>`;
  }
  const st = state.stations[t.station] || { name: t.station, materials: {} };
  const v = st.materials[t.material];
  const left = v ? `${esc(st.name)} has <b>${Math.round(v.stock)} ${esc(t.material)} left</b> and runs out in <b>${fmtS(v.stockout_s)}</b>.` : "";
  const busy = car.mode === "LIFTING" ? " Lifting the box now." : car.mode === "LOWERING" ? " Putting the box down now." : "";
  const head = t.leg === 0
    ? `<h1><span>Fetching</span>${chip(t.material, "big")}<span>for ${esc(st.name)}</span></h1>
       <p class="why">Picking it up at rack ${esc(t.legs[0].path.at(-1))}. ${left}${busy}</p>`
    : `<h1><span>Carrying</span>${chip(t.material, "big")}<span>to ${esc(st.name)}</span></h1>
       <p class="why">${left}${busy}</p>`;
  return `<div class="label eyebrow">Roo now</div>${head}
    ${t.blocked ? `<span class="badge crit">Stopped by an obstacle: after 10 s the AI finds another way</span>` : ""}`;
}

function renderHero(dec, state) {
  const hero = $("#hero");
  const q = ordered(dec);
  const busy = !!(state.car.online && state.car.task);
  if (busy) {
    hero.innerHTML = `${taskHero(state)}<p class="car">${batteryText(state)}</p>`;
    return;
  }
  if (!state.car.online) {                   // nothing moves until the car logs in: say that first
    hero.innerHTML = `
      <div class="label eyebrow">Roo now</div>
      <h1>Roo is offline</h1>
      <p class="why">Nothing moves until the car logs in with its key (Setup → Devices), or connect the Carkaroo
        Simulator to practise. The AI keeps deciding meanwhile.</p>
      ${carLine(state)}`;
    return;
  }
  const label = "The AI's choice";
  const offline = !state.car.online
    ? `<p><span class="badge crit">Roo is offline: nothing moves until the car connects (see Setup → Devices)</span></p>` : "";
  if (!q.length) {
    const waiting = state.requests.length;
    // requests are open but the safety rules let none through (empty warehouse, blocked line, ...)
    const reasons = [...new Set((dec && dec.alerts) || [])];
    hero.innerHTML = waiting ? `
      <div class="label eyebrow">${label}</div>
      <h1>Can't serve the waiting request${waiting > 1 ? "s" : ""}</h1>
      <p class="why">${plural(waiting, "request")} waiting, but the safety rules stop the car:</p>
      <ul class="blocked">${reasons.map((a) => `<li>${esc(a)}</li>`).join("") || "<li>Checking again…</li>"}</ul>
      ${reasons.some((a) => a.startsWith("Warehouse")) ? `<p class="why">Restocked it? Press <b>Refilled</b> on the <a href="#stations">Stations page</a>.</p>` : ""}
      ${offline}${carLine(state)}` : `
      <div class="label eyebrow">The AI's choice</div>
      <h1>All stocked up</h1>
      <p class="why">Every station has enough for now, so Roo takes a break. The AI asks for a delivery
        by itself as soon as a station would run low before the car could get there.</p>
      ${offline}${carLine(state)}`;
    return;
  }
  const first = q[0];
  const badge = bestBadge(dec, q);
  hero.innerHTML = `
    <div class="label eyebrow">${label}</div>
    <h1><span>Bring</span>${chip(first.material, "big")}<span>to ${esc(first.station_name)}</span></h1>
    <p class="why">${esc(first.station)} has <b>${Math.round(first.stock)} ${esc(first.material)} left</b> and runs out in
      <b>${fmtS(first.stockout_s)}</b>. The trip takes ${fmtS(first.trip_s)}.${first.slack_s < 0 ? " It stops for a short time even if served now, so it cannot wait." : ""}</p>
    ${badge}
    ${dec.charge_first ? `<p><span class="badge crit">⚡ Battery too low: the car charges first</span></p>` : ""}
    ${offline}${carLine(state)}`;
}

// "✓ Best possible choice" when the exact optimizer agrees, else "≈ Almost best"
function bestBadge(dec, q) {
  if (q.length < 2) return "";
  if (dec.optimizer_agrees) return `<span class="badge good">✓ Best possible choice</span>`;
  const best = q.find((r) => r.request_id === dec.optimizer_best);
  const pct = dec.best_cost ? 100 * dec.regret / dec.best_cost : 0;
  return `<span class="badge warn">≈ Almost best: ${pct.toFixed(1)}% more cost${best ? `; the optimizer would start with ${esc(best.material)} → ${esc(best.station)}` : ""}</span>`;
}

function carLine(state) {
  return `<p class="car">${esc(carSentence(state))} <span class="bat">${batteryText(state)}</span></p>`;
}

// under the big line: the AI's next choice while Roo is busy, else a link to the full order
function renderNext(dec, state) {
  const q = ordered(dec);
  const busy = !!(state.car.online && state.car.task), offline = !state.car.online;
  const more = (n) => n > 0 ? `<p class="more">${plural(n, "more request")} waiting · <a href="#ai">see the AI's full order</a></p>` : "";
  if ((!busy && !offline) || !q.length) { setHtml($("#next"), more(q.length - 1)); return; }
  const first = q[0];
  setHtml($("#next"), `<div class="up-next">
      <div class="nx-label">${offline ? "The AI's choice, when Roo connects" : "Next, when Roo is free"}</div>
      <p class="nx"><span>Bring</span>${chip(first.material)}<span>to ${esc(first.station_name)}</span></p>
      <p class="nx-why"><span class="${first.slack_s < 60 ? "urgent" : ""}">runs out in ${fmtS(first.stockout_s)}</span>
        · trip ${fmtS(first.trip_s)}</p>
      ${bestBadge(dec, q)}
      ${dec.charge_first ? `<span class="badge crit">⚡ Battery too low: Roo charges first</span>` : ""}
    </div>${more(q.length - 1)}`);
}

// History: the totals so far
function renderKpis(state) {
  const stop = Object.values(state.stations).reduce((acc, st) =>
    acc + Object.values(st.materials).reduce((a, v) => a + v.stopped_s, 0), 0);
  const bat = Math.round(state.car.battery), on = state.car.online;
  setHtml($("#hist-kpis"), `
    <div class="kpi"><b>${state.stats.deliveries}</b><span>deliveries</span></div>
    <div class="kpi${stop > 0.5 ? " bad" : ""}"><b>${fmtS(stop)}</b><span>lines stopped</span></div>
    <div class="kpi${on && bat < 20 ? " bad" : ""}"><b>${on ? `${bat}%` : "–"}</b><span>${on ? "battery" : "battery (Roo offline)"}</span></div>`);
}

// ---------- Stations ----------
const PRIORITY = { 3: "high priority", 2: "medium priority", 1: "low priority" };

function renderStations(state) {
  const t = state.car.task;
  const onTheWay = t && t.kind === "delivery" ? `${t.station}:${t.material}` : null;
  $("#station-list").innerHTML = Object.entries(state.stations).map(([sid, st]) => {
    const mats = Object.entries(st.materials).map(([m, v]) => {
      const frac = Math.max(0, Math.min(1, v.stock / v.capacity));
      const cls = v.stock <= 0 ? "out" : v.stock < v.safety_stock ? "low" : "ok";
      const urgent = v.stock < v.safety_stock || v.stockout_s < 120;
      const tag = v.stock <= 0 ? `<span class="tag out">stopped</span>`
        : onTheWay === `${sid}:${m}` ? `<span class="tag way">on the way</span>` : "";
      return `<div class="mrow">${chip(m)}
          <div class="sbar" role="img" aria-label="${esc(m)}: ${Math.round(v.stock)} of ${v.capacity}, safety level ${v.safety_stock}">
            <div class="fill ${cls}" style="width:${(100 * frac).toFixed(1)}%"></div>
            <div class="safety" style="left:${(100 * Math.min(1, v.safety_stock / v.capacity)).toFixed(1)}%"></div></div>
          <span class="qty">${Math.round(v.stock)}</span>
          <div class="meta"><span class="${urgent ? "urgent" : ""}">${v.stock <= 0 ? "empty" : `runs out in ${fmtS(v.stockout_s)}`}</span>${tag}</div></div>`;
    }).join("");
    return `<article class="station${stationLevel(st) === "out" ? " stopped" : ""}">
      <header><h3>${esc(st.name)}</h3><span class="sid">${esc(sid)}</span><span class="prio">${PRIORITY[st.criticality] || ""}</span></header>
      ${mats}</article>`;
  }).join("");

  const low = layout.warehouse_low_boxes ?? 3;
  setHtml($("#warehouse"), Object.entries(layout.materials).map(([m, info]) => {
    const units = Math.max(0, state.warehouse[m] ?? 0), boxes = Math.floor(units / info.box);
    const cls = boxes < 1 ? "empty" : boxes < low ? "low" : "";
    const note = boxes < 1 ? "Empty: reorder" : boxes < low ? "Low: reorder soon" : `rack ${esc(info.rack)}`;
    return `<div class="rack ${cls}">${chip(m, "big")}<div>
      <b>${boxes} ${boxes === 1 ? "box" : "boxes"}</b>
      <span>${units} ${esc(info.name.toLowerCase())}</span><br><span class="state">${note}</span></div>
      <button class="ghost small" data-refill="${esc(m)}" title="Someone restocked rack ${esc(info.rack)}: back to ${info.full} units">Refilled</button></div>`;
  }).join(""));
}

// ---------- AI ----------
function renderAI(dec, state) {
  const s = state.stats;
  const pct = s.decisions ? Math.round(100 * s.optimizer_agrees / s.decisions) : null;
  $("#ai-score").innerHTML = `
    <div class="big">${pct === null ? "–" : `${pct}%`}</div>
    <p>Best possible choice in <b>${s.optimizer_agrees} of ${s.decisions}</b> decisions so far,
      checked live by the examiner (the exact optimizer).</p>
    <div class="policy">${dec && dec.policy !== "ml" ? `Rule in use: ${esc(dec.policy)}` : "Model: ML ranker (gradient-boosted trees)"}</div>`;

  const q = ordered(dec);
  if (!q.length) {
    $("#ai-table").innerHTML = `<p class="quiet empty">No requests are waiting right now.</p>`;
    $("#ai-why").innerHTML = `<p class="quiet">Nothing to explain until a station asks for a delivery.</p>`;
    return;
  }
  // the short table: what the AI thinks, and how urgent each request is
  const others = q.length - 1;
  const rows = q.map((r, i) => {
    const score = r.score === null || others === 0 ? "–"
      : `<span class="meter"><i><b style="width:${(100 * r.score / others).toFixed(0)}%"></b></i>${r.score.toFixed(1)} of ${others}</span>`;
    return `<tr class="${i === 0 ? "first" : ""}">
      <td class="num">${i + 1}</td>
      <td><span class="req">${chip(r.material)}${esc(r.station_name)}</span></td>
      <td>${score}</td>
      <td class="num${r.slack_s < 60 ? " urgent" : ""}">${fmtS(r.stockout_s)}</td></tr>`;
  }).join("");
  $("#ai-table").innerHTML = `<table class="rank">
      <thead><tr><th>#</th><th>Request</th>
        <th title="How many of the other requests this one should go before (higher = sooner)">AI score</th>
        <th title="Time until the station runs out">Runs out in</th></tr></thead>
      <tbody>${rows}</tbody></table>`;

  // the details, folded away: trip times, the optimizer's costs and the reasons
  const costs = q.map((r) => r.cost_if_first).filter((c) => c !== null && c !== undefined);
  const minCost = Math.min(...costs);
  const detail = q.map((r, i) => {
    const cost = r.cost_if_first === null || r.cost_if_first === undefined ? "–"
      : r.cost_if_first === minCost ? `<span class="star">${r.cost_if_first.toFixed(0)} ★</span>` : r.cost_if_first.toFixed(0);
    return `<tr><td class="num">${i + 1}</td><td><span class="req">${chip(r.material)}${esc(r.station_name)}</span></td>
      <td class="num">${fmtS(r.trip_s)}</td><td class="num">${cost}</td></tr>`;
  }).join("");
  $("#ai-why").innerHTML = `
    <table class="rank small">
      <thead><tr><th>#</th><th>Request</th><th title="Car to the rack, then to the station">Trip</th>
        <th title="Exact optimizer: cost of the best plan that starts with this request (lower is better)">Cost if first</th></tr></thead>
      <tbody>${detail}</tbody></table>
    <h3>Why this order</h3>
    <ul>${dec.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
    <p class="note">AI score: the ML ranker compares every pair of requests; "3.8 of 4" means it should go before
      about 3.8 of the 4 others. The highest goes first, and the AI decides again after every delivery.
      Cost if first (★ = lowest): line-stop time × station priority, time below the safety level, waiting and driving.
      Decided at ${clock(dec.ts)}.</p>`;
}

// ---------- History ----------
const ICON = { request: "+", task: "→", pickup: "↑", delivered: "✓", obstacle: "!", reroute: "↺",
  clear: "✓", charge: "⚡", charging: "⚡", unblock: "↺", refill: "▤", info: "•" };
function shortText(e) {
  // the long "why" is on the Now and AI pages: keep the history short
  return e.type === "task" ? e.text.split(" first.")[0] + " first" : e.type === "request" ? e.text.split(":")[0] : e.text;
}
// events that belong to the delivery task before them (until it is delivered)
const IN_TASK = new Set(["pickup", "delivered", "obstacle", "reroute", "clear", "unblock"]);
const TASK_RE = /^Task (\d+): (\S+) -> (\S+) \(([^)]*)\)/;

// one card per delivery (task, pickup, delivered...), the other events as single rows; newest first
function groupEvents(events) {
  const items = [];
  let open = null;
  for (const e of [...events].reverse()) {          // oldest first
    if (e.type === "task") {
      const m = TASK_RE.exec(e.text);
      open = { kind: "run", id: m ? m[1] : "", material: m ? m[2] : "", station: m ? m[4] || m[3] : "",
        ts: e.ts, steps: [e], done: false };
      items.push(open);
    } else if (open && !open.done && IN_TASK.has(e.type)) {
      open.steps.push(e);
      if (e.type === "delivered") open.done = true;
    } else {
      items.push({ kind: "one", e });
    }
  }
  return items.reverse();
}

const evRow = (e) => `<li><span class="t">${clock(e.ts)}</span><span class="i ${esc(e.type)}" aria-hidden="true">${ICON[e.type] || "•"}</span><span>${esc(shortText(e))}</span></li>`;

function renderHistory(state) {
  setHtml($("#alerts"), state.alerts.slice(0, 3).map((a) =>
    `<div class="alert crit"><span class="al-i" aria-hidden="true">!</span><span>${esc(a.text)}</span></div>`).join(""));
  if (!state.events.length) {
    setHtml($("#feed"), `<p class="empty"><svg viewBox="0 0 44 30" aria-hidden="true"><use href="#roo"/></svg>
      Nothing has happened yet. Roo is waiting for the first request.</p>`);
    return;
  }
  let html = "", singles = "";
  const flush = () => { if (singles) html += `<ol class="ev-list">${singles}</ol>`; singles = ""; };
  for (const it of groupEvents(state.events)) {
    if (it.kind === "one") { singles += evRow(it.e); continue; }
    flush();
    const last = it.steps.at(-1);
    const tag = it.done ? `<span class="tag done">delivered</span>` : `<span class="tag way">on the way</span>`;
    html += `<article class="run${it.done ? "" : " live"}">
      <header>${it.material ? chip(it.material) : ""}<b>${it.station ? `To ${esc(it.station)}` : "Delivery"}</b>
        <span class="run-id">${it.id ? `task ${esc(it.id)} · ` : ""}${clock(it.ts)}–${clock(last.ts)}</span>${tag}</header>
      <ol class="steps">${it.steps.map(evRow).join("")}</ol></article>`;
  }
  flush();
  setHtml($("#feed"), html);
}

// ---------- header ----------
function setLink(ok, state) {
  const el = $("#link");
  el.hidden = ok && !running;                // stopped: the mode pill already says so
  const carOk = state && state.car.online;
  el.className = `link ${ok && carOk ? "on" : "off"}`;
  el.textContent = !ok ? "AI offline" : carOk ? "Roo online" : "Roo offline";
}

// ---------- play controls ----------
// the warehouse has no sensor: a person presses "Refilled" after restocking a rack
$("#warehouse").addEventListener("click", async (ev) => {
  const b = ev.target.closest("[data-refill]");
  if (!b) return;
  const m = b.dataset.refill, info = layout.materials[m];
  if (!running) { toast("Start the factory first."); return; }
  if (await post("/api/refill", { material: m })) {
    toast(`Rack ${info.rack} refilled: ${info.full} ${m} (${Math.floor(info.full / info.box)} boxes).`);
    rooPet.play("love", 1800, `Thanks for refilling ${m}!`);
  }
});

function buildControls() {
  const stationOpts = Object.entries(layout.stations).map(([id, s]) => `<option value="${esc(id)}">${esc(s.name)} (${esc(id)})</option>`).join("");
  $("#map-controls").innerHTML = simCar ? `
    <div class="ctl"><h3>Low battery</h3>
      <p>Below 20% the AI sends the car to charge before the next delivery.</p>
      <button class="ghost" id="bat">Drain battery to 15%</button></div>
    <div class="ctl"><h3>Obstacle</h3>
      <p>Click a line on the map to block it for 60 s. The car stops, waits 10 s, then the AI finds another way.</p>
      <button class="ghost" id="clr">Remove all obstacles</button></div>`
    : `<p class="floor-hint"><b>Obstacles:</b> put something in front of Roo's ultrasonic sensor (or use the
      Carkaroo Simulator's obstacle). After 10 s the AI sends it another way.</p>`;
  $("#controls").innerHTML = `
    <div class="ctl"><h3>Ask for a delivery</h3>
      <p>Add a request by hand and see where the AI puts it.</p>
      <div class="row"><select id="rq-st" aria-label="Station">${stationOpts}</select>
        <select id="rq-m" aria-label="Material"></select><button id="rq-go">Request</button></div></div>
    ${simStations ? `
    <div class="ctl"><h3>Change a stock reading</h3>
      <p>Pretend a load cell reads a different number. Try a low one.</p>
      <div class="row"><select id="sk-st" aria-label="Station">${stationOpts}</select><select id="sk-m" aria-label="Material"></select>
        <input id="sk-v" type="number" min="0" value="2" aria-label="Units"><button id="sk-go">Set</button></div></div>`
    : `<div class="ctl"><h3>Stock readings</h3><p>The stock comes from the stations' load cells (or the Carkaroo
      Simulator). Take a box off a scale and watch the AI react.</p></div>`}`;
  const fill = (stSel, mSel) => {
    const mats = layout.stations[$(stSel).value].materials;
    $(mSel).innerHTML = mats.map((m) => `<option value="${esc(m)}">${esc(m)} · ${esc(layout.materials[m].name)}</option>`).join("");
  };
  $("#rq-st").addEventListener("change", () => fill("#rq-st", "#rq-m"));
  fill("#rq-st", "#rq-m");
  $("#rq-go").addEventListener("click", async () => {
    const st = $("#rq-st").value, m = $("#rq-m").value;
    if (await post("/api/request", { material: m, station: st })) toast(`Asked for ${m} at ${layout.stations[st].name}. See where the AI puts it on the Map.`);
  });
  if (simStations) {
    $("#sk-st").addEventListener("change", () => fill("#sk-st", "#sk-m"));
    fill("#sk-st", "#sk-m");
    $("#sk-go").addEventListener("click", async () => {
      const v = Number($("#sk-v").value);
      if (!Number.isFinite(v) || v < 0) { toast("Enter a stock of 0 or more."); return; }
      const st = $("#sk-st").value, m = $("#sk-m").value;
      if (await post("/api/sim", { cmd: "set_stock", station: st, material: m, stock: v })) toast(`${st} now reads ${v} × ${m}.`);
    });
  }
  if (simCar) {
    $("#bat").addEventListener("click", async () => { if (await post("/api/sim", { cmd: "set_battery", value: 15 })) toast("Battery set to 15%."); });
    $("#clr").addEventListener("click", async () => { if (await post("/api/sim", { cmd: "clear_obstacles" })) { obstacles.clear(); toast("Obstacles removed."); } });
  }
}

// ---------- Setup ----------
let setup = null;           // last /api/setup answer
let setupShape = "";        // what the Setup page was built for (rebuilt only when it changes)
const shownKeys = new Set();

const trackName = (s) => (s.tracks.find((x) => x.id === s.track) || {}).name || s.track;

function agoText(s) {
  if (s === null || s === undefined) return "never seen";
  return s < 60 ? `${Math.max(1, Math.round(s))} s ago` : s < 3600 ? `${Math.round(s / 60)} min ago` : "over an hour ago";
}

async function loadSetup() {
  try {
    const r = await fetch("/api/setup", { cache: "no-store" });
    if (!r.ok) return;
    setup = await r.json();
  } catch (e) { return; }
  const shape = JSON.stringify([setup.track, setup.local, setup.broker.ok, setup.running, setup.track_problems,
    setup.key_error, setup.tracks.map((x) => x.id), setup.devices.map((d) => [d.id, d.key])]);
  if (shape !== setupShape) { setupShape = shape; buildSetup(); }
  updateDevices();
  if (setup.factory) FactoryEditor.load(setup.factory.id, !setup.local);
}

function buildSetup() {
  const s = setup, b = s.broker;
  const readOnly = !s.local;
  $("#setup-note").innerHTML = (!b.ok ? `<div class="alert crit"><b>The broker is not running, so the car and the
      stations cannot connect and the factory cannot start.</b> ${esc(b.error || "")}</div>` : "")
    + (readOnly ? `<div class="alert">You are looking from another device, so this page is read-only and the keys are hidden.
        Make changes on the laptop.</div>` : "")
    + (s.key_error ? `<div class="alert crit">${esc(s.key_error)}</div>` : "")
    + (s.track_problems.length ? `<div class="alert crit"><b>The track does not fit your stations yet</b>, so the factory
        cannot start. Open the track editor below and fix:<ul>${s.track_problems.slice(0, 5).map((p) =>
        `<li>${esc(p)}</li>`).join("")}</ul></div>` : "");
  const trackOpts = s.tracks.map((x) => `<option value="${esc(x.id)}"${x.id === s.track ? " selected" : ""}>${esc(x.name)}</option>`).join("");
  $("#setup-mode").innerHTML = `
    <div class="row mode-row">
      <label>Track <select id="set-track"${readOnly ? " disabled" : ""}>${trackOpts}</select></label>
    </div>
    <div class="row run-row">
      ${s.running ? `<button id="set-apply"${readOnly ? " disabled" : ""}>Use this track</button>
        <button class="ghost" id="set-stop"${readOnly ? " disabled" : ""}>Stop</button>`
        : `<button class="go" id="set-apply"${readOnly || !b.ok ? " disabled" : ""}>Start</button>`}
    </div>
    <p class="hint">${s.running
      ? `Running on <b>${esc(trackName(s))}</b>. The AI decides as soon as the car and the stations are online.`
      : `Stopped. Press <b>Start</b>: the AI starts and waits for the car and the stations to log in.`}</p>
    <p class="run-wait" id="run-wait"></p>`;
  $("#set-apply").addEventListener("click", async () => {
    const btn = $("#set-apply"), label = btn.textContent;
    btn.disabled = true; btn.textContent = s.running ? "Switching…" : "Starting…";
    let r = await postJson("/api/mode", { track: $("#set-track").value });
    if (r.ok && !s.running) r = await postJson("/api/run", {});
    btn.disabled = false; btn.textContent = label;
    toast(r.ok ? (s.running ? "Now using that track." : "Started. Connect the car and the stations with their keys.")
      : (r.data.error || "Could not start."));
    if (r.ok) running = true;
    setupShape = "";
    loadSetup();
  });
  if ($("#set-stop")) $("#set-stop").addEventListener("click", async () => {
    if (await post("/api/stop", {})) { running = false; toast("Stopped. Roo is resting."); }
    setupShape = "";
    loadSetup();
  });

  const addr = b.addresses.length ? b.addresses.join(" or ") : "this laptop's IP address";
  const keys = s.devices.every((d) => d.key);
  $("#setup-devices").innerHTML = (keys ? `<div class="row dev-tools">
      <button class="ghost small" id="copy-all" type="button">Copy all for the simulator</button>
      <span class="quiet">The address, the port and every key, to paste into the Carkaroo Simulator.</span></div>` : "")
    + `<ul class="devices">${s.devices.map((d) => `
    <li class="device" data-dev="${esc(d.id)}">
      <div class="dev-row">
        <span class="dev-dot" aria-hidden="true"></span>
        <span class="dev-name"><b>${esc(d.kind === "car" ? `Car ${d.id}` : `${d.id} · ${d.name}`)}</b>
          <span class="dev-state"></span></span>
        <button class="ghost small" data-connect="${esc(d.id)}" aria-expanded="false">Connect</button>
      </div>
      <div class="connect" hidden>
        <dl>
          <dt>Broker</dt><dd><code>${esc(addr)}</code>, port <code>${b.port ?? 1883}</code></dd>
          <dt>Username</dt><dd><code>${esc(d.id)}</code></dd>
          <dt>Key</dt><dd>${d.key ? `<code class="key">${shownKeys.has(d.id) ? esc(d.key) : "••••••••••••"}</code>
            <button class="ghost small" data-show="${esc(d.id)}">${shownKeys.has(d.id) ? "Hide" : "Show"}</button>
            <button class="ghost small" data-copy="${esc(d.id)}">Copy</button>
            <button class="ghost small" data-newkey="${esc(d.id)}">New key</button>`
            : `<span class="quiet">${b.ok ? "shown on the laptop only" : "no broker running"}</span>`}</dd>
          <dt>Topics</dt><dd>${d.topics.map((x) => `<code>${esc(x)}</code>`).join(" ")}</dd>
        </dl>
        <pre class="snippet">// in the firmware, when connecting to MQTT
client.connect("${esc(d.id)}", "${esc(d.id)}", "&lt;key&gt;");${d.kind === "car" ? `
// last will, so the website shows the car offline at once if it drops:
//   topic factory/car/${esc(d.id)}/status, retained, payload {"state":"OFFLINE"}` : ""}</pre>
      </div>
    </li>`).join("")}</ul>`;

  const cur = s.tracks.find((x) => x.id === s.track) || { id: s.track, name: s.track };
  $("#setup-track").innerHTML = `
    <p>The AI uses <b>${esc(cur.name)}</b>. Draw your real track with its measurements in cm; the editor checks it
      before it can be used.</p>
    <div class="row"><button id="edit-track"${readOnly ? " disabled" : ""}>Edit this track</button>
      <button class="ghost" id="new-track"${readOnly ? " disabled" : ""}>Start an empty track</button></div>`;
  $("#edit-track").addEventListener("click", async () => {
    const r = await fetch(`/api/track/${encodeURIComponent(s.track)}`);
    if (r.ok) TrackEditor.open(await r.json(), cur.id === "sample" ? "" : cur.name);
  });
  $("#new-track").addEventListener("click", () => TrackEditor.open({ nodes: {}, edges: [] }, ""));
}

$("#setup-devices").addEventListener("click", async (ev) => {
  const t = ev.target.closest("button");
  if (!t || !setup) return;
  const dev = (id) => setup.devices.find((d) => d.id === id);
  if (t.id === "copy-all") {
    const text = [`# Carkaroo devices for ${factory ? factory.name : "this factory"}`,
      "broker: localhost", `port: ${setup.broker.port ?? 1883}`,
      ...setup.devices.map((d) => `${d.id}: ${d.key}`)].join("\n");
    try { await navigator.clipboard.writeText(text); toast("Copied. Paste it into the simulator's Connect box."); }
    catch (e) { toast("Copy did not work: use Show and Copy for each device."); }
  } else if (t.dataset.connect) {
    const box = t.closest(".device").querySelector(".connect");
    box.hidden = !box.hidden;
    t.setAttribute("aria-expanded", String(!box.hidden));
  } else if (t.dataset.show) {
    const id = t.dataset.show;
    if (shownKeys.has(id)) shownKeys.delete(id); else shownKeys.add(id);
    t.closest("dd").querySelector(".key").textContent = shownKeys.has(id) ? dev(id).key : "••••••••••••";
    t.textContent = shownKeys.has(id) ? "Hide" : "Show";
  } else if (t.dataset.copy) {
    try { await navigator.clipboard.writeText(dev(t.dataset.copy).key); toast("Key copied."); }
    catch (e) { toast("Copy did not work: press Show and copy it by hand."); }
  } else if (t.dataset.newkey) {
    const id = t.dataset.newkey;
    if (!confirm(`Make a new key for ${id}? The old key stops working at once, so ${id} needs the new one in its firmware.`)) return;
    const r = await postJson(`/api/device/${encodeURIComponent(id)}/key`, {});
    toast(r.ok ? `New key for ${id}.` : (r.data.error || "Could not make a new key."));
    shownKeys.add(id);
    setupShape = "";
    await loadSetup();
    const box = document.querySelector(`.device[data-dev="${CSS.escape(id)}"] .connect`);
    if (box) box.hidden = false;
  }
});

function updateDevices() {
  for (const d of setup.devices) {
    const li = document.querySelector(`.device[data-dev="${CSS.escape(d.id)}"]`);
    if (!li) continue;
    li.classList.toggle("online", d.online);
    li.querySelector(".dev-state").textContent = d.online ? `online · last message ${agoText(d.last_seen_s)}`
      : `offline · ${agoText(d.last_seen_s)}`;
  }
  // while running: who the AI is still waiting for
  const wait = $("#run-wait");
  if (wait) {
    const off = setup.devices.filter((d) => !d.online).map((d) => (d.kind === "car" ? `Car ${d.id}` : d.id));
    wait.textContent = !setup.running ? "" : off.length
      ? `Waiting for: ${off.join(", ")}. Connect them with their keys (Devices), or with the Carkaroo Simulator.`
      : "Everything is online.";
    wait.classList.toggle("ok", setup.running && !off.length);
  }
}

function setMode(d) {
  const pill = $("#mode-pill");
  pill.hidden = !d.mode || !factory;
  $("#factory-chip").hidden = !factory || !d.setup;
  if (factory) $("#factory-name").textContent = factory.name;
  $("#switch-factory").disabled = !local;
  if (!d.mode) return;
  pill.textContent = d.running ? "Running" : "Stopped";
  pill.className = `mode-pill ${d.running ? "real" : "stopped"}`;
}

// ---------- main loop ----------
function render(d) {
  const state = d.state, dec = d.decision;
  $("#clock").hidden = !state;              // no factory time while stopped
  if (!state) return;
  $("#clock").textContent = clock(state.ts);
  if (page === "map") { renderMap(state); renderHero(dec, state); renderNext(dec, state); }
  else if (page === "stations") renderStations(state);
  else if (page === "ai") renderAI(dec, state);
  else if (page === "history") { renderKpis(state); renderHistory(state); }
}

// the Setup page has its own, slower poll
setInterval(() => { if (page === "setup" && !TrackEditor.isOpen()) loadSetup(); }, 1000);

async function poll() {
  try {
    const r = await fetch("/api/snapshot", { cache: "no-store" });
    const d = await r.json();
    const parts = d.sim_parts || { car: d.sim, stations: d.sim };
    const first = !lastSnap;
    const was = [factory && factory.id, running, local].join("|");
    factory = d.setup ? d.factory : { id: "", name: "" };   // the plain dashboard has no login
    running = d.running !== false;
    local = d.local !== false;
    if (!layout || d.layout_version !== layoutVersion || parts.car !== simCar || parts.stations !== simStations) {
      // first load, a new track or a new mode: rebuild the map and the controls
      layout = d.layout; layoutVersion = d.layout_version;
      simCar = parts.car; simStations = parts.stations;
      nodes = {}; obstacles.clear();
      buildMap(); buildControls();
      placeMap();
    }
    setMode(d);
    lastSnap = d;
    if (d.state) lastTs = d.state.ts;
    if (first || was !== [factory && factory.id, running, local].join("|")) route();   // login, Start or Stop
    else render(d);
    renderRoo(d);
    setLink(true, d.state);
  } catch (e) {
    setLink(false, null);
    rooLogo.set("thinking");
    rooPet.set("thinking", "I can't reach the AI. Is the app running?");
  }
  setTimeout(poll, 300);
}
route();
poll();
