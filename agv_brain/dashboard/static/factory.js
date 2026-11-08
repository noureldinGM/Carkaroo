// "Stations and materials" on the Setup page: build the factory (names, what each station
// uses, how much it holds) and save it (GET/POST /api/factory/settings). Uses esc, chip,
// postJson and toast from app.js. The server checks everything again before saving.
"use strict";

const FactoryEditor = (() => {
  const PRIO = [[3, "High"], [2, "Medium"], [1, "Low"]];
  let draft = null;          // {materials: [...], stations: [...], limits}
  let saved = "";            // the draft as loaded or last saved
  let forId = null;          // the factory this draft belongs to
  let readOnly = false;
  const box = () => $("#setup-factory");
  const dirty = () => draft && JSON.stringify([draft.materials, draft.stations]) !== saved;
  const matName = (id) => (draft.materials.find((m) => m.id === id) || { name: id }).name;

  // load once per factory (the Setup page polls every second: never redraw under the cursor)
  async function load(factoryId, ro) {
    if (factoryId === forId && draft && ro === readOnly) return;
    readOnly = ro;
    if (factoryId === forId && draft) { render(); return; }
    let r;
    try { r = await fetch("/api/factory/settings", { cache: "no-store" }); } catch (e) { return; }
    if (!r.ok) return;
    draft = await r.json();
    forId = factoryId;
    saved = JSON.stringify([draft.materials, draft.stations]);
    render();
  }

  // ---------- drawing ----------
  const num = (path, v, label, min, max, step = 1) =>
    `<label class="fe-num"><span>${label}</span><input type="number" data-path="${path}" value="${esc(v)}"
      min="${min}" max="${max}" step="${step}"${readOnly ? " disabled" : ""}></label>`;

  function render() {
    if (!draft) return;
    const dis = readOnly ? " disabled" : "";
    const L = draft.limits;
    const mats = draft.materials.map((m, i) => `
      <div class="fe-mat">
        ${chip(m.id)}
        <label class="fe-name"><span>Material ${esc(m.id)}</span><input data-path="m.${i}.name" value="${esc(m.name)}"
          maxlength="${L.name}"${dis}></label>
        ${num(`m.${i}.box`, m.box, "Units per box (one trip)", 1, 1000)}
        ${num(`m.${i}.warehouse`, m.warehouse, "In the warehouse when full", 0, 100000)}
        <button class="ghost small" type="button" data-del-mat="${i}"${draft.materials.length < 2 || readOnly ? " disabled" : ""}
          aria-label="Remove ${esc(m.name)}">Remove</button>
      </div>`).join("");

    const stations = draft.stations.map((s, i) => `
      <article class="fe-st">
        <header>
          <span class="sid">${esc(s.id)}</span>
          <input class="fe-st-name" data-path="s.${i}.name" value="${esc(s.name)}" maxlength="${L.name}" aria-label="Name of ${esc(s.id)}"${dis}>
          <select data-path="s.${i}.priority" aria-label="Priority of ${esc(s.id)}"${dis}>
            ${PRIO.map(([v, n]) => `<option value="${v}"${s.priority === v ? " selected" : ""}>${n} priority</option>`).join("")}
          </select>
          <button class="ghost small" type="button" data-del-st="${i}"${draft.stations.length < 2 || readOnly ? " disabled" : ""}
            aria-label="Remove ${esc(s.name)}">Remove</button>
        </header>
        ${draft.materials.map((m) => {
          const v = s.materials[m.id];
          return `<div class="fe-use${v ? " on" : ""}">
            <label class="fe-tick"><input type="checkbox" data-use="${i}" data-mat="${esc(m.id)}"${v ? " checked" : ""}${dis}>
              ${chip(m.id)}<span>uses ${esc(m.name)}</span></label>
            ${v ? `<div class="fe-nums">
              ${num(`s.${i}.${m.id}.capacity`, v.capacity, "Holds", 1, 10000)}
              ${num(`s.${i}.${m.id}.safety`, v.safety, "Safety level", 0, 10000)}
              ${num(`s.${i}.${m.id}.stock`, v.stock, "Stock at start", 0, 10000)}
              ${num(`s.${i}.${m.id}.use_per_min`, v.use_per_min, "Uses per minute", 0, 1000, 0.1)}
            </div>` : ""}
          </div>`;
        }).join("")}
      </article>`).join("");

    box().innerHTML = `
      <h4 class="fe-h">Materials <span class="quiet">${draft.materials.length} of ${L.materials}</span></h4>
      <div class="fe-mats">${mats}</div>
      <button class="ghost small" type="button" id="fe-add-mat"${draft.materials.length >= L.materials || readOnly ? " disabled" : ""}>+ Add a material</button>
      <h4 class="fe-h">Stations <span class="quiet">${draft.stations.length} of ${L.stations}</span></h4>
      <div class="fe-sts">${stations}</div>
      <button class="ghost small" type="button" id="fe-add-st"${draft.stations.length >= L.stations || readOnly ? " disabled" : ""}>+ Add a station</button>
      <div class="row fe-save">
        <button id="fe-save" type="button"${dis}>Save stations and materials</button>
        <button class="ghost" id="fe-reset" type="button"${dis}>Undo changes</button>
        <span class="fe-state" id="fe-state"></span>
      </div>
      <span class="err-text" id="fe-err" role="alert"></span>`;
    showState();
  }

  function showState() {
    const el = $("#fe-state");
    if (el) el.textContent = dirty() ? "Not saved yet" : "Saved";
    if (el) el.classList.toggle("unsaved", !!dirty());
  }

  // ---------- editing ----------
  function setPath(path, raw) {
    const p = path.split(".");
    const isNum = (k) => k !== "name";
    const val = (k) => (isNum(k) ? (raw === "" ? NaN : Number(raw)) : raw);
    if (p[0] === "m") draft.materials[+p[1]][p[2]] = val(p[2]);
    else if (p.length === 3) draft.stations[+p[1]][p[2]] = val(p[2]);
    else draft.stations[+p[1]].materials[p[2]][p[3]] = val(p[3]);
  }

  function freeId(all, used) { return all.find((x) => !used.includes(x)); }

  function addMaterial() {
    const id = freeId(["A", "B", "C", "D", "E"], draft.materials.map((m) => m.id));
    if (!id) return;
    draft.materials.push({ id, name: `Material ${id}`, box: 10, warehouse: 200 });
    // a material must be used somewhere: the first station uses it to start with
    draft.stations[0].materials[id] = { capacity: 30, safety: 6, stock: 20, use_per_min: 1 };
    render();
  }
  function addStation() {
    const id = freeId(Array.from({ length: 8 }, (_, k) => `S${k + 1}`), draft.stations.map((s) => s.id));
    if (!id) return;
    const m = draft.materials[0].id;
    draft.stations.push({ id, name: `Station ${id.slice(1)}`, priority: 2,
      materials: { [m]: { capacity: 30, safety: 6, stock: 20, use_per_min: 1 } } });
    render();
  }

  box().addEventListener("input", (ev) => {
    const t = ev.target;
    if (t.dataset.path) { setPath(t.dataset.path, t.value); showState(); $("#fe-err").textContent = ""; }
  });
  box().addEventListener("change", (ev) => {
    const t = ev.target;
    if (t.matches("select[data-path]")) { setPath(t.dataset.path, t.value); showState(); }
    if (t.dataset.use !== undefined) {
      const s = draft.stations[+t.dataset.use], m = t.dataset.mat;
      if (t.checked) s.materials[m] = { capacity: 30, safety: 6, stock: 20, use_per_min: 1 };
      else delete s.materials[m];
      render();
    }
  });
  box().addEventListener("click", async (ev) => {
    const b = ev.target.closest("button");
    if (!b || !draft) return;
    if (b.id === "fe-add-mat") addMaterial();
    else if (b.id === "fe-add-st") addStation();
    else if (b.dataset.delMat !== undefined) {
      const m = draft.materials[+b.dataset.delMat];
      if (!confirm(`Remove ${m.name} (${m.id}) from the factory and from every station?`)) return;
      draft.materials.splice(+b.dataset.delMat, 1);
      for (const s of draft.stations) delete s.materials[m.id];
      render();
    } else if (b.dataset.delSt !== undefined) {
      const s = draft.stations[+b.dataset.delSt];
      if (!confirm(`Remove ${s.name} (${s.id})?`)) return;
      draft.stations.splice(+b.dataset.delSt, 1);
      render();
    } else if (b.id === "fe-reset") {
      [draft.materials, draft.stations] = JSON.parse(saved);
      render();
    } else if (b.id === "fe-save") save(b);
  });

  async function save(btn) {
    btn.disabled = true; btn.textContent = "Saving…";
    const r = await postJson("/api/factory/settings", { materials: draft.materials, stations: draft.stations });
    btn.disabled = false; btn.textContent = "Save stations and materials";
    if (!r.ok) { $("#fe-err").textContent = r.data.error || "Could not save."; return; }
    saved = JSON.stringify([draft.materials, draft.stations]);
    render();
    const probs = r.data.track_problems || [];
    toast(probs.length ? "Saved. Now draw the new stations on the track." : r.data.running
      ? "Saved. The factory restarted with them." : "Saved. Press Start when you're ready.");
    setupShape = "";
    loadSetup();
  }

  return {
    load,
    dirty: () => !!dirty(),
    forget() { draft = null; forId = null; },
  };
})();
