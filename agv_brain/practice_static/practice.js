// The Carkaroo Simulator's page: choose a factory, connect the pretend devices with their keys,
// and play with the pretend world. Polls /api/state; every value shown goes through esc().
"use strict";

const $ = (s) => document.querySelector(s);
const SVGNS = "http://www.w3.org/2000/svg";
let st = null;              // last /api/state
let shape = "";             // what the page was built for (factory + devices)
let floor = {};             // svg parts

Roo.logo($("#logo"));

// ---------- Roo the pet: lives in a lane along the bottom (design/roo.js), says what to do next ----------
// The secret is the same as on the Carkaroo website: click the checkered finish strip 3 times.
const pet = Roo.pet($("#roo-pet"), {
  secret: ".top .finish",
  cargo: () => {
    const mats = st && st.layout ? Object.keys(st.layout.materials) : ["A", "B", "C"];
    const m = mats[Math.floor(Math.random() * mats.length)];
    return { letter: m, name: st && st.layout ? st.layout.materials[m].name : m };
  },
});
pet.show();
let curiousUntil = 0;
let wasAll = false;             // everything was connected at the last poll
function petLine() {
  if (!st || !st.factory) return ["happy", "Pick the factory I should pretend to be."];
  const n = st.devices.length, on = st.devices.filter((d) => d.state === "on").length;
  const car = st.devices.find((d) => d.kind === "car");
  if (!on) return ["happy", "Paste the keys from the Carkaroo website and I'll log in."];
  if (car && car.state !== "on") return ["asleep", "My plug is pulled. Connect me again."];
  if (car && (car.obstacles || []).length) return ["shocked", "Something is in my way. Watch the AI find another way."];
  if (car && car.battery < 20) return ["sleepy", `Battery ${car.battery}%. The AI will send me to the dock.`];
  if (Date.now() < curiousUntil) return ["curious", "Ooh! Let's see what the AI does with that."];
  if (on < n) return ["happy", `${on} of ${n} connected. Keep going!`];
  if (car && car.mode !== "IDLE") return ["driving", "Pretend-driving! Watch me on the Carkaroo website."];
  return ["happy", "Everything is connected. Watch the Carkaroo website!"];
}

function esc(t) {
  return String(t).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function sv(tag, attrs = {}, parent = null) {
  const e = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}
let toastTimer = 0;
function toast(text) {
  const t = $("#toast");
  t.textContent = text;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 3800);
}
async function post(url, body) {
  let r;
  try {
    r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  } catch (e) { toast("Can't reach the simulator. Is it still running?"); return null; }
  let data = {};
  try { data = await r.json(); } catch (e) { /* empty */ }
  if (!r.ok) { toast(data.error || "That did not work."); return null; }
  if (data.devices) { st = { ...st, ...data }; render(); }
  return data;
}

// ---------- drawing ----------
function render() {
  if (!st) return;
  const s = st;
  $("#note").innerHTML = s.local ? "" : `<div class="alert">The simulator can only be used on the laptop itself.</div>`;
  $("#sim-factory").textContent = s.factory ? `Pretending: ${s.factory.name}` : "";
  const want = JSON.stringify([s.factory && s.factory.id, s.factories.map((f) => f.id), s.devices.map((d) => d.id)]);
  if (want !== shape) { shape = want; build(); }
  for (const d of s.devices) {
    const li = document.querySelector(`.device[data-dev="${CSS.escape(d.id)}"]`);
    if (!li) continue;
    li.className = `device ${d.state}`;
    li.querySelector(".dev-name span").textContent = d.state === "on" ? "connected · logged in with its key"
      : d.state === "error" ? "not connected" : "not connected";
    li.querySelector(".err").textContent = d.error || "";
    const btn = li.querySelector("button");
    btn.textContent = d.state === "on" ? "Disconnect" : "Connect";
    btn.className = d.state === "on" ? "ghost small" : "small";
    li.querySelector("input").hidden = d.state === "on";
    li.querySelector(".dev-live").textContent = d.state !== "on" ? ""
      : d.kind === "car" ? `at ${d.node} · facing ${d.heading} · ${d.mode.toLowerCase()} · battery ${d.battery}%`
        : Object.entries(d.stock || {}).map(([m, v]) => `${m}: ${v}`).join(" · ");
  }
  drawCar();
  // the Connect card: a one-line summary, folded the moment everything is connected
  const n = s.devices.length, on = s.devices.filter((d) => d.state === "on").length;
  const sum = $("#conn-sum");
  sum.textContent = !s.factory ? "Choose a factory" : `${on} of ${n} connected${on === n && n ? " ✓" : ""}`;
  sum.classList.toggle("ok", !!n && on === n);
  const all = !!n && on === n;
  if (all && !wasAll) $("#connect-box").open = false;
  if (!on && wasAll) $("#connect-box").open = true;
  wasAll = all;
  const [mood, line] = petLine();
  pet.set(mood, line);
}

function build() {
  const s = st;
  $("#factory").innerHTML = s.factories.length
    ? s.factories.map((f) => `<option value="${esc(f.id)}"${s.factory && s.factory.id === f.id ? " selected" : ""}>${esc(f.name)}</option>`).join("")
    : `<option value="">No factory yet: log in on the Carkaroo website first</option>`;
  $("#host").value = s.host; $("#port").value = s.port;
  $("#devices").innerHTML = !s.factory ? `<li class="quiet">Choose a factory first.</li>` : s.devices.map((d) => `
    <li class="device ${esc(d.state)}" data-dev="${esc(d.id)}">
      <span class="dev-dot" aria-hidden="true"></span>
      <span class="dev-name"><b>${esc(d.kind === "car" ? `Car ${d.id}` : `${d.id} · ${d.name}`)}</b><span></span></span>
      <input type="password" autocomplete="off" placeholder="key for ${esc(d.id)}" aria-label="Key for ${esc(d.id)}">
      <span class="dev-btns"><button class="small" type="button" data-dev="${esc(d.id)}">Connect</button></span>
      <span class="err" role="alert"></span>
      <span class="dev-live"></span>
    </li>`).join("");
  buildPlay();
  buildFloor();
}

function buildPlay() {
  const s = st;
  if (!s.factory) { $("#play").innerHTML = `<p class="quiet">Choose a factory first.</p>`; return; }
  const L = s.layout;
  const stOpts = Object.entries(L.stations).map(([id, x]) => `<option value="${esc(id)}">${esc(id)} · ${esc(x.name)}</option>`).join("");
  $("#play").innerHTML = `
    <div class="ctl-row"><b>The car's battery</b>
      <div class="row"><button class="ghost small" type="button" data-bat="15">Drain to 15%</button>
        <button class="ghost small" type="button" data-bat="100">Charge to 100%</button></div></div>
    <div class="ctl-row"><b>Obstacles</b><div class="row">
      <button class="ghost small" type="button" id="clear">Remove all obstacles</button>
      <span class="quiet">or click a line on the pretend floor</span></div></div>
    <div class="ctl-row"><b>A station's load cell</b><div class="row">
      <select id="sk-st" aria-label="Station">${stOpts}</select><select id="sk-m" aria-label="Material"></select>
      <input id="sk-v" type="number" min="0" value="2" aria-label="Units"><button class="small" type="button" id="sk-go">Set</button></div></div>`;
  const fill = () => {
    $("#sk-m").innerHTML = L.stations[$("#sk-st").value].materials
      .map((m) => `<option value="${esc(m)}">${esc(m)} · ${esc(L.materials[m].name)}</option>`).join("");
  };
  $("#sk-st").addEventListener("change", fill);
  fill();
}

function buildFloor() {
  const svg = $("#floor");
  svg.innerHTML = "";
  floor = {};
  if (!st.factory) return;
  const L = st.layout, pos = {};
  for (const n of L.nodes) pos[n.id] = n;
  const xs = L.nodes.map((n) => n.x), ys = L.nodes.map((n) => n.y);
  const pad = 40;
  svg.setAttribute("viewBox", `${Math.min(...xs) - pad} ${Math.min(...ys) - pad} ${Math.max(...xs) - Math.min(...xs) + 2 * pad} ${Math.max(...ys) - Math.min(...ys) + 2 * pad}`);
  floor.marks = sv("g", {}, svg);
  for (const [a, b] of L.edges) {
    const A = pos[a], B = pos[b];
    const g = sv("g", {}, svg);
    const hit = sv("line", { x1: A.x, y1: A.y, x2: B.x, y2: B.y, class: "hit" }, g);
    sv("line", { x1: A.x, y1: A.y, x2: B.x, y2: B.y, class: "track" }, g);
    hit.addEventListener("click", () => obstacle(a, b));
    sv("title", {}, hit).textContent = `Put an obstacle on ${a}–${b}`;
  }
  for (const n of L.nodes) {
    sv("circle", { cx: n.x, cy: n.y, r: n.type === "junction" ? 4 : 7, class: "node" }, svg);
    if (n.type !== "junction") sv("text", { x: n.x + 9, y: n.y - 8, class: "label" }, svg).textContent = n.id;
  }
  floor.pos = pos;
  // Roo seen from above, facing east before it turns: graphite body, yellow stripe and motors, two eyes in front
  floor.car = sv("g", { class: "roo-top" }, svg);
  floor.body = sv("g", {}, floor.car);
  for (const y of [-19, 12]) sv("rect", { x: -13, y, width: 15, height: 7, rx: 2, class: "rt-tire" }, floor.body);
  sv("rect", { x: -17, y: -12, width: 34, height: 24, rx: 6, class: "rt-body" }, floor.body);
  sv("rect", { x: -17, y: -2, width: 28, height: 4, class: "rt-stripe" }, floor.body);
  for (const y of [-13, 9]) sv("rect", { x: -11, y, width: 11, height: 4, rx: 1, class: "rt-motor" }, floor.body);
  for (const y of [-5, 5]) {
    sv("circle", { cx: 13, cy: y, r: 4, class: "rt-eye" }, floor.body);
    sv("circle", { cx: 14.5, cy: y, r: 1.7, class: "rt-pupil" }, floor.body);
  }
  sv("title", {}, floor.car).textContent = "Roo, the pretend car";
  floor.car.style.display = "none";
}

function drawCar() {
  if (!floor.car || !st.factory) return;
  const car = st.devices.find((d) => d.kind === "car");
  const on = car && car.state === "on" && floor.pos[car.node];
  floor.car.style.display = on ? "" : "none";
  if (on) {
    const p = floor.pos[car.node];
    floor.car.style.transform = `translate(${p.x}px, ${p.y}px)`;
    floor.body.setAttribute("transform", `rotate(${{ N: -90, E: 0, S: 90, W: 180 }[car.heading] ?? 0})`);
    floor.car.classList.toggle("low", car.battery < 20);
  }
  floor.marks.innerHTML = "";
  for (const [a, b] of (car && car.obstacles) || []) {
    const A = floor.pos[a], B = floor.pos[b];
    if (A && B) sv("line", { x1: A.x, y1: A.y, x2: B.x, y2: B.y, class: "blocked" }, floor.marks);
  }
}

// ---------- actions ----------
$("#choose").addEventListener("click", async () => {
  const id = $("#factory").value;
  if (!id) { toast("Log in on the Carkaroo website first: that makes the factory."); return; }
  if (await post("/api/choose", { factory: id })) toast("Now choose Connect for each device, or paste the keys.");
});
$("#connect-all").addEventListener("click", async () => {
  const text = $("#paste").value;
  const d = await post("/api/connect-all", { text });
  if (!d) return;
  const on = d.devices.filter((x) => x.state === "on").length;
  toast(on === d.devices.length ? "Everything is connected. Look at the Carkaroo website!" : `${on} of ${d.devices.length} connected: see the red notes.`);
  $("#paste").value = "";       // keys don't stay on the page
});
$("#devices").addEventListener("click", async (ev) => {
  const b = ev.target.closest("button[data-dev]");
  if (!b) return;
  const id = b.dataset.dev, d = st.devices.find((x) => x.id === id);
  if (d.state === "on") {
    if (await post("/api/disconnect", { device: id })) toast(`${id} unplugged. The Carkaroo website shows it offline.`);
    return;
  }
  const input = b.closest(".device").querySelector("input");
  b.disabled = true; b.textContent = "Connecting…";
  const r = await post("/api/connect", { device: id, key: input.value, host: $("#host").value, port: Number($("#port").value) });
  b.disabled = false;
  if (r) {
    input.value = "";
    const now = r.devices.find((x) => x.id === id);
    toast(now.state === "on" ? `${id} logged in. It turns green on the Carkaroo website.` : now.error);
  }
});
$("#play").addEventListener("click", async (ev) => {
  const b = ev.target.closest("button");
  if (!b) return;
  curiousUntil = Date.now() + 3500;          // Roo wonders what the AI will do
  if (b.dataset.bat) {
    if (await post("/api/control", { cmd: "set_battery", value: Number(b.dataset.bat) })) toast(`The car's battery is now ${b.dataset.bat}%.`);
  } else if (b.id === "clear") {
    if (await post("/api/control", { cmd: "clear_obstacles" })) toast("Obstacles removed.");
  } else if (b.id === "sk-go") {
    const v = Number($("#sk-v").value), s = $("#sk-st").value, m = $("#sk-m").value;
    if (await post("/api/control", { cmd: "set_stock", station: s, material: m, stock: v })) toast(`${s}'s load cell now reads ${v} × ${m}.`);
  }
});
async function obstacle(a, b) {
  if (await post("/api/control", { cmd: "obstacle", edge: [a, b], duration_s: 60 })) {
    toast(`Obstacle on ${a}–${b} for 60 s. The pretend car stops there; watch the AI find another way.`);
  }
}

// ---------- poll ----------
async function poll() {
  try {
    const r = await fetch("/api/state", { cache: "no-store" });
    st = await r.json();
    render();
  } catch (e) { /* the simulator stopped: keep the last view */ }
  setTimeout(poll, 1000);
}
poll();
