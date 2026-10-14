"""Scorpion colony: chunky riveted armour pieces round the honeycomb-topped turret tower, the ribbed
horseshoe claw arch and segmented limbs.

Built by build_colony.py (usage in its docstring); shared helpers in colony_common.py.

Colony crew B rebuild (2026-10-14, after Mike: "the buildings are not up to par with the original
vision").  The old model read as soft blobs.  The body sprite (reference/models/colony_scorpion; no
original 3-D render exists) is a tight cluster of glossy, pointed, leaf/claw-shaped armour pieces with
lines running along them, black crevices and big dark rivets, a round tower whose top is a honeycomb
ringed by spikes (OpenSA puts the turret on it) and whose dark front carries four lit slits, an open
horseshoe claw of ribbed segments (south-east), a closed bulbous claw (west) and segmented limbs
(north-west, east).  This version keeps the previous crew's sprite fit for the tower, the turret, the
limbs and the claw path (its middle lifted 0.15 so it clears the palm piece) and rebuilds every part:
 * `blade`: the pointed armour pieces (root and tip fitted to the sprite) - blunt root, broad body,
   rounded-pointed tip, domed cross-section with a ridge, skirts sunk into the carapace, hammered
   noise; their grooves fan out from the tower (`fan_grooves`); horns on some tips;
 * `shell`: the round masses under / between them (west claw bulb, tower foot, south-west and north-west
   pieces) and the dark hub that shows in the crevices;
 * the tower: lathe-built body, collar, a recessed band in dark team colour (not black) with ribs and
   four dim, warm, framed slits, an overhanging rim and a real honeycomb of sunk hexagonal cells; a
   spike crown with big horns north, west and east-north-east, the north-east horn; the turret disc is
   smaller than before (r 0.42, was 0.8) so the honeycomb ring stays visible round it;
 * `armoured_chain`: the claw arch (flat, finely stepped band) and the limbs (bead segments);
 * rivets: the sprite's eight big ones, placed by casting the sprite camera's ray at their screen
   positions onto the real mesh, plus rows of small ones along the edges of four pieces;
 * baked shading like the beetle (`bake_shading`, copied from colony_beetle.py): ambient occlusion,
   sky/ground occlusion, bevel-edge highlights, mottling and grain in every material's colour bake.
"""
import math

from mathutils import Vector, noise

from colony_common import *  # noqa: F401,F403
from colony_common import _cyl, _sphere, _spike, _box, _cone, _torus, _attach, _finish_colony, _make_turret, _smooth_path  # noqa: F401


# ---------------------------------------------------------------------------------------------
# baked-shading helpers (copied from colony_beetle.py - crew B; colony_common stays untouched)
# ---------------------------------------------------------------------------------------------
def _out(node, *names):
    for n in names:
        if n in node.outputs:
            return node.outputs[n]
    return node.outputs[0]


def _bsdf(mat):
    return next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def _mr(nt, value, a, b, lo, hi, smooth=False):
    m = nt.nodes.new("ShaderNodeMapRange")
    m.clamp = True
    if smooth:
        m.interpolation_type = "SMOOTHSTEP"
    m.inputs["From Min"].default_value = a
    m.inputs["From Max"].default_value = b
    m.inputs["To Min"].default_value = lo
    m.inputs["To Max"].default_value = hi
    nt.links.new(value, m.inputs["Value"])
    return m.outputs["Result"]


def _mul(nt, a, b):
    return salib._math(nt, "MULTIPLY", a, b)


def bake_shading(mat, ao_far=0.8, far_floor=0.1, far_gamma=1.5, ao_near=0.14, near_floor=0.5, down_floor=0.35,
                 ground_h=0.4, ground_floor=0.45, edge_gain=0.22, bevel_r=0.03, grain=0.1, grain_scale=55.0,
                 mottle=(0.74, 1.04), mottle_scale=3.5, base=0.92, extra=()):
    """Multiply view-independent shading into the material's base colour (kept by the bake, which only
    whitens TeamTint) and put a bevel normal under its bump: far/near ambient occlusion, sky occlusion,
    ground contact, bevelled-edge highlights, mottling and grain.  Returns the material."""
    nt = mat.node_tree
    p = _bsdf(mat)
    src = p.inputs["Base Color"].links[0].from_socket
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    facs = []
    if base != 1.0:
        v = nt.nodes.new("ShaderNodeValue")
        v.outputs[0].default_value = base
        facs.append(v.outputs[0])
    if mottle:
        mn = nt.nodes.new("ShaderNodeTexNoise")
        mn.inputs["Scale"].default_value = mottle_scale
        mn.inputs["Detail"].default_value = 6.0
        mn.inputs["Roughness"].default_value = 0.6
        nt.links.new(tc.outputs["Object"], mn.inputs["Vector"])
        facs.append(_mr(nt, _out(mn, "Factor", "Fac"), 0.3, 0.7, mottle[0], mottle[1]))
    for dist, floor, gamma in ((ao_far, far_floor, far_gamma), (ao_near, near_floor, 1.0)):
        if dist <= 0:
            continue
        ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
        ao.samples = 16
        ao.only_local = True
        ao.inputs["Distance"].default_value = dist
        g = salib._math(nt, "POWER", ao.outputs["AO"], gamma)
        facs.append(_mr(nt, g, 0.0, 1.0, floor, 1.0))
    if down_floor < 1.0:
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(geo.outputs["Normal"], sep.inputs[0])
        facs.append(_mr(nt, sep.outputs["Z"], -0.7, 0.85, down_floor, 1.0, smooth=True))
    if ground_floor < 1.0:
        sz = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["Object"], sz.inputs[0])
        facs.append(_mr(nt, sz.outputs["Z"], 0.0, ground_h, ground_floor, 1.0, smooth=True))
    bev = nt.nodes.new("ShaderNodeBevel")
    bev.samples = 8
    bev.inputs["Radius"].default_value = bevel_r
    if edge_gain:
        dot = nt.nodes.new("ShaderNodeVectorMath")
        dot.operation = "DOT_PRODUCT"
        nt.links.new(bev.outputs["Normal"], dot.inputs[0])
        nt.links.new(geo.outputs["Normal"], dot.inputs[1])
        facs.append(_mr(nt, _out(dot, "Value"), 0.86, 0.995, 1.0 + edge_gain, 1.0))
    if grain:
        n = nt.nodes.new("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = grain_scale
        n.inputs["Detail"].default_value = 4.0
        nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
        facs.append(_mr(nt, _out(n, "Factor", "Fac"), 0.3, 0.7, 1.0 - grain, 1.0 + grain))
    facs += list(extra)
    f = facs[0]
    for x in facs[1:]:
        f = _mul(nt, f, x)
    nt.links.new(salib._mix_rgb(nt, "MULTIPLY", src, f, 1.0), p.inputs["Base Color"])
    bmp = next((n for n in nt.nodes if n.type == "BUMP"), None)
    if bmp is not None:
        nt.links.new(bev.outputs["Normal"], bmp.inputs["Normal"])
    else:
        nt.links.new(bev.outputs["Normal"], p.inputs["Normal"])
    return mat


def fan_grooves(mat, center=(0.0, 0.0), count=44, width=0.06, dark=0.42, depth=1.4, r_min=0.25, rings=0.0):
    """Grooves radiating from `center` (object XY): `count` lines round the full turn - the fanned
    ribs of the sprite's carapace plates - and, with `rings` (spacing, cells), concentric arcs across
    them.  Cut into the bump; returns the colour factor socket."""
    nt = mat.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    x = salib._math(nt, "SUBTRACT", sep.outputs["X"], center[0])
    y = salib._math(nt, "SUBTRACT", sep.outputs["Y"], center[1])
    r = salib._math(nt, "SQRT", salib._math(nt, "ADD", _mul(nt, x, x), _mul(nt, y, y)))
    ang = salib._math(nt, "ARCTAN2", y, x)
    wave = salib._math(nt, "ABSOLUTE", salib._math(nt, "SINE", _mul(nt, ang, count / 2.0)))
    g = _mr(nt, wave, 0.0, width, 1.0, 0.0, smooth=True)
    g = _mul(nt, g, _mr(nt, r, r_min, r_min + 0.15, 0.0, 1.0))
    if rings:  # concentric arcs across the fan: the sprite's net of curving lines
        rw = salib._math(nt, "ABSOLUTE", salib._math(nt, "SINE", _mul(nt, r, math.pi / rings)))
        g = salib._math(nt, "MAXIMUM", g, _mul(nt, _mr(nt, rw, 0.0, width * 0.8, 0.8, 0.0, smooth=True),
                                                _mr(nt, r, r_min, r_min + 0.15, 0.0, 1.0)))
    add_height(mat, g, -depth)
    return _mr(nt, g, 0.0, 1.0, 1.0, dark)


def drop_faces(o, pred):
    """Delete the faces of a part for which pred(face) is true (hidden faces)."""
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.normal_update()
    kill = [f for f in bm.faces if pred(f)]
    if kill:
        bmesh.ops.delete(bm, geom=kill, context="FACES")
    bm.to_mesh(o.data)
    bm.free()
    o.data.update()
    return o


def _mesh_obj(mats, name, verts, faces, mat, smooth_angle=40.0, recalc=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    o = bpy.data.objects.new(name, me)
    salib.link(o)
    salib.select_only([o])
    if recalc:
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode="OBJECT")
    o.data.materials.append(mats[mat])
    for f in o.data.polygons:
        f.use_smooth = True
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(smooth_angle))
    except Exception:
        pass
    return o


def scorp_materials():
    mats = colony_materials("Y")
    col = (0.97, 0.85, 0.47)
    armour = salib.material("M_Colony", col, roughness=0.34, kind="chitin", tint=True, variation=0.16, cell_scale=3.0,
                            bump=0.22, dirt=0.0, coat=0.35)
    mats["M_Colony"] = bake_shading(armour, far_floor=0.06, far_gamma=1.8, mottle=(0.62, 1.06))
    rib = salib.material("M_Colony.rib", col, roughness=0.36, kind="chitin", tint=True, variation=0.15, cell_scale=3.5,
                         bump=0.18, dirt=0.0, coat=0.3)
    mats["M_Colony.rib"] = bake_shading(rib, far_floor=0.06, far_gamma=1.8,
                                        mottle=(0.62, 1.06),
                                        extra=[fan_grooves(rib, center=SCORP_TOWER, count=30, width=0.32, dark=0.36,
                                                           depth=1.1, r_min=0.75)])
    band = salib.material("M_Colony.band", col, roughness=0.42, kind="chitin", tint=True, variation=0.14, cell_scale=6.0,
                          bump=0.3, dirt=0.0, coat=0.2)
    mats["M_Colony.band"] = bake_shading(band, bevel_r=0.025, edge_gain=0.28)
    comb = salib.material("M_Colony.comb", col, roughness=0.34, kind="chitin", tint=True, variation=0.1, cell_scale=9.0,
                          bump=0.2, dirt=0.0, coat=0.4)
    mats["M_Colony.comb"] = bake_shading(comb, ao_far=0.3, far_floor=0.3, ao_near=0.08, near_floor=0.4, edge_gain=0.3,
                                         bevel_r=0.012, mottle=(0.85, 1.04), base=1.0)
    recess = darken(salib.material("M_Colony.recess", col, roughness=0.5, kind="chitin", tint=True, variation=0.12,
                                   cell_scale=8.0, bump=0.2, dirt=0.0), 0.34)
    mats["M_Colony.recess"] = bake_shading(recess, ao_far=0.5, far_floor=0.35, edge_gain=0.15, base=1.0)
    under = darken(salib.material("M_Colony.under", col, roughness=0.85, kind="chitin", tint=True, variation=0.2,
                                  cell_scale=5.0, bump=0.12, dirt=0.0, coat=0.0), 0.3)
    mats["M_Colony.under"] = bake_shading(under, far_floor=0.04, far_gamma=2.0, near_floor=0.3)
    spike = darken(salib.material("M_Colony.spike", col, roughness=0.32, kind="chitin", tint=True, variation=0.1,
                                  cell_scale=12.0, bump=0.2, dirt=0.0, coat=0.5), 0.92)
    mats["M_Colony.spike"] = bake_shading(spike, ao_far=0.35, far_floor=0.4, ao_near=0.08, near_floor=0.6, down_floor=0.5,
                                          edge_gain=0.25, bevel_r=0.01, grain=0.04, ground_floor=0.8, mottle=(0.88, 1.02),
                                          base=1.0)
    rivet = salib.material("M_ScorpRivet", (0.3, 0.29, 0.29), roughness=0.28, metallic=0.25, kind="glossy")
    mats["M_ScorpRivet"] = bake_shading(rivet, ao_far=0.2, far_floor=0.4, ao_near=0.05, near_floor=0.5, down_floor=0.45,
                                        ground_floor=1.0, edge_gain=0.5, bevel_r=0.01, grain=0.06, mottle=(0.8, 1.05), base=1.0)
    mats["M_ScorpSlit"] = salib.material("M_ScorpSlit", (0.9, 0.78, 0.68), roughness=0.4, emission=(1.0, 0.8, 0.62),
                                         emission_strength=0.45, kind="glossy")
    for k in ("M_Bone", "M_Wood", "M_Gunmetal", "M_Black", "M_Hollow"):
        bake_shading(mats[k], ao_far=0.35, far_floor=0.3, ao_near=0.08, near_floor=0.55, down_floor=0.5, ground_floor=1.0,
                     edge_gain=0.35, bevel_r=0.012, grain=0.05, mottle=(0.85, 1.05), base=1.0)
    return mats


# ---------------------------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------------------------
SCORP_TOWER = (0.42, 1.2)
TOWER_TOP = 2.12           # honeycomb surface; turret pivot just above (OpenSA screen 0.43,-2.13 -> z ~2.17)
PIVOT_Z = TOWER_TOP + 0.02
# base masses under the armour (x, y, rx, ry, rz, material, p): the hub round the tower foot (dark: it is
# what shows in the crevices between the pieces), the bulb of the closed west claw, the mass at the tower foot
MASSES = [(0.2, 0.35, 1.35, 1.15, 0.92, "M_Colony.under", 2.0),
          (-1.75, 0.3, 0.86, 0.84, 0.8, "M_Colony", 1.9),
          (0.45, 0.95, 0.92, 0.62, 0.92, "M_Colony", 2.2),
          (-0.95, -1.3, 0.72, 0.6, 0.6, "M_Colony.rib", 2.4),      # the round south-west piece
          (-1.15, 1.1, 0.62, 0.48, 0.62, "M_Colony.rib", 2.0)]     # low round piece under the north-west limb
# the sprite's pointed armour pieces (leaf / claw shapes, ribbed along their length), root and tip fitted to
# the body sprite with u = X, v = -(0.866 Y + 0.5 Z):
# root (x, y), z_root, tip (x, y), z_tip, half width, thickness, bend, horn at the tip (length, radius) or None
BLADES = [((-1.0, 0.3), 1.0, (-2.55, 0.6), 0.55, 0.62, 0.3, 0.0, (0.26, 0.1)),      # W, over the claw bulb
          ((0.2, -0.1), 1.28, (-0.9, 0.12), 0.98, 0.5, 0.26, -0.1, (0.3, 0.1)),       # centre, pointing W (the shelf)
          ((0.15, -0.35), 1.08, (0.25, -1.75), 0.36, 0.6, 0.28, 0.0, None),            # the palm, pointing S
          ((0.6, 0.18), 1.18, (2.2, 0.05), 0.6, 0.6, 0.3, 0.06, (0.26, 0.1)),          # E
          ((0.9, 0.62), 1.25, (1.62, 1.8), 0.72, 0.5, 0.28, -0.1, (0.3, 0.1)),         # NE
          ((-0.2, 1.45), 1.0, (-1.1, 2.1), 0.62, 0.45, 0.24, 0.1, None)]               # NW under the limb
BLADE_RIDGE = 0.05


def blade_frame(b, u):
    """Centre point (on the axis, at the top), axis and side vectors of blade b at u."""
    (rx_, ry_), zr, (tx_, ty_), zt, hw, th, bend, horn = b
    r0 = Vector((rx_, ry_, 0.0))
    ax = Vector((tx_ - rx_, ty_ - ry_, 0.0))
    L = ax.length
    ax.normalize()
    side = Vector((-ax.y, ax.x, 0.0))
    zc = zr + (zt - zr) * (3 * u * u - 2 * u * u * u)
    c = r0 + ax * (L * u) + side * (bend * L * u * u)
    return Vector((c.x, c.y, zc)), ax, side


def blade_point(b, u, v):
    """Top-surface point of blade b at (u along, v across in -1..1), without the noise."""
    (rx_, ry_), zr, (tx_, ty_), zt, hw, th, bend, horn = b
    c, ax, side = blade_frame(b, u)
    w = max(0.015, hw * _blade_w(u))
    thk = th * (0.45 + 0.55 * _blade_w(u))
    dome = thk * max(0.0, 1.0 - v * v) ** 0.55 + BLADE_RIDGE * (1.0 - abs(v)) * min(1.0, 3.0 * (1.0 - u))
    p = c + side * (w * v)
    return Vector((p.x, p.y, c.z + dome))


SHELL_P = 2.2


def _profile(f, p=SHELL_P):
    return max(0.0, 1.0 - f ** p) ** (1.0 / p)


def _rot(x, y, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return x * c - y * s, x * s + y * c


def _lobe(a, lobes):
    """Radial factor of a shell outline at angle a (radians): pointed lobes [(angle deg, amp, width deg)]."""
    f = 1.0
    for ang, amp, w in lobes:
        d = math.atan2(math.sin(a - math.radians(ang)), math.cos(a - math.radians(ang)))
        f += amp * math.exp(-(d / math.radians(w)) ** 2)
    return f


def shell(mats, name, mat, cx, cy, z0, rx, ry, rz, rot=0.0, p=SHELL_P, lip=0.0, sink=0.16, n_a=48, seed=0.0,
          bumps=0.03, lobes=(), tilt=(0.0, 0.0), jag=0.06):
    """A chunky armour shell: a superellipse dome over an irregular outline (pointed `lobes`, `jag`
    low-frequency wobble), tilted by `tilt` (dz per cell in x, y: the outer edge lifts like a scale),
    with a rolled rim (a raised lip just inside the edge), its skirt sunk `sink` below z0, hammered noise."""
    fr = [0.0, 0.16, 0.32, 0.47, 0.6, 0.7, 0.77, 0.82, 0.86, 0.9, 0.935, 0.965, 0.99, 1.0]

    def h(f):
        lipz = lip * math.exp(-((f - 0.92) / 0.035) ** 2) - 0.9 * lip * math.exp(-((f - 0.85) / 0.025) ** 2)
        return rz * _profile(f, p) + lipz

    verts, faces = [], []
    verts.append(Vector((cx, cy, z0 + h(0.0))))
    rings = []
    for f in fr[1:]:
        ring = []
        for j in range(n_a):
            a = 2 * math.pi * j / n_a
            k = _lobe(a, lobes) * (1.0 + jag * noise.noise(Vector((math.cos(a) * 1.3 + seed, math.sin(a) * 1.3, seed))))
            lx, ly = _rot(rx * f * k * math.cos(a), ry * f * k * math.sin(a), rot)
            z = z0 + h(f) + tilt[0] * lx + tilt[1] * ly
            pnt = Vector((cx + lx, cy + ly, z))
            if f < 0.97:
                z += bumps * noise.noise(pnt * 1.8 + Vector((seed, seed, 0)))
            ring.append(len(verts))
            verts.append(Vector((cx + lx, cy + ly, z)))
        rings.append(ring)
    skirt = []
    for j in range(n_a):  # vertical skirt down into the carapace
        v = verts[rings[-1][j]]
        skirt.append(len(verts))
        verts.append(Vector((v.x, v.y, z0 - sink)))
    rings.append(skirt)
    for j in range(n_a):
        faces.append((0, rings[0][j], rings[0][(j + 1) % n_a]))
    for ra, rb in zip(rings, rings[1:]):
        for j in range(n_a):
            k = (j + 1) % n_a
            faces.append((ra[j], rb[j], rb[k], ra[k]))
    # open at the bottom: the winding above already faces out (no consistency guess on an open mesh)
    return _mesh_obj(mats, name, verts, faces, mat, smooth_angle=55.0, recalc=False)


def _blade_w(u):
    """Half-width profile of a blade along its axis: blunt rounded root, broad body, rounded-pointed tip."""
    return max(0.0, 1.0 - u ** 2.2) ** 0.5 * min(1.0, (u + 0.12) / 0.3) ** 0.5


def blade(mats, name, mat, root, tip, z_root, z_tip, half_w, thick, ridge=0.05, sink=0.35, n_u=20, n_v=15, seed=0.0,
          bend=0.0, bumps=0.025):
    """A pointed armour piece (the sprite's leaf/claw-shaped plates): its axis runs from `root` (x, y)
    to `tip`, its top from z_root to z_tip, half width `half_w` (blunt root, widest near the root,
    pointed tip), a domed cross-section of `thick` with a ridge along the axis, `bend` curves the
    axis sideways; side and root skirts drop `sink` into the carapace."""
    r0 = Vector((root[0], root[1], 0.0))
    ax = Vector((tip[0] - root[0], tip[1] - root[1], 0.0))
    L = ax.length
    ax.normalize()
    side = Vector((-ax.y, ax.x, 0.0))
    rows = []
    verts = []
    for i in range(n_u):
        u = i / (n_u - 1)
        w = max(0.015, half_w * _blade_w(u))
        zc = z_root + (z_tip - z_root) * (3 * u * u - 2 * u * u * u)
        th = thick * (0.45 + 0.55 * _blade_w(u))
        c = r0 + ax * (L * u) + side * (bend * L * u * u)
        row = []
        pts = []
        for j in range(n_v):
            v = -1.0 + 2.0 * j / (n_v - 1)
            dome = th * max(0.0, 1.0 - v * v) ** 0.55 + ridge * (1.0 - abs(v)) * min(1.0, 3.0 * (1.0 - u))
            p = c + side * (w * v)
            z = zc + dome
            if abs(v) < 0.95:
                z += bumps * noise.noise(Vector((p.x, p.y, z)) * 2.2 + Vector((seed, 0.0, seed)))
            pts.append(Vector((p.x, p.y, z)))
        # [left skirt, top v -1..1, right skirt]
        left, right = pts[0], pts[-1]
        row = [Vector((left.x - side.x * 0.02, left.y - side.y * 0.02, zc - sink))] + pts + \
              [Vector((right.x + side.x * 0.02, right.y + side.y * 0.02, zc - sink))]
        rows.append(row)
    # root skirt: a copy of the first row dropped into the carapace
    first = [Vector((p.x - ax.x * 0.03, p.y - ax.y * 0.03, z_root - sink)) for p in rows[0]]
    rows.insert(0, first)
    M = n_v + 2
    for row in rows:
        verts += row
    faces = []
    for i in range(len(rows) - 1):
        for j in range(M - 1):
            a, b = i * M + j, i * M + j + 1
            faces.append((a, a + M, b + M, b))
    o = _mesh_obj(mats, name, verts, faces, mat, smooth_angle=60.0, recalc=False)
    return o


def honeycomb(mats, name, mat, cx, cy, z, radius, cell=0.085, depth=0.075, inner=0.62):
    """A field of sunk hexagonal cells (pointy-top hexagons, circumradius `cell`): each cell a funnel
    from its rim (at z) down to a flat bottom `depth` lower; cells within `radius`."""
    verts, faces = [], []
    dx, dy = math.sqrt(3) * cell, 1.5 * cell
    n = int(radius / dy) + 2
    for row in range(-n, n + 1):
        for col in range(-n, n + 1):
            x = col * dx + (dx / 2 if row % 2 else 0.0)
            y = row * dy
            if math.hypot(x, y) > radius - cell * 0.9:
                continue
            base = len(verts)
            for k in range(6):
                a = math.radians(30 + 60 * k)
                verts.append(Vector((cx + x + cell * math.cos(a), cy + y + cell * math.sin(a), z)))
            for k in range(6):
                a = math.radians(30 + 60 * k)
                verts.append(Vector((cx + x + inner * cell * math.cos(a), cy + y + inner * cell * math.sin(a), z - depth)))
            for k in range(6):  # funnel walls, wound so their normals face up into the cell
                k2 = (k + 1) % 6
                faces.append((base + k, base + k2, base + 6 + k2, base + 6 + k))
            faces.append(tuple(base + 6 + k for k in range(6)))  # flat bottom, normal up
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)  # neighbouring cells share their rims
    bm.to_mesh(me)
    bm.free()
    me.update()
    o = bpy.data.objects.new(name, me)
    salib.link(o)
    salib.select_only([o])
    o.data.materials.append(mats[mat])
    for f in o.data.polygons:
        f.use_smooth = True
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(30))
    except Exception:
        pass
    return o


def lathe(mats, name, mat, cx, cy, profile, segs=40, smooth_angle=35.0):
    """Surface of revolution of the (r, z) profile round the vertical axis through (cx, cy); a last
    point with r = 0 closes the top."""
    verts, faces, rings = [], [], []
    apex = None
    for r, z in profile:
        if r <= 1e-5:
            apex = len(verts)
            verts.append(Vector((cx, cy, z)))
            break
        ring = []
        for j in range(segs):
            a = 2 * math.pi * j / segs
            ring.append(len(verts))
            verts.append(Vector((cx + r * math.cos(a), cy + r * math.sin(a), z)))
        rings.append(ring)
    for ra, rb in zip(rings, rings[1:]):
        for j in range(segs):
            k = (j + 1) % segs
            faces.append((ra[j], ra[k], rb[k], rb[j]))
    if apex is not None:
        for j in range(segs):
            faces.append((rings[-1][j], rings[-1][(j + 1) % segs], apex))
    # wound outwards for a profile that climbs (inwards where it turns in over a top): no recalc on
    # these open surfaces
    return _mesh_obj(mats, name, verts, faces, mat, smooth_angle=smooth_angle, recalc=False)


def armoured_chain(mats, name, mat, pts, width, thick, seg_len=0.24, shape=None, power=3.5, n_c=16, steps=6,
                   tip=(0.0, 0.0), tip_len=0.4, ridge=0.0):
    """A chain of overlapping armour segments along the smooth 3-D path `pts` (claw arch, limbs):
    superellipse cross-section width x thick, each segment flared at its back rim and tucked in at
    its front so the joints step like a scorpion's tail.  `shape` = [(u, scale)] across one segment;
    `tip` = (start, end) taper to a point over `tip_len` at the path ends."""
    shape = shape or [(0.0, 1.0), (0.1, 1.07), (0.25, 1.02), (0.85, 0.94), (1.0, 0.9)]
    P = [Vector(p) for p in _smooth_path(pts, steps)]
    L = [0.0]
    for a, b in zip(P, P[1:]):
        L.append(L[-1] + (b - a).length)
    total = L[-1]

    def at(s):
        s = max(0.0, min(total, s))
        i = 0
        while i < len(L) - 2 and L[i + 1] < s:
            i += 1
        f = (s - L[i]) / max(1e-9, L[i + 1] - L[i])
        pos = P[i].lerp(P[i + 1], f)
        tan = (P[i + 1] - P[i]).normalized()
        return pos, tan

    n_seg = max(1, int(round(total / seg_len)))
    verts, faces = [], []
    for k in range(n_seg):
        s0, s1 = total * k / n_seg, total * (k + 1) / n_seg
        rings = []
        for u, sc in shape:
            s = s0 + u * (s1 - s0)
            pos, tan = at(s)
            side = tan.cross(Vector((0, 0, 1)))
            if side.length < 1e-6:
                side = Vector((1, 0, 0))
            side.normalize()
            up = side.cross(tan).normalized()
            if up.z < 0:
                up, side = -up, -side
            taper = 1.0
            if tip[0] and s < tip_len:
                taper = min(taper, 1.0 - tip[0] * (1.0 - s / tip_len) ** 1.5)
            if tip[1] and total - s < tip_len:
                taper = min(taper, 1.0 - tip[1] * (1.0 - (total - s) / tip_len) ** 1.5)
            ring = []
            for j in range(n_c):
                a = 2 * math.pi * j / n_c
                ca, sa = math.cos(a), math.sin(a)
                cx_ = math.copysign(abs(ca) ** (2.0 / power), ca)
                cy_ = math.copysign(abs(sa) ** (2.0 / power), sa)
                ridge_z = ridge * math.exp(-(a - math.pi / 2) ** 2 / 0.08) if ridge else 0.0
                p = pos + side * (cx_ * width * 0.5 * sc * taper) + up * (cy_ * thick * 0.5 * sc * taper + ridge_z * taper)
                ring.append(len(verts))
                verts.append(p)
            rings.append(ring)
        for ra, rb in zip(rings, rings[1:]):
            for j in range(n_c):
                jj = (j + 1) % n_c
                faces.append((ra[j], ra[jj], rb[jj], rb[j]))
        c0 = len(verts)  # back cap (the visible rim face of the joint)
        verts.append(sum((verts[i] for i in rings[0]), Vector()) / n_c)
        for j in range(n_c):
            faces.append((rings[0][(j + 1) % n_c], rings[0][j], c0))
        c1 = len(verts)
        verts.append(sum((verts[i] for i in rings[-1]), Vector()) / n_c)
        for j in range(n_c):
            faces.append((rings[-1][j], rings[-1][(j + 1) % n_c], c1))
    return _mesh_obj(mats, name, verts, faces, mat, smooth_angle=50.0)


def scorpion_turret(name, mats, pivot):
    """Pale disc (turret sprite) with a dark hollow carrying two brown spear rails, spears loaded with
    bone heads.  Smaller than the sprite's disc so the honeycomb ring of the tower top stays visible."""
    p = Vector(pivot)
    fixed = [_cyl(mats, p + Vector((0, 0, 0.1)), 0.42, 0.2, "M_Bone", verts=32),
             _torus(mats, p + Vector((0, 0, 0.2)), 0.38, 0.045, "M_Bone", segs=(32, 8)),
             _cyl(mats, p + Vector((0, 0, 0.215)), 0.31, 0.03, "M_Black", verts=28)]
    moving = []
    for sx in (-1, 1):
        x = sx * 0.22
        moving.append(_box(mats, (p.x + x, p.y - 0.18, p.z + 0.33), (0.17, 1.2, 0.14), "M_Wood", bevel=0.03))
        for y in (0.3, -0.48):
            moving.append(_box(mats, (p.x + x, p.y + y, p.z + 0.42), (0.21, 0.12, 0.07), "M_Bone", bevel=0.015))
        moving.append(_cyl(mats, p + Vector((x, -0.3, 0.45)), 0.035, 1.25, "M_Gunmetal", verts=8, rot=(math.radians(90), 0, 0)))
        moving.append(_cone(mats, p + Vector((x, -1.06, 0.45)), 0.11, 0.0, 0.3, "M_Bone", rot=(math.radians(90), 0, 0), verts=8))
    return _make_turret(name, mats, pivot, fixed, moving)


def build_scorpion_colony(quick=False):
    name = "colony_scorpion"
    salib.reset_scene(name)
    mats = scorp_materials()
    parts = []
    # the carapace under everything: dark team colour in the crevices between the shells
    parts.append(drop_faces(mound("Carapace", mats, "M_Colony.under", (-0.35, 0.4), (2.1, 1.75), 0.66, noise=0.1,
                                  noise_scale=0.6, seed=13, segments=48, rings=16),
                            lambda f: f.calc_center_median().z < 0.01 and f.normal.z < -0.5))
    # black hollows under the shelf, left of the tower and under the north-west limb
    for cx, cy, cz, rx, ry, rz in ((-1.5, 1.42, 0.0, 0.62, 0.4, 0.62), (-0.45, 1.3, 0.2, 0.32, 0.3, 0.95),
                                   (-0.35, -0.3, 0.0, 0.55, 0.45, 0.66)):
        parts.append(_sphere(mats, (cx, cy, cz), 1.0, "M_Hollow", scale=(rx, ry, rz), segments=16, rings=8))
    for k, (cx, cy, rx, ry, rz, mat, p) in enumerate(MASSES):  # the masses under the armour pieces
        parts.append(shell(mats, f"Mass{k}", mat, cx, cy, 0.0, rx, ry, rz, p=p, seed=20 + k, jag=0.04))
    for k, b in enumerate(BLADES):  # the pointed armour pieces, ribbed along their length (fan from the tower)
        (rx_, ry_), zr, (tx_, ty_), zt, hw, th, bend, horn = b
        parts.append(blade(mats, f"Blade{k}", "M_Colony.rib", (rx_, ry_), (tx_, ty_), zr, zt, hw, th, ridge=BLADE_RIDGE,
                           bend=bend, seed=k * 1.3))
        if horn:  # a horn growing out of the tip
            ln, r1 = horn
            c, ax, side = blade_frame(b, 0.9)
            d = (blade_frame(b, 0.99)[0] - c).normalized()
            sp = _spike(mats, tuple(c + Vector((0, 0, 0.05))), tuple(d + Vector((0, 0, 0.12))), ln, r1=r1, mat="M_Colony.spike",
                        verts=10)
            parts.append(drop_faces(sp, lambda f: len(f.verts) > 3))
    # ---- the turret tower ----
    tx, ty = SCORP_TOWER
    top = TOWER_TOP
    parts.append(lathe(mats, "TowerBody", "M_Colony", tx, ty,
                       [(0.7, -0.1), (0.7, 0.86), (0.74, 0.9), (0.76, 0.95), (0.74, 1.0), (0.64, 1.02)], segs=40))
    parts.append(lathe(mats, "TowerBand", "M_Colony.recess", tx, ty, [(0.64, 1.01), (0.62, 1.04), (0.62, 1.74), (0.66, 1.78)],
                       segs=40))
    parts.append(lathe(mats, "TowerTop", "M_Colony", tx, ty,
                       [(0.65, 1.77), (0.78, 1.83), (0.82, 1.92), (0.83, 2.04), (0.81, top + 0.04), (0.74, top + 0.045),
                        (0.71, top - 0.01), (0.7, top - 0.09), (0.0, top - 0.09)], segs=48))
    parts.append(honeycomb(mats, "Honeycomb", "M_Colony.comb", tx, ty, top, 0.72, cell=0.083))
    slits = (-147, -123, -85, -63)
    for a in slits:  # four dim lit slits in the dark band, each in a dark frame
        ar = math.radians(a)
        c, s = math.cos(ar), math.sin(ar)
        rot = (0, 0, ar + math.pi / 2)
        parts.append(_box(mats, (tx + 0.63 * c, ty + 0.63 * s, 1.32), (0.08, 0.03, 0.28), "M_ScorpSlit", rot=rot))
        for dz, w, hgt in ((0.17, 0.15, 0.05), (-0.17, 0.15, 0.05)):
            parts.append(_box(mats, (tx + 0.645 * c, ty + 0.645 * s, 1.32 + dz), (w, 0.06, hgt), "M_Colony.recess", rot=rot,
                              bevel=0.01))
        for side in (-1, 1):
            off = Vector((-s, c, 0.0)) * (0.065 * side)
            parts.append(_box(mats, (tx + 0.645 * c + off.x, ty + 0.645 * s + off.y, 1.32), (0.045, 0.06, 0.34),
                              "M_Colony.recess", rot=rot, bevel=0.01))
    for k in range(18):  # vertical ribs round the band (none across the slits)
        a = -180 + k * 20 + 10
        if any(abs(((a - sa + 180) % 360) - 180) < 13 for sa in slits):
            continue
        ar = math.radians(a)
        parts.append(_box(mats, (tx + 0.63 * math.cos(ar), ty + 0.63 * math.sin(ar), 1.4), (0.06, 0.05, 0.7), "M_Colony.recess",
                          rot=(0, 0, ar + math.pi / 2), bevel=0.012))
    for k in range(14):  # crown of spikes on the rim; big horns to the north, west and east-north-east
        a = math.radians(90 + k * 360 / 14)
        ln, r1 = {0: (0.55, 0.13), 4: (0.5, 0.15), 11: (0.48, 0.15), 1: (0.3, 0.09), 13: (0.3, 0.09)}.get(k, (0.2, 0.08))
        base = (tx + 0.79 * math.cos(a), ty + 0.79 * math.sin(a), top)
        out = 0.9 if r1 > 0.12 else 0.45
        sp = _spike(mats, base, (math.cos(a) * out, math.sin(a) * out, 1.0), ln, r1=r1, mat="M_Colony.spike", verts=8)
        parts.append(drop_faces(sp, lambda f: len(f.verts) > 3))
    parts.append(tube(mats, "Horn", [(tx + 0.5, ty + 0.38, top - 0.36), (tx + 0.82, ty + 0.5, top - 0.06),
                                     (tx + 1.0, ty + 0.55, top + 0.3)], 0.2, "M_Colony.spike", radii=[1.0, 0.7, 0.05],
                      bevel_res=3, res_u=6))
    # ---- limbs: overlapping bead-like armour segments ----
    bead = [(0.0, 0.72), (0.15, 0.98), (0.45, 1.1), (0.8, 0.98), (1.0, 0.76)]
    parts.append(armoured_chain(mats, "LimbNW", "M_Colony.band", [(-0.45, 1.98, 0.8), (-1.08, 2.25, 0.66), (-1.48, 2.45, 0.56),
                                                                  (-1.95, 2.68, 0.42)],
                                0.56, 0.52, seg_len=0.4, shape=bead, power=2.4, n_c=18, tip=(0.0, 0.2)))
    parts.append(armoured_chain(mats, "LimbE", "M_Colony.band", [(1.6, 0.9, 0.74), (2.14, 0.86, 0.68), (2.5, 0.84, 0.64)],
                                0.52, 0.5, seg_len=0.36, shape=bead, power=2.4, n_c=18))
    sp = _spike(mats, (2.6, 0.83, 0.63), (1.0, -0.05, -0.03), 0.36, r1=0.2, mat="M_Colony.spike", verts=12)
    parts.append(drop_faces(sp, lambda f: len(f.verts) > 3))
    # ---- the open horseshoe claw: a ribbed arch of armour segments, tips on the ground ----
    # (the previous crew's sprite fit, its middle lifted ~0.15 so the band clears the palm piece instead of
    # cutting through it at a shallow angle - that showed as z-fighting in game)
    claw = [(0.6, -2.8, 0.1), (0.42, -2.3, 0.42), (0.3, -1.8, 0.8), (0.45, -1.22, 1.08), (1.1, -0.74, 1.15),
            (1.8, -0.66, 1.02), (2.38, -0.92, 0.66), (2.66, -1.32, 0.3), (2.6, -1.56, 0.08)]
    flat = [(0.0, 1.0), (0.1, 1.05), (0.22, 1.0), (0.9, 0.97), (1.0, 0.95)]
    parts.append(armoured_chain(mats, "Claw", "M_Colony.band", claw, 0.58, 0.17, seg_len=0.16, shape=flat, power=6.0,
                                n_c=20, tip=(0.2, 0.2), tip_len=0.35))
    body = join_into(parts, "ColonyBody")
    # ---- rivets: the sprite's eight big ones, found by casting the sprite camera's ray at their screen
    # positions onto the real surface; rows of small ones along the long edges of three pieces ----
    from mathutils.bvhtree import BVHTree
    bvh = BVHTree.FromObject(body, bpy.context.evaluated_depsgraph_get())
    el = math.radians(SPRITE_ELEVATION)
    ray = Vector((0.0, math.cos(el), -math.sin(el)))
    rivets = []
    for u, v in ((-1.23, -1.58), (-0.78, -0.57), (-0.01, 0.23), (-0.05, 0.78), (1.31, -0.47), (1.69, -0.15),
                 (1.13, -1.16), (1.48, -1.33)):
        org = Vector((u, (-v - math.cos(el) * 6.0) / math.sin(el), 6.0))
        hit, nrm, _, _ = bvh.ray_cast(org, ray)
        if hit is None:
            continue
        rivets.append(_sphere(mats, tuple(hit - nrm * 0.035), 0.13, "M_ScorpRivet", scale=(1, 1, 0.85), segments=16, rings=8))
    for bi, sides in ((2, (-0.72, 0.72)), (3, (-0.72,)), (1, (-0.7,)), (4, (-0.7,))):  # palm, E, centre, NE
        for vv in sides:
            for uu in (0.18, 0.33, 0.48, 0.63):
                p = blade_point(BLADES[bi], uu, vv)
                rivets.append(_sphere(mats, tuple(p - Vector((0, 0, 0.015))), 0.05, "M_ScorpRivet", segments=10, rings=6))
    body = join_into([body] + rivets, "ColonyBody")
    t, bs = scorpion_turret("Turret_1", mats, (tx, ty, PIVOT_Z))
    _attach(t, body)
    return _finish_colony(name, body, [t], [bs], 9.5, 1.1, quick)
