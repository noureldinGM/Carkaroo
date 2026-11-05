"""Six more box-free ideas for the Carkaroo wordmark (ideas 7-12), same sheet style as make_wordmark_ideas.py."""
import numpy as np
from PIL import Image, ImageDraw
from make_section_dividers import OUT, SS, S, INK, SIGNAL, WHITE, segoe, draw_roo

GREY = (214, 216, 218)
PW, PH, GAP = 640, 230, 24
img = Image.new("RGB", (S(GAP + 2 * (PW + GAP)), S(GAP + 3 * (PH + 46 + GAP))), WHITE)
d = ImageDraw.Draw(img)
word = segoe(96)
cap = segoe(17, "seguisb.ttf")
L = lambda t, f=word: d.textlength(t, font=f)


def panel(i, label):
    c, r = i % 2, i // 2
    x0, y0 = S(GAP + c * (PW + GAP)), S(GAP + r * (PH + 46 + GAP))
    d.rounded_rectangle((x0, y0, x0 + S(PW), y0 + S(PH)), radius=S(10), fill=GREY)
    sq = S(10)
    for k in range(PW // 10):
        yy = y0 if k % 2 == 0 else y0 + sq
        d.rectangle((x0 + k * sq, yy, x0 + (k + 1) * sq, yy + sq), fill=INK)
    d.text((x0 + S(PW / 2), y0 + S(PH + 24)), label, font=cap, fill=INK, anchor="mm")
    return x0, y0


def mask(text, pos, font=word, stroke=0):
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).text(pos, text, font=font, fill=255, anchor="ls", stroke_width=stroke, stroke_fill=255)
    return m


def fill_mask(m, pattern):
    """Paint an RGB pattern image (full sheet size) through a mask."""
    img.paste(pattern, (0, 0), m)


# 7  Eyes for the oo: the last two letters become Roo's googly eyes, looking ahead
x0, y0 = panel(0, "7  Eyes as the oo")
bx, by = x0 + S(40), y0 + S(156)
d.text((bx, by), "Carkar", font=word, fill=INK, anchor="ls")
r = S(29)
ex = bx + L("Carkar") + r + S(4)
for k in range(2):
    cx, cy = ex + k * (2 * r + S(6)), by - r
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=INK)
    d.ellipse((cx - r + S(8), cy - r + S(8), cx + r - S(8), cy + r - S(8)), fill=WHITE)
    pr = S(10)
    d.ellipse((cx + S(5) - pr, cy + S(2) - pr, cx + S(5) + pr, cy + S(2) + pr), fill=INK)
    d.ellipse((cx + S(8) - S(3), cy - S(3) - S(3), cx + S(8) + S(3), cy - S(3) + S(3)), fill=WHITE)
d.arc((ex - S(14), by - 2 * r - S(44), ex + 2 * r + S(20), by - 2 * r + S(2)), 200, 340, fill=SIGNAL, width=S(7))
d.line((bx + S(4), by + S(16), ex + 3 * r + S(20), by + S(16)), fill=SIGNAL, width=S(9))

# 8  Body stripe: a yellow stripe runs through the letters, like the stripe on Roo's side
x0, y0 = panel(1, "8  Body stripe")
bx, by = x0 + S(56), y0 + S(150)
d.text((bx, by), "Carkaroo", font=word, fill=INK, anchor="ls")
tw = L("Carkaroo")
sy0, sy1 = by - S(40), by - S(28)
band = Image.new("L", img.size, 0)
ImageDraw.Draw(band).rectangle((bx - S(10), sy0, bx + tw + S(10), sy1), fill=255)
cut = Image.fromarray(np.minimum(np.array(band), np.array(mask("Carkaroo", (bx, by)))))
img.paste(SIGNAL, (0, 0), cut)
ImageDraw.Draw(img).line((bx - S(40), (sy0 + sy1) / 2, bx - S(12), (sy0 + sy1) / 2), fill=SIGNAL, width=S(12))
draw_roo(d, bx + tw + S(8), y0 + S(92), S(1.8), dust=False, speed=False)

# 9  Hollow + solid: "Carka" drawn as an ink outline only, "roo" solid yellow
x0, y0 = panel(2, "9  Hollow Carka, solid roo")
bx, by = x0 + S(34), y0 + S(150)
d.text((bx, by), "Carka", font=word, fill=INK, anchor="ls", stroke_width=S(4), stroke_fill=INK)
d.text((bx, by), "Carka", font=word, fill=GREY, anchor="ls")
rx = bx + L("Carka") + S(4)
d.text((rx + S(5), by + S(5)), "roo", font=word, fill=INK, anchor="ls")
d.text((rx, by), "roo", font=word, fill=SIGNAL, anchor="ls")
draw_roo(d, x0 + S(488), y0 + S(86), S(2.15), dust=False, speed=False)

# 10  Accelerating: letters grow and turn from ink to yellow, like the car picking up speed
x0, y0 = panel(3, "10  Accelerating letters")
bx, by = x0 + S(92), y0 + S(160)
x = bx
cols = [INK, INK, INK, INK, INK, (120, 100, 30), (190, 150, 25), SIGNAL]
for k, ch in enumerate("Carkaroo"):
    f = segoe(66 + k * 7)
    if k >= 5:
        d.text((x, by), ch, font=f, fill=cols[k], anchor="ls", stroke_width=S(3), stroke_fill=INK)
    else:
        d.text((x, by), ch, font=f, fill=cols[k], anchor="ls")
    x += d.textlength(ch, font=f) - S(1)
for k, ln in enumerate((40, 60, 40)):
    y = by - S(36 + k * 18)
    d.line((bx - S(14) - S(ln), y, bx - S(14), y), fill=INK, width=S(5))

# 11  Finish flag: "roo" filled with a checkered flag
x0, y0 = panel(4, "11  Checkered roo")
bx, by = x0 + S(40), y0 + S(150)
d.text((bx, by), "Carka", font=word, fill=INK, anchor="ls")
rx = bx + L("Carka") + S(4)
d.text((rx, by), "roo", font=word, fill=INK, anchor="ls", stroke_width=S(4), stroke_fill=INK)
chk = Image.new("RGB", img.size, WHITE)
cd = ImageDraw.Draw(chk)
sq = S(13)
for i in range(int(L("roo") // sq) + 3):
    for j in range(9):
        if (i + j) % 2 == 0:
            cd.rectangle((rx + i * sq, by - S(100) + j * sq, rx + (i + 1) * sq, by - S(100) + (j + 1) * sq), fill=INK)
fill_mask(mask("roo", (rx, by)), chk)
d = ImageDraw.Draw(img)
d.line((rx, by + S(14), rx + L("roo"), by + S(14)), fill=SIGNAL, width=S(9))
draw_roo(d, x0 + S(488), y0 + S(86), S(2.15), dust=False, speed=False)

# 12  Tyre tracks: two tread lines run from under the word to Roo's wheels
x0, y0 = panel(5, "12  Tyre tracks")
bx, by = x0 + S(30), y0 + S(130)
d.text((bx, by), "Carka", font=word, fill=INK, anchor="ls")
d.text((bx + L("Carka"), by), "roo", font=word, fill=SIGNAL, anchor="ls", stroke_width=S(4), stroke_fill=INK)
rs = S(2.0)
rox, roy = x0 + S(476), y0 + S(126)
draw_roo(d, rox, roy, rs, dust=False, speed=False)
wheel_y = roy + (22 + 4 + 6.4) * rs
for row, yy in enumerate((wheel_y - S(2), wheel_y + S(12))):
    x = bx + S(10) + row * S(6)
    end = rox + (11 + 14 - 6) * rs
    k = 0
    while x < end:
        a = min(255, 70 + int(185 * (x - bx) / (end - bx)))
        c = tuple(int(GREY[i] + (INK[i] - GREY[i]) * a / 255) for i in range(3))
        d.polygon([(x, yy - S(4)), (x + S(9), yy - S(4)), (x + S(5), yy + S(4)), (x - S(4), yy + S(4))], fill=c)
        x += S(14)

img.resize((img.width // SS, img.height // SS), Image.LANCZOS).save(OUT / "wordmark-ideas-2.png")
print("ok")
