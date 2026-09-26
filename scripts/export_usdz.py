"""Export the office as a USDZ for iPhone / iPad (AR Quick Look).

    blender -b -P scripts/export_usdz.py -- --out exports/office.usdz --tex 1024

Builds the same scene as office_scene.py, then:
  * drops the ceiling, downlights and the outside sunshade (so you can look into the room from above)
  * converts curves (cables, chair frames) to meshes
  * rewrites materials that use custom node set-ups into plain PBR (USD Preview Surface) equivalents
  * exports meshes + materials + downscaled textures, Y-up, metres (real-world AR scale)
Lighting is not exported: Quick Look lights the model itself.
"""

import argparse
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import office_scene as S  # noqa: E402

DROP_PREFIXES = ("ceiling_", "downlight_", "chajja", "shelf_led_")


def _principled(nt):
    return next((n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)


def _upstream_image(sock, depth=0):
    """First Image Texture node feeding this socket (through any chain), or None."""
    if not sock.is_linked or depth > 8:
        return None
    node = sock.links[0].from_node
    if node.bl_idname == "ShaderNodeTexImage":
        return node
    for inp in node.inputs:
        img = _upstream_image(inp, depth + 1)
        if img is not None:
            return img
    return None


def _replace_with_principled(m, color, alpha=1.0, rough=0.5, metallic=0.0):
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = color
    b.inputs["Alpha"].default_value = alpha
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metallic
    nt.links.new(b.outputs[0], out.inputs["Surface"])


def simplify_materials():
    for m in bpy.data.materials:
        if not m.node_tree:
            continue
        nt = m.node_tree
        name = m.name
        if name.startswith("window_glass") or name.startswith("drinking_glass"):
            _replace_with_principled(m, (0.9, 0.95, 0.95, 1), alpha=0.15, rough=0.02)
            continue
        if name.startswith("sheer_curtain"):
            _replace_with_principled(m, (0.93, 0.92, 0.89, 1), alpha=0.45, rough=0.9)
            continue
        if name.startswith("chair_mesh"):
            _replace_with_principled(m, (0.015, 0.015, 0.016, 1), alpha=0.85, rough=0.6)
            continue
        b = _principled(nt)
        if b is None:
            continue
        # Base colour: flat colour for painted surfaces, otherwise the underlying image
        bc = b.inputs["Base Color"]
        if bc.is_linked:
            src = bc.links[0].from_node
            if src.bl_idname == "ShaderNodeMix" and not src.inputs[6].is_linked:
                col = tuple(src.inputs[6].default_value)
                nt.links.remove(bc.links[0])
                bc.default_value = col
            elif src.bl_idname != "ShaderNodeTexImage":
                img = _upstream_image(bc)
                nt.links.remove(bc.links[0])
                if img is not None:
                    nt.links.new(img.outputs["Color"], bc)
        # Roughness: map-range chains -> the image itself
        r = b.inputs["Roughness"]
        if r.is_linked and r.links[0].from_node.bl_idname not in ("ShaderNodeTexImage", "ShaderNodeSeparateColor"):
            img = _upstream_image(r)
            nt.links.remove(r.links[0])
            if img is not None:
                nt.links.new(img.outputs["Color"], r)
        # Normal: keep image normal maps, drop procedural bumps
        n = b.inputs["Normal"]
        if n.is_linked and n.links[0].from_node.bl_idname == "ShaderNodeBump":
            nt.links.remove(n.links[0])
        # Emission strength driven by light-path tricks -> constant
        es = b.inputs["Emission Strength"]
        if es.is_linked:
            nt.links.remove(es.links[0])
            es.default_value = 2.0
        # Screens / prints: also show the image as base colour
        ec = b.inputs["Emission Color"]
        if ec.is_linked and not bc.is_linked:
            img = _upstream_image(ec)
            if img is not None:
                nt.links.new(img.outputs["Color"], bc)


def curves_to_meshes():
    curves = [o for o in bpy.context.scene.objects if o.type == "CURVE"]
    if not curves:
        return
    for o in curves:
        o.hide_set(False)
    with bpy.context.temp_override(selected_editable_objects=curves, selected_objects=curves, active_object=curves[0], object=curves[0]):
        bpy.ops.object.convert(target="MESH")


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(S.REPO, "exports", "office.usdz"))
    ap.add_argument("--tex", default="1024", choices=["256", "512", "1024", "2048", "KEEP"])
    args = ap.parse_args(argv)

    S.build_scene()
    # remove objects that only make sense for the photos
    for o in list(bpy.data.objects):
        if o.name.startswith(DROP_PREFIXES) and o.type in ("MESH", "EMPTY"):
            bpy.data.objects.remove(o)
    for coll in bpy.data.collections:
        if coll.name == "_protos":
            for o in list(coll.objects):
                bpy.data.objects.remove(o)
    curves_to_meshes()
    simplify_materials()

    keep = [o for o in bpy.context.scene.objects if o.type in ("MESH", "EMPTY", "ARMATURE") and not o.hide_render]
    for o in bpy.context.scene.objects:
        o.select_set(o in keep)
    dg = bpy.context.evaluated_depsgraph_get()
    tris = sum(len(o.evaluated_get(dg).data.loop_triangles) for o in keep if o.type == "MESH")
    print(f"[usdz] exporting {len(keep)} objects, ~{tris:,} triangles")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    bpy.ops.wm.usd_export(
        filepath=os.path.abspath(args.out),
        selected_objects_only=True,
        export_materials=True,
        generate_preview_surface=True,
        export_textures_mode="NEW",
        overwrite_textures=True,
        export_subdivision="TESSELLATE",
        export_armatures=False,
        export_shapekeys=False,
        export_lights=False,
        export_cameras=False,
        export_curves=False,
        export_volumes=False,
        convert_world_material=False,
        use_instancing=True,
        evaluation_mode="RENDER",
        convert_orientation=True,
        export_global_forward_selection="NEGATIVE_Z",
        export_global_up_selection="Y",
        usdz_downscale_size=args.tex,
        convert_scene_units="METERS",
        root_prim_path="/office",
        accessibility_label="Home office, first floor",
    )
    size = os.path.getsize(args.out) / 1e6
    print(f"[usdz] wrote {args.out} ({size:.1f} MB)")


if __name__ == "__main__":
    main()
