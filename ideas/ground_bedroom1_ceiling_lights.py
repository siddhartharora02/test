"""Reflected ceiling plan (lighting idea) for ground-floor bed room-1 (SW room).

Orientation matches the architect's sheet: left = south, right = north, top = west, bottom = east.
x = feet from the south wall (0..16.25), y = feet from the west wall (0..12).
"""
import sys

OUT = sys.argv[1]
S = 44            # px per foot
OX, OY = 150, 260 # room origin (inner SW corner) in px
L, W = 16.25, 12.0
T = 0.4           # drawn wall thickness (ft)

def X(x): return OX + x * S
def Y(y): return OY + y * S

parts = []
add = parts.append

# ---- soft light pools (the "mockup" feel) ----
def pool(x, y, r, color, op):
    add(f'<circle cx="{X(x)}" cy="{Y(y)}" r="{r*S}" fill="url(#g_{color})" opacity="{op}" clip-path="url(#room)"/>')

DL = [("DL1", 3.5, 8.75), ("DL2", 8.0, 8.75), ("DL3", 12.75, 8.75), ("DL4", 12.75, 3.25)]
COB = [("C1", 1.25, 1.0, "over side table"), ("C2", 9.25, 1.0, "over side table"),
       ("C3", 13.75, 6.0, "person at the dresser / mirror")]
# Nothing over the wardrobe: DL1-DL2 at 8'-9" are 1'-3" in front of its shutters and light them.

# floor
add(f'<rect x="{X(0)}" y="{Y(0)}" width="{L*S}" height="{W*S}" fill="#f6f1e8"/>')
for _, x, y in DL:
    pool(x, y, 4.2, "warm", 0.55)
for _, x, y, _d in COB:
    pool(x, y, 2.0, "cob", 0.75)

# ---- furniture (dashed, for reference only) ----
def furn(x0, y0, x1, y1, label, fs=13):
    add(f'<rect x="{X(x0)}" y="{Y(y0)}" width="{(x1-x0)*S}" height="{(y1-y0)*S}" fill="none" '
        f'stroke="#9a8f80" stroke-width="1.5" stroke-dasharray="6 4" rx="3"/>')
    if label:
        add(f'<text x="{X((x0+x1)/2)}" y="{Y((y0+y1)/2)+4}" class="furn" font-size="{fs}">{label}</text>')

furn(2.25, 0.0, 8.25, 6.8, "")                       # king bed 6' x 6'-6" + headboard
add(f'<text x="{X(5.25)}" y="{Y(4.6)}" class="furn">BED 6\'x6\'-6"</text>')
furn(2.25, 0.0, 8.25, 0.35, "")                      # headboard
furn(2.7, 0.55, 4.95, 1.9, "")                       # pillows
furn(5.55, 0.55, 7.8, 1.9, "")
furn(0.5, 0.2, 2.0, 1.7, "side", 11)
furn(8.5, 0.2, 10.0, 1.7, "side", 11)
furn(3.0, 10.0, 10.5, 12.0, "")
add(f'<text x="{X(6.75)}" y="{Y(11.65)}" class="furn">WARDROBE (2\' deep)</text>')
furn(14.75, 4.0, 16.25, 8.0, "")
add(f'<text x="{X(15.5)}" y="{Y(6.0)}" class="furn" transform="rotate(-90 {X(15.5)} {Y(6.0)})">DRESSER</text>')

# ---- walls with openings ----
wall = "#4a4a4a"
def hwall(x0, x1, y, outward):  # horizontal wall segment along y, thickness outward (-1 top, +1 bottom)
    yy = y if outward > 0 else y - T
    add(f'<rect x="{X(x0)}" y="{Y(yy)}" width="{(x1-x0)*S}" height="{T*S}" fill="{wall}"/>')
def vwall(y0, y1, x, outward):
    xx = x if outward > 0 else x - T
    add(f'<rect x="{X(xx)}" y="{Y(y0)}" width="{T*S}" height="{(y1-y0)*S}" fill="{wall}"/>')

# west wall (top): D3 toilet 10.0-12.4, D2 13.3-16.1
hwall(-T, 10.0, 0, -1); hwall(12.4, 13.3, 0, -1); hwall(16.1, L + T, 0, -1)
# east wall (bottom): column 11.4-12.8, D1 12.8-16.0
hwall(-T, 11.4, W, 1); hwall(16.0, L + T, W, 1)
add(f'<rect x="{X(11.4)}" y="{Y(W)}" width="{1.4*S}" height="{0.75*S}" fill="#d22"/>')
# south wall (left): window W2 at 8.5-12.0
vwall(-T, 8.5, 0, -1)
add(f'<rect x="{X(-T)}" y="{Y(8.5)}" width="{T*S}" height="{3.5*S}" fill="#bfe9f5" stroke="#3aa6c9" stroke-width="2"/>')
# north wall (right): solid partition to bed room-2
vwall(-T, W + T, L, 1)

def door_label(x, y, txt, anchor="middle"):
    add(f'<text x="{X(x)}" y="{Y(y)}" class="door" text-anchor="{anchor}">{txt}</text>')
door_label(11.2, -0.75, "D3 → toilet")
door_label(14.7, -0.75, "D2 → open / wash area")
door_label(14.4, W + 1.0, "D1 → lobby (main door)")
add(f'<text x="{X(-0.95)}" y="{Y(10.25)}" class="door" transform="rotate(-90 {X(-0.95)} {Y(10.25)})">W2 window</text>')
add(f'<text x="{X(L+1.0)}" y="{Y(6)}" class="door" transform="rotate(90 {X(L+1.0)} {Y(6)})">wall to bed room-2</text>')
add(f'<text x="{X(-0.95)}" y="{Y(4.0)}" class="door" transform="rotate(-90 {X(-0.95)} {Y(4.0)})">SOUTH wall</text>')
door_label(4.5, -0.75, "WEST wall (toilet side)")
door_label(5.5, W + 1.0, "EAST wall (lobby side)")

# ---- fixtures ----
def downlight(name, x, y):
    cx, cy = X(x), Y(y)
    add(f'<circle cx="{cx}" cy="{cy}" r="15" fill="#fff" stroke="#222" stroke-width="2.5"/>')
    add(f'<circle cx="{cx}" cy="{cy}" r="8" fill="#ffd36b" stroke="#222" stroke-width="1.5"/>')
    add(f'<text x="{cx}" y="{cy-22}" class="tag">{name}</text>')
def cob(name, x, y):
    cx, cy = X(x), Y(y)
    add(f'<rect x="{cx-10}" y="{cy-10}" width="20" height="20" fill="#fff" stroke="#b5400c" stroke-width="2.5" rx="3"/>')
    add(f'<circle cx="{cx}" cy="{cy}" r="5" fill="#ff8a3d"/>')
    add(f'<text x="{cx}" y="{cy-17}" class="tag cobtag">{name}</text>')

for n, x, y in DL:
    downlight(n, x, y)
for n, x, y, _d in COB:
    cob(n, x, y)

# ---- dimension chains (from inside wall faces) ----
def dim_h(xs, y, label_y_off=-8):
    yy = Y(y)
    add(f'<line x1="{X(xs[0])}" y1="{yy}" x2="{X(xs[-1])}" y2="{yy}" class="dim"/>')
    for a in xs:
        add(f'<line x1="{X(a)}" y1="{yy-6}" x2="{X(a)}" y2="{yy+6}" class="dim"/>')
    for a, b in zip(xs, xs[1:]):
        add(f'<text x="{(X(a)+X(b))/2}" y="{yy+label_y_off}" class="dimt">{ftin(b-a)}</text>')
def dim_v(ys, x):
    xx = X(x)
    add(f'<line x1="{xx}" y1="{Y(ys[0])}" x2="{xx}" y2="{Y(ys[-1])}" class="dim"/>')
    for a in ys:
        add(f'<line x1="{xx-6}" y1="{Y(a)}" x2="{xx+6}" y2="{Y(a)}" class="dim"/>')
    for a, b in zip(ys, ys[1:]):
        my = (Y(a)+Y(b))/2
        add(f'<text x="{xx+10}" y="{my+4}" class="dimt" text-anchor="start">{ftin(b-a)}</text>')

def ftin(v):
    inches = round(v * 12)
    f, i = divmod(inches, 12)
    return f"{f}'-{i}\"" if i else f"{f}'-0\""

dim_h([0, 3.5, 8.0, 12.75, L], -2.1)            # downlight x positions (row y = 8'-9")
add(f'<text x="{X(-0.3)}" y="{Y(-2.1)+4}" class="dimlab" text-anchor="end">downlights</text>')
dim_h([0, 1.25, 9.25, L], -3.3)
add(f'<text x="{X(-0.3)}" y="{Y(-3.3)+4}" class="dimlab" text-anchor="end">COB C1–C2</text>')
dim_v([0, 1.0, 3.25, 6.0, 8.75, W], L + 2.3)
add(f'<text x="{X(L+2.3)}" y="{Y(-0.5)}" class="dimlab">from west wall</text>')

# overall
add(f'<text x="{X(L/2)}" y="{Y(-4.6)}" class="title">Bed room-1 (ground floor, SW) — ceiling lighting idea</text>')
add(f'<text x="{X(L/2)}" y="{Y(-4.0)+6}" class="sub">16\'-3" × 12\'-0", ceiling 10\'-0" · reflected ceiling plan · no cove light · furniture dashed = assumed layout</text>')

# ---- legend ----
dim_h([0, 13.75, L], W + 2.0, 18)
add(f'<text x="{X(-0.3)}" y="{Y(W+2.0)+4}" class="dimlab" text-anchor="end">COB C3</text>')
lx, ly = X(0), Y(W + 3.4)
leg = [
    ("dl", "Downlight ×4 — 12 W each (~1,100 lm), round recessed, 3000 K or 3-in-1 CCT  →  48 W"),
    ("cob", "COB spot ×3 — 7 W each (~550 lm), 3000 K, 24–36° beam, anti-glare, tiltable  →  21 W"),
    ("txt", "Cove light: none in this room.   TOTAL ≈ 69 W  (195 sq ft ≈ 0.35 W/sq ft, ~130 lux general light)"),
    ("txt", "18 W downlights instead: 4 × 18 W ≈ 190 lux = too bright for a bedroom (OK only with a dimmer)."),
    ("txt", "C1–C2 over the side tables · C3 in front of the dresser (lights your face) · nothing over the wardrobe or the pillows"),
    ("txt", "Switching: A = downlights (2-way, door + bedside) · B = C1–C2 (bedside) · C = C3 (door)"),
]
for i, (k, t) in enumerate(leg):
    yy = ly + i * 30
    if k == "dl":
        add(f'<circle cx="{lx+12}" cy="{yy}" r="12" fill="#fff" stroke="#222" stroke-width="2.5"/><circle cx="{lx+12}" cy="{yy}" r="6" fill="#ffd36b" stroke="#222" stroke-width="1.5"/>')
    elif k == "cob":
        add(f'<rect x="{lx+3}" y="{yy-9}" width="18" height="18" fill="#fff" stroke="#b5400c" stroke-width="2.5" rx="3"/><circle cx="{lx+12}" cy="{yy}" r="4.5" fill="#ff8a3d"/>')
    else:
        add(f'<text x="{lx+12}" y="{yy+5}" class="leg" text-anchor="middle">•</text>')
    add(f'<text x="{lx+34}" y="{yy+5}" class="leg">{t}</text>')

w_px = int(X(L) + 3.6 * S + 40)
h_px = int(ly + len(leg) * 30 + 20)
svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w_px}" height="{h_px}" viewBox="0 0 {w_px} {h_px}">
<defs>
 <clipPath id="room"><rect x="{X(0)}" y="{Y(0)}" width="{L*S}" height="{W*S}"/></clipPath>
 <radialGradient id="g_warm"><stop offset="0" stop-color="#ffe2a8"/><stop offset="1" stop-color="#ffe2a8" stop-opacity="0"/></radialGradient>
 <radialGradient id="g_cob"><stop offset="0" stop-color="#ffb070"/><stop offset="1" stop-color="#ffb070" stop-opacity="0"/></radialGradient>
</defs>
<style>
 text{{font-family:Inter,Helvetica,Arial,sans-serif;fill:#222}}
 .furn{{fill:#8a7f70;font-size:13px;text-anchor:middle;letter-spacing:.5px}}
 .door{{fill:#555;font-size:13px;text-anchor:middle}}
 .tag{{font-size:13px;font-weight:700;text-anchor:middle}}
 .cobtag{{fill:#b5400c}}
 .dim{{stroke:#2a8a3a;stroke-width:1.3}}
 .dimt{{fill:#2a8a3a;font-size:12.5px;text-anchor:middle}}
 .dimlab{{fill:#2a8a3a;font-size:12px;font-style:italic}}
 .title{{font-size:22px;font-weight:700;text-anchor:middle}}
 .sub{{font-size:13.5px;fill:#555;text-anchor:middle}}
 .leg{{font-size:14px}}
</style>
<rect width="100%" height="100%" fill="#fff"/>
{"".join(parts)}
</svg>'''
open(OUT, "w").write(f'<!doctype html><html><body style="margin:0;background:#fff">{svg}</body></html>')
print(w_px, h_px)
