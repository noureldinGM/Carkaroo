// Carkaroo design tokens for the 3D simulation, "Night Race" theme.
// Same values as design/tokens.css. Works as a plain <script> (window.CARKAROO)
// or with require(). Three.js example:
//   const K = window.CARKAROO;
//   scene.background = new THREE.Color(K.scene.background);
//   const body = new THREE.MeshStandardMaterial(K.three.body);
(function (root) {
  "use strict";

  const color = {
    // fog and asphalt
    fog: "#eceeee", card: "#ffffff", asphalt: "#121314", night: "#111214", graphite: "#2a2d31",
    ink: "#121314", ink2: "#4a4e53", muted: "#63686e", line: "#d9dcde",
    chrome: "#8b9096", chromeLight: "#c9cdd1",
    // the one accent
    signal: "#f6c21c",
    // status
    good: "#1d6b3f", warn: "#946006", crit: "#b7372a",
    stop: "#d9483b", charge: "#7fd39f", offline: "#9a9c94", stockOk: "#3f9a62", stockLow: "#f0a417",
    // materials (always show the letter too)
    materialA: "#3566a8", materialB: "#1d7a6c", materialC: "#b35a1f", materialX: "#6b665c",
    // the lit track
    trackBoard: "#f4f5f5", tape: "#121314", trackSub: "#5d6268",
  };
  const material = { A: color.materialA, B: color.materialB, C: color.materialC };

  // MeshStandardMaterial settings. Satin plastic and brushed metal, never glossy or glowing,
  // except the yellow, which may glow softly at night (emissive) like a lit kerb.
  const satin = (c, extra) => Object.assign({ color: c, roughness: 0.55, metalness: 0 }, extra);
  const three = {
    body: satin(color.graphite, { roughness: 0.45, metalness: 0.2 }),     // Roo's body
    stripe: satin(color.signal, { emissive: color.signal, emissiveIntensity: 0.15 }),
    motor: satin(color.signal),
    tire: satin(color.asphalt, { roughness: 0.9 }),
    hub: satin(color.signal),
    sonar: satin(color.chrome, { roughness: 0.3, metalness: 0.8 }),       // chrome sensor block
    eye: satin("#f4f5f5", { roughness: 0.2, metalness: 0.5 }),
    fork: satin(color.chromeLight, { roughness: 0.3, metalness: 0.8 }),
    track: satin(color.trackBoard, { roughness: 0.95 }),                  // the lit white board
    tape: satin(color.tape, { roughness: 0.8 }),
    ground: satin(color.night, { roughness: 1 }),                         // asphalt around the board
    station: satin(color.card, { roughness: 0.7 }),
    stationEdge: satin(color.asphalt),                                    // the thick outline, as a base plate
    rack: satin(color.chrome, { roughness: 0.4, metalness: 0.7 }),
    boxA: satin(color.materialA), boxB: satin(color.materialB), boxC: satin(color.materialC),
    flag: { checker: [color.asphalt, "#ffffff"], square: 0.03 },          // checkered flags at the dock / finish
    route: { color: color.signal, transparent: true, opacity: 0.9 },      // MeshBasicMaterial: flat highlighter band
    routeLater: { color: color.signal, transparent: true, opacity: 0.45 },
    blocked: { color: color.stop },
    charge: { color: color.charge, transparent: true, opacity: 0.85 },
    state: { ok: color.graphite, blocked: color.stop, charging: color.charge, offline: color.offline },
  };

  // Scene. 1 unit = 1 metre; the track editor's grid is 10 cm.
  // Two moods share one scene: "fog" (day, like the poster) and "night" (dark, like the website's dark mode).
  const scene = {
    unit: "m", grid: 0.1,
    moods: {
      fog:   { background: color.fog,   fog: { color: color.fog, near: 6, far: 22 },
               hemi: { sky: "#ffffff", ground: "#9aa0a6", intensity: 0.9 }, sun: { color: "#ffffff", intensity: 1.4 } },
      night: { background: color.night, fog: { color: color.night, near: 5, far: 18 },
               hemi: { sky: "#3a3f45", ground: "#0b0c0d", intensity: 0.5 }, sun: { color: "#dfe6ee", intensity: 1.1 },
               trackLights: { color: "#ffffff", intensity: 0.8 } },   // overhead floodlights over the board
    },
    sunPosition: [4, 8, 3], castShadow: true,
    camera: { fov: 38, start: [3.2, 4.2, 5.2], minDistance: 1.2, maxDistance: 18, maxPolarAngle: 1.35 },
    tapeWidth: 0.019, tapeHeight: 0.002,     // 19 mm electrical tape
    routeWidth: 0.06, routeLift: 0.003,       // the yellow band just above the tape
    finishLine: { squares: 2, square: 0.03 }, // a checkered strip across the dock entrance
  };

  // The real car, in metres (measure yours and update; keep the proportions if unsure).
  // Timing comes from config/materials.yaml (car: speed_cm_s, turn_s, uturn_s); read it from
  // /api/snapshot when you can, these are only the defaults.
  const carSize = {
    length: 0.26, width: 0.15, height: 0.07, cornerRadius: 0.02,
    wheelRadius: 0.033, wheelWidth: 0.026, sonarSize: [0.045, 0.02, 0.02], stripeWidth: 0.018,
    speed: 0.15, turnTime: 2.0, uturnTime: 4.0,
    hop: { height: 0.015, duration: 0.45 },   // the small hop after each delivery
  };

  const motion = { ease: "cubic-bezier(.3,.7,.4,1)", fast: 0.15, move: 0.3 };
  const font = {
    display: '"Barlow Condensed", "Arial Narrow", "Segoe UI", system-ui, sans-serif',   // italic 700 for labels
    sans: '"IBM Plex Sans", "Segoe UI", system-ui, sans-serif',
    mono: '"IBM Plex Mono", Consolas, "Courier New", monospace',
  };

  const CARKAROO = { name: "Carkaroo", car: "Roo", theme: "Night Race", color, material, three, scene, carSize, motion, font };
  root.CARKAROO = CARKAROO;
  if (typeof module === "object" && module.exports) module.exports = CARKAROO;
})(typeof window !== "undefined" ? window : globalThis);
