"""Ground-floor lobby: three minimal TV-unit designs on the west wall.

    blender -b -P scripts/lobby_scene.py -- --design all --quality preview
    blender -b -P scripts/lobby_scene.py -- --design fluted --quality final

Designs: oak (floating oak console), fluted (fluted panel + slim console), stone (stone slab + plinth + niche).
Reuses materials, assets, world and render settings from office_scene.py.
"""

import argparse
import json
import math
import os
import sys
import time

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fetch_assets as fa  # noqa: E402
import office_lib as L  # noqa: E402
import office_scene as S  # noqa: E402
from office_lib import kelvin, srgb  # noqa: E402

F, fbox, M, A, C = S.F, S.fbox, S.M, S.A, S.C

# =============================================================================
# CONFIG (feet). Ground-floor plan "GROUND FLOOR DOOR & WINDOW PLAN - 04012025".
# Origin: south-west inner corner of the lobby. +X = east, +Y = north, +Z = up.
# =============================================================================
LOBBY_W = 16.0  # west -> east
LOBBY_L = 28 + 10.5 / 12  # south -> north (incl. the staircase at the north end)
CEIL_H = 10.0
T = 0.75  # wall thickness used for all lobby walls
WIN_S = dict(x0=4.75, x1=12.75, sill=3.0, lintel=7.0)  # 8'-0" window W on the south wall
TV_WALL_Y1 = 12.75  # solid west wall from the SW corner to bedroom-1 door
DOORS_W = [(12.75, 16.25), (17.0, 20.5)]  # bedroom-1 / bedroom-2 doors on the west wall
STAIR_Y0 = 20.5  # staircase zone starts here (not modelled in detail)
TV_YC = TV_WALL_Y1 / 2  # centre of the TV wall
TV_Z = 3.6  # centre height of a 65" TV (seated eye level)
DOWNLIGHTS = [(3.0, 3.2), (3.0, 9.55), (9.5, 3.2), (9.5, 9.55), (9.5, 16.5), (3.0, 16.5)]

EXPOSURE = 2.75
DESIGNS = {
    "oak": dict(file="lobby_tv_01_floating_oak.png", title="Floating oak console"),
    "fluted": dict(file="lobby_tv_02_fluted_panel.png", title="Fluted panel + slim console"),
    "stone": dict(file="lobby_tv_03_stone_slab.png", title="Stone slab + plinth + niche"),
}
CAMERA = dict(pos=(13.2, TV_YC, 4.0), heading=180.0, lens=24, shift_x=0.0, shift_y=0.03)


# =============================================================================
def build_materials_lobby():
    acg = {n: fa.acg_maps(n) for n in fa.ACG_TEXTURES}
    ph = {n: fa.fetch_ph_texture(n, r) for n, r in fa.PH_TEXTURES.items()}
    M["stone"] = L.pbr_mat("nero_stone_honed", acg["Marble016"], size=1.6, rough=(0.32, 0.45), normal=0.2)
    M["walnut"] = L.pbr_mat("walnut", ph["oak_veneer_01"], size=1.2, rough=(0.35, 0.55), normal=0.35, value=0.45, tint=srgb("#B07A52"), coat=0.2, coat_rough=0.3)
    M["greige"] = L.simple_mat("greige_lacquer", srgb("#CFC8BD"), rough=0.35, coat=0.1)
    M["tv_screen"] = L.simple_mat("tv_off", srgb("#050506"), rough=0.06, coat=1.0, coat_rough=0.02)
    M["lobby_wall"] = L.pbr_mat("lobby_wall", acg["PaintedPlaster017"], size=2.2, color=srgb("#EEEAE3"), color_var=0.07, rough=(0.72, 0.9), normal=0.18)
    M["door_white"] = M["walnut"]  # doors and frames are walnut (owner, Sep 2026)
    M["led_warm"] = L.simple_mat("led_warm", (1, 1, 1, 1), rough=0.4, emission=(*kelvin(2700), 1), emission_strength=10.0)


def build_room():
    c = C["arch"]
    wall, sec = M["lobby_wall"], M["section"]
    W, Lg = LOBBY_W, LOBBY_L
    sides = {"-x": 1, "+x": 1, "-y": 1, "+y": 1, "-z": 1}
    fbox("lobby_floor", (-T, -T, -0.5), (W + T, Lg + T, 0), [M["floor"], sec], c, face_mats=sides)
    S.reg("cut", fbox("lobby_ceiling", (-T, -T, CEIL_H), (W + T, Lg + T, CEIL_H + 0.5), M["ceiling"], c))
    # west wall (TV wall) with the two bedroom doors
    y = -T
    cuts = DOORS_W + [(STAIR_Y0, STAIR_Y0)]
    for i, (a, b) in enumerate(DOORS_W):
        fbox(f"west_wall_{i}", (-T, y, 0), (0, a, CEIL_H), [wall, sec], c, face_mats={"+z": 1})
        fbox(f"west_wall_head_{i}", (-T, a, 7.0), (0, b, CEIL_H), [wall, sec], c, face_mats={"+z": 1})
        # closed flush door + frame
        fbox(f"door_{i}", (-T + 0.2, a, 0.03), (-T + 0.35, b, 7.0), M["door_white"], c, bevel=0.002)
        for j, (p0, p1) in enumerate((((0, a - 0.25, 0), (0.06, a, 7.0)), ((0, b, 0), (0.06, b + 0.25, 7.0)), ((0, a - 0.25, 7.0), (0.06, b + 0.25, 7.25)))):
            fbox(f"door_frame_{i}_{j}", p0, p1, M["door_white"], c, bevel=0.002)
        y = b
    fbox("west_wall_n", (-T, y, 0), (0, Lg + T, CEIL_H), [wall, sec], c, face_mats={"+z": 1})
    # south wall with the 8' window
    w = WIN_S
    fbox("south_wall_w", (-T, -T, 0), (w["x0"], 0, CEIL_H), [wall, sec], c, face_mats={"+z": 1})
    fbox("south_wall_e", (w["x1"], -T, 0), (W + T, 0, CEIL_H), [wall, sec], c, face_mats={"+z": 1})
    fbox("south_wall_sill", (w["x0"], -T, 0), (w["x1"], 0, w["sill"]), [wall, sec], c)
    fbox("south_wall_head", (w["x0"], -T, w["lintel"]), (w["x1"], 0, CEIL_H), [wall, sec], c, face_mats={"+z": 1})
    fy0, fy1, fw = -0.55, -0.4, 2.2 / 12
    for i, (p0, p1) in enumerate((((w["x0"], fy0, w["sill"]), (w["x1"], fy1, w["sill"] + fw)), ((w["x0"], fy0, w["lintel"] - fw), (w["x1"], fy1, w["lintel"])), ((w["x0"], fy0, w["sill"]), (w["x0"] + fw, fy1, w["lintel"])), ((w["x1"] - fw, fy0, w["sill"]), (w["x1"], fy1, w["lintel"])), (((w["x0"] + w["x1"]) / 2 - fw / 2, fy0, w["sill"]), ((w["x0"] + w["x1"]) / 2 + fw / 2, fy1, w["lintel"])))):
        fbox(f"lobby_window_frame_{i}", p0, p1, M["alu_grey"], c, bevel=0.002)
    fbox("lobby_window_glass", (w["x0"], -0.48, w["sill"]), (w["x1"], -0.475, w["lintel"]), M["glass"], c)
    for i, (p0, p1, rot) in enumerate((((w["x0"] - 0.25, 0, w["sill"] - 0.25), (w["x1"] + 0.25, 0.07, w["sill"]), True), ((w["x0"] - 0.25, 0, w["lintel"]), (w["x1"] + 0.25, 0.07, w["lintel"] + 0.25), True), ((w["x0"] - 0.25, 0, w["sill"]), (w["x0"], 0.07, w["lintel"]), False), ((w["x1"], 0, w["sill"]), (w["x1"] + 0.25, 0.07, w["lintel"]), False))):
        fbox(f"lobby_window_teak_{i}", p0, p1, M["teak"], c, bevel=0.002, uv_rot=rot)
    # east wall (behind the camera) and a wall closing the staircase zone
    fbox("east_wall", (W, -T, 0), (W + T, Lg + T, CEIL_H), [wall, sec], c, face_mats={"+z": 1})
    fbox("stair_wall", (0, STAIR_Y0 + 0.4, 0), (W, STAIR_Y0 + 0.4 + T, CEIL_H), [wall, sec], c, face_mats={"+z": 1})
    # marble skirting on the visible walls
    t, h = S.SKIRTING_T, S.SKIRTING_H
    for i, (p0, p1) in enumerate((((0, 0, 0), (t, DOORS_W[0][0], h)), ((0, 0, 0), (w["x0"], t, h)), ((w["x1"], 0, 0), (W, t, h)), ((0, STAIR_Y0 + 0.4 - t, 0), (W, STAIR_Y0 + 0.4, h)))):
        fbox(f"lobby_skirting_{i}", p0, p1, M["floor"], c, bevel=0.002, segs=2)
    # recessed downlights
    for i, (x, yy) in enumerate(DOWNLIGHTS):
        bm = bmesh.new()
        L.bm_cyl(bm, 0.06, 0.004, loc=F(x, yy, CEIL_H) - Vector((0, 0, 0.004)), segs=40)
        d = L.mesh_obj(f"lobby_downlight_{i}", bm, M["downlight"], c)
        d.visible_shadow = False
        lt = bpy.data.lights.new(f"lobby_downlight_{i}", "SPOT")
        lt.energy = 6.0
        lt.color = kelvin(3000)
        lt.spot_size = math.radians(80)
        lt.spot_blend = 0.45
        lt.shadow_soft_size = 0.03
        ob = bpy.data.objects.new(f"lobby_downlight_{i}", lt)
        ob.location = F(x, yy, CEIL_H) - Vector((0, 0, 0.02))
        C["lights"].objects.link(ob)


def tv(coll, x_front, z_centre, yc=TV_YC):
    """65-inch TV, wall mounted, screen facing +X."""
    Wt, Ht, Dt = 1.45, 0.83, 0.03
    x = F(x_front)
    L.box_obj("tv_body", (x - Dt, F(yc) - Wt / 2, F(z_centre) - Ht / 2), (x, F(yc) + Wt / 2, F(z_centre) + Ht / 2), M["plastic_black"], coll, bevel=0.003)
    L.box_obj("tv_screen", (x, F(yc) - Wt / 2 + 0.006, F(z_centre) - Ht / 2 + 0.006), (x + 0.0006, F(yc) + Wt / 2 - 0.006, F(z_centre) + Ht / 2 - 0.006), M["tv_screen"], coll)


def led_strip(name, coll, p0, p1, energy, rot, size, size_y):
    """Emissive strip (visual) + matching area light (feet corners)."""
    s = fbox(name, p0, p1, M["led_warm"], coll)
    s.visible_shadow = False
    lt = bpy.data.lights.new(name, "AREA")
    lt.shape = "RECTANGLE"
    lt.size, lt.size_y = size, size_y
    lt.energy = energy
    lt.color = kelvin(2700)
    ob = bpy.data.objects.new(name, lt)
    ob.location = (F(*p0) + F(*p1)) / 2
    ob.rotation_euler = rot
    coll.objects.link(ob)
    return s, ob


def decor(coll, proto, name, xy, z, rz=0.0, scale=1.0):
    ob = proto.copy()
    ob.name = name
    coll.objects.link(ob)
    R = Matrix.Rotation(math.radians(rz), 3, "Z") @ Matrix.Diagonal((scale, scale, scale))
    L.place_by_bbox(ob, R, xc=F(xy[0]), yc=F(xy[1]), zmin=F(z))
    return ob


def book_stack(coll, name, x, y, z, n=3):
    lay = Matrix.Rotation(math.radians(90), 3, "Y") @ Matrix.Rotation(math.pi / 2, 3, "Z")
    zz = F(z)
    for k, b in enumerate([b for b in A["books"] if "hardcover" in b.name][3 : 3 + n]):
        ob = b.copy()
        ob.name = f"{name}_{k}"
        coll.objects.link(ob)
        ext = L.place_by_bbox(ob, Matrix.Rotation(0.06 * (k - 1), 3, "Z") @ lay, xc=F(x), yc=F(y), zmin=zz)
        zz += ext.z
    return zz / L.FT


# ----------------------------------------------------------------------------- designs
def design_oak(coll):
    """1. Floating oak console, clean wall, warm glow underneath."""
    y0, y1 = TV_YC - 3.5, TV_YC + 3.5
    zb, zt, d = 0.75, 1.75, 14 / 12
    fbox("oak_console", (0, y0, zb), (d, y1, zt), M["oak"], coll, bevel=0.003, uv_rot=True)
    for k in range(1, 4):  # push-to-open flap door joints
        yy = y0 + k * (y1 - y0) / 4
        fbox(f"oak_joint_{k}", (d, yy - 0.004, zb + 0.03), (d + 0.002, yy + 0.004, zt - 0.03), M["plastic_black"], coll)
    led_strip("oak_under_led", coll, (0.3, y0 + 0.2, zb - 0.02), (0.37, y1 - 0.2, zb), 6.0, (0, 0, 0), 0.02, F(6.6))
    tv(coll, 0.12, TV_Z + 0.35)
    fbox("soundbar", (0.02, TV_YC - 1.5, zt), (0.3, TV_YC + 1.5, zt + 0.22), M["plastic_black"], coll, bevel=0.01)
    top = book_stack(coll, "oak_books", 0.55, y0 + 1.0, zt)
    decor(coll, A["brass_vase_03"], "oak_brass", (0.55, y0 + 1.0), top)
    decor(coll, A["ceramic_vase_01"], "oak_vase", (0.5, y1 - 0.9), zt, scale=0.75)
    decor(coll, A["potted_plant_01"], "oak_plant", (1.2, TV_WALL_Y1 - 1.3), 0.0, rz=40)


def design_fluted(coll):
    """2. Floor-to-ceiling fluted walnut panel behind the TV, asymmetric slim console."""
    p0, p1 = TV_YC - 2.5, TV_YC + 2.5
    fbox("fluted_backer", (0, p0, 0), (0.08, p1, CEIL_H), M["walnut"], coll)
    bm = bmesh.new()
    pitch, n = 1.5 / 12, int(5.0 / (1.5 / 12))
    for k in range(n):
        yc = p0 + (k + 0.5) * pitch
        L.bm_cyl(bm, F(0.55 / 12), F(CEIL_H) - 0.002, loc=F(0.08, yc, 0.0), segs=16)
    fl = L.mesh_obj("fluted_ribs", bm, M["walnut"], coll)
    fl.scale = (0.7, 1.0, 1.0)
    led_strip("fluted_top_led", coll, (0.2, p0, CEIL_H - 0.08), (0.28, p1, CEIL_H - 0.02), 14.0, (0, math.radians(35), 0), F(5.0), 0.03)
    c0, c1 = TV_YC - 2.0, TV_YC + 5.5
    zb, zt, d = 0.7, 1.6, 15 / 12
    fbox("fluted_console", (0.08, c0, zb), (d, c1, zt - 0.08), M["greige"], coll, bevel=0.003)
    fbox("fluted_console_top", (0.08, c0, zt - 0.08), (d + 0.02, c1, zt), M["oak"], coll, bevel=0.002, uv_rot=True)
    for k in range(1, 3):
        yy = c0 + k * (c1 - c0) / 3
        fbox(f"fluted_joint_{k}", (d, yy - 0.004, zb + 0.03), (d + 0.002, yy + 0.004, zt - 0.1), M["plastic_dark"], coll)
    tv(coll, 0.2, TV_Z + 0.3)
    # sculptural lamp + plant at the open end of the console
    lx, ly = 0.6, c1 - 0.8
    bm = bmesh.new()
    L.bm_lathe(bm, [(0, 0), (0.07, 0), (0.075, 0.02), (0.02, 0.05), (0.012, 0.35), (0, 0.35)], segs=48)
    L.mesh_obj("lamp_base", bm, M["brass"], coll, uv=False).location = F(lx, ly, zt)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=40, v_segments=20, radius=0.11)
    for f in bm.faces:
        f.smooth = True
    globe = L.mesh_obj("lamp_globe", bm, M["shade"], coll, uv=False)
    globe.location = F(lx, ly, zt) + Vector((0, 0, 0.44))
    lt = bpy.data.lights.new("fluted_lamp", "POINT")
    lt.energy, lt.color, lt.shadow_soft_size = 8.0, kelvin(2700), 0.06
    lo = bpy.data.objects.new("fluted_lamp", lt)
    lo.location = globe.location
    coll.objects.link(lo)
    top = book_stack(coll, "fluted_books", 0.6, c1 - 2.0, zt, n=2)
    decor(coll, A["carved_wooden_elephant"], "fluted_elephant", (0.6, c1 - 2.0), top, rz=160, scale=1.3)
    decor(coll, A["potted_plant_02"], "fluted_plant", (1.0, 1.1), 0.0, rz=10, scale=1.1)


def design_stone(coll):
    """3. Book-matched stone slab behind the TV, low stone plinth, backlit oak niche."""
    s0, s1 = TV_YC - 2.4, TV_YC + 2.4
    fbox("stone_slab", (0, s0, 0.5), (0.1, s1, 8.8), M["stone"], coll, bevel=0.002)
    fbox("stone_plinth", (0, 0.4, 0), (1.35, TV_WALL_Y1 - 0.4, 0.5), M["stone"], coll, bevel=0.003)
    led_strip("stone_top_led", coll, (0.12, s0 + 0.1, 8.8), (0.2, s1 - 0.1, 8.84), 7.0, (0, math.radians(20), 0), F(4.6), 0.03)
    tv(coll, 0.22, TV_Z + 0.45)
    # oak-lined niche in a box-out on the right (north) side
    n0, n1 = TV_WALL_Y1 - 2.2, TV_WALL_Y1 - 0.4
    fbox("niche_boxout_l", (0, n0, 0.5), (0.5, n0 + 0.2, 7.8), M["lobby_wall"], coll)
    fbox("niche_boxout_r", (0, n1 - 0.2, 0.5), (0.5, n1, 7.8), M["lobby_wall"], coll)
    fbox("niche_boxout_top", (0, n0, 7.8), (0.5, n1, 8.8), M["lobby_wall"], coll)
    fbox("niche_back", (0, n0 + 0.2, 0.5), (0.05, n1 - 0.2, 7.8), M["oak"], coll)
    for k, z in enumerate((2.6, 4.4, 6.1)):
        fbox(f"niche_shelf_{k}", (0.05, n0 + 0.2, z - 0.08), (0.5, n1 - 0.2, z), M["oak"], coll, bevel=0.002, uv_rot=True)
        led_strip(f"niche_led_{k}", coll, (0.35, n0 + 0.25, z - 0.1), (0.42, n1 - 0.25, z - 0.08), 1.2, (0, 0, 0), 0.02, F(1.3))
    yc = (n0 + n1) / 2
    decor(coll, A["ceramic_vase_01"], "niche_vase", (0.25, yc), 0.5, scale=0.85)
    decor(coll, A["brass_vase_03"], "niche_brass", (0.25, yc), 2.6)
    top = book_stack(coll, "niche_books", 0.25, yc, 4.4, n=3)
    decor(coll, A["potted_plant_04"], "niche_succulent", (0.25, yc), 6.1)
    decor(coll, A["carved_wooden_elephant"], "stone_elephant", (0.8, s0 + 0.6), 0.5, rz=200, scale=1.3)


BUILDERS = {"oak": design_oak, "fluted": design_fluted, "stone": design_stone}


def build_scene():
    t0 = time.time()
    fa.fetch_all()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for n in ("arch", "decor", "lights", "cameras"):
        C[n] = L.collection(n)
    C["protos"] = L.collection("_protos")
    S.build_materials()
    build_materials_lobby()
    S.load_assets()
    build_room()
    for key in DESIGNS:
        C["design_" + key] = L.collection("design_" + key)
        BUILDERS[key](C["design_" + key])
    S.build_world()
    # move the office window portal onto the lobby's south window
    po = bpy.data.objects["window_portal"]
    w = WIN_S
    po.location = F((w["x0"] + w["x1"]) / 2, -T - 0.02, (w["sill"] + w["lintel"]) / 2)
    po.rotation_euler = (math.radians(-90), 0, 0)
    po.data.size = F(w["x1"] - w["x0"])
    po.data.size_y = F(w["lintel"] - w["sill"])
    S.make_camera("cam_lobby", CAMERA)
    print(f"[lobby] built in {time.time() - t0:.1f}s")


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", default="all", choices=["all", *DESIGNS])
    ap.add_argument("--quality", default="preview", choices=list(S.QUALITY))
    ap.add_argument("--out", default=os.path.join(S.REPO, "renders", "lobby"))
    args = ap.parse_args(argv)
    build_scene()
    S.setup_render(args.quality)
    sc = bpy.context.scene
    sc.camera = bpy.data.objects["cam_lobby"]
    sc.view_settings.exposure = EXPOSURE
    sc.view_settings.white_balance_temperature = 4300
    sc.view_settings.white_balance_tint = S.WHITE_BALANCE_TINT
    out = args.out if args.quality == "final" else os.path.join(args.out, "previews")
    os.makedirs(out, exist_ok=True)
    keys = list(DESIGNS) if args.design == "all" else [args.design]
    times = {}
    for key in keys:
        for k in DESIGNS:
            C["design_" + k].hide_render = k != key
        sc.render.filepath = os.path.join(out, DESIGNS[key]["file"])
        t = time.time()
        bpy.ops.render.render(write_still=True)
        times[key] = round(time.time() - t, 1)
        print(f"[render] lobby {key}: {times[key]:.1f}s -> {sc.render.filepath}", flush=True)
    with open(os.path.join(out, "render_times.json"), "w") as f:
        json.dump({k: {"seconds": s, "quality": args.quality} for k, s in times.items()}, f, indent=2)


if __name__ == "__main__":
    main()
