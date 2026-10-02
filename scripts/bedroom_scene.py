"""First-floor bedroom-1: straight-on, photo-style views of three walls (cheap box model).

    blender -b -P scripts/bedroom_scene.py -- --view all --quality preview
    blender -b -P scripts/bedroom_scene.py -- --view all --quality final

Views: corner (photo-1 angle: bed wall + balcony wall), south (photo-2 angle: balcony door/window +
wardrobe), bed (straight-on bed wall + AC).
Reuses materials, assets, world and render settings from office_scene.py.
Only run when the owner asks for Blender (see CLAUDE.md).
"""

import argparse
import json
import math
import os
import sys
import time

import bmesh
import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fetch_assets as fa  # noqa: E402
import office_lib as L  # noqa: E402
import office_scene as S  # noqa: E402
from office_lib import kelvin, srgb  # noqa: E402

F, fbox, M, A, C = S.F, S.fbox, S.M, S.A, S.C

# =============================================================================
# CONFIG (feet). Bedroom-1 (SW corner of the first-floor plan): 16'-3" N-S x 12'-0" E-W.
# Origin: inner NW corner. +X = south (along the bed wall, towards the balcony wall), +Y = east.
# Walls: x = 0 north (partition to the other room), y = 0 west (dress/toilet doors),
#        y = RD east (bed wall, entry door from the lobby), x = RW south (balcony DW1 + wardrobe).
# =============================================================================
RW, RD, CEIL_H = 16.25, 12.0, 10.0
T = 0.75
# south wall (x = RW), from the west: wardrobe | window 3' | glazed balcony door 3' | 0'-3" pier
WIN_Y = (5.7, 8.7)
DOOR_Y = (8.7, 11.7)
WIN_SILL, OPEN_TOP = 2.75, 7.0
ENTRY_DOOR = (0.6, 4.1)  # D1 from the lobby, north end of the bed wall
WEST_DOORS = ((0.3, 3.0), (3.6, 6.1))  # D2 (zall) and D3 (dress/toilet) on the west wall
BED = dict(xc=9.9, w=6.5, l=7.0, h=1.55)  # king bed in latte laminate, ~3' clear of the balcony wall
AC = dict(xc=9.6, z_top=8.75, w=3.0, h=1.0, d=0.72)  # on the bed wall at the wire point
WARD = dict(x0=0.0, x1=5.45, d=2.0, top=9.15, niche_w=3.3)  # south wall, west corner up to the window
BAND = dict(z=9.25, t=0.25, inset=1.9, r=1.4, step_z=9.6, step_inset=2.45, step_r=1.1)
COVE_W = 1.5

COL = dict(wall="#EDEBE2", latte="#CABBA7", greige="#B8AFA3", plinth="#2B2826", taupe="#8C7B6B", bedding="#E9E6DF")
VIEWS = {  # res = final size; previews are 0.4x
    "corner": dict(file="bedroom_01_corner.png", pos=(4.2, 0.9, 5.0), heading=57.0, lens=24, shift_y=0.06, exposure=2.6, res=(1200, 1600)),
    "south": dict(file="bedroom_02_window_wardrobe.png", pos=(0.9, 3.4, 5.0), heading=-6.0, lens=22, shift_y=0.08, exposure=2.6, res=(900, 1600)),
    "bed": dict(file="bedroom_03_bed_wall.png", pos=(9.0, 0.8, 4.25), heading=90.0, lens=28, shift_y=0.03, exposure=2.7, res=(1600, 1000)),
}
QUALITY = {"preview": dict(scale=0.4, samples=24), "final": dict(scale=1.0, samples=128)}


def mats():
    acg = {n: fa.acg_maps(n) for n in fa.ACG_TEXTURES}
    M["cream"] = L.pbr_mat("wall_cream", acg["PaintedPlaster017"], size=2.2, color=srgb(COL["wall"]), color_var=0.06, rough=(0.75, 0.9), normal=0.15)
    M["latte"] = L.simple_mat("latte_laminate", srgb(COL["latte"]), rough=0.55, bump=0.04, bump_scale=600)
    M["greige_lam"] = L.simple_mat("greige_laminate", srgb(COL["greige"]), rough=0.5, bump=0.04, bump_scale=600)
    M["plinth"] = L.simple_mat("dark_plinth", srgb(COL["plinth"]), rough=0.6)
    M["gold"] = L.simple_mat("brushed_gold", srgb("#C7A465"), rough=0.3, metallic=1.0)
    M["bedding"] = L.pbr_mat("bedding_white", acg["Fabric031"], size=0.2, color=srgb(COL["bedding"]), color_var=0.15, normal=0.6, rough=(0.8, 0.95), sheen=0.5)
    M["taupe_curtain"] = L.pbr_mat("blackout_taupe", fa.fetch_ph_texture("rough_linen", "2k"), size=0.27, color=srgb(COL["taupe"]), color_var=0.25, normal=0.8, rough=(0.85, 1.0), sheen=0.4)
    M["fan"] = L.simple_mat("fan_matte_white", srgb("#ECEAE5"), rough=0.4)


def ceiling():
    c = C["arch"]
    b = BAND
    for name, inset, r, z0, z1 in (("band", b["inset"], b["r"], b["z"], b["z"] + b["t"]), ("step", b["step_inset"], b["step_r"], b["step_z"], CEIL_H)):
        plate = fbox(f"ceil_{name}", (-0.01, -0.01, z0), (RW + 0.01, RD + 0.01, z1), M["ceiling"], c)
        bm = bmesh.new()
        pts = S.rounded_rect_pts(F(inset), F(inset), F(RW - inset), F(RD - inset), F(r))
        lo = [bm.verts.new((x, y, F(z0) - 0.05)) for x, y in pts]
        hi = [bm.verts.new((x, y, F(z1) + 0.05)) for x, y in pts]
        n = len(pts)
        for i in range(n):
            bm.faces.new((lo[i], lo[(i + 1) % n], hi[(i + 1) % n], hi[i]))
        bm.faces.new(list(reversed(lo)))
        bm.faces.new(hi)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        cutter = L.mesh_obj(f"ceil_{name}_cutter", bm, M["ceiling"], C["protos"], uv=False)
        mod = plate.modifiers.new("hole", "BOOLEAN")
        mod.operation, mod.solver, mod.object = "DIFFERENCE", "EXACT", cutter
    zi = b["z"] + b["t"] + 0.01
    ins = b["inset"] + 0.12
    for i, (xa, ya, xb, yb) in enumerate(((ins, ins, RW - ins, ins), (ins, RD - ins, RW - ins, RD - ins), (ins, ins, ins, RD - ins), (RW - ins, ins, RW - ins, RD - ins))):
        lt = bpy.data.lights.new(f"cove_{i}", "AREA")
        horiz = ya == yb
        length = (xb - xa) if horiz else (yb - ya)
        lt.shape, lt.size, lt.size_y = "RECTANGLE", F(length), 0.025
        lt.energy, lt.color = COVE_W * length / 8.0, kelvin(4000)
        ob = bpy.data.objects.new(f"cove_{i}", lt)
        ob.location = F((xa + xb) / 2, (ya + yb) / 2, zi)
        ob.rotation_euler = (math.pi, 0, 0 if horiz else math.pi / 2)
        C["lights"].objects.link(ob)
    # ceiling fan at the centre point
    c = C["arch"]
    cx, cy = RW / 2, RD / 2
    bm = bmesh.new()
    L.bm_cyl(bm, 0.012, F(1.0), loc=F(cx, cy, CEIL_H - 1.0), segs=16)
    L.bm_cyl(bm, 0.05, 0.03, loc=F(cx, cy, CEIL_H) - Vector((0, 0, 0.03)), segs=32)
    L.bm_lathe(bm, [(0, 0), (0.07, 0.0), (0.11, 0.03), (0.11, 0.08), (0.07, 0.11), (0, 0.11)], segs=48, loc=F(cx, cy, CEIL_H - 1.0) - Vector((0, 0, 0.11)))
    L.mesh_obj("fan_motor", bm, M["fan"], c, uv=False)
    bm = bmesh.new()
    for k in range(3):
        a = math.radians(30 + 120 * k)
        R = Matrix.Rotation(a, 4, "Z") @ Matrix.Rotation(math.radians(6), 4, "X")
        L.bm_box(bm, (0.12, -0.065, -0.006), (0.66, 0.065, 0.006), matrix=Matrix.Translation(F(cx, cy, CEIL_H - 1.0) - Vector((0, 0, 0.07))) @ R)
    L.mesh_obj("fan_blades", bm, M["walnut"], c, bevel=0.004)


def room():
    c = C["arch"]
    wall, sec = M["cream"], M["section"]
    fbox("floor", (-T, -T, -0.5), (RW + T, RD + T, 0), [M["floor"], sec], c, face_mats={"-x": 1, "+x": 1, "-y": 1, "+y": 1})
    fbox("slab", (-T, -T, CEIL_H), (RW + T, RD + T, CEIL_H + 0.5), M["ceiling"], c)
    # bed wall (y = RD) with a doorway near the left corner
    a, b = ENTRY_DOOR
    fbox("bedwall_l", (-T, RD, 0), (a, RD + T, CEIL_H), wall, c)
    fbox("bedwall_r", (b, RD, 0), (RW + T, RD + T, CEIL_H), wall, c)
    fbox("bedwall_head", (a, RD, 7.0), (b, RD + T, CEIL_H), wall, c)
    fbox("toilet_door", (a, RD + 0.3, 0.02), (b, RD + 0.45, 7.0), M["walnut"], c, bevel=0.002)
    # west wall (y = 0) with the D2 / D3 doors, north wall (x = 0)
    (e0, e1), (f0, f1) = WEST_DOORS
    for i, (xa, xb) in enumerate(((-T, e0), (e1, f0), (f1, RW + T))):
        fbox(f"wall_y0_{i}", (xa, -T, 0), (xb, 0, CEIL_H), wall, c)
    for i, (xa, xb) in enumerate(WEST_DOORS):
        fbox(f"wall_y0_head_{i}", (xa, -T, 7.0), (xb, 0, CEIL_H), wall, c)
        fbox(f"west_door_{i}", (xa, -0.45, 0.02), (xb, -0.3, 7.0), M["walnut"], c, bevel=0.002)
        for j, (p0, p1) in enumerate((((xa - 0.25, -0.02, 0), (xa, 0.04, 7.25)), ((xb, -0.02, 0), (xb + 0.25, 0.04, 7.25)), ((xa - 0.25, -0.02, 7.0), (xb + 0.25, 0.04, 7.25)))):
            fbox(f"west_door_frame_{i}_{j}", p0, p1, M["walnut"], c, bevel=0.003)
        fbox(f"west_door_knob_{i}", (xb - 0.45, -0.3, 3.4), (xb - 0.35, -0.22, 3.5), M["gold"], c)
    fbox("wall_x0", (-T, 0, 0), (0, RD, CEIL_H), wall, c)
    # balcony wall (x = RW): door + window
    d0, d1 = DOOR_Y
    w0, w1 = WIN_Y
    fbox("balc_s", (RW, -T, 0), (RW + T, w0, CEIL_H), wall, c)
    fbox("balc_n", (RW, d1, 0), (RW + T, RD + T, CEIL_H), wall, c)
    fbox("balc_head", (RW, w0, OPEN_TOP), (RW + T, d1, CEIL_H), wall, c)
    fbox("balc_sill", (RW, w0, 0), (RW + T, w1, WIN_SILL), wall, c)
    fx = RW + 0.45
    for i, (p0, p1) in enumerate((((fx, w0, WIN_SILL), (fx + 0.15, d1, WIN_SILL + 0.15)), ((fx, w0, OPEN_TOP - 0.15), (fx + 0.15, d1, OPEN_TOP)), ((fx, w0, WIN_SILL), (fx + 0.15, w0 + 0.15, OPEN_TOP)), ((fx, w1 - 0.07, 0), (fx + 0.15, w1 + 0.07, OPEN_TOP)), ((fx, d1 - 0.15, 0), (fx + 0.15, d1, OPEN_TOP)))):
        fbox(f"balc_frame_{i}", p0, p1, M["upvc"], c, bevel=0.002)
    fbox("balc_glass_w", (fx + 0.07, w0 + 0.15, WIN_SILL + 0.15), (fx + 0.08, w1 - 0.07, OPEN_TOP - 0.15), M["glass"], c)
    fbox("balc_glass_d", (fx + 0.07, d0 + 0.07, 0.02), (fx + 0.08, d1 - 0.15, OPEN_TOP - 0.15), M["glass"], c)
    for k in range(9):  # horizontal grill outside the window
        z = WIN_SILL + 0.35 + k * 0.45
        fbox(f"grill_{k}", (RW + T + 0.02, w0 - 0.1, z), (RW + T + 0.1, w1 + 0.1, z + 0.06), M["black_metal"], c)
    fbox("balcony_floor", (RW + T, -2, -0.5), (RW + 6, RD + 2, -0.1), M["floor"], c)
    # skirting
    t, h = S.SKIRTING_T, S.SKIRTING_H
    for i, (p0, p1) in enumerate((((e1 + 0.25, 0, 0), (f0 - 0.25, t, h)), ((f1 + 0.25, 0, 0), (RW, t, h)), ((0, 0, 0), (t, RD, h)), ((0, RD - t, 0), (a, RD, h)), ((b, RD - t, 0), (RW, RD, h)), ((RW - t, 0, 0), (RW, w0, h)), ((RW - t, d1, 0), (RW, RD, h)))):
        fbox(f"skirt_{i}", p0, p1, M["floor"], c, bevel=0.002, segs=2)
    # curtains: sheer + taupe blackout, pulled to the sides of the opening
    rod_x, rod_z = RW - 0.3, OPEN_TOP + 0.6
    bm = bmesh.new()
    ya, yb = WARD["x1"] + 0.05, RD - 0.05
    L.bm_bar(bm, F(rod_x, ya, rod_z), F(rod_x, yb, rod_z), 0.01, segs=16)
    L.mesh_obj("curtain_rod", bm, M["gold"], c)
    for name, (pa, pb), xo, mat in (("sheer_w", (ya + 0.1, w0 + 1.0), 0.0, None), ("sheer_e", (d1 - 1.0, yb - 0.1), 0.0, None), ("black_w", (ya + 0.05, ya + 0.75), -0.12, M["taupe_curtain"]), ("black_e", (yb - 0.75, yb - 0.05), -0.12, M["taupe_curtain"])):
        ob = S.sheer_panel(name, rod_x + xo, pa, pb, rod_z - 0.05, 0.05)
        if mat:
            ob.data.materials[0] = mat


def bed_wall():
    c = C["decor"]
    bd = BED
    x0, x1 = bd["xc"] - bd["w"] / 2, bd["xc"] + bd["w"] / 2
    y1 = RD - 0.12
    y0 = y1 - bd["l"]
    fbox("bed_headboard", (x0 - 0.1, y1 - 0.25, 0.25), (x1 + 0.1, y1, 3.6), M["latte"], c, bevel=0.006)
    fbox("bed_base", (x0, y0, 0.25), (x1, y1 - 0.25, 1.05), M["latte"], c, bevel=0.006)
    fbox("bed_plinth", (x0 + 0.3, y0 + 0.3, 0), (x1 - 0.3, y1 - 0.5, 0.25), M["plinth"], c)
    fbox("mattress", (x0 + 0.08, y0 + 0.08, 1.05), (x1 - 0.08, y1 - 0.3, 1.75), M["bedding"], c, bevel=0.03, segs=4)
    L.box_obj("duvet", F(x0 - 0.05, y0 - 0.05, 1.3), F(x1 + 0.05, y1 - 2.4, 1.85), M["bedding"], c, bevel=0.035, segs=4, subsurf=1)
    fbox("duvet_fold", (x0 - 0.04, y1 - 2.7, 1.8), (x1 + 0.04, y1 - 2.3, 1.95), M["bedding"], c, bevel=0.03, segs=3)
    for i, xc in enumerate((bd["xc"] - 1.6, bd["xc"] + 1.6)):
        L.box_obj(f"pillow_{i}", F(xc - 1.25, y1 - 1.6, 1.75), F(xc + 1.25, y1 - 0.35, 2.3), M["bedding"], c, bevel=0.05, segs=4, subsurf=2)
    for i, xc in enumerate((bd["xc"] - 0.9, bd["xc"] + 0.9)):
        L.box_obj(f"cushion_{i}", F(xc - 0.75, y1 - 1.75, 1.85), F(xc + 0.75, y1 - 1.45, 3.05), M["taupe_curtain"], c, bevel=0.05, segs=4, subsurf=2)
    # bedside tables + ceramic lamps
    for i, xs in enumerate((x0 - 0.35 - 1.75, x1 + 0.35)):
        fbox(f"bedside_{i}", (xs, y1 - 1.5, 0.6), (xs + 1.75, y1, 1.85), M["latte"], c, bevel=0.005)
        fbox(f"bedside_drawer_{i}", (xs + 0.04, y1 - 1.51, 0.7), (xs + 1.71, y1 - 1.5, 1.75), M["greige_lam"], c)
        fbox(f"bedside_pull_{i}", (xs + 0.6, y1 - 1.55, 1.55), (xs + 1.15, y1 - 1.51, 1.6), M["gold"], c)
        bm = bmesh.new()
        L.bm_lathe(bm, [(0, 0), (0.08, 0), (0.1, 0.12), (0.06, 0.2), (0.012, 0.26), (0, 0.26)], segs=40)
        base = L.mesh_obj(f"lamp_base_{i}", bm, M["ceramic_sand"], c, uv=False)
        base.location = F(xs + 0.87, y1 - 0.7, 1.85)
        bm = bmesh.new()
        L.bm_lathe(bm, [(0.15, 0.0), (0.11, 0.2), (0.108, 0.2), (0.148, 0.0)], segs=48)
        shade = L.mesh_obj(f"lamp_shade_{i}", bm, M["shade"], c, uv=False)
        shade.location = base.location + Vector((0, 0, 0.25))
        lt = bpy.data.lights.new(f"bedside_bulb_{i}", "POINT")
        lt.energy, lt.color, lt.shadow_soft_size = 5.0, kelvin(3500), 0.03
        lo = bpy.data.objects.new(f"bedside_bulb_{i}", lt)
        lo.location = shade.location + Vector((0, 0, 0.1))
        C["lights"].objects.link(lo)
    # split AC on the bed wall + switchboards beside the bed
    ac = AC
    ax0, ax1 = ac["xc"] - ac["w"] / 2, ac["xc"] + ac["w"] / 2
    az0 = ac["z_top"] - ac["h"]
    fbox("ac_body", (ax0, RD - ac["d"], az0), (ax1, RD, ac["z_top"]), M["plastic_white"], c, bevel=0.035, segs=5)
    fbox("ac_vent", (ax0 + 0.15, RD - ac["d"] + 0.05, az0 - 0.002), (ax1 - 0.15, RD - ac["d"] + 0.28, az0 + 0.02), M["plastic_dark"], c)
    fbox("ac_display", (ac["xc"] + 0.8, RD - ac["d"] - 0.004, az0 + 0.35), (ac["xc"] + 1.05, RD - ac["d"], az0 + 0.42), M["phone"], c)
    for i, x in enumerate((x0 - 0.35 - 0.9, x1 + 0.35 + 0.9)):
        fbox(f"switch_{i}", (x - 0.35, RD - 0.04, 2.6), (x + 0.35, RD, 3.0), M["socket"], c, bevel=0.004)


def wardrobe():
    """Built in a local frame (back on y = 0, front facing +y), then turned onto the south wall:
    local x -> room +y (east), local y -> room -x (into the room)."""
    before = set(bpy.data.objects)
    _wardrobe_local()
    to_wall = Matrix.Translation(F(RW, 0, 0)) @ Matrix.Rotation(math.pi / 2, 4, "Z")
    for ob in set(bpy.data.objects) - before:
        if ob.users_collection and ob.users_collection[0] is not C["protos"]:
            ob.matrix_world = to_wall @ ob.matrix_world


def _wardrobe_local():
    c = C["decor"]
    w = WARD
    x1, d, top = w["x1"], w["d"], w["top"]
    split = x1 - w["niche_w"]  # west side = full-height shutters, window side = drawers + lit niche
    x0, xs = split, w["x0"]  # niche bay spans x0..x1; shutter bay spans xs..split
    fbox("ward_plinth", (xs + 0.1, 0, 0), (x1 - 0.1, d - 0.15, 0.33), M["plinth"], c)
    nz0, nz1 = 2.9, 5.4  # open niche
    fbox("ward_carcass_r", (xs, 0, 0.33), (split, d - 0.06, top), M["latte"], c, bevel=0.003)
    fbox("ward_carcass_low", (x0, 0, 0.33), (x1, d - 0.06, nz0), M["latte"], c, bevel=0.003)
    fbox("ward_carcass_up", (x0, 0, nz1), (x1, d - 0.06, top), M["latte"], c, bevel=0.003)
    zl = 7.0  # loft line
    ff = d - 0.06
    gap = 0.012

    def front(name, xa, xb, za, zb, handle=None):
        fbox(name, (xa + gap, ff, za + gap), (xb - gap, d, zb - gap), M["greige_lam"], c, bevel=0.0015)
        if handle == "v":  # pulls at the meeting edge of a shutter pair
            hx = xa + 0.12 if name.endswith("_r") else xb - 0.17
            fbox(name + "_pull", (hx, d, za + 2.2), (hx + 0.05, d + 0.04, za + 3.6), M["gold"], c, bevel=0.003)
        elif handle == "h":
            xm = (xa + xb) / 2
            fbox(name + "_pull", (xm - 0.4, d, zb - 0.22), (xm + 0.4, d + 0.04, zb - 0.17), M["gold"], c, bevel=0.003)

    # west section: two full-height shutters
    mid = (xs + split) / 2
    front("ward_shutter_l", xs, mid, 0.33, zl, "v")
    front("ward_shutter_r", mid, split, 0.33, zl, "v")
    # window section: drawers, lit open niche, shutter above
    front("ward_drawer_0", x0, x1, 0.33, 1.6, "h")
    front("ward_drawer_1", x0, x1, 1.6, 2.9, "h")
    fbox("ward_niche_back", (x0 + 0.08, 0.0, nz0), (x1 - 0.04, 0.1, nz1), M["latte"], c)
    fbox("ward_niche_shelf", (x0 + 0.08, 0.1, 4.12), (x1 - 0.04, ff, 4.2), M["latte"], c, bevel=0.002)
    for i, (p0, p1) in enumerate((((x0, 0.0, nz0), (x0 + 0.08, ff, nz1)), ((x1 - 0.04, 0.0, nz0), (x1, ff, nz1)))):
        fbox(f"ward_niche_side_{i}", p0, p1, M["latte"], c)
    for i, z in enumerate((5.36, 4.1)):
        s = fbox(f"niche_led_{i}", (x0 + 0.15, ff - 0.25, z - 0.02), (x1 - 0.1, ff - 0.18, z), M["cove_led"], c)
        s.visible_shadow = False
        lt = bpy.data.lights.new(f"niche_led_{i}", "AREA")
        lt.shape, lt.size, lt.size_y, lt.energy, lt.color = "RECTANGLE", F(x1 - x0 - 0.3), 0.02, 2.0, kelvin(3500)
        lo = bpy.data.objects.new(f"niche_led_{i}", lt)
        lo.location = F((x0 + x1) / 2, ff - 0.22, z - 0.04)
        C["lights"].objects.link(lo)
    front("ward_upper", x0, x1, 5.4, zl, "h")
    # lofts in one continuous line
    n = 4
    lw = (x1 - xs) / n
    for k in range(n):
        xa = xs + k * lw
        front(f"ward_loft_{k}", xa, xa + lw, zl, top)
        fbox(f"ward_loft_pull_{k}", (xa + 0.3, d, zl + 0.08), (xa + lw - 0.3, d + 0.04, zl + 0.13), M["gold"], c, bevel=0.003)
    # niche decor
    S.instance_on(A["ceramic_vase_01"], "niche_vase", c, (x0 + 0.7, 0.8), 2.9, scale=0.7)
    S.instance_on(A["potted_plant_04"], "niche_plant", c, (x1 - 0.7, 0.8), 2.9)
    S.instance_on(A["carved_wooden_elephant"], "niche_elephant", c, (x0 + 1.6, 0.9), 4.2, rot_z_deg=200, scale=1.2)
    S.instance_on(A["brass_vase_03"], "niche_brass", c, (x1 - 0.8, 0.8), 4.2)


def build():
    t0 = time.time()
    fa.fetch_all()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for n in ("arch", "decor", "lights", "cameras", "backdrop"):
        C[n] = L.collection(n)
    C["protos"] = L.collection("_protos")
    S.build_materials()
    lobby_mats_walnut()
    mats()
    S.load_assets()
    room()
    ceiling()
    bed_wall()
    wardrobe()
    S.build_world()
    bpy.data.objects["sun"].data.energy = 0.0  # soft daylight only (no direct sun patches)
    po = bpy.data.objects["window_portal"]
    po.location = F(RW + T + 0.02, (WIN_Y[0] + DOOR_Y[1]) / 2, OPEN_TOP / 2)
    po.data.size, po.data.size_y = F(OPEN_TOP), F(DOOR_Y[1] - WIN_Y[0])
    for key, v in VIEWS.items():
        S.make_camera(f"cam_{key}", dict(v, shift_x=0.0))
    print(f"[bedroom] built in {time.time() - t0:.1f}s")


def lobby_mats_walnut():
    ph = {n: fa.fetch_ph_texture(n, r) for n, r in fa.PH_TEXTURES.items()}
    M["walnut"] = L.pbr_mat("walnut", ph["oak_veneer_01"], size=1.2, rough=(0.35, 0.55), normal=0.35, value=0.45, tint=srgb("#B07A52"), coat=0.2, coat_rough=0.3)


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--view", default="all", choices=["all", *VIEWS])
    ap.add_argument("--quality", default="preview", choices=list(QUALITY))
    ap.add_argument("--out", default=os.path.join(S.REPO, "renders", "bedroom"))
    args = ap.parse_args(argv)
    build()
    S.setup_render("preview")
    sc = bpy.context.scene
    q = QUALITY[args.quality]
    sc.cycles.samples = q["samples"]
    sc.cycles.adaptive_threshold = 0.02
    out = args.out if args.quality == "final" else os.path.join(args.out, "previews")
    os.makedirs(out, exist_ok=True)
    times = {}
    for key in (list(VIEWS) if args.view == "all" else [args.view]):
        v = VIEWS[key]
        sc.camera = bpy.data.objects[f"cam_{key}"]
        sc.render.resolution_x, sc.render.resolution_y = (round(n * q["scale"]) for n in v["res"])
        sc.view_settings.exposure = v["exposure"]
        sc.view_settings.white_balance_temperature = 4300
        sc.view_settings.white_balance_tint = -40  # AgX + cream interreflection drift pink; pull toward green
        sc.render.filepath = os.path.join(out, v["file"])
        t = time.time()
        bpy.ops.render.render(write_still=True)
        times[key] = round(time.time() - t, 1)
        print(f"[render] bedroom {key}: {times[key]:.1f}s -> {sc.render.filepath}", flush=True)
    with open(os.path.join(out, "render_times.json"), "w") as f:
        json.dump({k: {"seconds": s, "quality": args.quality} for k, s in times.items()}, f, indent=2)


if __name__ == "__main__":
    main()
