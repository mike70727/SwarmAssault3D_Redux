"""Builds the five faction colonies: colony_ant, colony_beetle, colony_spider, colony_scorpion,
colony_wasp.

Fourth iteration (model crew, second shift).  Every layout below is fitted to the original 144-px
colony sprites (reference/models/colony_<family>/colony_body_<team>.png, 24 px = 1 cell), which are
orthographic renders from the south at ~60 deg elevation (tower-top rims 24 x 21 px; the ant's rope
rings have aspect 0.87).  With the frame centre = colony centre a point projects to the sprite as
    u = X,   v (down) = -(0.866 Y + 0.5 Z)        (cells; Blender X east, Y north, Z up)
so a sprite feature fixes 0.866 Y + 0.5 Z; heights come from second constraints (ring radii, feet on
the ground, wall faces) and from the original 3-D renders of the loading screens (reference/models/
_common: ant = loading 0 top, spider = loading 1 bottom-left, beetle = loading 2 bottom).
Turret positions: OpenSA's Turreted offsets (forward F, right R in WDist) map to the sprite as
u = R/1024, v = -0.632 F/1024 (calibrated on the four measured ant/spider tower tops); that puts the
beetle turret on its cap (top 1.72), the scorpion turret on the honeycomb-topped tower and the wasp
turret on the big west cell.  colonies.ron offsets = (pivot x, -pivot y), height = barrel axis z.

Shared contract: origin at the centre of the 6x6 footprint on the ground, Z up, the turret objects
Turret_1.. have their origin on the yaw axis at the tower top, barrels point -Y (sim south) at
rest; `idle` clip on the body, `turret_fire` (recoil) on the <Turret>_Barrels children.
Team-coloured parts use M_Colony (and M_Colony.<variant> - the game tints by the name before the
dot); their textures bake light grey, the colour is the glTF factor replaced at runtime
(M_Colony.dark / .tower are darkened bakes = a darker shade of the team colour).

Usage: blender -b --factory-startup --python build_colony.py -- colony_ant [colony_beetle ...]
       flags: --all (every colony), --quick (no bake/export: only the sprite-view check renders).
Set SA_COLONY_QA_DIR to a folder to get, per colony, <name>_spriteview.png (with turrets),
<name>_spriteview_body.png (body only, transparent: silhouette overlay against the body sprite) and a
side-by-side sprite/model image (SA_COLONY_REF_DIR = the folder holding colony_<family>/colony_body_Y.png).
"""
import math
import os
import random
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmesh  # noqa: E402
import bpy  # noqa: E402
import salib  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

QA_DIR = os.environ.get("SA_COLONY_QA_DIR")
REF_DIR = os.environ.get("SA_COLONY_REF_DIR")
SPRITE_ELEVATION = 60.0  # degrees, the original sprites' camera (game camera: 58)
TRI_BUDGET = 27000


# ---------------------------------------------------------------------------------------------
# primitives (all transforms applied; every part is a plain mesh object with one material)
# ---------------------------------------------------------------------------------------------
def _smooth(o, smooth=True):
    for f in o.data.polygons:
        f.use_smooth = smooth
    return o


def _sphere(mats, pos, radius, mat, scale=(1, 1, 1), rot=(0, 0, 0), segments=24, rings=14, ico=None,
            jitter=0.0, seed=0, smooth=True):
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
    return _smooth(o, smooth)


def _cyl(mats, pos, radius, depth, mat, verts=24, rot=(0, 0, 0), scale=(1, 1, 1), smooth=None):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=radius, depth=depth, location=pos, rotation=rot)
    o = bpy.context.object
    o.scale = scale
    bpy.ops.object.transform_apply(scale=True, rotation=True)
    o.data.materials.append(mats[mat])
    if smooth is None:
        smooth = verts > 8
    if smooth:
        # smooth the wall, keep the caps flat
        for f in o.data.polygons:
            f.use_smooth = abs(f.normal.z) < 0.5 if rot == (0, 0, 0) else True
    return o


def _box(mats, pos, size, mat, rot=(0, 0, 0), bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=pos, rotation=rot)
    o = bpy.context.object
    o.scale = size
    bpy.ops.object.transform_apply(scale=True, rotation=True)
    o.data.materials.append(mats[mat])
    if bevel > 0:
        salib.bevel_object(o, min(bevel, min(size) * 0.3))
    return o


def _cone(mats, pos, r1, r2, depth, mat, rot=(0, 0, 0), verts=12, smooth=True):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r1, radius2=r2, depth=depth, location=pos, rotation=rot)
    o = bpy.context.object
    bpy.ops.object.transform_apply(rotation=True)
    o.data.materials.append(mats[mat])
    return _smooth(o, smooth)


def _torus(mats, pos, major, minor, mat, rot=(0, 0, 0), segs=(32, 10)):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, location=pos, rotation=rot,
                                     major_segments=segs[0], minor_segments=segs[1])
    o = bpy.context.object
    bpy.ops.object.transform_apply(rotation=True)
    o.data.materials.append(mats[mat])
    return _smooth(o)


def _spike(mats, base, direction, length, r1=0.09, mat="M_Colony", verts=8, limit=2.95):
    d = Vector(direction).normalized()
    base = Vector(base)
    tip = base + d * length
    for axis in (0, 1):  # keep the tip inside the 6x6 footprint
        if abs(tip[axis]) > limit and abs(d[axis]) > 1e-6:
            length = min(length, (limit * (1 if d[axis] > 0 else -1) - base[axis]) / d[axis])
            tip = base + d * length
    rot = d.to_track_quat("Z", "Y").to_euler()
    return _cone(mats, tuple((base + tip) / 2), r1, 0.0, length, mat, rot=rot, verts=verts)


def tube(mats, name, pts, radius, mat, radii=None, bevel_res=5, res_u=8, caps=True):
    """Smooth round tube along a Bezier path through `pts` (optional per-point radius factors)."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = bevel_res
    cu.resolution_u = res_u
    cu.fill_mode = "FULL"
    cu.use_fill_caps = caps
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        bp = sp.bezier_points[i]
        bp.co = Vector(p)
        bp.handle_left_type = bp.handle_right_type = "AUTO"
        if radii is not None:
            bp.radius = radii[i]
    ob = bpy.data.objects.new(name, cu)
    salib.link(ob)
    salib.select_only([ob])
    bpy.ops.object.convert(target="MESH")
    ob = bpy.context.object
    ob.data.materials.append(mats[mat])
    return _smooth(ob)


def convex_part(mats, points, mat, name="Hull", bevel=0.0, smooth=False):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    for p in points:
        bm.verts.new(Vector(p))
    bm.verts.ensure_lookup_table()
    res = bmesh.ops.convex_hull(bm, input=bm.verts)
    junk = {g for g in res.get("geom_unused", []) + res.get("geom_interior", []) if isinstance(g, bmesh.types.BMVert)}
    if junk:
        bmesh.ops.delete(bm, geom=list(junk), context="VERTS")
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    salib.link(o)
    o.data.materials.append(mats[mat])
    if bevel > 0:
        salib.bevel_object(o, bevel, segments=2)
    return _smooth(o, smooth)


def mound(name, mats, mat, center, radii, height, shear=(0.0, 0.0), noise=0.1, noise_scale=0.8, seed=1,
          segments=56, rings=28, flatten=-0.05):
    """Flat-bottomed lumpy dome.  `shear` moves the summit sideways (per unit of height)."""
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, segments=segments, ring_count=rings, location=(0, 0, 0))
    o = bpy.context.object
    o.name = name
    o.scale = (radii[0], radii[1], height)
    bpy.ops.object.transform_apply(scale=True)
    me = o.data
    for v in me.vertices:
        if v.co.z < flatten:
            v.co.z = flatten
        else:
            v.co.x += shear[0] * v.co.z
            v.co.y += shear[1] * v.co.z
    me.update()
    if noise > 0:
        tex = bpy.data.textures.get("MoundNoise") or bpy.data.textures.new("MoundNoise", "CLOUDS")
        tex.noise_scale = noise_scale
        tex.noise_depth = 3
        d = o.modifiers.new("Displace", "DISPLACE")
        d.texture = tex
        d.strength = noise
        d.mid_level = 0.5
        d.texture_coords = "LOCAL"
        salib.select_only([o])
        bpy.ops.object.modifier_apply(modifier=d.name)
        for v in me.vertices:
            if v.co.z < flatten:
                v.co.z = flatten
    o.location = (center[0], center[1], 0.0)
    bpy.ops.object.transform_apply(location=True)
    o.data.materials.append(mats[mat])
    return _smooth(o)


def _catmull(points, steps):
    """Catmull-Rom resampling of a 2-D polyline (keeps the end points)."""
    out = []
    n = len(points)
    for i in range(n - 1):
        p0, p1, p2, p3 = (Vector(points[max(0, i - 1)]), Vector(points[i]), Vector(points[i + 1]),
                          Vector(points[min(n - 1, i + 2)]))
        for k in range(steps):
            t = k / steps
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(Vector(points[-1]))
    return [(p.x, p.y) for p in out]


def lathe_r(profile, z):
    """Radius of a lathe profile [(r, z), ...] (z ascending) at height z."""
    if z <= profile[0][1]:
        return profile[0][0]
    for (r0, z0), (r1, z1) in zip(profile, profile[1:]):
        if z <= z1:
            return r0 + (r1 - r0) * (z - z0) / max(1e-9, z1 - z0)
    return profile[-1][0]


def lathe_mound(name, mats, mat, center, profile, scale=(1.0, 1.0), segments=64, steps=3, noise=0.1, noise_scale=0.6,
                seed=1, rot=0.0):
    """Closed lathe solid standing on the ground: flat bottom, rings from the (r, z) profile (r = 0 at
    the end closes the top), scaled elliptically, with a radial Clouds displacement (lumps)."""
    prof = _catmull(profile, steps)
    verts = [(center[0], center[1], 0.0)]
    rings = []
    apex = None
    for r, z in prof:
        if r <= 1e-4:
            apex = len(verts)
            verts.append((center[0], center[1], z))
            break
        idx = []
        for j in range(segments):
            a = 2 * math.pi * j / segments
            idx.append(len(verts))
            lx, ly = r * scale[0] * math.cos(a), r * scale[1] * math.sin(a)
            cr, sr = math.cos(math.radians(rot)), math.sin(math.radians(rot))
            verts.append((center[0] + lx * cr - ly * sr, center[1] + lx * sr + ly * cr, max(0.0, z)))
        rings.append(idx)
    faces = []
    for j in range(segments):
        faces.append((0, rings[0][(j + 1) % segments], rings[0][j]))
    for ra, rb in zip(rings, rings[1:]):
        for j in range(segments):
            k = (j + 1) % segments
            faces.append((ra[j], ra[k], rb[k], rb[j]))
    if apex is not None:
        last = rings[-1]
        for j in range(segments):
            faces.append((last[j], last[(j + 1) % segments], apex))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    o = bpy.data.objects.new(name, me)
    salib.link(o)
    salib.select_only([o])
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    if noise > 0:
        tex = bpy.data.textures.get(f"LatheNoise{seed}") or bpy.data.textures.new(f"LatheNoise{seed}", "CLOUDS")
        tex.noise_scale = noise_scale
        tex.noise_depth = 3
        d = o.modifiers.new("Displace", "DISPLACE")
        d.texture = tex
        d.strength = noise
        d.mid_level = 0.5
        d.texture_coords = "GLOBAL"
        bpy.ops.object.modifier_apply(modifier=d.name)
        for v in o.data.vertices:
            if v.co.z < 0.0:
                v.co.z = 0.0
    o.data.materials.append(mats[mat])
    return _smooth(o)


def hull_z(ellipsoids, x, y):
    """Highest surface of a list of ellipsoids (cx, cy, cz, rx, ry, rz) at ground point (x, y)."""
    best = 0.0
    for cx, cy, cz, rx, ry, rz in ellipsoids:
        r2 = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2
        if r2 < 1.0:
            best = max(best, cz + rz * math.sqrt(1.0 - r2))
    return best


def curved_wall(mats, center, a0, a1, r_in, r_out, height, mat, steps=32, bevel=0.05, name="CurvedWall", batter=None):
    """Curved wall standing on the ground around `center` from angle a0 to a1 (degrees); r_in, r_out
    and height are functions of t in [0, 1] along the wall (flat top, square ends).  `batter(t)` moves
    the foot of the outer face outwards (a sloping outer face, like a ramp)."""
    verts, faces = [], []
    for k in range(steps + 1):
        t = k / steps
        a = math.radians(a0 + (a1 - a0) * t)
        c, s = math.cos(a), math.sin(a)
        ri, ro, h = r_in(t), r_out(t), height(t)
        bt = batter(t) if batter else 0.0
        for r, z in ((ri, 0.0), (ri, h), (ro, h), (ro + bt, 0.0)):
            verts.append((center[0] + r * c, center[1] + r * s, z))
    for k in range(steps):
        b, n = k * 4, k * 4 + 4
        faces += [(b, n, n + 1, b + 1), (b + 1, n + 1, n + 2, b + 2), (b + 2, n + 2, n + 3, b + 3), (b + 3, n + 3, n, b)]
    e = steps * 4
    faces += [(0, 1, 2, 3), (e + 3, e + 2, e + 1, e)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    o = bpy.data.objects.new(name, me)
    salib.link(o)
    salib.select_only([o])
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    o.data.materials.append(mats[mat])
    if bevel > 0:
        salib.bevel_object(o, bevel, segments=2)
    for f in o.data.polygons:
        f.use_smooth = abs(f.normal.z) < 0.5
    return o


def fluted_cyl(mats, pos, r, depth, mat, flutes=16, groove=0.08, segs_per=2, name="Fluted"):
    """Vertical cylinder with `flutes` rounded vertical ribs (star-ish cross-section), base at pos.z."""
    n = flutes * segs_per * 2
    verts, faces = [], []
    for z in (pos[2], pos[2] + depth):
        for j in range(n):
            a = 2 * math.pi * j / n
            rr = r - groove * (0.5 - 0.5 * math.cos(2 * math.pi * flutes * j / n))
            verts.append((pos[0] + rr * math.cos(a), pos[1] + rr * math.sin(a), z))
    for j in range(n):
        k = (j + 1) % n
        faces.append((j, k, n + k, n + j))
    faces.append(tuple(range(n - 1, -1, -1)))
    faces.append(tuple(range(n, 2 * n)))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    o = bpy.data.objects.new(name, me)
    salib.link(o)
    o.data.materials.append(mats[mat])
    for f in o.data.polygons:
        f.use_smooth = abs(f.normal.z) < 0.5
    return o


def _smooth_path(pts, steps=4):
    """Catmull-Rom resampling of a 3-D polyline."""
    out = []
    n = len(pts)
    for i in range(n - 1):
        p0, p1, p2, p3 = (Vector(pts[max(0, i - 1)]), Vector(pts[i]), Vector(pts[i + 1]), Vector(pts[min(n - 1, i + 2)]))
        for k in range(steps):
            t = k / steps
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                                    (-p0 + 3 * p1 - 3 * p2 + p3) * t3)))
    out.append(tuple(pts[-1]))
    return out


def screen_to_surface(u, v, zfun, el=SPRITE_ELEVATION):
    """Point of a height field zfun(x, y) seen at sprite-screen position (u, v) (cells, v down): march
    the view ray from high above down to the surface."""
    se, ce = math.sin(math.radians(el)), math.cos(math.radians(el))
    for k in range(400):
        z = 4.0 - k * 0.01
        y = (-v - ce * z) / se
        if zfun(u, y) >= z:
            return (u, y, z)
    return (u, -v / se, 0.0)


def set_origin(o, point):
    """Move the object origin to `point` (world) without moving the geometry."""
    point = Vector(point)
    delta = point - o.matrix_world.translation
    o.data.transform(Matrix.Translation(-delta))
    o.location = o.location + delta


def join_into(objs, name):
    salib.select_only(objs)
    bpy.ops.object.join()
    o = bpy.context.object
    o.name = name
    o.data.name = name
    o.data.validate()
    return o


def tri_count(o):
    o.data.calc_loop_triangles()
    return len(o.data.loop_triangles)


# ---------------------------------------------------------------------------------------------
# materials: the shared procedural shaders plus colony-specific surface tweaks
# ---------------------------------------------------------------------------------------------
def _principled(mat):
    return next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def _coord(nt):
    tc = nt.nodes.new("ShaderNodeTexCoord")
    return tc.outputs["Object"]


def add_height(mat, socket, weight):
    """Add a height signal (0..1 socket) into the material's bump."""
    nt = mat.node_tree
    bmp = next((n for n in nt.nodes if n.type == "BUMP"), None)
    if bmp is None:
        bmp = nt.nodes.new("ShaderNodeBump")
        bmp.inputs["Strength"].default_value = 0.5
        bmp.inputs["Distance"].default_value = 0.02
        nt.links.new(bmp.outputs["Normal"], _principled(mat).inputs["Normal"])
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    nt.links.new(socket, mul.inputs[0])
    mul.inputs[1].default_value = weight
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    links = bmp.inputs["Height"].links
    if links:
        nt.links.new(links[0].from_socket, add.inputs[0])
    else:
        add.inputs[0].default_value = 0.0
    nt.links.new(mul.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], bmp.inputs["Height"])
    return bmp


def cobbles(mat, scale=5.0, weight=1.2, randomness=0.9):
    """Rounded cobble/boulder relief (inverted Voronoi distance)."""
    nt = mat.node_tree
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = scale
    vor.inputs["Randomness"].default_value = randomness
    nt.links.new(_coord(nt), vor.inputs["Vector"])
    inv = nt.nodes.new("ShaderNodeMath")
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.0
    nt.links.new(vor.outputs["Distance"], inv.inputs[1])
    pw = nt.nodes.new("ShaderNodeMath")
    pw.operation = "POWER"
    nt.links.new(inv.outputs[0], pw.inputs[0])
    pw.inputs[1].default_value = 2.0
    add_height(mat, pw.outputs[0], weight)
    return mat


def ribs(mat, scale=4.0, weight=0.6, direction="Z"):
    """Horizontal ring ribs (wave bands along an axis) in the bump."""
    nt = mat.node_tree
    w = nt.nodes.new("ShaderNodeTexWave")
    w.wave_type = "BANDS"
    w.bands_direction = direction
    w.wave_profile = "SIN"
    w.inputs["Scale"].default_value = scale
    w.inputs["Distortion"].default_value = 0.0
    w.inputs["Detail"].default_value = 0.0
    nt.links.new(_coord(nt), w.inputs["Vector"])
    add_height(mat, w.outputs["Fac"], weight)
    return mat


def speckle(mat, scale=40.0, dark=0.5, light=1.4, lo=0.3, hi=0.72, bump=0.4):
    """Granite speckle: fine high-contrast dark/light grains multiplied into the base colour."""
    nt = mat.node_tree
    p = _principled(mat)
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = 2.0
    n.inputs["Roughness"].default_value = 0.7
    nt.links.new(_coord(nt), n.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = lo
    ramp.color_ramp.elements[0].color = (dark, dark, dark, 1.0)
    ramp.color_ramp.elements[1].position = hi
    ramp.color_ramp.elements[1].color = (light, light * 0.97, light * 0.93, 1.0)
    nt.links.new(n.outputs["Factor"], ramp.inputs["Fac"])
    src = p.inputs["Base Color"].links[0].from_socket
    nt.links.new(salib._mix_rgb(nt, "MULTIPLY", src, ramp.outputs["Color"], 1.0), p.inputs["Base Color"])
    if bump > 0:
        add_height(mat, n.outputs["Factor"], bump)
    return mat


def swirl(mat, scale=2.2, weight=0.9):
    """Swirling ridges (twisted rings) in the bump - the larva domes of the wasp cells."""
    nt = mat.node_tree
    w = nt.nodes.new("ShaderNodeTexWave")
    w.wave_type = "RINGS"
    w.rings_direction = "Z"
    w.inputs["Scale"].default_value = scale
    w.inputs["Distortion"].default_value = 6.0
    w.inputs["Detail"].default_value = 1.0
    nt.links.new(_coord(nt), w.inputs["Vector"])
    add_height(mat, w.outputs["Fac"], weight)
    return mat


def darken(mat, k):
    """Multiply the base colour by a constant (kept in the bake: a darker / paler team tint)."""
    nt = mat.node_tree
    p = _principled(mat)
    src = p.inputs["Base Color"].links[0].from_socket
    nt.links.new(salib._mix_rgb(nt, "MULTIPLY", src, (k, k, k, 1.0), 1.0), p.inputs["Base Color"])
    return mat


def stripes(mat, scale=1.6, distortion=5.0, dark=0.35, light=1.15, direction="DIAGONAL"):
    """Wavy strata bands multiplied into the base colour (spider mound)."""
    nt = mat.node_tree
    p = _principled(mat)
    w = nt.nodes.new("ShaderNodeTexWave")
    w.wave_type = "BANDS"
    w.bands_direction = direction
    w.inputs["Scale"].default_value = scale
    w.inputs["Distortion"].default_value = distortion
    w.inputs["Detail"].default_value = 3.0
    w.inputs["Detail Roughness"].default_value = 0.6
    nt.links.new(_coord(nt), w.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.25
    ramp.color_ramp.elements[0].color = (dark, dark, dark, 1.0)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (light, light, light, 1.0)
    nt.links.new(w.outputs["Fac"], ramp.inputs["Fac"])
    src = p.inputs["Base Color"].links[0].from_socket
    out = salib._mix_rgb(nt, "MULTIPLY", src, ramp.outputs["Color"], 1.0)
    nt.links.new(out, p.inputs["Base Color"])
    add_height(mat, w.outputs["Fac"], 0.5)
    return mat


def colony_materials(team="Y"):
    """Shared materials plus the colony palette.  Team-coloured surfaces (M_Colony*) are tinted,
    baked light so the runtime colour factor stays clean."""
    mats = salib.standard_materials(team)
    col = (0.97, 0.85, 0.47)
    mats["M_Colony"] = salib.material("M_Colony", col, roughness=0.5, kind="chitin", tint=True, variation=0.18,
                                      cell_scale=9.0, bump=0.3, dirt=0.25, coat=0.25)
    mats["M_Colony.knob"] = salib.material("M_Colony.knob", col, roughness=0.6, kind="chitin", tint=True,
                                           variation=0.2, cell_scale=40.0, bump=1.0, dirt=0.3, coat=0.15)
    mats["M_Colony.rib"] = ribs(salib.material("M_Colony.rib", col, roughness=0.5, kind="chitin", tint=True,
                                               variation=0.18, cell_scale=9.0, bump=0.3, dirt=0.25), scale=5.0, weight=0.7)
    mats["M_Colony.plate"] = salib.material("M_Colony.plate", col, roughness=0.45, kind="chitin", tint=True,
                                            variation=0.15, cell_scale=20.0, bump=0.5, dirt=0.3, coat=0.3)
    mats["M_Rock"] = cobbles(salib.material("M_Rock", (0.36, 0.30, 0.24), roughness=0.95, kind="stone", variation=0.55),
                             scale=4.5, weight=2.5)
    mats["M_Granite"] = speckle(cobbles(salib.material("M_Granite", (0.5, 0.44, 0.38), roughness=0.9, kind="stone",
                                                     variation=0.6), scale=7.0, weight=1.6), scale=38.0, dark=0.42,
                                light=1.5)
    mats["M_Earth"] = cobbles(salib.material("M_Earth", (0.26, 0.22, 0.18), roughness=1.0, kind="earth"), scale=12.0, weight=0.7)
    mats["M_Silver"] = stripes(salib.material("M_Silver", (0.74, 0.74, 0.75), roughness=0.35, metallic=0.7, kind="metal"),
                               scale=2.0, distortion=7.0, dark=0.18, light=1.35, direction="Z")
    mats["M_Chrome"] = stripes(salib.material("M_Chrome", (0.7, 0.7, 0.73), roughness=0.25, metallic=0.15, kind="glossy"),
                               scale=0.85, distortion=6.0, dark=0.22, light=1.55, direction="Z")
    mats["M_Colony.dark"] = darken(salib.material("M_Colony.dark", col, roughness=0.5, kind="chitin", tint=True,
                                                  variation=0.12, cell_scale=8.0, bump=0.2, dirt=0.2), 0.42)
    mats["M_Colony.tower"] = darken(salib.material("M_Colony.tower", col, roughness=0.55, kind="chitin", tint=True,
                                                   variation=0.12, cell_scale=6.0, bump=0.15, dirt=0.2), 0.72)
    mats["M_RockDark"] = cobbles(salib.material("M_RockDark", (0.16, 0.145, 0.13), roughness=0.95, kind="stone",
                                                variation=0.5, dirt=0.6), scale=5.0, weight=1.5)
    mats["M_Hollow"] = salib.material("M_Hollow", (0.035, 0.03, 0.026), roughness=0.95, kind="stone", variation=0.3,
                                      bump=0.2, dirt=0.0)
    mats["M_Colony.egg"] = swirl(salib.material("M_Colony.egg", col, roughness=0.45, kind="chitin", tint=True,
                                                variation=0.1, cell_scale=4.0, bump=0.2, dirt=0.15, coat=0.3))
    mats["M_Pale"] = salib.material("M_Pale", (0.78, 0.69, 0.65), roughness=0.65, kind="organic", variation=0.2)
    mats["M_Bone"] = salib.material("M_Bone", (0.80, 0.77, 0.68), roughness=0.7, kind="organic", variation=0.25)
    mats["M_Wood"] = salib.material("M_Wood", (0.45, 0.28, 0.17), roughness=0.75, kind="wood")
    mats["M_Gunmetal"] = salib.material("M_Gunmetal", (0.22, 0.22, 0.24), roughness=0.4, metallic=0.9, kind="metal")
    mats["M_Iron"] = salib.material("M_Iron", (0.27, 0.27, 0.28), roughness=0.4, metallic=0.35, kind="glossy")
    mats["M_GunGrey"] = salib.material("M_GunGrey", (0.46, 0.44, 0.4), roughness=0.4, metallic=0.35, kind="glossy")
    mats["M_Gun"] = salib.material("M_Gun", (0.47, 0.46, 0.37), roughness=0.45, metallic=0.85, kind="metal")
    mats["M_Egg"] = salib.material("M_Egg", (0.92, 0.88, 0.74), roughness=0.4, kind="organic", sss=0.3, variation=0.15)
    mats["M_White"] = salib.material("M_White", (0.95, 0.95, 0.9), roughness=0.3, emission=(0.95, 0.95, 0.85),
                                     emission_strength=1.2, kind="glossy")
    return mats


# ---------------------------------------------------------------------------------------------
# clips
# ---------------------------------------------------------------------------------------------
def _own_action(obj, name):
    act = bpy.data.actions.new(name)
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
    return act


def turret_fire_clip(turret, barrels, name="turret_fire", frames=8, recoil=0.12):
    acts = []
    for b in barrels:
        act = _own_action(b, f"{turret.name}_{name}")
        base = b.location.copy()
        b.location = base
        b.keyframe_insert("location", frame=1)
        b.location = base + Vector((0, recoil, 0))
        b.keyframe_insert("location", frame=3)
        b.location = base
        b.keyframe_insert("location", frame=frames)
        act.frame_range = (1, frames)
        act.use_frame_range = True
        salib.stash_actions(b, [act], track_names=[name])
        acts.append(act)
    return acts


def idle_clip(obj, name="idle", frames=60, amount=0.01):
    act = _own_action(obj, f"{obj.name}_{name}")
    for f, s in ((1, 1.0), (frames // 2, 1.0 + amount), (frames, 1.0)):
        obj.scale = (1.0, 1.0, s)
        obj.keyframe_insert("scale", frame=f)
    act.frame_range = (1, frames)
    act.use_frame_range = True
    act.use_cyclic = True
    salib.stash_actions(obj, [act], track_names=[name])
    obj.scale = (1, 1, 1)
    return act


# ---------------------------------------------------------------------------------------------
# turrets (origin = yaw pivot on the tower top; the moving parts are one child object)
# ---------------------------------------------------------------------------------------------
def _make_turret(name, mats, pivot, fixed, moving):
    t = join_into(fixed, name)
    set_origin(t, pivot)
    b = join_into(moving, f"{name}_Barrels")
    set_origin(b, pivot)
    b.parent = t
    b.matrix_parent_inverse = t.matrix_world.inverted()
    return t, [b]


def ant_turret(name, mats, pivot):
    """Team-coloured ball on a dark ring with two dark machine-gun barrels (turret sprite)."""
    p = Vector(pivot)
    # ball ~1.08 cells across (turret sprite: 26 px), sunk a little into the tower top; barrel tips
    # 0.9 from the yaw axis (sprite: 20 px)
    fixed = [_sphere(mats, p + Vector((0, 0, 0.44)), 0.52, "M_Colony", segments=32, rings=18),
             _cyl(mats, p + Vector((0, 0, 0.04)), 0.36, 0.08, "M_Colony.dark", verts=24),
             _torus(mats, p + Vector((0, 0, 0.13)), 0.36, 0.07, "M_Colony.dark", segs=(24, 8))]
    moving = []
    for sx in (-1, 1):
        moving.append(_cyl(mats, p + Vector((sx * 0.15, -0.62, 0.5)), 0.055, 0.62, "M_Gunmetal", verts=12,
                           rot=(math.radians(90), 0, 0)))
        moving.append(_torus(mats, p + Vector((sx * 0.15, -0.91, 0.5)), 0.06, 0.022, "M_Gunmetal",
                             rot=(math.radians(90), 0, 0), segs=(12, 6)))
    return _make_turret(name, mats, pivot, fixed, moving)


def beetle_turret(name, mats, pivot):
    """Gunmetal four-lobed cannon (turret sprite: cross ~1.1 cells across, barrel tip ~1.15 from the
    yaw axis) on a short pedestal."""
    p = Vector(pivot)
    fixed = [_cyl(mats, p + Vector((0, 0, 0.06)), 0.3, 0.12, "M_Iron", verts=20),
             _cyl(mats, p + Vector((0, 0, 0.17)), 0.17, 0.14, "M_GunGrey", verts=16),
             _sphere(mats, p + Vector((0, 0, 0.38)), 0.27, "M_GunGrey", segments=20, rings=12)]
    for dx, dy in ((0.3, 0), (-0.3, 0), (0, 0.3), (0, -0.3)):
        fixed.append(_sphere(mats, p + Vector((dx, dy, 0.33)), 0.2, "M_GunGrey", scale=(1.15, 1.15, 0.85), segments=16,
                             rings=10))
    moving = [_cyl(mats, p + Vector((0, -0.66, 0.42)), 0.085, 0.98, "M_GunGrey", verts=14, rot=(math.radians(90), 0, 0)),
              _torus(mats, p + Vector((0, -1.14, 0.42)), 0.095, 0.03, "M_GunGrey", rot=(math.radians(90), 0, 0), segs=(14, 6)),
              _cyl(mats, p + Vector((0, 0.12, 0.42)), 0.14, 0.36, "M_Iron", verts=14, rot=(math.radians(90), 0, 0))]
    return _make_turret(name, mats, pivot, fixed, moving)


def spider_turret(name, mats, pivot):
    """Octagonal team-coloured drum (turret sprite: ~30 px = 1.25 cells across, flat sides facing the
    axes) with a bevelled top, a dark teardrop hole and a short thin barrel at its foot."""
    p = Vector(pivot)
    r8 = (0, 0, math.radians(22.5))
    fixed = [_cyl(mats, p + Vector((0, 0, 0.045)), 0.52, 0.09, "M_Colony.dark", verts=8, rot=r8),
             _cyl(mats, p + Vector((0, 0, 0.27)), 0.64, 0.36, "M_Colony", verts=8, rot=r8),
             _cone(mats, p + Vector((0, 0, 0.51)), 0.64, 0.44, 0.12, "M_Colony", rot=r8, verts=8, smooth=False),
             _cyl(mats, p + Vector((0, 0.09, 0.575)), 0.15, 0.03, "M_Black", verts=12, scale=(1.0, 1.45, 1.0)),
             _cone(mats, p + Vector((0, 0.36, 0.575)), 0.08, 0.0, 0.03, "M_Black", verts=8)]
    moving = [_cyl(mats, p + Vector((0, -0.69, 0.14)), 0.042, 0.42, "M_Gunmetal", verts=10, rot=(math.radians(90), 0, 0)),
              _cyl(mats, p + Vector((0, -0.56, 0.14)), 0.075, 0.14, "M_Gunmetal", verts=10, rot=(math.radians(90), 0, 0))]
    return _make_turret(name, mats, pivot, fixed, moving)


def scorpion_turret(name, mats, pivot):
    """Pale disc (turret sprite: ~40 px = 1.6 cells across) with a dark hollow, carrying two brown
    spear rails 0.64 apart, spears loaded with bone arrowheads (the sprite's white heads)."""
    p = Vector(pivot)
    fixed = [_cyl(mats, p + Vector((0, 0, 0.11)), 0.8, 0.22, "M_Bone", verts=32),
             _torus(mats, p + Vector((0, 0, 0.22)), 0.74, 0.05, "M_Bone", segs=(32, 6)),
             _cyl(mats, p + Vector((0, 0, 0.23)), 0.6, 0.04, "M_Black", verts=28)]
    moving = []
    for sx in (-1, 1):
        x = sx * 0.32
        moving.append(_box(mats, (p.x + x, p.y - 0.15, p.z + 0.36), (0.22, 1.15, 0.16), "M_Wood", bevel=0.03))
        for y in (0.3, -0.5):
            moving.append(_box(mats, (p.x + x, p.y + y, p.z + 0.45), (0.26, 0.13, 0.08), "M_Bone", bevel=0.0))
        moving.append(_cyl(mats, p + Vector((x, -0.3, 0.48)), 0.035, 1.2, "M_Gunmetal", verts=8,
                           rot=(math.radians(90), 0, 0)))
        moving.append(_cone(mats, p + Vector((x, -1.04, 0.48)), 0.11, 0.0, 0.28, "M_Bone",
                            rot=(math.radians(90), 0, 0), verts=8))
    return _make_turret(name, mats, pivot, fixed, moving)


def wasp_turret(name, mats, pivot):
    """Dark disc base with a thick ribbed gatling gun (wasp turret sprite)."""
    p = Vector(pivot)
    fixed = [_cyl(mats, p + Vector((0, 0, 0.11)), 0.42, 0.22, "M_Iron", verts=24),
             _torus(mats, p + Vector((0, 0, 0.22)), 0.4, 0.04, "M_Accent", segs=(24, 8)),
             _cyl(mats, p + Vector((0, 0, 0.33)), 0.16, 0.25, "M_Iron", verts=16)]
    # gun ~1.15 from the yaw axis to the muzzle (turret sprite: 28 px)
    moving = [_cyl(mats, p + Vector((0, -0.36, 0.5)), 0.16, 1.05, "M_Gun", verts=16, rot=(math.radians(90), 0, 0)),
              _box(mats, (p.x, p.y + 0.22, p.z + 0.5), (0.34, 0.3, 0.3), "M_Iron", bevel=0.04)]
    for y in (-0.12, -0.38, -0.64):
        moving.append(_torus(mats, p + Vector((0, y, 0.5)), 0.16, 0.035, "M_Gun", rot=(math.radians(90), 0, 0), segs=(16, 6)))
    for i in range(5):
        a = i / 5 * 2 * math.pi
        moving.append(_cyl(mats, p + Vector((0.09 * math.cos(a), -1.0, 0.5 + 0.09 * math.sin(a))), 0.035, 0.28,
                           "M_Gunmetal", verts=8, rot=(math.radians(90), 0, 0)))
    return _make_turret(name, mats, pivot, fixed, moving)


# ---------------------------------------------------------------------------------------------
# finishing: clips, bake/export/previews (salib), sprite-view comparison
# ---------------------------------------------------------------------------------------------
def _attach(t, body):
    t.parent = body
    t.matrix_parent_inverse = body.matrix_world.inverted()


def sprite_view_render(path, size=432, samples=48, turrets=True, transparent=False):
    """Render the scene like the original sprite: orthographic, 6 cells wide, from the south at
    SPRITE_ELEVATION degrees, lit from the north-west.  turrets=False hides the Turret_* objects (the
    body sprite has none); transparent=True leaves out the ground (alpha = model silhouette)."""
    sc = bpy.context.scene
    hidden = [o for o in sc.objects if not turrets and o.name.startswith("Turret_")]
    for o in hidden:
        o.hide_render = True
    cam_data = bpy.data.cameras.new("SpriteCam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 6.0
    cam = bpy.data.objects.new("SpriteCam", cam_data)
    salib.link(cam)
    el = math.radians(SPRITE_ELEVATION)
    cam.location = (0.0, -math.cos(el) * 40.0, math.sin(el) * 40.0)
    cam.rotation_euler = (Vector((0, 0, 0)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    sun_data = bpy.data.lights.new("SpriteSun", "SUN")
    sun_data.energy = 3.0
    sun_data.angle = math.radians(6)
    sun = bpy.data.objects.new("SpriteSun", sun_data)
    salib.link(sun)
    sun.rotation_euler = Vector((0.45, -0.55, -1.0)).to_track_quat("-Z", "Y").to_euler()
    fill_data = bpy.data.lights.new("SpriteFill", "SUN")
    fill_data.energy = 0.7
    fill = bpy.data.objects.new("SpriteFill", fill_data)
    salib.link(fill)
    fill.rotation_euler = Vector((-0.5, 0.3, -1.0)).to_track_quat("-Z", "Y").to_euler()
    bpy.ops.mesh.primitive_plane_add(size=14, location=(0, 0, -0.002))
    ground = bpy.context.object
    ground.name = "SpriteGround"
    ground.data.materials.append(salib.material("M_SpriteGround", (0.19, 0.19, 0.2), roughness=1.0, kind="glossy"))
    old = (sc.camera, sc.render.resolution_x, sc.render.resolution_y, sc.render.image_settings.file_format,
           sc.render.filepath)
    sc.camera = cam
    sc.render.engine = "CYCLES"
    salib.use_cycles_device(sc)
    sc.cycles.samples = samples
    sc.cycles.use_denoising = False
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    if sc.world and sc.world.node_tree:
        bg = sc.world.node_tree.nodes.get("Background")
        if bg:
            bg.inputs[1].default_value = 0.35
    sc.render.resolution_x = sc.render.resolution_y = size
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = transparent
    ground.hide_render = transparent
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA" if transparent else "RGB"
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    for o in (cam, sun, fill, ground):
        bpy.data.objects.remove(o, do_unlink=True)
    for o in hidden:
        o.hide_render = False
    sc.render.film_transparent = False
    sc.render.image_settings.color_mode = "RGB"
    sc.camera, sc.render.resolution_x, sc.render.resolution_y, sc.render.image_settings.file_format, sc.render.filepath = old
    salib.log("sprite view", path)
    return path


def sprite_comparison(name, render_png, out_jpg):
    """Original sprite (Y) | model render | neutral sprite (X), with the cell grid."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None
    if not REF_DIR:
        return None
    sheets = []
    for team in ("Y", "X"):
        p = os.path.join(REF_DIR, name, f"colony_body_{team}.png")
        if not os.path.exists(p):
            return None
        sheets.append(Image.open(p).convert("RGB").crop((0, 0, 432, 432)))
    ren = Image.open(render_png).convert("RGB").resize((432, 432))
    tiles = [("original sprite (Y)", sheets[0]), ("new model, same view", ren), ("original neutral (X)", sheets[1])]
    sheet = Image.new("RGB", (432 * 3 + 20, 432 + 24), (30, 30, 30))
    d = ImageDraw.Draw(sheet)
    for i, (label, im) in enumerate(tiles):
        im = im.copy()
        g = ImageDraw.Draw(im)
        for k in range(7):
            x = k * 72
            c = (255, 70, 70) if k == 3 else (120, 120, 120)
            g.line([(x, 0), (x, 431)], fill=c)
            g.line([(0, x), (431, x)], fill=c)
        sheet.paste(im, (i * 442, 22))
        d.text((i * 442 + 4, 4), f"{name}: {label}", fill=(255, 255, 0))
    sheet.save(out_jpg, quality=90)
    salib.log("comparison", out_jpg)
    return out_jpg


def _clear_textures(name):
    d = os.path.join(salib.TEXTURE_DIR, name)
    if os.path.isdir(d):
        shutil.rmtree(d)


def _finish_colony(name, body, turrets, barrels_all, radius, center_z, quick=False):
    objs = [body] + turrets + [b for bs in barrels_all for b in bs]
    tris = {o.name: tri_count(o) for o in objs}
    total = sum(tris.values())
    salib.log(name, "triangles", total, tris)
    assert total <= TRI_BUDGET, f"{name}: {total} triangles over budget {TRI_BUDGET}"
    for t in turrets:
        assert t.rotation_euler[:] == (0.0, 0.0, 0.0) and tuple(round(s, 4) for s in t.scale) == (1, 1, 1)
    for o in objs:
        for v in o.data.vertices:
            w = o.matrix_world @ v.co
            assert abs(w.x) <= 3.05 and abs(w.y) <= 3.05, f"{name}: {o.name} leaves the 6x6 footprint at {w}"
    if quick:
        if QA_DIR:
            os.makedirs(QA_DIR, exist_ok=True)
            # body only on a transparent film: the silhouette overlay against the body sprite
            sprite_view_render(os.path.join(QA_DIR, f"{name}_spriteview_body.png"), turrets=False, transparent=True)
            png = sprite_view_render(os.path.join(QA_DIR, f"{name}_spriteview_quick.png"))
            sprite_comparison(name, png, os.path.join(QA_DIR, f"{name}_compare_quick.jpg"))
        return None
    idle_clip(body)
    for t, bs in zip(turrets, barrels_all):
        turret_fire_clip(t, bs)
    _clear_textures(name)
    path, s = salib.finalize_asset(name, objs, preview_radius=radius, preview_center=(0, 0, center_z),
                                   views=("front", "back", "left", "right", "threequarter", "top"))
    for i in range(len(turrets)):
        assert f"Turret_{i + 1}" in s["node_names"], s["node_names"]
    assert "M_Colony" in s["materials"], s["materials"]
    clips = sorted(a["name"] for a in s["animations"])
    assert clips == ["idle", "turret_fire"], clips
    if QA_DIR:
        os.makedirs(QA_DIR, exist_ok=True)
        sprite_view_render(os.path.join(QA_DIR, f"{name}_spriteview_body.png"), turrets=False, transparent=True)
        png = sprite_view_render(os.path.join(QA_DIR, f"{name}_spriteview.png"))
        sprite_comparison(name, png, os.path.join(QA_DIR, f"{name}_compare.jpg"))
        with open(os.path.join(QA_DIR, f"{name}_build.txt"), "w") as f:
            f.write(f"{name}\ntriangles {total} {tris}\nnodes {s['node_names']}\nmaterials {s['materials']}\n"
                    f"clips {s['animations']}\nturrets {[tuple(round(c, 3) for c in t.matrix_world.translation) for t in turrets]}\n")
    return path


# ---------------------------------------------------------------------------------------------
# ANT: dark cobbled earth mound coiled by team-coloured rope bands, two tall flat-topped towers
# (north-east of centre and south of centre), a curved flat-topped wall in the south-east.
# ---------------------------------------------------------------------------------------------
# Fourth iteration (second shift), measured off the sprite with the 60-degree ortho projection
# u = X, v = -(0.866 Y + 0.5 Z) and checked against the green ant colony of the original loading
# screen 0: a steep rock cone (rope rings at z 1.0 / 1.35 / 1.7 sit on it: ring centres and radii
# give the axis and the slope), buttress bands down its flanks, two towers as high as the cone.
ANT_AXIS = (-0.33, 0.59)
ANT_PROFILE = [(2.12, 0.0), (2.0, 0.18), (1.66, 0.55), (1.27, 1.0), (0.95, 1.35), (0.66, 1.7), (0.42, 2.02),
               (0.22, 2.3), (0.0, 2.45)]
ANT_SCALE = (1.0, 0.95)
ANT_TOWER_H = 2.5
ANT_TOWER_R = 0.48
ANT_TOWERS = ((0.5, 1.33), (-0.12, -1.29))  # Turret_1 north-east (foot hidden in the cone), Turret_2 south


def ant_r(z):
    return lathe_r(ANT_PROFILE, z)


def ant_point(angle_deg, r, z):
    a = math.radians(angle_deg)
    return (ANT_AXIS[0] + r * ANT_SCALE[0] * math.cos(a), ANT_AXIS[1] + r * ANT_SCALE[1] * math.sin(a), z)


def ant_band(mats, name, a_top, z_top, a_foot, radius=0.15, n=8):
    """Thick team-coloured band lying on the cone: from (a_top, z_top) it runs down the flank (turning
    to a_foot) and ends on the ground at the foot of the cone."""
    pts = []
    for k in range(n + 1):
        f = k / n
        a = a_top + (a_foot - a_top) * f
        z = z_top * (1.0 - f)
        r = ant_r(z) + radius * 0.4
        if k == n:
            z, r = radius * 0.7, ant_r(0.0) + 0.04
        pts.append(ant_point(a, r, z))
    return tube(mats, name, pts, radius, "M_Colony", radii=[0.75] + [1.0] * n, bevel_res=3, res_u=5)


def build_ant_colony(quick=False):
    name = "colony_ant"
    salib.reset_scene(name)
    mats = colony_materials("Y")
    parts = [lathe_mound("Mound", mats, "M_Granite", ANT_AXIS, ANT_PROFILE, scale=ANT_SCALE, segments=64, steps=3,
                         noise=0.22, noise_scale=0.38, seed=4)]
    rnd = random.Random(8)
    # lumps of rock on the flanks and loose rocks heaped round the foot (the sprite's cone is rough)
    ring_z = (1.0, 1.35, 1.7)
    k = 0
    while k < 34:
        z = rnd.uniform(0.15, 2.15)
        if min(abs(z - rz) for rz in ring_z) < 0.13:
            continue
        a = rnd.uniform(0, 360)
        x, y, _ = ant_point(a, ant_r(z) - 0.05, z)
        parts.append(_sphere(mats, (x, y, z), rnd.uniform(0.13, 0.24), "M_Granite", ico=1, jitter=0.025, seed=k,
                             scale=(rnd.uniform(1.0, 1.5), rnd.uniform(1.0, 1.5), rnd.uniform(0.7, 1.0)),
                             rot=(0, 0, rnd.uniform(0, 3))))
        k += 1
    for i in range(18):
        a = rnd.uniform(0, 360)
        x, y, _ = ant_point(a, ant_r(0.0) - rnd.uniform(0.2, 0.45), 0.0)
        parts.append(_sphere(mats, (x, y, 0.05), rnd.uniform(0.18, 0.28), "M_Granite", ico=1, jitter=0.03, seed=40 + i,
                             scale=(rnd.uniform(0.9, 1.4), rnd.uniform(0.9, 1.4), rnd.uniform(0.6, 0.9)),
                             rot=(0, 0, rnd.uniform(0, 3))))
    # thin rope rings tied round the cone
    for k, z in enumerate(ring_z):
        r = ant_r(z) + 0.02
        ring = [ant_point(j * 360 / 36, r, z) for j in range(36)]
        ring.append(ring[0])
        parts.append(tube(mats, f"Ring{k}", ring, 0.045, "M_Colony", bevel_res=1, res_u=3))
    # thick bands: one spiralling from the north over the north-west shoulder down to the west-south-west
    # foot, a south-west buttress, an east-north-east buttress
    for i, (a_top, z_top, a_foot) in enumerate(((95, 0.95, 205), (236, 1.15, 249), (45, 1.25, 8))):
        parts.append(ant_band(mats, f"Band{i}", a_top, z_top, a_foot))
    # towers: plain team-coloured cylinders with a rim; the south one on a fluted skirt
    for i, (x, y) in enumerate(ANT_TOWERS):
        parts.append(_cyl(mats, (x, y, ANT_TOWER_H / 2), ANT_TOWER_R, ANT_TOWER_H, "M_Colony", verts=32))
        parts.append(_torus(mats, (x, y, ANT_TOWER_H - 0.045), ANT_TOWER_R - 0.03, 0.05, "M_Colony", segs=(32, 6)))
        if i == 1:
            parts.append(fluted_cyl(mats, (x, y, 0.0), ANT_TOWER_R + 0.09, 0.72, "M_Colony", flutes=18, groove=0.07))
            parts.append(_torus(mats, (x, y, 0.74), ANT_TOWER_R + 0.03, 0.05, "M_Colony", segs=(32, 6)))
    # the curved ramp-wall round the south-east foot: a flat top about 1 high with a sloping outer face,
    # from the south tower round to the east, where it curls down

    def wall_h(t):
        return 1.0 - 0.08 * t - (0.6 * ((t - 0.72) / 0.28) ** 1.5 if t > 0.72 else 0.0)

    parts.append(curved_wall(mats, ANT_AXIS, -78, -20, lambda t: 2.12, lambda t: 2.48, wall_h, "M_Colony", steps=36,
                             bevel=0.06, name="Wall", batter=lambda t: 0.1 + 0.45 * max(0.0, 1 - t / 0.45) ** 2))
    body = join_into(parts, "ColonyBody")
    turrets, barrels_all = [], []
    for i, (x, y) in enumerate(ANT_TOWERS):
        t, bs = ant_turret(f"Turret_{i + 1}", mats, (x, y, ANT_TOWER_H))
        _attach(t, body)
        turrets.append(t)
        barrels_all.append(bs)
    return _finish_colony(name, body, turrets, barrels_all, 9.0, 1.2, quick)


# ---------------------------------------------------------------------------------------------
# BEETLE (fourth iteration, second shift): the blue beetle colony of the original loading screen 2 -
# a dome of long curved shell slats separated by dark slits, flaring out at the foot, a flattened
# cap on top with incised rings and arcs, long thin spikes standing out of the slats, and the
# gunmetal cannon on the cap.  The cap's outline in the sprite (centre v -0.6, radius 0.9) and
# OpenSA's turret offset (screen 0, -0.86) both give a cap top ~1.72 above the centre.
# ---------------------------------------------------------------------------------------------
BEETLE_CAP = (0.0, 0.0, 1.17, 0.9, 0.55)  # x, y, z centre, radius, half height
BEETLE_PROFILE = [(0.9, 1.13), (1.3, 1.08), (1.65, 0.95), (1.95, 0.75), (2.13, 0.5), (2.23, 0.25), (2.27, 0.04)]
BEETLE_SLATS = 9
BEETLE_FLARE = (0.62, 0.3, 0.45, 0.2, 0.5, 0.25, 0.4, 0.15, 0.35)  # from due south, anticlockwise


def slat(mats, name, a_mid, half_width, profile, bulge=0.12, flare=0.25, thick=0.09, mat="M_Colony", seed=0):
    """One curved shell slat of the dome: a strip over the profile (r, z) between angles
    a_mid +- half_width (radians, narrowing towards the top), convex across, its foot curling out."""
    prof = _catmull(profile, 3)
    n_t, n_s = len(prof), 7
    verts, faces = [], []
    for side in (0, 1):  # outer surface, then inner surface
        for i, (r, z) in enumerate(prof):
            t = i / (n_t - 1)
            hw = half_width * (0.55 + 0.45 * t)
            curl = flare * max(0.0, (t - 0.7) / 0.3) ** 2
            for j in range(n_s):
                sv = -1.0 + 2.0 * j / (n_s - 1)
                a = a_mid + sv * hw
                out = bulge * (1.0 - sv * sv) * math.sin(math.pi * min(1.0, t * 1.15)) - (thick if side else 0.0)
                rr = r + out + curl
                zz = z + curl * 0.35 - (thick * 0.4 if side else 0.0)
                verts.append((rr * math.cos(a), rr * math.sin(a), max(0.0, zz)))
    off = n_t * n_s
    for i in range(n_t - 1):
        for j in range(n_s - 1):
            a0, a1, b0, b1 = i * n_s + j, i * n_s + j + 1, (i + 1) * n_s + j, (i + 1) * n_s + j + 1
            faces.append((a0, a1, b1, b0))
            faces.append((off + a0, off + b0, off + b1, off + a1))
    for i in range(n_t - 1):  # side walls
        for j in (0, n_s - 1):
            a0, b0 = i * n_s + j, (i + 1) * n_s + j
            faces.append((a0, b0, off + b0, off + a0) if j == 0 else (a0, off + a0, off + b0, b0))
    for j in range(n_s - 1):  # top and bottom ends
        faces.append((j, off + j, off + j + 1, j + 1))
        e = (n_t - 1) * n_s
        faces.append((e + j, e + j + 1, off + e + j + 1, off + e + j))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    o = bpy.data.objects.new(name, me)
    salib.link(o)
    salib.select_only([o])
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    o.data.materials.append(mats[mat])
    return _smooth(o)


def build_beetle_colony(quick=False):
    name = "colony_beetle"
    salib.reset_scene(name)
    mats = colony_materials("Y")
    cx, cy, cz, cr, ch = BEETLE_CAP
    # dark rock core: shows grey-brown through the slits
    parts = [lathe_mound("Core", mats, "M_RockDark", (cx, cy), [(2.1, 0.0), (1.95, 0.6), (1.5, 1.0), (0.9, 1.12), (0.0, 1.2)],
                         segments=48, steps=2, noise=0.08, noise_scale=0.5, seed=3)]
    rnd = random.Random(3)
    step = 2 * math.pi / BEETLE_SLATS
    for i in range(BEETLE_SLATS):  # broad petals, the southern one reaching far out (sprite)
        a = -math.pi / 2 + i * step + rnd.uniform(-0.05, 0.05)
        parts.append(slat(mats, f"Slat{i}", a, step * 0.5 * rnd.uniform(0.9, 0.96), BEETLE_PROFILE,
                          bulge=rnd.uniform(0.17, 0.25), flare=BEETLE_FLARE[i],
                          mat="M_Colony.plate" if i % 2 else "M_Colony", seed=i))
        # one long thin spike per slat (some get two), out of the slat's upper half
        for k, (fr, ln) in enumerate(((rnd.uniform(0.35, 0.55), rnd.uniform(0.85, 1.15)),
                                      (rnd.uniform(0.6, 0.75), rnd.uniform(0.6, 0.9)))):
            if k == 1 and rnd.random() < 0.55:
                continue
            idx = fr * (len(BEETLE_PROFILE) - 1)
            r0, z0 = BEETLE_PROFILE[int(idx)]
            r1, z1 = BEETLE_PROFILE[min(len(BEETLE_PROFILE) - 1, int(idx) + 1)]
            f = idx - int(idx)
            r, z = r0 + (r1 - r0) * f + 0.08, z0 + (z1 - z0) * f + 0.02
            aa = a + rnd.uniform(-0.12, 0.12)
            base = (r * math.cos(aa), r * math.sin(aa), z)
            d = Vector((math.cos(aa) * 0.85, math.sin(aa) * 0.85, 0.35 + 0.4 * (1 - fr)))
            parts.append(_spike(mats, base, d, ln, r1=0.06, verts=8))
    # the cap: a flattened dome with a rim, incised rings and arcs
    parts.append(_sphere(mats, (cx, cy, cz), cr, "M_Colony", scale=(1, 1, ch / cr), segments=40, rings=20))
    parts.append(_torus(mats, (cx, cy, cz + 0.02), cr * 0.98, 0.07, "M_Colony", segs=(40, 8)))

    def on_cap(x, y, lift=0.012):
        r2 = (x / cr) ** 2 + (y / cr) ** 2
        return (cx + x, cy + y, cz + ch * math.sqrt(max(0.0, 1 - r2)) + lift)

    # incised pattern of the sprite's medallion: inner ring, side arcs, a meridian and a short west bar
    ring = [on_cap(0.45 * math.cos(k * 2 * math.pi / 32), 0.45 * math.sin(k * 2 * math.pi / 32)) for k in range(32)]
    parts.append(tube(mats, "CapRing", ring + [ring[0]], 0.028, "M_Colony.dark", bevel_res=1, res_u=2))
    for k, (a0, a1, rr) in enumerate(((118, 236, 0.74), (-52, 52, 0.74))):
        arc = [on_cap(rr * math.cos(math.radians(a0 + (a1 - a0) * j / 12)), rr * math.sin(math.radians(a0 + (a1 - a0) * j / 12)))
               for j in range(13)]
        parts.append(tube(mats, f"CapArc{k}", arc, 0.026, "M_Colony.dark", bevel_res=1, res_u=2))
    for k, (x0, y0, x1, y1) in enumerate(((0.0, 0.45, 0.0, 0.86), (0.0, -0.45, 0.0, -0.86), (-0.74, -0.05, -0.45, -0.05))):
        line = [on_cap(x0 + (x1 - x0) * j / 6, y0 + (y1 - y0) * j / 6) for j in range(7)]
        parts.append(tube(mats, f"CapLine{k}", line, 0.026, "M_Colony.dark", bevel_res=1, res_u=2))
    body = join_into(parts, "ColonyBody")
    t, bs = beetle_turret("Turret_1", mats, (cx, cy, cz + ch))
    _attach(t, body)
    return _finish_colony(name, body, [t], [bs], 9.5, 0.9, quick)


# ---------------------------------------------------------------------------------------------
# SPIDER (fourth iteration, second shift): a giant upturned spider over a chrome bell.  From a hub
# about 2.2 high, 13 knobbly team-coloured legs slope out to knees (r ~1.9, z ~1.8) and drop steeply
# to the ground (r ~2.8) - that is why, seen from the south at 60 deg, the sprite's north legs end
# short at their knees and the south legs run long down the picture (cf. the red spider colony of
# the original loading screen 1: an open cage of knobbly legs round a chrome core).  Two pale
# team-tinted towers stand clear of the legs and carry octagonal sniper drums.
# ---------------------------------------------------------------------------------------------
SPIDER_AXIS = (0.05, 0.1)
SPIDER_HUB_Z = 2.2
SPIDER_BELL = [(2.35, 0.0), (2.25, 0.45), (1.95, 1.0), (1.45, 1.5), (0.9, 1.85), (0.5, 2.05), (0.0, 2.12)]
# (angle, foot radius): the sprite's legs leave a gap in the south-east (the east tower and the dark
# interior show there); the north-west ones are short and mostly hidden behind the north-west tower
SPIDER_LEGS = ((88, 2.8), (72, 2.6), (58, 2.8), (40, 2.62), (24, 2.78), (6, 2.85), (-16, 2.3), (-92, 2.82),
               (-125, 2.78), (-151, 2.68), (-174, 2.75), (164, 2.5), (140, 2.2), (114, 2.3))
SPIDER_TOWERS = (((-0.86, 0.68), 2.75), ((0.95, -1.06), 2.75))  # top-face centres fitted to the sprite


def spider_leg(mats, name, angle, knee_r=1.92, knee_z=1.78, foot_r=2.8, radius=0.19):
    a = math.radians(angle)
    d = Vector((math.cos(a), math.sin(a), 0.0))
    o = Vector((SPIDER_AXIS[0], SPIDER_AXIS[1], 0.0))
    span = foot_r - knee_r
    prof = [(0.42, SPIDER_HUB_Z - 0.05, 0.92), (0.9, SPIDER_HUB_Z + 0.22, 1.0), (1.45, SPIDER_HUB_Z + 0.12, 1.0),
            (knee_r, knee_z, 1.0), (knee_r + span * 0.45, knee_z * 0.6, 0.94), (foot_r - span * 0.2, knee_z * 0.24, 0.86),
            (foot_r, 0.06, 0.78)]
    pts = [tuple(o + d * r + Vector((0, 0, z))) for r, z, _ in prof]
    leg = tube(mats, name, pts, radius, "M_Colony.knob", radii=[k for _, _, k in prof], bevel_res=4, res_u=6)
    knee = _sphere(mats, pts[3], radius * 1.22, "M_Colony.knob", segments=14, rings=9)  # the fat round knee
    return join_into([leg, knee], name)


def build_spider_colony(quick=False):
    name = "colony_spider"
    salib.reset_scene(name)
    mats = colony_materials("Y")
    ax, ay = SPIDER_AXIS
    # the chrome body is longer north-east to south-west (the sprite is cut diagonally at the SE and NW)
    parts = [lathe_mound("Bell", mats, "M_Chrome", SPIDER_AXIS, SPIDER_BELL, scale=(1.0, 0.78), rot=45.0, segments=64,
                         steps=3, noise=0.05, noise_scale=0.8, seed=6)]
    # hub: thick ring, dark hole with a pale bar, a crown of knobs (the leg roots)
    hz = SPIDER_HUB_Z
    parts.append(_cyl(mats, (ax, ay, hz - 0.2), 0.5, 0.4, "M_Chrome", verts=24))
    parts.append(_torus(mats, (ax, ay, hz + 0.02), 0.46, 0.15, "M_Colony", segs=(32, 10)))
    parts.append(_cyl(mats, (ax, ay, hz - 0.02), 0.33, 0.12, "M_Black", verts=20))
    parts.append(_box(mats, (ax, ay, hz + 0.05), (0.66, 0.09, 0.07), "M_Chrome", rot=(0, 0, math.radians(-45)), bevel=0.02))
    rnd = random.Random(12)
    for i, (a, foot) in enumerate(SPIDER_LEGS):
        ar = math.radians(a)
        parts.append(_sphere(mats, (ax + 0.6 * math.cos(ar), ay + 0.6 * math.sin(ar), hz + 0.08), 0.21, "M_Colony.knob",
                             segments=14, rings=9))
        knee = min(rnd.uniform(1.85, 2.0), foot - 0.55)
        parts.append(spider_leg(mats, f"Leg{i}", a + rnd.uniform(-2, 2), knee_r=knee, knee_z=rnd.uniform(1.7, 1.86),
                                foot_r=foot))
    # pale team-tinted towers
    for (x, y), top in SPIDER_TOWERS:
        parts.append(_cyl(mats, (x, y, top / 2), 0.42, top, "M_Colony.tower", verts=32))
        parts.append(_torus(mats, (x, y, top - 0.04), 0.39, 0.045, "M_Colony.tower", segs=(32, 6)))
    body = join_into(parts, "ColonyBody")
    turrets, barrels_all = [], []
    for i, ((x, y), top) in enumerate(SPIDER_TOWERS):
        t, bs = spider_turret(f"Turret_{i + 1}", mats, (x, y, top))
        _attach(t, body)
        turrets.append(t)
        barrels_all.append(bs)
    return _finish_colony(name, body, turrets, barrels_all, 9.5, 1.3, quick)


# ---------------------------------------------------------------------------------------------
# SCORPION (fourth iteration, second shift): an armoured carapace of team-coloured plates (dark gaps,
# rivets), with
#  * the turret tower in the north: a round tower (r 0.7, top 2.15) whose top is the sprite's
#    honeycomb disc ringed by spikes - OpenSA puts the turret exactly there (screen 0.43,-2.13) - and
#    whose dark front band carries the four lit window slits; a big smooth horn on its north-east rim;
#  * a bulbous closed claw in the west, a segmented limb along the north-west edge and a segmented
#    limb with a spike tip in the east;
#  * an open horseshoe claw of ribbed segments in the south-east whose two tips touch the ground
#    (south and south-east), enclosing open ground.
# ---------------------------------------------------------------------------------------------
SCORP_TOWER = (0.42, 1.2)
SCORP_TOWER_R = 0.7
SCORP_TOWER_H = 2.15
# armour pieces (x, y, z0, rx, ry, rz, kind) mapped onto the sprite's plate regions; z0 > 0 lifts a
# plate into a shelf over a dark hollow.  kind: "claw" smooth bulb, "plate" faceted shell, "rib" grooved
SCORP_HULL = [(-1.7, 0.3, 0.0, 0.88, 0.9, 1.15, "claw"),     # west closed claw
              (0.0, 0.05, 0.55, 0.78, 0.66, 0.8, "plate"),   # the big plate under the tower (a shelf)
              (1.3, 0.25, 0.0, 0.8, 0.74, 1.05, "rib"),      # east grooved plates
              (1.35, 1.05, 0.0, 0.7, 0.62, 1.0, "plate"),    # north-east plate
              (-0.62, 2.02, 0.0, 0.5, 0.42, 0.9, "plate"),   # north-west plate by the tower
              (-0.05, -1.05, 0.0, 0.55, 0.62, 0.85, "rib"),  # the claw's palm (rivets)
              (-1.0, -1.32, 0.0, 0.7, 0.56, 0.75, "plate"),  # south-west plates
              (0.45, 0.85, 0.0, 0.88, 0.56, 1.0, "plate"),   # mass behind (round the tower foot)
              (-1.15, 1.05, 0.0, 0.62, 0.5, 0.55, "plate"),  # low plate under the north-west limb
              (-0.85, 0.35, 0.0, 0.6, 0.6, 0.95, "plate")]   # joins the west claw to the centre


def scorp_z(x, y):
    return hull_z([(cx, cy, z0, rx, ry, rz) for cx, cy, z0, rx, ry, rz, _ in SCORP_HULL], x, y)


def segmented_band(mats, name, pts, width, thick, mat, seg_len=0.26, gap=0.035, taper=0.0, bevel=0.05):
    """A flat band of bevelled box segments along the polyline `pts` (ribbed, like a scorpion tail)."""
    pts = [Vector(p) for p in pts]
    seg = [(pts[i + 1] - pts[i]).length for i in range(len(pts) - 1)]
    total = sum(seg)
    n = max(2, int(total / seg_len))
    out = []

    def at(sv):
        i = 0
        while i < len(seg) - 1 and sv > seg[i]:
            sv -= seg[i]
            i += 1
        t = sv / seg[i] if seg[i] > 0 else 0.0
        return pts[i].lerp(pts[i + 1], min(1.0, t))

    for k in range(n):
        p0, p1 = at(total * k / n), at(total * (k + 1) / n)
        c = (p0 + p1) / 2
        d = (p1 - p0).normalized()
        f = 1.0 - taper * (k / max(1, n - 1))
        side = d.cross(Vector((0, 0, 1)))
        if side.length < 1e-6:
            side = Vector((1, 0, 0))
        side.normalize()
        up = side.cross(d).normalized()
        if up.z < 0:
            up = -up
            side = -side
        m = Matrix((side, d, up)).transposed()
        bpy.ops.mesh.primitive_cube_add(size=1.0)
        o = bpy.context.object
        o.data.transform(Matrix.Diagonal((width * f, (p1 - p0).length - gap, thick * f, 1.0)))
        o.data.transform(m.to_4x4())
        o.data.transform(Matrix.Translation(c))
        o.data.materials.append(mats[mat])
        salib.bevel_object(o, min(bevel, thick * 0.25), segments=2)
        for poly in o.data.polygons:
            poly.use_smooth = False
        out.append(o)
    return join_into(out, name)


def build_scorpion_colony(quick=False):
    name = "colony_scorpion"
    salib.reset_scene(name)
    mats = colony_materials("Y")
    parts = []
    # dark hollows (black) that show between and under the plates
    for cx, cy, cz, rx, ry, rz in ((-1.5, 1.42, 0.0, 0.62, 0.4, 0.62), (-0.45, 1.3, 0.2, 0.32, 0.3, 0.95),
                                   (-0.35, -0.3, 0.0, 0.55, 0.45, 0.66)):
        parts.append(_sphere(mats, (cx, cy, cz), 1.0, "M_Hollow", scale=(rx, ry, rz), segments=16, rings=8))
    # armour: the closed west claw is a smooth bulb, the plates are shells with a few creases
    for i, (cx, cy, z0, rx, ry, rz, kind) in enumerate(SCORP_HULL):
        if kind == "claw":
            parts.append(_sphere(mats, (cx, cy, z0), 1.0, "M_Colony", scale=(rx, ry, rz), segments=28, rings=16))
            # scalloped armour shells over the closed claw (the sprite's west mass is plated, not a ball)
            for k, (dx, dy, sx, sy, sz, tilt) in enumerate(((-0.25, 0.3, 0.55, 0.45, 0.2, 0.0), (0.3, 0.25, 0.5, 0.42, 0.2, 0.3),
                                                           (-0.35, -0.35, 0.5, 0.42, 0.2, -0.4), (0.25, -0.38, 0.45, 0.4, 0.2, 0.5))):
                x, y = cx + dx, cy + dy
                z = z0 + rz * math.sqrt(max(0.0, 1 - (dx / rx) ** 2 - (dy / ry) ** 2)) - 0.06
                parts.append(_sphere(mats, (x, y, z), 1.0, "M_Colony.rib", scale=(sx, sy, sz), rot=(0.25 * dy / ry, -0.25 * dx / rx, tilt),
                                     segments=20, rings=10))
            continue
        rnd = random.Random(30 + i)
        pts = []
        for k in range(64):
            zf = rnd.uniform(-0.05, 1.0)
            zf = math.copysign(abs(zf) ** 0.8, zf)
            a = rnd.uniform(0, 2 * math.pi)
            rr = math.sqrt(max(0.0, 1 - zf * zf)) * rnd.uniform(0.94, 1.03)
            # tops cut flat at 86 % (armour plates, not pebbles)
            pts.append((cx + rx * rr * math.cos(a), cy + ry * rr * math.sin(a), max(0.0, min(z0 + rz * 0.86, z0 + rz * zf))))
        o = convex_part(mats, pts, "M_Colony.rib" if kind == "rib" else "M_Colony", name=f"Plate{i}", bevel=0.04)
        salib.select_only([o])
        try:
            bpy.ops.object.shade_smooth_by_angle(angle=math.radians(24))
        except Exception:
            pass
        parts.append(o)
    # the turret tower: team rim + honeycomb top + spike crown, dark recessed band with lit slits
    tx, ty = SCORP_TOWER
    th, tr = SCORP_TOWER_H, SCORP_TOWER_R
    parts.append(_cyl(mats, (tx, ty, 0.55), tr, 1.1, "M_Colony", verts=32))
    parts.append(_cyl(mats, (tx, ty, 1.42), tr - 0.07, 0.66, "M_Black", verts=32))
    parts.append(_cyl(mats, (tx, ty, 1.95), tr, 0.4, "M_Colony", verts=32))
    parts.append(_cyl(mats, (tx, ty, th - 0.02), tr - 0.04, 0.04, "M_Colony.dark", verts=32))
    hr = 0.082
    for row in range(-8, 9):
        for col in range(-8, 9):
            x = col * hr * 1.8 + (hr * 0.9 if row % 2 else 0.0)
            y = row * hr * 1.56
            if x * x + y * y < (tr - 0.1) ** 2:
                parts.append(_cyl(mats, (tx + x, ty + y, th + 0.025), hr * 0.92, 0.05, "M_Colony.plate", verts=6,
                                  rot=(0, 0, math.radians(30))))
    for a in (-147, -123, -85, -63):  # lit slits round the south side
        ar = math.radians(a)
        parts.append(_box(mats, (tx + (tr - 0.06) * math.cos(ar), ty + (tr - 0.06) * math.sin(ar), 1.38),
                          (0.1, 0.06, 0.48), "M_White", rot=(0, 0, ar + math.pi / 2)))
    for k in range(14):  # crown of spikes on the rim, the northern one tall
        a = math.radians(90 + k * 360 / 14)
        ln = 0.62 if k == 0 else (0.38 if k in (1, 13) else 0.24)
        base = (tx + (tr - 0.04) * math.cos(a), ty + (tr - 0.04) * math.sin(a), th - 0.05)
        parts.append(_spike(mats, base, (math.cos(a) * 0.35, math.sin(a) * 0.35, 1.0), ln, r1=0.075, verts=6))
    parts.append(tube(mats, "Horn", [(tx + 0.5, ty + 0.38, th - 0.35), (tx + 0.82, ty + 0.5, th - 0.05),
                                     (tx + 1.0, ty + 0.55, th + 0.3)], 0.2, "M_Colony", radii=[1.0, 0.7, 0.05],
                      bevel_res=3, res_u=6))
    # segmented limb along the north-west edge, segmented limb with a spike tip in the east
    for x, y, z, r in ((-0.7, 2.05, 0.75, 0.32), (-1.08, 2.25, 0.66, 0.3), (-1.45, 2.43, 0.56, 0.28),
                       (-1.8, 2.62, 0.46, 0.26)):
        parts.append(_sphere(mats, (x, y, z), r, "M_Colony", scale=(1.15, 0.9, 0.85), rot=(0, 0, math.radians(-25)),
                             segments=18, rings=10))
    for x, y, z, r in ((1.78, 0.88, 0.72, 0.3), (2.14, 0.86, 0.68, 0.27), (2.48, 0.84, 0.64, 0.24)):
        parts.append(_sphere(mats, (x, y, z), r, "M_Colony", scale=(1.2, 0.9, 0.85), segments=18, rings=10))
    parts.append(_spike(mats, (2.62, 0.83, 0.63), (1.0, -0.05, -0.03), 0.38, r1=0.2, verts=10))
    # the open horseshoe claw of ribbed segments (tips on the ground south and south-east)
    claw = [(0.6, -2.8, 0.12), (0.42, -2.3, 0.4), (0.3, -1.8, 0.68), (0.45, -1.22, 0.9), (1.1, -0.74, 1.0),
            (1.8, -0.66, 0.9), (2.38, -0.92, 0.6), (2.66, -1.32, 0.3), (2.6, -1.56, 0.1)]
    parts.append(segmented_band(mats, "Claw", _smooth_path(claw, 4), 0.46, 0.26, "M_Colony", seg_len=0.17, gap=0.004,
                                bevel=0.025))
    # a low armoured base under the pieces: the sprite's carapace is one mass with dark crevices, the
    # ground only shows inside the open claw
    parts.append(mound("Carapace", mats, "M_Colony.rib", (-0.4, 0.45), (2.05, 1.7), 0.62, noise=0.12, noise_scale=0.6,
                       seed=13, segments=48, rings=16))
    # rivets
    for u, v in ((-1.23, -1.58), (-0.78, -0.57), (-0.01, 0.23), (-0.05, 0.78), (1.31, -0.47), (1.69, -0.15),
                 (1.13, -1.16), (1.48, -1.33)):
        x, y, z = screen_to_surface(u, v, scorp_z)
        parts.append(_sphere(mats, (x, y, z - 0.02), 0.13, "M_Iron", segments=12, rings=8))
    body = join_into(parts, "ColonyBody")
    t, bs = scorpion_turret("Turret_1", mats, (tx, ty, th))
    _attach(t, body)
    return _finish_colony(name, body, [t], [bs], 9.5, 1.1, quick)


# ---------------------------------------------------------------------------------------------
# WASP (fourth iteration, second shift): a packed comb of rimmed hexagonal cells, stepped - the back
# row is the tallest (2.3), which is why the sprite shows each back cell's front wall above the cell
# in front of it - with team-coloured larva domes in their dark tops, over a dark rock base in the
# south-west, and the big tilted panelled slab on the east.  The gatling turret stands on the big
# west cell: OpenSA's turret offset (2150,-950) lands exactly on it (screen -0.93,-1.33).
# ---------------------------------------------------------------------------------------------
def build_wasp_colony(quick=False):
    name = "colony_wasp"
    salib.reset_scene(name)
    mats = colony_materials("Y")
    # dark rock base, visible only in the south-west under the cells (sprite)
    parts = [mound("Base", mats, "M_Rock", (-1.35, -0.7), (1.05, 1.35), 0.7, noise=0.2, noise_scale=0.5, seed=9,
                   segments=40, rings=16)]
    rnd = random.Random(11)
    for i in range(9):
        a = rnd.uniform(math.radians(150), math.radians(290))
        r = rnd.uniform(0.7, 1.05)
        x, y = -1.35 + r * math.cos(a), -0.7 + r * 1.2 * math.sin(a)
        parts.append(_sphere(mats, (x, y, 0.1), rnd.uniform(0.22, 0.36), "M_Rock", ico=1, jitter=0.03, seed=i,
                             scale=(rnd.uniform(0.9, 1.3), rnd.uniform(0.9, 1.3), rnd.uniform(0.6, 0.9)),
                             rot=(0, 0, rnd.uniform(0, 3))))
    # (x, y, circumradius, height, kind): top centres fitted to the sprite with v = -(0.866 y + 0.5 h)
    cells = [((-0.77, 1.34), 0.5, 2.3, "egg"), ((0.15, 0.77), 0.47, 2.3, "egg"), ((0.97, 1.3), 0.5, 2.3, "egg"),
             ((-0.9, 0.33), 0.84, 2.0, "turret"), ((0.94, 0.38), 0.5, 1.9, "egg"), ((-2.02, 0.5), 0.42, 1.5, "egg"),
             ((0.08, -0.26), 0.47, 1.75, "egg"), ((-0.6, -1.07), 0.4, 1.65, "egg"), ((-1.49, -1.39), 0.5, 1.9, "egg"),
             ((-0.55, -1.96), 0.4, 0.5, "dark")]
    turret_pivot = None
    # the comb itself: one team-coloured block under the main cells (the sprite's cells share walls),
    # its top 0.3 below the lowest of them so every rim still stands out
    comb = [c for c in cells if c[3] != "dark" and c[0] != (-1.49, -1.39)]
    pts = []
    for (x, y), r, h, kind in comb:
        for k in range(6):
            a = k * math.pi / 3
            for z in (0.0, min(ch for _, _, ch, _ in comb) - 0.3):
                pts.append((x + r * 0.98 * math.cos(a), y + r * 0.98 * math.sin(a), z))
    parts.append(convex_part(mats, pts, "M_Colony", name="Comb", bevel=0.03))
    for (x, y), r, h, kind in cells:  # r = the rim's circumradius (the sprite's hexagon)
        parts.append(_cyl(mats, (x, y, h / 2 - 0.1), r * 0.9, h - 0.2, "M_Colony", verts=6))
        parts.append(_cyl(mats, (x, y, h - 0.02), r, 0.22, "M_Colony", verts=6))
        parts.append(_cyl(mats, (x, y, h - 0.04), r * 0.76, 0.26, "M_Black", verts=6))
        if kind == "egg":
            parts.append(_sphere(mats, (x, y, h - 0.02), r * 0.7, "M_Colony.egg", scale=(1, 1, 0.5), segments=18,
                                 rings=10))
        elif kind == "turret":
            turret_pivot = (x, y, h + 0.09)
            parts.append(_sphere(mats, (x, y, h - 0.02), r * 0.7, "M_Colony.egg", scale=(1, 1, 0.3), segments=24,
                                 rings=10))
            parts.append(_cyl(mats, (x, y, h + 0.05), r * 0.5, 0.08, "M_Iron", verts=6))
    # tilted panelled slab (long axis NE, high edge at the north-west, low edge at the south-east);
    # centre/angle/tilt/size fitted to the sprite's three visible corners (tools2/fit_slab.py)
    sc_ = (0.75, -0.3, 1.0)
    ang, tilt = math.radians(50), math.radians(14)
    rot = (tilt, 0, ang)
    m = Matrix.Rotation(ang, 3, "Z") @ Matrix.Rotation(tilt, 3, "X")

    def on_slab(lx, ly, lz):
        p = m @ Vector((lx, ly, lz))
        return (sc_[0] + p.x, sc_[1] + p.y, sc_[2] + p.z)

    parts.append(_box(mats, sc_, (3.8, 2.0, 0.24), "M_Colony", rot=rot, bevel=0.05))
    for lx in (-1.25, 0.0, 1.25):
        for ly in (-0.47, 0.47):
            parts.append(_box(mats, on_slab(lx, ly, 0.17), (1.08, 0.74, 0.12), "M_Colony", rot=rot, bevel=0.03))
    for lx in (-0.625, 0.625):
        parts.append(_box(mats, on_slab(lx, 0.0, 0.14), (0.07, 1.95, 0.05), "M_Black", rot=rot))
    parts.append(_box(mats, on_slab(0.0, 0.0, 0.14), (3.75, 0.07, 0.05), "M_Black", rot=rot))
    parts.append(_box(mats, on_slab(0.0, -0.99, -0.02), (3.8, 0.14, 0.34), "M_Colony.dark", rot=rot, bevel=0.03))
    parts.append(_box(mats, (sc_[0] - 0.15, sc_[1] + 0.1, 0.4), (2.8, 1.1, 0.8), "M_Black", rot=(0, 0, ang)))
    body = join_into(parts, "ColonyBody")
    t, bs = wasp_turret("Turret_1", mats, turret_pivot)
    _attach(t, body)
    return _finish_colony(name, body, [t], [bs], 10.0, 1.0, quick)


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
    quick = "--quick" in flags
    for a in args:
        if a not in BUILDERS:
            raise SystemExit(f"unknown colony {a}; choose from {list(BUILDERS)}")
        BUILDERS[a](quick=quick)
        print("BUILT", a, "(quick)" if quick else "", flush=True)
