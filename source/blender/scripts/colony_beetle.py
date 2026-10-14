"""Beetle colony: a dome of curved shell slats with spikes and a cannon on the cap.

Built by build_colony.py (usage in its docstring); shared helpers in colony_common.py.
"""
from colony_common import *  # noqa: F401,F403


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
