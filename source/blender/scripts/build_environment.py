"""Builds static environment objects: rocks, mushroom, flower, grass tuft, colony bit, ant hole.

References: Original_Game/Plants_Hazards_And_Decorations (OBMUSHWH*, OBFLOWER*, OBGRASS*, ANTHOLE*,
OBBROWNM* ...) and OpenSA's colonybit projectile sprite. These are simple props without rigs; each is
exported as its own GLB with the origin on the ground.
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import salib  # noqa: E402
from mathutils import Vector  # noqa: E402


def noisy_sphere(name, mat, radius, scale, noise, seed, subdiv=3):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdiv, radius=radius, location=(0, 0, 0))
    o = bpy.context.object
    o.name = name
    rnd = random.Random(seed)
    for v in o.data.vertices:
        v.co += Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1))) * noise * radius
    o.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    o.data.materials.append(mat)
    return o


def finish(name, objs, radius, center_z, flat=False):
    salib.select_only(objs)
    if len(objs) > 1:
        bpy.ops.object.join()
    o = bpy.context.object
    o.name = name
    o.data.name = name
    if not flat:
        salib.detail_object(o, subdiv=1, displace=0.015, smooth_angle=35.0, noise_scale=0.3)
    path, _ = salib.finalize_asset(name, [o], preview_radius=radius, preview_center=(0, 0, center_z), texture_size=512,
                                   views=("front", "threequarter", "top"), preview_size=384, preview_samples=48)
    return path


def rock(name, size, seed):
    salib.reset_scene(name)
    m = salib.material("M_Rock", (0.46, 0.42, 0.37), roughness=0.95, kind="stone")
    parts = [noisy_sphere("RockA", m, size, (1.1, 0.9, 0.62), 0.12, seed)]
    parts[0].location.z = size * 0.3
    b = noisy_sphere("RockB", m, size * 0.55, (0.9, 1.0, 0.7), 0.15, seed + 7)
    b.location = (size * 0.6, -size * 0.3, size * 0.2)
    parts.append(b)
    for p in parts:
        for f in p.data.polygons:
            f.use_smooth = False
    return finish(name, parts, size * 3.2, size * 0.4)


def mushroom():
    name = "mushroom"
    salib.reset_scene(name)
    stem = salib.material("M_Stem", (0.86, 0.80, 0.62), roughness=0.8, kind="organic")
    cap = salib.material("M_Cap", (0.75, 0.18, 0.12), roughness=0.5, kind="organic", coat=0.5, variation=0.3)
    dot = salib.material("M_Dot", (0.95, 0.95, 0.9), roughness=0.6, kind="organic")
    parts = []
    bpy.ops.mesh.primitive_cylinder_add(vertices=14, radius=0.18, depth=0.9, location=(0, 0, 0.45))
    s = bpy.context.object
    s.data.materials.append(stem)
    parts.append(s)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.55, segments=20, ring_count=12, location=(0, 0, 0.95))
    c = bpy.context.object
    c.scale = (1.0, 1.0, 0.62)
    bpy.ops.object.transform_apply(scale=True)
    c.data.materials.append(cap)
    for p in c.data.polygons:
        p.use_smooth = True
    parts.append(c)
    rnd = random.Random(5)
    for i in range(7):
        a = rnd.uniform(0, 2 * math.pi)
        r = rnd.uniform(0.1, 0.42)
        x, y = r * math.cos(a), r * math.sin(a)
        zz = 0.95 + 0.34 * math.sqrt(max(0.0, 1 - (r / 0.55) ** 2))
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.07, segments=8, ring_count=5, location=(x, y, zz))
        d = bpy.context.object
        d.scale = (1, 1, 0.4)
        bpy.ops.object.transform_apply(scale=True)
        d.data.materials.append(dot)
        parts.append(d)
    return finish(name, parts, 2.6, 0.7)


def flower():
    name = "flower"
    salib.reset_scene(name)
    stem = salib.material("M_Stem", (0.25, 0.55, 0.18), roughness=0.8, kind="organic")
    petal = salib.material("M_Petal", (0.90, 0.25, 0.30), roughness=0.6, kind="petal")
    core = salib.material("M_Core", (0.95, 0.80, 0.25), roughness=0.6, kind="organic", variation=0.5, cell_scale=60.0)
    parts = []
    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.05, depth=1.3, location=(0, 0, 0.65))
    s = bpy.context.object
    s.data.materials.append(stem)
    parts.append(s)
    for s_ in (+1, -1):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.22, segments=10, ring_count=6, location=(s_ * 0.22, 0.0, 0.45))
        leaf = bpy.context.object
        leaf.scale = (1.3, 0.6, 0.2)
        leaf.rotation_euler = (0, s_ * 0.5, 0)
        bpy.ops.object.transform_apply(scale=True, rotation=True)
        leaf.data.materials.append(stem)
        parts.append(leaf)
    for i in range(6):
        a = i / 6 * 2 * math.pi
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.22, segments=10, ring_count=6, location=(0.3 * math.cos(a), 0.3 * math.sin(a), 1.32))
        p = bpy.context.object
        p.scale = (1.4, 0.8, 0.25)
        p.rotation_euler = (0, 0, a)
        bpy.ops.object.transform_apply(scale=True, rotation=True)
        p.data.materials.append(petal)
        parts.append(p)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.18, segments=12, ring_count=8, location=(0, 0, 1.36))
    c = bpy.context.object
    c.scale = (1, 1, 0.5)
    bpy.ops.object.transform_apply(scale=True)
    c.data.materials.append(core)
    parts.append(c)
    return finish(name, parts, 2.8, 0.8)


def grass_tuft():
    name = "grass_tuft"
    salib.reset_scene(name)
    g = salib.material("M_Grass", (0.30, 0.62, 0.20), roughness=0.9, kind="organic", variation=0.5)
    parts = []
    rnd = random.Random(11)
    for i in range(9):
        a = rnd.uniform(0, 2 * math.pi)
        r = rnd.uniform(0.0, 0.18)
        h = rnd.uniform(0.5, 0.8)
        bpy.ops.mesh.primitive_cone_add(vertices=5, radius1=0.05, radius2=0.0, depth=h, location=(r * math.cos(a), r * math.sin(a), h / 2))
        b = bpy.context.object
        b.rotation_euler = (rnd.uniform(-0.4, 0.4), rnd.uniform(-0.4, 0.4), 0)
        bpy.ops.object.transform_apply(rotation=True)
        b.data.materials.append(g)
        parts.append(b)
    return finish(name, parts, 2.0, 0.3)


def colony_bit():
    name = "colony_bit"
    salib.reset_scene(name)
    m = salib.material("M_Bit", (1.0, 0.82, 0.25), roughness=0.3, emission=(1.0, 0.7, 0.2), emission_strength=1.5, kind="glossy")
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.28, location=(0, 0, 0))
    o = bpy.context.object
    o.scale = (1.0, 1.0, 1.3)
    bpy.ops.object.transform_apply(scale=True)
    o.data.materials.append(m)
    return finish(name, [o], 1.4, 0.0)


def ant_hole():
    name = "ant_hole"
    salib.reset_scene(name)
    sand = salib.material("M_Sand", (0.62, 0.52, 0.36), roughness=0.95, kind="earth")
    dark = salib.material("M_Eye", (0.02, 0.02, 0.02), roughness=0.2, kind="glossy")
    bpy.ops.mesh.primitive_torus_add(major_radius=0.55, minor_radius=0.22, location=(0, 0, 0.05), major_segments=24, minor_segments=10)
    ring = bpy.context.object
    ring.scale = (1, 1, 0.5)
    bpy.ops.object.transform_apply(scale=True)
    ring.data.materials.append(sand)
    bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=0.4, depth=0.1, location=(0, 0, 0.0))
    hole = bpy.context.object
    hole.data.materials.append(dark)
    return finish(name, [ring, hole], 2.4, 0.1)


BUILDERS = {
    "rock_large": lambda: rock("rock_large", 1.3, 1),
    "rock_small": lambda: rock("rock_small", 0.7, 9),
    "mushroom": mushroom,
    "flower": flower,
    "grass_tuft": grass_tuft,
    "colony_bit": colony_bit,
    "ant_hole": ant_hole,
}

if __name__ == "__main__":
    args = [a for a in salib.script_args() if not a.startswith("-")] or list(BUILDERS)
    for a in args:
        BUILDERS[a]()
        print("BUILT", a, flush=True)
