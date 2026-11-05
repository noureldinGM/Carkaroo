r"""Sketch sheet: 4 ideas for the column strip behind the poster boxes (Edition 2, page 3).

Run:  .venv\Scripts\python design\print\make_column_ideas.py   ->  column-ideas.png
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
INK, SIG, WHITE, ROO, CHROME, FOG = (18, 19, 20), (246, 194, 28), (255, 255, 255), (42, 45, 49), (139, 144, 150), (236, 238, 238)
SS = 2
CW, CH = 560, 1180          # one column mock-up
GAPX, TOP = 50, 160

def bahn(size, var=b"Bold Condensed"):
    f = ImageFont.truetype(r"C:\Windows\Fonts\bahnschrift.ttf", int(size * SS)); f.set_variation_by_name(var); return f
def seg(size, name="seguisb.ttf"):
    return ImageFont.truetype(rf"C:\Windows\Fonts\{name}", int(size * SS))

W = GAPX + 4 * (CW + GAPX)
H = TOP + CH + 140
img = Image.new("RGB", (W * SS, H * SS), FOG)
bg = Image.open(OUT / "workshop-floor.jpg").convert("RGB").resize((W * SS, H * SS))
img.paste(bg)
d = ImageDraw.Draw(img, "RGBA")
S = lambda v: v * SS
R = lambda x0, y0, x1, y1: [S(x0), S(y0), S(x1), S(y1)]

def box(x, y, w, h, title):
    d.rounded_rectangle(R(x, y + 8, x + w, y + h + 8), S(26), fill=SIG)
    d.rounded_rectangle(R(x, y, x + w, y + h), S(26), fill=WHITE, outline=INK, width=S(6))
    for dy, ln, c in ((20, 22, INK), (27, 31, SIG), (34, 17, INK)):
        d.rounded_rectangle(R(x + 30 + (31 - ln) / 2, y + dy, x + 30 + (31 - ln) / 2 + ln, y + dy + 4), S(2), fill=c)
    d.text((S(x + 72), S(y + 18)), title, font=bahn(30, b"Bold"), fill=INK)
    ty = y + 66
    while ty < y + h - 26:
        d.rounded_rectangle(R(x + 30, ty, x + w - 30 - (60 if (ty // 18) % 4 == 3 else 0), ty + 6), S(3), fill=(205, 208, 210))
        ty += 18

BOXES = [("CONCLUSIONS", 270), ("RECOMMENDATION", 250), ("LITERATURE CITED", 230), ("ACKNOWLEDGMENT", 140)]
def layout(x0, pad_l, pad_r, gap=44, top=TOP + 30):
    out, y = [], top
    for t, h in BOXES:
        out.append((x0 + pad_l, y, CW - pad_l - pad_r, h, t)); y += h + 8 + gap
    return out

def label(x0, letter, name, line):
    d.text((S(x0), S(40)), letter, font=bahn(64), fill=INK)
    d.text((S(x0 + 58), S(46)), name, font=bahn(34, b"Bold"), fill=INK)
    for k, part in enumerate(line.split("|")):
        d.text((S(x0 + 58), S(86 + k * 24)), part.strip(), font=seg(19), fill=(60, 63, 66))

def kerb_v(x, y0, y1, w=14, blk=22):
    y, i = y0, 0
    while y < y1:
        d.rectangle(R(x, y, x + w, min(y + blk, y1)), fill=SIG if i % 2 == 0 else WHITE); y += blk; i += 1

# ---- A: race lane -------------------------------------------------------------
x0 = GAPX
label(x0, "A", "RACE LANE", "Asphalt lane, yellow/white kerbs on both edges | dashed centre line, checkered finish at the foot")
d.rounded_rectangle(R(x0, TOP, x0 + CW, TOP + CH), S(34), fill=ROO)
kerb_v(x0 + 10, TOP + 30, TOP + CH - 60); kerb_v(x0 + CW - 24, TOP + 30, TOP + CH - 60)
cx = x0 + CW / 2
y = TOP + 10
while y < TOP + CH - 70:
    d.rounded_rectangle(R(cx - 4, y, cx + 4, y + 26), S(4), fill=WHITE); y += 52
for (bx, by, bw, bh, t) in layout(x0, 40, 40): box(bx, by, bw, bh, t)
for r in range(2):
    for i in range(int((CW - 80) / 16)):
        if (i + r) % 2 == 0:
            d.rectangle(R(x0 + 40 + i * 16, TOP + CH - 50 + r * 16, x0 + 56 + i * 16, TOP + CH - 34 + r * 16), fill=WHITE)

# ---- B: conveyor -----------------------------------------------------------------
x0 = GAPX + (CW + GAPX)
label(x0, "B", "CONVEYOR", "Mid-grey belt between chrome rollers | each section rides down like a crate")
d.rounded_rectangle(R(x0, TOP, x0 + CW, TOP + CH), S(34), fill=(88, 93, 99))
for xr in (x0 + 4, x0 + CW - 30):
    d.rounded_rectangle(R(xr, TOP + 8, xr + 26, TOP + CH - 8), S(13), fill=INK)
    y = TOP + 26
    while y < TOP + CH - 26:
        d.ellipse(R(xr + 4, y - 9, xr + 22, y + 9), fill=CHROME, outline=(200, 204, 207), width=S(2))
        d.ellipse(R(xr + 10, y - 3, xr + 16, y + 3), fill=SIG); y += 40
y = TOP + 20
while y < TOP + CH - 20:
    d.line([S(x0 + 34), S(y), S(x0 + CW - 34), S(y)], fill=(104, 109, 115), width=S(3)); y += 22
for (bx, by, bw, bh, t) in layout(x0, 44, 44): box(bx, by, bw, bh, t)
for (bx, by, bw, bh, t) in layout(x0, 44, 44)[:-1]:     # little down arrows between crates
    ay = by + bh + 8 + 22; ax = x0 + CW / 2
    d.polygon([(S(ax - 16), S(ay - 8)), (S(ax + 16), S(ay - 8)), (S(ax), S(ay + 10))], fill=SIG)

# ---- C: route map ----------------------------------------------------------------
x0 = GAPX + 2 * (CW + GAPX)
label(x0, "C", "ROUTE MAP", "No dark strip at all: Roo's route runs down | the side, with a numbered stop per section")
lx = x0 + 34
items = layout(x0, 78, 0)
d.rounded_rectangle(R(lx - 9, TOP + 40, lx + 9, items[-1][1] + 40), S(9), fill=INK)
d.rounded_rectangle(R(lx - 5, TOP + 40, lx + 5, items[-1][1] + 40), S(5), fill=SIG)
y = TOP + 48
while y < items[-1][1] + 34:
    d.rectangle(R(lx - 1.5, y, lx + 1.5, y + 10), fill=INK); y += 22
for i, (bx, by, bw, bh, t) in enumerate(items, 1):
    box(bx, by, bw, bh, t)
    py = by + 36
    d.line([S(lx), S(py), S(bx), S(py)], fill=INK, width=S(6))
    d.ellipse(R(lx - 26, py - 26, lx + 26, py + 26), fill=WHITE, outline=INK, width=S(6))
    d.text((S(lx), S(py + 1)), f"{i:02d}", font=bahn(26), fill=INK, anchor="mm")
# Roo at the start (simple wheel car mark)
d.rounded_rectangle(R(lx - 28, TOP - 4, lx + 34, TOP + 26), S(10), fill=SIG, outline=INK, width=S(5))
for wx in (lx - 14, lx + 20):
    d.ellipse(R(wx - 9, TOP + 18, wx + 9, TOP + 36), fill=INK)

# ---- D: AGV floor lane -----------------------------------------------------------
x0 = GAPX + 3 * (CW + GAPX)
label(x0, "D", "AGV FLOOR LANE", "Light concrete lane, hazard-tape edges | and floor arrows, like a real AGV factory")
d.rounded_rectangle(R(x0, TOP, x0 + CW, TOP + CH), S(34), fill=(214, 217, 219))
tape = Image.new("RGBA", (S(22), S(CH - 40)), SIG + (255,))
td = ImageDraw.Draw(tape)
for k in range(-4, CH // 14 + 4):
    yy = S(k * 28)
    td.polygon([(0, yy), (S(22), yy - S(22)), (S(22), yy - S(8)), (0, yy + S(14))], fill=INK)
for xt in (x0 + 10, x0 + CW - 32):
    img.paste(tape, (S(xt), S(TOP + 20)), tape)
items = layout(x0, 46, 46)
for (bx, by, bw, bh, t) in items: box(bx, by, bw, bh, t)
for (bx, by, bw, bh, t) in items[:-1]:
    ay = by + bh + 8 + 8; ax = x0 + CW / 2
    for k in range(2):
        yy = ay + k * 14
        d.line([(S(ax - 22), S(yy)), (S(ax), S(yy + 14)), (S(ax + 22), S(yy))], fill=WHITE, width=S(6))
d.text((S(x0 + CW / 2), S(TOP + CH - 40)), "AGV LANE", font=bahn(28), fill=(150, 154, 158), anchor="mm")

d.text((S(GAPX), S(H - 70)), "Each sketch is one poster column (Conclusions → Acknowledgment). Boxes get wider and gaps get even in every option.",
       font=seg(22), fill=INK)
img.resize((W, H), Image.LANCZOS).save(OUT / "column-ideas.png", optimize=True)
print("saved", W, H)
