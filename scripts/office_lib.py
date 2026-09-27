"""Geometry, material, image and asset helpers for office_scene.py (Blender 5.x)."""

import math
import os

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Matrix, Quaternion, Vector

FT = 0.3048  # metres per foot


def ft(v):
    """feet -> metres (scalars or sequences)."""
    if isinstance(v, (int, float)):
        return v * FT
    return tuple(x * FT for x in v)


# ---------------------------------------------------------------------------
# Colour
# ---------------------------------------------------------------------------
def srgb(hexstr, a=1.0):
    """'#RRGGBB' (display sRGB) -> linear RGBA tuple for shader inputs."""
    h = hexstr.lstrip("#")
    c = [int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]
    lin = [((v + 0.055) / 1.055) ** 2.4 if v > 0.04045 else v / 12.92 for v in c]
    return (*lin, a)


def hex01(hexstr):
    """'#RRGGBB' -> sRGB 0..1 numpy triple (for painting byte images)."""
    h = hexstr.lstrip("#")
    return np.array([int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)


def kelvin(t):
    """Approximate black-body colour (linear RGB) for a colour temperature in K."""
    t = t / 100.0
    r = 255.0 if t <= 66 else 329.698727446 * ((t - 60) ** -0.1332047592)
    g = 99.4708025861 * math.log(t) - 161.1195681661 if t <= 66 else 288.1221695283 * ((t - 60) ** -0.0755148492)
    if t >= 66:
        b = 255.0
    elif t <= 19:
        b = 0.0
    else:
        b = 138.5177312231 * math.log(t - 10) - 305.0447927307
    c = [min(max(x, 0.0), 255.0) / 255.0 for x in (r, g, b)]
    return tuple(((v + 0.055) / 1.055) ** 2.4 if v > 0.04045 else v / 12.92 for v in c)


# ---------------------------------------------------------------------------
# Collections / objects
# ---------------------------------------------------------------------------
def collection(name, parent=None):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    parent = parent or bpy.context.scene.collection
    if c.name not in parent.children:
        parent.children.link(c)
    return c


def empty(name, coll, loc=(0, 0, 0), rot_z=0.0, rot=None):
    e = bpy.data.objects.new(name, None)
    e.empty_display_size = 0.15
    e.location = loc
    e.rotation_euler = rot if rot is not None else (0.0, 0.0, rot_z)
    coll.objects.link(e)
    return e


def parent_to(ob, parent):
    ob.parent = parent
    ob.matrix_parent_inverse = Matrix.Identity(4)


def set_input(node, name, value):
    sock = node.inputs.get(name)
    if sock is None:
        print(f"  [warn] {node.bl_idname} has no input '{name}'")
        return
    sock.default_value = value


# ---------------------------------------------------------------------------
# bmesh primitives (all dimensions in metres, in the object's local space)
# ---------------------------------------------------------------------------
def bm_box(bm, p0, p1, matrix=None, mat_index=0):
    """Axis-aligned box from corner p0 to p1, optionally transformed afterwards."""
    size = Vector(p1) - Vector(p0)
    centre = (Vector(p0) + Vector(p1)) / 2
    m = Matrix.Translation(centre) @ Matrix.Diagonal((*size, 1.0))
    if matrix is not None:
        m = matrix @ m
    res = bmesh.ops.create_cube(bm, size=1.0, matrix=m)
    faces = {f for v in res["verts"] for f in v.link_faces}
    for f in faces:
        f.material_index = mat_index
    return res["verts"], faces


def bm_cyl(bm, r, h, loc=(0, 0, 0), segs=32, r2=None, rot=None, mat_index=0):
    """Cylinder/cone standing on loc (base) along +Z, optionally rotated about loc."""
    m = Matrix.Translation(Vector(loc))
    if rot is not None:
        m = m @ rot.to_matrix().to_4x4()
    m = m @ Matrix.Translation((0, 0, h / 2))
    res = bmesh.ops.create_cone(
        bm, cap_ends=True, cap_tris=False, segments=segs, radius1=r, radius2=r if r2 is None else r2, depth=h, matrix=m
    )
    faces = {f for v in res["verts"] for f in v.link_faces}
    for f in faces:
        f.smooth = len(f.verts) == 4
        f.material_index = mat_index
    return res["verts"], faces


def bm_bar(bm, a, b, r, segs=16, mat_index=0):
    """Cylinder between points a and b."""
    a, b = Vector(a), Vector(b)
    d = b - a
    q = Vector((0, 0, 1)).rotation_difference(d.normalized())
    return bm_cyl(bm, r, d.length, loc=a, segs=segs, rot=q, mat_index=mat_index)


def bm_lathe(bm, profile, segs=48, loc=(0, 0, 0), mat_index=0, smooth=True):
    """Revolve a (radius, z) profile around Z. r=0 points collapse to a pole."""
    lx, ly, lz = loc
    rings = []
    for r, z in profile:
        if r < 1e-7:
            rings.append([bm.verts.new((lx, ly, lz + z))])
        else:
            rings.append(
                [
                    bm.verts.new((lx + r * math.cos(2 * math.pi * i / segs), ly + r * math.sin(2 * math.pi * i / segs), lz + z))
                    for i in range(segs)
                ]
            )
    faces = []
    for a, b in zip(rings, rings[1:]):
        if len(a) == 1 and len(b) == 1:
            continue
        for i in range(segs):
            j = (i + 1) % segs
            if len(a) == 1:
                faces.append(bm.faces.new((a[0], b[j], b[i])))
            elif len(b) == 1:
                faces.append(bm.faces.new((a[i], a[j], b[0])))
            else:
                faces.append(bm.faces.new((a[i], a[j], b[j], b[i])))
    for f in faces:
        f.smooth = smooth
        f.material_index = mat_index
    return faces


def bm_box_uv(bm, rot=False, scale=1.0, offset=(0.0, 0.0)):
    """Real-world-scale box projection UVs (1 UV unit = 1 m / scale)."""
    uv = bm.loops.layers.uv.verify()
    bm.normal_update()
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for loop in f.loops:
            co = loop.vert.co
            if ax == 2:
                u, v = co.x, co.y
            elif ax == 0:
                u, v = co.y, co.z
            else:
                u, v = co.x, co.z
            if rot:
                u, v = v, u
            loop[uv].uv = (u * scale + offset[0], v * scale + offset[1])


def mesh_obj(name, bm, mats, coll, parent=None, bevel=0.0, segs=3, uv=True, uv_rot=False, uv_offset=(0, 0), subsurf=0, smooth_all=False):
    if uv:
        bm_box_uv(bm, rot=uv_rot, offset=uv_offset)
    if smooth_all:
        for f in bm.faces:
            f.smooth = True
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats if isinstance(mats, (list, tuple)) else [mats]:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    if bevel > 0:
        for p in me.polygons:
            p.use_smooth = True
        mod = ob.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = segs
        mod.limit_method = "ANGLE"
        mod.angle_limit = math.radians(40)
        mod.harden_normals = True
    if subsurf:
        mod = ob.modifiers.new("Subsurf", "SUBSURF")
        mod.levels = subsurf
        mod.render_levels = subsurf
    if parent is not None:
        parent_to(ob, parent)
    return ob


def box_obj(name, p0, p1, mats, coll, parent=None, bevel=0.0, segs=3, uv_rot=False, face_mats=None, uv_offset=(0, 0)):
    """Box object. face_mats maps '+x','-x','+y','-y','+z','-z' -> material slot index."""
    bm = bmesh.new()
    _, faces = bm_box(bm, p0, p1)
    if face_mats:
        bm.normal_update()
        axes = {"+x": Vector((1, 0, 0)), "-x": Vector((-1, 0, 0)), "+y": Vector((0, 1, 0)), "-y": Vector((0, -1, 0)), "+z": Vector((0, 0, 1)), "-z": Vector((0, 0, -1))}
        for f in faces:
            for key, idx in face_mats.items():
                if f.normal.dot(axes[key]) > 0.99:
                    f.material_index = idx
    return mesh_obj(name, bm, mats, coll, parent=parent, bevel=bevel, segs=segs, uv_rot=uv_rot, uv_offset=uv_offset)


def cable(name, pts, radius, mat, coll, parent=None):
    """Smooth cable along points (bezier, auto handles)."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = 3
    cu.resolution_u = 16
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(pts) - 1)
    for bp, p in zip(sp.bezier_points, pts):
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    cu.materials.append(mat)
    ob = bpy.data.objects.new(name, cu)
    coll.objects.link(ob)
    if parent is not None:
        parent_to(ob, parent)
    return ob


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------
def _new_material(name):
    m = bpy.data.materials.new(name)
    if bpy.app.version < (5, 0, 0):
        m.use_nodes = True
    nt = m.node_tree
    bsdf = next((n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)
    out = next((n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial"), None)
    if out is None:
        out = nt.nodes.new("ShaderNodeOutputMaterial")
    if bsdf is None:
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    return m, nt, bsdf, out


def _img(nt, path, noncolor=False):
    n = nt.nodes.new("ShaderNodeTexImage")
    img = bpy.data.images.load(path, check_existing=True)
    if noncolor:
        img.colorspace_settings.name = "Non-Color"
    n.image = img
    return n


def simple_mat(name, color, rough=0.5, metallic=0.0, spec=0.5, coat=0.0, coat_rough=0.05, sheen=0.0, emission=None, emission_strength=0.0, bump=0.0, bump_scale=200.0):
    m, nt, b, _ = _new_material(name)
    set_input(b, "Base Color", color)
    set_input(b, "Roughness", rough)
    set_input(b, "Metallic", metallic)
    set_input(b, "Specular IOR Level", spec)
    if coat:
        set_input(b, "Coat Weight", coat)
        set_input(b, "Coat Roughness", coat_rough)
    if sheen:
        set_input(b, "Sheen Weight", sheen)
    if emission is not None:
        set_input(b, "Emission Color", emission)
        set_input(b, "Emission Strength", emission_strength)
    if bump:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = bump_scale
        nz.inputs["Detail"].default_value = 6.0
        nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
        bn = nt.nodes.new("ShaderNodeBump")
        bn.inputs["Strength"].default_value = bump
        bn.inputs["Distance"].default_value = 0.0005
        nt.links.new(nz.outputs["Fac"], bn.inputs["Height"])
        nt.links.new(bn.outputs["Normal"], b.inputs["Normal"])
    return m


def pbr_mat(name, maps, size=1.0, rot=0.0, color=None, color_var=0.0, tint=None, value=1.0, sat=1.0, rough=(None, None), normal=1.0, spec=0.5, coat=0.0, coat_rough=0.1, metallic=0.0, sheen=0.0):
    """Principled material from a PBR texture set with real-world tiling (size = metres per tile).

    color      -> use this flat colour instead of the diffuse map (e.g. painted walls)
    color_var  -> modulate that colour by the diffuse map's luminance (0 = off)
    tint       -> multiply the diffuse map by this colour
    rough      -> (min, max) remap of the roughness map
    """
    m, nt, b, _ = _new_material(name)
    N, L = nt.nodes, nt.links
    tc = N.new("ShaderNodeTexCoord")
    mp = N.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / size, 1 / size, 1 / size)
    mp.inputs["Rotation"].default_value[2] = rot
    L.new(tc.outputs["UV"], mp.inputs["Vector"])
    vec = mp.outputs["Vector"]

    if color is None and "diff" in maps:
        d = _img(nt, maps["diff"])
        L.new(vec, d.inputs["Vector"])
        col = d.outputs["Color"]
        if value != 1.0 or sat != 1.0:
            hs = N.new("ShaderNodeHueSaturation")
            hs.inputs["Saturation"].default_value = sat
            hs.inputs["Value"].default_value = value
            L.new(col, hs.inputs["Color"])
            col = hs.outputs["Color"]
        if tint is not None:
            mx = N.new("ShaderNodeMix")
            mx.data_type = "RGBA"
            mx.blend_type = "MULTIPLY"
            mx.inputs[0].default_value = 1.0
            L.new(col, mx.inputs[6])
            mx.inputs[7].default_value = tint
            col = mx.outputs[2]
        L.new(col, b.inputs["Base Color"])
    elif color is not None:
        if color_var > 0 and "diff" in maps:
            d = _img(nt, maps["diff"])
            L.new(vec, d.inputs["Vector"])
            bw = N.new("ShaderNodeRGBToBW")
            L.new(d.outputs["Color"], bw.inputs["Color"])
            # factor = 1 + color_var * (lum - 0.5)
            m1 = N.new("ShaderNodeMath")
            m1.operation = "MULTIPLY_ADD"
            L.new(bw.outputs[0], m1.inputs[0])
            m1.inputs[1].default_value = color_var
            m1.inputs[2].default_value = 1.0 - 0.5 * color_var
            mx = N.new("ShaderNodeMix")
            mx.data_type = "RGBA"
            mx.blend_type = "MULTIPLY"
            mx.inputs[0].default_value = 1.0
            mx.inputs[6].default_value = color
            cm = N.new("ShaderNodeCombineColor")
            for i in range(3):
                L.new(m1.outputs[0], cm.inputs[i])
            L.new(cm.outputs[0], mx.inputs[7])
            L.new(mx.outputs[2], b.inputs["Base Color"])
        else:
            set_input(b, "Base Color", color)

    if "rough" in maps and rough != (None, None):
        r = _img(nt, maps["rough"], True)
        L.new(vec, r.inputs["Vector"])
        mr = N.new("ShaderNodeMapRange")
        mr.inputs["To Min"].default_value = rough[0]
        mr.inputs["To Max"].default_value = rough[1]
        L.new(r.outputs["Color"], mr.inputs["Value"])
        L.new(mr.outputs["Result"], b.inputs["Roughness"])
    elif "rough" in maps:
        r = _img(nt, maps["rough"], True)
        L.new(vec, r.inputs["Vector"])
        L.new(r.outputs["Color"], b.inputs["Roughness"])
    elif rough[0] is not None:
        set_input(b, "Roughness", rough[0])

    if "nor_gl" in maps and normal > 0:
        n = _img(nt, maps["nor_gl"], True)
        L.new(vec, n.inputs["Vector"])
        nm = N.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = normal
        L.new(n.outputs["Color"], nm.inputs["Color"])
        L.new(nm.outputs["Normal"], b.inputs["Normal"])

    set_input(b, "Specular IOR Level", spec)
    set_input(b, "Metallic", metallic)
    if coat:
        set_input(b, "Coat Weight", coat)
        set_input(b, "Coat Roughness", coat_rough)
    if sheen:
        set_input(b, "Sheen Weight", sheen)
    return m


def image_mat(name, image, emission=0.0, rough=0.3, spec=0.5, coat=0.0):
    """Material showing a generated image (UV 0..1). emission>0 -> self-lit screen."""
    m, nt, b, _ = _new_material(name)
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = image
    t.interpolation = "Cubic"
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(tc.outputs["UV"], t.inputs["Vector"])
    if emission > 0:
        set_input(b, "Base Color", (0.004, 0.004, 0.004, 1))
        nt.links.new(t.outputs["Color"], b.inputs["Emission Color"])
        set_input(b, "Emission Strength", emission)
    else:
        nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
    set_input(b, "Roughness", rough)
    set_input(b, "Specular IOR Level", spec)
    if coat:
        set_input(b, "Coat Weight", coat)
        set_input(b, "Coat Roughness", 0.03)
    return m


def thin_glass_mat(name, tint=(0.96, 0.985, 0.975, 1.0)):
    """Architectural glass: no refraction offset, lets shadow rays through (sun + portal)."""
    m, nt, b, out = _new_material(name)
    N, L = nt.nodes, nt.links
    N.remove(b)
    tr = N.new("ShaderNodeBsdfTransparent")
    tr.inputs["Color"].default_value = tint
    gl = N.new("ShaderNodeBsdfGlossy")
    gl.inputs["Roughness"].default_value = 0.0
    fr = N.new("ShaderNodeFresnel")
    fr.inputs["IOR"].default_value = 1.52
    mx = N.new("ShaderNodeMixShader")
    L.new(fr.outputs[0], mx.inputs[0])
    L.new(tr.outputs[0], mx.inputs[1])
    L.new(gl.outputs[0], mx.inputs[2])
    L.new(mx.outputs[0], out.inputs["Surface"])
    return m


def sheer_mat(name, maps, opacity=0.5, color=(0.93, 0.92, 0.89, 1.0)):
    """Sheer voile: translucent + transparent, weave from a fabric normal/diffuse map."""
    m, nt, b, out = _new_material(name)
    N, L = nt.nodes, nt.links
    set_input(b, "Base Color", color)
    set_input(b, "Roughness", 0.85)
    set_input(b, "Sheen Weight", 0.4)
    tl = N.new("ShaderNodeBsdfTranslucent")
    tl.inputs["Color"].default_value = color
    tr = N.new("ShaderNodeBsdfTransparent")
    mx1 = N.new("ShaderNodeMixShader")
    mx1.inputs[0].default_value = 0.55
    L.new(b.outputs[0], mx1.inputs[1])
    L.new(tl.outputs[0], mx1.inputs[2])
    mx2 = N.new("ShaderNodeMixShader")
    # opacity modulated by the weave
    tc = N.new("ShaderNodeTexCoord")
    mp = N.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / 0.27, 1 / 0.27, 1)
    L.new(tc.outputs["UV"], mp.inputs["Vector"])
    d = _img(nt, maps["diff"])
    L.new(mp.outputs[0], d.inputs["Vector"])
    bw = N.new("ShaderNodeRGBToBW")
    L.new(d.outputs["Color"], bw.inputs["Color"])
    mr = N.new("ShaderNodeMapRange")
    mr.inputs["To Min"].default_value = opacity - 0.12
    mr.inputs["To Max"].default_value = opacity + 0.12
    L.new(bw.outputs[0], mr.inputs["Value"])
    L.new(mr.outputs["Result"], mx2.inputs[0])
    L.new(tr.outputs[0], mx2.inputs[1])
    L.new(mx1.outputs[0], mx2.inputs[2])
    L.new(mx2.outputs[0], out.inputs["Surface"])
    return m


def mesh_fabric_mat(name, color=(0.012, 0.012, 0.013, 1.0), freq=260.0, thread=0.45):
    """Office-chair mesh: opaque threads on a UV grid, transparent holes."""
    m, nt, b, out = _new_material(name)
    N, L = nt.nodes, nt.links
    set_input(b, "Base Color", color)
    set_input(b, "Roughness", 0.55)
    set_input(b, "Sheen Weight", 0.3)
    tc = N.new("ShaderNodeTexCoord")
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(tc.outputs["UV"], sep.inputs[0])
    masks = []
    for i in range(2):
        mul = N.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = freq
        L.new(sep.outputs[i], mul.inputs[0])
        fr = N.new("ShaderNodeMath")
        fr.operation = "FRACT"
        L.new(mul.outputs[0], fr.inputs[0])
        lt = N.new("ShaderNodeMath")
        lt.operation = "LESS_THAN"
        lt.inputs[1].default_value = thread
        L.new(fr.outputs[0], lt.inputs[0])
        masks.append(lt)
    mx = N.new("ShaderNodeMath")
    mx.operation = "MAXIMUM"
    L.new(masks[0].outputs[0], mx.inputs[0])
    L.new(masks[1].outputs[0], mx.inputs[1])
    tr = N.new("ShaderNodeBsdfTransparent")
    ms = N.new("ShaderNodeMixShader")
    L.new(mx.outputs[0], ms.inputs[0])
    L.new(tr.outputs[0], ms.inputs[1])
    L.new(b.outputs[0], ms.inputs[2])
    L.new(ms.outputs[0], out.inputs["Surface"])
    return m


# ---------------------------------------------------------------------------
# Generated images (screens, whiteboard)
# ---------------------------------------------------------------------------
def np_to_image(name, arr):
    """HxWx3 sRGB float array (row 0 = top) -> packed-in-memory Blender image."""
    h, w = arr.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=False)
    rgba = np.ones((h, w, 4), np.float32)
    rgba[..., :3] = np.clip(arr, 0, 1)
    img.pixels.foreach_set(rgba[::-1].ravel())
    img.pack()
    return img


def _rect(img, x, y, w, h, col):
    img[int(y) : int(y + h), int(x) : int(x + w)] = col


def _round_rect(img, x, y, w, h, col, r=6):
    H, W = img.shape[:2]
    yy, xx = np.mgrid[int(y) : int(y + h), int(x) : int(x + w)]
    cx = np.clip(xx, x + r, x + w - r)
    cy = np.clip(yy, y + r, y + h - r)
    m = (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r
    sub = img[int(y) : int(y + h), int(x) : int(x + w)]
    sub[m[: sub.shape[0], : sub.shape[1]]] = col


def _text(img, rng, x, y, width, col, h=7, gap=7):
    """Fake a line of text with word-sized bars."""
    cx = x
    while cx < x + width - 12:
        wl = int(rng.integers(12, 70))
        wl = min(wl, int(x + width - cx))
        _rect(img, cx, y, wl, h, col)
        cx += wl + gap


def screen_code(seed=1, W=1600, H=900):
    rng = np.random.default_rng(seed)
    c = hex01
    img = np.zeros((H, W, 3), np.float32)
    img[:] = c("#1f2229")
    _rect(img, 0, 0, W, 34, c("#2c2f37"))
    _rect(img, 0, 34, 52, H, c("#2c2f37"))
    _rect(img, 52, 34, 270, H, c("#191b21"))
    _rect(img, 322, 34, W, 36, c("#23262d"))
    for i, tw in enumerate((180, 150, 170)):
        _rect(img, 322 + i * 190, 34, tw, 36, c("#1f2229") if i == 0 else c("#262930"))
        _text(img, rng, 322 + i * 190 + 16, 49, tw - 40, c("#c8ccd4") if i == 0 else c("#7d8490"))
    for i in range(6):
        _round_rect(img, 14, 60 + i * 56, 24, 24, c("#6b7280"), r=5)
    y = 58
    for i in range(30):
        ind = int(rng.integers(0, 3)) * 16
        _rect(img, 72 + ind, y + 1, 9, 9, c("#8b93a1"))
        _text(img, rng, 88 + ind, y, int(rng.integers(70, 170)), c("#e5c07b") if i == 7 else c("#a9b1bd"), h=8, gap=6)
        y += 24
    pal = [c("#c678dd"), c("#61afef"), c("#98c379"), c("#d19a66"), c("#e06c75"), c("#abb2bf"), c("#56b6c2")]
    y, ind, ln = 86, 0, 1
    split = int(H * 0.68)
    while y < split - 20:
        _text(img, rng, 340, y, 26, c("#4b5263"), h=8)
        x = 392 + ind * 32
        r = rng.random()
        if r < 0.12:
            pass
        elif r < 0.22:
            _text(img, rng, x, y, int(rng.integers(160, 520)), c("#5c6370"), h=8)
        else:
            for _ in range(int(rng.integers(1, 6))):
                wl = int(rng.integers(24, 120))
                _rect(img, x, y, wl, 8, pal[int(rng.integers(0, len(pal)))])
                x += wl + 10
                if x > W - 200:
                    break
        ind = int(np.clip(ind + rng.integers(-1, 2), 0, 4))
        y += 20
        ln += 1
    _rect(img, 322, split, W, 2, c("#3a3f4b"))
    _rect(img, 322, split + 2, W, H - split, c("#181a1f"))
    y = split + 22
    while y < H - 40:
        col = c("#98c379") if rng.random() < 0.3 else c("#c8ccd4")
        _text(img, rng, 342, y, int(rng.integers(200, 900)), col, h=8)
        y += 20
    _rect(img, 0, H - 26, W, 26, c("#2f6fd6"))
    return img


def screen_dashboard(seed=2, W=1600, H=900):
    rng = np.random.default_rng(seed)
    c = hex01
    img = np.zeros((H, W, 3), np.float32)
    img[:] = c("#f3f4f7")
    _rect(img, 0, 0, W, 40, c("#e2e4e9"))
    _round_rect(img, 200, 8, 900, 24, c("#ffffff"), r=12)
    _rect(img, 0, 40, 230, H, c("#1f2a44"))
    for i in range(9):
        _text(img, rng, 32, 92 + i * 44, 140, c("#aeb8d0") if i != 2 else c("#ffffff"), h=9)
    _rect(img, 0, 170, 4, 30, c("#4f8cff"))
    # KPI cards
    for i in range(4):
        x = 262 + i * 330
        _round_rect(img, x, 70, 300, 120, c("#ffffff"), r=10)
        _text(img, rng, x + 20, 92, 120, c("#9aa1ad"), h=8)
        _rect(img, x + 20, 118, int(rng.integers(90, 160)), 26, c("#1f2937"))
        _rect(img, x + 20, 160, 60, 8, c("#22a06b") if i != 2 else c("#e5484d"))
    # bar chart
    _round_rect(img, 262, 215, 820, 400, c("#ffffff"), r=10)
    _text(img, rng, 290, 238, 200, c("#1f2937"), h=10)
    base = 580
    for i in range(14):
        hgt = int(60 + 220 * (0.5 + 0.5 * math.sin(i * 0.7 + 1)) * rng.uniform(0.7, 1.0))
        _rect(img, 300 + i * 54, base - hgt, 30, hgt, c("#4f8cff"))
        _rect(img, 300 + i * 54, base - int(hgt * 0.45), 30, int(hgt * 0.45), c("#9ec0ff"))
    # line chart
    _round_rect(img, 1100, 215, 470, 400, c("#ffffff"), r=10)
    xs = np.linspace(1130, 1540, 300)
    ys = 470 - 80 * np.sin(np.linspace(0, 5, 300)) - np.cumsum(rng.normal(0, 2, 300))
    for x, yv in zip(xs, ys):
        _rect(img, x, yv, 3, 3, c("#8b5cf6"))
    # table
    _round_rect(img, 262, 640, 1308, 240, c("#ffffff"), r=10)
    for r in range(6):
        y = 668 + r * 34
        if r:
            _rect(img, 280, y - 10, 1270, 1, c("#e8eaee"))
        for col_i, x in enumerate((290, 560, 820, 1080, 1340)):
            _text(img, rng, x, y, 150, c("#374151") if r else c("#9aa1ad"), h=8)
    return img


def screen_mail(seed=3, W=1440, H=900):
    rng = np.random.default_rng(seed)
    c = hex01
    img = np.zeros((H, W, 3), np.float32)
    img[:] = c("#ffffff")
    _rect(img, 0, 0, W, 30, c("#ececec"))
    _rect(img, 0, 30, 250, H, c("#f1f3f6"))
    _round_rect(img, 20, 50, 150, 44, c("#c2e7ff"), r=16)
    for i in range(10):
        _text(img, rng, 40, 120 + i * 36, 150, c("#44474f"), h=9)
    _rect(img, 250, 30, 1, H, c("#dadce0"))
    for i in range(16):
        y = 60 + i * 50
        _rect(img, 260, y + 40, W - 270, 1, c("#eeeeee"))
        bold = i < 4
        _text(img, rng, 290, y + 12, 170, c("#202124") if bold else c("#5f6368"), h=10 if bold else 8)
        _text(img, rng, 500, y + 12, 700, c("#202124") if bold else c("#5f6368"), h=8)
        _rect(img, W - 110, y + 12, 60, 8, c("#5f6368"))
    return img


def _stroke(img, pts, width, col, alpha=1.0):
    """Anti-aliased thick polyline on an sRGB image (row 0 = top)."""
    H, W = img.shape[:2]
    r = width / 2
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        xa, xb = int(max(min(x0, x1) - r - 2, 0)), int(min(max(x0, x1) + r + 2, W))
        ya, yb = int(max(min(y0, y1) - r - 2, 0)), int(min(max(y0, y1) + r + 2, H))
        if xa >= xb or ya >= yb:
            continue
        yy, xx = np.mgrid[ya:yb, xa:xb].astype(np.float32)
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy + 1e-6
        t = np.clip(((xx - x0) * dx + (yy - y0) * dy) / L2, 0, 1)
        d = np.hypot(xx - (x0 + t * dx), yy - (y0 + t * dy))
        a = np.clip(r + 0.5 - d, 0, 1)[..., None] * alpha
        sub = img[ya:yb, xa:xb]
        img[ya:yb, xa:xb] = sub * (1 - a) + col * a


def _scribble(rng, x, y, length, size=14):
    """Fake handwriting: a wobbly looping line."""
    n = int(length / 2.2)
    t = np.linspace(0, 1, n)
    xs = x + t * length + size * 0.35 * np.sin(t * length / size * 2 * math.pi * 0.9)
    ys = y - size * 0.45 * np.abs(np.sin(t * length / size * math.pi * 1.1 + rng.uniform(0, 3))) + rng.normal(0, 0.6, n)
    return list(zip(xs, ys))


def whiteboard_image(seed=4, W=1600, H=1200):
    rng = np.random.default_rng(seed)
    img = np.ones((H, W, 3), np.float32) * hex01("#f6f6f3")
    # ghosting of previously erased marker
    yy, xx = np.mgrid[0:H, 0:W]
    for _ in range(7):
        cx, cy = rng.uniform(0, W), rng.uniform(0, H)
        sx, sy = rng.uniform(80, 300), rng.uniform(30, 120)
        g = np.exp(-(((xx - cx) / sx) ** 2 + ((yy - cy) / sy) ** 2))
        img -= (g * 0.035)[..., None] * np.array([0.9, 0.9, 0.6], np.float32)
    blue, red, black, green = hex01("#1d3fa8"), hex01("#c2262e"), hex01("#1c1c1f"), hex01("#177a3d")
    # title
    _stroke(img, _scribble(rng, 120, 150, 520, 40), 6, black)
    _stroke(img, [(110, 175), (680, 170)], 4, red)
    # flow: three boxes with arrows
    boxes = [(120, 300, 300, 160), (560, 300, 300, 160), (1000, 300, 300, 160)]
    for bx, by, bw, bh in boxes:
        j = lambda: rng.normal(0, 2.5)
        _stroke(img, [(bx + j(), by + j()), (bx + bw + j(), by + j()), (bx + bw + j(), by + bh + j()), (bx + j(), by + bh + j()), (bx + j(), by + j())], 5, blue)
        _stroke(img, _scribble(rng, bx + 40, by + 70, bw - 90, 26), 4, black)
        _stroke(img, _scribble(rng, bx + 50, by + 115, bw - 140, 22), 4, black)
    for (ax, ay), (bx2, by2) in (((420, 380), (555, 380)), ((860, 380), (995, 380))):
        _stroke(img, [(ax, ay), (bx2, by2)], 5, black)
        _stroke(img, [(bx2 - 25, by2 - 16), (bx2, by2), (bx2 - 25, by2 + 16)], 5, black)
    # loop back arrow
    arc = [(1150 + 330 * math.cos(a), 470 + 170 * math.sin(a)) for a in np.linspace(0.05, math.pi - 0.05, 40)]
    arc = [(x - 880, y) for x, y in arc]
    _stroke(img, arc, 4, green)
    # list on the lower left
    for i in range(5):
        y = 760 + i * 80
        _stroke(img, [(140, y - 10), (150, y - 12)], 12, red)
        _stroke(img, _scribble(rng, 190, y, rng.uniform(260, 520), 28), 4, black if i % 2 else blue)
    # check marks
    for i in (0, 2):
        y = 760 + i * 80
        _stroke(img, [(720, y - 20), (735, y), (770, y - 45)], 6, green)
    # circle with numbers on the right
    circ = [(1180 + 150 * math.cos(a), 900 + 150 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 60)]
    _stroke(img, circ, 5, red)
    _stroke(img, _scribble(rng, 1110, 910, 140, 34), 5, red)
    return img


def art_print(seed=5, W=900, H=1200):
    """Muted mid-century abstract print: layered arches + sun on warm paper."""
    rng = np.random.default_rng(seed)
    img = np.ones((H, W, 3), np.float32) * hex01("#EEE6D8")
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)

    def disc(cx, cy, r, col, lower_only=False):
        m = (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r
        if lower_only:
            m &= yy <= cy
        img[m] = col

    # sun
    disc(W * 0.7, H * 0.26, W * 0.15, hex01("#D9A05B"))
    # arch rainbow standing on the bottom third
    base_y = H * 0.78
    for r, col in ((W * 0.40, "#B9623F"), (W * 0.31, "#E5CFB2"), (W * 0.24, "#7F8F74"), (W * 0.15, "#EEE6D8"), (W * 0.08, "#2F3A40")):
        disc(W * 0.42, base_y, r, hex01(col), lower_only=True)
    img[int(base_y) :, :] = hex01("#C9B79C")
    img[int(base_y) : int(base_y) + 6, :] = hex01("#2F3A40")
    # paper grain
    img *= (1.0 + rng.normal(0, 0.012, (H, W, 1))).astype(np.float32)
    return img


# ---------------------------------------------------------------------------
# Poly Haven asset import
# ---------------------------------------------------------------------------
def _fix_image_paths(folder):
    for img in bpy.data.images:
        if img.source != "FILE" or not img.filepath:
            continue
        p = bpy.path.abspath(img.filepath)
        if not os.path.exists(p):
            cand = os.path.join(folder, img.filepath.lstrip("/").replace("\\", "/"))
            if os.path.exists(cand):
                img.filepath = cand


def append_objects(blend_path, coll, skip_prefixes=("wdg_",), skip_names=()):
    """Append all objects from a Poly Haven .blend into coll. Returns list of objects."""
    with bpy.data.libraries.load(blend_path, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if not n.startswith(skip_prefixes) and n not in skip_names]
    objs = [o for o in dst.objects if o is not None]
    for o in objs:
        coll.objects.link(o)
    _fix_image_paths(os.path.dirname(blend_path))
    return objs


def join_objects(objs, name):
    meshes = [o for o in objs if o.type == "MESH"]
    for o in objs:
        if o.type != "MESH":
            bpy.data.objects.remove(o)
    if len(meshes) > 1:
        with bpy.context.temp_override(active_object=meshes[0], selected_editable_objects=meshes, selected_objects=meshes):
            bpy.ops.object.join()
    ob = meshes[0]
    ob.name = name
    return ob


def bbox_local(ob):
    pts = [Vector(c) for c in ob.bound_box]
    return pts


def place_by_bbox(ob, rot_matrix3, xmin=None, ymax=None, zmin=None, xc=None, yc=None):
    """Rotate ob by rot_matrix3, then translate so its rotated bbox touches the given planes.
    Returns (width_x, depth_y, height_z) of the rotated bbox."""
    pts = [rot_matrix3 @ p for p in bbox_local(ob)]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    loc = Vector((0.0, 0.0, 0.0))
    if xmin is not None:
        loc.x = xmin - mn.x
    if xc is not None:
        loc.x = xc - (mn.x + mx.x) / 2
    if ymax is not None:
        loc.y = ymax - mx.y
    if yc is not None:
        loc.y = yc - (mn.y + mx.y) / 2
    if zmin is not None:
        loc.z = zmin - mn.z
    ob.matrix_world = Matrix.Translation(loc) @ rot_matrix3.to_4x4()
    return mx - mn


def stretch_above(ob, z_cut, dz):
    for v in ob.data.vertices:
        if v.co.z > z_cut:
            v.co.z += dz


def look_at_rotation(cam_loc, target):
    d = Vector(target) - Vector(cam_loc)
    return d.to_track_quat("-Z", "Y").to_euler()


__all__ = [n for n in dir() if not n.startswith("_") or n in ("_rect",)]
