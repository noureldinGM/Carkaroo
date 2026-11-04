// Carkaroo design tokens for the 3D simulation (and any other JavaScript).
// Same values as design/tokens.css. Works as a plain <script> (window.CARKAROO)
// or as an ES module copy: `export default CARKAROO`.
//
// Three.js example:
//   const mat = new THREE.MeshStandardMaterial(CARKAROO.three.chassis);
//   scene.background = new THREE.Color(CARKAROO.color.paper);
(function (root) {
  "use strict";

  const color = {
    // surfaces and text
    paper: "#f5f3ec", card: "#ffffff", ink: "#1c1d1a", ink2: "#545750", muted: "#6b6e66",
    line: "#e4e2d8", line2: "#cfccbf",
    // the robot kit
    chassis: "#1a7f45", chassisBright: "#1f8a4c", chassisDark: "#145c33", chassisSoft: "#e1f2e6",
    motor: "#f6c21c", motorDark: "#8a6a00", motorInk: "#2a2305",
    tire: "#23231f", sonar: "#2f6fd0", eye: "#e9ecef", pupil: "#1c1d1a",
    wireRed: "#e2483d", wireOrange: "#f08a24",
    // status
    good: "#1f7a45", warn: "#946006", crit: "#b7372a",
    stop: "#d9483b", charge: "#7fd39f", offline: "#9a9c94", stockLow: "#f0a417",
    // materials (always show the letter too)
    materialA: "#3566a8", materialB: "#1d7a6c", materialC: "#b35a1f", materialX: "#6b665c",
    // the track mat
    matBg: "#fbfaf6", matEdge: "#e2dfd3", matTape: "#22221f", matText: "#1c1d1a", matSub: "#6f7268",
  };

  const material = { A: color.materialA, B: color.materialB, C: color.materialC };

  // MeshStandardMaterial settings: matte toy plastic, nothing shiny or glassy.
  const plastic = (c, extra) => Object.assign({ color: c, roughness: 0.55, metalness: 0 }, extra);
  const three = {
    chassis: plastic(color.chassisBright),
    motor: plastic(color.motor),
    tire: plastic(color.tire, { roughness: 0.9 }),
    sonar: plastic(color.sonar),
    eye: plastic(color.eye, { roughness: 0.3, metalness: 0.4 }),     // the ultrasonic "eyes" are metal cans
    wire: plastic(color.wireRed, { roughness: 0.4 }),
    fork: plastic("#c9ccc4", { roughness: 0.35, metalness: 0.6 }),   // the servo fork
    floor: plastic(color.matBg, { roughness: 0.95 }),                // the white track mat
    tape: plastic(color.matTape, { roughness: 0.8 }),                // black line tape
    station: plastic(color.card, { roughness: 0.7 }),
    rack: plastic("#d8d4c6", { roughness: 0.7 }),
    boxA: plastic(color.materialA), boxB: plastic(color.materialB), boxC: plastic(color.materialC),
    route: { color: color.motor, transparent: true, opacity: 0.85 },  // MeshBasicMaterial: a flat highlighter band
    routeLater: { color: color.motor, transparent: true, opacity: 0.45 },
    blocked: { color: color.stop },
    charge: { color: color.charge, transparent: true, opacity: 0.85 },
    // car body color by state (swap chassis.color)
    state: { ok: color.chassisBright, blocked: color.stop, charging: color.charge, offline: color.offline },
  };

  // Scale and scene. 1 world unit = 1 metre; the track editor's grid is 10 cm.
  const scene = {
    unit: "m", grid: 0.1,
    background: color.paper,
    fog: { color: color.paper, near: 8, far: 30 },
    light: {
      hemi: { sky: "#ffffff", ground: "#d8d4c6", intensity: 0.9 },
      sun: { color: "#fff6e0", intensity: 1.6, position: [4, 8, 3], castShadow: true },
    },
    camera: { fov: 40, start: [3.5, 4.5, 5.5], minDistance: 1.2, maxDistance: 18, maxPolarAngle: 1.35 },
    tapeWidth: 0.019, tapeHeight: 0.002,    // 19 mm electrical tape
    routeWidth: 0.06, routeLift: 0.003,      // the yellow band sits just above the tape
  };

  // The real car, in metres (measure yours and update; keep proportions if unsure).
  const car = {
    length: 0.26, width: 0.15, height: 0.07, cornerRadius: 0.02,
    wheelRadius: 0.033, wheelWidth: 0.026, sonarSize: [0.045, 0.02, 0.02],
    // timing comes from config/materials.yaml (car: speed_cm_s, turn_s, uturn_s); read it from
    // /api/snapshot when you can, these are only the defaults
    speed: 0.15,            // m/s average line-following speed
    turnTime: 2.0,          // s extra for a left or right at a junction
    uturnTime: 4.0,         // s to turn around
    hop: { height: 0.015, duration: 0.45 },  // the little "roo hop" when a delivery is done
  };

  const motion = { ease: "cubic-bezier(.3,.7,.4,1)", fast: 0.15, move: 0.3 };
  const font = {
    round: '"Fredoka", "Trebuchet MS", "Segoe UI", system-ui, sans-serif',
    sans: '"IBM Plex Sans", "Segoe UI", system-ui, sans-serif',
    mono: '"IBM Plex Mono", Consolas, "Courier New", monospace',
  };

  const CARKAROO = { name: "Carkaroo", car: "Roo", color, material, three, scene, carSize: car, motion, font };
  root.CARKAROO = CARKAROO;
  if (typeof module === "object" && module.exports) module.exports = CARKAROO;
})(typeof window !== "undefined" ? window : globalThis);
