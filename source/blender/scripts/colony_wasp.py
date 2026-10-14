"""Wasp colony: an organic paper comb - thick, rounded, slightly irregular hexagonal cells with curled
larvae inside - over a dark fibrous base, with the big tilted panelled slab and a gatling turret.

Built by build_colony.py (usage in its docstring); shared helpers in colony_common.py and the crew-A
helpers in colony_ant.py (baked shading, tubes, packed-UV finish).

Fifth iteration (colony crew A, 2026-10-14; Mike: "the buildings are not up to par with the original
vision").  Kept from the previous crew (fitted to the sprite, u = X, v = -(0.866 Y + 0.5 Z)): the cell
top centres, sizes and heights (stepped: the back row tallest), the comb block under them, the dark
base in the south-west, the slab (centre/angle/tilt fitted to three sprite corners) and the turret
on the big west cell (OpenSA offset).  New:
  * every cell is a paper cell, not a prism: a wall swept round a rounded, slightly irregular hexagon,
    with a rounded rim, a floor, and a segmented larva curled on it (the sprite's swirls); the big
    west cell is capped (the turret sits on its lid);
  * a paper material: layered shade bands (real wasp paper is chewed wood laid in bands), fibres and
    grain in the bump, deep occlusion inside the cells and between them, baked into the colour map;
  * the slab is a chunky stack of bevelled paper plates; the base is dark old fibre, not rock;
  * the gatling has six barrels round an axle, clamp rings, a ribbed housing and an ammo drum.
"""
from colony_common import *  # noqa: F401,F403
from colony_ant import (_m, _mesh_object, _remap, ca_bake_shading, ca_finish_colony, ca_material, ensure_uv,
                        rope_tube, smoothstep)


# ---------------------------------------------------------------------------------------------
# paper
# ---------------------------------------------------------------------------------------------
def ca_paper(mat, bands=7.0, band_amp=0.28, fibre=0.45, grain=0.22):
    """Wasp paper: wavy horizontal bands of slightly different shade (layers of chewed fibre),
    stretched fibre streaks and a fine grain in the bump."""
    nt = mat.node_tree
    coord = _coord(nt)
    w = nt.nodes.new("ShaderNodeTexWave")
    w.wave_type = "BANDS"
    w.bands_direction = "Z"
    w.wave_profile = "SAW"
    w.inputs["Scale"].default_value = bands
    w.inputs["Distortion"].default_value = 5.0
    w.inputs["Detail"].default_value = 2.0
    nt.links.new(coord, w.inputs["Vector"])
    shade = _remap(nt, w.outputs["Fac"], 0.0, 1.0, 1.0 - band_amp, 1.0)
    p = _principled(mat)
    src = p.inputs["Base Color"].links[0].from_socket
    nt.links.new(salib._mix_rgb(nt, "MULTIPLY", src, shade, 1.0), p.inputs["Base Color"])
    # fibres: noise squashed along z (long streaks round the walls)
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0, 1.0, 7.0)
    nt.links.new(coord, mp.inputs["Vector"])
    fn = nt.nodes.new("ShaderNodeTexNoise")
    fn.inputs["Scale"].default_value = 14.0
    fn.inputs["Detail"].default_value = 4.0
    nt.links.new(mp.outputs["Vector"], fn.inputs["Vector"])
    add_height(mat, fn.outputs["Factor"], fibre)
    gn = salib._noise(nt, coord, 90.0, detail=2.0, roughness=0.6)
    add_height(mat, gn.outputs["Factor"], grain)
    return mat


def wasp_materials():
    col = (0.97, 0.85, 0.47)
    team = dict(ao=0.75, ao_dark=0.26, ao_gamma=1.4, crevice=0.09, crevice_dark=0.45, grain=0.08, grain_scale=35.0,
                foot=0.4, foot_dark=0.55, sky=0.3)
    m = {}
    m["M_Colony"] = ca_paper(ca_material("M_Colony", col, tint=True, roughness=0.55, variation=0.1, cell_scale=6.0,
                                         bump=0.25, coat=0.1, shading=team))
    m["M_Colony.egg"] = ca_material("M_Colony.egg", col, tint=True, roughness=0.32, variation=0.08, cell_scale=10.0,
                                    bump=0.25, coat=0.45, shading=dict(team, ao=0.45, foot=0.0))
    m["M_Colony.slab"] = ca_paper(ca_material("M_Colony.slab", col, tint=True, roughness=0.5, variation=0.1,
                                              cell_scale=5.0, bump=0.3, coat=0.15, shading=team),
                                  bands=4.0, band_amp=0.1, fibre=0.4)
    m["M_Colony.dark"] = darken(ca_material("M_Colony.dark", col, tint=True, roughness=0.5, variation=0.08, bump=0.2,
                                            coat=0.2, shading=dict(team, foot=0.0)), 0.42)
    m["M_Fibre"] = ca_paper(ca_material("M_Fibre", (0.2, 0.16, 0.12), kind="earth", roughness=0.9, variation=0.4, bump=0.6,
                                        coat=0.0, shading=dict(ao=0.8, ao_dark=0.3, crevice=0.1, crevice_dark=0.5, foot=0.3,
                                                               foot_dark=0.6, sky=0.3)),
                            bands=9.0, band_amp=0.3, fibre=1.0)
    m["M_GunA"] = ca_material("M_GunA", (0.42, 0.41, 0.38), kind="glossy", roughness=0.3, metallic=0.3, coat=0.5,
                              shading=dict(ao=0.3, ao_dark=0.45, crevice=0.05, crevice_dark=0.55, foot=0.0, sky=0.25))
    m["M_GunB"] = ca_material("M_GunB", (0.5, 0.47, 0.33), kind="glossy", roughness=0.32, metallic=0.4, coat=0.5,
                              shading=dict(ao=0.3, ao_dark=0.45, crevice=0.05, crevice_dark=0.55, foot=0.0, sky=0.25))
    return m


# ---------------------------------------------------------------------------------------------
# cells
# ---------------------------------------------------------------------------------------------
def rounded_hexagon(cx, cy, r, fillet=0.22, per_corner=5, per_edge=3, jitter=0.0, seed=0, rot=0.0):
    """Closed path round a hexagon of circumradius r with filleted corners; radial jitter makes it a
    little irregular (hand-made paper).  Returns [(x, y, nx, ny)] (point, outward normal)."""
    rnd = random.Random(seed)
    jit = [1.0 + rnd.uniform(-jitter, jitter) for _ in range(6)]
    pts = []
    for k in range(6):
        a0 = math.radians(rot + 60 * k)
        a1 = math.radians(rot + 60 * (k + 1))
        c0 = Vector((math.cos(a0), math.sin(a0))) * r * jit[k]
        c1 = Vector((math.cos(a1), math.sin(a1))) * r * jit[(k + 1) % 6]
        e = c1 - c0
        for j in range(per_edge):  # straight part of the edge between the fillets
            t = fillet + (1 - 2 * fillet) * j / per_edge
            pts.append(c0 + e * t)
        # fillet round the corner c1 (quadratic Bezier from the edge end to the next edge start)
        c2 = Vector((math.cos(math.radians(rot + 60 * (k + 2))), math.sin(math.radians(rot + 60 * (k + 2))))) * r * jit[(k + 2) % 6]
        p0, p2 = c0 + e * (1 - fillet), c1 + (c2 - c1) * fillet
        for j in range(per_corner):
            t = j / per_corner
            pts.append(p0 * (1 - t) ** 2 + c1 * 2 * t * (1 - t) + p2 * t * t)
    n = len(pts)
    out = []
    for i, q in enumerate(pts):
        tng = (pts[(i + 1) % n] - pts[i - 1]).normalized()
        nrm = Vector((tng.y, -tng.x))  # counter-clockwise path -> outward normal on the right
        out.append((cx + q.x, cy + q.y, nrm.x, nrm.y))
    return out


def paper_cell(mats, name, cx, cy, r, h, wall=0.16, depth=0.36, seed=0, mat="M_Colony", floor_mat=None):
    """Hexagonal paper cell: the wall's cross-section (outer face, a rounded rim, inner face, floor)
    swept round rounded_hexagon(); one object, UVs = (path length, profile length)."""
    path = rounded_hexagon(cx, cy, r, jitter=0.035, seed=seed)
    t = wall
    rim_z = h - t / 2
    # outer face bowed out a little (paper cells are barrel-shaped), then the rounded rim
    prof = [(0.0, 0.0), (-0.02, rim_z * 0.3), (-0.035, rim_z * 0.6), (-0.02, rim_z * 0.85), (0.0, rim_z)]
    for k in range(1, 6):  # the rounded rim
        a = math.pi * k / 6
        prof.append((t / 2 - t / 2 * math.cos(a), rim_z + t / 2 * math.sin(a)))
    prof += [(t, rim_z), (t, h - depth), (t + 0.06, h - depth - 0.02)]
    m = len(prof)
    verts, faces, uvs = [], [], []
    plen = [0.0]
    for (a0, b0), (a1, b1) in zip(prof, prof[1:]):
        plen.append(plen[-1] + math.hypot(a1 - a0, b1 - b0))
    slen = [0.0]
    for p0, p1 in zip(path, path[1:] + path[:1]):
        slen.append(slen[-1] + math.hypot(p1[0] - p0[0], p1[1] - p0[1]))
    for x, y, nx, ny in path:
        for d, z in prof:
            verts.append(Vector((x - nx * d, y - ny * d, z)))
    n = len(path)
    for i in range(n):
        i2 = (i + 1) % n
        for j in range(m - 1):
            faces.append((i * m + j, i2 * m + j, i2 * m + j + 1, i * m + j + 1))
            uvs.append([(slen[i], plen[j]), (slen[i + 1], plen[j]), (slen[i + 1], plen[j + 1]), (slen[i], plen[j + 1])])
    # floor: a fan from the inner edge of the profile to the cell centre
    centre = len(verts)
    verts.append(Vector((cx, cy, h - depth - 0.04)))
    off = slen[-1] + 0.5
    for i in range(n):
        i2 = (i + 1) % n
        faces.append((i * m + m - 1, i2 * m + m - 1, centre))
        q0, q1 = verts[i * m + m - 1], verts[i2 * m + m - 1]
        uvs.append([(off + q0.x - cx, q0.y - cy), (off + q1.x - cx, q1.y - cy), (off, 0.0)])
    # winding: path counter-clockwise x profile up the outer face -> every face points out of the wall
    # (into the cell on the inner face, up on the floor); no normal recalculation needed (open mesh)
    return _mesh_object(name, verts, faces, mats[mat], uvs=uvs)


def larva(mats, name, cx, cy, z0, r_in, seed=0):
    """A grub curled on the cell floor (the sprite's swirl): a segmented tube along an inward spiral,
    fattest in the middle, the head end raised."""
    rnd = random.Random(seed)
    a0 = rnd.uniform(0, 2 * math.pi)
    rr = r_in * 0.5
    thick = r_in * 0.44
    pts = []
    for k in range(9):
        f = k / 8
        a = a0 + 1.55 * math.pi * f
        rad = rr * (1.0 - 0.45 * f)
        pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a), z0 + thick * 0.75 + 0.07 * f))

    def radius(f):  # tapering ends, nine segments
        return (0.55 + 0.45 * math.sin(math.pi * min(1.0, f * 1.15)) ** 0.6) * (1.0 + 0.09 * math.cos(2 * math.pi * 9 * f))

    return rope_tube(mats, name, pts, thick, "M_Colony.egg", radius_fn=radius, sides=10, step=0.045)


# ---------------------------------------------------------------------------------------------
# WASP
# ---------------------------------------------------------------------------------------------
# (x, y, circumradius, height, kind): top centres fitted to the sprite with v = -(0.866 y + 0.5 h)
WASP_CELLS = [((-0.77, 1.34), 0.5, 2.3, "egg"), ((0.15, 0.77), 0.47, 2.3, "egg"), ((0.97, 1.3), 0.5, 2.3, "egg"),
              ((-0.9, 0.33), 0.84, 2.0, "turret"), ((0.94, 0.38), 0.5, 1.9, "egg"), ((-2.02, 0.5), 0.42, 1.5, "egg"),
              ((0.08, -0.26), 0.47, 1.75, "egg"), ((-0.6, -1.07), 0.4, 1.65, "egg"), ((-1.49, -1.39), 0.5, 1.9, "egg"),
              ((-0.55, -1.96), 0.4, 0.5, "dark")]
WASP_GUN_Z = 0.5  # gun axis above the turret pivot -> colonies.ron height 2.59 (pivot 2.09)


def wasp_turret(name, mats, pivot):
    """Dark disc base with a gatling (wasp turret sprite): six barrels round an axle with clamp rings,
    a ribbed housing and an ammo drum.  Muzzles 1.2 from the yaw axis."""
    p = Vector(pivot)
    g = WASP_GUN_Z
    rx = math.radians(90)
    fixed = [_cyl(mats, p + Vector((0, 0, 0.1)), 0.44, 0.2, "M_Iron", verts=32),
             _torus(mats, p + Vector((0, 0, 0.2)), 0.42, 0.045, "M_GunB", segs=(32, 8)),
             _cyl(mats, p + Vector((0, 0, 0.33)), 0.17, 0.26, "M_Iron", verts=16)]
    moving = [_cyl(mats, p + Vector((0, -0.2, g)), 0.17, 0.62, "M_GunB", verts=20, rot=(rx, 0, 0)),
              _box(mats, p + Vector((0, 0.24, g)), (0.36, 0.34, 0.32), "M_GunA", bevel=0.05),
              _cyl(mats, p + Vector((0.27, 0.2, g)), 0.13, 0.16, "M_GunB", verts=16, rot=(0, rx, 0))]
    for y in (-0.06, -0.22, -0.38):  # cooling ribs on the housing
        moving.append(_torus(mats, p + Vector((0, y, g)), 0.17, 0.03, "M_GunA", rot=(rx, 0, 0), segs=(20, 6)))
    for y in (-0.6, -1.08):  # barrel clamps
        moving.append(_cyl(mats, p + Vector((0, y, g)), 0.13, 0.05, "M_GunA", verts=16, rot=(rx, 0, 0)))
    moving.append(_cyl(mats, p + Vector((0, -0.8, g)), 0.035, 0.75, "M_GunA", verts=8, rot=(rx, 0, 0)))  # axle
    for i in range(6):
        a = i / 6 * 2 * math.pi
        moving.append(_cyl(mats, p + Vector((0.085 * math.cos(a), -0.86, g + 0.085 * math.sin(a))), 0.036, 0.68,
                           "M_GunA", verts=8, rot=(rx, 0, 0)))
    return _make_turret(name, mats, pivot, fixed, moving)


def build_wasp_colony(quick=False):
    name = "colony_wasp"
    salib.reset_scene(name)
    mats = colony_materials("Y")
    mats.update(wasp_materials())
    # dark fibrous base, visible in the south-west under the cells (sprite)
    parts = [ensure_uv(mound("Base", mats, "M_Fibre", (-1.3, -0.7), (0.88, 1.3), 0.75, noise=0.22, noise_scale=0.45,
                             seed=9, segments=48, rings=18))]
    rnd = random.Random(11)
    for i in range(9):
        a = rnd.uniform(math.radians(170), math.radians(290))
        r = rnd.uniform(0.6, 0.9)
        x, y = -1.35 + r * math.cos(a), -0.7 + r * 1.2 * math.sin(a)
        parts.append(_sphere(mats, (x, y, 0.1), rnd.uniform(0.2, 0.32), "M_Fibre", ico=2, jitter=0.03, seed=i,
                             scale=(rnd.uniform(0.9, 1.3), rnd.uniform(0.9, 1.3), rnd.uniform(0.6, 0.9)),
                             rot=(0, 0, rnd.uniform(0, 3))))
    turret_pivot = None
    # the comb: one paper block under the main cells (the sprite's cells share walls), its top 0.3
    # below the lowest of them so every rim still stands out
    comb = [c for c in WASP_CELLS if c[3] != "dark" and c[0] != (-1.49, -1.39)]
    low = min(ch for _, _, ch, _ in comb) - 0.3
    pts = []
    for (x, y), r, h, kind in comb:
        for k in range(6):
            a = k * math.pi / 3
            for z in (0.0, low):
                pts.append((x + r * 0.97 * math.cos(a), y + r * 0.97 * math.sin(a), z))
    parts.append(ensure_uv(convex_part(mats, pts, "M_Colony", name="Comb", bevel=0.08)))
    for i, ((x, y), r, h, kind) in enumerate(WASP_CELLS):  # r = the rim's circumradius (the sprite's hexagon)
        r *= 1.1  # the filleted corners make a cell look smaller than a sharp hexagon: rims nearly touch
        wall = 0.18 if kind != "turret" else 0.22
        depth = 0.3 if kind == "egg" else (0.2 if kind == "turret" else 0.3)  # the larvae fill the cell tops
        parts.append(paper_cell(mats, f"Cell{i}", x, y, r, h, wall=wall, depth=depth, seed=20 + i))
        r_in = r * 0.87 - wall
        if kind == "egg":
            parts.append(larva(mats, f"Larva{i}", x, y, h - depth - 0.04, r_in, seed=40 + i))
        elif kind == "turret":
            # a capped cell: a low domed paper lid, the turret seat on top
            turret_pivot = (x, y, h + 0.09)
            parts.append(_sphere(mats, (x, y, h - depth), r_in + 0.02, "M_Colony.egg", scale=(1, 1, 0.34), segments=32,
                                 rings=12))
            parts.append(_cyl(mats, (x, y, h + 0.04), r * 0.52, 0.1, "M_Iron", verts=6))
        else:
            parts.append(_cyl(mats, (x, y, h - depth - 0.02), r_in + 0.02, 0.04, "M_Black", verts=6))
    # tilted panelled slab (long axis NE, high edge at the north-west, low edge at the south-east);
    # centre/angle/tilt/size fitted to the sprite's three visible corners (previous crew)
    sc_ = (0.75, -0.3, 1.0)
    ang, tilt = math.radians(50), math.radians(14)
    rot = (tilt, 0, ang)
    mrot = Matrix.Rotation(ang, 3, "Z") @ Matrix.Rotation(tilt, 3, "X")

    def on_slab(lx, ly, lz):
        q = mrot @ Vector((lx, ly, lz))
        return (sc_[0] + q.x, sc_[1] + q.y, sc_[2] + q.z)

    parts.append(_box(mats, sc_, (3.8, 2.0, 0.26), "M_Colony.slab", rot=rot, bevel=0.07))
    for lx in (-1.25, 0.0, 1.25):
        for ly in (-0.47, 0.47):
            parts.append(_box(mats, on_slab(lx, ly, 0.18), (1.06, 0.72, 0.13), "M_Colony.slab", rot=rot, bevel=0.045))
            parts.append(_box(mats, on_slab(lx, ly, 0.26), (0.8, 0.48, 0.06), "M_Colony.slab", rot=rot, bevel=0.025))
    parts.append(_box(mats, on_slab(0.0, -0.99, -0.02), (3.8, 0.16, 0.36), "M_Colony.dark", rot=rot, bevel=0.04))
    parts.append(_box(mats, (sc_[0] - 0.15, sc_[1] + 0.1, 0.4), (2.8, 1.1, 0.8), "M_Fibre", rot=(0, 0, ang), bevel=0.05))
    body = join_into(parts, "ColonyBody")
    t, bs = wasp_turret("Turret_1", mats, turret_pivot)
    _attach(t, body)
    return ca_finish_colony(name, body, [t], [bs], 10.0, 1.0, quick)
