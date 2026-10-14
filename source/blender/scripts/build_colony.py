"""Builds the five colony families (Stage 2: Ant; Stage 4: Beetle, Spider, Scorpion, Wasp).

References: Quick_References/Buildings/<Family>_Colony_<team>/Colony_Body.png (144 px = 6 cells),
Turret_*.png (36 px) and Overviews/Original_Colony_Bodies.jpg.

Ant colony (from the sprites): a dark earth mound with yellow ribs/arches, a ring-shaped entrance on
top, two tall yellow cylinders (turret towers) and a curved yellow wall segment on the south-east.
The turrets are yellow spheres with twin barrels and sit on the tower tops as separate objects
`Turret_1`, `Turret_2` so the game can rotate them (sim turret yaw) - the barrels are children.

All colonies share: origin at the centre of the 6x6 footprint on the ground, Z up, turret rest
pose pointing -Y (Bevy +Z = sim south), materials M_Ground / M_Colony / M_Dark / M_Accent.
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import salib  # noqa: E402
from mathutils import Vector  # noqa: E402


def mound(name, mats, radius=2.9, height=1.25, noise=0.12, seed=1):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, segments=40, ring_count=24, location=(0, 0, 0))
    o = bpy.context.object
    o.name = name
    o.scale = (1.0, 0.92, height / radius)
    bpy.ops.object.transform_apply(scale=True)
    rnd = random.Random(seed)
    me = o.data
    for v in me.vertices:
        if v.co.z < -0.05:
            v.co.z = -0.05  # flatten below ground
            continue
        n = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-0.3, 0.3))) * noise
        v.co += n * (v.co.z / height + 0.2)
    me.update()
    for p in me.polygons:
        p.use_smooth = True
    o.data.materials.append(mats["M_Ground"])
    return o


def tower(name, mats, x, y, radius, height, mat="M_Colony"):
    bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=radius, depth=height, location=(x, y, height / 2))
    o = bpy.context.object
    o.name = name
    o.data.materials.append(mats[mat])
    for p in o.data.polygons:
        p.use_smooth = p.normal.z < 0.5
    # rim
    bpy.ops.mesh.primitive_torus_add(major_radius=radius, minor_radius=radius * 0.18, location=(x, y, height), major_segments=24, minor_segments=8)
    r = bpy.context.object
    r.name = name + "_rim"
    r.data.materials.append(mats["M_Dark"])
    return o, r


def arch(name, mats, center, radius, tube, rot_z=0.0, tilt=0.0, mat="M_Colony", segments=20):
    """Half torus (an arch) standing on the ground."""
    bpy.ops.mesh.primitive_torus_add(major_radius=radius, minor_radius=tube, location=center, major_segments=segments * 2, minor_segments=8)
    o = bpy.context.object
    o.name = name
    o.rotation_euler = (math.radians(90) + tilt, 0, rot_z)
    bpy.ops.object.transform_apply(rotation=True)
    # delete the half below ground
    me = o.data
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.object.mode_set(mode="OBJECT")
    for v in me.vertices:
        v.select = v.co.z < -0.02
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.delete(type="VERT")
    bpy.ops.object.mode_set(mode="OBJECT")
    o.data.materials.append(mats[mat])
    for p in o.data.polygons:
        p.use_smooth = True
    return o


def twin_barrel_turret(name, mats, pos, radius=0.42, barrel_len=0.75, barrel_r=0.07, spread=0.14, body_mat="M_Colony"):
    """Sphere turret with two forward (-Y) barrels. Returns (turret, [barrels])."""
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, segments=18, ring_count=12, location=pos)
    t = bpy.context.object
    t.name = name
    t.data.materials.append(mats[body_mat])
    for p in t.data.polygons:
        p.use_smooth = True
    salib.detail_object(t, subdiv=1, displace=0.0, smooth_angle=40.0)
    barrels = []
    for i, s in enumerate((+1, -1)):
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=barrel_r, depth=barrel_len, location=(pos[0] + s * spread, pos[1] - radius * 0.6 - barrel_len / 2, pos[2] + 0.05), rotation=(math.radians(90), 0, 0))
        b = bpy.context.object
        b.name = f"{name}_Barrel_{i + 1}"
        b.data.materials.append(mats["M_Accent"])
        salib.detail_object(b, subdiv=1, displace=0.0, smooth_angle=40.0)
        b.parent = t
        b.matrix_parent_inverse = t.matrix_world.inverted()
        barrels.append(b)
    return t, barrels


def turret_fire_clip(turret, barrels, name="turret_fire", frames=8):
    """Recoil action on the barrels (object-level animation), stored on an NLA track per object."""
    acts = []
    for b in barrels:
        act = bpy.data.actions.new(f"{turret.name}_{name}")
        act.use_fake_user = True
        if b.animation_data is None:
            b.animation_data_create()
        b.animation_data.action = act
        if hasattr(act, "slots"):
            slot = act.slots.new(b.id_type, b.name) if len(act.slots) == 0 else act.slots[0]
            try:
                b.animation_data.action_slot = slot
            except Exception:
                pass
        base = b.location.copy()
        b.location = base
        b.keyframe_insert("location", frame=1)
        b.location = base + Vector((0, 0.12, 0))
        b.keyframe_insert("location", frame=3)
        b.location = base
        b.keyframe_insert("location", frame=frames)
        act.frame_range = (1, frames)
        act.use_frame_range = True
        salib.stash_actions(b, [act], track_names=[name])
        acts.append(act)
    return acts


def idle_clip(obj, name="idle", frames=60, amount=0.02):
    """Very subtle breathing scale on the body so colonies have an `idle` clip (optional in game)."""
    act = bpy.data.actions.new(f"{obj.name}_{name}")
    act.use_fake_user = True
    if obj.animation_data is None:
        obj.animation_data_create()
    obj.animation_data.action = act
    if hasattr(act, "slots"):
        slot = act.slots.new(obj.id_type, obj.name) if len(act.slots) == 0 else act.slots[0]
        try:
            obj.animation_data.action_slot = slot
        except Exception:
            pass
    for f, s in ((1, 1.0), (frames // 2, 1.0 + amount), (frames, 1.0)):
        obj.scale = (1.0, 1.0, s)
        obj.keyframe_insert("scale", frame=f)
    act.frame_range = (1, frames)
    act.use_frame_range = True
    act.use_cyclic = True
    salib.stash_actions(obj, [act], track_names=[name])
    obj.scale = (1, 1, 1)
    return act


def join_into(objs, name, mats_keep=True, mirror_y=False):
    """Join the parts into one object.  `mirror_y` flips the layout so that coordinates read off the
    original sprites (image down = south = simulation +y) land on the right side in the game:
    Blender +Y exports to glTF -Z, i.e. simulation -y (north)."""
    salib.select_only(objs)
    bpy.ops.object.join()
    o = bpy.context.object
    o.name = name
    o.data.name = name
    if mirror_y:
        o.scale = (1.0, -1.0, 1.0)
        bpy.ops.object.transform_apply(scale=True)
        # the negative scale inverts the face winding: make every shell point outwards again
        # (Cycles shades back faces so the previews hide this, the game does not)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode="OBJECT")
    # realism pass: smooth the primitives and add a gentle surface undulation
    salib.detail_object(o, subdiv=1, displace=0.02, smooth_angle=40.0, noise_scale=0.6)
    return o


def spines(mats, count, radius, z_center, length, seed=2, mat="M_Dark"):
    rnd = random.Random(seed)
    out = []
    for i in range(count):
        a = i / count * 2 * math.pi + rnd.uniform(-0.1, 0.1)
        el = rnd.uniform(-0.15, 0.55)
        d = Vector((math.cos(a) * math.cos(el), math.sin(a) * math.cos(el), math.sin(el)))
        base = Vector((0, 0, z_center)) + d * radius * 0.85
        tip = base + d * length * rnd.uniform(0.8, 1.2)
        rot = d.to_track_quat("Z", "Y").to_euler()
        bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=0.09, radius2=0.0, depth=(tip - base).length, location=tuple((base + tip) / 2), rotation=rot)
        o = bpy.context.object
        o.data.materials.append(mats[mat])
        out.append(o)
    return out


def tube_chain(mats, points, radius, mat="M_Colony", verts=10):
    """Cylinders between consecutive points with sphere joints (robust curved tubes)."""
    out = []
    pts = [Vector(p) for p in points]
    for a, b in zip(pts, pts[1:]):
        d = b - a
        rot = d.to_track_quat("Z", "Y").to_euler()
        bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=radius, depth=d.length, location=tuple((a + b) / 2), rotation=rot)
        o = bpy.context.object
        o.data.materials.append(mats[mat])
        for p in o.data.polygons:
            p.use_smooth = True
        out.append(o)
    for p in pts[1:-1]:
        bpy.ops.mesh.primitive_uv_sphere_add(radius=radius * 1.02, segments=12, ring_count=8, location=tuple(p))
        j = bpy.context.object
        j.data.materials.append(mats[mat])
        for f in j.data.polygons:
            f.use_smooth = True
        out.append(j)
    return out


# ---------------------------------------------------------------------------------------------
# Second iteration: layouts, shapes and proportions follow the original 144-px colony sprites
# (reference pack Quick_References/Buildings/*_Colony_Y/Colony_Body.png, 24 px = 1 cell, oblique view).
# ---------------------------------------------------------------------------------------------
def _sphere(mats, pos, radius, mat, scale=(1, 1, 1), rot=(0, 0, 0), segments=20, rings=12, ico=None, jitter=0.0, seed=0):
    if ico is not None:
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=ico, radius=radius, location=pos)
    else:
        bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, segments=segments, ring_count=rings, location=pos)
    o = bpy.context.object
    o.scale = scale
    o.rotation_euler = rot
    bpy.ops.object.transform_apply(scale=True, rotation=True)
    if jitter > 0:
        rnd = random.Random(seed)
        for v in o.data.vertices:
            v.co += Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1))) * jitter
    o.data.materials.append(mats[mat])
    for f in o.data.polygons:
        f.use_smooth = True
    return o


def _cyl(mats, pos, radius, depth, mat, verts=24, rot=(0, 0, 0), scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=radius, depth=depth, location=pos, rotation=rot)
    o = bpy.context.object
    o.scale = scale
    bpy.ops.object.transform_apply(scale=True, rotation=True)
    o.data.materials.append(mats[mat])
    for f in o.data.polygons:
        f.use_smooth = verts > 8
    return o


def _box(mats, pos, size, mat, rot=(0, 0, 0), bevel=0.06):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=pos, rotation=rot)
    o = bpy.context.object
    o.scale = size
    bpy.ops.object.transform_apply(scale=True, rotation=True)
    o.data.materials.append(mats[mat])
    if bevel > 0:
        salib.bevel_object(o, min(bevel, min(size) * 0.3))
    return o


def _cone(mats, pos, r1, r2, depth, mat, rot=(0, 0, 0), verts=12):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r1, radius2=r2, depth=depth, location=pos, rotation=rot)
    o = bpy.context.object
    o.data.materials.append(mats[mat])
    for f in o.data.polygons:
        f.use_smooth = True
    return o


def _torus(mats, pos, major, minor, mat, rot=(0, 0, 0), segs=(36, 10)):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, location=pos, rotation=rot, major_segments=segs[0], minor_segments=segs[1])
    o = bpy.context.object
    o.data.materials.append(mats[mat])
    for f in o.data.polygons:
        f.use_smooth = True
    return o


def _spike(mats, base, direction, length, r1=0.09, mat="M_Colony"):
    d = Vector(direction).normalized()
    base = Vector(base)
    tip = base + d * length
    rot = d.to_track_quat("Z", "Y").to_euler()
    return _cone(mats, tuple((base + tip) / 2), r1, 0.0, length, mat, rot=rot, verts=8)


def _rock_material(mats, name="M_Rock", color=(0.33, 0.29, 0.25)):
    mats[name] = salib.material(name, color, roughness=0.95, kind="stone", variation=0.55)
    return mats[name]


def _finish_colony(name, body, turrets, barrels_all, radius, center_z):
    idle_clip(body)
    for t, bs in zip(turrets, barrels_all):
        turret_fire_clip(t, bs)
    objs = [body] + turrets + [b for bs in barrels_all for b in bs]
    path, s = salib.finalize_asset(name, objs, preview_radius=radius, preview_center=(0, 0, center_z), views=("front", "back", "left", "right", "threequarter", "top"))
    for i in range(len(turrets)):
        assert f"Turret_{i + 1}" in s["node_names"], s["node_names"]
    assert "M_Colony" in s["materials"], s["materials"]
    return path


def _attach(t, body):
    t.parent = body
    t.matrix_parent_inverse = body.matrix_world.inverted()


def build_ant_colony():
    """Rocky mound coiled by yellow rings, two tall cylinder towers (turrets on top) and a curved
    ramp in the south-east, as in the original sprite."""
    name = "colony_ant"
    salib.reset_scene(name)
    mats = salib.standard_materials("Y")
    _rock_material(mats)
    parts = []
    m = mound("Mound", mats, radius=2.5, height=1.85, noise=0.28, seed=4)
    m.data.materials.clear()
    m.data.materials.append(mats["M_Rock"])
    parts.append(m)
    rnd = random.Random(8)
    for i in range(12):  # boulders embedded in the mound
        a = rnd.uniform(0, 2 * math.pi)
        r = rnd.uniform(0.5, 2.3)
        z = max(0.0, 1.5 * (1 - (r / 2.6) ** 2)) * 0.85
        parts.append(_sphere(mats, (r * math.cos(a), r * math.sin(a), z), rnd.uniform(0.32, 0.6), "M_Rock",
                             scale=(rnd.uniform(0.8, 1.3), rnd.uniform(0.8, 1.3), rnd.uniform(0.5, 0.8)), ico=2, jitter=0.05, seed=i))
    # coiled yellow rings around the mound
    for rad, z, tilt in ((2.4, 0.36, 0.10), (2.0, 0.85, 0.12), (1.5, 1.3, 0.08)):
        parts.append(_torus(mats, (0.05, 0.1, z), rad, 0.21, "M_Colony", rot=(tilt, 0.0, 0.4)))
    # two tall towers with rims
    towers = ((-0.5, -1.4), (-0.3, 1.0))
    for x, y in towers:
        parts.append(_cyl(mats, (x, y, 1.0), 0.6, 2.0, "M_Colony"))
        parts.append(_torus(mats, (x, y, 2.0), 0.58, 0.07, "M_Dark", segs=(24, 8)))
    # curved ramp (quarter ring) in the south-east
    pts = [(2.45 * math.cos(math.radians(a)), 2.45 * math.sin(math.radians(a)), 0.42) for a in range(100, -21, -10)]
    parts += tube_chain(mats, pts, 0.36, mat="M_Colony", verts=12)
    body = join_into(parts, "ColonyBody", mirror_y=True)
    turrets, barrels_all = [], []
    for i, (x, y) in enumerate(towers):
        t, bs = twin_barrel_turret(f"Turret_{i + 1}", mats, (x, -y, 2.0 + 0.3), radius=0.3, barrel_len=0.6, barrel_r=0.06, spread=0.11)
        _attach(t, body)
        turrets.append(t)
        barrels_all.append(bs)
    return _finish_colony(name, body, turrets, barrels_all, 9.5, 0.9)


def build_beetle_colony():
    """Spiky yellow ball: eight bulging wedge plates around a central dome, a seamed top plate and
    long spikes radiating from the rim (original sprite)."""
    name = "colony_beetle"
    salib.reset_scene(name)
    mats = salib.standard_materials("Y")
    parts = [_sphere(mats, (0, 0, 0.75), 1.75, "M_Colony", scale=(1, 1, 0.9))]
    for i in range(8):  # bulging vertical plates around the ball
        a = i / 8 * 2 * math.pi + math.pi / 8
        parts.append(_sphere(mats, (1.35 * math.cos(a), 1.35 * math.sin(a), 0.85), 1.0, "M_Colony", scale=(1.15, 0.62, 0.95), rot=(0, 0, a)))
        g = i / 8 * 2 * math.pi
        parts.append(_box(mats, (1.6 * math.cos(g), 1.6 * math.sin(g), 1.0), (1.7, 0.06, 1.3), "M_Black", rot=(0, 0.55, g), bevel=0))
    parts.append(_cyl(mats, (0, 0, 2.05), 1.1, 0.3, "M_Colony"))                 # top plate
    parts.append(_box(mats, (0, 0, 2.2), (0.07, 2.1, 0.05), "M_Black", rot=(0, 0, 0.35), bevel=0))  # shell seam
    parts.append(_torus(mats, (0, 0, 2.19), 1.08, 0.05, "M_Dark", segs=(32, 6)))
    rnd = random.Random(3)
    for i in range(26):  # long spikes all around the ball
        a = i / 26 * 2 * math.pi + rnd.uniform(-0.08, 0.08)
        el = rnd.uniform(-0.05, 0.5)
        d = (math.cos(a) * math.cos(el), math.sin(a) * math.cos(el), math.sin(el))
        base = (2.0 * math.cos(a), 2.0 * math.sin(a), 0.5 + rnd.uniform(0.0, 1.1))
        parts.append(_spike(mats, base, d, rnd.uniform(1.0, 1.5), r1=0.1))
    for i in range(8):  # short spikes on the top plate rim
        a = i / 8 * 2 * math.pi + 0.2
        parts.append(_spike(mats, (0.95 * math.cos(a), 0.95 * math.sin(a), 2.18), (math.cos(a) * 0.6, math.sin(a) * 0.6, 0.8), 0.7, r1=0.08))
    body = join_into(parts, "ColonyBody", mirror_y=True)
    t, bs = twin_barrel_turret("Turret_1", mats, (0, 0, 2.2 + 0.34), radius=0.34, barrel_len=0.75, barrel_r=0.07, spread=0.13)
    _attach(t, body)
    return _finish_colony(name, body, [t], [bs], 10.0, 1.0)


def hex_turret(name, mats, pos, radius=0.34, height=0.5):
    """Spider sniper turret: hexagonal yellow tower with a dark muzzle opening and a thin barrel."""
    t = _cyl(mats, pos, radius, height, "M_Colony", verts=6)
    t.name = name
    hole = _cone(mats, (pos[0], pos[1] - radius * 0.9, pos[2] + 0.08), 0.15, 0.03, 0.3, "M_Black", rot=(math.radians(-90), 0, 0), verts=10)
    salib.select_only([t, hole])
    bpy.ops.object.join()
    t = bpy.context.object
    t.name = name
    barrel = _cyl(mats, (pos[0], pos[1] - radius - 0.3, pos[2] + 0.08), 0.045, 0.65, "M_Accent", verts=10, rot=(math.radians(90), 0, 0))
    barrel.name = f"{name}_Barrel_1"
    barrel.parent = t
    barrel.matrix_parent_inverse = t.matrix_world.inverted()
    return t, [barrel]


def build_spider_colony():
    """Pale striped mound wrapped by thick yellow legs meeting at a crowned summit hub, two pale
    cylinder towers carrying hexagonal sniper turrets (original sprite)."""
    name = "colony_spider"
    salib.reset_scene(name)
    mats = salib.standard_materials("Y")
    _rock_material(mats, "M_SpiderRock", (0.62, 0.55, 0.51))
    mats["M_Pale"] = salib.material("M_Pale", (0.80, 0.68, 0.64), roughness=0.7, kind="organic", variation=0.3)
    m = mound("Mound", mats, radius=2.45, height=1.65, noise=0.1, seed=6)
    m.data.materials.clear()
    m.data.materials.append(mats["M_SpiderRock"])
    parts = [m]
    # summit hub with a dark hole and a crown of knobs
    parts.append(_sphere(mats, (0, 0, 1.6), 0.65, "M_Colony", scale=(1, 1, 0.6)))
    parts.append(_cyl(mats, (0, 0, 1.78), 0.26, 0.4, "M_Black", verts=14))
    for i in range(10):
        a = i / 10 * 2 * math.pi
        parts.append(_sphere(mats, (0.62 * math.cos(a), 0.62 * math.sin(a), 1.74), 0.15, "M_Colony", segments=10, rings=8))
    # ten thick legs from the hub down to the ground
    for i in range(10):
        a = i / 10 * 2 * math.pi + 0.25
        c, s_ = math.cos(a), math.sin(a)
        pts = [(0.45 * c, 0.45 * s_, 1.62), (1.25 * c, 1.25 * s_, 1.48), (2.1 * c, 2.1 * s_, 0.95), (2.75 * c, 2.75 * s_, 0.3), (3.05 * c, 3.05 * s_, 0.05)]
        parts += tube_chain(mats, pts, 0.26, mat="M_Colony", verts=10)
    towers = ((-1.4, -1.5), (1.0, -0.3))
    for x, y in towers:
        parts.append(_cyl(mats, (x, y, 0.78), 0.46, 1.56, "M_Pale"))
        parts.append(_torus(mats, (x, y, 1.56), 0.44, 0.06, "M_Dark", segs=(24, 8)))
    body = join_into(parts, "ColonyBody", mirror_y=True)
    turrets, barrels_all = [], []
    for i, (x, y) in enumerate(towers):
        t, bs = hex_turret(f"Turret_{i + 1}", mats, (x, -y, 1.56 + 0.26))
        _attach(t, body)
        turrets.append(t)
        barrels_all.append(bs)
    return _finish_colony(name, body, turrets, barrels_all, 10.0, 1.0)


def build_scorpion_colony():
    """Armoured yellow fortress: plated base, vaulted dark entrance with a grate, honeycomb back
    slab with a three-slit face, spiked pillars, riveted claw-like plates (original sprite)."""
    name = "colony_scorpion"
    salib.reset_scene(name)
    mats = salib.standard_materials("Y")
    mats["M_Colony.honey"] = salib.material("M_Colony.honey", (0.97, 0.85, 0.47), roughness=0.5, kind="chitin", tint=True, variation=0.3, cell_scale=9.0, bump=0.7)
    mats["M_White"] = salib.material("M_White", (0.95, 0.95, 0.9), roughness=0.3, emission=(0.9, 0.9, 0.8), emission_strength=0.6, kind="glossy")
    parts = [_box(mats, (0, 0, 0.2), (5.4, 5.0, 0.4), "M_Colony", bevel=0.08)]
    # vaulted entrance in the south: roof, dark interior, arch ring, grate
    parts.append(_cyl(mats, (0.2, 1.2, 0.4), 1.15, 1.6, "M_Colony", rot=(math.radians(90), 0, 0)))
    parts.append(_box(mats, (0.2, 1.6, 0.55), (1.9, 1.4, 1.0), "M_Black", bevel=0))
    parts.append(arch("Arch", mats, (0.2, 2.3, 0.0), 1.05, 0.2, rot_z=0.0))
    for x in (-0.4, 0.2, 0.8):
        parts.append(_cyl(mats, (x, 2.25, 0.5), 0.035, 1.0, "M_Black", verts=6))
    for z in (0.45, 0.85):
        parts.append(_cyl(mats, (0.2, 2.25, z), 0.035, 1.8, "M_Black", verts=6, rot=(0, math.radians(90), 0)))
    # honeycomb back slab with the face slits
    parts.append(_box(mats, (0.4, -1.7, 1.15), (2.4, 0.6, 2.3), "M_Colony.honey", bevel=0.05))
    for x in (0.1, 0.4, 0.7):
        parts.append(_box(mats, (x, -1.37, 1.35), (0.12, 0.06, 0.35), "M_White", bevel=0))
    # spiked pillars
    for x, y, h in ((-1.1, -1.9, 2.2), (1.9, -1.9, 2.0), (-2.3, -2.3, 1.2), (2.4, -2.4, 1.3)):
        parts.append(_cyl(mats, (x, y, h / 2), 0.3, h, "M_Colony", verts=14))
        parts.append(_cone(mats, (x, y, h + 0.35), 0.32, 0.0, 0.8, "M_Colony", verts=10))
    # claw-like riveted plates on both sides
    rnd = random.Random(5)
    for sx in (-1, 1):
        cx = sx * 1.95
        parts.append(_sphere(mats, (cx, 0.2, 0.5), 0.95, "M_Colony", scale=(1.0, 1.35, 0.62)))
        parts.append(_sphere(mats, (cx, -1.0, 0.45), 0.7, "M_Colony", scale=(1.0, 1.0, 0.6)))
        parts.append(_cone(mats, (cx + sx * 0.2, 1.75, 0.45), 0.45, 0.05, 1.1, "M_Colony", rot=(math.radians(90), 0, 0), verts=12))
        for i in range(6):
            a = rnd.uniform(0, 2 * math.pi)
            r = rnd.uniform(0.2, 0.7)
            parts.append(_sphere(mats, (cx + r * math.cos(a), 0.2 + r * 1.3 * math.sin(a), 0.5 + 0.62 * math.sqrt(max(0.0, 1 - (r / 0.95) ** 2)) * 0.95), 0.11, "M_Black", segments=10, rings=8))
    body = join_into(parts, "ColonyBody", mirror_y=True)
    t, bs = twin_barrel_turret("Turret_1", mats, (-1.1, 1.9, 2.2 + 0.3), radius=0.3, barrel_len=0.65, barrel_r=0.06, spread=0.11)
    _attach(t, body)
    return _finish_colony(name, body, [t], [bs], 10.0, 1.0)


def build_wasp_colony():
    """Cluster of rimmed hexagonal cells of different heights with eggs in their sunken tops, and a
    big slanted slab with raised panels on the right, over a rocky base (original sprite)."""
    name = "colony_wasp"
    salib.reset_scene(name)
    mats = salib.standard_materials("Y")
    _rock_material(mats)
    mats["M_Pale"] = salib.material("M_Pale", (0.92, 0.85, 0.70), roughness=0.6, kind="organic", variation=0.3)
    m = mound("Base", mats, radius=2.75, height=0.55, noise=0.25, seed=9)
    m.data.materials.clear()
    m.data.materials.append(mats["M_Rock"])
    parts = [m]
    cells = [((-1.9, -1.6), 1.9), ((-0.7, -1.6), 1.5), ((0.5, -1.6), 1.3), ((-1.3, -0.55), 2.1), ((-0.1, -0.55), 1.7),
             ((-1.9, 0.5), 1.6), ((-0.7, 0.5), 1.4), ((-1.3, 1.55), 1.2), ((-2.5, -0.55), 1.3)]
    for (x, y), h in cells:
        parts.append(_cyl(mats, (x, y, h / 2), 0.62, h, "M_Colony", verts=6))
        parts.append(_cyl(mats, (x, y, h), 0.7, 0.14, "M_Colony", verts=6))
        parts.append(_cyl(mats, (x, y, h + 0.1), 0.5, 0.06, "M_Dark", verts=6))
        parts.append(_sphere(mats, (x, y, h + 0.12), 0.3, "M_Pale", scale=(1, 1, 0.6)))
    tilt = math.radians(-28)
    parts.append(_box(mats, (1.3, 0.6, 1.0), (2.4, 3.4, 0.42), "M_Colony", rot=(tilt, 0, 0), bevel=0.06))
    for dx, dy in ((-0.55, -1.0), (0.55, -1.0), (-0.55, 0.1), (0.55, 0.1)):
        # raised panels on the slab surface (rotate the offset with the slab)
        lz = 0.27
        y = 0.6 + dy * math.cos(tilt) - lz * math.sin(tilt)
        z = 1.0 + dy * math.sin(tilt) + lz * math.cos(tilt)
        parts.append(_box(mats, (1.3 + dx, y, z), (0.85, 0.6, 0.12), "M_Colony", rot=(tilt, 0, 0), bevel=0.03))
    parts.append(_box(mats, (2.55, 0.6, 1.02), (0.16, 3.4, 0.5), "M_Dark", rot=(tilt, 0, 0), bevel=0.03))
    body = join_into(parts, "ColonyBody", mirror_y=True)
    t, bs = twin_barrel_turret("Turret_1", mats, (1.0, 0.9, 1.8 + 0.3), radius=0.3, barrel_len=0.7, barrel_r=0.06, spread=0.11)
    _attach(t, body)
    return _finish_colony(name, body, [t], [bs], 10.0, 1.0)


BUILDERS = {
    "colony_ant": build_ant_colony,
    "colony_beetle": build_beetle_colony,
    "colony_spider": build_spider_colony,
    "colony_scorpion": build_scorpion_colony,
    "colony_wasp": build_wasp_colony,
}

if __name__ == "__main__":
    flags = [a for a in salib.script_args() if a.startswith("-")]
    args = [a for a in salib.script_args() if not a.startswith("-")] or (list(BUILDERS) if "--all" in flags else ["colony_ant"])
    for a in args:
        if a not in BUILDERS:
            raise SystemExit(f"unknown colony {a}; choose from {list(BUILDERS)}")
        BUILDERS[a]()
        print("BUILT", a, flush=True)
