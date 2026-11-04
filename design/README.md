# Carkaroo design system

**Carkaroo** = *car* + *kangaroo*. A kangaroo carries what matters in its pouch; our car carries boxes on its fork to the stations that are about to run out. The car itself is called **Roo**.

One look for everything: the live website, the coming 3D simulation, slides, posters and the exhibition stand. It is built from the real robot kit: a green chassis, yellow TT motors, black tires, the ultrasonic sensor's two "eyes", jumper wires, and a white track mat with black tape.

Open the living style guide at **http://localhost:8050/design/** while the app runs, or open `design/index.html` straight from the folder.

| File | What it is | Used by |
| --- | --- | --- |
| `tokens.css` | every color, font, size, radius and shadow as CSS variables, light and dark | website, style guide |
| `components.css` | buttons, chips, badges, cards, bars, the ribbon | website, style guide |
| `tokens.json` | the same tokens as JSON | slides, charts, other tools |
| `carkaroo.js` | the same tokens for JavaScript, plus Three.js materials, scale, lights and camera | 3D simulation |
| `logo/` | the mark, the logo (light and dark), Roo from above, the ribbon | everything |
| `index.html` | the style guide page | you, teammates |

Change a value in `tokens.css` first, then copy it to `tokens.json` and `carkaroo.js`.

---

## 1. Voice

Carkaroo talks like a helpful teammate on the factory floor: short, plain and specific.

- **Say what happens, with real numbers.** *"Bring B to Packaging. It runs out in 2 min 10 s; the trip takes 48 s."* Not *"Optimal dispatch candidate identified."*
- **Roo is the car's name.** *"Roo is carrying B to Packaging."* Use "the car" in technical text (protocol, firmware, setup).
- **One idea per sentence**, verbs first on buttons: *Apply*, *Refilled*, *Save and use it*.
- **Explain the AI in human terms.** *"It beats about 3.8 of the 4 other requests"*, not *"pairwise score 0.95"*.
- **Fun is a seasoning.** A small hop, a friendly empty state (*"All stocked up, so Roo takes a break"*). Never jokes in errors or safety messages.
- Symbols allowed in text: ✓ (best), ≈ (almost), ⚡ (battery), ★ (lowest cost). No emoji decoration.

Taglines (pick one per piece, don't stack them):
- *Carries what the line needs, before it runs out.*
- *The AI delivery car that never lets a line stop.*
- *Hop. Drop. Keep the line running.*

## 2. Logo

| File | Use |
| --- | --- |
| `logo/carkaroo-logo.svg` | the main logo on light backgrounds (paper, white slides) |
| `logo/carkaroo-logo-dark.svg` | on dark backgrounds; it carries its own dark plate |
| `logo/carkaroo-mark.svg` | Roo alone: favicon, app icon, slide corners, stickers |
| `logo/roo-top.svg` | Roo seen from above, facing right: maps, diagrams, the 3D model reference |
| `logo/ribbon.svg` | the jumper-wire ribbon, stretched across the top of slides and posters |

- The wordmark is **Carka** in ink + **roo** in chassis green, set in Fredoka SemiBold.
- Clear space around the logo: the height of one wheel (the mark's tire) on every side.
- Smallest size: mark 24 px wide on screen, 10 mm in print.
- Don't recolor Roo, stretch it, add outlines or shadows, or put it on photos without a paper-colored plate.
- The logo files use Fredoka as text. Install Fredoka (free, Google Fonts) on any computer that edits slides, or export the slide to PDF/PNG before sharing.

## 3. Color

Colors come from the kit. Each one has a job; don't use a color for a job it doesn't have.

**Brand**

| Token | Light | Job |
| --- | --- | --- |
| `chassis` | `#1a7f45` | primary: buttons, active tab, the AI score card, "good" |
| `chassis-bright` | `#1f8a4c` | Roo's body in drawings, the logo, 3D (never behind small text) |
| `motor` | `#f6c21c` | the route, "now" labels, highlights, focus ring. Text on it is `motor-ink`; **never yellow text** |
| `tire` / `mat-tape` | `#23231f` / `#22221f` | tires, black track tape |
| `sonar`, `wire-red`, `wire-orange` | `#2f6fd0`, `#e2483d`, `#f08a24` | only in the ribbon and in drawings of the car |

**Surfaces and text:** `paper #f5f3ec` (page and slide background), `card #ffffff`, `ink #1c1d1a`, `ink-2 #545750`, `muted #6b6e66`, `line #e4e2d8`, `line-2 #cfccbf`.

**Status:** `good #1f7a45 on #e1f2e6`, `warn #946006 on #fbefcf`, `crit #b7372a on #f8e0db`. On the map: `stop #d9483b` (obstacle, blocked), `charge #7fd39f`, `offline #9a9c94`, `stock-low #f0a417`.

**Materials** (same in every theme, always with the white letter on the chip, so color is never the only clue):

| | Token | Color |
| --- | --- | --- |
| **A** steel | `material-a` | `#3566a8` |
| **B** plastic | `material-b` | `#1d7a6c` |
| **C** copper | `material-c` | `#b35a1f` |

**The ribbon** is always five wires in this order, top to bottom: red, orange, yellow, green, blue.

**Dark mode** swaps surfaces and text (see `tokens.css`). The track mat stays a light board, a little dimmer, because the real mat is white.

All text pairs meet 4.5:1 contrast in both themes (white on `chassis` 5.0, on `material-c` 4.8; `motor-ink` on `motor` 9.4).

## 4. Type

| Family | Font | For |
| --- | --- | --- |
| round | **Fredoka** 400/500/600 | headings, buttons, tabs, big numbers, the logo |
| sans | **IBM Plex Sans** 400/500/600 | body text, explanations |
| mono | **IBM Plex Mono** 400/500 | times, IDs, keys, code |

All three are free on Google Fonts. Offline, the website falls back to system fonts.

| Style | Size / line height | Example |
| --- | --- | --- |
| display | Fredoka 600, 42 / 1.12 | *Bring B to Packaging* |
| h1 | Fredoka 600, 32 / 1.15 | page titles |
| h2 | Fredoka 600, 21 / 1.2 | section titles |
| h3 | Fredoka 600, 18 / 1.2 | card titles |
| number | Fredoka 600, 28 / 1.1 | KPI values |
| body | Plex Sans 400, 15 / 1.55 | text |
| small | Plex Sans 400, 13 / 1.45 | captions, hints |
| code | Plex Mono 400, 13 / 1.5 | `S2-B`, `12:04` |

Sentence case everywhere. Never all caps.

## 5. Shape, space and depth

- **Spacing** on a 4 px grid: `space-1` 4 … `space-8` 36. Cards pad 16–20, page sides 24, columns gap 28.
- **Radius:** 6 (code), 10 (buttons, inputs), 14 (tiles), 18 (cards, the mat), pill (tabs, badges).
- **Depth is a toy block, not glass.** Pressable things get a darker bottom edge (`shadow-press`) that disappears while pressed. Cards get a 2 px "sitting on the bench" edge (`shadow-card`). No blurry floating shadows, no gradients except the ribbon.
- **Dashed lines** (2 px, `line`) separate "about Roo" footers, like the dashed lanes on a mat.

## 6. Components

All in `components.css`, shown live in the style guide:

- **Button** (`button`, `.button`): chassis green with the press edge. `.ghost` for secondary, `.go` (yellow) for the one "start" action on a screen, `.small` in tight rows.
- **Material chip** (`.mat.A`, `.mat.B`, `.mat.C`, `.big`): the color square with its letter. The only way to show a material.
- **Badge** (`.badge.good|warn|crit`): the result of a decision. **Tag** (`.tag.way|out|sim|real`): small state on a card. **Mode pill** (`.mode-pill.sim|real`): yellow = simulation, green = real.
- **Eyebrow** (`.eyebrow`): yellow pill above the main sentence, *"The AI's choice"*.
- **Card** (`.card`, `.ctl`), **KPI tile** (`.kpi`, `.bad`): one number, one label, green edge (red when bad).
- **Stock bar** (`.sbar` with `.fill` and `.safety`): fill = what's left, black tick = safety level.
- **Alert** (`.alert`, `.crit`), **Toast** (`.toast.show`), **Connection dot** (`.link.on|off`).
- **Track mat** (`.floor-card`): the dotted white board every map sits on.

## 7. Drawing the factory (2D)

- The floor is the **track mat**: off-white board, faint dot grid, black tape 5 units wide with round caps.
- The **route** is a yellow highlighter band (16 wide, 85% opacity) *under* the tape; the part after pickup is dotted.
- **Blocked** lines are red dashes; obstacles are red circles with a white "!".
- **Stations** are white boxes; a yellow border = waiting for a delivery, red = stopped. The dot is stock: green OK, yellow low, red empty.
- **Roo** is drawn from above (`logo/roo-top.svg`): green body, yellow motors, black tires, two sonar eyes at the front, a red wire. Blocked → red body, charging → mint, offline → grey.

## 8. The 3D simulation

Use `carkaroo.js` (`window.CARKAROO`). It has every color, ready Three.js `MeshStandardMaterial` settings, and the scene setup.

- **Scale:** 1 unit = 1 metre. The track editor's grid is 10 cm, so tracks from `config/tracks/` map straight in.
- **World:** the floor is the white mat (`three.floor`) with black tape strips (`scene.tapeWidth` 19 mm, raised 2 mm). The background and fog are `paper`, so the factory sits on the workbench, not in space.
- **Materials are matte toy plastic** (roughness about 0.55, no metalness). Only the sonar cans and the fork are a little metallic. No glow, no neon, no glass.
- **Light:** one warm sun with soft shadows from the upper right, plus a hemisphere light. Same light all the time; no day/night.
- **Roo:** a rounded green box on four black wheels with yellow hubs/motors, a blue sonar block with two eyes at the front, a grey fork at the back, a red wire loop on top. When carrying, the box on the fork has its material color and its letter on every side.
- **Route:** a flat yellow band (`three.route`) 3 mm above the tape, dotted after pickup. Blocked segment: red dashes. Charging: mint.
- **Stations and racks:** white blocks with a Fredoka label sprite facing the camera, and the same stock dot as the 2D map. Racks hold boxes in A/B/C colors.
- **Motion:** the car follows the real timings from `config/materials.yaml` (15 cm/s, 2 s per turn, 4 s U-turn) times the sim speed. When a delivery is done Roo does one small hop (`carSize.hop`). Respect "reduce motion": no hop, no camera fly-ins.
- **Camera:** starts at a 3/4 view from above (`scene.camera`), orbit with limits so the floor is never seen from below. A "Follow Roo" toggle is the only camera mode beyond orbit.
- **Overlay UI** (labels, panels) is plain HTML with `tokens.css` and `components.css`, so it matches the website exactly.

## 9. Presentations, posters and reports

**Slides (16:9)**

- Background `paper #f5f3ec` (or `card #ffffff` for data-heavy slides). Text `ink`. Dark slides only for a video or the demo: background `#141613`, text `#ecefe6`, dark logo.
- The **ribbon** runs across the very top of every slide (10 px at 1920 wide). The **mark** sits in the bottom-right corner, 48 px.
- Titles: Fredoka SemiBold 44–54 pt, sentence case, saying the point (*"The AI picks the best delivery 91% of the time"*). Body: IBM Plex Sans 20–24 pt. Numbers: Fredoka, big. At most 3 bullets.
- One highlight color per slide: `motor` yellow behind a key phrase or as a pill. Green for "good" results, red only for problems.
- Show materials with the colored letter squares, never with color alone.
- Layouts to reuse: **Title** (logo big, tagline, names, ribbon), **One big number** (number in Fredoka 120 pt + one sentence), **Before / after** (two cards side by side), **Map** (the track mat full width with a yellow route), **How it works** (3–4 steps in pill boxes joined by black tape lines), **Thank you** (Roo + QR code).

**Charts** (reports, slides): background `paper` or white, gridlines `line`, labels `ink-2`. Our AI is always **chassis green**; baselines are grey (`#b9b8b2`), the exact optimizer is `ink`. Materials use their own colors. Python charts use `scripts/plot_style.py`.

**Posters and print:** same rules; use `paper` as the background so the white track mat stands out. Keep the ribbon at the top edge. Minimum body text 24 pt at A1.

## 10. Do and don't

| Do | Don't |
| --- | --- |
| Use the kit colors for their jobs | Blue–purple "AI" gradients, glowing brains, circuit backgrounds |
| Put the letter on every material color | Color alone to tell A, B and C apart |
| Say the decision in one plain sentence | Jargon: "inference", "optimal policy", "candidate" |
| Matte, toy-like shapes with a press edge | Glass, neon, heavy drop shadows |
| One fun touch per screen (a hop, a friendly empty state) | Jokes in errors, emoji decoration |
