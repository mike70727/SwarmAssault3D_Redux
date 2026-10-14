"""Level structures from the OpenSA maps: one stand-alone colony turret per family, the tesla coil
turret, the popcorn plant (neutral creep tower) and the firepower / production boosters.

Conventions follow build_colony.py: the static body is `ColonyBody`, the rotating part is the object
`Turret_1` (parented to the body) with the barrels parented to it; clips `idle` and `turret_fire`.
Footprints: turrets 1x1 cell, boosters 3x2 cells (OpenSA Building dimensions).
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import build_colony as bc  # noqa: E402
import salib  # noqa: E402
from mathutils import Vector  # noqa: E402

PREVIEW_VIEWS = ("front", "back", "left", "right", "threequarter", "top")


def disc(name, mats, radius, height, z=None, verts=24, mat="M_Colony"):
    z = height / 2 if z is None else z
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=radius, depth=height, location=(0, 0, z))
    o = bpy.context.object
    o.name = name
    for p in o.data.polygons:
        p.use_smooth = verts > 8
    o.data.materials.append(mats[mat])
    return o


def ring(name, mats, major, minor, z, mat="M_Dark", scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, location=(0, 0, z), major_segments=28, minor_segments=10)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    for p in o.data.polygons:
        p.use_smooth = True
    o.data.materials.append(mats[mat])
    return o


def block(name, mats, pos, size, mat="M_Neutral", rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=pos, rotation=rot)
    o = bpy.context.object
    o.name = name
    o.scale = size
    bpy.ops.object.transform_apply(scale=True, rotation=True)
    o.data.materials.append(mats[mat])
    salib.bevel_object(o, min(size) * 0.18)
    return o


def ball(name, mats, pos, radius, mat, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, segments=20, ring_count=12, location=pos)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    for p in o.data.polygons:
        p.use_smooth = True
    o.data.materials.append(mats[mat])
    return o


def cone(name, mats, pos, r1, r2, depth, mat, rot=(0, 0, 0), verts=14):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r1, radius2=r2, depth=depth, location=pos, rotation=rot)
    o = bpy.context.object
    o.name = name
    for p in o.data.polygons:
        p.use_smooth = True
    o.data.materials.append(mats[mat])
    return o


# ---------------------------------------------------------------------------------------------
def build_turret(name, fam):
    salib.reset_scene(name)
    mats = salib.standard_materials("Y")
    parts = []
    body_mat = "M_Colony"
    top = 0.55
    if fam == "ant":
        parts.append(disc("Base", mats, 0.46, 0.30))
        parts.append(ring("Rim", mats, 0.40, 0.06, 0.30, "M_Colony"))
        parts.append(disc("Neck", mats, 0.22, 0.25, z=0.42))
    elif fam == "beetle":
        parts.append(disc("Base", mats, 0.47, 0.28, mat="M_Dark"))
        parts.append(ring("Rim", mats, 0.44, 0.05, 0.28, "M_Black"))
        parts += bc.spines(mats, 6, 0.42, 0.22, 0.32, seed=3, mat="M_Dark")
        parts.append(disc("Neck", mats, 0.24, 0.3, z=0.42, mat="M_Dark"))
        top = 0.6
    elif fam == "spider":
        parts.append(disc("Base", mats, 0.28, 0.62, z=0.31, mat="M_Neutral"))
        for i in range(4):
            a = math.radians(45 + 90 * i)
            pts = [(0.2 * math.cos(a), 0.2 * math.sin(a), 0.5), (0.42 * math.cos(a), 0.42 * math.sin(a), 0.32), (0.5 * math.cos(a), 0.5 * math.sin(a), 0.0)]
            parts += bc.tube_chain(mats, pts, 0.045, mat="M_Colony", verts=8)
        top = 0.68
    elif fam == "scorpion":
        parts.append(block("Base", mats, (0, 0, 0.15), (0.92, 0.92, 0.30), "M_Neutral"))
        for sx in (-1, 1):
            for sy in (-1, 1):
                parts.append(block(f"Post{sx}{sy}", mats, (sx * 0.34, sy * 0.34, 0.42), (0.2, 0.2, 0.26), "M_Neutral"))
        parts.append(disc("Neck", mats, 0.22, 0.2, z=0.4, mat="M_Accent", verts=8))
        top = 0.58
    elif fam == "wasp":
        parts.append(disc("Base", mats, 0.5, 0.26, verts=6, mat="M_Colony"))
        parts.append(disc("Cell", mats, 0.34, 0.5, z=0.38, verts=6, mat="M_Dark"))
        parts.append(disc("CellTop", mats, 0.28, 0.08, z=0.64, verts=6, mat="M_Colony"))
        top = 0.78
    elif fam == "tesla":
        parts.append(disc("Base", mats, 0.44, 0.22, mat="M_Accent", verts=12))
        parts.append(disc("Pole", mats, 0.08, 0.6, z=0.5, mat="M_Black", verts=10))
        for i in range(4):
            parts.append(ring(f"Coil{i}", mats, 0.24 - 0.025 * i, 0.035, 0.3 + 0.12 * i, "M_Accent"))
        mats["M_Spark"] = salib.material("M_Spark", (0.60, 0.85, 1.0), roughness=0.15, emission=(0.35, 0.65, 1.0), emission_strength=2.5, kind="glossy")
        body_mat = "M_Spark"
        top = 0.88
    body = bc.join_into(parts, "ColonyBody")
    radius = 0.2 if fam == "tesla" else 0.27
    t, barrels = bc.twin_barrel_turret("Turret_1", mats, (0, 0, top), radius=radius, barrel_len=0.48, barrel_r=0.05, spread=0.09, body_mat=body_mat)
    t.parent = body
    t.matrix_parent_inverse = body.matrix_world.inverted()
    bc.idle_clip(body)
    bc.turret_fire_clip(t, barrels)
    objs = [body, t] + barrels
    path, s = salib.finalize_asset(name, objs, preview_radius=3.2, preview_center=(0, 0, 0.5), views=PREVIEW_VIEWS, texture_size=512, small_size=256)
    assert "Turret_1" in s["node_names"], s["node_names"]
    assert sorted(a["name"] for a in s["animations"]) == ["idle", "turret_fire"], s["animations"]
    return path


def build_popcorn(name="popcorn_plant"):
    salib.reset_scene(name)
    mats = salib.standard_materials("Y")
    mats["M_Stem"] = salib.material("M_Stem", (0.33, 0.58, 0.22), roughness=0.7, kind="organic")
    mats["M_Husk"] = salib.material("M_Husk", (0.84, 0.70, 0.30), roughness=0.6, kind="organic", variation=0.5)
    mats["M_Pop"] = salib.material("M_Pop", (0.98, 0.94, 0.74), roughness=0.55, kind="organic", variation=0.6, sss=0.3)
    parts = [disc("Stalk", mats, 0.07, 0.95, z=0.47, verts=12, mat="M_Stem")]
    for i in range(3):
        a = math.radians(120 * i + 20)
        parts.append(cone(f"Leaf{i}", mats, (0.22 * math.cos(a), 0.22 * math.sin(a), 0.22), 0.14, 0.0, 0.6, "M_Stem", rot=(math.radians(-55) * math.sin(a), math.radians(55) * math.cos(a), 0)))
    parts.append(cone("Husk", mats, (0, 0, 0.98), 0.14, 0.30, 0.32, "M_Husk"))
    body = bc.join_into(parts, "ColonyBody")
    rnd = random.Random(7)
    head_parts = [ball("Head", mats, (0, 0, 1.3), 0.22, "M_Pop")]
    for i in range(9):
        a = rnd.uniform(0, 2 * math.pi)
        el = rnd.uniform(-0.4, 1.0)
        r = 0.24
        p = (r * math.cos(a) * math.cos(el), r * math.sin(a) * math.cos(el), 1.3 + r * math.sin(el))
        head_parts.append(ball(f"Kernel{i}", mats, p, rnd.uniform(0.08, 0.12), "M_Pop", scale=(1, 1, rnd.uniform(0.8, 1.2))))
    head = bc.join_into(head_parts, "Turret_1")
    head.parent = body
    head.matrix_parent_inverse = body.matrix_world.inverted()
    bc.idle_clip(body, amount=0.04)
    bc.turret_fire_clip(head, [head])
    path, s = salib.finalize_asset(name, [body, head], preview_radius=3.4, preview_center=(0, 0, 0.7), views=PREVIEW_VIEWS, texture_size=512, small_size=512)
    assert "Turret_1" in s["node_names"], s["node_names"]
    assert sorted(a["name"] for a in s["animations"]) == ["idle", "turret_fire"], s["animations"]
    return path


def build_booster(name, kind):
    salib.reset_scene(name)
    mats = salib.standard_materials("Y")
    col = (0.92, 0.22, 0.18) if kind == "firepower" else (0.25, 0.85, 0.50)
    mats["M_Crystal"] = salib.material("M_Crystal", col, roughness=0.12, emission=col, emission_strength=1.4, kind="glossy")
    mats["M_Rock"] = salib.material("M_Rock", (0.42, 0.38, 0.33), roughness=0.95, kind="stone")
    base = bc.mound("Base", mats, radius=1.45, height=0.42, noise=0.08, seed=5)
    base.scale = (1.0, 0.68, 1.0)
    bpy.ops.object.transform_apply(scale=True)
    base.data.materials.clear()
    base.data.materials.append(mats["M_Rock"])
    parts = [base]
    rnd = random.Random(11 if kind == "firepower" else 12)
    if kind == "firepower":
        for i in range(8):
            a = rnd.uniform(0, 2 * math.pi)
            r = rnd.uniform(0.0, 0.9)
            depth = rnd.uniform(0.8, 1.5)
            tilt = rnd.uniform(-0.35, 0.35)
            parts.append(cone(f"Crystal{i}", mats, (r * math.cos(a), 0.6 * r * math.sin(a), 0.25 + depth * 0.4), rnd.uniform(0.12, 0.2), 0.02, depth, "M_Crystal", rot=(tilt, rnd.uniform(-0.35, 0.35), a), verts=6))
    else:
        for i in range(8):
            a = rnd.uniform(0, 2 * math.pi)
            r = rnd.uniform(0.0, 0.9)
            rad = rnd.uniform(0.22, 0.4)
            parts.append(ball(f"Pod{i}", mats, (r * math.cos(a), 0.6 * r * math.sin(a), 0.3 + rad * 0.9), rad, "M_Crystal", scale=(1, 1, rnd.uniform(1.0, 1.4))))
            parts.append(disc(f"PodStem{i}", mats, 0.05, 0.4, z=0.3, verts=8, mat="M_Dark"))
    body = bc.join_into(parts, "ColonyBody")
    bc.idle_clip(body, amount=0.03)
    path, s = salib.finalize_asset(name, [body], preview_radius=5.0, preview_center=(0, 0, 0.5), views=PREVIEW_VIEWS, texture_size=1024)
    assert [a["name"] for a in s["animations"]] == ["idle"], s["animations"]
    return path


BUILDERS = {
    "turret_ant": lambda: build_turret("turret_ant", "ant"),
    "turret_beetle": lambda: build_turret("turret_beetle", "beetle"),
    "turret_spider": lambda: build_turret("turret_spider", "spider"),
    "turret_scorpion": lambda: build_turret("turret_scorpion", "scorpion"),
    "turret_wasp": lambda: build_turret("turret_wasp", "wasp"),
    "turret_tesla": lambda: build_turret("turret_tesla", "tesla"),
    "popcorn_plant": build_popcorn,
    "booster_firepower": lambda: build_booster("booster_firepower", "firepower"),
    "booster_production": lambda: build_booster("booster_production", "production"),
}

if __name__ == "__main__":
    flags = [a for a in sys.argv[1:] if a.startswith("-")]
    args = [a for a in sys.argv[1:] if not a.startswith("-")] or (list(BUILDERS) if "--all" in flags else ["turret_ant"])
    for a in args:
        if a not in BUILDERS:
            raise SystemExit(f"unknown structure {a}; choose from {list(BUILDERS)}")
        BUILDERS[a]()
        print("BUILT", a, flush=True)
