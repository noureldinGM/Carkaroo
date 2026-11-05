"""Render the Carkaroo print assets (poster / portfolio / slides):

  title-lockup.png       "Carka" + "roo" on a slanted plate, Bahnschrift Bold Condensed, transparent
  workshop-floor.jpg     A0-landscape background: chrome-grey floor with a faint factory plan
  workshop-floor-a4.jpg  the same floor for A4 portrait pages

Run:  .venv\\Scripts\\python design\\print\\make_print_assets.py
Needs Pillow and the Windows font Bahnschrift (C:\\Windows\\Fonts\\bahnschrift.ttf).
"""
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parent
INK, SIGNAL = (18, 19, 20), (246, 194, 28)
FONT = r"C:\Windows\Fonts\bahnschrift.ttf"


def font(size, style=b"Bold Condensed"):
    f = ImageFont.truetype(FONT, size)
    f.set_variation_by_name(style)
    return f


def skew(img, deg=-12):
    """Lean an RGBA image forward like italic type."""
    k = math.tan(math.radians(-deg))
    w, h = img.size
    nw = int(w + k * h)
    return img.transform((nw, h), Image.AFFINE, (1, -k, k * h, 0, 1, 0), Image.BICUBIC)


def title_lockup(height=520):
    f = font(int(height * 0.92))
    a = Image.new("RGBA", (3000, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(a)
    l, t, r, b = d.textbbox((0, 0), "Carka", font=f)
    pad = int(height * 0.12)                 # room for the lean, so the "C" is not clipped
    d.text((pad - l, (height - (b - t)) // 2 - t), "Carka", font=f, fill=INK)
    carka_w = pad + r - l
    # the plate with "roo": yellow kerb, asphalt plate, yellow letters
    fr = font(int(height * 0.78))
    rl, rt, rr, rb = d.textbbox((0, 0), "roo", font=fr)
    pw, ph = (rr - rl) + int(height * 0.34), int(height * 0.86)
    px, py = carka_w + int(height * 0.08), (height - ph) // 2 - int(height * 0.03)
    kerb = int(height * 0.06)
    d.rounded_rectangle((px + kerb, py + kerb, px + pw + kerb, py + ph + kerb), radius=int(height * 0.06), fill=SIGNAL)
    d.rounded_rectangle((px, py, px + pw, py + ph), radius=int(height * 0.06), fill=INK)
    d.text((px + (pw - (rr - rl)) // 2 - rl, py + (ph - (rb - rt)) // 2 - rt), "roo", font=fr, fill=SIGNAL)
    a = a.crop((0, 0, px + pw + kerb + 4, height))
    a = skew(a)
    a = a.crop(a.getbbox())
    a.save(OUT / "title-lockup.png")
    return a.size


def workshop_floor(w, h, name, scale=1.0):
    """Chrome-grey floor: soft vertical shade, faint dot grid, a quiet factory plan in light lines."""
    top, bottom = (200, 204, 208), (170, 175, 180)
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        t = y / (h - 1)
        c = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(w):
            px[x, y] = c
    # vignette: a touch darker at the edges, so the centre feels lit
    vig = Image.new("L", (w, h), 0)
    ImageDraw.Draw(vig).ellipse((-w * 0.25, -h * 0.35, w * 1.25, h * 1.35), fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(int(min(w, h) * 0.12)))
    dark = Image.new("RGB", (w, h), (120, 125, 130))
    img = Image.composite(img, dark, vig.point(lambda v: int(150 + v * 105 / 255)))

    lay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    s = scale
    # dot grid (10 cm on the floor)
    step = int(46 * s)
    for y in range(step // 2, h, step):
        for x in range(step // 2, w, step):
            r = max(1, int(2.2 * s))
            d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, 38))
    # the factory plan: aisles, station outlines, lane arrows (white, faint)
    rnd = random.Random(12328)
    line = (255, 255, 255, 70)
    lw = max(2, int(6 * s))
    for k in range(5):                       # long aisles with dashed centre lines
        y = int(h * (0.18 + k * 0.17))
        for x in range(0, w, int(120 * s)):
            d.line((x, y, x + int(60 * s), y), fill=(255, 255, 255, 55), width=lw)
    for k in range(6):                       # cross aisles
        x = int(w * (0.08 + k * 0.17))
        d.line((x, 0, x, h), fill=(255, 255, 255, 30), width=max(1, int(3 * s)))
    placed = []
    for _ in range(400):                     # station / rack outlines, never overlapping
        if len(placed) >= 22:
            break
        bw, bh = int(rnd.randint(160, 340) * s), int(rnd.randint(110, 220) * s)
        x, y = rnd.randint(0, w - bw), rnd.randint(0, h - bh)
        gap = int(60 * s)
        if any(x < X + W + gap and X < x + bw + gap and y < Y + H + gap and Y < y + bh + gap for X, Y, W, H in placed):
            continue
        placed.append((x, y, bw, bh))
        d.rounded_rectangle((x, y, x + bw, y + bh), radius=int(18 * s), outline=line, width=lw)
        if rnd.random() < 0.5:               # a little load mark inside some stations
            d.line((x + bw * 0.2, y + bh * 0.5, x + bw * 0.8, y + bh * 0.5), fill=(255, 255, 255, 45), width=lw)
    for _ in range(10):                      # direction arrows on the floor
        x, y, a = rnd.randint(0, w), rnd.randint(0, h), rnd.choice([0, 90, 180, 270])
        L = int(70 * s)
        pts = [(-L, -L * 0.45), (L * 0.4, -L * 0.45), (L * 0.4, -L), (L * 1.2, 0), (L * 0.4, L), (L * 0.4, L * 0.45), (-L, L * 0.45)]
        ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
        d.polygon([(x + px_ * ca - py_ * sa, y + px_ * sa + py_ * ca) for px_, py_ in pts], fill=(255, 255, 255, 28))
    # a soft checkered flag fading in from the bottom-right corner
    sq = int(64 * s)
    for gy in range(0, int(h * 0.32), sq):
        for gx in range(0, int(w * 0.30), sq):
            if (gx // sq + gy // sq) % 2 == 0:
                fade = 1 - max(gx / (w * 0.30), gy / (h * 0.32))
                if fade > 0:
                    d.rectangle((w - gx - sq, h - gy - sq, w - gx, h - gy), fill=(18, 19, 20, int(34 * fade)))
    img = Image.alpha_composite(img.convert("RGBA"), lay).convert("RGB")
    img.save(OUT / name, quality=88, optimize=True)
    return img.size


if __name__ == "__main__":
    print("title", title_lockup())
    print("A0", workshop_floor(4535, 3402, "workshop-floor.jpg", scale=1.0))
    print("A4", workshop_floor(1588, 2246, "workshop-floor-a4.jpg", scale=0.5))
