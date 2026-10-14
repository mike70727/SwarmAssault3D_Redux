"""Ant colony: dark cobbled earth mound coiled by team-coloured rope bands, two towers.

Built by build_colony.py (usage in its docstring); shared helpers in colony_common.py.
"""
from colony_common import *  # noqa: F401,F403


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
