"""Photoreal Cycles render of the first-floor home office.

    blender -b -P scripts/office_scene.py -- --view all --quality final
    blender -b -P scripts/office_scene.py -- --view entrance --quality preview
    blender -b -P scripts/office_scene.py -- --save-blend assets/office.blend --no-render

Views: entrance | desk | cutaway | all.  Quality: preview (640 px, 32 spp) | final (1920x1200).
Assets are downloaded automatically into assets/ on first run (see fetch_assets.py).
"""

import argparse
import json
import math
import os
import sys
import time

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import fetch_assets as fa  # noqa: E402
import office_lib as L  # noqa: E402
from office_lib import ft, kelvin, srgb  # noqa: E402

# =============================================================================
# CONFIG  (all dimensions in FEET; 4" = 4/12)
# Origin: south-west inner corner of the office, finished floor level.
# +X = east (window wall), +Y = north (desk wall), +Z = up.
# =============================================================================
ROOM_W = 12.0  # inner, west -> east
ROOM_L = 16 + 1.5 / 12  # inner, south -> north (16'-1 1/2")
CEIL_H = 10.0
T_EAST, T_SOUTH, T_NORTH, T_WEST = 9 / 12, 9 / 12, 4.5 / 12, 4.5 / 12

WINDOW_Y0 = 7.75  # east wall, from south inner wall
WINDOW_W = 6.0
WINDOW_SILL = 3.0
WINDOW_LINTEL = 7.0
CHAJJA_DEPTH = 1.75  # concrete sunshade outside, above the lintel

PASSAGE_W = 5.0  # entry passage at the SW corner, running west from the room
PASSAGE_LEN = 4 + 5 / 12
DOOR_W = 3.5  # door into the lobby at the passage's west end
DOOR_H = 7.0
DOOR_Y0 = (PASSAGE_W - DOOR_W) / 2

SKIRTING_H = 4 / 12
SKIRTING_T = 0.4 / 12

# Desk on the north wall
DESK_X0, DESK_X1 = ROOM_W - 9.5, ROOM_W - 2.5  # 2'-6" .. 9'-6" from the east wall
DESK_D = 2.5
DESK_H = 2.5  # top surface (30")
DESK_TOP_T = 1 / 12
MON_CX = 5.9  # centre of the dual-monitor setup
PEDESTAL = dict(x0=2.7, x1=4.05, d=1.7, h=2.05)

# Storage wall on the south wall
STORE_X0, STORE_X1 = ROOM_W - 10.0, ROOM_W - 1.5  # 1'-6" .. 10'-0" from the east wall
BASE_H = 2.75  # closed cabinets incl. oak top (2'-9")
BASE_D = 1.5
PLINTH_H = 4 / 12
SHELF_TOP = 8 + 5 / 12  # open shelves up to 8'-5"
SHELF_D = 1.0
BOARD_T = 1 / 12
SHELF_BOARDS = [4.125, 5.5, 6.875]  # underside of the intermediate shelf boards
N_BAYS = 3

# Round table group near the window
TABLE_C = (ROOM_W - 4.25, 5 + 2 / 12)  # 4'-3" from east wall, 5'-2" from south wall
TABLE_D = 3.0
TABLE_H = 2.5
RUG_D = 6.0
TABLE_CHAIR_ANGLES = [35, 160, 275]  # where the 3 chairs sit around the table (deg, 0 = east)
TABLE_CHAIR_R = 2.05
PENDANT_DROP = 3.25  # pendant bottom above the table top

# West wall
WHITEBOARD = dict(yc=11.3, zc=4.9, w=4.0, h=3.0)
AC = dict(yc=11.3, z_top=9.45, w=2.95, h=0.98, d=0.72)
PLANTS = {"potted_plant_01": (10.85, 15.3, 20), "potted_plant_02": (0.95, 1.0, -30)}
OFFICE_CHAIRS = [("office_chair_1", (MON_CX, 12.65), 0.0), ("office_chair_2", (8.55, 12.35), 28.0)]

# Downlights (x, y) in the ceiling
DOWNLIGHTS = [(3.75, 2.55), (8.75, 2.55), (3.5, 8.6), (8.25, 9.4), (3.75, 14.45), (8.25, 14.45)]
SHELF_LED_W = 0.6  # warm LED strip under each shelf (per bay)
ART = dict(yc=4.1, zc=5.1, w=2.0, h=2.67)  # framed print on the east wall, south of the window

# Lighting / exposure
SUN_AZIMUTH = 95.0  # compass bearing of the sun (90 = due east); elevation comes from the HDRI
HDRI_CLAMP = 20.0  # HDRI pixels brighter than this are moved into the sun lamp
SUN_ANGLE = 0.9  # sun lamp angular diameter (deg)
DOWNLIGHT_W = 5.0
DOWNLIGHT_K = 3500
PENDANT_W = 18.0
SCREEN_NITS = 1.6  # emission strength of the monitor/laptop screens
EXPOSURE = 2.35
WHITE_BALANCE_K = 4700
WHITE_BALANCE_TINT = -6.0

CAMERA_H = 4.25  # 4'-3"
VIEWS = {
    "entrance": dict(file="01_entrance.png", pos=(-0.85, 1.35, CAMERA_H), heading=41.0, lens=24, shift_x=0.0, shift_y=0.02, hide=[], exposure=EXPOSURE, wb=4300),
    "desk": dict(file="02_desk_videocall.png", pos=(6.1, 13.0, CAMERA_H), heading=-90.0, lens=24, shift_x=0.0, shift_y=0.0, hide=["office_chair_1"], exposure=EXPOSURE + 0.3, wb=3600),
    "cutaway": dict(file="03_cutaway.png", pos=(3.6, -12.5, 31.0), target=(3.9, 8.1, 0.0), lens=31, hide=[], cutaway=True, exposure=EXPOSURE + 0.5, wb=4300),
}

QUALITY = {
    "preview": dict(res=(640, 400), samples=32),
    "final": dict(res=(1920, 1200), samples=256),
}

# =============================================================================
# Derived helpers
# =============================================================================
DESK_Y0 = ROOM_L - DESK_D
M = {}  # materials
A = {}  # appended asset prototypes
REG = {}  # name -> list of objects (per-view visibility)
C = {}  # collections


def reg(key, *objs):
    REG.setdefault(key, []).extend(objs)
    return objs[0] if len(objs) == 1 else objs


def F(*v):
    """feet -> metres Vector/scalar."""
    if len(v) == 1:
        return v[0] * L.FT
    return Vector([x * L.FT for x in v])


def fbox(name, p0, p1, mats, coll, **kw):
    """Box with corners in feet."""
    return L.box_obj(name, F(*p0), F(*p1), mats, coll, **kw)


# =============================================================================
# Materials
# =============================================================================
def build_materials():
    tex = fa.PH_TEXTURES
    ph = {n: {k: v for k, v in fa.fetch_ph_texture(n, r).items()} for n, r in tex.items()}
    acg = {n: fa.acg_maps(n) for n in fa.ACG_TEXTURES}
    plaster = acg["PaintedPlaster017"]

    M["wall"] = L.pbr_mat("wall_warm_white", plaster, size=2.2, color=srgb("#ECE7DE"), color_var=0.08, rough=(0.72, 0.9), normal=0.18)
    M["accent"] = L.pbr_mat("wall_slate", plaster, size=2.2, color=srgb("#3D4850"), color_var=0.10, rough=(0.7, 0.88), normal=0.18)
    M["ceiling"] = L.pbr_mat("ceiling", plaster, size=2.5, color=srgb("#F2F0EB"), color_var=0.04, rough=(0.8, 0.95), normal=0.08)
    M["section"] = L.simple_mat("section_cut", srgb("#121212"), rough=0.95, spec=0.2)
    M["floor"] = L.pbr_mat("floor_wood_tile", ph["laminate_floor_02"], size=1.7, rough=(0.16, 0.42), normal=0.5, coat=0.35, coat_rough=0.12, value=1.0, sat=0.78)
    M["fabric_oat"] = L.pbr_mat("fabric_oatmeal", acg["Fabric031"], size=0.25, tint=srgb("#CFC6B8"), value=1.25, sat=0.4, normal=0.8, rough=(0.8, 0.95), sheen=0.6)
    M["oak"] = L.pbr_mat("oak", ph["oak_veneer_01"], size=1.4, rough=(0.38, 0.62), normal=0.35, coat=0.2, coat_rough=0.25)
    M["teak"] = L.pbr_mat("door_teak", ph["oak_veneer_01"], size=1.2, rough=(0.3, 0.55), normal=0.3, value=0.55, tint=srgb("#C88A5A"), coat=0.35, coat_rough=0.18)
    M["white_lacquer"] = L.simple_mat("white_lacquer", srgb("#F1EFEA"), rough=0.3, coat=0.15, coat_rough=0.2)
    M["upvc"] = L.simple_mat("upvc_white", srgb("#F4F4F1"), rough=0.28, spec=0.5)
    M["black_metal"] = L.simple_mat("black_powdercoat", srgb("#1C1C1D"), rough=0.42, bump=0.06, bump_scale=900)
    M["alu"] = L.pbr_mat("brushed_alu", acg["Metal032"], size=0.6, metallic=1.0, tint=srgb("#D0D3D6"), rough=(0.22, 0.38), normal=0.3)
    M["space_grey"] = L.simple_mat("space_grey_alu", srgb("#6E7074"), rough=0.32, metallic=1.0)
    M["chrome"] = L.simple_mat("chrome", srgb("#E8E8E8"), rough=0.06, metallic=1.0)
    M["brass"] = L.simple_mat("brass", srgb("#C9A25B"), rough=0.25, metallic=1.0)
    M["plastic_black"] = L.simple_mat("plastic_black", srgb("#151516"), rough=0.5, bump=0.05, bump_scale=1500)
    M["plastic_dark"] = L.simple_mat("plastic_dark", srgb("#2A2B2E"), rough=0.45)
    M["plastic_white"] = L.simple_mat("plastic_white", srgb("#EFEFEC"), rough=0.32)
    M["rubber"] = L.simple_mat("rubber", srgb("#101010"), rough=0.75)
    M["keycap"] = L.simple_mat("keycap", srgb("#303134"), rough=0.55)
    M["keycap_light"] = L.simple_mat("keycap_light", srgb("#D9D9D6"), rough=0.5)
    M["fabric_chair"] = L.pbr_mat("chair_fabric", acg["Fabric031"], size=0.25, tint=srgb("#5A5E63"), value=0.55, normal=0.8, rough=(0.75, 0.95), sheen=0.5)
    M["mesh"] = L.mesh_fabric_mat("chair_mesh")
    M["glass"] = L.thin_glass_mat("window_glass")
    M["glass_cup"] = L.thin_glass_mat("drinking_glass", tint=(0.93, 0.95, 0.95, 1))
    M["sheer"] = L.sheer_mat("sheer_curtain", ph["rough_linen"], opacity=0.5)
    M["granite"] = L.simple_mat("granite_sill", srgb("#26272A"), rough=0.14, bump=0.02, bump_scale=400)
    M["felt"] = L.simple_mat("felt_pad", srgb("#3B3E42"), rough=0.9, sheen=0.6, bump=0.1, bump_scale=2500)
    M["paper"] = L.simple_mat("paper", srgb("#F3F0E8"), rough=0.85)
    M["phone"] = L.simple_mat("phone_glass", srgb("#0B0B0C"), rough=0.08, coat=1.0)
    M["mug"] = L.simple_mat("mug_glaze", srgb("#2F5E66"), rough=0.2, coat=0.5)
    M["mug_inside"] = L.simple_mat("mug_inside", srgb("#EDE9E0"), rough=0.2)
    M["coffee"] = L.simple_mat("coffee", srgb("#2A160B"), rough=0.1)
    M["ceramic_sage"] = L.simple_mat("ceramic_sage", srgb("#9AA58E"), rough=0.6)
    M["ceramic_sand"] = L.simple_mat("ceramic_sand", srgb("#D8CBB5"), rough=0.7, bump=0.15, bump_scale=300)
    M["terracotta"] = L.simple_mat("terracotta", srgb("#B86B4B"), rough=0.75, bump=0.2, bump_scale=250)
    M["steel"] = L.simple_mat("steel_bottle", srgb("#C5C8CA"), rough=0.22, metallic=1.0)
    M["downlight"] = L.simple_mat("downlight_diffuser", (1, 1, 1, 1), rough=0.3, emission=(*kelvin(DOWNLIGHT_K), 1), emission_strength=40.0)
    M["led_red"] = L.simple_mat("led_red", srgb("#FF2A1A"), emission=srgb("#FF2A1A"), emission_strength=3.0)
    M["led_blue"] = L.simple_mat("led_blue", srgb("#3BA0FF"), emission=srgb("#3BA0FF"), emission_strength=2.0)
    M["socket"] = L.simple_mat("socket_white", srgb("#F6F6F3"), rough=0.22, coat=0.3)
    M["hole"] = L.simple_mat("socket_hole", srgb("#0A0A0A"), rough=0.9)
    M["whiteboard_frame"] = M["alu"]
    M["marker_blue"] = L.simple_mat("marker_blue", srgb("#1D3FA8"), rough=0.4)
    M["marker_black"] = L.simple_mat("marker_black", srgb("#1B1B1D"), rough=0.4)
    M["rug"] = rug_material(acg["Carpet016"])

    M["screen_code"] = L.image_mat("screen_code", L.np_to_image("img_code", L.screen_code()), emission=SCREEN_NITS, rough=0.18)
    M["screen_dash"] = L.image_mat("screen_dash", L.np_to_image("img_dash", L.screen_dashboard()), emission=SCREEN_NITS * 0.8, rough=0.18)
    M["screen_mail"] = L.image_mat("screen_mail", L.np_to_image("img_mail", L.screen_mail()), emission=SCREEN_NITS * 0.8, rough=0.1, coat=0.6)
    M["art"] = L.image_mat("art_print", L.np_to_image("img_art", L.art_print()), rough=0.8, spec=0.3)
    led = L.simple_mat("led_strip", (1, 1, 1, 1), rough=0.4)
    nt = led.node_tree
    b = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    lp = nt.nodes.new("ShaderNodeLightPath")
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = 2.5
    nt.links.new(lp.outputs["Is Camera Ray"], mul.inputs[0])
    b.inputs["Emission Color"].default_value = (*kelvin(3000), 1)
    nt.links.new(mul.outputs[0], b.inputs["Emission Strength"])
    M["led_strip"] = led
    M["whiteboard"] = L.image_mat("whiteboard_surface", L.np_to_image("img_whiteboard", L.whiteboard_image()), rough=0.07, spec=0.6, coat=0.6)


def rug_material(maps):
    m = L.pbr_mat("rug", maps, size=0.9, tint=srgb("#D8CDBE"), value=1.0, normal=1.0, rough=(0.85, 1.0), sheen=0.8)
    nt = m.node_tree
    N, Lk = nt.nodes, nt.links
    b = next(n for n in N if n.bl_idname == "ShaderNodeBsdfPrincipled")
    src = b.inputs["Base Color"].links[0].from_socket
    tc = N.new("ShaderNodeTexCoord")
    ln = N.new("ShaderNodeVectorMath")
    ln.operation = "LENGTH"
    sep = N.new("ShaderNodeSeparateXYZ")
    Lk.new(tc.outputs["Object"], sep.inputs[0])
    cmb = N.new("ShaderNodeCombineXYZ")
    Lk.new(sep.outputs[0], cmb.inputs[0])
    Lk.new(sep.outputs[1], cmb.inputs[1])
    Lk.new(cmb.outputs[0], ln.inputs[0])
    ramp = N.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "EASE"
    r = F(RUG_D) / 2
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (1, 1, 1, 1)
    els[1].position, els[1].color = (r - 0.16) / r, (1, 1, 1, 1)
    for pos, col in (((r - 0.15) / r, srgb("#5B4A3C")), ((r - 0.11) / r, srgb("#5B4A3C")), ((r - 0.10) / r, (1, 1, 1, 1))):
        e = els.new(pos)
        e.color = col
    div = N.new("ShaderNodeMath")
    div.operation = "DIVIDE"
    div.inputs[1].default_value = r
    Lk.new(ln.outputs["Value"], div.inputs[0])
    Lk.new(div.outputs[0], ramp.inputs["Fac"])
    mx = N.new("ShaderNodeMix")
    mx.data_type = "RGBA"
    mx.blend_type = "MULTIPLY"
    mx.inputs[0].default_value = 1.0
    Lk.new(src, mx.inputs[6])
    Lk.new(ramp.outputs["Color"], mx.inputs[7])
    Lk.new(mx.outputs[2], b.inputs["Base Color"])
    return m


# =============================================================================
# Assets
# =============================================================================
def load_assets():
    coll = C["protos"]
    single = ["dining_chair_02", "modern_ceiling_lamp_01", "ceramic_vase_01", "brass_vase_03", "carved_wooden_elephant", "standing_picture_frame_02", "round_spectacles", "wall_clock"]
    for n in single:
        objs = L.append_objects(fa.ph_model_blend(n), coll)
        A[n] = L.join_objects(objs, n)
    for n in ("potted_plant_01", "potted_plant_02", "potted_plant_04"):
        A[n] = L.join_objects(L.append_objects(fa.ph_model_blend(n), coll), n)
    A["books"] = [o for o in L.append_objects(fa.ph_model_blend("decorative_book_set_01"), coll) if o.type == "MESH"]
    A["ency"] = sorted(
        [o for o in L.append_objects(fa.ph_model_blend("book_encyclopedia_set_01"), coll, skip_names=("Sphere_stash_0",)) if o.type == "MESH"],
        key=lambda o: o.name,
    )
    A["notepads"] = {o.name: o for o in L.append_objects(fa.ph_model_blend("office_notepads"), coll)}
    A["stationery"] = {o.name: o for o in L.append_objects(fa.ph_model_blend("stationery_supplies"), coll)}
    C["protos"].hide_render = True
    C["protos"].hide_viewport = True


def instance(proto, name, coll, loc_m, rot_z_deg=0.0, scale=1.0, rot=None):
    ob = proto.copy()
    ob.name = name
    ob.location = loc_m
    ob.rotation_euler = rot if rot is not None else (0, 0, math.radians(rot_z_deg))
    ob.scale = (scale, scale, scale)
    coll.objects.link(ob)
    return ob


def instance_on(proto, name, coll, xy_ft, z_ft, rot_z_deg=0.0, scale=1.0):
    """Place proto so its (scaled, rotated) bbox bottom sits on z and its bbox centre is at xy."""
    ob = proto.copy()
    ob.name = name
    coll.objects.link(ob)
    R = Matrix.Rotation(math.radians(rot_z_deg), 3, "Z") @ Matrix.Diagonal((scale, scale, scale))
    L.place_by_bbox(ob, R, xc=F(xy_ft[0]), yc=F(xy_ft[1]), zmin=F(z_ft))
    return ob


def append_rigged(blend, name, coll, loc_m, rot_z_deg):
    objs = L.append_objects(blend, coll)
    root = L.empty(name, coll, loc=loc_m, rot_z=math.radians(rot_z_deg))
    for o in objs:
        # helpers driven by Child Of constraints already follow the (re-parented) rig
        if o.parent is None and not any(c.type == "CHILD_OF" for c in o.constraints):
            L.parent_to(o, root)
    return root, objs


# =============================================================================
# Architecture
# =============================================================================
def build_architecture():
    c = C["arch"]
    wall, accent, sec = M["wall"], M["accent"], M["section"]
    top = {"+z": 1}
    xw0 = -PASSAGE_LEN - T_WEST  # outer face of the door wall
    E0, E1 = ROOM_W, ROOM_W + T_EAST

    # --- floor & ceiling slabs (room + passage) ---
    sides = {"-x": 1, "+x": 1, "-y": 1, "+y": 1, "-z": 1}
    fbox("floor_room", (-T_WEST, -T_SOUTH, -0.5), (E1, ROOM_L + T_NORTH, 0), [M["floor"], sec], c, face_mats=sides)
    fbox("floor_passage", (xw0, -T_SOUTH, -0.5), (-T_WEST, PASSAGE_W + T_WEST, 0), [M["floor"], sec], c, face_mats=sides)
    ceil = [
        fbox("ceiling_room", (-T_WEST, -T_SOUTH, CEIL_H), (E1, ROOM_L + T_NORTH, CEIL_H + 0.5), M["ceiling"], c),
        fbox("ceiling_passage", (xw0, -T_SOUTH, CEIL_H), (-T_WEST, PASSAGE_W + T_WEST, CEIL_H + 0.5), M["ceiling"], c),
    ]
    reg("cut", *ceil)

    # --- east wall with the window opening ---
    wy0, wy1 = WINDOW_Y0, WINDOW_Y0 + WINDOW_W
    fbox("wall_E_south", (E0, -T_SOUTH, 0), (E1, wy0, CEIL_H), [wall, sec], c, face_mats={"+z": 1, "-y": 1, "+x": 1})
    fbox("wall_E_north", (E0, wy1, 0), (E1, ROOM_L + T_NORTH, CEIL_H), [wall, sec], c, face_mats=top)
    fbox("wall_E_below_sill", (E0, wy0, 0), (E1, wy1, WINDOW_SILL - 1 / 12), [wall, sec], c)
    fbox("wall_E_above_lintel", (E0, wy0, WINDOW_LINTEL), (E1, wy1, CEIL_H), [wall, sec], c, face_mats=top)
    reg("outside", fbox("chajja", (E1, wy0 - 0.5, WINDOW_LINTEL + 0.35), (E1 + CHAJJA_DEPTH, wy1 + 0.5, WINDOW_LINTEL + 0.7), M["wall"], c, bevel=0.01))

    # --- north wall: slate accent on the room face ---
    fbox("wall_N", (-T_WEST, ROOM_L, 0), (E1, ROOM_L + T_NORTH, CEIL_H), [wall, sec, accent], c, face_mats={"+z": 1, "-x": 1, "+y": 1, "-y": 2})

    # --- south wall (runs along the passage too) ---
    reg("cut", fbox("wall_S", (xw0, -T_SOUTH, 0), (E1, 0, CEIL_H), [wall, sec], c, face_mats=top))

    # --- west wall (partition to the pantry), from the passage to the north wall ---
    reg("cut", fbox("wall_W", (-T_WEST, PASSAGE_W, 0), (0, ROOM_L + T_NORTH, CEIL_H), [wall, sec], c, face_mats=top))
    # passage north wall (pantry side)
    reg("cut", fbox("wall_passage_N", (xw0, PASSAGE_W, 0), (-T_WEST, PASSAGE_W + T_WEST, CEIL_H), [wall, sec], c, face_mats=top))
    # door wall at the far end of the passage
    dy0, dy1 = DOOR_Y0, DOOR_Y0 + DOOR_W
    reg(
        "cut",
        fbox("wall_door_S", (xw0, -T_SOUTH, 0), (-PASSAGE_LEN, dy0, CEIL_H), [wall, sec], c, face_mats=top),
        fbox("wall_door_N", (xw0, dy1, 0), (-PASSAGE_LEN, PASSAGE_W + T_WEST, CEIL_H), [wall, sec], c, face_mats=top),
        fbox("wall_door_head", (xw0, dy0, DOOR_H), (-PASSAGE_LEN, dy1, CEIL_H), [wall, sec], c, face_mats=top),
    )

    build_skirting()
    build_window()
    build_door()
    build_downlights()


def build_skirting():
    c = C["arch"]
    h, t = SKIRTING_H, SKIRTING_T
    runs = [
        ("sk_N", (0, ROOM_L - t, 0), (ROOM_W, ROOM_L, h), False),
        ("sk_E", (ROOM_W - t, 0, 0), (ROOM_W, ROOM_L, h), False),
        ("sk_W", (0, PASSAGE_W, 0), (t, ROOM_L, h), True),
        ("sk_S_room_w", (-PASSAGE_LEN, 0, 0), (STORE_X0, t, h), True),
        ("sk_S_room_e", (STORE_X1, 0, 0), (ROOM_W, t, h), False),
        ("sk_passage_N", (-PASSAGE_LEN, PASSAGE_W - t, 0), (0, PASSAGE_W, h), True),
        ("sk_door_S", (-PASSAGE_LEN, 0, 0), (-PASSAGE_LEN + t, DOOR_Y0, h), True),
        ("sk_door_N", (-PASSAGE_LEN, DOOR_Y0 + DOOR_W, 0), (-PASSAGE_LEN + t, PASSAGE_W, h), True),
    ]
    for name, p0, p1, cut in runs:
        ob = fbox(name, p0, p1, M["floor"], c, bevel=0.002, segs=2)
        if cut:
            reg("cut", ob)


def build_window():
    c = C["arch"]
    wy0, wy1 = WINDOW_Y0, WINDOW_Y0 + WINDOW_W
    zs, zl = WINDOW_SILL, WINDOW_LINTEL
    x_in = ROOM_W
    # granite sill projecting 1" into the room
    fbox("window_sill", (x_in - 1.25 / 12, wy0 - 0.15, zs - 1 / 12), (x_in + 0.5, wy1 + 0.15, zs), M["granite"], c, bevel=0.003)
    # UPVC sliding window: outer frame + 2 sashes on offset tracks
    fx0, fx1 = x_in + 0.30, x_in + 0.52  # frame depth inside the wall
    fw = 2.6 / 12  # outer frame profile
    frame = [
        ((fx0, wy0, zs), (fx1, wy1, zs + fw)),
        ((fx0, wy0, zl - fw), (fx1, wy1, zl)),
        ((fx0, wy0, zs), (fx1, wy0 + fw, zl)),
        ((fx0, wy1 - fw, zs), (fx1, wy1, zl)),
    ]
    for i, (p0, p1) in enumerate(frame):
        fbox(f"window_frame_{i}", p0, p1, M["upvc"], c, bevel=0.003)
    sw = 2.0 / 12  # sash profile
    half = (WINDOW_W - 2 * fw) / 2
    for s in range(2):
        y0 = wy0 + fw + s * half - (0.12 if s else 0)
        y1 = y0 + half + 0.12
        xa = fx0 + 0.03 + s * 0.09
        xb = xa + 0.07
        z0, z1 = zs + fw, zl - fw
        parts = [((xa, y0, z0), (xb, y1, z0 + sw)), ((xa, y0, z1 - sw), (xb, y1, z1)), ((xa, y0, z0), (xb, y0 + sw, z1)), ((xa, y1 - sw, z0), (xb, y1, z1))]
        for i, (p0, p1) in enumerate(parts):
            fbox(f"window_sash{s}_{i}", p0, p1, M["upvc"], c, bevel=0.0025)
        fbox(f"window_glass{s}", ((xa + xb) / 2 - 0.005, y0 + sw - 0.02, z0 + sw - 0.02), ((xa + xb) / 2 + 0.005, y1 - sw + 0.02, z1 - sw + 0.02), M["glass"], c)
        # handle
        hy = y1 - sw - 0.05 if s == 0 else y0 + sw + 0.05
        fbox(f"window_handle{s}", (xa - 0.06, hy - 0.03, (z0 + z1) / 2 - 0.2), (xa, hy + 0.03, (z0 + z1) / 2 + 0.2), M["upvc"], c, bevel=0.004)

    # curtain rod + brackets + two sheer panels pulled to the sides
    rod_x, rod_z = ROOM_W - 0.3, WINDOW_LINTEL + 0.55
    ry0, ry1 = wy0 - 1.0, wy1 + 1.0
    bm = bmesh.new()
    L.bm_bar(bm, F(rod_x, ry0, rod_z), F(rod_x, ry1, rod_z), 0.011, segs=20)
    for y in (ry0 + 0.1, ry1 - 0.1):
        L.bm_bar(bm, F(rod_x, y, rod_z), F(ROOM_W, y, rod_z), 0.008, segs=12)
        L.bm_cyl(bm, 0.02, 0.012, loc=F(ROOM_W - 0.02, y, rod_z), rot=Euler((0, math.radians(90), 0)).to_quaternion())
    for y in (ry0, ry1):
        L.bm_cyl(bm, 0.016, 0.03, loc=F(rod_x, y - (0.03 / L.FT if y == ry0 else 0), rod_z), rot=Euler((math.radians(-90), 0, 0)).to_quaternion())
    L.mesh_obj("curtain_rod", bm, M["black_metal"], c)
    for name, (a, b) in (("curtain_S", (ry0 + 0.05, wy0 + 1.15)), ("curtain_N", (wy1 - 1.05, ry1 - 0.05))):
        sheer_panel(name, rod_x - 0.02, a, b, rod_z - 0.05, 0.08)


def sheer_panel(name, x, y0, y1, z_top, z_bot):
    """Gathered voile panel with vertical folds (feet in, metres out)."""
    rng = np.random.default_rng(len(name))
    nu, nv = 140, 60
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new()
    grid = []
    fold = 0.105  # metres per fold
    width_m = F(y1 - y0)
    for j in range(nv + 1):
        v = j / nv
        z = F(z_top + (z_bot - z_top) * v)
        row = []
        for i in range(nu + 1):
            u = i / nu
            y = F(y0) + u * width_m
            ph = 2 * math.pi * y / fold
            amp = 0.045 + 0.01 * math.sin(3.1 * y) + 0.012 * v
            xo = amp * math.sin(ph + 0.4 * math.sin(1.7 * y + v * 2.0)) + rng.normal(0, 0.0008)
            row.append(bm.verts.new((F(x) + xo, y, z)))
        grid.append(row)
    for j in range(nv):
        for i in range(nu):
            f = bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
            f.smooth = True
            for loop, (uu, vv) in zip(f.loops, ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))):
                loop[uv].uv = (uu / nu * width_m * 1.8, -vv / nv * F(z_top - z_bot))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(M["sheer"])
    ob = bpy.data.objects.new(name, me)
    C["arch"].objects.link(ob)
    return ob


def build_door():
    c = C["arch"]
    xd = -PASSAGE_LEN
    dy0, dy1 = DOOR_Y0, DOOR_Y0 + DOOR_W
    fw, proj = 4 / 12, 0.08  # frame width, projection into the passage
    parts = [
        fbox("door_frame_S", (xd - T_WEST, dy0, 0), (xd + proj, dy0 + fw, DOOR_H), M["teak"], C["arch"], bevel=0.003),
        fbox("door_frame_N", (xd - T_WEST, dy1 - fw, 0), (xd + proj, dy1, DOOR_H), M["teak"], C["arch"], bevel=0.003),
        fbox("door_frame_head", (xd - T_WEST, dy0, DOOR_H - fw), (xd + proj, dy1, DOOR_H), M["teak"], C["arch"], bevel=0.003, uv_rot=True),
        fbox("door_leaf", (xd - 0.05, dy0 + fw, 0.04), (xd + 0.07, dy1 - fw, DOOR_H - fw), M["teak"], C["arch"], bevel=0.002),
    ]
    bm = bmesh.new()
    hy, hz = dy1 - fw - 0.28, 3.3
    L.bm_cyl(bm, 0.028, 0.012, loc=F(xd + 0.07, hy, hz), rot=Euler((0, math.radians(90), 0)).to_quaternion())
    L.bm_bar(bm, F(xd + 0.07, hy, hz), F(xd + 0.25, hy, hz), 0.009)
    L.bm_bar(bm, F(xd + 0.25, hy, hz), F(xd + 0.25, hy - 0.42, hz), 0.009)
    L.bm_box(bm, F(xd + 0.07, hy - 0.035, hz - 0.55), F(xd + 0.075, hy + 0.035, hz - 0.35))
    parts.append(L.mesh_obj("door_handle", bm, M["alu"], c, bevel=0.001))
    reg("cut", *parts)


def build_downlights():
    c = C["arch"]
    for i, (x, y) in enumerate(DOWNLIGHTS):
        bm = bmesh.new()
        L.bm_cyl(bm, 0.075, 0.006, loc=F(x, y, CEIL_H - 0.02), segs=48)
        ring = L.mesh_obj(f"downlight_ring_{i}", bm, M["plastic_white"], c, bevel=0.002)
        bm = bmesh.new()
        L.bm_cyl(bm, 0.06, 0.002, loc=F(x, y, CEIL_H - 0.021), segs=48)
        disc = L.mesh_obj(f"downlight_diffuser_{i}", bm, M["downlight"], c)
        disc.visible_shadow = False
        reg("cut", ring, disc)
        lt = bpy.data.lights.new(f"downlight_{i}", "SPOT")
        lt.energy = DOWNLIGHT_W
        lt.color = kelvin(DOWNLIGHT_K)
        lt.spot_size = math.radians(88)
        lt.spot_blend = 0.4
        lt.shadow_soft_size = 0.035
        ob = bpy.data.objects.new(f"downlight_{i}", lt)
        ob.location = F(x, y, CEIL_H - 0.035)
        C["lights"].objects.link(ob)


# =============================================================================
# Desk zone
# =============================================================================
def build_desk():
    c = C["desk"]
    x0, x1, y0, y1 = DESK_X0, DESK_X1, DESK_Y0, ROOM_L - 0.04
    fbox("desk_top", (x0, y0, DESK_H - DESK_TOP_T), (x1, y1, DESK_H), M["oak"], c, bevel=0.003, uv_rot=True)
    leg = 2 / 12
    for i, (lx, ly) in enumerate(((x0 + 0.15, y0 + 0.12), (x1 - 0.15 - leg, y0 + 0.12), (x0 + 0.15, y1 - 0.15 - leg), (x1 - 0.15 - leg, y1 - 0.15 - leg))):
        fbox(f"desk_leg_{i}", (lx, ly, 0), (lx + leg, ly + leg, DESK_H - DESK_TOP_T), M["black_metal"], c, bevel=0.002)
        fbox(f"desk_foot_{i}", (lx - 0.01, ly - 0.01, 0), (lx + leg + 0.01, ly + leg + 0.01, 0.02), M["rubber"], c)
    rail = [((x0 + 0.15, y0 + 0.12, DESK_H - DESK_TOP_T - 2.5 / 12), (x1 - 0.15, y0 + 0.12 + 1 / 12, DESK_H - DESK_TOP_T)), ((x0 + 0.15, y1 - 0.15 - 1 / 12, DESK_H - DESK_TOP_T - 2.5 / 12), (x1 - 0.15, y1 - 0.15, DESK_H - DESK_TOP_T))]
    for side in (x0 + 0.15, x1 - 0.15 - 1 / 12):
        rail.append(((side, y0 + 0.12, DESK_H - DESK_TOP_T - 2.5 / 12), (side + 1 / 12, y1 - 0.15, DESK_H - DESK_TOP_T)))
    for i, (p0, p1) in enumerate(rail):
        fbox(f"desk_rail_{i}", p0, p1, M["black_metal"], c, bevel=0.002)
    # cable tray under the back edge
    fbox("cable_tray", (MON_CX - 1.8, y1 - 0.7, DESK_H - 0.55), (MON_CX + 1.8, y1 - 0.25, DESK_H - 0.5), M["black_metal"], c, bevel=0.002)
    fbox("cable_tray_lip", (MON_CX - 1.8, y1 - 0.7, DESK_H - 0.55), (MON_CX + 1.8, y1 - 0.68, DESK_H - 0.35), M["black_metal"], c)

    build_pedestal()
    build_monitors()
    build_keyboard_mouse()
    build_laptop()
    build_desk_items()
    build_switchboard("switchboard_desk", (9.05, ROOM_L, 3.45), "north", kind="sockets")


def build_pedestal():
    c = C["desk"]
    p = PEDESTAL
    x0, x1 = p["x0"], p["x1"]
    y0 = DESK_Y0 + 0.25
    y1 = y0 + p["d"]
    z0, z1 = 0.22, p["h"]
    fbox("pedestal_body", (x0, y0 + 0.06, z0), (x1, y1, z1 - 0.06), M["white_lacquer"], c, bevel=0.002)
    fbox("pedestal_top", (x0, y0 + 0.06, z1 - 0.06), (x1, y1, z1), M["oak"], c, bevel=0.002, uv_rot=True)
    hs = [(z0, z0 + 0.72), (z0 + 0.73, z0 + 1.2), (z0 + 1.21, z1 - 0.07)]
    for i, (a, b) in enumerate(hs):
        fbox(f"pedestal_drawer_{i}", (x0 + 0.01, y0, a + 0.01), (x1 - 0.01, y0 + 0.06, b - 0.01), M["white_lacquer"], c, bevel=0.0015)
        fbox(f"pedestal_pull_{i}", ((x0 + x1) / 2 - 0.25, y0 - 0.06, b - 0.1), ((x0 + x1) / 2 + 0.25, y0, b - 0.06), M["black_metal"], c, bevel=0.002)
    for i, (cx, cy) in enumerate(((x0 + 0.12, y0 + 0.2), (x1 - 0.12, y0 + 0.2), (x0 + 0.12, y1 - 0.2), (x1 - 0.12, y1 - 0.2))):
        bm = bmesh.new()
        L.bm_cyl(bm, 0.025, 0.018, loc=F(cx, cy, 0.0) + Vector((-0.009, 0, 0.025)), rot=Euler((0, math.radians(90), 0)).to_quaternion())
        L.bm_box(bm, F(cx, cy, 0) + Vector((-0.012, -0.02, 0.045)), F(cx, cy, 0) + Vector((0.012, 0.02, F(z0))))
        L.mesh_obj(f"pedestal_caster_{i}", bm, M["rubber"], c, bevel=0.002)


def monitor(name, centre_m, yaw_deg, screen_mat):
    """27-inch 16:9 monitor, screen facing -Y (local)."""
    c = C["desk"]
    g = L.empty(name, c, loc=centre_m, rot_z=math.radians(yaw_deg))
    W, H, D = 0.6135, 0.3665, 0.018
    L.box_obj(name + "_bezel", (-W / 2, -D / 2, -H / 2), (W / 2, D / 2, H / 2), M["plastic_black"], c, parent=g, bevel=0.004)
    L.box_obj(name + "_back", (-0.2, D / 2 - 0.002, -0.14), (0.2, D / 2 + 0.028, 0.12), M["plastic_black"], c, parent=g, bevel=0.012, segs=4)
    L.box_obj(name + "_vesa", (-0.055, D / 2 + 0.026, -0.055), (0.055, D / 2 + 0.036, 0.055), M["black_metal"], c, parent=g, bevel=0.002)
    # screen (active area) with explicit 0..1 UVs
    sw, sh = W - 0.014, H - 0.026
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new()
    vs = [bm.verts.new(p) for p in ((-sw / 2, -D / 2 - 0.0006, -sh / 2 + 0.006), (sw / 2, -D / 2 - 0.0006, -sh / 2 + 0.006), (sw / 2, -D / 2 - 0.0006, sh / 2 + 0.006), (-sw / 2, -D / 2 - 0.0006, sh / 2 + 0.006))]
    f = bm.faces.new(vs)
    for loop, t in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        loop[uv].uv = t
    L.mesh_obj(name + "_screen", bm, screen_mat, c, parent=g, uv=False)
    # small LED
    L.box_obj(name + "_led", (W / 2 - 0.03, -D / 2 - 0.001, -H / 2 + 0.003), (W / 2 - 0.026, -D / 2, -H / 2 + 0.006), M["led_blue"], c, parent=g)
    return g, Vector(centre_m) + Matrix.Rotation(math.radians(yaw_deg), 3, "Z") @ Vector((0, D / 2 + 0.036, 0))


def build_monitors():
    c = C["desk"]
    zc = F(DESK_H) + 0.36
    yc = F(DESK_Y0) + 0.60
    ang = 14
    offs = 0.318
    gL, vL = monitor("monitor_L", Vector((F(MON_CX) - offs, yc, zc)), ang, M["screen_code"])
    gR, vR = monitor("monitor_R", Vector((F(MON_CX) + offs, yc, zc)), -ang, M["screen_dash"])
    # dual monitor arm: desk clamp + pole + two 2-segment arms
    pole = Vector((F(MON_CX), F(ROOM_L) - 0.09, F(DESK_H)))
    bm = bmesh.new()
    L.bm_box(bm, pole + Vector((-0.035, -0.05, -0.06)), pole + Vector((0.035, 0.06, 0.012)))
    L.bm_cyl(bm, 0.022, 0.52, loc=pole)
    L.bm_cyl(bm, 0.03, 0.035, loc=pole + Vector((0, 0, 0.38)))
    top = pole + Vector((0, 0, 0.40))
    for v in (vL, vR):
        elbow = (top + v) / 2 + Vector((0, 0.1, 0))
        L.bm_bar(bm, top, Vector((elbow.x, elbow.y, top.z)), 0.017)
        L.bm_cyl(bm, 0.022, 0.05, loc=Vector((elbow.x, elbow.y, top.z - 0.025)))
        L.bm_bar(bm, Vector((elbow.x, elbow.y, top.z)), Vector((v.x, v.y + 0.05, v.z)), 0.016)
        L.bm_bar(bm, Vector((v.x, v.y + 0.05, v.z)), v, 0.02)
    L.mesh_obj("monitor_arm", bm, M["black_metal"], c, bevel=0.002)
    # power + display cables to the tray
    for i, v in enumerate((vL, vR)):
        L.cable(f"monitor_cable_{i}", [v + Vector((0.03 * (1 - 2 * i), 0.01, -0.12)), v + Vector((0.02, 0.06, -0.25)), Vector((v.x * 0.5 + pole.x * 0.5, pole.y - 0.02, F(DESK_H) + 0.02)), Vector((pole.x + 0.05 * (1 - 2 * i), pole.y + 0.02, F(DESK_H) - 0.1)), Vector((pole.x + 0.1, F(ROOM_L) - 0.35, F(DESK_H) - 0.16))], 0.0032, M["plastic_black"], c)


def keycap_grid(bm, x0, y0, rows, cols, pitch, size, h, z):
    for r in range(rows):
        for k in range(cols):
            x = x0 + k * pitch
            y = y0 + r * pitch
            L.bm_box(bm, (x, y, z), (x + size, y + size, z + h))


def build_keyboard_mouse():
    c = C["desk"]
    cx, cy, z = F(MON_CX) - 0.02, F(DESK_Y0) + 0.2, F(DESK_H)
    g = L.empty("keyboard", c, loc=(cx, cy, z), rot_z=math.radians(-2))
    L.box_obj("keyboard_body", (-0.215, -0.065, 0), (0.215, 0.065, 0.016), M["space_grey"], c, parent=g, bevel=0.003)
    bm = bmesh.new()
    keycap_grid(bm, -0.205, -0.036, 5, 22, 0.0186, 0.0158, 0.006, 0.014)
    L.bm_box(bm, (-0.09, -0.057, 0.014), (0.07, -0.0412, 0.02))
    for kx in (-0.205, -0.1864, -0.1678, 0.0886, 0.1072, 0.1258, 0.1444, 0.163, 0.1816):
        L.bm_box(bm, (kx, -0.057, 0.014), (kx + 0.0158, -0.0412, 0.02))
    L.mesh_obj("keyboard_keys", bm, M["keycap"], c, parent=g, bevel=0.0012, segs=2)
    # mouse pad + mouse
    mx, my = cx + 0.33, cy + 0.03
    L.box_obj("mouse_pad", (mx - 0.14, my - 0.12, z), (mx + 0.14, my + 0.12, z + 0.003), M["felt"], c, bevel=0.0015)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=1.0)
    for v in bm.verts:
        v.co.x *= 0.031
        v.co.y *= 0.058
        v.co.z = max(v.co.z, -0.1) * 0.036
        v.co.y += 0.012 * v.co.z / 0.036
    for f in bm.faces:
        f.smooth = True
    ms = L.mesh_obj("mouse", bm, M["plastic_black"], c, uv=False)
    ms.location = (mx + 0.01, my, z + 0.0036 + 0.0036)
    ms.rotation_euler = (0, 0, math.radians(-8))


def build_laptop():
    c = C["desk"]
    cx, cy, z = F(8.45), F(DESK_Y0) + 0.33, F(DESK_H)
    g = L.empty("laptop", c, loc=(cx, cy, z), rot_z=math.radians(-10))
    W, Dp, T = 0.312, 0.221, 0.0155
    L.box_obj("laptop_base", (-W / 2, -Dp / 2, 0.001), (W / 2, Dp / 2, T), M["space_grey"], c, parent=g, bevel=0.004, segs=4)
    bm = bmesh.new()
    keycap_grid(bm, -0.135, -0.005, 5, 14, 0.0193, 0.0165, 0.0008, T - 0.0002)
    L.bm_box(bm, (-0.0885, 0.0915, T - 0.0002), (0.0885, 0.1, T + 0.0006))
    L.mesh_obj("laptop_keys", bm, M["keycap"], c, parent=g, bevel=0.0006, segs=1)
    L.box_obj("laptop_trackpad", (-0.065, -0.1, T - 0.0001), (0.065, -0.018, T + 0.0002), M["plastic_dark"], c, parent=g, bevel=0.001)
    hinge = L.empty("laptop_hinge", c, loc=(0, Dp / 2 - 0.004, T), rot=(math.radians(-108), 0, 0))
    L.parent_to(hinge, g)
    Wl, Ll, Tl = W, 0.214, 0.006
    L.box_obj("laptop_lid", (-Wl / 2, -Ll, 0), (Wl / 2, 0, Tl), M["space_grey"], c, parent=hinge, bevel=0.003)
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new()
    sw, sl, m = Wl - 0.018, Ll - 0.03, 0.01
    vs = [bm.verts.new(p) for p in ((-sw / 2, -m, -0.0004), (sw / 2, -m, -0.0004), (sw / 2, -m - sl, -0.0004), (-sw / 2, -m - sl, -0.0004))]
    f = bm.faces.new(vs)
    for loop, t in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        loop[uv].uv = t
    L.mesh_obj("laptop_screen", bm, M["screen_mail"], c, parent=hinge, uv=False)
    L.box_obj("laptop_bezel", (-Wl / 2 + 0.002, -Ll + 0.002, -0.0003), (Wl / 2 - 0.002, -0.002, 0.0), M["phone"], c, parent=hinge)
    # charger cable from the left side, across the desk to the socket on the wall
    base = g.matrix_world
    p0 = Vector((cx - 0.17, cy + 0.05, z + 0.006))
    L.cable("laptop_cable", [p0, p0 + Vector((-0.08, 0.1, -0.004)), Vector((F(8.7), F(ROOM_L) - 0.12, z + 0.004)), Vector((F(9.0), F(ROOM_L) - 0.02, z + 0.12)), Vector((F(9.05) - 0.03, F(ROOM_L) - 0.02, F(3.45) - 0.02))], 0.0025, M["plastic_white"], c)


def build_desk_items():
    c = C["desk"]
    z = DESK_H
    # desk lamp (rigged Poly Haven asset) at the back-left corner, head turned toward the desk
    lamp, _ = append_rigged(fa.ph_model_blend("desk_lamp_arm_01"), "desk_lamp", c, F(3.05, ROOM_L - 0.6, z), -125)
    L.cable("desk_lamp_cable", [F(3.05, ROOM_L - 0.45, z) + Vector((0, 0.02, 0.005)), F(3.1, ROOM_L - 0.15, z) + Vector((0, 0, 0.003)), F(3.2, ROOM_L - 0.05, z - 0.3), F(3.4, ROOM_L - 0.05, 0.3)], 0.0028, M["plastic_black"], c)
    # pencil cup with a few pens standing in it
    st = A["stationery"]
    cup = instance(st["stationery_supplies_pencilcup"], "pencil_cup", c, (0, 0, 0))
    L.place_by_bbox(cup, Matrix.Identity(3), xc=F(3.95), yc=F(ROOM_L - 0.55), zmin=F(z))
    cc = cup.matrix_world.translation
    for i, key in enumerate(("stationery_supplies_pen_blue", "stationery_supplies_pencil_new_a", "stationery_supplies_pen_red", "stationery_supplies_pencil_new_b")):
        p = instance(st[key], f"pen_{i}", c, (0, 0, 0))
        a = i * 1.6
        R = Matrix.Rotation(0.14, 3, Vector((math.cos(a), math.sin(a), 0))) @ Matrix.Rotation(math.radians(90), 3, "Y")
        L.place_by_bbox(p, R, xc=cc.x + 0.012 * math.cos(a), yc=cc.y + 0.012 * math.sin(a), zmin=F(z) + 0.006)
    # notepad + pen
    pad = instance(A["notepads"]["office_notepads_yellow_pad"], "notepad", c, (0, 0, 0))
    L.place_by_bbox(pad, Matrix.Rotation(math.radians(14), 3, "Z"), xc=F(4.45), yc=F(DESK_Y0 + 0.75), zmin=F(z))
    pen = instance(st["stationery_supplies_pen_fancy"], "desk_pen", c, (0, 0, 0))
    L.place_by_bbox(pen, Matrix.Rotation(math.radians(70), 3, "Z"), xc=F(4.55), yc=F(DESK_Y0 + 0.78), zmin=F(z) + 0.01)
    # phone
    g = L.empty("phone", c, loc=F(4.85, DESK_Y0 + 0.45, z), rot_z=math.radians(-18))
    L.box_obj("phone_body", (-0.036, -0.075, 0), (0.036, 0.075, 0.0082), M["phone"], c, parent=g, bevel=0.006, segs=5)
    L.box_obj("phone_camera", (-0.028, 0.035, -0.0006), (-0.006, 0.066, 0.0005), M["space_grey"], c, parent=g, bevel=0.002)
    # coffee mug
    bm = bmesh.new()
    prof = [(0, 0), (0.037, 0), (0.039, 0.004), (0.041, 0.09), (0.0415, 0.095), (0.0375, 0.095), (0.0355, 0.09), (0.0345, 0.008), (0, 0.008)]
    L.bm_lathe(bm, prof, segs=48)
    mug = L.mesh_obj("mug", bm, M["mug"], c, uv=False)
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, radius=0.035, segments=48)
    cof = L.mesh_obj("mug_coffee", bm, M["coffee"], c, uv=False)
    cof.location.z = 0.078
    L.parent_to(cof, mug)
    tor_ob = torus_handle("mug_handle", 0.026, 0.0055)
    L.parent_to(tor_ob, mug)
    tor_ob.location = (0.045, 0, 0.048)
    mug.location = F(7.25, DESK_Y0 + 0.62, z)
    mug.rotation_euler.z = math.radians(-35)
    # spectacles
    instance_on(A["round_spectacles"], "spectacles", c, (7.75, DESK_Y0 + 1.25), z, rot_z_deg=160)
    # wall clock on the slate wall above the monitors
    clock = instance(A["wall_clock"], "wall_clock", c, (0, 0, 0))
    L.place_by_bbox(clock, Matrix.Identity(3), xc=F(MON_CX), ymax=F(ROOM_L) - 0.002, zmin=F(7.0))


def torus_handle(name, R, r):
    bm = bmesh.new()
    segs, rs = 32, 12
    rings = []
    for i in range(segs + 1):
        a = -math.pi / 2 + math.pi * i / segs
        cx, cz = R * math.cos(a), R * math.sin(a)
        ring = []
        for j in range(rs):
            b = 2 * math.pi * j / rs
            d = r * math.cos(b)
            ring.append(bm.verts.new((cx + d * math.cos(a), r * math.sin(b), cz + d * math.sin(a))))
        rings.append(ring)
    for i in range(segs):
        for j in range(rs):
            f = bm.faces.new((rings[i][j], rings[i][(j + 1) % rs], rings[i + 1][(j + 1) % rs], rings[i + 1][j]))
            f.smooth = True
    return L.mesh_obj(name, bm, M["mug"], C["desk"], uv=False)


def build_switchboard(name, pos_ft, wall, kind="sockets"):
    """Indian modular switch plate (white), mounted on a wall. wall: 'north' or 'west'."""
    c = C["desk"]
    x, y, z = pos_ft
    if wall == "north":
        g = L.empty(name, c, loc=F(x, y, z), rot_z=0.0)
    else:  # west wall: plate faces +X
        g = L.empty(name, c, loc=F(x, y, z), rot_z=math.radians(90))
    # local: plate in XZ plane, facing -Y (away from wall)
    Wp = 0.2 if kind == "sockets" else 0.26
    Hp = 0.125
    L.box_obj(name + "_plate", (-Wp / 2, -0.011, -Hp / 2), (Wp / 2, 0, Hp / 2), M["socket"], c, parent=g, bevel=0.004, segs=4)
    bm_sw = bmesh.new()
    bm_led = bmesh.new()
    bm_hole = bmesh.new()
    bm_face = bmesh.new()

    def rocker(cx):
        L.bm_box(bm_sw, (cx - 0.0095, -0.02, -0.02), (cx + 0.0095, -0.011, 0.02))
        L.bm_box(bm_sw, (cx - 0.0085, -0.023, 0.0), (cx + 0.0085, -0.02, 0.018))
        L.bm_box(bm_led, (cx - 0.002, -0.0212, 0.024), (cx + 0.002, -0.0112, 0.028))

    def socket(cx, big):
        r = 0.026 if big else 0.02
        L.bm_cyl(bm_face, r, 0.006, loc=(cx, -0.011, 0.0), rot=Euler((math.radians(90), 0, 0)).to_quaternion(), segs=40)
        hr = 0.0035 if big else 0.0026
        for dx, dz in ((-0.011, -0.007), (0.011, -0.007), (0.0, 0.011)):
            s = 1.25 if big else 1.0
            L.bm_cyl(bm_hole, hr, 0.0012, loc=(cx + dx * s, -0.0172, dz * s), rot=Euler((math.radians(90), 0, 0)).to_quaternion(), segs=12)

    if kind == "sockets":
        socket(-0.058, True)
        rocker(-0.012)
        socket(0.036, False)
        rocker(0.078)
    else:
        for i in range(6):
            rocker(-0.105 + i * 0.026)
        # fan regulator knob
        L.bm_cyl(bm_face, 0.02, 0.012, loc=(0.085, -0.011, 0.0), rot=Euler((math.radians(90), 0, 0)).to_quaternion(), segs=40)
    L.mesh_obj(name + "_switches", bm_sw, M["socket"], c, parent=g, bevel=0.0012, segs=2)
    L.mesh_obj(name + "_leds", bm_led, M["led_red"], c, parent=g)
    L.mesh_obj(name + "_holes", bm_hole, M["hole"], c, parent=g)
    L.mesh_obj(name + "_faces", bm_face, M["socket"], c, parent=g, bevel=0.0015, segs=2)
    return g


# =============================================================================
# Office chairs (procedural ergonomic mesh chair, facing +Y)
# =============================================================================
def office_chair(name, xy_ft, yaw_deg):
    c = C["chairs"]
    g = L.empty(name, c, loc=F(xy_ft[0], xy_ft[1], 0), rot_z=math.radians(yaw_deg))
    parts = [g]
    rng = np.random.default_rng(sum(map(ord, name)))
    # 5-star base
    bm = bmesh.new()
    for i in range(5):
        a = math.radians(90 + i * 72)
        R = Matrix.Rotation(a, 4, "Z")
        verts, _ = L.bm_box(bm, (0.03, -0.024, 0.075), (0.315, 0.024, 0.112))
        Ri = R.inverted()
        for v in verts:
            t = (v.co.x - 0.03) / 0.285
            v.co.y *= 1 - 0.35 * t
            v.co.z = 0.075 + (v.co.z - 0.075) * (1 - 0.45 * t)
            v.co = R @ v.co
    L.bm_cyl(bm, 0.052, 0.075, loc=(0, 0, 0.06), segs=32)
    parts.append(L.mesh_obj(name + "_base", bm, M["plastic_black"], c, parent=g, bevel=0.004))
    # casters
    bm_w, bm_h = bmesh.new(), bmesh.new()
    for i in range(5):
        a = math.radians(90 + i * 72)
        px, py = 0.3 * math.cos(a), 0.3 * math.sin(a)
        roll = a + rng.uniform(-0.6, 0.6)
        ax = Vector((math.cos(roll + math.pi / 2), math.sin(roll + math.pi / 2), 0))
        q = Vector((0, 0, 1)).rotation_difference(ax)
        for off in (0.004, -0.019):
            L.bm_cyl(bm_w, 0.027, 0.015, loc=Vector((px, py, 0.027)) + ax * off, rot=q, segs=24)
        L.bm_box(bm_h, (px - 0.012, py - 0.012, 0.045), (px + 0.012, py + 0.012, 0.08))
    parts.append(L.mesh_obj(name + "_wheels", bm_w, M["plastic_black"], c, parent=g, bevel=0.003))
    parts.append(L.mesh_obj(name + "_caster_forks", bm_h, M["plastic_black"], c, parent=g, bevel=0.004))
    # gas lift
    bm = bmesh.new()
    L.bm_cyl(bm, 0.028, 0.2, loc=(0, 0, 0.1))
    parts.append(L.mesh_obj(name + "_gas_cover", bm, M["plastic_black"], c, parent=g))
    bm = bmesh.new()
    L.bm_cyl(bm, 0.014, 0.11, loc=(0, 0, 0.295))
    parts.append(L.mesh_obj(name + "_gas", bm, M["chrome"], c, parent=g))
    # mechanism + lever
    bm = bmesh.new()
    L.bm_box(bm, (-0.12, -0.12, 0.395), (0.12, 0.1, 0.45))
    L.bm_bar(bm, (0.12, 0.03, 0.42), (0.21, 0.07, 0.41), 0.006)
    parts.append(L.mesh_obj(name + "_mechanism", bm, M["plastic_black"], c, parent=g, bevel=0.005))
    # seat pan + cushion
    parts.append(L.box_obj(name + "_seat_pan", (-0.24, -0.22, 0.445), (0.24, 0.22, 0.465), M["plastic_black"], c, parent=g, bevel=0.012, segs=3))
    bm = bmesh.new()
    verts, _ = L.bm_box(bm, (-0.25, -0.235, 0.46), (0.25, 0.245, 0.535))
    for v in verts:  # waterfall front, slightly narrower back
        if v.co.y > 0:
            v.co.z -= 0.012
        if v.co.y < 0:
            v.co.x *= 0.94
    parts.append(L.mesh_obj(name + "_seat", bm, M["fabric_chair"], c, parent=g, bevel=0.03, segs=5, subsurf=1))
    # mesh back: curved grid
    nu, nv = 28, 36
    z0, z1 = 0.6, 1.14

    def back_pt(u, v):
        hw = 0.235 - 0.03 * (v - 0.55) ** 2 - (0.035 if v > 0.9 else 0) * (v - 0.9) * 10
        x = u * hw
        z = z0 + v * (z1 - z0)
        y = -0.24 - 0.13 * v + 0.07 * u * u + 0.03 * math.exp(-((v - 0.25) / 0.16) ** 2)
        return Vector((x, y, z))

    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new()
    grid = [[bm.verts.new(back_pt(-1 + 2 * i / nu, j / nv)) for i in range(nu + 1)] for j in range(nv + 1)]
    for j in range(nv):
        for i in range(nu):
            f = bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
            f.smooth = True
            for loop in f.loops:
                loop[uvl].uv = (loop.vert.co.x, loop.vert.co.z)
    parts.append(L.mesh_obj(name + "_back_mesh", bm, M["mesh"], c, parent=g, uv=False))
    # back frame (tube around the mesh)
    ring = [back_pt(-1 + 2 * i / nu, 0) for i in range(nu + 1)] + [back_pt(1, j / nv) for j in range(1, nv + 1)]
    ring += [back_pt(1 - 2 * i / nu, 1) for i in range(1, nu + 1)] + [back_pt(-1, 1 - j / nv) for j in range(1, nv)]
    cu = bpy.data.curves.new(name + "_frame", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 0.012
    cu.bevel_resolution = 3
    sp = cu.splines.new("POLY")
    sp.points.add(len(ring) - 1)
    for p, co in zip(sp.points, ring):
        p.co = (*co, 1)
    sp.use_cyclic_u = True
    cu.materials.append(M["plastic_black"])
    fr = bpy.data.objects.new(name + "_frame", cu)
    c.objects.link(fr)
    L.parent_to(fr, g)
    parts.append(fr)
    # spine connecting the mechanism to the back
    bm = bmesh.new()
    pts = [Vector((0, -0.1, 0.42)), Vector((0, -0.25, 0.44)), Vector((0, -0.31, 0.55)), back_pt(0, 0.3) + Vector((0, -0.03, 0))]
    for a, b in zip(pts, pts[1:]):
        L.bm_bar(bm, a, b, 0.022)
    parts.append(L.mesh_obj(name + "_spine", bm, M["plastic_black"], c, parent=g))
    # armrests
    bm = bmesh.new()
    for s in (-1, 1):
        L.bm_box(bm, (s * 0.12, -0.06, 0.405), (s * 0.28, -0.02, 0.43))
        L.bm_box(bm, (s * 0.265 - 0.013, -0.075, 0.405), (s * 0.265 + 0.013, -0.02, 0.665))
    parts.append(L.mesh_obj(name + "_arm_posts", bm, M["plastic_black"], c, parent=g, bevel=0.004))
    bm = bmesh.new()
    for s in (-1, 1):
        L.bm_box(bm, (s * 0.265 - 0.04, -0.17, 0.665), (s * 0.265 + 0.04, 0.08, 0.692))
    parts.append(L.mesh_obj(name + "_arm_pads", bm, M["plastic_dark"], c, parent=g, bevel=0.011, segs=4))
    reg(name, *parts)
    return g


# =============================================================================
# Storage wall (south)
# =============================================================================
def build_storage():
    c = C["storage"]
    x0, x1 = STORE_X0, STORE_X1
    # plinth, carcass, doors, oak top
    fbox("storage_plinth", (x0 + 0.08, 0, 0), (x1 - 0.08, BASE_D - 0.25, PLINTH_H), M["plastic_dark"], c)
    fbox("storage_carcass", (x0, 0, PLINTH_H), (x1, BASE_D - 0.06, BASE_H - BOARD_T), M["white_lacquer"], c, bevel=0.002)
    n = 6
    dw = (x1 - x0) / n
    for i in range(n):
        a, b = x0 + i * dw + 0.006, x0 + (i + 1) * dw - 0.006
        fbox(f"storage_door_{i}", (a, BASE_D - 0.06, PLINTH_H + 0.01), (b, BASE_D, BASE_H - BOARD_T - 0.012), M["white_lacquer"], c, bevel=0.0015)
        hx = b - 0.12 if i % 2 == 0 else a + 0.08
        fbox(f"storage_pull_{i}", (hx, BASE_D, BASE_H - BOARD_T - 0.55), (hx + 0.04, BASE_D + 0.07, BASE_H - BOARD_T - 0.18), M["black_metal"], c, bevel=0.003)
    fbox("storage_top", (x0 - 0.02, 0, BASE_H - BOARD_T), (x1 + 0.02, BASE_D + 0.02, BASE_H), M["oak"], c, bevel=0.003, uv_rot=True)
    # open oak shelving above
    inner = (x1 - x0 - (N_BAYS + 1) * BOARD_T) / N_BAYS
    ups = [x0 + i * (inner + BOARD_T) for i in range(N_BAYS + 1)]
    for i, ux in enumerate(ups):
        fbox(f"shelf_upright_{i}", (ux, 0, BASE_H), (ux + BOARD_T, SHELF_D, SHELF_TOP), M["oak"], c, bevel=0.002, uv_offset=(i * 0.37, 0))
    boards = SHELF_BOARDS + [SHELF_TOP - BOARD_T]
    for i, zb in enumerate(boards):
        for b in range(N_BAYS):
            bx0 = ups[b] + BOARD_T
            fbox(f"shelf_board_{i}_{b}", (bx0, 0, zb), (bx0 + inner, SHELF_D, zb + BOARD_T), M["oak"], c, bevel=0.002, uv_rot=True, uv_offset=(0.3 * b + 0.11 * i, 0.2 * i))
    # hidden warm LED strip under each shelf (front edge) - subtle glow on the backdrop
    levels = [BASE_H] + [zb + BOARD_T for zb in SHELF_BOARDS]
    bays = [(ups[b] + BOARD_T, ups[b] + BOARD_T + inner) for b in range(N_BAYS)]
    fill_shelves(levels, bays)
    for lvl, zb in enumerate(SHELF_BOARDS + [SHELF_TOP - BOARD_T]):
        for b, (bx0, bx1) in enumerate(bays):
            y = SHELF_D - 0.12
            strip = fbox(f"shelf_led_{lvl}_{b}", (bx0 + 0.04, y - 0.03, zb - 0.012), (bx1 - 0.04, y + 0.03, zb), M["led_strip"], c)
            strip.visible_shadow = False
            lt = bpy.data.lights.new(f"shelf_led_{lvl}_{b}", "AREA")
            lt.shape = "RECTANGLE"
            lt.size = F(bx1 - bx0 - 0.1)
            lt.size_y = 0.012
            lt.energy = SHELF_LED_W
            lt.color = kelvin(3000)
            lo = bpy.data.objects.new(f"shelf_led_{lvl}_{b}", lt)
            lo.location = F((bx0 + bx1) / 2, y, zb - 0.02)
            C["lights"].objects.link(lo)


def fill_shelves(levels, bays):
    c = C["decor"]
    rng = np.random.default_rng(7)
    pool = list(A["books"])
    rng.shuffle(pool)
    it = {"i": 0}

    def next_book():
        b = pool[it["i"] % len(pool)]
        it["i"] += 1
        return b

    ency = A["ency"]
    front = F(SHELF_D) - 0.035
    upright = Matrix.Rotation(math.pi, 3, "Z")

    def lathe_obj(name, prof, mat, segs=48):
        bm = bmesh.new()
        L.bm_lathe(bm, prof, segs=segs)
        ob = L.mesh_obj(name, bm, mat, C["protos"], uv=False)
        return ob

    protos = {
        "vase": (A["ceramic_vase_01"], 0.78, 0),
        "brass": (A["brass_vase_03"], 1.0, 0),
        "elephant": (A["carved_wooden_elephant"], 1.25, 200),
        "frame": (A["standing_picture_frame_02"], 1.0, 180),
        "succ": (A["potted_plant_04"], 1.0, 30),
        "bottle": (lathe_obj("bottle_vase", [(0, 0), (0.05, 0), (0.055, 0.01), (0.056, 0.12), (0.045, 0.17), (0.016, 0.2), (0.014, 0.26), (0.018, 0.265), (0.012, 0.265), (0.01, 0.2), (0, 0.2)], M["ceramic_sage"]), 1.0, 0),
        "jar": (lathe_obj("sand_jar", [(0, 0), (0.06, 0), (0.068, 0.02), (0.07, 0.11), (0.058, 0.15), (0.04, 0.155), (0.04, 0.165), (0, 0.165)], M["ceramic_sand"]), 1.0, 0),
        "bowl": (lathe_obj("terracotta_bowl", [(0, 0), (0.04, 0), (0.08, 0.025), (0.1, 0.06), (0.094, 0.062), (0.075, 0.03), (0.035, 0.008), (0, 0.008)], M["terracotta"]), 1.0, 0),
    }

    def rotated_extent(ob, R):
        pts = [R @ Vector(p) for p in ob.bound_box]
        return max(p.x for p in pts) - min(p.x for p in pts)

    count = {"n": 0}

    def put(proto, R, xmin, z, ymax=None, yc=None, scale=1.0):
        ob = proto.copy()
        count["n"] += 1
        ob.name = f"{proto.name}_{count['n']}"
        c.objects.link(ob)
        S = R @ Matrix.Diagonal((scale, scale, scale))
        return L.place_by_bbox(ob, S, xmin=xmin, ymax=ymax, yc=yc, zmin=z), ob

    def fill(level, bay, tokens, align="L"):
        z = F(levels[level])
        bx0, bx1 = F(bays[bay][0]) + 0.02, F(bays[bay][1]) - 0.02
        # expand tokens into concrete placements (proto, rotation, scale, gap_after)
        items = []
        for tok in tokens:
            kind = tok[0]
            if kind == "b":
                for _ in range(tok[1]):
                    items.append((next_book(), upright, 1.0, 0.0015, None))
            elif kind == "e":
                for k in range(tok[1]):
                    items.append((ency[k], upright, 1.0, 0.0005, None))
            elif kind == "lean":
                b = next_book()
                items.append((b, Matrix.Rotation(math.radians(tok[1]), 3, "Y") @ upright, 1.0, 0.004, None))
            elif kind == "stack":
                books = [next_book() for _ in range(tok[1])]
                items.append(("stack", books, tok[2] if len(tok) > 2 else None, 0.05, None))
            elif kind == "o":
                proto, sc, rz = protos[tok[1]]
                items.append((proto, Matrix.Rotation(math.radians(rz), 3, "Z"), sc, 0.05, None))
            elif kind == "gap":
                items.append(("gap", tok[1], None, 0.0, None))
        widths = []
        for it_ in items:
            if it_[0] == "gap":
                widths.append(it_[1])
            elif it_[0] == "stack":
                lay = Matrix.Rotation(math.radians(90), 3, "Y") @ upright
                widths.append(max(rotated_extent(b, lay) for b in it_[1]) + it_[3])
            else:
                widths.append(rotated_extent(it_[0], it_[1]) * it_[2] + it_[3])
        total = sum(widths)
        x = bx0 if align == "L" else (bx1 - total if align == "R" else (bx0 + bx1 - total) / 2)
        for it_, w in zip(items, widths):
            if it_[0] == "gap":
                pass
            elif it_[0] == "stack":
                zz = z
                lay = Matrix.Rotation(math.radians(90), 3, "Y") @ upright
                wmax = w - it_[3]
                for k, b in enumerate(it_[1]):
                    jitter = Matrix.Rotation(rng.uniform(-0.06, 0.06), 3, "Z")
                    ob = b.copy()
                    ob.name = b.name + f"_stk{count['n']}"
                    count["n"] += 1
                    c.objects.link(ob)
                    ext = L.place_by_bbox(ob, jitter @ lay, xc=x + wmax / 2 + rng.uniform(-0.01, 0.01), ymax=front - rng.uniform(0, 0.02), zmin=zz)
                    zz += ext.z
                if it_[2]:
                    proto, sc, rz = protos[it_[2]]
                    ob = proto.copy()
                    ob.name = f"{proto.name}_top{count['n']}"
                    count["n"] += 1
                    c.objects.link(ob)
                    L.place_by_bbox(ob, Matrix.Rotation(math.radians(rz), 3, "Z") @ Matrix.Diagonal((sc, sc, sc)), xc=x + wmax / 2, yc=front - 0.1, zmin=zz)
            else:
                proto, R, sc, gap, _ = it_
                if proto in A["books"] or proto in ency:
                    put(proto, R, x, z, ymax=front - rng.uniform(0, 0.012), scale=sc)
                else:
                    put(proto, R, x, z, yc=F(SHELF_D) / 2 + 0.02, scale=sc)
            x += w

    # --- styling: (level, bay) -> tokens ---
    fill(0, 0, [("b", 13), ("gap", 0.06), ("o", "frame")], "L")
    fill(0, 1, [("o", "vase"), ("gap", 0.08), ("stack", 3, "bowl")], "C")
    fill(0, 2, [("e", 20), ("gap", 0.05), ("o", "jar")], "L")
    fill(1, 0, [("stack", 4, "brass"), ("gap", 0.06), ("b", 9), ("lean", -14)], "L")
    fill(1, 1, [("b", 15), ("lean", 16), ("gap", 0.12), ("o", "succ")], "L")
    fill(1, 2, [("o", "bottle"), ("gap", 0.08), ("stack", 3), ("gap", 0.03), ("b", 6)], "R")
    fill(2, 0, [("o", "jar"), ("gap", 0.06), ("o", "bowl")], "C")
    fill(2, 1, [("stack", 5, "elephant"), ("gap", 0.05), ("b", 10)], "L")
    fill(2, 2, [("b", 17), ("lean", 12)], "R")
    fill(3, 0, [("b", 14), ("gap", 0.07), ("o", "succ")], "L")
    fill(3, 1, [("o", "bottle"), ("gap", 0.06), ("o", "brass")], "C")
    fill(3, 2, [("lean", -14), ("b", 8), ("gap", 0.06), ("stack", 2, "jar")], "R")


# =============================================================================
# Round table group
# =============================================================================
def build_table_zone():
    c = C["table"]
    cx, cy = TABLE_C
    # rug (round, with bound edge)
    bm = bmesh.new()
    L.bm_cyl(bm, F(RUG_D) / 2, 0.009, loc=(0, 0, 0), segs=160)
    rug = L.mesh_obj("rug", bm, M["rug"], c, bevel=0.004, segs=3)
    rug.location = F(cx, cy, 0)
    # table: oak top on a black pedestal
    g = L.empty("round_table", c, loc=F(cx, cy, 0))
    bm = bmesh.new()
    L.bm_cyl(bm, F(TABLE_D) / 2, 0.028, loc=(0, 0, F(TABLE_H) - 0.028), segs=128)
    L.mesh_obj("table_top", bm, M["oak"], c, parent=g, bevel=0.005, segs=4)
    bm = bmesh.new()
    L.bm_cyl(bm, 0.04, F(TABLE_H) - 0.06, loc=(0, 0, 0.02), segs=40)
    L.bm_cyl(bm, 0.16, 0.025, loc=(0, 0, F(TABLE_H) - 0.058), segs=48)
    L.bm_lathe(bm, [(0, 0.0), (0.26, 0.0), (0.26, 0.012), (0.2, 0.03), (0.05, 0.05), (0, 0.05)], segs=64)
    L.mesh_obj("table_base", bm, M["black_metal"], c, parent=g, bevel=0.002)
    # three chairs facing the centre
    for i, th in enumerate(TABLE_CHAIR_ANGLES):
        a = math.radians(th)
        px, py = cx + TABLE_CHAIR_R * math.cos(a), cy + TABLE_CHAIR_R * math.sin(a)
        dining_chair(f"table_chair_{i}", (px, py), th + 90 + (6 if i == 1 else -4))
    # pendant light above the table, rod stretched so the shade hangs at PENDANT_DROP
    p = A["modern_ceiling_lamp_01"].copy()
    p.data = p.data.copy()
    p.name = "pendant"
    c.objects.link(p)
    z_bottom = F(TABLE_H + PENDANT_DROP)
    zs = [v.co.z for v in p.data.vertices]
    zmin, zmax = min(zs), max(zs)
    L.stretch_above(p, zmin + 0.45, F(CEIL_H) - z_bottom - (zmax - zmin))
    p.location = F(cx, cy, 0) + Vector((0, 0, z_bottom - zmin))
    lt = bpy.data.lights.new("pendant_bulb", "POINT")
    lt.energy = PENDANT_W
    lt.color = kelvin(3000)
    lt.shadow_soft_size = 0.04
    lo = bpy.data.objects.new("pendant_bulb", lt)
    lo.location = F(cx, cy, 0) + Vector((0, 0, z_bottom + 0.19))
    C["lights"].objects.link(lo)
    # table-top items: succulent, notebook, steel bottle, glass
    instance_on(A["potted_plant_04"], "table_succulent", c, (cx - 0.1, cy + 0.15), TABLE_H, rot_z_deg=40)
    nb = instance(A["notepads"]["office_notepads_a4_stack"], "table_papers", c, (0, 0, 0))
    L.place_by_bbox(nb, Matrix.Rotation(math.radians(-25), 3, "Z"), xc=F(cx + 0.55), yc=F(cy - 0.45), zmin=F(TABLE_H))
    bm = bmesh.new()
    L.bm_lathe(bm, [(0, 0), (0.035, 0), (0.037, 0.005), (0.037, 0.2), (0.03, 0.225), (0.022, 0.235), (0.022, 0.26), (0, 0.26)], segs=48)
    bot = L.mesh_obj("steel_bottle", bm, M["steel"], c, uv=False)
    bot.location = F(cx - 0.6, cy - 0.35, TABLE_H)
    bm = bmesh.new()
    L.bm_lathe(bm, [(0, 0), (0.033, 0), (0.036, 0.11), (0.0335, 0.11), (0.0305, 0.006), (0, 0.006)], segs=48)
    gl = L.mesh_obj("water_glass", bm, M["glass_cup"], c, uv=False)
    gl.location = F(cx - 0.35, cy - 0.62, TABLE_H)


# =============================================================================
# West wall: whiteboard, split AC, light switches
# =============================================================================
def build_west_wall():
    c = C["west"]
    wb = WHITEBOARD
    y0, y1 = wb["yc"] - wb["w"] / 2, wb["yc"] + wb["w"] / 2
    z0, z1 = wb["zc"] - wb["h"] / 2, wb["zc"] + wb["h"] / 2
    fr = 0.09
    objs = []
    for i, (p0, p1) in enumerate((((0, y0, z0), (fr, y1, z0 + 0.08)), ((0, y0, z1 - 0.08), (fr, y1, z1)), ((0, y0, z0), (fr, y0 + 0.08, z1)), ((0, y1 - 0.08, z0), (fr, y1, z1)))):
        objs.append(fbox(f"whiteboard_frame_{i}", p0, p1, M["alu"], c, bevel=0.002))
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new()
    ya, yb, za, zb = F(y0 + 0.08), F(y1 - 0.08), F(z0 + 0.08), F(z1 - 0.08)
    xs = F(0.05)
    vs = [bm.verts.new(p) for p in ((xs, ya, za), (xs, yb, za), (xs, yb, zb), (xs, ya, zb))]
    f = bm.faces.new(vs)
    for loop, t in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        loop[uv].uv = t
    objs.append(L.mesh_obj("whiteboard_surface", bm, M["whiteboard"], c, uv=False))
    objs.append(fbox("whiteboard_backer", (0, y0 + 0.05, z0 + 0.05), (0.045, y1 - 0.05, z1 - 0.05), M["plastic_white"], c))
    objs.append(fbox("whiteboard_tray", (0, y0 + 0.6, z0 - 0.12), (0.28, y1 - 0.6, z0), M["alu"], c, bevel=0.002))
    for i, (mat, yy) in enumerate(((M["marker_blue"], wb["yc"] - 0.4), (M["marker_black"], wb["yc"] - 0.15))):
        bm = bmesh.new()
        L.bm_bar(bm, F(0.16, yy, z0 + 0.03), F(0.16, yy + 0.42, z0 + 0.03), 0.009)
        objs.append(L.mesh_obj(f"marker_{i}", bm, mat, c))
    objs.append(fbox("whiteboard_eraser", (0.05, wb["yc"] + 0.35, z0), (0.24, wb["yc"] + 0.8, z0 + 0.09), M["plastic_dark"], c, bevel=0.004))
    # split AC
    ac = AC
    ay0, ay1 = ac["yc"] - ac["w"] / 2, ac["yc"] + ac["w"] / 2
    az1 = ac["z_top"]
    az0 = az1 - ac["h"]
    objs.append(fbox("ac_body", (0, ay0, az0), (ac["d"], ay1, az1), M["plastic_white"], c, bevel=0.035, segs=5))
    objs.append(fbox("ac_vent", (ac["d"] - 0.28, ay0 + 0.15, az0 - 0.002), (ac["d"] - 0.05, ay1 - 0.15, az0 + 0.02), M["plastic_dark"], c))
    objs.append(fbox("ac_flap", (ac["d"] - 0.02, ay0 + 0.16, az0 + 0.02), (ac["d"] + 0.005, ay1 - 0.16, az0 + 0.2), M["plastic_white"], c, bevel=0.004))
    objs.append(fbox("ac_display", (ac["d"], ac["yc"] + 0.75, az0 + 0.35), (ac["d"] + 0.004, ac["yc"] + 1.0, az0 + 0.42), M["phone"], c))
    objs.append(fbox("ac_seam", (ac["d"] + 0.0005, ay0 + 0.03, az1 - 0.3), (ac["d"] + 0.002, ay1 - 0.03, az1 - 0.29), M["plastic_dark"], c))
    # drain/refrigerant pipe cover going up into the wall behind
    sb = build_switchboard("switchboard_entry", (0.0, 6.1, 4.0), "west", kind="lights")
    objs += [sb] + list(sb.children_recursive)
    for o in list(c.objects):
        if o not in objs:
            objs.append(o)
    reg("cut", *objs)


# =============================================================================
# Plants
# =============================================================================
def build_art():
    c = C["decor"]
    a = ART
    y0, y1 = a["yc"] - a["w"] / 2, a["yc"] + a["w"] / 2
    z0, z1 = a["zc"] - a["h"] / 2, a["zc"] + a["h"] / 2
    x = ROOM_W
    fw, fd = 0.09, 0.1  # frame width / depth (ft)
    for i, (p0, p1, rot) in enumerate((((x - fd, y0, z0), (x, y1, z0 + fw), True), ((x - fd, y0, z1 - fw), (x, y1, z1), True), ((x - fd, y0, z0), (x, y0 + fw, z1), False), ((x - fd, y1 - fw, z0), (x, y1, z1), False))):
        fbox(f"art_frame_{i}", p0, p1, M["oak"], c, bevel=0.0015, uv_rot=rot)
    fbox("art_mat", (x - fd + 0.03, y0 + fw, z0 + fw), (x - 0.01, y1 - fw, z1 - fw), M["paper"], c)
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new()
    m = 0.28  # mat border (ft)
    xs = F(x - fd + 0.029)
    ya, yb, za, zb = F(y0 + fw + m), F(y1 - fw - m), F(z0 + fw + m), F(z1 - fw - m)
    vs = [bm.verts.new(p) for p in ((xs, yb, za), (xs, ya, za), (xs, ya, zb), (xs, yb, zb))]
    f = bm.faces.new(vs)
    for loop, t in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        loop[uv].uv = t
    L.mesh_obj("art_print", bm, M["art"], c, uv=False)


def dining_chair(name, xy_ft, yaw_deg):
    """Scandinavian oak dining chair with an upholstered seat, facing +Y (local)."""
    c = C["table"]
    g = L.empty(name, c, loc=F(xy_ft[0], xy_ft[1], 0), rot_z=math.radians(yaw_deg))
    bm = bmesh.new()
    seat_z = 0.43
    legs = [((0.19, 0.18), (0.205, 0.2), 0.0), ((-0.19, 0.18), (-0.205, 0.2), 0.0), ((0.18, -0.17), (0.2, -0.22), 1), ((-0.18, -0.17), (-0.2, -0.22), 1)]
    for top, foot, back in legs:
        a = Vector((foot[0], foot[1], 0.0))
        b = Vector((top[0], top[1], seat_z))
        L.bm_cyl(bm, 0.0165, (b - a).length, loc=a, r2=0.021, rot=Vector((0, 0, 1)).rotation_difference(b - a), segs=20)
        if back:  # back legs rise into the backrest posts, raked backwards
            c2 = Vector((top[0] * 0.97, top[1] - 0.075, 0.79))
            L.bm_cyl(bm, 0.02, (c2 - b).length, loc=b, r2=0.015, rot=Vector((0, 0, 1)).rotation_difference(c2 - b), segs=20)
    for (x0, y0), (x1, y1) in (((0.2, 0.19), (0.19, -0.19)), ((-0.2, 0.19), (-0.19, -0.19)), ((0.2, 0.19), (-0.2, 0.19))):
        L.bm_bar(bm, (x0, y0, 0.17), (x1, y1, 0.17), 0.009, segs=12)
    # seat frame
    L.bm_box(bm, (-0.215, -0.19, seat_z - 0.045), (0.215, 0.215, seat_z))
    L.mesh_obj(name + "_frame", bm, M["oak"], c, parent=g, bevel=0.003)
    # curved backrest (bent plywood)
    bm = bmesh.new()
    n, rad, span = 24, 0.42, math.radians(62)
    ctr = Vector((0, 0.2, 0))
    ring = []
    for i in range(n + 1):
        ang = -math.pi / 2 - span / 2 + span * i / n
        col = []
        for rr in (rad, rad + 0.016):
            for z in (0.63, 0.79):
                zz = z + (0.012 if z > 0.7 else 0) * math.cos((i / n - 0.5) * math.pi)
                col.append(bm.verts.new((ctr.x + rr * math.cos(ang), ctr.y + rr * math.sin(ang) - 0.075, zz)))
        ring.append(col)
    for i in range(n):
        a, b = ring[i], ring[i + 1]
        for q in ((a[0], b[0], b[1], a[1]), (a[3], b[3], b[2], a[2]), (a[1], b[1], b[3], a[3]), (a[2], b[2], b[0], a[0])):
            f = bm.faces.new(q)
            f.smooth = True
    bm.faces.new((ring[0][0], ring[0][1], ring[0][3], ring[0][2]))
    bm.faces.new((ring[-1][2], ring[-1][3], ring[-1][1], ring[-1][0]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    L.mesh_obj(name + "_back", bm, M["oak"], c, parent=g, bevel=0.002, uv_rot=True)
    # upholstered seat pad
    bm = bmesh.new()
    L.bm_box(bm, (-0.205, -0.18, seat_z - 0.005), (0.205, 0.21, seat_z + 0.045))
    L.mesh_obj(name + "_cushion", bm, M["fabric_oat"], c, parent=g, bevel=0.018, segs=4, subsurf=1)
    return g


def build_plants():
    for name, (x, y, rz) in PLANTS.items():
        instance_on(A[name], name, C["decor"], (x, y), 0.0, rot_z_deg=rz, scale=1.0 if name == "potted_plant_01" else 1.1)


# =============================================================================
# World (HDRI with the sun extracted into a sun lamp) + portal
# =============================================================================
def build_world():
    sc = bpy.context.scene
    src = bpy.data.images.load(fa.hdri_path())
    w, h = src.size
    px = np.empty(w * h * 4, np.float32)
    src.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    rgb = px[..., :3]
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    el = ((np.arange(h) + 0.5) / h - 0.5) * np.pi
    dom = (2 * np.pi / w) * (np.pi / h) * np.cos(el)
    keep = np.minimum(1.0, HDRI_CLAMP / np.maximum(lum, 1e-9))
    excess = rgb * (1.0 - keep)[..., None]
    E = (excess * dom[:, None, None]).sum((0, 1))  # RGB irradiance of the removed sun
    wgt = (lum * (1.0 - keep)) * dom[:, None]
    phi = (0.5 - (np.arange(w) + 0.5) / w) * 2 * np.pi
    ce, se = np.cos(el)[:, None], np.sin(el)[:, None]
    d = np.array([(wgt * ce * np.cos(phi)[None]).sum(), (wgt * ce * np.sin(phi)[None]).sum(), (wgt * se).sum()])
    d /= np.linalg.norm(d)
    px[..., :3] = rgb * keep[..., None]
    img = bpy.data.images.new("hdri_sunless", w, h, alpha=True, float_buffer=True)
    img.pixels.foreach_set(px.ravel())
    bpy.data.images.remove(src)

    sun_el = math.asin(d[2])
    tex_az = math.atan2(d[1], d[0])
    want_az = math.radians(90.0 - SUN_AZIMUTH)
    rz = tex_az - want_az
    sun_strength = float(E @ np.array([0.2126, 0.7152, 0.0722]))
    sun_col = E / max(E.max(), 1e-9)
    print(f"[world] HDRI sun elevation {math.degrees(sun_el):.1f} deg, irradiance {sun_strength:.2f}, colour {sun_col.round(3)}")

    world = bpy.data.worlds.new("World")
    sc.world = world
    if bpy.app.version < (5, 0, 0):
        world.use_nodes = True
    nt = world.node_tree
    N, Lk = nt.nodes, nt.links
    for n in list(N):
        N.remove(n)
    tc = N.new("ShaderNodeTexCoord")
    mp = N.new("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value[2] = rz
    env = N.new("ShaderNodeTexEnvironment")
    env.image = img
    bg = N.new("ShaderNodeBackground")
    Lk.new(tc.outputs["Generated"], mp.inputs["Vector"])
    Lk.new(mp.outputs["Vector"], env.inputs["Vector"])
    Lk.new(env.outputs["Color"], bg.inputs["Color"])
    # cutaway: plain backdrop for camera rays only (lighting still comes from the HDRI)
    lp = N.new("ShaderNodeLightPath")
    flat = N.new("ShaderNodeBackground")
    flat.inputs["Color"].default_value = srgb("#E9E7E3")
    flat.inputs["Strength"].default_value = 1.0
    mul = N.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.name = "cutaway_switch"
    mul.inputs[1].default_value = 0.0
    Lk.new(lp.outputs["Is Camera Ray"], mul.inputs[0])
    mix = N.new("ShaderNodeMixShader")
    Lk.new(mul.outputs[0], mix.inputs[0])
    Lk.new(bg.outputs[0], mix.inputs[1])
    Lk.new(flat.outputs[0], mix.inputs[2])
    out = N.new("ShaderNodeOutputWorld")
    Lk.new(mix.outputs[0], out.inputs["Surface"])

    # sun lamp matched to the removed HDRI sun
    sd = Vector((math.cos(sun_el) * math.cos(want_az), math.cos(sun_el) * math.sin(want_az), math.sin(sun_el)))
    lt = bpy.data.lights.new("sun", "SUN")
    lt.energy = sun_strength
    lt.color = tuple(float(v) for v in sun_col)
    lt.angle = math.radians(SUN_ANGLE)
    sun = bpy.data.objects.new("sun", lt)
    sun.rotation_euler = sd.to_track_quat("Z", "Y").to_euler()
    C["lights"].objects.link(sun)

    # light portal over the window opening (outside face of the east wall)
    pl = bpy.data.lights.new("window_portal", "AREA")
    pl.shape = "RECTANGLE"
    pl.size = F(WINDOW_LINTEL - WINDOW_SILL)
    pl.size_y = F(WINDOW_W)
    pl.cycles.is_portal = True
    po = bpy.data.objects.new("window_portal", pl)
    po.location = F(ROOM_W + T_EAST + 0.02, WINDOW_Y0 + WINDOW_W / 2, (WINDOW_SILL + WINDOW_LINTEL) / 2)
    po.rotation_euler = (0, math.radians(90), 0)
    C["lights"].objects.link(po)
    return world


# =============================================================================
# Render setup, cameras, per-view visibility
# =============================================================================
def setup_render(quality):
    sc = bpy.context.scene
    q = QUALITY[quality]
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.device = "CPU"
    cy.samples = q["samples"]
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.01 if quality == "final" else 0.05
    cy.adaptive_min_samples = 0
    cy.use_denoising = True
    try:
        cy.denoiser = "OPENIMAGEDENOISE"
    except TypeError:
        pass
    cy.denoising_input_passes = "RGB_ALBEDO_NORMAL"
    try:
        cy.denoising_prefilter = "ACCURATE"
        cy.denoising_quality = "HIGH"
    except (TypeError, AttributeError):
        pass
    cy.max_bounces = 12
    cy.diffuse_bounces = 6
    cy.glossy_bounces = 4
    cy.transmission_bounces = 8
    cy.transparent_max_bounces = 32
    cy.volume_bounces = 0
    cy.sample_clamp_direct = 0.0
    cy.sample_clamp_indirect = 8.0
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.blur_glossy = 1.0
    cy.use_light_tree = True
    sc.render.resolution_x, sc.render.resolution_y = q["res"]
    sc.render.resolution_percentage = 100
    sc.render.use_persistent_data = True
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_depth = "8"
    vs = sc.view_settings
    vs.view_transform = "AgX"
    for look in ("AgX - Medium High Contrast", "Medium High Contrast"):
        try:
            vs.look = look
            break
        except TypeError:
            continue
    print(f"[render] view transform {vs.view_transform}, look '{vs.look}'")
    vs.exposure = EXPOSURE
    vs.gamma = 1.0
    try:
        vs.use_white_balance = True
        vs.white_balance_temperature = WHITE_BALANCE_K
    except AttributeError:
        pass


def make_camera(name, v):
    cam = bpy.data.cameras.new(name)
    cam.sensor_fit = "HORIZONTAL"
    cam.sensor_width = 36.0
    cam.lens = v["lens"]
    cam.clip_start = 0.05
    cam.clip_end = 100
    ob = bpy.data.objects.new(name, cam)
    ob.location = F(*v["pos"])
    if "target" in v:
        ob.rotation_euler = L.look_at_rotation(ob.location, F(*v["target"]))
    else:  # level camera (vertical lines stay vertical); heading = compass-free angle from +X
        ob.rotation_euler = (math.radians(90), 0, math.radians(v["heading"] - 90))
        cam.shift_x = v.get("shift_x", 0.0)
        cam.shift_y = v.get("shift_y", 0.0)
    C["cameras"].objects.link(ob)
    return ob


def apply_view(key, v):
    sc = bpy.context.scene
    for objs in REG.values():
        for o in objs:
            o.hide_render = False
            o.visible_camera = True
    for k in v.get("hide", []):
        for o in REG.get(k, []):
            o.hide_render = True
    cut = v.get("cutaway", False)
    for o in REG.get("cut", []) + REG.get("outside", []):
        o.visible_camera = not cut
    sc.world.node_tree.nodes["cutaway_switch"].inputs[1].default_value = 1.0 if cut else 0.0
    sc.camera = bpy.data.objects[f"cam_{key}"]
    sc.view_settings.exposure = v.get("exposure", EXPOSURE)
    try:
        sc.view_settings.white_balance_temperature = v.get("wb", WHITE_BALANCE_K)
        sc.view_settings.white_balance_tint = v.get("tint", WHITE_BALANCE_TINT)
    except AttributeError:
        pass


def build_scene():
    t0 = time.time()
    fa.fetch_all()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for n in ("arch", "desk", "chairs", "storage", "decor", "table", "west", "lights", "cameras"):
        C[n] = L.collection(n)
    C["protos"] = L.collection("_protos")
    build_materials()
    load_assets()
    build_architecture()
    build_desk()
    for name, xy, yaw in OFFICE_CHAIRS:
        office_chair(name, xy, yaw)
    build_storage()
    build_table_zone()
    build_west_wall()
    build_plants()
    build_art()
    build_world()
    for key, v in VIEWS.items():
        make_camera(f"cam_{key}", v)
    print(f"[scene] built in {time.time() - t0:.1f}s, {len(bpy.data.objects)} objects")


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--view", default="all", choices=["all", *VIEWS.keys()])
    ap.add_argument("--quality", default="preview", choices=list(QUALITY))
    ap.add_argument("--out", default=os.path.join(REPO, "renders"))
    ap.add_argument("--samples", type=int, default=None)
    ap.add_argument("--res", default=None, help="override resolution, e.g. 1280x800")
    ap.add_argument("--save-blend", default=None)
    ap.add_argument("--no-render", action="store_true")
    args = ap.parse_args(argv)

    build_scene()
    setup_render(args.quality)
    if args.samples:
        bpy.context.scene.cycles.samples = args.samples
    if args.res:
        w, h = (int(x) for x in args.res.lower().split("x"))
        bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y = w, h
    if args.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.save_blend))
    if args.no_render:
        return
    out_dir = args.out if args.quality == "final" else os.path.join(args.out, "previews")
    os.makedirs(out_dir, exist_ok=True)
    keys = list(VIEWS) if args.view == "all" else [args.view]
    times = {}
    for key in keys:
        v = VIEWS[key]
        apply_view(key, v)
        path = os.path.join(out_dir, v["file"])
        bpy.context.scene.render.filepath = path
        t = time.time()
        bpy.ops.render.render(write_still=True)
        times[key] = round(time.time() - t, 1)
        print(f"[render] {key}: {times[key]:.1f}s -> {path}", flush=True)
    tfile = os.path.join(out_dir, "render_times.json")
    old = {}
    if os.path.exists(tfile):
        with open(tfile) as f:
            old = json.load(f)
    old.update({k: {"seconds": s, "quality": args.quality, "samples": bpy.context.scene.cycles.samples, "resolution": list(QUALITY[args.quality]["res"])} for k, s in times.items()})
    with open(tfile, "w") as f:
        json.dump(old, f, indent=2)


if __name__ == "__main__":
    main()
