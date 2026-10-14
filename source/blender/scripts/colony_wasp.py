"""Wasp colony: a packed comb of rimmed hexagonal cells on a rock base, with a slab.

Built by build_colony.py (usage in its docstring); shared helpers in colony_common.py.
"""
from colony_common import *  # noqa: F401,F403


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
