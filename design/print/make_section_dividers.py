r"""Render the portfolio section dividers: Roo races along the track carrying the topic.

  section-01.jpg ... section-05.jpg   A4 portrait, 1588 x 2246 (2x of 794 x 1123)
  section-06.jpg                      the closing page: Roo waves goodbye with a wheel

Each divider has the workshop floor, a big lap number, and a sign with the topic that Roo carries
on two poles. Below that are the track, with a start line on the left, a finish line on the right
and one checkpoint flag per sub-topic, a "lap" counter and the Carkaroo lockup.

- Roo moves along the track from page to page, starting at the start line on page 1 and reaching
  the finish on page 5. On the closing page Roo is past the finish line.
- The sign is bent by the wind. It leans back on its poles, its far (trailing) edge flutters and
  is a little shorter, and wind streaks trail behind it. The whole sign stays on the page, so no
  edge is cut off.

Run:  .venv\Scripts\python design\print\make_section_dividers.py
Needs Pillow, NumPy and SciPy, the Windows fonts Bahnschrift and Segoe UI, and
workshop-floor-a4.jpg and title-lockup.png from make_print_assets.py.
"""
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import map_coordinates

OUT = Path(__file__).resolve().parent
W, H = 1588, 2246
SS = 2                                    # supersampling, for smooth edges
INK, SIGNAL, WHITE = (18, 19, 20), (246, 194, 28), (255, 255, 255)
ROO, CHROME, SEAM = (42, 45, 49), (139, 144, 150), (93, 98, 104)
PUFF = (233, 235, 237)
FONTS = r"C:\Windows\Fonts"

SECTIONS = [
    ("Introduction", []),
    ("Present and Justify a Problem and Solution Requirements",
     ["Egypt Grand Challenges", "Problem to be Solved", "Research", "Prior Solutions"]),
    ("Generating and Defending a Solution",
     ["Solution and Design Requirements", "Selection of Solution", "Selection of a Prototype"]),
    ("Constructing and Testing a Prototype",
     ["Materials and Methods", "Test Plan", "Data Collection"]),
    ("Evaluation, Reflection, Recommendations",
     ["Analysis and Discussion", "Recommendations", "Learning Transfer", "List of Sources"]),
]

ROO_S = 11                       # Roo's scale on the dividers (svg units -> px at 1x)
ROO_X = [40, 230, 420, 610, 800]  # Roo's left edge on pages 1..5, at 1x: it drives a bit further each lap
TRACK_Y = 1655                   # where the wheels touch the track, at 1x
START_X, FINISH_X = 52, W - 92   # the start and finish lines on the track, at 1x


def bahn(size, style=b"Bold Condensed"):
    f = ImageFont.truetype(f"{FONTS}\\bahnschrift.ttf", int(size * SS))
    f.set_variation_by_name(style)
    return f


def segoe(size, file="seguibli.ttf"):
    return ImageFont.truetype(f"{FONTS}\\{file}", int(size * SS))


def S(v):
    return int(round(v * SS))


def skew(img, deg=-12):
    k = math.tan(math.radians(-deg))
    w, h = img.size
    return img.transform((int(w + k * h), h), Image.AFFINE, (1, -k, k * h, 0, 1, 0), Image.BICUBIC)


def wrap(draw, text, font, width):
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if draw.textlength(t, font=font) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w_
    return lines + [cur]


def draw_roo(d, ox, oy, s, eyes="look", speed=True, dust=True, wave=False):
    """Roo from logo/roo-cartoon.svg (viewBox -14 -4 66 36), drawn at scale s with the top-left at (ox, oy).

    eyes "look" are the usual round eyes; "happy" are closed, smiling ^ ^ eyes.
    wave adds motion arcs around the front wheel, for the goodbye wave.
    """
    X = lambda x: ox + (x + 14) * s
    Y = lambda y: oy + (y + 4) * s
    w = lambda v: max(1, int(round(v * s)))

    def rrect(x, y, ww, hh, r, fill, sw=0):
        h_ = sw * s / 2
        d.rounded_rectangle((X(x) - h_, Y(y) - h_, X(x + ww) + h_, Y(y + hh) + h_), radius=r * s + h_,
                            fill=INK if sw else fill)
        if sw:
            d.rounded_rectangle((X(x) + h_, Y(y) + h_, X(x + ww) - h_, Y(y + hh) - h_), radius=max(0, r * s - h_), fill=fill)

    def circle(cx, cy, r, fill, sw=0):
        R = r * s + (sw * s / 2 if sw else 0)
        d.ellipse((X(cx) - R, Y(cy) - R, X(cx) + R, Y(cy) + R), fill=INK if sw else fill)
        if sw:
            R2 = r * s - sw * s / 2
            d.ellipse((X(cx) - R2, Y(cy) - R2, X(cx) + R2, Y(cy) + R2), fill=fill)

    def line(pts, color, sw):
        P = [(X(x), Y(y)) for x, y in pts]
        d.line(P, fill=color, width=w(sw), joint="curve")
        for p in (P[0], P[-1]):
            r = sw * s / 2
            d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=color)

    def arc(cx, cy, r, a0, a1, color, sw):
        pts = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
               for a in np.linspace(a0, a1, 20)]
        line(pts, color, sw)

    if speed:
        for y, x0, x1 in ((9, -12, -3), (14, -10, -1), (19, -12, -4)):     # speed lines
            line([(x0, y), (x1, y)], INK, 1.6)
    if dust:                                                             # dust kicked up behind the rear wheel
        for cx, cy, r in ((1.5, 26.2, 2.3), (-2.6, 27.0, 1.6), (-5.6, 27.6, 1.0)):
            circle(cx, cy, r, PUFF, 0.7)
    bez = [((1 - t) ** 3 * 8 + 3 * (1 - t) ** 2 * t * 8 + 3 * (1 - t) * t * t * 16 + t ** 3 * 17,
            (1 - t) ** 3 * 6 + 3 * (1 - t) ** 2 * t * -0.5 + 3 * (1 - t) * t * t * -0.5 + t ** 3 * 6)
           for t in [i / 24 for i in range(25)]]
    line(bez, SIGNAL, 2.4)                                               # antenna
    rrect(2, 6, 36, 15, 5, ROO, 1.6)                                     # body
    d.rectangle((X(2.8), Y(12), X(30.8), Y(15.4)), fill=SIGNAL)          # stripe
    line([(6, 9), (22, 9)], SEAM, 1.2)
    rrect(30, 1.5, 13, 10, 2.5, CHROME, 1.6)                             # sonar head
    for cx in (33.8, 39.2):
        if eyes == "happy":                                              # closed, smiling eyes: ^ ^
            arc(cx, 7.9, 1.6, 205, 335, INK, 1.4)
        else:
            circle(cx, 6.5, 2.9, WHITE, 1.2)
            circle(cx + 0.7, 6.8, 1.25, INK)
    for cx in (11, 29):                                                  # wheels
        circle(cx, 22, 6.4, INK, 1.2)
        circle(cx, 22, 3, SIGNAL, 1.1)
    if wave:                                                             # the front wheel waves: motion arcs
        arc(29, 22, 9.8, -5, 50, INK, 1.2)
        arc(29, 22, 12.6, 3, 40, INK, 1.2)
    return X, Y


def finish_strip(d, y, flip=False):
    sq = S(16)
    d.rectangle((0, y, S(W), y + 2 * sq), fill=WHITE)
    for i in range(0, S(W) // sq + 1):
        for row in (0, 1):
            if (i + row) % 2 == 0:
                d.rectangle((i * sq, y + row * sq, (i + 1) * sq, y + (row + 1) * sq), fill=INK)
    ly = y - S(8) if flip else y + 2 * sq
    d.rectangle((0, ly, S(W), ly + S(8)), fill=SIGNAL)


def checker_block(d, x0, y0, cols=3, rows=4, sq=S(13)):
    d.rectangle((x0, y0, x0 + cols * sq, y0 + rows * sq), fill=WHITE)
    for row in range(rows):
        for col in range(cols):
            if (row + col) % 2 == 0:
                d.rectangle((x0 + col * sq, y0 + row * sq, x0 + (col + 1) * sq, y0 + (row + 1) * sq), fill=INK)


def draw_track(d, track_y, start=True, finish=True):
    """The yellow route under black tape, the full width of the page, with start and finish lines."""
    d.rectangle((0, track_y - S(22), S(W), track_y + S(30)), fill=SIGNAL)
    d.rectangle((0, track_y - S(2), S(W), track_y + S(14)), fill=INK)
    if start:
        checker_block(d, S(START_X), track_y - S(22))
    if finish:
        checker_block(d, S(FINISH_X), track_y - S(22))


# ---------------------------------------------------------------- the sign, bent by the wind

def wind_sign(title, sign_w, tf, lean=S(42), flutter=S(11)):
    """Draw the sign flat, then bend it as if it is moving fast to the right.

    The top leans back (left) by `lean`, the trailing edge is a little shorter (depth) and ripples
    by up to `flutter`, and the leading (right) edge stays straight. Returns the bent RGBA image,
    where the flat sign's top-left sits at (pad, pad), and a function giving the bottom edge's y at
    a flat-sign x, for attaching the poles.
    """
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lines = wrap(probe, title.upper(), tf, sign_w - S(120))
    lh = tf.size * 1.02
    sign_h = int(len(lines) * lh + S(110))
    sh = S(18)                                          # the yellow shadow offset
    pad = lean + flutter + S(40)
    cw, ch = sign_w + sh + 2 * pad, sign_h + sh + 2 * pad
    flat = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    fd = ImageDraw.Draw(flat)
    fd.rounded_rectangle((pad + sh, pad + sh, pad + sign_w + sh, pad + sign_h + sh), radius=S(34), fill=SIGNAL)
    fd.rounded_rectangle((pad, pad, pad + sign_w, pad + sign_h), radius=S(34), fill=WHITE, outline=INK, width=S(10))
    yy = pad + S(55)
    for ln in lines:
        fd.text((pad + sign_w / 2, yy), ln, font=tf, fill=INK, anchor="mt")
        yy += lh

    cy = sign_h / 2

    def k(u):                                           # height factor: 0.93 at the trailing edge, 1 at the front
        return 0.93 + 0.07 * np.clip(u / sign_w, 0, 1)

    def ripple(u):                                      # the flutter, strongest at the trailing edge
        un = np.clip(u / sign_w, 0, 1)
        return flutter * np.sin(2 * math.pi * un * 1.15 + 0.5) * (1 - 0.75 * un)

    # inverse map: for each output pixel, where it comes from on the flat sign
    V, U = np.mgrid[0:ch, 0:cw].astype(np.float32)
    u, v = U - pad, V - pad
    ys = cy + (v - cy - ripple(u)) / k(u)
    xs = u + lean * (1 - np.clip(ys, -sh, sign_h + sh) / sign_h)
    src = np.asarray(flat, dtype=np.float32)
    # premultiplied alpha, so the edges blend cleanly
    a = src[..., 3:4] / 255.0
    pm = np.concatenate([src[..., :3] * a, src[..., 3:4]], axis=2)
    out = np.stack([map_coordinates(pm[..., c], [ys + pad, xs + pad], order=1, mode="constant", cval=0)
                    for c in range(4)], axis=2)
    alpha = out[..., 3:4]
    rgb = np.where(alpha > 0, out[..., :3] / np.maximum(alpha / 255.0, 1e-6), 0)
    bent = Image.fromarray(np.concatenate([np.clip(rgb, 0, 255), alpha], axis=2).astype(np.uint8), "RGBA")

    def bottom_at(u_flat):                              # y of the sign's bottom edge, in bent-image coords
        return pad + cy + (sign_h - cy) * float(k(u_flat)) + float(ripple(u_flat))

    return bent, pad, sign_h, bottom_at


def pole(d, x0, y0, x1, y1):
    """A chrome pole with an ink outline from (x0, y0) to (x1, y1)."""
    d.line((x0, y0, x1, y1), fill=INK, width=S(22))
    d.line((x0, y0, x1, y1), fill=CHROME, width=S(10))


def wind_streaks(d, x_right, y_top, height):
    """Three ink streaks trailing behind the sign; x_right is where they end, near the sign."""
    for f, ln in ((0.22, 150), (0.5, 96), (0.78, 170)):
        y = y_top + height * f
        x1 = x_right
        x0 = x1 - S(ln)
        if x0 < S(16):
            continue
        d.line((x0, y, x1, y), fill=INK, width=S(9))
        for px in (x0, x1):
            d.ellipse((px - S(4.5), y - S(4.5), px + S(4.5), y + S(4.5)), fill=INK)


# ---------------------------------------------------------------- page parts shared by every page

def base_page():
    floor = Image.open(OUT / "workshop-floor-a4.jpg").convert("RGB").resize((S(W), S(H)), Image.LANCZOS)
    img = floor.convert("RGBA")
    d = ImageDraw.Draw(img)
    finish_strip(d, 0)
    finish_strip(d, S(H - 32), flip=True)
    return img, d


def big_lean_text(img, txt, size, nx=S(80), ny=S(130)):
    """The big leaning lap number (or word) with a yellow offset, drawn so nothing is clipped."""
    nf = bahn(size)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    l, t, r, b = probe.textbbox((0, 0), txt, font=nf)
    pad = int((b - t) * math.tan(math.radians(12))) + S(40)
    num = Image.new("RGBA", (r - l + pad + S(60), b - t + S(60)), (0, 0, 0, 0))
    nd = ImageDraw.Draw(num)
    nd.text((pad - l + S(18), S(10) - t + S(18)), txt, font=nf, fill=SIGNAL)
    nd.text((pad - l, S(10) - t), txt, font=nf, fill=INK, stroke_width=S(4), stroke_fill=INK)
    num = skew(num)
    num = num.crop(num.getbbox())
    img.alpha_composite(num, (nx, ny))
    return nx + num.width, ny


def lap_counter(img, d, ex, ey, tag_text, lap_text, done, current):
    tag_f = segoe(40)
    tw = d.textlength(tag_text, font=tag_f)
    tag = Image.new("RGBA", (int(tw + S(64)), S(76)), (0, 0, 0, 0))
    td = ImageDraw.Draw(tag)
    td.rectangle((0, 0, tag.width, tag.height), fill=SIGNAL)
    td.text((S(32), S(38)), tag_text, font=tag_f, fill=INK, anchor="lm")
    tag = skew(tag)
    img.alpha_composite(tag, (int(ex), int(ey)))
    lf = segoe(46)
    d.text((ex, ey + S(120)), lap_text, font=lf, fill=INK)
    for i in range(5):                                                   # 5 laps, the done ones in yellow
        x0, y0 = ex + i * S(62), ey + S(200)
        d.rounded_rectangle((x0, y0, x0 + S(46), y0 + S(46)), radius=S(8),
                            fill=SIGNAL if i < done else WHITE, outline=INK, width=S(5))
        if i == current - 1:
            d.rounded_rectangle((x0 + S(13), y0 + S(13), x0 + S(33), y0 + S(33)), radius=S(4), fill=INK)


def lockup(img):
    lock = Image.open(OUT / "title-lockup.png").convert("RGBA")
    lw = S(380)
    lock = lock.resize((lw, int(lock.height * lw / lock.width)), Image.LANCZOS)
    img.alpha_composite(lock, (S(W) - lw - S(80), S(H - 60) - lock.height - S(36)))


def save(img, n):
    out = img.convert("RGB").resize((W, H), Image.LANCZOS)
    path = OUT / f"section-{n:02d}.jpg"
    out.save(path, quality=90, optimize=True)
    return path


# ---------------------------------------------------------------- the five dividers

def divider(n, title, checkpoints):
    img, d = base_page()

    num_right, ny = big_lean_text(img, f"{n:02d}", 560)
    lap_counter(img, d, num_right + S(40), ny + S(90), "SECTION", f"LAP {n} OF 5", n, n)

    s = S(ROO_S)
    track_y = S(TRACK_Y)
    ox = S(ROO_X[n - 1])
    oy = track_y - 32.4 * s                                              # wheels touch the track
    draw_track(d, track_y)

    # ---- the sign, bent by the wind, on two poles that lean back ----
    tf = bahn(118 if len(title) < 40 else 104)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    one_line = probe.textlength(title.upper(), font=tf)
    sign_w = int(min(S(1180), max(S(700), one_line + S(200))))
    bent, pad, sign_h, bottom_at = wind_sign(title, sign_w, tf)
    lean, drift = S(42), S(48)                       # the top of the sign leans back; the poles too
    pole_x = [ox + (5 + 14) * s, ox + (25 + 14) * s]
    body_top = oy + (6 + 4) * s
    pole_len = S(190)
    # the sign follows Roo, but always stays whole on the page
    sx = (pole_x[0] + pole_x[1]) / 2 - drift - sign_w / 2
    sx = min(max(sx, S(26) + lean), S(W) - S(30) - S(18) - sign_w)
    sign_bottom = body_top - pole_len
    sy = sign_bottom - sign_h                                            # flat sign top on the page
    for px in pole_x:
        uf = px - drift - sx
        top_y = sy - pad + bottom_at(uf) - S(26)
        pole(d, px, body_top + S(4), px - drift, top_y)
    img.alpha_composite(bent, (int(sx - pad), int(sy - pad)))
    wind_streaks(d, sx - lean - S(34), sy + S(10), sign_h * 0.8)

    draw_roo(d, ox, oy, s)

    # ---- checkpoints: one flag per sub-topic, along the track ----
    if checkpoints:
        cf = segoe(34, "seguisb.ttf")
        k = len(checkpoints)
        span0, span1 = S(110), S(W - 110)
        for i, name in enumerate(checkpoints):
            cx = span0 + (span1 - span0) * (i + 0.5) / k
            d.ellipse((cx - S(20), track_y - S(14), cx + S(20), track_y + S(26)), fill=WHITE, outline=INK, width=S(6))
            d.rectangle((cx - S(4), track_y + S(30), cx + S(4), track_y + S(100)), fill=INK)
            lines_c = wrap(d, name, cf, S(1260 / k))
            bw = max(d.textlength(t, font=cf) for t in lines_c) + S(44)
            bh = len(lines_c) * cf.size * 1.2 + S(30)
            bx, by = cx - bw / 2, track_y + S(100)
            d.rounded_rectangle((bx + S(8), by + S(8), bx + bw + S(8), by + bh + S(8)), radius=S(12), fill=SIGNAL)
            d.rounded_rectangle((bx, by, bx + bw, by + bh), radius=S(12), fill=INK)
            ty = by + S(15)
            for t in lines_c:
                d.text((cx, ty), t, font=cf, fill=WHITE, anchor="mt")
                ty += cf.size * 1.2
    else:
        sf = segoe(46)
        d.text((S(W / 2), track_y + S(120)), "START YOUR ENGINES", font=sf, fill=INK, anchor="mt")

    lockup(img)
    return save(img, n)


# ---------------------------------------------------------------- the closing page

def speech_bubble(img, text, x, y, tail_to, font):
    """A white bubble with an ink outline and a yellow shadow; (x, y) is its top-left."""
    d = ImageDraw.Draw(img)
    tw = d.textlength(text, font=font)
    bw, bh = int(tw + S(90)), int(font.size * 1.0 + S(70))
    sh = S(14)
    tx, ty = tail_to
    base = [(x + bw * 0.30, y + bh - S(4)), (x + bw * 0.48, y + bh - S(4))]
    tail = [base[0], (tx, ty), base[1]]
    # shadow, then the outlined bubble and tail
    d.rounded_rectangle((x + sh, y + sh, x + bw + sh, y + bh + sh), radius=S(30), fill=SIGNAL)
    d.polygon([(px + sh * 0.6, py + sh * 0.6) for px, py in tail], fill=SIGNAL)
    d.polygon(tail, fill=INK)
    inner = [(base[0][0] + S(10), base[0][1] - S(6)), (tx + (S(6) if tx < base[0][0] else -S(2)), ty - S(16)),
             (base[1][0] - S(10), base[1][1] - S(6))]
    d.rounded_rectangle((x, y, x + bw, y + bh), radius=S(30), fill=INK)
    d.rounded_rectangle((x + S(9), y + S(9), x + bw - S(9), y + bh - S(9)), radius=S(22), fill=WHITE)
    d.polygon(inner, fill=WHITE)
    d.text((x + bw / 2, y + bh / 2), text, font=font, fill=INK, anchor="mm")


def closing_page(n=6):
    img, d = base_page()

    word_right, ny = big_lean_text(img, "BYE!", 460)
    lap_counter(img, d, word_right + S(40), ny + S(70), "FINISH", "ALL 5 LAPS DONE", 5, 0)

    track_y = S(TRACK_Y - 170)                     # higher than the dividers, to make room for the message
    draw_track(d, track_y, start=False, finish=False)
    # the finish line Roo has just crossed, and chevrons: the road goes on
    checker_block(d, S(330), track_y - S(22), cols=4, rows=4)
    for i in range(3):
        cx = S(W - 250 + i * 56)
        d.polygon([(cx, track_y - S(18)), (cx + S(22), track_y - S(18)), (cx + S(44), track_y + S(4)),
                   (cx + S(22), track_y + S(26)), (cx, track_y + S(26)), (cx + S(22), track_y + S(4))], fill=WHITE)

    # Roo, pulled up past the finish, on its back wheel, waving the front one
    s = S(13)
    layer = Image.new("RGBA", (S(W), S(H)), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ox = S(560)
    oy = track_y - 32.4 * s
    X, Y = draw_roo(ld, ox, oy, s, eyes="happy", speed=False, dust=False, wave=True)
    pivot = (X(11), track_y)                                             # rear wheel on the track
    layer = layer.rotate(17, resample=Image.BICUBIC, center=pivot)
    img.alpha_composite(layer)

    # the head after the wheelie, for the bubble's tail
    a = math.radians(17)
    hx, hy = X(36.5) - pivot[0], Y(1.0) - pivot[1]
    head = (pivot[0] + hx * math.cos(a) + hy * math.sin(a), pivot[1] - hx * math.sin(a) + hy * math.cos(a))
    bf = bahn(70)
    speech_bubble(img, "SEE YOU ON THE NEXT TRACK!", S(560), track_y - S(740), (head[0] - S(30), head[1] - S(30)), bf)

    # the message under the track
    mf = bahn(104)
    d = ImageDraw.Draw(img)
    l1, l2 = "THIS IS THE END OF OUR RACE,", "NOT THE END OF THE ROAD."
    y1 = track_y + S(140)
    d.text((S(W / 2), y1), l1, font=mf, fill=INK, anchor="mt")
    w2 = d.textlength(l2, font=mf)
    band = Image.new("RGBA", (int(w2 + S(90)), int(mf.size * 1.25)), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    bd.rectangle((0, 0, band.width, band.height), fill=SIGNAL)
    bd.text((band.width / 2, band.height / 2 + S(4)), l2, font=mf, fill=INK, anchor="mm")
    band = skew(band)
    img.alpha_composite(band, (int(S(W / 2) - band.width / 2), int(y1 + mf.size * 1.25)))

    lockup(img)
    return save(img, n)


if __name__ == "__main__":
    for i, (t, cps) in enumerate(SECTIONS, 1):
        print(divider(i, t, cps))
    print(closing_page())
