// Track editor on the Setup page: draw the real track on a 10 cm grid.
// The server checks every change (POST /api/track/validate) and saves it (POST /api/track/save).
"use strict";

const TrackEditor = (() => {
  const K = 2;          // screen pixels per cm
  const SNAP = 10;      // grid step in cm
  const TOOLS = [
    ["line", "Line", "Click points to draw straight lines. Each click on an empty spot adds a junction. Esc stops."],
    ["junction", "Junction", "Click a spot or a line to add a junction (a + or T crossing on the track)."],
    ["rack", "Rack", "Click a line end to put the rack for the chosen material."],
    ["station", "Station", "Click a line end to put the chosen station."],
    ["dock", "Dock", "Click a line end for the charging dock, where the car starts."],
    ["move", "Move", "Drag a point to move it. Click a line to give its real length (for a curved line)."],
    ["delete", "Delete", "Click a point or a line to remove it."],
  ];
  let track = { nodes: {}, edges: [] };
  let tool = "line";
  let from = null;          // line tool: the point the next line starts from
  let selEdge = null;       // move tool: the line being edited
  let drag = null;
  let hover = null;         // snapped cursor position in cm
  let history = [];
  let saved = "";           // the track as it was opened or last saved (to know if it changed)
  let open = false;
  let problems = { errors: [], warnings: [] };
  let checkTimer = 0;
  let el = {};

  // ---------- model ----------
  const snapshot = () => JSON.stringify(track);
  function remember() { history.push(snapshot()); if (history.length > 100) history.shift(); }
  const dirty = () => snapshot() !== saved;
  function undo() {
    if (!history.length) return;
    track = JSON.parse(history.pop()); from = null; selEdge = null;
    changed();
  }
  const nodeAt = (x, y) => Object.keys(track.nodes).find((id) => track.nodes[id].x === x && track.nodes[id].y === y);
  const hasEdge = (a, b) => track.edges.some((e) => (e[0] === a && e[1] === b) || (e[0] === b && e[1] === a));
  function nextJunction() {
    let n = 1;
    while (track.nodes[`J${n}`]) n++;
    return `J${n}`;
  }
  function edgeThrough(x, y) {   // a line that passes over (x, y), between its two ends
    return track.edges.findIndex(([a, b]) => {
      const A = track.nodes[a], B = track.nodes[b];
      if (!A || !B) return false;
      if (A.x === B.x && A.x === x) return y > Math.min(A.y, B.y) && y < Math.max(A.y, B.y);
      if (A.y === B.y && A.y === y) return x > Math.min(A.x, B.x) && x < Math.max(A.x, B.x);
      return false;
    });
  }
  function addNode(id, type, x, y) {
    track.nodes[id] = { x, y, type };
    // dropped on a line (or where two lines cross): split every line there
    for (let k = edgeThrough(x, y); k >= 0; k = edgeThrough(x, y)) {
      const [a, b] = track.edges[k];
      track.edges.splice(k, 1, [a, id], [id, b]);
    }
  }
  function renameOrPlace(id, type, x, y) {
    const here = nodeAt(x, y);
    if (here) {                        // turn an existing point (a line end) into this rack/station/dock
      if (track.nodes[id] && id !== here) { toast(`${id} is already on the track. Delete it first, or use Move.`); return false; }
      const n = track.nodes[here];
      delete track.nodes[here];
      track.nodes[id] = { ...n, type };
      track.edges = track.edges.map((e) => e.map((v, i) => (i < 2 && v === here ? id : v)));
      return true;
    }
    if (track.nodes[id]) { toast(`${id} is already on the track. Use Move to put it somewhere else.`); return false; }
    addNode(id, type, x, y);
    return true;
  }
  function connect(a, b) {
    const A = track.nodes[a], B = track.nodes[b];
    if (a === b || hasEdge(a, b)) return true;
    if (A.x !== B.x && A.y !== B.y) { toast("Lines must go straight across or straight up/down."); return false; }
    track.edges.push([a, b]);
    return true;
  }
  function removeNode(id) {
    delete track.nodes[id];
    track.edges = track.edges.filter((e) => e[0] !== id && e[1] !== id);
  }

  // ---------- drawing ----------
  function extents() {
    const xs = Object.values(track.nodes).map((n) => n.x), ys = Object.values(track.nodes).map((n) => n.y);
    return [Math.max(400, ...xs.map((x) => x + 100)), Math.max(200, ...ys.map((y) => y + 80))];
  }

  function draw() {
    const svg = el.svg;
    const [W, H] = extents();
    svg.setAttribute("viewBox", `-40 -30 ${W * K + 60} ${H * K + 50}`);
    svg.innerHTML = "";
    const grid = sv("g", { class: "ed-grid" }, svg);
    for (let x = 0; x <= W; x += SNAP) sv("line", { x1: x * K, y1: 0, x2: x * K, y2: H * K, class: x % 50 ? "g1" : "g5" }, grid);
    for (let y = 0; y <= H; y += SNAP) sv("line", { x1: 0, y1: y * K, x2: W * K, y2: y * K, class: y % 50 ? "g1" : "g5" }, grid);
    for (let x = 0; x <= W; x += 100) sv("text", { x: x * K, y: -10, "text-anchor": "middle", class: "ed-axis" }, grid).textContent = `${x}`;
    for (let y = 100; y <= H; y += 100) sv("text", { x: -8, y: y * K + 4, "text-anchor": "end", class: "ed-axis" }, grid).textContent = `${y}`;
    sv("text", { x: -8, y: -10, "text-anchor": "end", class: "ed-axis" }, grid).textContent = "cm";

    const lines = sv("g", {}, svg);
    track.edges.forEach((e, i) => {
      const A = track.nodes[e[0]], B = track.nodes[e[1]];
      if (!A || !B) return;
      const bent = A.x !== B.x && A.y !== B.y;
      if (i === selEdge) sv("line", { x1: A.x * K, y1: A.y * K, x2: B.x * K, y2: B.y * K, class: "ed-sel" }, lines);
      sv("line", { x1: A.x * K, y1: A.y * K, x2: B.x * K, y2: B.y * K, class: `ed-line${bent ? " bad" : ""}` }, lines);
      const len = e[2] ? `${e[2]} cm (curved)` : `${Math.abs(A.x - B.x) + Math.abs(A.y - B.y)} cm`;
      const mx = (A.x + B.x) / 2 * K, my = (A.y + B.y) / 2 * K;
      sv("text", { x: mx + (A.x === B.x ? 8 : 0), y: my + (A.x === B.x ? 4 : -8), "text-anchor": A.x === B.x ? "start" : "middle",
        class: "ed-len" }, lines).textContent = len;
      const hit = sv("line", { x1: A.x * K, y1: A.y * K, x2: B.x * K, y2: B.y * K, class: "ed-hit", "data-edge": i }, lines);
      hit.addEventListener("pointerdown", (ev) => { ev.stopPropagation(); edgeClick(i, ev); });
    });

    // the line being drawn
    if (tool === "line" && from && hover && track.nodes[from]) {
      const A = track.nodes[from];
      const ok = A.x === hover.x || A.y === hover.y;
      sv("line", { x1: A.x * K, y1: A.y * K, x2: hover.x * K, y2: hover.y * K, class: `ed-preview${ok ? "" : " bad"}` }, svg);
    }

    const pts = sv("g", {}, svg);
    for (const [id, n] of Object.entries(track.nodes)) {
      const g = sv("g", { class: `ed-node ${n.type}${id === from ? " from" : ""}`, transform: `translate(${n.x * K},${n.y * K})` }, pts);
      if (n.type === "junction") {
        sv("circle", { r: 7, class: "ed-j" }, g);
        sv("text", { x: 10, y: -9, class: "ed-label" }, g).textContent = id;
      } else {
        const mat = n.type === "rack" ? Object.keys(layout.materials).find((m) => layout.materials[m].rack === id) : null;
        sv("rect", { x: -30, y: -14, width: 60, height: 28, rx: 7, class: `ed-box ${mat ? `chip ${mat}` : ""}` }, g);
        sv("text", { y: 5, "text-anchor": "middle", class: `ed-box-text${mat ? " on-chip" : ""}` }, g).textContent = id;
      }
      g.addEventListener("pointerdown", (ev) => { ev.stopPropagation(); nodeDown(id, ev); });
    }
    if (hover && tool !== "move" && tool !== "delete") {
      sv("circle", { cx: hover.x * K, cy: hover.y * K, r: 4, class: "ed-cursor" }, svg);
    }
    el.coords.textContent = hover ? `x ${hover.x} cm · y ${hover.y} cm` : "";
  }

  function cmFromEvent(ev) {
    const pt = el.svg.createSVGPoint();
    pt.x = ev.clientX; pt.y = ev.clientY;
    const p = pt.matrixTransform(el.svg.getScreenCTM().inverse());
    return { x: Math.max(0, Math.round(p.x / K / SNAP) * SNAP), y: Math.max(0, Math.round(p.y / K / SNAP) * SNAP) };
  }

  // ---------- input ----------
  function chosen(kind) { return el[kind].value; }

  function place(type, p) {
    if (type === "junction") {
      if (nodeAt(p.x, p.y)) return;
      remember(); addNode(nextJunction(), "junction", p.x, p.y); changed();
    } else {
      const id = type === "rack" ? layout.materials[chosen("rack")].rack : type === "station" ? chosen("station") : layout.dock;
      remember();
      if (!renameOrPlace(id, type, p.x, p.y)) { history.pop(); return; }
      changed();
    }
  }

  function gridDown(ev) {
    const p = cmFromEvent(ev);
    if (tool === "line") {
      const here = nodeAt(p.x, p.y);
      if (from && track.nodes[from]) {
        const A = track.nodes[from];
        if (A.x !== p.x && A.y !== p.y) { toast("Lines must go straight across or straight up/down."); return; }
      }
      remember();
      let id = here;
      if (!id) { id = nextJunction(); addNode(id, "junction", p.x, p.y); }
      if (from && track.nodes[from] && !connect(from, id)) { history.pop(); return; }
      from = id;
      changed();
    } else if (["junction", "rack", "station", "dock"].includes(tool)) {
      place(tool, p);
    } else {
      selEdge = null; draw(); showEdge();
    }
  }

  function nodeDown(id, ev) {
    if (tool === "line") {
      if (from && from !== id) {
        remember();
        if (!connect(from, id)) { history.pop(); return; }
      }
      from = id;
      changed();
    } else if (tool === "delete") {
      remember(); removeNode(id); if (from === id) from = null; changed();
    } else if (tool === "move") {
      drag = { id, start: snapshot(), moved: false };
      el.svg.setPointerCapture(ev.pointerId);
    } else {
      place(tool, { x: track.nodes[id].x, y: track.nodes[id].y });
    }
  }

  function edgeClick(i, ev) {
    if (tool === "delete") {
      remember(); track.edges.splice(i, 1); selEdge = null; changed();
    } else if (tool === "move") {
      selEdge = i; draw(); showEdge();
    } else {
      gridDown(ev);           // other tools act on the spot under the line
    }
  }

  function showEdge() {
    const box = el.edgeBox;
    if (selEdge === null || !track.edges[selEdge]) { box.hidden = true; return; }
    const [a, b, len] = track.edges[selEdge];
    const A = track.nodes[a], B = track.nodes[b];
    box.hidden = false;
    box.innerHTML = `<b>Line ${esc(a)}–${esc(b)}</b>
      <p>Straight distance ${Math.abs(A.x - B.x) + Math.abs(A.y - B.y)} cm. If the real line is curved, give its real length:</p>
      <div class="row"><input id="ed-len" type="number" min="1" placeholder="cm" value="${len || ""}" aria-label="Real length in cm">
      <button class="ghost small" id="ed-len-set">Set</button><button class="ghost small" id="ed-len-del">Delete line</button></div>`;
    $("#ed-len-set").addEventListener("click", () => {
      const v = Number($("#ed-len").value);
      remember();
      const e = track.edges[selEdge];
      if (Number.isFinite(v) && v > 0) e[2] = v; else e.length = 2;
      changed();
    });
    $("#ed-len-del").addEventListener("click", () => { remember(); track.edges.splice(selEdge, 1); selEdge = null; changed(); });
  }

  function pointerMove(ev) {
    const p = cmFromEvent(ev);
    if (drag) {
      const n = track.nodes[drag.id];
      if (n.x !== p.x || n.y !== p.y) {
        if (nodeAt(p.x, p.y)) return;
        if (!drag.moved) { history.push(drag.start); drag.moved = true; }
        n.x = p.x; n.y = p.y;
        hover = p; draw(); scheduleCheck();
      }
      return;
    }
    if (!hover || hover.x !== p.x || hover.y !== p.y) { hover = p; draw(); }
  }

  function setTool(t) {
    tool = t; from = null; selEdge = null;
    el.bar.querySelectorAll("[data-tool]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.tool === t)));
    el.hint.textContent = TOOLS.find((x) => x[0] === t)[2];
    el.rackWrap.hidden = t !== "rack";
    el.stationWrap.hidden = t !== "station";
    showEdge(); draw();
  }

  // ---------- checking and saving ----------
  function changed() { draw(); showEdge(); scheduleCheck(); }

  function scheduleCheck() {
    clearTimeout(checkTimer);
    checkTimer = setTimeout(check, 250);
  }

  async function check() {
    const r = await postJson("/api/track/validate", { track });
    problems = r.data.errors ? r.data : { errors: [r.data.error || "Could not check the track."], warnings: [] };
    const ok = !problems.errors.length;
    el.problems.innerHTML = (ok ? `<li class="ok">✓ Ready: the car can drive every trip on this track.</li>` : "")
      + problems.errors.map((p) => `<li class="err">${esc(p)}</li>`).join("")
      + problems.warnings.map((p) => `<li class="warn">${esc(p)}</li>`).join("");
    el.save.disabled = el.use.disabled = !ok;
  }

  async function save(andUse) {
    const name = el.name.value.trim();
    if (!name) { el.nameErr.textContent = "Give the track a name first."; el.name.focus(); return; }
    el.nameErr.textContent = "";
    let r = await postJson("/api/track/save", { name, track });
    if (!r.ok && r.data.exists) {
      if (!confirm(`A track named "${name}" already exists. Replace it with this one?`)) return;
      r = await postJson("/api/track/save", { name, track, overwrite: true });
    }
    if (!r.ok) { toast(r.data.error || "Could not save the track."); return; }
    saved = snapshot();
    if (!andUse) { toast(`Saved "${name}". Choose it under Factory mode to use it.`); return; }
    el.use.disabled = true; el.use.textContent = "Switching…";
    const m = await postJson("/api/mode", { track: r.data.id });
    el.use.textContent = "Save and use it";
    el.use.disabled = false;
    toast(m.ok ? `Saved and now using "${name}".` : (m.data.error || "Saved, but could not switch to it."));
    if (m.ok) close(true);
  }

  // ---------- open / close ----------
  function build() {
    const box = $("#editor");
    const rackOpts = Object.entries(layout.materials).map(([m, i]) => `<option value="${esc(m)}">${esc(i.rack)} · ${esc(m)} ${esc(i.name)}</option>`).join("");
    const stOpts = Object.entries(layout.stations).map(([id, s]) => `<option value="${esc(id)}">${esc(id)} · ${esc(s.name)}</option>`).join("");
    box.innerHTML = `
      <div class="ed-bar" role="toolbar" aria-label="Track tools">
        ${TOOLS.map(([id, name]) => `<button class="ghost small" data-tool="${id}" aria-pressed="false">${name}</button>`).join("")}
        <span class="ed-pick" id="ed-rack-wrap" hidden><select id="ed-rack" aria-label="Rack for which material">${rackOpts}</select></span>
        <span class="ed-pick" id="ed-station-wrap" hidden><select id="ed-station" aria-label="Which station">${stOpts}</select></span>
        <button class="ghost small" id="ed-undo" title="Ctrl+Z">Undo</button>
      </div>
      <p class="ed-hint"><span id="ed-hint"></span> <span class="ed-coords" id="ed-coords"></span></p>
      <div class="ed-main">
        <div class="ed-canvas"><svg id="ed-svg" role="img" aria-label="Track drawing on a 10 cm grid"></svg></div>
        <aside class="ed-side">
          <div id="ed-edge" class="ed-edge" hidden></div>
          <h4>Check</h4>
          <ul id="ed-problems" class="ed-problems"><li>Checking…</li></ul>
          <label class="ed-name">Track name <input id="ed-name" maxlength="40" placeholder="e.g. Exhibition table"></label>
          <span class="err-text" id="ed-name-err" role="alert"></span>
          <div class="row">
            <button id="ed-use">Save and use it</button>
            <button class="ghost" id="ed-save">Save</button>
            <button class="ghost" id="ed-close">Close</button>
          </div>
        </aside>
      </div>`;
    el = { svg: $("#ed-svg"), bar: box.querySelector(".ed-bar"), hint: $("#ed-hint"), coords: $("#ed-coords"),
      rack: $("#ed-rack"), station: $("#ed-station"), rackWrap: $("#ed-rack-wrap"), stationWrap: $("#ed-station-wrap"),
      edgeBox: $("#ed-edge"), problems: $("#ed-problems"), name: $("#ed-name"), nameErr: $("#ed-name-err"),
      save: $("#ed-save"), use: $("#ed-use") };
    el.bar.querySelectorAll("[data-tool]").forEach((b) => b.addEventListener("click", () => setTool(b.dataset.tool)));
    $("#ed-undo").addEventListener("click", undo);
    el.svg.addEventListener("pointerdown", gridDown);
    el.svg.addEventListener("pointermove", pointerMove);
    el.svg.addEventListener("pointerup", () => { if (drag && drag.moved) changed(); drag = null; });
    el.svg.addEventListener("pointerleave", () => { if (!drag) { hover = null; draw(); } });
    el.name.addEventListener("input", () => { el.nameErr.textContent = ""; });
    el.save.addEventListener("click", () => save(false));
    el.use.addEventListener("click", () => save(true));
    $("#ed-close").addEventListener("click", () => close(false));
  }

  function keys(ev) {
    if (!open) return;
    if (ev.key === "Escape") { from = null; selEdge = null; draw(); showEdge(); }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "z" && ev.target.tagName !== "INPUT") { ev.preventDefault(); undo(); }
  }
  document.addEventListener("keydown", keys);

  function close(force) {
    if (!force && dirty() && !confirm("Close the editor without saving your changes?")) return;
    open = false;
    $("#editor").hidden = true;
    $("#setup-track").hidden = false;
    setupShape = "";
    loadSetup();
  }

  return {
    isOpen: () => open,
    open(raw, name) {
      track = { nodes: JSON.parse(JSON.stringify(raw.nodes || {})), edges: (raw.edges || []).map((e) => [...e]) };
      for (const n of Object.values(track.nodes)) { n.x = Number(n.x); n.y = Number(n.y); }
      history = []; from = null; selEdge = null; hover = null;
      open = true;
      saved = snapshot();
      build();
      el.name.value = name || "";
      $("#setup-track").hidden = true;
      $("#editor").hidden = false;
      setTool(Object.keys(track.nodes).length ? "move" : "line");
      check();
      $("#editor").scrollIntoView({ behavior: "smooth", block: "start" });
    },
  };
})();
