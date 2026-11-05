"""Render the poster's section banners in the "race number" style (poster edition 1).

Each banner: a white race-number disc, an asphalt plate leaning -12 degrees with a yellow kerb,
and the heading in Bahnschrift Bold Condensed. Sizes are A0 poster pixels (4535 x 3402 page).

  race-banner-01.png ... race-banner-10.png   transparent PNGs
  race-banners.json                            where each one goes on the poster (left, top, width, height)

Run:  .venv\\Scripts\\python design\\print\\make_race_banners.py
"""
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
INK, SIGNAL, WHITE = (18, 19, 20), (246, 194, 28), (255, 255, 255)
SS = 2

# (heading, plate left, plate top, plate width, plate height) - the current plates on the poster
BANNERS = [
    ("ABSTRACT", 381, 709, 518, 112),
    ("INTRODUCTION", 294, 1320, 680, 112),
    ("MATERIALS & METHODS", 270, 2214, 736, 136),
    ("RESULTS", 1496, 2247, 518, 112),
    ("ANALYSIS", 2576, 677, 597, 112),
    ("CONCLUSIONS", 3589, 678, 680, 112),
    ("RECOMMENDATION", 3552, 1379, 736, 112),
    ("LITERATURE CITED", 3625, 2026, 599, 112),
    ("ACKNOWLEDGMENT", 3639, 2605, 597, 112),
    ("FOR FURTHER INFORMATION", 3581, 2950, 711, 136),
]


def bahn(size):
    f = ImageFont.truetype(r"C:\Windows\Fonts\bahnschrift.ttf", int(size * SS))
    f.set_variation_by_name(b"Bold Condensed")
    return f


def banner(n, text, px, py, pw, ph):
    H = 112                                   # one plate height for every banner, so they all match
    D = H + 44                                # race-number disc
    kerb, ring = 16, 9
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    size = 68
    slant = H * math.tan(math.radians(12))
    while True:                               # shrink the heading until it fits the plate
        f = bahn(size)
        tw = probe.textlength(text, font=f) / SS
        need = D / 2 + 26 + tw + slant + 34
        if need <= max(pw, 500) + 120 or size <= 50:
            break
        size -= 2
    W = max(pw, int(need))
    cx_center = px + pw / 2                   # keep each banner centred where the old one was
    plate_left = cx_center - W / 2 + D / 4
    plate_top = py + ph / 2 - H / 2
    ox, oy = plate_left - D / 2 - 8, plate_top - (D - H) / 2 - 8   # canvas origin on the poster
    cw, ch = W + D / 2 + kerb + 20, D + kerb + 20
    img = Image.new("RGBA", (int(cw * SS), int(ch * SS)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    X = lambda v: (v - ox) * SS
    Yy = lambda v: (v - oy) * SS
    s = slant

    def plate(dx, dy, fill):
        d.polygon([(X(plate_left + s + dx), Yy(plate_top + dy)), (X(plate_left + W + dx), Yy(plate_top + dy)),
                   (X(plate_left + W - s + dx), Yy(plate_top + H + dy)), (X(plate_left + dx), Yy(plate_top + H + dy))],
                  fill=fill)

    plate(kerb, kerb, SIGNAL)
    plate(0, 0, INK)
    d.text((X(plate_left + D / 2 + 26 + (W - D / 2 - 26 - s) / 2), Yy(plate_top + H / 2 + 2)), text,
           font=f, fill=WHITE, anchor="mm")
    # the race-number disc, half over the plate's left end
    dcx, dcy = plate_left + 18, plate_top + H / 2
    r = D / 2
    d.ellipse((X(dcx - r + 6), Yy(dcy - r + 6), X(dcx + r + 6), Yy(dcy + r + 6)), fill=SIGNAL)
    d.ellipse((X(dcx - r), Yy(dcy - r), X(dcx + r), Yy(dcy + r)), fill=INK)
    d.ellipse((X(dcx - r + ring), Yy(dcy - r + ring), X(dcx + r - ring), Yy(dcy + r - ring)), fill=WHITE)
    d.text((X(dcx), Yy(dcy + 3)), f"{n:02d}", font=bahn(74), fill=INK, anchor="mm")

    out = img.resize((int(cw), int(ch)), Image.LANCZOS)
    path = OUT / f"race-banner-{n:02d}.png"
    out.save(path, optimize=True)
    return {"file": path.name, "heading": text, "left": round(ox), "top": round(oy), "width": out.width, "height": out.height}


if __name__ == "__main__":
    spots = [banner(i, *b) for i, b in enumerate(BANNERS, 1)]
    (OUT / "race-banners.json").write_text(json.dumps(spots, indent=1))
    for s_ in spots:
        print(s_)
