// Roo's reactions: one face for the logo and for Roo the character, driven by the live data.
// Plain <script>: window.Roo. Needs roo.css.
//
//   Roo.logo(el)                 -> the "Carkar" + eyes logo (the two o's are Roo's eyes)
//   Roo.buddy(el)                -> Roo the car with a speech bubble
//   x.set("worried", "Hurry!")   -> change the mood (and the line in the bubble)
//   Roo.read(snapshot, memory)   -> { mood, say } from /api/snapshot, see RULES below
//
// Moods only change the eyes, the antenna and small effects around the car (a tear, a drop,
// "!", Zzz, a bolt, confetti). The car itself is never redrawn.
(function (root) {
  "use strict";

  let uid = 0;
  const NS = "http://www.w3.org/2000/svg";
  const reduce = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------- the eye: white, pupil with a shine, an eyelid, a closed-happy arc, a closed-flat line ----------
  // u = 1/10 of the eye radius, so pupil offsets look the same at every size
  function eye(cx, cy, r, white, ring, side) {
    const id = `roo-eye-${++uid}`;
    const pr = r * 0.42;
    return `
      <g class="eye eye-${side}" style="--u:${(r / 10).toFixed(3)}">
        <clipPath id="${id}"><circle cx="${cx}" cy="${cy}" r="${white}"/></clipPath>
        ${ring ? `<circle class="eye-ring" cx="${cx}" cy="${cy}" r="${r}"/>` : ""}
        <circle class="eye-white" cx="${cx}" cy="${cy}" r="${white}"/>
        <g clip-path="url(#${id})">
          <g class="pupil"><circle cx="${cx + r * 0.18}" cy="${cy + r * 0.05}" r="${pr}"/>
            <circle class="shine" cx="${cx + r * 0.32}" cy="${cy - r * 0.16}" r="${pr * 0.34}"/></g>
          <g class="lid-w"><rect class="lid" x="${cx - white * 1.3}" y="${cy - white * 1.05}" width="${white * 2.6}" height="${white * 2.1}"/></g>
        </g>
        <path class="mark happy" d="M ${cx - white * 0.62} ${cy + white * 0.22} Q ${cx} ${cy - white * 0.78} ${cx + white * 0.62} ${cy + white * 0.22}"/>
        <path class="mark shut" d="M ${cx - white * 0.6} ${cy + white * 0.1} Q ${cx} ${cy + white * 0.42} ${cx + white * 0.6} ${cy + white * 0.1}"/>
      </g>`;
  }

  // ---------- the logo: "Carkar" in the display font, then the eyes as "oo", the antenna over them ----------
  function logo(el, opts = {}) {
    el.classList.add("roo-logo");
    el.innerHTML = `<span class="word">Carkar</span><svg class="roo-face eyes" viewBox="0 0 62 46" aria-hidden="true">
        <path class="antenna" d="M 6 15 Q 31 -4 56 15"/>
        ${eye(15, 32, 13, 9, true, "l")}${eye(46, 32, 13, 9, true, "r")}
      </svg>`;
    el.setAttribute("aria-label", "Carkaroo");
    const f = face(el, el.querySelector("svg"), opts);
    logoTouch(f);
    return f;
  }

  // ---------- Roo the car (side view, from logo/roo-cartoon.svg) with effects and a speech bubble ----------
  function buddy(el, opts = {}) {
    el.classList.add("roo-buddy");
    el.innerHTML = `<span class="roo-body" tabindex="0" role="button" aria-label="Roo, the Carkaroo car. Tap, hold or drag me.">
      <svg class="roo-face car" viewBox="-17 -15 76 48" aria-hidden="true">
        <g class="fx-speed"><path d="M-12 9 H-3 M-10 14 H-1 M-12 19 H-4"/></g>
        <g class="bob">
          <path class="antenna" d="M8 6 C 8 -0.5, 16 -0.5, 17 6"/>
          <rect class="body" x="2" y="6" width="36" height="15" rx="5"/>
          <rect class="stripe" x="2.8" y="12" width="28" height="3.4"/>
          <path class="seam" d="M6 9 H22"/>
          <rect class="head" x="30" y="1.5" width="13" height="10" rx="2.5"/>
          ${eye(33.8, 6.5, 2.9, 2.9, false, "l")}${eye(39.2, 6.5, 2.9, 2.9, false, "r")}
          <path class="fx-tear" d="M33.6 10.2 q -1.1 1.9 0 2.6 q 1.1 -0.7 0 -2.6 z"/>
          <path class="fx-drop" d="M44.6 -0.6 q -1.6 2.6 0 3.6 q 1.6 -1 0 -3.6 z"/>
        </g>
        <g class="wheel"><circle class="tire" cx="11" cy="22" r="6.4"/><circle class="hub" cx="11" cy="22" r="3"/></g>
        <g class="wheel"><circle class="tire" cx="29" cy="22" r="6.4"/><circle class="hub" cx="29" cy="22" r="3"/></g>
        <text class="fx-bang" x="47" y="-3">!</text>
        <g class="fx-zzz"><text x="44" y="-2">z</text><text x="48" y="-6">z</text><text x="52.5" y="-10.5">Z</text></g>
        <path class="fx-bolt" d="M47 -9 l -3.4 6 h 2.8 l -1.6 5.4 l 4.6 -7 h -2.9 l 1.9 -4.4 z"/>
        <g class="fx-dots"><circle cx="45" cy="-3" r="1.1"/><circle cx="48.5" cy="-5" r="1.4"/><circle cx="52.5" cy="-7.5" r="1.8"/></g>
        <g class="fx-confetti"><rect x="20" y="-6" width="2" height="2"/><rect x="27" y="-9" width="2" height="2"/>
          <rect x="34" y="-11" width="2" height="2"/><rect x="41" y="-8" width="2" height="2"/><rect x="13" y="-3" width="2" height="2"/>
          <rect x="47" y="-12" width="2" height="2"/></g>
        <g class="fx-hearts"><path d="M46 -4 c -1.6 -2.4 -4.4 -0.6 -2.6 1.6 l 2.6 2.6 l 2.6 -2.6 c 1.8 -2.2 -1 -4 -2.6 -1.6 z"/>
          <path d="M52 -10 c -1.2 -1.8 -3.3 -0.5 -2 1.2 l 2 2 l 2 -2 c 1.3 -1.7 -.8 -3 -2 -1.2 z"/></g>
        <g class="fx-stars"><path d="M45 -6 l .9 2 2 .3 -1.5 1.4 .4 2 -1.8 -1 -1.8 1 .4 -2 -1.5 -1.4 2 -.3 z"/>
          <path d="M26 -8 l .7 1.5 1.6 .2 -1.2 1.1 .3 1.6 -1.4 -.8 -1.4 .8 .3 -1.6 -1.2 -1.1 1.6 -.2 z"/></g>
        <text class="fx-note" x="46" y="-4">&#9834;</text>
      </svg></span>
      <p class="roo-say" aria-live="polite"></p>`;
    const f = face(el, el.querySelector("svg"), opts);
    interact(f, el.querySelector(".roo-body"));
    return f;
  }

  // ---------- shared behaviour: mood, actions, blinking, looking at the pointer ----------
  const faces = [];
  let lastInput = Date.now(), pointer = null;
  function face(el, svg, opts) {
    const say = el.querySelector(".roo-say");
    const f = {
      el, svg, mood: null, line: "", act: null, timer: null,
      // the live mood, from the data
      set(mood, line) {
        if (mood !== f.mood) {
          f.mood = mood;
          el.dataset.mood = mood;
          replay(svg, "enter");
        }
        if (line !== undefined) f.line = line;
        if (say && !f.act && say.textContent !== f.line) say.textContent = f.line;
        return f;
      },
      // a short action on top of the mood (a boop, a wink, a yawn...), then back to the mood
      play(act, ms = 1400, line) {
        clearTimeout(f.timer);
        f.act = act;
        el.dataset.act = act;
        replay(svg, "acting");
        if (say && line) say.textContent = line;
        if (ms !== Infinity) f.timer = setTimeout(f.stop, ms);
        return f;
      },
      stop() {
        clearTimeout(f.timer);
        f.act = null; delete el.dataset.act;
        if (say) say.textContent = f.line;
      },
      serious: () => ["asleep", "shocked", "sad"].includes(f.mood),
    };
    f.set(opts.mood || "happy", opts.say);
    faces.push(f);
    return f;
  }
  function replay(svg, cls) { svg.classList.remove(cls); void svg.getBoundingClientRect(); svg.classList.add(cls); }

  // ---------- touching Roo: tap (boop), many taps (dizzy), hold (rev, then zoom), drag (ride along), rub (tickle) ----------
  const LINES = {
    boop: ["Hey!", "Beep beep!", "Hi there!", "Boop!", "That's me, Roo!", "Ready when you are."],
    dizzy: ["Whoa... too many boops.", "The floor is spinning..."],
    rev: ["Vroom... vroom...", "Revving up..."],
    dash: ["Zoom!", "Fastest car on the line!"],
    ride: ["Wheee!", "Where are we going?"],
    back: ["Backing up!", "Beep... beep... beep..."],
    drop: ["Again!", "That was fun."],
    tickle: ["Hehe, that tickles!", "Stop it! Hehe."],
    hello: ["There you are!", "Welcome back!"],
    away: ["Where did you go?", "Hello? Anyone there?"],
    yawn: ["Yawn... it's quiet today.", "Yawn... anyone there?"],
    nap: ["Zzz... wake me with a tap."],
    wake: ["Oh! I'm awake!", "I wasn't sleeping, I promise."],
    serious: { sad: "I know. I'm on it.", shocked: "Something is in my way.", asleep: "I'm offline. Turn me on from the Setup page." },
  };
  const pick = (a) => a[Math.floor(Math.random() * a.length)];

  function interact(f, body) {
    let down = null, taps = [], rub = 0, rubSince = 0;
    const clampX = (x) => Math.max(-120, Math.min(160, x));
    body.addEventListener("pointerdown", (ev) => {
      lastInput = Date.now();
      down = { x: ev.clientX, y: ev.clientY, moved: false, held: false };
      body.setPointerCapture(ev.pointerId);
      down.hold = setTimeout(() => {
        if (!down || down.moved) return;
        down.held = true;
        if (!f.serious()) f.play("rev", Infinity, pick(LINES.rev));
      }, 450);
    });
    body.addEventListener("pointermove", (ev) => {
      // rubbing over Roo without pressing tickles it
      if (!down) {
        if (f.serious() || ev.pointerType !== "mouse") return;
        const now = Date.now();
        if (now - rubSince > 1200) { rub = 0; rubSince = now; }
        rub += Math.abs(ev.movementX) + Math.abs(ev.movementY);
        if (rub > 900 && f.act !== "tickle") { f.play("tickle", 1600, pick(LINES.tickle)); rub = 0; }
        return;
      }
      const dx = ev.clientX - down.x;
      if (!down.moved && Math.abs(dx) + Math.abs(ev.clientY - down.y) > 8) {
        down.moved = true; clearTimeout(down.hold);
        body.classList.add("dragging");
      }
      if (down.moved) {
        body.style.setProperty("--dx", `${clampX(dx)}px`);
        const act = dx < 0 ? "back" : "ride";
        if (f.act !== act && !f.serious()) f.play(act, Infinity, pick(LINES[act]));
      }
    });
    const up = () => {
      if (!down) return;
      clearTimeout(down.hold);
      const d = down; down = null;
      body.classList.remove("dragging");
      if (d.moved) {                       // let go: roll back home
        body.style.setProperty("--dx", "0px");
        if (!f.serious()) f.play("drop", 1300, pick(LINES.drop)); else f.stop();
      } else if (d.held) {                 // held: zoom off and come back
        f.play("dash", 1100, pick(LINES.dash));
      } else boop();
    };
    body.addEventListener("pointerup", up);
    body.addEventListener("pointercancel", up);
    body.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); boop(); } });

    function boop() {
      lastInput = Date.now();
      if (f.act === "nap") { f.play("wake", 1600, pick(LINES.wake)); return; }
      if (f.serious()) { f.play("blinkonce", 600, LINES.serious[f.mood]); return; }
      const now = Date.now();
      taps = taps.filter((t) => now - t < 2500); taps.push(now);
      if (taps.length >= 5) { taps = []; f.play("dizzy", 2200, pick(LINES.dizzy)); return; }
      f.play(taps.length >= 3 ? "giggle" : "boop", 1200, pick(taps.length >= 3 ? LINES.tickle : LINES.boop));
    }
  }

  // ---------- life: blinking, looking at you, fidgets when calm, yawns and naps when nobody is around ----------
  function blinkLoop() {
    for (const f of faces) {
      if (!LOOKS[f.mood] || !LOOKS[f.mood].blink || f.act) continue;
      f.el.classList.add("blink");
      setTimeout(() => f.el.classList.remove("blink"), 150);
    }
    setTimeout(blinkLoop, 2500 + Math.random() * 3500);
  }
  function look() {
    for (const f of faces) {
      const b = f.svg.getBoundingClientRect();
      if (!pointer || f.mood === "asleep" || f.act === "nap" || !b.width) {
        f.el.style.removeProperty("--fx"); f.el.style.removeProperty("--fy"); f.el.style.removeProperty("--lean"); continue;
      }
      const dx = pointer.x - (b.left + b.width * 0.72), dy = pointer.y - (b.top + b.height * 0.35);
      const d = Math.hypot(dx, dy) || 1, k = Math.min(1, d / 260);
      f.el.style.setProperty("--fx", (3.2 * k * dx / d).toFixed(2));
      f.el.style.setProperty("--fy", (2.8 * k * dy / d).toFixed(2));
      // lean a little toward the pointer when it's close
      const near = Math.max(0, 1 - d / 500);
      f.el.style.setProperty("--lean", `${(near * 5 * (dy < 0 ? -1 : 1) * Math.sign(dx)).toFixed(2)}deg`);
    }
  }
  const FIDGETS = [["lookaround", 2200], ["wiggle", 1200], ["hum", 2000, ["La la la...", "Hop, drop, keep the line running!"]],
    ["hopsmall", 800], ["stretch", 1500]];
  function lifeLoop() {
    const idle = Date.now() - lastInput;
    for (const f of faces) {
      if (!f.el.classList.contains("roo-buddy")) continue;
      if (f.mood !== "happy") { if (f.act === "nap" || f.act === "yawn") f.stop(); continue; }
      if (idle > 60000 && f.act !== "nap") f.play("nap", Infinity, pick(LINES.nap));
      else if (idle > 30000 && idle < 33000 && !f.act) f.play("yawn", 2600, pick(LINES.yawn));
      else if (!f.act && idle > 3000 && Math.random() < 0.09) {
        const [act, ms, lines] = pick(FIDGETS);
        f.play(act, ms, lines ? pick(lines) : undefined);
      }
    }
    setTimeout(lifeLoop, 1000);
  }
  if (typeof document !== "undefined") {
    const seen = (ev) => {
      lastInput = Date.now();
      if (ev && ev.clientX !== undefined) pointer = { x: ev.clientX, y: ev.clientY };
      for (const f of faces) if (f.act === "nap") f.play("wake", 1600, pick(LINES.wake));
      look();
    };
    document.addEventListener("pointermove", seen, { passive: true });
    document.addEventListener("pointerdown", seen, { passive: true });
    document.addEventListener("keydown", () => { lastInput = Date.now(); });
    window.addEventListener("scroll", look, { passive: true });
    // the pointer leaves the page: Roo looks for you, and is happy when you come back
    document.documentElement.addEventListener("pointerleave", () => {
      pointer = null; look();
      for (const f of faces) if (f.el.classList.contains("roo-buddy") && !f.act && !f.serious()) f.play("lookaround", 2400, pick(LINES.away));
    });
    document.documentElement.addEventListener("pointerenter", () => {
      for (const f of faces) if (f.el.classList.contains("roo-buddy") && (!f.act || f.act === "lookaround") && !f.serious()) f.play("boop", 1300, pick(LINES.hello));
    });
    if (!reduce) { setTimeout(blinkLoop, 1500); setTimeout(lifeLoop, 2000); }
  }

  // the logo: wink when clicked, eyes go wide when you hover
  function logoTouch(f) {
    f.el.addEventListener("pointerenter", () => { if (!f.serious() && !f.act) f.play("wide", 900); });
    f.el.addEventListener("click", () => { if (!f.serious()) f.play("wink", 700); });
  }

  // which moods blink (the look itself is in roo.css)
  const LOOKS = {
    happy: { blink: true }, proud: {}, driving: { blink: true }, worried: { blink: true },
    sad: { blink: true }, shocked: {}, sleepy: {}, charging: {}, asleep: {}, thinking: { blink: true },
    curious: { blink: true },
  };

  // ---------- the moods: what each one means, when it shows, and what Roo says ----------
  // Lines follow the voice rules: short and plain, real numbers, and no jokes when something is wrong.
  const MOODS = {
    asleep:   { name: "Asleep",   when: "The car is offline.",
                say: () => pick(["I'm offline. Wake me up from the Setup page.", "Zzz… I'm not connected."]) },
    thinking: { name: "Thinking", when: "The website is waiting for the AI's first decision.",
                say: () => pick(["Thinking…", "Let me check the stations…"]) },
    shocked:  { name: "Shocked",  when: "Something blocks the track, or the car reports a problem.",
                say: (c) => c.where ? `Something is in my way near ${c.where}. The AI is finding another way.` : "Something is in my way. The AI is finding another way." },
    sad:      { name: "Sad",      when: "A production line has stopped: a station ran out.",
                say: (c) => `${c.station} ran out of ${c.material}. ${c.coming ? "I'm bringing it now." : "I'm sorry, I'll get there as fast as I can."}` },
    proud:    { name: "Proud",    when: "A delivery was just made (for 4 seconds).",
                say: (c) => pick([`Delivered ${c.material} to ${c.station}!`, `${c.station} is good to go.`, `Hop, drop, done! That's ${c.count} today.`]) },
    sleepy:   { name: "Sleepy",   when: "The battery is under 20% and the car isn't charging yet.",
                say: (c) => `Battery ${c.battery}%. I need a charge soon.` },
    charging: { name: "Charging", when: "The car is charging at the dock.",
                say: (c) => `Charging… ${c.battery}%.` },
    worried:  { name: "Worried",  when: "A station runs out in less than a minute after the car could get there.",
                say: (c) => `Hurry: ${c.station} runs out of ${c.material} in ${c.left}.` },
    driving:  { name: "Driving",  when: "The car is on a task.",
                say: (c) => c.carrying ? `Carrying ${c.material} to ${c.station}.` : c.charge ? "Going to the dock to charge." : `Going to pick up ${c.material} for ${c.station}.` },
    happy:    { name: "Happy",    when: "Everything is stocked and nothing is wrong.",
                say: () => pick(["All stocked up. I'm taking a breather.", "Every line is running. Nice!", "Nothing to carry right now."]) },
    curious:  { name: "Curious",  when: "On the Try it page, right after you change an input.",
                say: () => pick(["Ooh, what did you change?", "Let's see what the AI does with that."]) },
  };
  // first match wins, top to bottom
  const ORDER = ["asleep", "thinking", "shocked", "sad", "proud", "sleepy", "charging", "worried", "driving", "happy"];

  function fmt(s) {
    if (s === null || s === undefined || !isFinite(s)) return "–";
    s = Math.max(0, Math.round(s));
    return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`;
  }

  // memory keeps what the rules need between snapshots: the delivery count, when Roo became proud,
  // and the mood shown (a mood stays at least 2.5 s so Roo doesn't flicker)
  function read(d, memory = {}) {
    const now = Date.now();
    const state = d && d.state, dec = d && d.decision;
    let mood = "happy", ctx = {};
    if (!state) mood = "thinking";
    else {
      const car = state.car, t = car.task;
      const names = {};
      for (const [sid, st] of Object.entries(state.stations)) names[sid] = st.name || sid;
      const deliveries = state.stats ? state.stats.deliveries : 0;
      if (memory.deliveries !== undefined && deliveries > memory.deliveries) {
        const last = (state.events || []).find((e) => e.type === "delivered");
        memory.proudUntil = now + 4000;
        memory.proudCtx = { count: deliveries, station: memory.lastStation || "The station", material: memory.lastMaterial || "the box" };
        if (last && last.text) memory.proudCtx.text = last.text;
      }
      memory.deliveries = deliveries;
      if (t && t.kind === "delivery") { memory.lastStation = names[t.station] || t.station; memory.lastMaterial = t.material; }

      const stopped = [];
      for (const [sid, st] of Object.entries(state.stations))
        for (const [m, v] of Object.entries(st.materials)) if (v.stock <= 0) stopped.push({ sid, m });
      const q = dec && dec.queue ? dec.queue : [];
      const urgent = q.filter((r) => r.slack_s !== undefined && r.slack_s < 60).sort((a, b) => a.stockout_s - b.stockout_s)[0];
      const battery = Math.round(car.battery);

      if (!car.online) mood = "asleep";
      else if (car.mode === "BLOCKED" || car.mode === "ERROR" || (t && t.blocked)) {
        mood = "shocked"; ctx.where = t && t.edge ? t.edge[0] : car.node;
      } else if (stopped.length) {
        const s = stopped[0];
        mood = "sad";
        ctx = { station: names[s.sid], material: s.m, coming: !!(t && t.kind === "delivery" && t.station === s.sid && t.material === s.m) };
      } else if (memory.proudUntil > now) { mood = "proud"; ctx = memory.proudCtx; }
      else if (car.mode === "CHARGING") { mood = "charging"; ctx.battery = battery; }
      else if (battery < 20) { mood = "sleepy"; ctx.battery = battery; }
      else if (urgent) { mood = "worried"; ctx = { station: urgent.station_name || urgent.station, material: urgent.material, left: fmt(urgent.stockout_s) }; }
      else if (t) {
        mood = "driving";
        ctx = { charge: t.kind === "charge", carrying: t.kind === "delivery" && t.leg === 1, material: t.material, station: names[t.station] || t.station };
      }
      if (memory.curiousUntil > now && !["asleep", "shocked", "sad"].includes(mood)) mood = "curious";
    }
    // hold a mood for 2.5 s unless the new one is more important
    if (memory.mood && memory.mood !== mood && now - memory.since < 2500 && ORDER.indexOf(mood) > ORDER.indexOf(memory.mood)
        && memory.mood !== "proud" && memory.mood !== "curious") {
      return { mood: memory.mood, say: memory.say };
    }
    // a new line when the mood or what it is about changes (and a fresh one every 12 s)
    const key = mood + JSON.stringify(ctx || {});
    if (mood !== memory.mood) memory.since = now;
    if (key !== memory.key || !memory.say || now - memory.sayAt > 12000) {
      memory.say = MOODS[mood].say(ctx || {});
      memory.key = key; memory.sayAt = now;
    }
    memory.mood = mood;
    return { mood, say: memory.say };
  }

  root.Roo = { logo, buddy, read, MOODS, ORDER, poke: (memory) => { memory.curiousUntil = Date.now() + 3500; } };
})(typeof window !== "undefined" ? window : globalThis);
