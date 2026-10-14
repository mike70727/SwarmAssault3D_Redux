"""Scorpion colony: an armoured carapace of plates, a honeycomb-topped turret tower.

Built by build_colony.py (usage in its docstring); shared helpers in colony_common.py.
"""
from colony_common import *  # noqa: F401,F403


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
