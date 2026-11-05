"""Idea 7 at print size: "Carkar" + two googly eyes as the "oo", antenna above, yellow line below.

Transparent PNG, cropped tight, for the poster header (replaces the old title image and the separate Roo).
"""
from PIL import Image, ImageDraw
from make_section_dividers import OUT, INK, SIGNAL, WHITE, FONTS
from PIL import ImageFont

K = 8                                     # pixels per sketch unit (the sketch was drawn at 2 px/unit)
font = ImageFont.truetype(rf"{FONTS}\seguibli.ttf", int(96 * K))
img = Image.new("RGBA", (int(700 * K), int(240 * K)), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
U = lambda v: v * K

bx, by = U(10), U(190)
d.text((bx, by), "Carkar", font=font, fill=INK, anchor="ls")
r = U(29)
ex = bx + d.textlength("Carkar", font=font) + r + U(4)
for k in range(2):
    cx, cy = ex + k * (2 * r + U(6)), by - r
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=INK)
    d.ellipse((cx - r + U(8), cy - r + U(8), cx + r - U(8), cy + r - U(8)), fill=WHITE)
    pr = U(10)
    d.ellipse((cx + U(5) - pr, cy + U(2) - pr, cx + U(5) + pr, cy + U(2) + pr), fill=INK)
    d.ellipse((cx + U(5), cy - U(6), cx + U(11), cy), fill=WHITE)          # eye shine
d.arc((ex - U(14), by - 2 * r - U(44), ex + 2 * r + U(20), by - 2 * r + U(2)), 200, 340, fill=SIGNAL, width=int(U(7)))
d.rounded_rectangle((bx + U(4), by + U(12), ex + 3 * r + U(20), by + U(21)), radius=U(4.5), fill=SIGNAL)

img = img.crop(img.getbbox())
img = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)
img.save(OUT / "wordmark-eyes.png")
print(img.size)
