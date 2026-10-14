"""Candy-tileset decorations used by the converted levels (OpenSA plant_jelly_bean, plant_gumnut,
plant_choc_chip, plant_smarty, plant_jaffa). Simple glossy props, origin on the ground, ~1 cell."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import build_environment as be  # noqa: E402
import salib  # noqa: E402


def sphere(name, mat, pos, radius, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, segments=24, ring_count=14, location=pos)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    for p in o.data.polygons:
        p.use_smooth = True
    o.data.materials.append(mat)
    return o


def cylinder(name, mat, pos, radius, depth, verts=32, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=radius, depth=depth, location=pos, rotation=rot)
    o = bpy.context.object
    o.name = name
    for p in o.data.polygons:
        p.use_smooth = True
    o.data.materials.append(mat)
    salib.bevel_object(o, min(radius, depth) * 0.3, segments=3)
    return o


def cone(name, mat, pos, r1, r2, depth):
    bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=r1, radius2=r2, depth=depth, location=pos)
    o = bpy.context.object
    o.name = name
    for p in o.data.polygons:
        p.use_smooth = True
    o.data.materials.append(mat)
    return o


def jelly_bean():
    name = "candy_jelly_bean"
    salib.reset_scene(name)
    m = salib.material("M_Bean", (0.88, 0.16, 0.22), roughness=0.18, kind="glossy")
    a = sphere("BeanA", m, (-0.14, 0.0, 0.24), 0.25, scale=(1.3, 1.0, 0.95))
    b = sphere("BeanB", m, (0.16, 0.06, 0.24), 0.25, scale=(1.3, 1.0, 0.95))
    return be.finish(name, [a, b], 2.4, 0.25)


def gumnut():
    name = "candy_gumnut"
    salib.reset_scene(name)
    nut = salib.material("M_Nut", (0.48, 0.30, 0.16), roughness=0.55, kind="wood")
    cap = salib.material("M_NutCap", (0.30, 0.18, 0.10), roughness=0.6, kind="wood")
    body = sphere("Nut", nut, (0, 0, 0.32), 0.3, scale=(1.0, 1.0, 1.05))
    top = cylinder("Cap", cap, (0, 0, 0.6), 0.3, 0.1, verts=24)
    stem = cylinder("Stem", cap, (0.05, 0.0, 0.72), 0.04, 0.2, verts=8)
    return be.finish(name, [body, top, stem], 2.4, 0.3)


def choc_chip():
    name = "candy_choc_chip"
    salib.reset_scene(name)
    m = salib.material("M_Choc", (0.27, 0.15, 0.08), roughness=0.3, kind="glossy")
    base = cylinder("ChipBase", m, (0, 0, 0.06), 0.34, 0.12, verts=28)
    tip = cone("ChipTip", m, (0, 0, 0.36), 0.33, 0.04, 0.5)
    return be.finish(name, [base, tip], 2.4, 0.25)


def smarty():
    name = "candy_smarty"
    salib.reset_scene(name)
    m = salib.material("M_Smarty", (0.96, 0.55, 0.10), roughness=0.15, kind="glossy")
    disc = cylinder("Smarty", m, (0, 0, 0.08), 0.36, 0.16, verts=36)
    return be.finish(name, [disc], 2.4, 0.1)


def jaffa():
    name = "candy_jaffa"
    salib.reset_scene(name)
    m = salib.material("M_Jaffa", (0.95, 0.42, 0.08), roughness=0.3, kind="organic", variation=0.25, cell_scale=60.0, bump=0.3)
    ball = sphere("Jaffa", m, (0, 0, 0.33), 0.33)
    return be.finish(name, [ball], 2.4, 0.3)


BUILDERS = {"candy_jelly_bean": jelly_bean, "candy_gumnut": gumnut, "candy_choc_chip": choc_chip, "candy_smarty": smarty, "candy_jaffa": jaffa}

if __name__ == "__main__":
    args = [a for a in salib.script_args() if not a.startswith("-")] or list(BUILDERS)
    for a in args:
        BUILDERS[a]()
        print("BUILT", a, flush=True)
