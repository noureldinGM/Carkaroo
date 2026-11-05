# Carkaroo design system: "Night Race"

**Carkaroo** = *car* + *kangaroo*. A kangaroo carries what matters in its pouch; our car carries boxes on its fork to the stations that are about to run out. The car itself is called **Roo**.

**Night Race** is one look for everything: the poster, the portfolio, the live website, slides, and the coming 3D simulation. It blends two sides:

- **From our poster and portfolio:** monochrome racing. Asphalt black, white, chrome greys, fog, checkered flags, slanted banner headings, bold italic type, big rounded panels with thick black outlines, and "Relevance to our project" call-outs.
- **From the robot kit:** one color only, the **yellow of Roo's TT motors**. It's the signal: the route on the map, the kerb under panels, the highlight on a slide, the stripe on Roo.

Everything else was left out on purpose: no rainbow, no warm paper, no green brand color.

Open the living style guide at **http://localhost:8050/design/** while the app runs, or open `design/index.html` straight from the folder.

| File | What it is | Used by |
| --- | --- | --- |
| `tokens.css` | every color, font, size, radius and motif as CSS variables, fog (light) and night (dark) | website, style guide |
| `components.css` | buttons, banners, the finish strip, panels with a kerb, KPI tiles, chips, badges, call-outs | website, style guide |
| `tokens.json` | the same tokens as JSON (hex values for Canva and slides) | Canva, slides, charts |
| `carkaroo.js` | the same tokens for JavaScript: Three.js materials, fog and night moods, scale, car timings | 3D simulation |
| `logo/` | logo (light and dark), Roo side view, Roo from above, the finish strip | everything |
| `roo.js`, `roo.css` | the live logo and Roo the character: moods from the live data, touch and idle animations | website, style guide |
| `roo-moods.html` | every mood of Roo, the rules, try them live | you, teammates |
| `index.html` | the style guide page | you, teammates |

Change a value in `tokens.css` first, then copy it to `tokens.json` and `carkaroo.js`. Python charts use `scripts/plot_style.py`.

---

## 1. Voice

Carkaroo talks like a race engineer on the radio: short, plain, specific.

- **Say what happens, with real numbers.** *"Bring B to Packaging. It runs out in 2 min 10 s; the trip takes 48 s."*
- **Roo is the car's name** on screens and slides (*"Roo is carrying B to S3"*). Use "the car" or "the AGV" in technical and academic text (portfolio, protocol, firmware).
- **Explain the AI in human terms:** *"It beats about 3.8 of the 4 other requests"*, not *"pairwise score 0.95"*.
- **Fun is seasoning:** one hop, one checkered flag, a friendly empty state. Never in errors or safety messages.
- Symbols allowed in text: ✓ (best), ≈ (almost), ⚡ (battery), ★ (lowest cost).

Taglines (one per piece):
- *Carries what the line needs, before it runs out.*
- *The AI delivery car that never lets a line stop.*
- *Hop. Drop. Keep the line running.*

## 2. Logo

| File | Use |
| --- | --- |
| `logo/carkaroo-logo.svg` | main logo on fog, white or the poster's grey photo |
| `logo/carkaroo-logo-dark.svg` | on dark backgrounds (it carries its own asphalt plate) |
| `logo/carkaroo-mark.svg` | Roo alone: favicon, slide corner, stickers, the poster corner |
| `logo/roo-top.svg` | Roo from above, facing right: maps, diagrams, 3D reference |
| `logo/finish-strip.svg` | the checkered strip with a yellow line, for the top edge of slides and posters |

- The wordmark is **Carkar** in Barlow Condensed Bold Italic, then **Roo's two eyes as the "oo"**, with the yellow antenna over the eyes and a yellow line under the word (the poster's logo). On the website it is live (`roo.js`): the eyes blink, look at the pointer and show Roo's mood.
- Roo: graphite body, yellow racing stripe, yellow hubs and antenna, chrome sensor block with two white eyes.
- Clear space: one eye all around the logo, one wheel around Roo. Smallest: mark 24 px on screen, 10 mm in print.
- Don't recolor Roo, stretch it, outline it or add shadows.
- Logo files use Barlow Condensed as live text. Install it (free, Google Fonts) on any computer that edits slides, or export to PDF/PNG.

### Roo, the main character

Roo is alive on the website (`roo.js` + `roo.css`, preview at **/design/roo-moods.html**). The live data picks one mood, the logo's eyes and Roo on the Now page show it, and Roo says one short line:

| Mood | When |
| --- | --- |
| Asleep | the car is offline |
| Thinking | waiting for the AI |
| Shocked | the track is blocked or the car reports an error |
| Sad | a station ran out and its line stopped |
| Proud | a delivery was just made (4 s, hop and confetti) |
| Sleepy | battery under 20 % |
| Charging | at the dock |
| Worried | a station runs out less than a minute after Roo could get there |
| Driving | on a task |
| Happy | everything is stocked |
| Curious | you just changed something in Try it (on the Now page) |

You can play with Roo: **tap** (boop), **tap 5 times** (dizzy), **hold** (revs the engine, then zooms off and back), **drag** (it rides along and rolls back), **rub it with the mouse** (it giggles). The logo **winks** when clicked. Left alone, Roo looks around, hums, stretches, yawns after 30 s and naps after a minute; it looks for you when the pointer leaves the page. A **Refilled** press gets hearts. In the serious moods (offline, blocked, a line stopped) Roo doesn't play: it answers plainly. Moods only move the eyes, the antenna and small effects; the car is never redrawn. "Reduce motion" turns the animations off.

## 3. Color

Black, white and chrome do almost all the work. Yellow is the only accent. Status colors are small and appear only when they mean something.

**The race**

| Token | Fog (light) | Night (dark) | Job |
| --- | --- | --- | --- |
| `signal` | `#f6c21c` | `#f6c21c` | the one accent: route, kerbs, highlights, focus, Roo's stripe. Text on it is `signal-ink`. **Never yellow text on fog or white.** |
| `primary` | `#121314` | `#eef0f0` | buttons, active tab, slanted banners |
| `ink` / `outline` | `#121314` | `#eef0f0` / `#4a4e53` | text and the thick panel outline |
| `chrome` | `#8b9096` | `#8b9096` | metal: banner caps, sensors, edges on dark |
| `roo` | `#2a2d31` | `#4a4e53` | Roo's body |

**Fog and asphalt:** `paper #eceeee` (night `#111214`), `card #ffffff` (`#1b1d20`), `ink-2 #4a4e53`, `muted #63686e`, `line #d9dcde`, `primary-soft #e2e4e6` (call-outs).

**Status:** `good #1d6b3f on #e2efe6`, `warn #946006 on #fbefcf`, `crit #b7372a on #f8e0db`. On the map: `stop #d9483b`, `charge #7fd39f`, `offline #9a9c94`, stock dots `#3f9a62` / `#f0a417` / red.

**Materials** (same in every theme, always with the white letter on the chip): **A** steel `#3566a8`, **B** plastic `#1d7a6c`, **C** copper `#b35a1f`.

All text pairs meet 4.5:1 contrast in both themes (yellow on asphalt is 11:1).

## 4. Type

| Family | Font | For |
| --- | --- | --- |
| display | **Barlow Condensed** 700 *italic* | headings, banners, buttons, tabs, big numbers, the logo |
| sans | **IBM Plex Sans** 400/500/600 | reading text |
| mono | **IBM Plex Mono** 400/500 | times, IDs, keys, code |

| Style | Size / line height | Example |
| --- | --- | --- |
| display | 48 / 1.02 italic | *Bring B to Packaging* |
| h1 | 38 / 1.05 italic | page titles |
| h2 | 24 / 1.1 italic | section titles |
| h3 | 20 / 1.15 italic | panel titles |
| banner | 17 / 1, UPPERCASE, +6% tracking | INTRODUCTION |
| number | 34 / 1 italic | 91.2% |
| body | 15 / 1.55 | text |
| small | 13 / 1.45 | captions |

Headings lean forward (italic) like the poster's titles. Uppercase only on banners and tabs.

## 5. Shape and motifs

- **Panels:** big rounded boxes (radius 20) with a **thick ink outline** (2.5 px on screen; about 17 px on the A0 poster), like the poster's boxes.
- **Kerb:** a solid yellow edge under panels and KPI tiles, 5 px down. It replaces soft shadows, like the painted kerb at the edge of a racetrack.
- **Slanted banner:** asphalt plate skewed −12°, a small checker cap on the left, uppercase italic white text. Used for section titles, like the poster's silver banners.
- **Finish strip:** two rows of checkers over a yellow line. On the top edge of the website, every slide and the poster, and on the bottom edge of the poster.
- **Call-out:** a light grey box with a bold italic title, from the portfolio's "Relevance to our project".
- Spacing on a 4 px grid (`space-1` 4 … `space-8` 36). Radius 4 (tags), 8 (buttons), 14 (tiles), 20 (panels).

## 6. Components

All in `components.css`, shown live in the style guide: **button** (asphalt; `.ghost`; `.go` = yellow for the one "start" action), **banner** / `.section-title`, **eyebrow** (slanted yellow tag), **finish** strip, **checker**, **card / ctl** panel, **KPI** tile with kerb, **callout**, **alert**, **material chip**, **badge**, **tag**, **mode pill** (slanted; yellow = simulation, asphalt = real), **stock bar** (ink fill, yellow safety tick), **track** (`.floor-card`), **toast**.

## 7. Drawing the factory (2D)

- The floor is a **lit white track board** with a faint dot grid, thick ink outline and black tape. It stays light at night, like a floodlit track.
- The **route** is a yellow band under the tape; dotted after the pickup. **Blocked** = red dashes; obstacles = red circles.
- **Stations** are white boxes: yellow border = waiting for delivery, red = stopped. The dot is stock.
- **Roo** from above (`logo/roo-top.svg`): graphite body, yellow stripe and motors, chrome-ringed eyes. Blocked → red body, charging → mint, offline → grey.

## 8. The 3D simulation

Use `carkaroo.js` (`window.CARKAROO`).

- **Scale:** 1 unit = 1 m; the track editor's 10 cm grid maps straight in.
- **Two moods, one scene:** `fog` (light grey, like the poster) and `night` (asphalt black with floodlights over the board, like the website's dark mode). Let the user toggle; default to night for demos.
- **World:** the white track board on an asphalt ground, black tape 19 mm wide, a checkered strip at the dock entrance, checkered flags on the dock.
- **Materials:** satin plastic and brushed chrome (`three.*`). The only thing that may glow is yellow (Roo's stripe, the route), softly.
- **Roo:** a graphite rounded box, yellow stripe along the side, black wheels with yellow hubs, a chrome sensor block with two white eyes at the front, a chrome fork at the back. The carried box shows its material color and letter on every side.
- **Route:** flat yellow band 3 mm above the tape, dotted after pickup; blocked = red dashes; charging = mint.
- **Motion:** real timings from `config/materials.yaml` (15 cm/s, 2 s per turn, 4 s U-turn) times the sim speed. One small hop after each delivery. Respect "reduce motion".
- **Camera:** 3/4 view from above, orbit with limits, plus a "Follow Roo" mode.
- **Overlay UI:** plain HTML with `tokens.css` + `components.css`, so it matches the website.

## 9. Poster, portfolio, slides and reports

**Poster (A0) and portfolio (A4).** Keep the existing layouts. They already *are* Night Race:
- the grey misty photo or fog background, checkered flags, silver slanted banners, black-outlined rounded boxes;
- add the **yellow kerb** under each box (the same rounded box in `#f6c21c`, about 30 px lower on A0 and 6 px on A4, behind the box);
- add the **finish strip** (checkers + yellow line) along the top and bottom edges;
- text stays black; use `signal` only in shapes, never as text color on white;
- the "Relevance to our project" boxes stay light grey (`#e2e4e6`).

**Slides (16:9).**
- Background fog `#eceeee` (or white for data). Dark slides `#111214` for the demo, the video and the end.
- Finish strip on the top edge; the Roo mark bottom-right, 48 px.
- Titles in Barlow Condensed Bold Italic, 48–60 pt, saying the point (*"Roo picks the best delivery 91% of the time"*). Body in IBM Plex Sans 20–24 pt. At most 3 bullets.
- One yellow highlight per slide (a phrase on a yellow block, or the yellow kerb under a key number).
- Layouts in the style guide: **Title**, **One big number** (huge italic number with a yellow offset shadow), **How it works** (pill steps joined by black tape), **Closing** (dark).

**Charts** (`scripts/plot_style.py`): white background so they sit inside white panels. Our AI is always asphalt black (dashed for unseen layouts), other methods are chrome, gold and red (the worst). Yellow is never a thin line on white; use it as a highlight band.

## 10. Do and don't

| Do | Don't |
| --- | --- |
| Black, white and chrome first; yellow as the one accent | Rainbow color, blue–purple "AI" gradients, glowing brains |
| Thick outlines, slanted banners, checkers, yellow kerbs | Glass, neon, soft floating shadows |
| Put the letter on every material color | Color alone to tell A, B and C apart |
| Say the decision in one plain sentence | Jargon: "inference", "optimal policy", "candidate" |
| One fun touch per screen | Jokes in errors or safety messages |
