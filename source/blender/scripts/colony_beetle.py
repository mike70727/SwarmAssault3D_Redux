"""Beetle colony: a bulky fortress of thick curved armour-shell plates round a domed cap, deep dark
slits, long spikes and thorns, the gunmetal cannon on the cap.

Built by build_colony.py (usage in its docstring); shared helpers in colony_common.py.

Colony crew B rebuild (2026-10-14, after Mike: "the buildings are not up to par with the original
vision").  References: the body sprite (reference/models/colony_beetle) and the original 3-D render
in loading screen 2 (blue colony, bottom).  The old model was a flat dome of thin even slats; the
original is a rounded, fairly tall dome of THICK shell plates cut by long pointed lens-shaped slits
(dark inside), a domed cap with an engraved medallion, many long spikes and short dark thorns.
 * `ShellPlate`: own generator - a thick curved shell lying on a superellipse dome profile (inner
   R 2.08 H 1.58 p 2.3; the 60-deg sprite's north silhouette still fits), a gentle bulge across,
   near-square rounded long edges (the slit walls show the thickness), flared feet on the south
   side, skewed boundaries; pointed lens slits of individual widths at each boundary (wide where the
   sprite shows its dark gaps); low-frequency hammered noise; engraving (border, bands, spine) from
   a per-vertex (t, s, flag) attribute.
 * a dark granite core well inside the plates, the cap (r 0.95, base 1.48, top 1.84) with a thick rim
   and an incised medallion; the turret pivot at 1.83 projects to the sprite point OpenSA gives
   (screen 0, -0.9 vs -0.86); 26 spikes, 33 thorns.
 * baked shading (`bake_shading`): far + near ambient occlusion, sky occlusion (sides darker than
   tops, undersides darkest), ground contact, bevel-edge highlights, mottling and grain are multiplied
   into the base colour of every material.  salib's bake only whitens the TeamTint node, so all of it
   ends up in the colour texture and the runtime team tint keeps its depth; the bevel normal also goes
   into the normal map.
"""
import math
import random

from mathutils import Vector, noise

from colony_common import *  # noqa: F401,F403
from colony_common import _cyl, _sphere, _spike, _torus, _attach, _finish_colony, _make_turret  # noqa: F401

# ---------------------------------------------------------------------------------------------
# baked-shading material helpers (crew B; colony_common stays untouched)
# ---------------------------------------------------------------------------------------------


def _out(node, *names):
    for n in names:
        if n in node.outputs:
            return node.outputs[n]
    return node.outputs[0]


def _bsdf(mat):
    return next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def _mr(nt, value, a, b, lo, hi, smooth=False):
    """Map range [a, b] -> [lo, hi] (clamped)."""
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


def bake_shading(mat, ao_far=0.85, far_floor=0.1, far_gamma=1.5, ao_near=0.14, near_floor=0.5, down_floor=0.35,
                 ground_h=0.4, ground_floor=0.45, edge_gain=0.22, bevel_r=0.03, grain=0.1, grain_scale=55.0,
                 mottle=(0.74, 1.04), mottle_scale=3.5, base=0.92, extra=()):
    """Multiply view-independent shading into the material's base colour and put a bevel normal
    under its bump: far/near ambient occlusion, sky occlusion (sides darker than tops, undersides
    darkest), ground contact, bevelled-edge highlights, mottling and grain.  `extra` = further factor
    sockets (grooves...).  Returns the material."""
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
    if down_floor < 1.0:  # sky occlusion: sides see half the sky, faces turned down see the ground
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(geo.outputs["Normal"], sep.inputs[0])
        facs.append(_mr(nt, sep.outputs["Z"], -0.7, 0.85, down_floor, 1.0, smooth=True))
    if ground_floor < 1.0:  # contact darkening at the foot (there is no ground in the bake)
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


def grooves(mat, scale=2.2, width=0.03, keep=0.5, depth=1.0, dark=0.4, warp=0.3, seed=0.0):
    """Sparse incised grooves (distorted Voronoi cell edges broken up by a noise mask): cut into the
    bump and returned as a colour factor socket (1 = no groove, `dark` in the groove)."""
    nt = mat.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    off = nt.nodes.new("ShaderNodeVectorMath")
    off.operation = "ADD"
    nt.links.new(tc.outputs["Object"], off.inputs[0])
    off.inputs[1].default_value = (seed, seed * 0.7, seed * 1.3)
    wn = nt.nodes.new("ShaderNodeTexNoise")
    wn.inputs["Scale"].default_value = 1.1
    wn.inputs["Detail"].default_value = 2.0
    nt.links.new(off.outputs[0], wn.inputs["Vector"])
    sc = nt.nodes.new("ShaderNodeVectorMath")
    sc.operation = "SCALE"
    nt.links.new(_out(wn, "Color"), sc.inputs[0])
    sc.inputs["Scale"].default_value = warp
    wv = nt.nodes.new("ShaderNodeVectorMath")
    wv.operation = "ADD"
    nt.links.new(off.outputs[0], wv.inputs[0])
    nt.links.new(sc.outputs[0], wv.inputs[1])
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.feature = "DISTANCE_TO_EDGE"
    vor.inputs["Scale"].default_value = scale
    vor.inputs["Randomness"].default_value = 1.0
    nt.links.new(wv.outputs[0], vor.inputs["Vector"])
    line = _mr(nt, vor.outputs["Distance"], 0.0, width, 1.0, 0.0, smooth=True)
    mn = nt.nodes.new("ShaderNodeTexNoise")
    mn.inputs["Scale"].default_value = 1.7
    mn.inputs["Detail"].default_value = 1.0
    nt.links.new(off.outputs[0], mn.inputs["Vector"])
    mask = _mr(nt, _out(mn, "Factor", "Fac"), 1.0 - keep - 0.04, 1.0 - keep + 0.04, 0.0, 1.0)
    g = _mul(nt, line, mask)
    add_height(mat, g, -depth)
    return _mr(nt, g, 0.0, 1.0, 1.0, dark)


def plate_grooves(mat, border=0.76, bands=(0.3, 0.55), ws=0.055, wt=0.013, dark=0.28, depth=1.2):
    """Engraving of the shell plates from their (t, s, flag) point attribute `plate_ts` (written by
    ShellPlate.mesh): a border groove inset from both long edges, transverse bands, and a centre spine
    on plates flagged 2.  Cut into the bump; returns the colour factor socket."""
    nt = mat.node_tree
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_type = "GEOMETRY"
    at.attribute_name = "plate_ts"
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(_out(at, "Vector"), sep.inputs[0])
    t, s, flag = sep.outputs["X"], sep.outputs["Y"], sep.outputs["Z"]
    is_plate = _mr(nt, flag, 0.4, 0.6, 0.0, 1.0)
    spine = _mr(nt, flag, 1.4, 1.6, 0.0, 1.0)
    abs_s = salib._math(nt, "ABSOLUTE", s)
    g = _mr(nt, salib._math(nt, "ABSOLUTE", salib._math(nt, "SUBTRACT", abs_s, border)), 0.0, ws, 1.0, 0.0, smooth=True)
    inside = _mr(nt, abs_s, border - 0.03, border + 0.01, 1.0, 0.0)
    for b in bands:
        bt = _mr(nt, salib._math(nt, "ABSOLUTE", salib._math(nt, "SUBTRACT", t, b)), 0.0, wt, 1.0, 0.0, smooth=True)
        g = salib._math(nt, "MAXIMUM", g, _mul(nt, bt, inside))
    sp = _mul(nt, _mr(nt, abs_s, 0.0, ws * 0.8, 1.0, 0.0, smooth=True), spine)
    sp = _mul(nt, sp, _mr(nt, t, 0.06, 0.1, 0.0, 1.0))
    g = salib._math(nt, "MAXIMUM", g, sp)
    ends = _mul(nt, _mr(nt, t, 0.03, 0.06, 0.0, 1.0), _mr(nt, t, 0.86, 0.9, 1.0, 0.0))
    g = _mul(nt, _mul(nt, g, is_plate), ends)
    add_height(mat, g, -depth)
    return _mr(nt, g, 0.0, 1.0, 1.0, dark)


def medallion(mat, center=(0.0, 0.0), rings=(), arcs=(), spokes=(), dark=0.36, depth=1.4):
    """Incised medallion on a cap centred on `center` (object XY): rings (r, w), arcs (r, w, a0, a1 deg),
    spokes (angle deg, r0, r1, w).  Cut into the bump; returns the colour factor socket."""
    nt = mat.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    x = salib._math(nt, "SUBTRACT", sep.outputs["X"], center[0])
    y = salib._math(nt, "SUBTRACT", sep.outputs["Y"], center[1])
    r = salib._math(nt, "SQRT", salib._math(nt, "ADD", _mul(nt, x, x), _mul(nt, y, y)))
    ang = salib._math(nt, "ARCTAN2", y, x)  # radians, -pi..pi
    parts = []

    def ring_mask(r0, w):
        d = salib._math(nt, "ABSOLUTE", salib._math(nt, "SUBTRACT", r, r0))
        return _mr(nt, d, 0.0, w, 1.0, 0.0, smooth=True)

    for r0, w in rings:
        parts.append(ring_mask(r0, w))
    for r0, w, a0, a1 in arcs:
        lo, hi = math.radians(a0), math.radians(a1)
        win = _mul(nt, _mr(nt, ang, lo - 0.03, lo + 0.03, 0.0, 1.0), _mr(nt, ang, hi - 0.03, hi + 0.03, 1.0, 0.0))
        parts.append(_mul(nt, ring_mask(r0, w), win))
    for a, r0, r1, w in spokes:
        ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
        across = salib._math(nt, "ABSOLUTE", salib._math(nt, "SUBTRACT", _mul(nt, x, sa), _mul(nt, y, ca)))
        along = salib._math(nt, "ADD", _mul(nt, x, ca), _mul(nt, y, sa))
        m = _mr(nt, across, 0.0, w, 1.0, 0.0, smooth=True)
        m = _mul(nt, m, _mul(nt, _mr(nt, along, r0 - 0.02, r0 + 0.02, 0.0, 1.0), _mr(nt, along, r1 - 0.02, r1 + 0.02, 1.0, 0.0)))
        parts.append(m)
    g = parts[0]
    for q in parts[1:]:
        g = salib._math(nt, "MAXIMUM", g, q)
    add_height(mat, g, -depth)
    return _mr(nt, g, 0.0, 1.0, 1.0, dark)


def beetle_materials():
    mats = colony_materials("Y")
    col = (0.97, 0.85, 0.47)
    # armour shell plates: glossy chitin with broad hammered dents, sparse incised grooves
    shell = salib.material("M_Colony", col, roughness=0.38, kind="chitin", tint=True, variation=0.16, cell_scale=3.2,
                           bump=0.2, dirt=0.0, coat=0.35)
    g = plate_grooves(shell)
    g2 = grooves(shell, scale=1.6, width=0.022, keep=0.22, depth=0.6, dark=0.5, seed=1.7)  # a few stray scratches
    mats["M_Colony"] = bake_shading(shell, extra=[g, g2])
    cap = salib.material("M_Colony.cap", col, roughness=0.34, kind="chitin", tint=True, variation=0.12, cell_scale=4.0,
                         bump=0.3, dirt=0.0, coat=0.4)
    m = medallion(cap, center=(0.0, 0.0), rings=((0.62, 0.04), (0.45, 0.025)),
                  arcs=((0.8, 0.035, 112, 248), (0.8, 0.035, -68, 68)),
                  spokes=((90, 0.62, 0.95, 0.03), (-90, 0.62, 0.95, 0.03), (180, 0.62, 0.8, 0.03), (35, 0.8, 0.95, 0.025),
                          (-35, 0.8, 0.95, 0.025), (145, 0.8, 0.95, 0.025), (-145, 0.8, 0.95, 0.025)), dark=0.25, depth=1.8)
    mats["M_Colony.cap"] = bake_shading(cap, far_floor=0.2, near_floor=0.45, edge_gain=0.18, mottle=(0.8, 1.04), base=0.97,
                                        extra=[m])
    spike = darken(salib.material("M_Colony.spike", col, roughness=0.3, kind="chitin", tint=True, variation=0.1,
                                  cell_scale=12.0, bump=0.2, dirt=0.0, coat=0.5), 0.5)
    mats["M_Colony.spike"] = bake_shading(spike, ao_far=0.4, far_floor=0.35, ao_near=0.08, near_floor=0.6, down_floor=0.5,
                                          edge_gain=0.25, bevel_r=0.01, grain=0.04, ground_floor=0.7, mottle=(0.85, 1.02),
                                          base=1.0)
    thorn = darken(salib.material("M_Colony.thorn", col, roughness=0.3, kind="chitin", tint=True, variation=0.1,
                                  cell_scale=12.0, bump=0.2, dirt=0.0, coat=0.5), 0.25)
    mats["M_Colony.thorn"] = bake_shading(thorn, ao_far=0.3, far_floor=0.4, ao_near=0.0, down_floor=0.6, edge_gain=0.3,
                                          bevel_r=0.01, grain=0.03, ground_floor=0.8, mottle=None, base=1.0)
    rock = speckle(cobbles(salib.material("M_BeetleRock", (0.36, 0.33, 0.37), roughness=0.9, kind="stone", variation=0.5,
                                          dirt=0.0), scale=6.0, weight=1.4), scale=34.0, dark=0.45, light=1.4)
    mats["M_BeetleRock"] = bake_shading(rock, ao_far=0.7, far_floor=0.08, far_gamma=1.8, ao_near=0.12, near_floor=0.45,
                                        edge_gain=0.12, grain=0.0, mottle=(0.65, 1.1), base=1.0)
    metal = salib.material("M_BeetleGun", (0.46, 0.44, 0.4), roughness=0.34, metallic=0.2, kind="glossy")
    mats["M_BeetleGun"] = bake_shading(metal, ao_far=0.35, far_floor=0.3, ao_near=0.08, near_floor=0.55, down_floor=0.5,
                                       ground_floor=1.0, edge_gain=0.45, bevel_r=0.015, grain=0.05, grain_scale=30.0,
                                       mottle=(0.82, 1.05), base=1.0)
    dark = salib.material("M_BeetleGunDark", (0.22, 0.21, 0.2), roughness=0.4, metallic=0.2, kind="glossy")
    mats["M_BeetleGunDark"] = bake_shading(dark, ao_far=0.3, far_floor=0.35, ao_near=0.08, near_floor=0.55,
                                           down_floor=0.55, ground_floor=1.0, edge_gain=0.6, bevel_r=0.015, grain=0.05,
                                           mottle=(0.85, 1.05), base=1.0)
    return mats


# ---------------------------------------------------------------------------------------------
# shell plates
# ---------------------------------------------------------------------------------------------
DOME_R, DOME_H, DOME_P = 2.08, 1.58, 2.3   # inner dome surface (the plates lie on it): superellipse
CAP = (0.0, 0.0, 1.48, 0.95, 0.36)      # cap centre x, y, base z, radius, height (top 1.84)
PIVOT_Z = 1.83                            # turret yaw pivot: projects to OpenSA's screen point (0, -0.9)


def _gap(t, g):
    """Width (cells) of the slit at a plate boundary at profile parameter t: a hairline joint, opening
    into a pointed lens of width `gmax` between t0 and t1 (the long slits of the original render)."""
    gmax, t0, t1 = g
    u = (t - t0) / (t1 - t0)
    return 0.025 + (gmax * math.sin(math.pi * u) ** 0.9 if 0.0 < u < 1.0 else 0.0)


class ShellPlate:
    """One thick armour plate between boundary angles a0 < a1 (degrees, anticlockwise from east)."""

    def __init__(self, a0, a1, g0, g1, r_top=1.07, bulk=1.0, thick=0.16, bulge=0.13, shoulder=0.07, flare=0.0,
                 flare_w=0.3, lift=0.0, lean=0.0, spine=False, skew0=0.0, skew1=0.0, taper=0.15, seed=0):
        self.a0, self.a1 = math.radians(a0), math.radians(a1)
        self.taper = taper  # thinning towards the long edges (0 = slab edges as thick as the middle)
        self.k0, self.k1 = math.radians(skew0), math.radians(skew1)  # boundary curves: angle + skew * t
        self.g0, self.g1 = g0, g1
        self.thick, self.bulge, self.shoulder = thick, bulge, shoulder
        self.flag = 2.0 if spine else 1.0
        self.seed = seed
        # inner profile (r, z) from the foot (t = 0) to the top end (t = 1)
        th_top = math.acos(min(1.0, (r_top / (DOME_R * bulk)) ** (DOME_P / 2)))
        self.prof = []
        n = 40
        for k in range(n + 1):
            t = k / n
            th = th_top * t  # superellipse angle: t = 0 the foot, t = 1 the top end
            c, s = math.cos(th), math.sin(th)
            r = DOME_R * bulk * (c ** (2 / DOME_P))
            z = DOME_H * (s ** (2 / DOME_P)) + lift * t
            r += lean * z  # the plate leans out: its top end stands off the cap
            if flare > 0 and t < flare_w:  # skirt: the foot curls out along the ground
                f = (1 - t / flare_w) ** 2
                r += flare * f
                z = max(0.0, z - 0.25 * flare * f)
            self.prof.append((r, z))
        self.nprof = n

    def inner(self, t):
        """(r, z, nr, nz) of the inner profile at t (linear interpolation of the table)."""
        x = max(0.0, min(1.0, t)) * self.nprof
        i = min(self.nprof - 1, int(x))
        f = x - i
        (r0, z0), (r1, z1) = self.prof[i], self.prof[i + 1]
        r, z = r0 + (r1 - r0) * f, z0 + (z1 - z0) * f
        dr, dz = r1 - r0, z1 - z0
        ln = math.hypot(dr, dz) or 1.0
        return r, z, dz / ln, -dr / ln

    def span(self, t):
        r = self.inner(t)[0]
        aL = self.a0 + self.k0 * t + _gap(t, self.g0) / (2 * r)
        aR = self.a1 + self.k1 * t - _gap(t, self.g1) / (2 * r)
        return aL, aR

    def offsets(self, t, s):
        """(outer, inner) offsets along the normal at (t, s): thick in the middle, thinner at the
        long edges, a fat shoulder near the top, the top end rounded off."""
        sh = 1.0 + self.shoulder / max(0.01, self.thick) * math.exp(-((t - 0.8) / 0.11) ** 2)
        end = 1.0
        if t > 0.9:
            end = max(0.4, math.sqrt(max(0.0, 1.0 - ((t - 0.9) / 0.1) ** 2)))
        across = max(0.0, 1.0 - s * s)
        th = self.thick * sh * (1.0 - self.taper * s * s) * end
        bu = self.bulge * (across ** 0.75) * (0.75 + 0.25 * math.sin(math.pi * min(1.0, t * 1.1))) * end
        # a curved shell: the outer face bulges by `bu`, the inner face follows it by 45 %
        return th + bu, 0.45 * bu

    def point(self, t, s, side=1.0, extra=0.0):
        """World point at (t, s) on the outer (side 1) or inner (side 0) surface."""
        r, z, nr, nz = self.inner(t)
        aL, aR = self.span(t)
        a = 0.5 * (aL + aR) + s * 0.5 * (aR - aL)
        out, inn = self.offsets(t, s)
        e = (out if side else inn) + extra
        if side:
            e += 0.028 * noise.noise(Vector((r * math.cos(a), r * math.sin(a), z)) * 1.7 + Vector((self.seed, 0, 0)))
        ca, sa = math.cos(a), math.sin(a)
        return Vector(((r + nr * e) * ca, (r + nr * e) * sa, max(0.0, z + nz * e))), Vector((nr * ca, nr * sa, nz))

    def mesh(self, mats, name, mat, n_t=26, n_s=11):
        # 65 % linear + 35 % cosine spacing: a little denser at the foot and the rounded top end
        ts = [0.65 * u + 0.35 * (0.5 - 0.5 * math.cos(math.pi * u)) for u in (k / (n_t - 1) for k in range(n_t))]
        ss = [math.sin(0.5 * math.pi * (-1 + 2 * j / (n_s - 1))) for j in range(n_s)]  # denser near the edges
        verts, faces, ts_attr = [], [], []
        M = 2 * n_s + 2
        for t in ts:
            ts_attr += [(t, s, self.flag) for s in ss] + [(t, 1.05, self.flag)] + \
                       [(t, s, self.flag) for s in reversed(ss)] + [(t, -1.05, self.flag)]
            ring = []
            for s in ss:
                ring.append(self.point(t, s, 1)[0])
            # rounded long edge (right): half-way between the surfaces, pushed out sideways
            po, _ = self.point(t, 1.0, 1)
            pi_, _ = self.point(t, 1.0, 0)
            aL, aR = self.span(t)
            side = Vector((-math.sin(aR), math.cos(aR), 0.0)) * 0.035
            ring.append((po + pi_) * 0.5 + side)
            for s in reversed(ss):
                ring.append(self.point(t, s, 0)[0])
            po, _ = self.point(t, -1.0, 1)
            pi_, _ = self.point(t, -1.0, 0)
            side = Vector((math.sin(aL), -math.cos(aL), 0.0)) * 0.035
            ring.append((po + pi_) * 0.5 + side)
            verts += [tuple(v) for v in ring]
        for k in range(n_t - 1):
            for i in range(M):
                a, b = k * M + i, k * M + (i + 1) % M
                faces.append((a, b, b + M, a + M))
        for k, flip in ((0, True), (n_t - 1, False)):  # foot and top end: zip the outer to the inner surface
            base = k * M
            for j in range(n_s - 1):
                o0, o1 = base + j, base + j + 1
                i0, i1 = base + n_s + 1 + (n_s - 1 - j), base + n_s + 1 + (n_s - 2 - j)
                f = (o0, o1, i1, i0)
                faces.append(tuple(reversed(f)) if flip else f)
            tri_r = (base + n_s - 1, base + n_s, base + n_s + 1)          # outer right, edge R, inner right
            tri_l = (base + M - 1, base, base + 2 * n_s)                   # edge L, outer left, inner left
            faces.append(tuple(reversed(tri_r)) if flip else tri_r)
            faces.append(tuple(reversed(tri_l)) if flip else tri_l)
        me = bpy.data.meshes.new(name)
        me.from_pydata(verts, [], faces)
        me.update()
        # (t, s, flag) per vertex: the material engraves borders/bands/spine from it (plate_grooves);
        # a generic attribute, not a UV or colour layer, so the glTF export leaves it out
        at = me.attributes.new("plate_ts", "FLOAT_VECTOR", "POINT")
        at.data.foreach_set("vector", [c for v in ts_attr for c in v])
        o = bpy.data.objects.new(name, me)
        salib.link(o)
        salib.select_only([o])
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode="OBJECT")
        o.data.materials.append(mats[mat])
        for f in o.data.polygons:
            f.use_smooth = True
        try:
            bpy.ops.object.shade_smooth_by_angle(angle=math.radians(50))
        except Exception:
            pass
        return o


# boundaries between the plates: angle (deg, anticlockwise from east), slit (gmax, t0, t1) = a pointed
# lens of width gmax between profile parameters t0..t1, skew (deg the boundary turns by the top).  The
# wide slits sit where the sprite shows its dark gaps (E, NE and W round the cap, SW rock, S-SE).
BOUNDS = [(-8, (0.4, 0.08, 0.86), 6), (24, (0.4, 0.2, 0.97), -5), (58, (0.18, 0.1, 0.85), 4), (92, (0.24, 0.12, 0.92), -3),
          (126, (0.18, 0.08, 0.85), 5), (160, (0.4, 0.2, 0.97), -4), (196, (0.28, 0.06, 0.84), 6), (232, (0.44, 0.05, 0.8), -6),
          (258, (0.16, 0.1, 0.82), 3), (283, (0.32, 0.06, 0.82), -4), (318, (0.22, 0.08, 0.84), 5)]
# per plate (between BOUNDS[i] and BOUNDS[i+1]): shape and spikes [(t, s, length, tilt above horizontal deg)]
PLATES = [
    dict(bulk=1.06, thick=0.19, bulge=0.045, shoulder=0.03, lean=0.02, r_top=1.02, lift=0.02,
         spikes=[(0.62, -0.1, 0.85, 14), (0.4, 0.35, 0.7, 6), (0.78, 0.45, 0.75, 30)]),                              # E
    dict(bulk=1.0, thick=0.18, bulge=0.038, shoulder=0.035, lean=0.04, r_top=1.06, lift=0.04,
         spikes=[(0.72, 0.0, 0.95, 32), (0.5, 0.45, 0.8, 22), (0.4, -0.4, 0.7, 14)]),                                # NE
    dict(bulk=1.02, thick=0.19, bulge=0.045, shoulder=0.04, lean=0.05, r_top=1.08, lift=0.05, spine=True,
         spikes=[(0.74, -0.25, 1.0, 42), (0.7, 0.35, 0.95, 38), (0.45, 0.0, 0.8, 20)]),                              # N
    dict(bulk=1.0, thick=0.17, bulge=0.038, shoulder=0.035, lean=0.04, r_top=1.05, lift=0.03,
         spikes=[(0.72, 0.1, 0.95, 38), (0.42, -0.3, 0.75, 16)]),                                                    # NNW
    dict(bulk=1.0, thick=0.18, bulge=0.038, shoulder=0.035, lean=0.05, r_top=1.07, lift=0.04,
         spikes=[(0.7, -0.2, 0.92, 30), (0.5, 0.4, 0.8, 22), (0.35, -0.35, 0.7, 10)]),                               # NW
    dict(bulk=1.04, thick=0.19, bulge=0.045, shoulder=0.03, lean=0.02, r_top=1.03, lift=0.02, spine=True,
         spikes=[(0.6, 0.0, 0.9, 18), (0.3, -0.45, 0.85, 4), (0.78, 0.4, 0.7, 34)]),                                 # W
    dict(bulk=1.0, thick=0.18, bulge=0.038, shoulder=0.03, flare=0.06, r_top=1.02, lift=0.02,
         spikes=[(0.5, 0.2, 0.75, 12), (0.3, -0.3, 0.6, 4)]),                                                        # WSW
    dict(bulk=0.99, thick=0.17, bulge=0.038, shoulder=0.03, flare=0.14, r_top=1.0, lift=0.02,
         spikes=[(0.45, 0.0, 0.6, 6)]),                                                                              # SW
    dict(bulk=1.02, thick=0.2, bulge=0.045, shoulder=0.03, flare=0.32, flare_w=0.3, r_top=1.0, lift=0.02, spine=True,
         spikes=[(0.42, 0.25, 0.55, 2), (0.6, -0.3, 0.5, 10)]),                                                      # S skirt
    dict(bulk=1.0, thick=0.18, bulge=0.038, shoulder=0.03, flare=0.16, r_top=1.0, lift=0.02,
         spikes=[(0.5, -0.1, 0.62, 6), (0.7, 0.3, 0.55, 20)]),                                                       # SE
    dict(bulk=1.02, thick=0.18, bulge=0.045, shoulder=0.03, flare=0.2, r_top=1.02, lift=0.02,
         spikes=[(0.55, 0.15, 0.72, 8), (0.35, -0.35, 0.6, 2)]),                                                     # ESE (hook)
]


def drop_faces(o, pred):
    """Delete the faces of a part for which pred(face) is true (hidden faces: they would only take
    texture space in the smart-UV bake)."""
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


def _on_ground_bottom(f):
    return f.calc_center_median().z < 0.01 and f.normal.z < -0.5


def _thorn(mats, plate, t, s, length=0.22, r=0.065, rnd=None):
    """A short dark thorn growing out of the plate surface, pointing down the slope and out."""
    p, n = plate.point(t, s, 1, extra=-0.02)
    p2, _ = plate.point(t - 0.05, s, 1, extra=-0.02)
    down = (p2 - p).normalized()
    d = (down * 0.75 + n * 0.65).normalized()
    return drop_faces(_spike(mats, tuple(p), tuple(d), length, r1=r, mat="M_Colony.thorn", verts=4), lambda f: len(f.verts) > 3)


def beetle_turret(name, mats, pivot):
    """Gunmetal four-lobed cannon (turret sprite: cross ~1.1 cells across, barrel tip ~1.15 from the
    yaw axis) on a drum; the original render shows a dark pedestal and a long grey barrel."""
    p = Vector(pivot)
    fixed = [_cyl(mats, p + Vector((0, 0, 0.05)), 0.38, 0.1, "M_BeetleGunDark", verts=28),
             _torus(mats, p + Vector((0, 0, 0.1)), 0.36, 0.045, "M_BeetleGunDark", segs=(28, 8)),
             _cyl(mats, p + Vector((0, 0, 0.17)), 0.26, 0.14, "M_BeetleGun", verts=24),
             _sphere(mats, p + Vector((0, 0, 0.36)), 0.27, "M_BeetleGun", scale=(1, 1, 0.85), segments=24, rings=12)]
    for dx, dy in ((0.29, 0), (-0.29, 0), (0, 0.29), (0, -0.29)):
        fixed.append(_sphere(mats, p + Vector((dx, dy, 0.32)), 0.19, "M_BeetleGun", scale=(1.1, 1.1, 0.9), segments=18,
                             rings=10))
    moving = [_cyl(mats, p + Vector((0, -0.68, 0.42)), 0.09, 1.0, "M_BeetleGun", verts=16, rot=(math.radians(90), 0, 0)),
              _cyl(mats, p + Vector((0, -0.3, 0.42)), 0.125, 0.2, "M_BeetleGunDark", verts=16, rot=(math.radians(90), 0, 0)),
              _torus(mats, p + Vector((0, -1.14, 0.42)), 0.1, 0.035, "M_BeetleGunDark", rot=(math.radians(90), 0, 0), segs=(16, 6)),
              _cyl(mats, p + Vector((0, 0.16, 0.42)), 0.15, 0.3, "M_BeetleGunDark", verts=16, rot=(math.radians(90), 0, 0))]
    return _make_turret(name, mats, pivot, fixed, moving)


def build_beetle_colony(quick=False):
    name = "colony_beetle"
    salib.reset_scene(name)
    mats = beetle_materials()
    rnd = random.Random(11)
    parts = []
    # dark granite core: fills the dome so the slits look into rock, not onto the ground
    core = lathe_mound("Core", mats, "M_BeetleRock", (0.0, 0.0),
                       [(1.86, 0.0), (1.8, 0.45), (1.62, 0.9), (1.3, 1.2), (0.8, 1.36), (0.0, 1.42)],
                       segments=56, steps=3, noise=0.07, noise_scale=0.45, seed=5)
    # the bottom and the part under the cap are never seen
    parts.append(drop_faces(core, lambda f: _on_ground_bottom(f) or
                            (f.calc_center_median().z > 1.2 and f.calc_center_median().xy.length < 0.78)))
    n = len(BOUNDS)
    for i in range(n):
        a0, g0, k0 = BOUNDS[i]
        a1, g1, k1 = BOUNDS[(i + 1) % n]
        if a1 <= a0:
            a1 += 360
        spec = dict(PLATES[i])
        spikes = spec.pop("spikes")
        pl = ShellPlate(a0, a1, g0, g1, skew0=k0, skew1=k1, seed=i * 3.1, **spec)
        parts.append(drop_faces(pl.mesh(mats, f"Plate{i}", "M_Colony"), _on_ground_bottom))
        for t, s, ln, tilt in spikes:
            p, nrm = pl.point(t, s, 1, extra=-0.03)
            radial = Vector((p.x, p.y, 0.0)).normalized()
            d = (radial * math.cos(math.radians(tilt)) + Vector((0, 0, math.sin(math.radians(tilt))))).normalized()
            d = (d * 0.7 + nrm * 0.3).normalized()
            sp = _spike(mats, tuple(p), tuple(d), ln * rnd.uniform(0.95, 1.08), r1=0.062, mat="M_Colony.spike", verts=8)
            parts.append(drop_faces(sp, lambda f: len(f.verts) > 3))  # the base disc sits inside the plate
        for k in range(3):  # short dark thorns near the slit edges, mid-height
            t = rnd.uniform(0.28, 0.62)
            s = (-0.72 if k % 2 else 0.72) * rnd.uniform(0.85, 1.0)
            if k == 2:
                s = rnd.uniform(-0.3, 0.3)
                t = rnd.uniform(0.2, 0.35)
            parts.append(_thorn(mats, pl, t, s, length=rnd.uniform(0.24, 0.34), r=0.075))
    # the cap: a domed medallion with a thick rim, a dark socket for the turret
    cx, cy, cz, cr, ch = CAP
    capo = _sphere(mats, (cx, cy, cz), cr, "M_Colony.cap", scale=(1, 1, ch / cr), segments=48, rings=24)
    parts.append(drop_faces(capo, lambda f: max(v.co.z for v in f.verts) < cz - 0.05))  # lower half: inside
    parts.append(_torus(mats, (cx, cy, cz + 0.03), cr - 0.01, 0.1, "M_Colony.cap", segs=(48, 10)))
    parts.append(_torus(mats, (cx, cy, PIVOT_Z - 0.01), 0.4, 0.05, "M_BeetleGunDark", segs=(32, 8)))
    body = join_into(parts, "ColonyBody")
    t, bs = beetle_turret("Turret_1", mats, (cx, cy, PIVOT_Z))
    _attach(t, body)
    return _finish_colony(name, body, [t], [bs], 9.5, 0.9, quick)
