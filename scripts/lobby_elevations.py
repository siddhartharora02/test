"""Quick 2D front elevations of the lobby TV-wall designs (no Blender, runs in seconds).

    python3 scripts/lobby_elevations.py        # -> renders/lobby/elevations/*.png

Draws the west wall of the ground-floor lobby to scale: SW corner at the left, the
12'-9" solid TV wall, then the walnut bedroom-1 door. Dimensions in feet (as in lobby_scene.py).
"""

import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "renders", "lobby", "elevations")

PX = 62  # pixels per foot
WALL_W = 17.25  # drawn width: TV wall (0..12.75) + door (12.75..16.25) + a bit of wall
WALL_H = 10.0
MX, MT, MB = 110, 140, 150  # margins: sides, top, bottom
TV_WALL = 12.75
TV_YC = TV_WALL / 2
DOOR = (12.75, 16.25)

C = dict(
    wall="#EEEAE3", ceiling="#E3DED6", floor="#E7E4DE", skirt="#D9D6CF", line="#3A3A3A", dim="#8A5A3C",
    oak="#B98A5A", oak_dark="#9C6F44", walnut="#6B4A33", walnut_dark="#553A28", greige="#CFC8BD",
    stone="#2B2B2D", tv="#111113", led="#FFD9A0", brass="#C9A25B", pot="#B86B4B", leaf="#5F7F45", white="#F7F5F0",
)


def font(size, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(os.path.join("/usr/share/fonts/truetype/dejavu", name), size)
    except OSError:
        return ImageFont.load_default()


def X(ft):
    return MX + ft * PX


def Z(ft):
    return MT + (WALL_H - ft) * PX


def rect(d, x0, z0, x1, z1, fill, outline=None, w=1):
    d.rectangle([X(x0), Z(z1), X(x1), Z(z0)], fill=fill, outline=outline, width=w)


def dim_h(d, x0, x1, z, label, above=True):
    y = Z(z)
    d.line([X(x0), y, X(x1), y], fill=C["dim"], width=2)
    for x in (x0, x1):
        d.line([X(x) - 6, y + 6, X(x) + 6, y - 6], fill=C["dim"], width=2)
    f = font(17)
    tw = d.textlength(label, font=f)
    d.text(((X(x0) + X(x1) - tw) / 2, y - 24 if above else y + 6), label, fill=C["dim"], font=f)


def dim_v(d, x, z0, z1, label):
    d.line([X(x), Z(z0), X(x), Z(z1)], fill=C["dim"], width=2)
    for z in (z0, z1):
        d.line([X(x) - 6, Z(z) + 6, X(x) + 6, Z(z) - 6], fill=C["dim"], width=2)
    d.text((X(x) + 8, (Z(z0) + Z(z1)) / 2 - 10), label, fill=C["dim"], font=font(17))


def ftin(v):
    f = int(v)
    i = round((v - f) * 12)
    if i == 12:
        f, i = f + 1, 0
    return f"{f}'-{i}\""


def glow(img, box, color, radius=40, strength=110):
    """Soft light wash (additive-looking) inside box=(x0,z0,x1,z1) in feet."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    r, g, b = Image.new("RGB", (1, 1), color).getpixel((0, 0))
    ld.rectangle([X(box[0]), Z(box[3]), X(box[2]), Z(box[1])], fill=(r, g, b, strength))
    layer = layer.filter(ImageFilter.GaussianBlur(radius))
    img.alpha_composite(layer)


def plant(d, xc, z0, h, pot_w=1.3, pot_h=1.2):
    x0, x1 = xc - pot_w / 2, xc + pot_w / 2
    d.polygon([(X(x0), Z(z0 + pot_h)), (X(x1), Z(z0 + pot_h)), (X(x1 - 0.15), Z(z0)), (X(x0 + 0.15), Z(z0))], fill=C["pot"])
    rnd = random.Random(int(xc * 100))
    for _ in range(38):
        a = rnd.uniform(0.15, math.pi - 0.15)
        rr = rnd.uniform(0.3, 1.0) * h
        cx = xc + math.cos(a) * rr * 0.45
        cz = z0 + pot_h + math.sin(a) * rr
        s = rnd.uniform(0.18, 0.32)
        d.ellipse([X(cx - s), Z(cz + s * 0.6), X(cx + s), Z(cz - s * 0.6)], fill=C["leaf"])


def vase(d, xc, z0, h, w, col):
    d.rounded_rectangle([X(xc - w / 2), Z(z0 + h), X(xc + w / 2), Z(z0)], radius=int(w * PX / 2.2), fill=col)


def books(d, xc, z0, n=3):
    cols = ["#3E5C6B", "#C9A25B", "#8C3D22", "#E4DDCF"]
    z = z0
    for k in range(n):
        w = 0.95 - 0.08 * k
        rect(d, xc - w / 2, z, xc + w / 2, z + 0.12, cols[k % len(cols)], outline=C["line"])
        z += 0.12
    return z


def tv(d, zc, xc=TV_YC):
    w, h = 4.73, 2.66  # 65" 16:9
    rect(d, xc - w / 2, zc - h / 2, xc + w / 2, zc + h / 2, C["tv"], outline="#000000", w=2)
    d.line([X(xc - w / 2 + 0.3), Z(zc + h / 2 - 0.25), X(xc - w / 2 + 1.4), Z(zc + h / 2 - 1.2)], fill="#2A2A2E", width=3)


def base(title, subtitle):
    img = Image.new("RGBA", (int(MX * 2 + WALL_W * PX), int(MT + WALL_H * PX + MB)), C["white"])
    d = ImageDraw.Draw(img)
    rect(d, 0, 0, WALL_W, WALL_H, C["wall"])
    rect(d, 0, WALL_H - 0.08, WALL_W, WALL_H, C["ceiling"])
    rect(d, 0, 0, WALL_W, 0.33, C["skirt"])
    # walnut door + frame
    a, b = DOOR
    rect(d, a - 0.25, 0, b + 0.25, 7.25, C["walnut_dark"])
    rect(d, a, 0, b, 7.0, C["walnut"])
    for k in range(1, 12):
        xx = a + k * (b - a) / 12
        d.line([X(xx), Z(6.9), X(xx), Z(0.1)], fill=C["walnut_dark"], width=1)
    rect(d, b - 0.45, 3.2, b - 0.2, 3.35, C["brass"])
    d.line([X(0), Z(0), X(WALL_W), Z(0)], fill=C["line"], width=3)
    d.line([X(0), Z(0), X(0), Z(WALL_H)], fill=C["line"], width=3)
    d.text((MX, 22), title, fill="#1F1F1F", font=font(30, bold=True))
    d.text((MX, 62), subtitle, fill="#555555", font=font(18))
    d.text((X(0) + 6, Z(WALL_H) + 8), "SW corner / south wall", fill="#777777", font=font(14))
    d.text((X(a) + 6, Z(7.25) - 22), "bedroom-1 door (walnut)", fill="#777777", font=font(14))
    dim_h(d, 0, TV_WALL, -1.3, f"TV wall {ftin(TV_WALL)}", above=False)
    dim_v(d, WALL_W - 0.35, 0, WALL_H, ftin(WALL_H))
    return img, d


def design_oak():
    img, d = base("1. Floating oak console", "Wall-hung oak console, clean painted wall, warm LED glow under the console")
    y0, y1 = TV_YC - 3.5, TV_YC + 3.5
    glow(img, (y0 + 0.2, 0.0, y1 - 0.2, 0.75), C["led"], radius=28, strength=150)
    d = ImageDraw.Draw(img)
    rect(d, y0, 0.75, y1, 1.75, C["oak"], outline=C["oak_dark"], w=2)
    for k in range(1, 4):
        xx = y0 + k * (y1 - y0) / 4
        d.line([X(xx), Z(1.72), X(xx), Z(0.78)], fill=C["oak_dark"], width=2)
    tv(d, 3.95)
    rect(d, TV_YC - 1.5, 1.75, TV_YC + 1.5, 1.97, "#1C1C1D")
    top = books(d, y0 + 1.0, 1.75)
    vase(d, y0 + 1.0, top, 0.65, 0.28, C["brass"])
    vase(d, y1 - 0.9, 1.75, 1.0, 0.55, C["white"])
    plant(d, TV_WALL - 1.1, 0.0, 2.6)
    dim_h(d, y0, y1, -0.45, "7'-0\" console, 14\" deep", above=False)
    dim_v(d, y0 - 0.6, 0, 0.75, "9\"")
    dim_v(d, y0 - 0.6, 0.75, 1.75, "12\"")
    return img


def design_fluted():
    img, d = base("2. Fluted walnut panel + slim console", "Floor-to-ceiling fluted panel behind the TV, asymmetric greige console with oak top, LED washing the flutes")
    p0, p1 = TV_YC - 2.5, TV_YC + 2.5
    rect(d, p0, 0, p1, WALL_H - 0.08, C["walnut"])
    pitch = 1.5 / 12
    k = 0
    x = p0
    while x < p1:
        d.line([X(x), Z(WALL_H - 0.1), X(x), Z(0.02)], fill=C["walnut_dark"], width=2)
        x += pitch
        k += 1
    glow(img, (p0, 6.5, p1, WALL_H - 0.1), C["led"], radius=45, strength=120)
    d = ImageDraw.Draw(img)
    rect(d, p0, WALL_H - 0.14, p1, WALL_H - 0.08, "#FFF1D6")
    c0, c1 = TV_YC - 2.0, TV_YC + 5.5
    rect(d, c0, 0.7, c1, 1.52, C["greige"], outline="#B7AFA3", w=2)
    rect(d, c0, 1.52, c1, 1.6, C["oak"])
    for i in range(1, 3):
        xx = c0 + i * (c1 - c0) / 3
        d.line([X(xx), Z(1.5), X(xx), Z(0.73)], fill="#B7AFA3", width=2)
    tv(d, 3.9)
    # globe lamp + books + elephant at the open end
    lx = c1 - 0.8
    d.line([X(lx), Z(1.6), X(lx), Z(2.7)], fill=C["brass"], width=4)
    glow(img, (lx - 0.5, 2.3, lx + 0.5, 3.3), C["led"], radius=22, strength=170)
    d = ImageDraw.Draw(img)
    d.ellipse([X(lx - 0.33), Z(3.25), X(lx + 0.33), Z(2.6)], fill="#FFF3DC", outline="#E8CFA2")
    books(d, c1 - 2.0, 1.6, n=2)
    plant(d, 1.1, 0.0, 2.3)
    dim_h(d, p0, p1, WALL_H + 0.25, "5'-0\" fluted panel, 1.5\" flutes")
    dim_h(d, c0, c1, -0.45, "7'-6\" console", above=False)
    return img


def design_stone():
    img, d = base("3. Stone slab + plinth + niche", "Honed dark stone slab behind the TV, low stone plinth, backlit oak niche in a shallow box-out")
    s0, s1 = TV_YC - 2.4, TV_YC + 2.4
    rect(d, 0.4, 0, TV_WALL - 0.4, 0.5, C["stone"])
    rect(d, s0, 0.5, s1, 8.8, C["stone"])
    rnd = random.Random(3)
    for _ in range(26):
        x = rnd.uniform(s0, s1)
        z = rnd.uniform(0.6, 8.7)
        pts = [(X(x), Z(z))]
        for _ in range(6):
            x = min(max(x + rnd.uniform(-0.5, 0.5), s0), s1)
            z = min(max(z + rnd.uniform(-0.6, 0.3), 0.55), 8.75)
            pts.append((X(x), Z(z)))
        d.line(pts, fill="#8C8C8E", width=1)
    glow(img, (s0, 7.4, s1, 8.8), C["led"], radius=35, strength=90)
    d = ImageDraw.Draw(img)
    tv(d, 4.05)
    n0, n1 = TV_WALL - 2.2, TV_WALL - 0.4
    rect(d, n0, 0.5, n1, 8.8, "#E6E1D8", outline="#CFC8BD", w=2)
    rect(d, n0 + 0.2, 0.5, n1 - 0.2, 7.8, C["oak"])
    for z in (2.6, 4.4, 6.1):
        glow(img, (n0 + 0.2, z - 1.4, n1 - 0.2, z - 0.1), C["led"], radius=14, strength=150)
    d = ImageDraw.Draw(img)
    for z in (2.6, 4.4, 6.1):
        rect(d, n0 + 0.2, z - 0.08, n1 - 0.2, z, C["oak_dark"])
    yc = (n0 + n1) / 2
    vase(d, yc, 0.5, 1.1, 0.5, C["white"])
    vase(d, yc, 2.6, 0.65, 0.28, C["brass"])
    books(d, yc, 4.4, n=3)
    plant(d, yc, 6.1, 0.5, pot_w=0.45, pot_h=0.35)
    dim_h(d, s0, s1, 9.2, "4'-9\" stone slab")
    dim_v(d, -1.4, 0, 0.5, "6\" plinth")
    dim_h(d, n0, n1, 9.2, "1'-10\" niche")
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    imgs = []
    for name, fn in (("lobby_elev_01_floating_oak.png", design_oak), ("lobby_elev_02_fluted_panel.png", design_fluted), ("lobby_elev_03_stone_slab.png", design_stone)):
        img = fn().convert("RGB")
        img.save(os.path.join(OUT, name))
        imgs.append(img)
        print("wrote", name)
    w, h = imgs[0].size
    sheet = Image.new("RGB", (w, h * 3), "white")
    for i, im in enumerate(imgs):
        sheet.paste(im, (0, i * h))
    sheet.save(os.path.join(OUT, "lobby_elevations_all.png"))
    print("wrote lobby_elevations_all.png")


if __name__ == "__main__":
    main()
