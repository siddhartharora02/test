"""Ceiling lighting idea (reflected ceiling plan) for FIRST-floor bed room-1 (SW room, 16'-3" x 12').

Simple SVG drawing -> HTML; screenshot it with Playwright. No Blender.
    python3 ideas/first_bedroom1_ceiling_lights.py /path/out.html

Orientation matches the architect's sheet: left = south, right = north, top = west, bottom = east.
x = feet from the south wall (0..16.25), y = feet from the west wall (0..12).
Layout from the site photos: bed headboard on the EAST wall, door+window (DW1) on the south wall near
the east corner, cupboard/study unit on the south wall near the west corner, entrance D1 at the NE.
False ceiling: ~2' perimeter band, rounded tray in the middle with a cove groove, fan point at centre.
"""
import math
import sys

OUT = sys.argv[1]
S = 44
OX, OY = 160, 250
L, W = 16.25, 12.0
T = 0.4
BAND = 2.0                                  # perimeter band width (assumed from photos)
TRAY = (BAND, BAND, L - BAND, W - BAND)     # x0, y0, x1, y1
TRAY_R = 1.5
FAN = (L / 2, W / 2)

def X(x): return OX + x * S
def Y(y): return OY + y * S

parts = []
add = parts.append

DL = [("DL1", 5.0, 3.25), ("DL2", 11.25, 3.25), ("DL3", 11.25, 8.75)]
COB = [("C1", 2.25, 11.0), ("C2", 9.75, 11.0),      # headboard wall, beside the bed
       ("C3", 1.5, 1.5), ("C4", 1.5, 4.25),         # cupboard / study unit
       ("C5", 3.5, 1.0), ("C6", 8.5, 1.0)]          # TV wall, either side of the TV

def rrect(x0, y0, x1, y1, r, **kw):
    a = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in kw.items())
    add(f'<rect x="{X(x0)}" y="{Y(y0)}" width="{(x1-x0)*S}" height="{(y1-y0)*S}" rx="{r*S}" {a}/>')

# ---- ceiling surfaces ----
rrect(0, 0, L, W, 0, fill="#ece7df")                                   # lower perimeter band
tx0, ty0, tx1, ty1 = TRAY
rrect(tx0, ty0, tx1, ty1, TRAY_R, fill="#fbf8f2", stroke="#b9b0a2", stroke_width=2)   # tray (higher)
rrect(tx0 + .6, ty0 + .6, tx1 - .6, ty1 - .6, TRAY_R - .5, fill="none", stroke="#cfc7ba", stroke_width=1.5)
# cove glow along the tray edge
rrect(tx0 + .25, ty0 + .25, tx1 - .25, ty1 - .25, TRAY_R - .2, fill="none", stroke="#ffb347",
      stroke_width=14, opacity=.28, filter="url(#blur)")
rrect(tx0 + .25, ty0 + .25, tx1 - .25, ty1 - .25, TRAY_R - .2, fill="none", stroke="#f08a00",
      stroke_width=3, stroke_dasharray="10 5")

# light pools
def pool(x, y, r, g, op):
    add(f'<circle cx="{X(x)}" cy="{Y(y)}" r="{r*S}" fill="url(#{g})" opacity="{op}" clip-path="url(#room)"/>')
for _, x, y in DL:
    pool(x, y, 4.0, "g_warm", .6)
for _, x, y in COB:
    pool(x, y, 1.9, "g_cob", .75)

# ---- furniture (dashed, on the floor below, for reference) ----
def furn(x0, y0, x1, y1, label="", fs=13, rot=False):
    add(f'<rect x="{X(x0)}" y="{Y(y0)}" width="{(x1-x0)*S}" height="{(y1-y0)*S}" fill="none" '
        f'stroke="#9a8f80" stroke-width="1.5" stroke-dasharray="6 4" rx="3"/>')
    if label:
        cx, cy = X((x0+x1)/2), Y((y0+y1)/2) + 4
        tr = f' transform="rotate(-90 {cx} {cy-4})"' if rot else ""
        add(f'<text x="{cx}" y="{cy}" class="furn" font-size="{fs}"{tr}>{label}</text>')

furn(3.0, 5.3, 9.0, 12.0)                         # king bed, headboard on east wall
furn(3.0, 11.6, 9.0, 12.0)                        # headboard
furn(3.4, 10.0, 5.8, 11.4); furn(6.2, 10.0, 8.6, 11.4)   # pillows
add(f'<text x="{X(6.0)}" y="{Y(7.6)}" class="furn">BED</text>')
furn(9.3, 10.4, 10.8, 11.9)
furn(0.0, 0.3, 2.0, 5.6, "CUPBOARD / STUDY", 12, rot=True)
furn(4.0, 0.0, 8.0, 1.3, "TV unit", 12)

# fan
fx, fy = FAN
add(f'<circle cx="{X(fx)}" cy="{Y(fy)}" r="{2*S}" fill="none" stroke="#7a8794" stroke-width="1.5" stroke-dasharray="4 4"/>')
for k in range(3):
    a = math.radians(90 + k * 120)
    add(f'<line x1="{X(fx)}" y1="{Y(fy)}" x2="{X(fx)+math.cos(a)*1.9*S}" y2="{Y(fy)+math.sin(a)*1.9*S}" stroke="#7a8794" stroke-width="7" stroke-linecap="round" opacity=".55"/>')
add(f'<circle cx="{X(fx)}" cy="{Y(fy)}" r="9" fill="#7a8794"/>')
add(f'<text x="{X(fx)+2.15*S}" y="{Y(fy)-6}" class="fan">FAN (existing centre point)</text>')

# ---- walls & openings ----
wall = "#4a4a4a"
def hwall(x0, x1, y, out):
    yy = y if out > 0 else y - T
    add(f'<rect x="{X(x0)}" y="{Y(yy)}" width="{(x1-x0)*S}" height="{T*S}" fill="{wall}"/>')
def vwall(y0, y1, x, out):
    xx = x if out > 0 else x - T
    add(f'<rect x="{X(xx)}" y="{Y(y0)}" width="{T*S}" height="{(y1-y0)*S}" fill="{wall}"/>')
def glass_v(y0, y1, x, color="#bfe9f5"):
    add(f'<rect x="{X(x - T)}" y="{Y(y0)}" width="{T*S}" height="{(y1-y0)*S}" fill="{color}" stroke="#3aa6c9" stroke-width="2"/>')

hwall(-T, 10.1, 0, -1); hwall(12.65, 13.4, 0, -1); hwall(16.2, L + T, 0, -1)       # west wall
hwall(-T, 11.5, W, 1); hwall(16.0, L + T, W, 1)                                   # east wall
add(f'<rect x="{X(11.5)}" y="{Y(W)}" width="{1.3*S}" height="{0.75*S}" fill="#d22"/>')
vwall(-T, 5.9, 0, -1); vwall(11.8, W + T, 0, -1)                                  # south wall
glass_v(5.9, 8.8, 0); glass_v(8.8, 11.8, 0, "#e3f6fb")                            # DW1 window + door
vwall(-T, W + T, L, 1)                                                            # north wall

def lab(x, y, txt, rot=0, cls="door"):
    tr = f' transform="rotate({rot} {X(x)} {Y(y)})"' if rot else ""
    add(f'<text x="{X(x)}" y="{Y(y)}" class="{cls}"{tr}>{txt}</text>')
lab(5.0, -0.75, "WEST wall · TV wall")
lab(11.4, -0.75, "D3 → dress")
lab(14.8, -0.75, "D2 → open")
lab(5.5, W + 1.0, "EAST wall · bed headboard")
lab(14.4, W + 1.0, "D1 entrance (NE)")
lab(-0.95, 7.35, "window", -90); lab(-0.95, 10.3, "door", -90)
lab(-1.65, 8.85, "SOUTH wall — DW1 (SE) → terrace", -90)
lab(L + 1.0, 6.0, "NORTH wall (to room)", 90)

# ---- fixtures ----
for n, x, y in DL:
    cx, cy = X(x), Y(y)
    add(f'<circle cx="{cx}" cy="{cy}" r="15" fill="#fff" stroke="#222" stroke-width="2.5"/>'
        f'<circle cx="{cx}" cy="{cy}" r="8" fill="#ffd36b" stroke="#222" stroke-width="1.5"/>'
        f'<text x="{cx}" y="{cy-22}" class="tag">{n}</text>')
for n, x, y in COB:
    cx, cy = X(x), Y(y)
    add(f'<rect x="{cx-10}" y="{cy-10}" width="20" height="20" fill="#fff" stroke="#b5400c" stroke-width="2.5" rx="3"/>'
        f'<circle cx="{cx}" cy="{cy}" r="5" fill="#ff8a3d"/>'
        f'<text x="{cx}" y="{cy-16}" class="tag cobtag">{n}</text>')
add(f'<text x="{X(L/2)}" y="{Y(ty0+0.25)-8}" class="cove">COVE LED strip — all round the tray (≈12 m)</text>')
add(f'<text x="{X(L-1.0)}" y="{Y(6.0)}" class="band" transform="rotate(90 {X(L-1.0)} {Y(6.0)})">2\' lower band</text>')

# ---- dimension chains ----
def ftin(v):
    f, i = divmod(round(v * 12), 12)
    return f"{f}'-{i}\""
def dim_h(xs, y, lbl, off=-8):
    yy = Y(y)
    add(f'<line x1="{X(xs[0])}" y1="{yy}" x2="{X(xs[-1])}" y2="{yy}" class="dim"/>')
    for a in xs:
        add(f'<line x1="{X(a)}" y1="{yy-6}" x2="{X(a)}" y2="{yy+6}" class="dim"/>')
    for a, b in zip(xs, xs[1:]):
        add(f'<text x="{(X(a)+X(b))/2}" y="{yy+off}" class="dimt">{ftin(b-a)}</text>')
    add(f'<text x="{X(-0.3)}" y="{yy+4}" class="dimlab" text-anchor="end">{lbl}</text>')
def dim_v(ys, x, lbl):
    xx = X(x)
    add(f'<line x1="{xx}" y1="{Y(ys[0])}" x2="{xx}" y2="{Y(ys[-1])}" class="dim"/>')
    for a in ys:
        add(f'<line x1="{xx-6}" y1="{Y(a)}" x2="{xx+6}" y2="{Y(a)}" class="dim"/>')
    for a, b in zip(ys, ys[1:]):
        add(f'<text x="{xx+10}" y="{(Y(a)+Y(b))/2+4}" class="dimt" text-anchor="start">{ftin(b-a)}</text>')
    add(f'<text x="{xx}" y="{Y(ys[0])-12}" class="dimlab">{lbl}</text>')

dim_h([0, 1.5, 3.5, 8.5, L], -2.0, "COB C3–C6")
dim_h([0, 5.0, 11.25, L], -3.1, "downlights")
dim_h([0, 2.25, 9.75, L], W + 2.0, "COB C1–C2", 18)
dim_v([0, 1.0, 1.5, 3.25, 4.25, 8.75, 11.0, W], L + 2.3, "from west wall")

add(f'<text x="{X(L/2)}" y="{Y(-4.6)}" class="title">First floor bed room-1 (SW) — ceiling lighting idea</text>')
add(f'<text x="{X(L/2)}" y="{Y(-4.0)+6}" class="sub">16\'-3" × 12\'-0" · view looking UP at the ceiling · furniture dashed (from site photos) · band / tray sizes approx.</text>')

# ---- legend ----
lx, ly = X(0), Y(W + 3.4)
leg = [
    ("dl", "Downlight ×3 — 12 W, 3000 K (or 3-in-1), wide beam · all ≥ 3'-0\" from the fan, none over the bed  →  36 W"),
    ("cob", "COB spot ×6 — 7 W, 3000 K, 24–36°, anti-glare, tiltable · C1–C2 headboard · C3–C4 cupboard · C5–C6 TV wall  →  42 W"),
    ("cove", "Cove strip ≈12 m in the tray groove — 3000 K, 8–10 W/m, with dimmer + 150 W driver  →  ≈ 100–120 W"),
    ("txt", "Total if everything is ON ≈ 180–200 W · night mode = cove only (dimmed) or C1–C2 only"),
    ("txt", "Switching: 1) downlights (door + bedside 2-way)  2) cove (bedside, dimmer)  3) C1–C2 (bedside)  4) C3–C6 (door)  + fan"),
]
for i, (k, t) in enumerate(leg):
    yy = ly + i * 30
    if k == "dl":
        add(f'<circle cx="{lx+12}" cy="{yy}" r="12" fill="#fff" stroke="#222" stroke-width="2.5"/><circle cx="{lx+12}" cy="{yy}" r="6" fill="#ffd36b" stroke="#222" stroke-width="1.5"/>')
    elif k == "cob":
        add(f'<rect x="{lx+3}" y="{yy-9}" width="18" height="18" fill="#fff" stroke="#b5400c" stroke-width="2.5" rx="3"/><circle cx="{lx+12}" cy="{yy}" r="4.5" fill="#ff8a3d"/>')
    elif k == "cove":
        add(f'<line x1="{lx}" y1="{yy}" x2="{lx+24}" y2="{yy}" stroke="#f08a00" stroke-width="3" stroke-dasharray="7 4"/>')
    else:
        add(f'<text x="{lx+12}" y="{yy+5}" class="leg" text-anchor="middle">•</text>')
    add(f'<text x="{lx+34}" y="{yy+5}" class="leg">{t}</text>')

w_px = int(X(L) + 3.8 * S + 40)
h_px = int(ly + len(leg) * 30 + 20)
svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w_px}" height="{h_px}" viewBox="0 0 {w_px} {h_px}">
<defs>
 <clipPath id="room"><rect x="{X(0)}" y="{Y(0)}" width="{L*S}" height="{W*S}"/></clipPath>
 <radialGradient id="g_warm"><stop offset="0" stop-color="#ffe2a8"/><stop offset="1" stop-color="#ffe2a8" stop-opacity="0"/></radialGradient>
 <radialGradient id="g_cob"><stop offset="0" stop-color="#ffb070"/><stop offset="1" stop-color="#ffb070" stop-opacity="0"/></radialGradient>
 <filter id="blur"><feGaussianBlur stdDeviation="6"/></filter>
</defs>
<style>
 text{{font-family:Inter,Helvetica,Arial,sans-serif;fill:#222}}
 .furn{{fill:#8a7f70;font-size:13px;text-anchor:middle;letter-spacing:.5px}}
 .door{{fill:#555;font-size:13px;text-anchor:middle}}
 .tag{{font-size:13px;font-weight:700;text-anchor:middle}}
 .cobtag{{fill:#b5400c}}
 .cove{{fill:#c06a00;font-size:13px;font-weight:700;text-anchor:middle}}
 .band{{fill:#9a9184;font-size:11px;text-anchor:middle;font-style:italic}}
 .fan{{fill:#5c6873;font-size:12px}}
 .dim{{stroke:#2a8a3a;stroke-width:1.3}}
 .dimt{{fill:#2a8a3a;font-size:12.5px;text-anchor:middle}}
 .dimlab{{fill:#2a8a3a;font-size:12px;font-style:italic}}
 .title{{font-size:22px;font-weight:700;text-anchor:middle}}
 .sub{{font-size:13px;fill:#555;text-anchor:middle}}
 .leg{{font-size:14px}}
</style>
<rect width="100%" height="100%" fill="#fff"/>
{"".join(parts)}
</svg>'''
open(OUT, "w").write(f'<!doctype html><html><body style="margin:0;background:#fff">{svg}</body></html>')
print(w_px, h_px)
