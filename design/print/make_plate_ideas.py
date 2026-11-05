"""Sketch three group-number plate ideas for the portfolio cover, in the Carkaroo style."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
S = 2
INK, Y, W, G = (18, 19, 20), (246, 194, 28), (255, 255, 255), (196, 200, 204)
F = r"C:\Windows\Fonts"
def f(name, size): return ImageFont.truetype(rf"{F}\{name}", int(size * S))
big, small, cap = f("seguibli.ttf", 50), f("seguibli.ttf", 15), f("seguisb.ttf", 18)

CW, CH = 360, 230
img = Image.new("RGB", (S * (CW * 3 + 80), S * (CH + 70)), (255, 255, 255))
d = ImageDraw.Draw(img)

def panel(i):
    x0 = S * (20 + i * (CW + 20))
    d.rounded_rectangle((x0, S * 20, x0 + S * CW, S * (20 + CH)), radius=S * 10, fill=G)
    return x0, S * 20

def nameStrip(x0, y0):   # the name strip below, for context
    sx, sy, w, h = x0 + S * 60, y0 + S * 170, S * 240, S * 32
    d.polygon([(sx + S*10 + S*5, sy + S*5), (sx + w + S*5, sy + S*5), (sx + w - S*10 + S*5, sy + h + S*5), (sx + S*5, sy + h + S*5)], fill=Y)
    d.polygon([(sx + S*10, sy), (sx + w, sy), (sx + w - S*10, sy + h), (sx, sy + h)], fill=W, outline=INK, width=S*2)
    d.text((sx + w / 2, sy + h / 2), "Abdelrahman Adel", font=f("seguibli.ttf", 14), fill=INK, anchor="mm")

def caption(x0, t):
    d.text((x0 + S * CW / 2, S * (CH + 45)), t, font=cap, fill=INK, anchor="mm")

# A: car number plate - yellow licence plate, ink border, bolts, dark side band
x0, y0 = panel(0)
px, py, pw, ph = x0 + S*55, y0 + S*40, S*250, S*100
d.rounded_rectangle((px + S*6, py + S*6, px + pw + S*6, py + ph + S*6), radius=S*14, fill=INK)
d.rounded_rectangle((px, py, px + pw, py + ph), radius=S*14, fill=Y, outline=INK, width=S*5)
d.rounded_rectangle((px + S*9, py + S*9, px + pw - S*9, py + ph - S*9), radius=S*8, outline=INK, width=S*2)
d.rectangle((px + S*9, py + S*9, px + S*58, py + ph - S*9), fill=INK)
for k, t in enumerate(("G.", "NO.")):
    d.text((px + S*33, py + S*(38 + k*24)), t, font=small, fill=Y, anchor="mm")
d.text((px + S*155, py + ph / 2 + S*2), "12328", font=big, fill=INK, anchor="mm")
for bx in (px + S*85, px + pw - S*22):
    d.ellipse((bx - S*4, py + S*16, bx + S*4, py + S*24), fill=W, outline=INK, width=S*2)
nameStrip(x0, y0); caption(x0, "A  Car number plate")

# B: race door number - white rounded board, thick ink ring, yellow top tab
x0, y0 = panel(1)
cx, cy = x0 + S*CW/2, y0 + S*92
bw, bh = S*190, S*104
d.rounded_rectangle((cx - bw/2 + S*7, cy - bh/2 + S*7, cx + bw/2 + S*7, cy + bh/2 + S*7), radius=S*52, fill=Y)
d.rounded_rectangle((cx - bw/2, cy - bh/2, cx + bw/2, cy + bh/2), radius=S*52, fill=W, outline=INK, width=S*7)
d.text((cx, cy + S*8), "12328", font=big, fill=INK, anchor="mm")
tw = S*86
d.rounded_rectangle((cx - tw/2, cy - bh/2 - S*14, cx + tw/2, cy - bh/2 + S*14), radius=S*14, fill=INK)
d.text((cx, cy - bh/2), "G.NO.", font=small, fill=Y, anchor="mm")
nameStrip(x0, y0); caption(x0, "B  Race door number")

# C: starting-grid slot - number on the floor inside a grid box with yellow corner marks
x0, y0 = panel(2)
gx, gy, gw, gh = x0 + S*70, y0 + S*30, S*220, S*118
d.rectangle((gx, gy, gx + gw, gy + gh), fill=(214, 217, 219))
L, T = S*30, S*7
for (ax, ay, sx, sy) in ((gx, gy, 1, 1), (gx + gw, gy, -1, 1), (gx, gy + gh, 1, -1), (gx + gw, gy + gh, -1, -1)):
    d.rectangle(sorted([ax, ax + sx*L]) [0:1] + [min(ay, ay + sy*T)] + [max(ax, ax + sx*L)] + [max(ay, ay + sy*T)], fill=Y)
    d.rectangle((min(ax, ax + sx*T), min(ay, ay + sy*L), max(ax, ax + sx*T), max(ay, ay + sy*L)), fill=Y)
d.text((gx + gw/2, gy + S*28), "G.NO.", font=small, fill=INK, anchor="mm")
d.text((gx + gw/2, gy + S*74), "12328", font=big, fill=INK, anchor="mm")
sq = S*9
for k in range(int(gw // sq)):
    for r in range(2):
        if (k + r) % 2 == 0:
            d.rectangle((gx + k*sq, gy + gh + S*6 + r*sq, gx + (k+1)*sq, gy + gh + S*6 + (r+1)*sq), fill=INK)
nameStrip(x0, y0 + S*8); caption(x0, "C  Starting-grid box")

img.resize((img.width // S, img.height // S), Image.LANCZOS).save(OUT / "plate-ideas.png")
print("ok")
