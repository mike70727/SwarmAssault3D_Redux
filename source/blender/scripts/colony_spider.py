"""Spider colony: a giant upturned spider over a chrome bell, two towers.

Built by build_colony.py (usage in its docstring); shared helpers in colony_common.py.
"""
from colony_common import *  # noqa: F401,F403


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
