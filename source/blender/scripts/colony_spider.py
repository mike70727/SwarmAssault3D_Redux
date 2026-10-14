"""Spider colony: a giant spider gripping a chrome bell - thick knobbly team-coloured legs rise from
the hub to high knees and come down to the ground - and two knobbly towers with sniper turrets.

Built by build_colony.py (usage in its docstring); shared helpers in colony_common.py and the crew-A
helpers in colony_ant.py (baked shading, tubes, displaced lathes, packed-UV finish).

Fifth iteration (colony crew A, 2026-10-14; Mike: "the buildings are not up to par with the original
vision").  Kept from the previous crew (fitted to the sprite, u = X, v = -(0.866 Y + 0.5 Z)): the bell
(lathe, axis (0.05, 0.1), long axis north-east), the hub at z 2.2, the leg directions with the
south-east gap, the towers (-0.86, 0.68) and (0.95, -1.06) with tops at 2.75.  New:
  * legs are spider legs, not tentacles: a straight femur rising from the hub to a high, swollen knee,
    then a steep tibia down to the ground; thick, covered in knobs (displaced geometry + a baked
    cellular bump), with deep occlusion between the knobs; legs that ran into a tower are gone;
  * the bell is chrome that reads as chrome in a game without reflections: its colour map carries the
    mirror image of a simple world (dark ground, bright horizon, pale sky) seen from the game camera,
    on a bell with rounded ribs, so the bands follow the form like the original's;
  * the hub is a chrome cap with a dark slot and a crown of knobs and spikes (loading screen 1);
  * towers are knobbly columns with rims; the turrets are octagonal drums with a mantlet and a long
    sniper barrel with a scope and muzzle brake (no dark hole: the drum's hatch is a closed lid).
"""
from colony_common import *  # noqa: F401,F403
from colony_ant import (_m, _remap, ca_bake_shading, ca_finish_colony, ca_material, displaced_lathe, ensure_uv,
                        rope_tube, smoothstep)
from mathutils import noise


def ca_chrome(name, elev=52.0, wobble=0.07, shading=None):
    """Chrome for a game without reflection probes: the base colour is the mirror image of a simple
    world - dark brown ground, a bright horizon line, a pale sky - seen from the game camera (from the
    south, `elev` degrees up), so the colour map carries the bands a chrome surface shows from there.
    Glossy and nearly non-metallic in game (a metallic surface without reflections renders flat dark)."""
    mat = salib.material(name, (0.7, 0.7, 0.72), roughness=0.16, metallic=0.1, kind="glossy", coat=0.8)
    nt = mat.node_tree
    p = _principled(mat)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    e = math.radians(elev)
    view = (0.0, -math.cos(e), math.sin(e))
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    nt.links.new(geo.outputs["Normal"], dot.inputs[0])
    dot.inputs[1].default_value = view
    sc = nt.nodes.new("ShaderNodeVectorMath")
    sc.operation = "SCALE"
    nt.links.new(geo.outputs["Normal"], sc.inputs[0])
    nt.links.new(_m(nt, "MULTIPLY", dot.outputs["Value"], 2.0), sc.inputs["Scale"])
    refl = nt.nodes.new("ShaderNodeVectorMath")
    refl.operation = "SUBTRACT"
    nt.links.new(sc.outputs["Vector"], refl.inputs[0])
    refl.inputs[1].default_value = view
    # an imperfect mirror: low-frequency wobble of the reflected direction
    n = salib._noise(nt, _coord(nt), 1.4, detail=2.0, roughness=0.5)
    centred = nt.nodes.new("ShaderNodeVectorMath")
    centred.operation = "SUBTRACT"
    nt.links.new(n.outputs["Color"], centred.inputs[0])
    centred.inputs[1].default_value = (0.5, 0.5, 0.5)
    wob = nt.nodes.new("ShaderNodeVectorMath")
    wob.operation = "MULTIPLY_ADD"
    nt.links.new(centred.outputs["Vector"], wob.inputs[0])
    wob.inputs[1].default_value = (wobble * 2.0,) * 3
    nt.links.new(refl.outputs["Vector"], wob.inputs[2])
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(wob.outputs["Vector"], sep.inputs["Vector"])
    t = _remap(nt, sep.outputs["Z"], -1.0, 1.0, 0.0, 1.0)
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    stops = [(0.0, (0.12, 0.1, 0.09)), (0.3, (0.26, 0.22, 0.19)), (0.44, (0.42, 0.36, 0.31)),
             (0.485, (0.55, 0.48, 0.42)), (0.5, (1.0, 0.98, 0.95)), (0.53, (0.9, 0.9, 0.9)),
             (0.7, (0.78, 0.79, 0.8)), (1.0, (0.62, 0.63, 0.66))]
    cr.elements[0].position, cr.elements[0].color = stops[0][0], salib._lin(stops[0][1])
    cr.elements[1].position, cr.elements[1].color = stops[-1][0], salib._lin(stops[-1][1])
    for pos, col in stops[1:-1]:
        el = cr.elements.new(pos)
        el.color = salib._lin(col)
    nt.links.new(t, ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], p.inputs["Base Color"])
    ca_bake_shading(mat, **(shading or {}))
    return mat


# ---------------------------------------------------------------------------------------------
SPIDER_AXIS = (0.05, 0.1)
SPIDER_HUB_Z = 2.2
SPIDER_BELL = [(2.5, 0.0), (2.4, 0.45), (2.08, 1.0), (1.55, 1.5), (0.95, 1.85), (0.52, 2.05), (0.0, 2.12)]
SPIDER_BELL_SCALE = (1.0, 0.78)
SPIDER_BELL_ROT = 45.0
# leg directions (deg): the sprite's gap in the south-east (the east tower and the dark interior show
# there); none within reach of a tower
SPIDER_LEG_ANGLES = (90, 72, 55, 38, 21, 4, -15, -95, -118, -140, -162, 178, 108)
SPIDER_TOWERS = (((-0.86, 0.68), 2.75), ((0.95, -1.06), 2.75))  # top-face centres fitted to the sprite
SPIDER_KNEE_Z = 2.56  # knees (with their knobs) stay under the sweeping sniper barrels (bottom 2.99)
SPIDER_GUN_Z = 0.32  # barrel axis above the tower top -> colonies.ron height 3.07


def bell_r(a_deg):
    """Base radius of the elliptical bell in direction a."""
    a = math.radians(a_deg - SPIDER_BELL_ROT)
    sx, sy = SPIDER_BELL_SCALE
    return SPIDER_BELL[0][0] / math.sqrt((math.cos(a) / sx) ** 2 + (math.sin(a) / sy) ** 2)


def knobs(cell=0.12, height=0.3, seed=3):
    """Radius factor for knobbly tubes: rounded knobs on a Worley lattice, parted by grooves."""
    off = Vector((seed * 5.3, seed * 2.1, seed * 7.7))

    def f(p):
        d, _ = noise.voronoi(p / cell + off, distance_metric="DISTANCE", exponent=2.5)
        k = max(0.0, 1.0 - d[0] / 0.9) ** 0.45 * smoothstep(0.0, 0.25, d[1] - d[0])
        return 1.0 + height * (k - 0.5)

    return f


def spider_leg(mats, name, a_deg, seed):
    """A spider's leg gripping the bell: the femur arches up from the hub to a high, swollen knee out
    over the bell's rim, the leg bends there and a long tibia, bowed a little outwards, comes down to
    plant its tip on the ground beyond the rim.  Thick to the end (the sprite's legs do not taper like
    tentacles), all of it knobbly.  Seen from the south the far (northern) legs would rise above the
    sprite's outline, so their knees sit lower and their feet closer."""
    a = math.radians(a_deg)
    d = Vector((math.cos(a), math.sin(a), 0.0))
    o = Vector((SPIDER_AXIS[0], SPIDER_AXIS[1], 0.0))
    br = bell_r(a_deg)
    north = max(0.0, math.sin(a))
    rf = min(2.88, br + 0.42) - 0.5 * north  # feet just outside the bell's rim
    rk = rf - 0.62  # the knee high above the rim
    zk = SPIDER_KNEE_Z - 0.6 * north
    h0 = SPIDER_HUB_Z - 0.08

    def P(r, z):
        return o + d * r + Vector((0.0, 0.0, z))

    # femur arching up to the knee, a tight bend, a steep tibia bowed a little outwards
    pts = [P(0.36, h0), P(0.36 + 0.5 * (rk - 0.36), h0 + 0.5 * (zk - h0) + 0.13), P(rk - 0.1, zk + 0.02), P(rk + 0.04, zk + 0.01),
           P(rk + 0.16, zk - 0.14), P(rk + 0.5 * (rf - rk) + 0.08, zk * 0.52), P(rk + 0.86 * (rf - rk) + 0.03, zk * 0.16),
           P(rf, 0.07)]
    lens = [(b - c).length for b, c in zip(pts[1:], pts[:-1])]
    fk = sum(lens[:3]) / sum(lens)

    def radius(f):  # a swollen knee, a slight taper to the foot
        return 1.0 + 0.16 * math.exp(-((f - fk) / 0.05) ** 2) - 0.12 * smoothstep(fk, 1.0, f)

    return rope_tube(mats, name, pts, 0.21, "M_Colony.knob", radius_fn=radius, sides=12, step=0.065,
                     surface_fn=knobs(seed=seed))


def spider_materials():
    col = (0.97, 0.85, 0.47)
    team = dict(ao=0.7, ao_dark=0.3, ao_gamma=1.4, crevice=0.07, crevice_dark=0.45, grain=0.05, foot=0.4,
                foot_dark=0.55, sky=0.3)
    m = {}
    m["M_Colony"] = ca_material("M_Colony", col, tint=True, roughness=0.38, variation=0.08, cell_scale=8.0, bump=0.3,
                                coat=0.3, shading=team)
    # knobbly skin: rounded nodules (the chitin Voronoi plates, ~0.07 cells) over the geometric knobs
    m["M_Colony.knob"] = ca_material("M_Colony.knob", col, tint=True, roughness=0.42, variation=0.12, cell_scale=15.0,
                                     bump=0.85, coat=0.25, shading=team)
    m["M_Colony.tower"] = darken(ca_material("M_Colony.tower", col, tint=True, roughness=0.45, variation=0.12,
                                             cell_scale=13.0, bump=0.65, coat=0.2, shading=team), 0.74)
    m["M_Colony.dark"] = darken(ca_material("M_Colony.dark", col, tint=True, roughness=0.4, variation=0.06, bump=0.2,
                                            coat=0.3, shading=dict(team, foot=0.0)), 0.42)
    m["M_ChromeA"] = ca_chrome("M_ChromeA", shading=dict(ao=0.9, ao_dark=0.35, ao_gamma=1.2, crevice=0.08,
                                                          crevice_dark=0.6, foot=0.0, sky=0.0))
    m["M_GunA"] = ca_material("M_GunA", (0.42, 0.41, 0.38), kind="glossy", roughness=0.3, metallic=0.3, coat=0.5,
                              shading=dict(ao=0.3, ao_dark=0.45, crevice=0.05, crevice_dark=0.55, foot=0.0, sky=0.25))
    return m


def spider_turret(name, mats, pivot):
    """Octagonal team-coloured drum (turret sprite: ~1.25 cells across, flat sides facing the axes)
    with a bevelled top and a closed hatch lid; a mantlet in front carries a long sniper barrel with a
    shroud, a muzzle brake and a scope.  Barrel tip 1.36 from the yaw axis."""
    p = Vector(pivot)
    g = SPIDER_GUN_Z
    r8 = (0, 0, math.radians(22.5))
    fixed = [_cyl(mats, p + Vector((0, 0, 0.045)), 0.5, 0.09, "M_Colony.dark", verts=8, rot=r8),
             _cyl(mats, p + Vector((0, 0, 0.26)), 0.6, 0.34, "M_Colony", verts=8, rot=r8),
             _cone(mats, p + Vector((0, 0, 0.49)), 0.6, 0.42, 0.12, "M_Colony", rot=r8, verts=8, smooth=False),
             _cyl(mats, p + Vector((0, 0.16, 0.56)), 0.17, 0.035, "M_Colony.dark", verts=16),
             _cyl(mats, p + Vector((0, 0.16, 0.585)), 0.15, 0.03, "M_Colony", verts=16),
             _box(mats, p + Vector((0, 0.16, 0.61)), (0.18, 0.04, 0.03), "M_GunA")]
    for k in range(8):  # bolts on the drum's upper edge
        a = math.radians(22.5 + 45 * k)
        fixed.append(_sphere(mats, p + Vector((0.52 * math.cos(a), 0.52 * math.sin(a), 0.43)), 0.03, "M_GunA",
                             segments=6, rings=4))
    rx = math.radians(90)
    moving = [_box(mats, p + Vector((0, -0.61, g)), (0.32, 0.18, 0.26), "M_GunA", bevel=0.04),
              _cyl(mats, p + Vector((0, -1.0, g)), 0.055, 0.74, "M_GunA", verts=12, rot=(rx, 0, 0)),
              _cyl(mats, p + Vector((0, -0.8, g)), 0.082, 0.32, "M_GunA", verts=12, rot=(rx, 0, 0)),
              _cyl(mats, p + Vector((0, -1.31, g)), 0.08, 0.12, "M_GunA", verts=12, rot=(rx, 0, 0)),
              _cyl(mats, p + Vector((0, -0.62, g + 0.2)), 0.05, 0.38, "M_GunA", verts=10, rot=(rx, 0, 0)),
              _box(mats, p + Vector((0, -0.62, g + 0.14)), (0.07, 0.12, 0.08), "M_GunA")]
    return _make_turret(name, mats, pivot, fixed, moving)


def build_spider_colony(quick=False):
    name = "colony_spider"
    salib.reset_scene(name)
    mats = colony_materials("Y")
    mats.update(spider_materials())
    ax, ay = SPIDER_AXIS

    def ribs(p):  # rounded ribs round the lower bell: the chrome reflections break into bands
        return 0.045 * max(0.0, math.sin(2.0 * math.pi * (p.z - 0.08) / 0.3)) ** 0.7 * (1.0 - smoothstep(0.9, 1.25, p.z))

    parts = [displaced_lathe("Bell", mats, "M_ChromeA", SPIDER_AXIS, SPIDER_BELL, scale=SPIDER_BELL_SCALE,
                             rot=SPIDER_BELL_ROT, segments=80, step=0.055, disp=ribs, seam_deg=45.0)]
    # hub: chrome collar, knobbly team ring, a dark slot with a chrome bar, a crown of knobs and spikes
    hz = SPIDER_HUB_Z
    parts.append(_cyl(mats, (ax, ay, hz - 0.18), 0.52, 0.36, "M_ChromeA", verts=32))
    parts.append(_torus(mats, (ax, ay, hz + 0.03), 0.47, 0.15, "M_Colony.knob", segs=(40, 10)))
    parts.append(_cyl(mats, (ax, ay, hz + 0.0), 0.33, 0.1, "M_Black", verts=24))
    parts.append(_box(mats, (ax, ay, hz + 0.06), (0.66, 0.1, 0.08), "M_ChromeA", rot=(0, 0, math.radians(-45)), bevel=0.02))
    for i, a in enumerate(SPIDER_LEG_ANGLES):
        ar = math.radians(a)
        c = (ax + 0.58 * math.cos(ar), ay + 0.58 * math.sin(ar), hz + 0.1)
        parts.append(_sphere(mats, c, 0.17, "M_Colony.knob", segments=12, rings=8))
        parts.append(_spike(mats, (c[0], c[1], c[2] + 0.1), (0.35 * math.cos(ar), 0.35 * math.sin(ar), 1.0), 0.26,
                            r1=0.07, mat="M_Colony.knob", verts=8))
    for i, a in enumerate(SPIDER_LEG_ANGLES):
        parts.append(spider_leg(mats, f"Leg{i}", a, seed=i + 1))
    # knobbly team-coloured towers with a rim and a foot ring
    for (x, y), top in SPIDER_TOWERS:
        parts.append(_cyl(mats, (x, y, top / 2), 0.42, top, "M_Colony.tower", verts=40))
        parts.append(_torus(mats, (x, y, top - 0.04), 0.4, 0.055, "M_Colony.tower", segs=(40, 8)))
        parts.append(_torus(mats, (x, y, 0.06), 0.43, 0.08, "M_Colony.tower", segs=(40, 8)))
    body = join_into(parts, "ColonyBody")
    turrets, barrels_all = [], []
    for i, ((x, y), top) in enumerate(SPIDER_TOWERS):
        t, bs = spider_turret(f"Turret_{i + 1}", mats, (x, y, top))
        _attach(t, body)
        turrets.append(t)
        barrels_all.append(bs)
    return ca_finish_colony(name, body, turrets, barrels_all, 9.5, 1.3, quick)
