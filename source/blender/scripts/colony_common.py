"""Shared code of the colony builders (build_colony.py + colony_<family>.py): primitives,
materials, clips, the turret helper and the finishing (bake/export/previews, sprite-view check).

Split out of build_colony.py so that each colony lives in its own file; the conventions and the
sprite projection are described in build_colony.py's docstring.
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
TRI_BUDGET = 40000  # per colony (body + turrets); colonies are few, so they can carry more detail than units


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




# everything above, underscore helpers included, for `from colony_common import *`
__all__ = [n for n in list(globals()) if not n.startswith("__")]
