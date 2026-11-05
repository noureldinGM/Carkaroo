"""Sketch box-free ideas for the Carkaroo wordmark in the poster header (no box behind "roo")."""
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_fill_holes
from make_section_dividers import OUT, SS, S, INK, SIGNAL, WHITE, segoe, draw_roo

GREY, GREY_D = (214, 216, 218), (188, 191, 194)
PW, PH, GAP = 640, 230, 24
img = Image.new("RGB", (S(GAP + 2 * (PW + GAP)), S(GAP + 3 * (PH + 46 + GAP))), WHITE)
d = ImageDraw.Draw(img)
word = segoe(96)
cap = segoe(17, "seguisb.ttf")


def panel(i, label):
    c, r = i % 2, i // 2
    x0, y0 = S(GAP + c * (PW + GAP)), S(GAP + r * (PH + 46 + GAP))
    d.rounded_rectangle((x0, y0, x0 + S(PW), y0 + S(PH)), radius=S(10), fill=GREY)
    sq = S(10)                                     # the poster's checker edge, for context
    for k in range(PW // 10):
        if k % 2 == 0:
            d.rectangle((x0 + k * sq, y0, x0 + (k + 1) * sq, y0 + sq), fill=INK)
        else:
            d.rectangle((x0 + k * sq, y0 + sq, x0 + (k + 1) * sq, y0 + 2 * sq), fill=INK)
    d.text((x0 + S(PW / 2), y0 + S(PH + 24)), label, font=cap, fill=INK, anchor="mm")
    return x0, y0


def speed_lines(x_right, y_mid, n=3, length=S(46), gap=S(14), color=INK, wd=S(5)):
    for k in range(n):
        y = y_mid + (k - (n - 1) / 2) * gap
        ln = length * (1 - 0.25 * (k % 2))
        d.line((x_right - ln, y, x_right, y), fill=color, width=wd)
        for px in (x_right - ln, x_right):
            d.ellipse((px - wd / 2, y - wd / 2, px + wd / 2, y + wd / 2), fill=color)


def wheel(cx, cy, r):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=INK)
    d.ellipse((cx - r * 0.47, cy - r * 0.47, cx + r * 0.47, cy + r * 0.47), fill=SIGNAL)
    d.ellipse((cx - r * 0.14, cy - r * 0.14, cx + r * 0.14, cy + r * 0.14), fill=INK)


L = lambda t, f=word: d.textlength(t, font=f)

# 1  Outlined "roo": yellow letters, thick ink outline and a hard ink shadow
x0, y0 = panel(0, "1  Outlined roo")
bx, by = x0 + S(28), y0 + S(150)
d.text((bx, by), "Carka", font=word, fill=INK, anchor="ls")
rx = bx + L("Carka") + S(2)
d.text((rx + S(6), by + S(6)), "roo", font=word, fill=INK, anchor="ls", stroke_width=S(4), stroke_fill=INK)
d.text((rx, by), "roo", font=word, fill=SIGNAL, anchor="ls", stroke_width=S(4), stroke_fill=INK)
draw_roo(d, x0 + S(492), y0 + S(86), S(2.15), dust=False, speed=False)

# 2  Wheels for the "oo": the word becomes the car, with the antenna over it
x0, y0 = panel(1, "2  Wheels as the oo")
bx, by = x0 + S(70), y0 + S(156)
speed_lines(bx - S(8), by - S(30))
d.text((bx, by), "Carkar", font=word, fill=INK, anchor="ls")
r = S(26)
wx = bx + L("Carkar") + r + S(4)
for k in range(2):
    wheel(wx + k * (2 * r + S(10)), by - r, r)
ax0, ax1 = wx - S(4), wx + 2 * r + S(14)               # antenna arc over the wheels, like Roo's
d.arc((ax0 + S(8), by - 2 * r - S(30), ax1 - S(8), by - 2 * r + S(6)), 200, 340, fill=SIGNAL, width=S(7))

# 3  Lane underline: all-ink word on a yellow track line, checker flag under "roo"
x0, y0 = panel(2, "3  Track underline")
bx, by = x0 + S(30), y0 + S(140)
d.text((bx, by), "Carkaroo", font=word, fill=INK, anchor="ls")
tw = L("Carkaroo")
ly = by + S(18)
d.polygon([(bx + S(4), ly), (bx + tw + S(150), ly), (bx + tw + S(144), ly + S(12)), (bx - S(2), ly + S(12))], fill=SIGNAL)
cx0 = bx + L("Carka") + S(10)
sq = S(8)
for k in range(int((L("roo") - S(8)) // sq)):
    for rr in range(2):
        if (k + rr) % 2 == 0:
            d.rectangle((cx0 + k * sq, ly + S(14) + rr * sq, cx0 + (k + 1) * sq, ly + S(14) + (rr + 1) * sq), fill=INK)
draw_roo(d, bx + tw + S(36), ly - S(36 * 2.0 - 4), S(2.0), dust=False, speed=False)

# 4  Motion trail: yellow "roo" racing ahead of fading copies of itself
x0, y0 = panel(3, "4  Motion trail")
bx, by = x0 + S(40), y0 + S(150)
d.text((bx, by), "Carka", font=word, fill=INK, anchor="ls")
rx = bx + L("Carka") + S(30)
ghost = Image.new("RGBA", img.size, (0, 0, 0, 0))
gd = ImageDraw.Draw(ghost)
for k, col in ((3, (205, 197, 160)), (2, (215, 193, 110)), (1, (230, 192, 60))):
    gd.text((rx - k * S(14), by), "roo", font=word, fill=col, anchor="ls")
m = Image.new("L", img.size, 0)
ImageDraw.Draw(m).text((rx, by), "roo", font=word, fill=255, anchor="ls", stroke_width=S(3), stroke_fill=255)
solid = binary_fill_holes(np.array(m) > 0)
a = np.array(ghost); a[solid, 3] = 0
img.paste(Image.fromarray(a), (0, 0), Image.fromarray(a))
d.text((rx, by), "roo", font=word, fill=SIGNAL, anchor="ls", stroke_width=S(3), stroke_fill=INK)
speed_lines(rx + L("roo") + S(70), by - S(36), wd=S(5))

# 5  Two-tone with a speed swoosh: tapered yellow streak sweeping under the word
x0, y0 = panel(4, "5  Speed swoosh")
bx, by = x0 + S(40), y0 + S(140)
tw = L("Carkaroo")
sy = by - S(8)
d.polygon([(bx - S(20), sy + S(10)), (bx + tw + S(150), sy - S(4)), (bx + tw + S(156), sy + S(8)), (bx + S(40), sy + S(20))], fill=SIGNAL)
d.text((bx, by), "Carka", font=word, fill=INK, anchor="ls")
d.text((bx + L("Carka"), by), "roo", font=word, fill=WHITE, anchor="ls", stroke_width=S(4), stroke_fill=INK)
draw_roo(d, bx + tw + S(22), sy - S(30 * 2.0), S(2.0), dust=False, speed=False)

# 6  Stacked: small "CARKA" over a huge yellow "ROO", Roo parked on top
x0, y0 = panel(5, "6  Stacked")
big = segoe(132)
small = segoe(46)
bx, by = x0 + S(150), y0 + S(196)
d.text((bx + S(7), by + S(7)), "roo", font=big, fill=INK, anchor="ls", stroke_width=S(5), stroke_fill=INK)
d.text((bx, by), "roo", font=big, fill=SIGNAL, anchor="ls", stroke_width=S(5), stroke_fill=INK)
d.text((bx + S(8), by - S(96)), "Carka", font=small, fill=INK, anchor="ls")
draw_roo(d, bx + L("roo", big) - S(36), y0 + S(40), S(2.3), dust=False)

img.resize((img.width // SS, img.height // SS), Image.LANCZOS).save(OUT / "wordmark-ideas.png")
print("ok")
