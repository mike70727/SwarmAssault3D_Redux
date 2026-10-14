"""Builds the spider family: Black Widow, Sniper, Missile - faithful rebuild from the original 1999 art.

References: reference/models/spider_*/ (the original developers' 3-D portraits, the 8-facing top-down
sprites, the team-colour masks) and the original loading screens (reference/models/_common).  Everything
below was measured on the sprites (24 px = 1 cell; the frames are 58 px / 50 px) and the portraits:

* Black Widow (51x42 px facing down): glossy black spider.  Big spherical abdomen (0.55 cells across)
  with the team-coloured HOURGLASS on top - the only part that takes the team colour (mask) - a small,
  lower cephalothorax in front with pale fangs, and eight very long thin legs with high knees.  From
  above legs I and II sweep forward, III sideways, IV backward; leg span 2.1 cells.
* Sniper (39x35 px): compact hairy brown tarantula.  Only the big teardrop abdomen is team-coloured
  (pointed rear tip, radial ridges); the flat cephalothorax, the pedipalps and the thick hairy legs stay
  brown.  Leg span 1.6 cells, legs fanned from forward-side to back.  No gun: neither the portrait nor
  the sprites show one - the attack frames flash on the middle of the carapace.
* Missile (50x37 px): team-coloured body - a round cephalothorax ball in front, a longer abdomen behind
  carrying the light-grey box launcher (the attack frames flash at the rear/top of the box) - and black
  legs spread sideways like a star (fan from 40 deg forward to 40 deg back), span 2.1 cells.

Rest pose faces -Y, origin on the ground at the centre of the leg footprint.  Clips idle / move / attack /
death.  salib.leg_bones() is reused for the bones (coxa / femur / tibia + an IK target bone per foot), but
the motion is local:
* the feet are keyed on the IK target bones in armature space (ik_local / key_foot / key_walk): salib's
  key_walk_cycle / key_death key them as if bone-local were world space (the ik bones point +Z, so their
  local Y is world Z) and the feet sank through the ground;
* solve_legs() turns the foot keys into FK femur / tibia keys with an analytic two-bone IK (no IK
  constraints, no poles): the knee stays in the leg's modelled bend plane carried by the body, so knees
  never flip down or across the body when the body lunges or rolls;
* `move` is keyed on frames 0..12 (frame 12 = frame 0), so the exported clip loops seamlessly from t = 0
  (a clip starting at Blender frame 1 starts at t = 1/30 s and the game holds that pose once per loop).
Foot / knee heights and the walk's ground slide were checked on the exported GLBs
(qa/agents/spiders/s2/glb_feet_check.py).
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import salib  # noqa: E402
from salib import BoneDef, Body, Clip, LegSpec, Part  # noqa: E402

VARIANTS = {
    "spider_black_widow": dict(kind="widow"),
    "spider_sniper": dict(kind="sniper"),
    "spider_missile": dict(kind="missile"),
}

# ----------------------------------------------------------------------------------------------
# measured layouts (left side; x = outward, y = +back / -forward, z = up), relative to the
# cephalothorax centre (CX=0, CY, CZ).  feet = ground contact points read off the sprites.
# ----------------------------------------------------------------------------------------------
LAYOUT = {
    "widow": dict(
        cy=-0.20, cz=0.32, leg_r=0.030, leg_verts=10,
        legs=[  # name, root, knee, foot, phase
            ("L1", (0.13, -0.14, 0.29), (0.40, -0.46, 0.76), (0.70, -0.75, 0.0), 0.0),
            ("L2", (0.16, -0.06, 0.29), (0.56, -0.28, 0.76), (1.05, -0.42, 0.0), 0.5),
            ("L3", (0.16, 0.03, 0.29), (0.58, 0.14, 0.72), (1.09, 0.35, 0.0), 0.0),
            ("L4", (0.13, 0.11, 0.29), (0.36, 0.48, 0.68), (0.57, 1.06, 0.0), 0.5),
        ],
    ),
    "sniper": dict(
        # feet / knees pulled in ~8 % (second shift): at the game's 58 deg camera the model was 1.81 cells
        # wide against the sprite's 1.62
        cy=-0.25, cz=0.28, leg_r=0.056, leg_verts=12,
        legs=[
            ("L1", (0.17, -0.16, 0.24), (0.42, -0.34, 0.64), (0.63, -0.44, 0.0), 0.0),
            ("L2", (0.21, -0.06, 0.24), (0.51, -0.11, 0.66), (0.78, -0.11, 0.0), 0.5),
            ("L3", (0.21, 0.05, 0.24), (0.49, 0.17, 0.64), (0.75, 0.30, 0.0), 0.0),
            ("L4", (0.17, 0.14, 0.24), (0.40, 0.34, 0.60), (0.57, 0.54, 0.0), 0.5),
        ],
    ),
    "missile": dict(
        cy=-0.22, cz=0.30, leg_r=0.034, leg_verts=10,
        legs=[
            ("L1", (0.15, -0.12, 0.26), (0.50, -0.38, 0.70), (0.87, -0.60, 0.0), 0.0),
            ("L2", (0.19, -0.04, 0.26), (0.60, -0.14, 0.72), (1.06, -0.20, 0.0), 0.5),
            ("L3", (0.19, 0.05, 0.26), (0.56, 0.22, 0.70), (0.95, 0.40, 0.0), 0.0),
            ("L4", (0.15, 0.13, 0.26), (0.48, 0.40, 0.66), (0.83, 0.65, 0.0), 0.5),
        ],
    ),
}


def leg_specs(kind):
    lay = LAYOUT[kind]
    cy, cz = lay["cy"], lay["cz"]
    specs = []
    for name, root, knee, foot, phase in lay["legs"]:
        sh = lambda p: (p[0], p[1] + cy, p[2])  # feet stay on the ground (z given absolute)
        m = lambda p: (-p[0], p[1], p[2])
        r, k, f = sh(root), sh(knee), sh(foot)
        specs.append(LegSpec(name, +1, r, k, f, phase=phase, radius=lay["leg_r"]))
        specs.append(LegSpec("R" + name[1:], -1, m(r), m(k), m(f), phase=(phase + 0.5) % 1.0, radius=lay["leg_r"]))
    return specs


# ----------------------------------------------------------------------------------------------
# geometry helpers (local copies / extensions of salib.Body - salib itself is shared and untouched)
# ----------------------------------------------------------------------------------------------
class SpiderBody(Body):
    """salib.Body plus polyline tubes with per-ring bone groups and custom meshes."""

    def _custom(self, name, verts, faces, bone, mat, groups=None, smooth=True, recalc=True):
        me = bpy.data.meshes.new(name)
        me.from_pydata([tuple(v) for v in verts], [], faces)
        me.update()
        o = bpy.data.objects.new(name, me)
        salib.link(o)
        if recalc:
            bm = bmesh.new()
            bm.from_mesh(me)
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bm.to_mesh(me)
            bm.free()
            me.update()
        o["sa_no_subdiv"] = True
        if groups:
            o["sa_custom_vg"] = True
            for gname, idx in groups.items():
                vg = o.vertex_groups.new(name=gname)
                vg.add(list(idx), 1.0, "REPLACE")
        return self._finish(o, bone, mat, smooth=smooth)

    def tube(self, nodes, mat, verts=10, cap_start=False, cap_end=True):
        """Jointed tube along a polyline.  nodes = [(point, radius, bone), ...]; each ring is skinned
        rigidly to its node's bone, so the quads between rings of different bones bend at the joint."""
        P = [Vector(n[0]) for n in nodes]
        R = [n[1] for n in nodes]
        n = len(P)
        tang = []
        for i in range(n):
            if i == 0:
                t = P[1] - P[0]
            elif i == n - 1:
                t = P[-1] - P[-2]
            else:
                t = (P[i] - P[i - 1]).normalized() + (P[i + 1] - P[i]).normalized()
                if t.length < 1e-6:
                    t = P[i + 1] - P[i - 1]
            tang.append(t.normalized())
        ref = Vector((0, 0, 1)) if abs(tang[0].z) < 0.9 else Vector((1, 0, 0))
        u = (ref - tang[0] * ref.dot(tang[0])).normalized()
        vs, faces = [], []
        groups = {}
        for i in range(n):
            t = tang[i]
            u = (u - t * u.dot(t)).normalized()
            v = t.cross(u).normalized()
            for k in range(verts):
                a = 2 * math.pi * k / verts
                vs.append(P[i] + (u * math.cos(a) + v * math.sin(a)) * R[i])
            groups.setdefault(nodes[i][2], []).extend(range(i * verts, i * verts + verts))
        for i in range(n - 1):
            for k in range(verts):
                a = i * verts + k
                b = i * verts + (k + 1) % verts
                faces.append((a, b, b + verts, a + verts))
        if cap_end:
            c = len(vs)
            vs.append(P[-1] + tang[-1] * R[-1] * 0.5)
            groups[nodes[-1][2]].append(c)
            base = (n - 1) * verts
            for k in range(verts):
                faces.append((base + k, base + (k + 1) % verts, c))
        if cap_start:
            c = len(vs)
            vs.append(P[0] - tang[0] * R[0] * 0.5)
            groups[nodes[0][2]].append(c)
            for k in range(verts):
                faces.append((k, (k + 1) % verts, c))
        return self._custom(f"{self.name}_tube", vs, faces, nodes[0][2], mat, groups)

    def lathe(self, bone, mat, center, length, radius, profile, around=32, along=16, lobes=0, lobe_depth=0.0,
              zscale=1.0, axis="Y"):
        """Surface of revolution around the body axis from the front (s=0) to the rear (s=1).
        `profile(s)` returns the relative radius; optional radial lobes (ridged abdomens)."""
        c = Vector(center)
        vs, faces = [], []
        vs.append(c + Vector((0, -length / 2, 0)))  # front pole
        rows = []
        for j in range(1, along):
            s = j / along
            rel = profile(s)
            row = []
            for k in range(around):
                a = 2 * math.pi * k / around
                r = radius * rel
                if lobes:
                    r *= 1.0 + lobe_depth * math.cos(lobes * a) * math.sin(math.pi * s) ** 0.6
                row.append(len(vs))
                vs.append(c + Vector((r * math.cos(a), -length / 2 + s * length, r * math.sin(a) * zscale)))
            rows.append(row)
        tip = len(vs)
        vs.append(c + Vector((0, length / 2, 0)))
        for k in range(around):
            faces.append((0, rows[0][(k + 1) % around], rows[0][k]))
        for j in range(len(rows) - 1):
            for k in range(around):
                a, b = rows[j][k], rows[j][(k + 1) % around]
                faces.append((a, b, rows[j + 1][(k + 1) % around], rows[j + 1][k]))
        last = rows[-1]
        for k in range(around):
            faces.append((last[k], last[(k + 1) % around], tip))
        return self._custom(f"{self.name}_lathe", vs, faces, bone, mat)

    def decal_on_ellipsoid(self, bone, mat, center, radius, scale, halfwidth, length_back, length_front,
                           waist, lift=0.008, nu=9, nv=25, shift=0.0):
        """Hourglass-shaped decal conformed to the top of an ellipsoid (sphere `radius` scaled by `scale`);
        `shift` moves the shape back (+Y) along the top."""
        c = Vector(center)
        sx, sy, sz = scale
        vs, faces = [], []
        for j in range(nv):
            v = -1.0 + 2.0 * j / (nv - 1)         # -1 = front base, +1 = rear base
            L = length_back if v > 0 else length_front
            hw = halfwidth[1] if v > 0 else halfwidth[0]
            w = waist + (hw - waist) * abs(v) ** 1.25   # concave bow-tie sides
            y = shift + v * L
            for i in range(nu):
                u = -1.0 + 2.0 * i / (nu - 1)
                x = u * w
                # point on the unit sphere (local), top hemisphere
                lx, ly = x / (radius * sx), y / (radius * sy)
                lz = math.sqrt(max(0.0, 1.0 - lx * lx - ly * ly))
                p = Vector((lx, ly, lz))
                nrm = Vector((lx / sx, ly / sy, lz / sz)).normalized()
                world = c + Vector((p.x * radius * sx, p.y * radius * sy, p.z * radius * sz)) + nrm * lift
                vs.append(world)
        for j in range(nv - 1):
            for i in range(nu - 1):
                a = j * nu + i
                faces.append((a, a + 1, a + nu + 1, a + nu))
        return self._custom(f"{self.name}_decal", vs, faces, bone, mat, recalc=False)

    def chamfered_box(self, bone, mat, center, size, chamfer, bevel=0.012):
        """Box with its rear-top edge cut at 45 deg (missile pod); edges bevelled."""
        cx, cy, cz = center
        hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
        vs = [
            (cx - hx, cy - hy, cz - hz), (cx + hx, cy - hy, cz - hz),      # 0 1 bottom front
            (cx + hx, cy + hy, cz - hz), (cx - hx, cy + hy, cz - hz),      # 2 3 bottom rear
            (cx - hx, cy - hy, cz + hz), (cx + hx, cy - hy, cz + hz),      # 4 5 top front
            (cx + hx, cy + hy - chamfer, cz + hz), (cx - hx, cy + hy - chamfer, cz + hz),  # 6 7 chamfer top
            (cx + hx, cy + hy, cz + hz - chamfer), (cx - hx, cy + hy, cz + hz - chamfer),  # 8 9 chamfer rear
        ]
        faces = [
            (0, 3, 2, 1),              # bottom
            (0, 1, 5, 4),              # front
            (4, 5, 6, 7),              # top
            (7, 6, 8, 9),              # chamfer (faces up-back)
            (9, 8, 2, 3),              # rear
            (1, 2, 8, 6, 5),           # right side
            (0, 4, 7, 9, 3),           # left side
        ]
        o = self._custom(f"{self.name}_box", vs, faces, bone, mat, smooth=False)
        o["sa_bevel"] = bevel
        return o

    def join_spider(self, name=None, smooth_angle=50.0):
        """salib.Body.join without the global displacement; honours per-part custom vertex groups."""
        name = name or f"{self.name}_Mesh"
        for p in self.parts:
            o = p.obj
            if salib.REALISM and not o.get("sa_no_subdiv"):
                salib.select_only([o])
                bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
                m = o.modifiers.new("Subd", "SUBSURF")
                m.levels = 1
                m.render_levels = 1
                bpy.ops.object.modifier_apply(modifier=m.name)
            elif salib.REALISM and o.get("sa_bevel"):
                salib.select_only([o])
                bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
                salib.bevel_object(o, float(o["sa_bevel"]))
            if not o.get("sa_custom_vg"):
                vg = o.vertex_groups.new(name=p.bone)
                vg.add(list(range(len(o.data.vertices))), 1.0, "REPLACE")
        objs = [p.obj for p in self.parts]
        salib.select_only(objs)
        bpy.ops.object.join()
        obj = bpy.context.object
        obj.name = name
        obj.data.name = name
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        try:
            bpy.ops.object.shade_smooth_by_angle(angle=math.radians(smooth_angle))
        except Exception:
            bpy.ops.object.shade_smooth()
        self.parts.clear()
        return obj


def roughen(obj, strength=0.008, scale=0.12):
    """Small procedural displacement on one body part (hairy / lumpy surfaces)."""
    if not salib.REALISM:
        return obj
    salib.select_only([obj])
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    tex = bpy.data.textures.get("SpiderNoise") or bpy.data.textures.new("SpiderNoise", "CLOUDS")
    tex.noise_scale = scale
    tex.noise_depth = 2
    d = obj.modifiers.new("Displace", "DISPLACE")
    d.texture = tex
    d.strength = strength
    d.mid_level = 0.5
    d.texture_coords = "GLOBAL"
    bpy.ops.object.modifier_apply(modifier=d.name)
    return obj


def groove_stripes(mat, obj, center, zscale, lobes, dark=0.18, width=0.5):
    """Dark grooves between the ridges of a lobed abdomen built by SpiderBody.lathe (the sniper
    portrait's black stripes, which converge at the rear tip).  The base colour is multiplied by a factor
    that falls to `dark` where cos(lobes * angle) -> -1, i.e. exactly along the geometric grooves; the
    stripes stay inside M_Team (the team-colour mask covers the whole abdomen), so the bake carries
    them as dark texels and the team tint turns them nearly black.  `center` is the lathe centre in
    world space; the joined mesh keeps its origin at the first part, so it is converted to the object
    space that the Object texture coordinates use."""
    if not salib.REALISM or not mat.use_nodes:
        return
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    link = next(lk for lk in nt.links if lk.to_socket == bsdf.inputs["Base Color"])
    src = link.from_socket
    c = obj.matrix_world.inverted() @ Vector(center)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])

    def math_node(op, a, b=0.0):
        m = nt.nodes.new("ShaderNodeMath")
        m.operation = op
        for sock, v in zip(m.inputs, (a, b)):
            if hasattr(v, "node"):
                nt.links.new(v, sock)
            else:
                sock.default_value = v
        return m.outputs[0]

    x = math_node("SUBTRACT", sep.outputs["X"], c.x)
    z = math_node("DIVIDE", math_node("SUBTRACT", sep.outputs["Z"], c.z), zscale)
    ang = math_node("ARCTAN2", z, x)                      # same angle as the lathe: x = r cos a, z = r sin a
    cos_l = math_node("COSINE", math_node("MULTIPLY", ang, float(lobes)))
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.clamp = True
    mr.inputs["From Min"].default_value = -1.0
    mr.inputs["From Max"].default_value = -1.0 + width
    mr.inputs["To Min"].default_value = dark
    mr.inputs["To Max"].default_value = 1.0
    nt.links.new(cos_l, mr.inputs["Value"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 1.0
    nt.links.new(src, mix.inputs[6])
    nt.links.new(mr.outputs["Result"], mix.inputs[7])
    nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])


def hi_sphere(body, bone, mat, center, radius, scale=(1, 1, 1), segments=28, rings=18):
    """UV sphere kept at its own resolution (no subdivision in the join)."""
    o = body.sphere(bone, mat, center, radius, scale=scale, segments=segments, rings=rings)
    o["sa_no_subdiv"] = True
    return o


def eye(body, center, radius):
    """Glossy eye sphere at a fixed resolution (the realism subdivision would quadruple it)."""
    return hi_sphere(body, "head", "M_Eye", center, radius, segments=10, rings=6)


def leg_tube(body, spec: LegSpec, mat, verts=10, knee_bulge=1.0, bristles=0, bristle_len=(0.055, 0.025)):
    """One leg as a jointed tube with visible joints: coxa -> trochanter -> femur -> patella/knee ->
    tibia -> tibia/metatarsus joint (second bend) -> metatarsus+tarsus -> claw.  The thickness tapers
    from the femur to the claw; rings are skinned to salib's coxa / femur / tibia bones."""
    n = f"leg.{spec.name}"
    root, knee, foot = Vector(spec.root), Vector(spec.knee), Vector(spec.foot)
    mid = root.lerp(knee, 0.35)                      # femur bone head (salib.leg_bones)
    r = spec.radius
    cox = (mid - root).normalized()
    fem = (knee - mid).normalized()
    tib = (foot - knee).normalized()
    out = Vector((foot.x - root.x, foot.y - root.y, 0)).normalized()
    ankle = knee.lerp(foot, 0.64) + Vector((0, 0, 0.07)) + out * 0.02
    tars = (foot - ankle)
    tar = tars.normalized()
    tars_flat = Vector((tars.x, tars.y, 0)).normalized()
    claw = foot + tars_flat * 0.05 + Vector((0, 0, 0.004))
    nodes = [
        (root - cox * 0.03, r * 1.45, f"{n}.coxa"),
        (root.lerp(mid, 0.5), r * 1.25, f"{n}.coxa"),
        (mid - cox * 0.025, r * 1.05, f"{n}.coxa"),
        (mid, r * 1.18, f"{n}.femur"),                           # trochanter bulb
        (mid + fem * 0.06, r * 1.0, f"{n}.femur"),
        (knee - fem * 0.08, r * 0.86, f"{n}.femur"),
        (knee, r * 1.12 * knee_bulge, f"{n}.femur"),             # patella / knee bulb
        (knee + tib * 0.08, r * 0.82, f"{n}.tibia"),
        (ankle - tar * 0.035, r * 0.62, f"{n}.tibia"),
        (ankle, r * 0.76, f"{n}.tibia"),                          # tibia / metatarsus joint bulb
        (ankle + tar * 0.035, r * 0.54, f"{n}.tibia"),
        (foot, r * 0.28, f"{n}.tibia"),
        (claw, r * 0.07, f"{n}.tibia"),
    ]
    tube = body.tube(nodes, mat, verts=verts, cap_start=True, cap_end=True)
    if bristles:
        # short tapered hairs along the femur and the tibia (hairy spiders)
        segs = [(mid + fem * 0.08, knee - fem * 0.1, f"{n}.femur", r * 1.0),
                (knee + tib * 0.1, ankle - tar * 0.05, f"{n}.tibia", r * 0.75)]
        i = 0
        for a, b, bone, rr in segs:
            d = (b - a)
            dn = d.normalized()
            ref = Vector((0, 0, 1)) if abs(dn.z) < 0.9 else Vector((1, 0, 0))
            u = (ref - dn * ref.dot(dn)).normalized()
            v = dn.cross(u)
            for k in range(bristles):
                i += 1
                t = 0.1 + 0.8 * ((k + 0.5) / bristles)
                ang = 2 * math.pi * ((i * 0.618034) % 1.0)
                radial = u * math.cos(ang) + v * math.sin(ang)
                base = a + d * t + radial * rr * 0.8
                dirn = (radial * 0.75 + dn * 0.55).normalized()
                length = bristle_len[0] + bristle_len[1] * ((i * 0.381966) % 1.0)
                rot = dirn.to_track_quat("Z", "Y").to_euler()
                h = body.cone(bone, mat, tuple(base + dirn * length * 0.5), r * 0.22, 0.0, length, rot=rot, verts=4)
                h["sa_no_subdiv"] = True
    return tube


def tri_count(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


# ----------------------------------------------------------------------------------------------
# animation helpers (local replacements for salib.key_walk_cycle / key_death)
# ----------------------------------------------------------------------------------------------
# salib.leg_bones() makes every IK target bone point straight up (+Z), so a pose-bone `location`
# keyed as (0, stride, lift) - what salib.key_walk_cycle does - moves the foot UP by `stride` and
# FORWARD by `lift`: the feet sink through the ground and the stride is tiny.  The helpers below
# convert armature-space offsets through the bone's rest matrix (same approach as build_scorpion.py)
# so stride / lift mean what they say.
def ik_local(rig, bone_name, offset):
    m = rig.data.bones[bone_name].matrix_local.to_3x3()
    return tuple(m.inverted() @ Vector(offset))


def key_foot(clip, rig, spec, frame, offset):
    clip.key(f"leg.{spec.name}.ik", frame, loc=ik_local(rig, f"leg.{spec.name}.ik", offset))


def key_walk(clip: Clip, rig, specs, frames: int, stride: float, lift: float, body_bob=0.012, first=0):
    """Alternating-tetrapod walk (L1+L3+R2+R4 against L2+L4+R1+R3) keyed on every frame: a planted
    foot slides straight back (+Y, the spider faces -Y) at a constant rate for half the cycle, then
    swings forward in an arc of height `lift`.  The game plays `move` at speed / 2.5, so the cycle
    covers 2.5 * (frames / 30) cells and a slide-free stride is 1.25 * (frames / 30) cells.

    The cycle is keyed on frames first .. first + frames inclusive (the last key repeats the first
    pose).  With first=0 the exported clip runs from t = 0 to t = frames / 30 and loops seamlessly in
    the game; a clip starting at frame 1 starts at t = 1/30 s, and Bevy holds that first key for a
    frame at every loop (the planted feet slide forward and snap back once per cycle)."""
    for spec in specs:
        for i in range(frames + 1):
            ph = (i / frames + spec.phase) % 1.0
            if ph < 0.5:
                s = ph / 0.5
                y, z = -stride / 2 + stride * s, 0.0
            else:
                s = (ph - 0.5) / 0.5
                y, z = stride / 2 - stride * s, lift * math.sin(math.pi * s)
            key_foot(clip, rig, spec, first + i, (0.0, y, z))
    for i in range(frames + 1):
        ph = (i / frames) * 2.0 * math.pi * 2.0      # two bobs per cycle (one per tetrapod step)
        clip.key("body", first + i, loc=(0, 0, body_bob * (0.5 - 0.5 * math.cos(ph))))


def slide_free_stride(frames: int) -> float:
    return 1.25 * frames / salib.FPS


def _align_y(carried, direction, head):
    """Armature-space bone matrix: the `carried` frame turned by the smallest rotation that points its
    Y axis (the bone axis) along `direction`, placed at `head` (no twist is introduced)."""
    r0 = carried.to_3x3()
    q = r0.col[1].normalized().rotation_difference(direction.normalized())
    m = (q.to_matrix() @ r0).to_4x4()
    m.translation = head
    return m


def solve_legs(rig, specs, first: int, last: int, twist=None):
    """Analytic two-bone leg IK, keyed as plain FK rotations on every frame first..last of the action
    that is currently on the rig.

    The IK target bones (leg.*.ik, keyed by key_foot / key_walk / key_feet_rest) give the foot positions;
    the body and everything else are already keyed.  For each frame the knee is placed in the leg's own
    modelled bend plane - the rest-pose knee direction carried along by the body's rotation - so the
    knees stay up and out like the rest pose through every clip.  The knee is lifted (the bend plane
    turned about the hip-foot line) whenever it would come closer to the ground than its own joint
    bulb.  This replaces Blender's IK constraint with a pole target: the poles hang from the rig root,
    so when the body pitched, lunged or rolled (attack / death) the solver flipped single knees down
    to the ground or across the body, on one side only.

    `twist(frame)` (radians, optional) turns the bend plane about the hip-foot line so the knees sag
    sideways - legs I / II toward the front, III / IV toward the rear - like the limp legs of the death."""
    sc = bpy.context.scene
    vl = bpy.context.view_layer
    pbs, bones = rig.pose.bones, rig.data.bones
    body_rest_inv = bones["body"].matrix_local.inverted()
    legs = []
    for spec in specs:
        n = f"leg.{spec.name}"
        cox, fem, tib = bones[f"{n}.coxa"], bones[f"{n}.femur"], bones[f"{n}.tibia"]
        hip, knee, foot = fem.head_local.copy(), fem.tail_local.copy(), tib.tail_local.copy()
        a, b = (knee - hip).length, (foot - knee).length
        u = (foot - hip).normalized()
        bend = (knee - hip) - u * (knee - hip).dot(u)
        # sag direction for `twist`, fixed per leg from the rest geometry: a positive turn moves the knee
        # along u x bend; legs I / II sag toward the front (-Y), III / IV toward the rear (+Y)
        side0 = u.cross(bend.normalized())
        sag = (1.0 if side0.y < 0 else -1.0) * (1.0 if int(spec.name[1]) <= 2 else -1.0)
        legs.append(dict(
            n=n, a=a, b=b, bend=bend.normalized(), sag=sag,
            fem_in_cox=cox.matrix_local.inverted() @ fem.matrix_local,
            tib_in_fem=fem.matrix_local.inverted() @ tib.matrix_local,
            floor=spec.radius * 1.15 + 0.012,          # knee joint bulb radius + a little air
            prev={},
        ))
    report = {"unreachable": 0.0, "lifted": 0}
    for f in range(first, last + 1):
        sc.frame_set(f)
        vl.update()
        body_rot = (pbs["body"].matrix @ body_rest_inv).to_3x3()
        sol = []
        for L in legs:
            n = L["n"]
            hip = pbs[f"{n}.coxa"].tail.copy()            # femur head (connected to the coxa)
            target = pbs[f"{n}.ik"].head.copy()
            d_vec = target - hip
            d = d_vec.length
            u = d_vec.normalized()
            reach_max, reach_min = (L["a"] + L["b"]) * 0.9995, abs(L["a"] - L["b"]) + 1e-4
            if d > reach_max:
                report["unreachable"] = max(report["unreachable"], d - reach_max)
            dc = min(max(d, reach_min), reach_max)
            cos_a = (L["a"] ** 2 + dc ** 2 - L["b"] ** 2) / (2 * L["a"] * dc)
            sin_a = math.sqrt(max(0.0, 1.0 - cos_a * cos_a))
            h = body_rot @ L["bend"]
            h = h - u * h.dot(u)
            if h.length < 1e-5:
                h = Vector((0, 0, 1)) - u * u.z
            h.normalize()
            side = u.cross(h)

            def knee_at(angle, h=h, side=side, hip=hip, u=u, cos_a=cos_a, sin_a=sin_a, a=L["a"]):
                hh = h * math.cos(angle) + side * math.sin(angle)
                return hip + (u * cos_a + hh * sin_a) * a

            a0 = L["sag"] * (twist(f) if twist is not None else 0.0)
            k = knee_at(a0)
            if k.z < L["floor"]:
                # turn the bend plane about the hip-foot line (smallest extra turn, either way) until
                # the knee clears the ground
                best = None
                for step in range(1, 181):
                    for sgn in (1, -1):
                        kk = knee_at(a0 + sgn * math.radians(step))
                        if kk.z >= L["floor"]:
                            best = kk
                            break
                    if best is not None:
                        break
                if best is None:   # cannot clear: take the highest knee
                    best = max((knee_at(math.radians(s)) for s in range(0, 360, 2)), key=lambda v: v.z)
                k = best
                report["lifted"] += 1
            foot = hip + u * dc
            sol.append((L, hip, k, foot))
        for L, hip, k, foot in sol:                       # femurs first ...
            carried = pbs[f"{L['n']}.coxa"].matrix @ L["fem_in_cox"]
            pbs[f"{L['n']}.femur"].matrix = _align_y(carried, k - hip, hip)
        vl.update()
        for L, hip, k, foot in sol:                       # ... then the tibias on the posed femurs
            carried = pbs[f"{L['n']}.femur"].matrix @ L["tib_in_fem"]
            pbs[f"{L['n']}.tibia"].matrix = _align_y(carried, foot - k, k)
        vl.update()
        for L, hip, k, foot in sol:
            for part in ("femur", "tibia"):
                pb = pbs[f"{L['n']}.{part}"]
                prev = L["prev"].get(part)
                if prev is not None:
                    e = pb.rotation_euler.copy()
                    e.make_compatible(prev)
                    pb.rotation_euler = e
                L["prev"][part] = pb.rotation_euler.copy()
                pb.keyframe_insert("rotation_euler", frame=f)
    # leave the rig evaluated at the clip's first frame: salib.bake_actions() bakes every clip on top of
    # the current pose, so channels a clip does not key (e.g. the body rotation in idle / move) would
    # otherwise inherit this clip's last frame (the death roll leaked into idle and move)
    sc.frame_set(first)
    vl.update()
    return report


def leg_report(name, report):
    salib.log(f"legs {name}: knee lifted off the ground on {report['lifted']} leg-frames, "
              f"worst foot-target overshoot {report['unreachable']:.3f}")
    return report


def key_feet_rest(clip: Clip, specs, frames):
    for spec in specs:
        clip.key(f"leg.{spec.name}.ik", 1, loc=(0, 0, 0))
        clip.key(f"leg.{spec.name}.ik", frames, loc=(0, 0, 0))


# ----------------------------------------------------------------------------------------------
# the three spiders
# ----------------------------------------------------------------------------------------------
def build(variant: str):
    kind = VARIANTS[variant]["kind"]
    lay = LAYOUT[kind]
    CY, CZ = lay["cy"], lay["cz"]
    salib.reset_scene(variant)
    mats = salib.standard_materials("Y")
    if kind == "widow":
        mats["M_Team"] = salib.material("M_Team", salib.TEAM_COLORS["Y"], roughness=0.3, kind="chitin", tint=True,
                                        variation=0.12, coat=0.6, dirt=0.05, bump=0.05)
    else:
        mats["M_Team"] = salib.material("M_Team", salib.TEAM_COLORS["Y"], roughness=0.75, kind="fur", tint=True,
                                        variation=0.3, dirt=0.3)
    mats["M_WidowBody"] = salib.material("M_WidowBody", (0.035, 0.035, 0.04), roughness=0.18, kind="chitin",
                                         coat=1.0, variation=0.15, dirt=0.0, bump=0.04)
    mats["M_WidowLeg"] = salib.material("M_WidowLeg", (0.11, 0.09, 0.075), roughness=0.32, kind="chitin",
                                        coat=0.6, variation=0.25, bump=0.1)
    mats["M_Fang"] = salib.material("M_Fang", (0.82, 0.74, 0.56), roughness=0.25, kind="glossy")
    mats["M_Brown"] = salib.material("M_Brown", (0.30, 0.21, 0.15), roughness=0.85, kind="fur", variation=0.45)
    mats["M_BrownLeg"] = salib.material("M_BrownLeg", (0.25, 0.17, 0.12), roughness=0.85, kind="fur", variation=0.4)
    mats["M_Gun"] = salib.material("M_Gun", (0.20, 0.20, 0.22), roughness=0.38, metallic=0.9, kind="metal")
    mats["M_MissileLeg"] = salib.material("M_MissileLeg", (0.10, 0.08, 0.065), roughness=0.42, kind="chitin",
                                          coat=0.45, variation=0.3, bump=0.12)
    # light-grey painted box (sprite / portrait grey ~ (140, 133, 119)): kept dielectric - salib's "metal"
    # kind forces metallic >= 0.8, and the game has no environment map, so a metal box renders dark grey
    mats["M_Launcher"] = salib.material("M_Launcher", (0.80, 0.78, 0.71), roughness=0.45, metallic=0.1, kind="chitin",
                                        variation=0.12, coat=0.2, bump=0.06, dirt=0.35)
    # salib's "fur" kind adds a white Sheen lobe; Cycles folds it into the diffuse-colour bake and the
    # brown comes out grey - keep the fur grain/bump but drop the sheen on the baked surfaces.
    for mname in ("M_Team", "M_Brown", "M_BrownLeg"):
        m = mats[mname]
        if m.use_nodes:
            p = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if p is not None and "Sheen Weight" in p.inputs:
                p.inputs["Sheen Weight"].default_value = 0.0
    body = SpiderBody(variant, mats)
    T = "M_Team"
    specs = leg_specs(kind)

    if kind == "widow":
        body_mat, leg_mat = "M_WidowBody", "M_WidowLeg"
        # cephalothorax (small, low) + pedicel + big glossy abdomen
        ceph = hi_sphere(body, "body", body_mat, (0, CY, CZ), 0.20, scale=(1.0, 1.2, 0.8), segments=24, rings=14)
        body.cylinder("body", body_mat, (0, CY + 0.25, CZ + 0.02), 0.05, 0.14, rot=(math.radians(90), 0, 0), verts=10)
        ab_c, ab_r, ab_s = (0, CY + 0.57, 0.44), 0.28, (1.0, 1.06, 1.0)
        hi_sphere(body, "abdomen", body_mat, ab_c, ab_r, scale=ab_s, segments=32, rings=20)
        # team-coloured hourglass on the top-rear of the abdomen (rear lobe larger), the sprite's yellow
        # mark: in the team-colour mask it is a block ~40 % of the abdomen's width at the far (rear) end of
        # the ball plus a small front lobe - enlarged and moved back (second shift) so the team colour still
        # reads at play distance
        body.decal_on_ellipsoid("abdomen", T, ab_c, ab_r, ab_s, halfwidth=(0.07, 0.118), length_back=0.18,
                                length_front=0.12, waist=0.016, lift=0.007, shift=0.05)
        # chelicerae with ivory fangs, pedipalps, eyes
        for s in (+1, -1):
            fb = "fang.L" if s > 0 else "fang.R"
            base = Vector((s * 0.055, CY - 0.19, CZ - 0.06))
            body.tube([(base, 0.040, fb), (base + Vector((0, -0.06, -0.05)), 0.036, fb),
                       (base + Vector((s * 0.005, -0.10, -0.11)), 0.028, fb)], body_mat, verts=10, cap_start=True)
            ft = base + Vector((s * 0.005, -0.10, -0.11))
            body.tube([(ft, 0.016, fb), (ft + Vector((-s * 0.01, -0.03, -0.04)), 0.010, fb),
                       (ft + Vector((-s * 0.025, -0.045, -0.085)), 0.003, fb)], "M_Fang", verts=8, cap_start=True)
            pb = "palp.L" if s > 0 else "palp.R"
            p0 = Vector((s * 0.11, CY - 0.17, CZ - 0.04))
            body.tube([(p0, 0.024, pb), (p0 + Vector((s * 0.10, -0.14, 0.09)), 0.020, pb),
                       (p0 + Vector((s * 0.17, -0.26, 0.00)), 0.015, pb),
                       (p0 + Vector((s * 0.16, -0.33, -0.10)), 0.008, pb)], leg_mat, verts=8, cap_start=True)
            eye(body,(s * 0.045, CY - 0.215, CZ + 0.075), 0.022)
            eye(body,(s * 0.085, CY - 0.19, CZ + 0.06), 0.016)
        for spec in specs:
            leg_tube(body, spec, leg_mat, verts=lay["leg_verts"], knee_bulge=1.05)
        preview_radius = 3.7
    elif kind == "sniper":
        body_mat, leg_mat = "M_Brown", "M_BrownLeg"
        ceph = hi_sphere(body, "body", body_mat, (0, CY, CZ), 0.24, scale=(1.0, 1.1, 0.72), segments=24, rings=14)
        roughen(ceph, 0.012, 0.09)
        body.cylinder("body", body_mat, (0, CY + 0.30, CZ + 0.04), 0.06, 0.16, rot=(math.radians(90), 0, 0), verts=10)

        def teardrop(s):  # relative radius from the front (0) to the pointed rear tip (1)
            pts = [(0.0, 0.0), (0.06, 0.50), (0.16, 0.82), (0.30, 0.97), (0.42, 1.0), (0.56, 0.95), (0.70, 0.78),
                   (0.82, 0.55), (0.91, 0.32), (0.97, 0.12), (1.0, 0.0)]
            for (s0, r0), (s1, r1) in zip(pts, pts[1:]):
                if s0 <= s <= s1:
                    t = (s - s0) / (s1 - s0)
                    t = t * t * (3 - 2 * t)
                    return r0 + (r1 - r0) * t
            return 0.0

        # 12 ridges (the portrait shows six or seven dark grooves on its visible half); the grooves are
        # darkened in the texture by groove_stripes() once the mesh is joined
        ab_center, ab_lobes = (0, CY + 0.67, 0.42), 12
        ab = body.lathe("abdomen", T, ab_center, 0.66, 0.29, teardrop, around=72, along=18,
                        lobes=ab_lobes, lobe_depth=0.07, zscale=0.92)
        roughen(ab, 0.004, 0.08)
        # spinneret nub at the pointed tip
        body.cone("abdomen", "M_Brown", (0, CY + 0.99, 0.40), 0.035, 0.012, 0.06, rot=(-math.radians(90), 0, 0), verts=8)
        # thick hairy chelicerae, pedipalps, eye cluster
        for s in (+1, -1):
            fb = "fang.L" if s > 0 else "fang.R"
            base = Vector((s * 0.07, CY - 0.22, CZ - 0.05))
            body.tube([(base, 0.05, fb), (base + Vector((0, -0.07, -0.05)), 0.045, fb),
                       (base + Vector((0, -0.12, -0.12)), 0.03, fb)], body_mat, verts=10, cap_start=True)
            ft = base + Vector((0, -0.12, -0.12))
            body.tube([(ft, 0.014, fb), (ft + Vector((-s * 0.01, -0.015, -0.03)), 0.009, fb),
                       (ft + Vector((-s * 0.022, -0.02, -0.055)), 0.003, fb)], "M_Fang", verts=8, cap_start=True)
            pb = "palp.L" if s > 0 else "palp.R"
            p0 = Vector((s * 0.14, CY - 0.19, CZ - 0.03))
            body.tube([(p0, 0.036, pb), (p0 + Vector((s * 0.11, -0.13, 0.12)), 0.032, pb),
                       (p0 + Vector((s * 0.18, -0.26, 0.04)), 0.024, pb),
                       (p0 + Vector((s * 0.17, -0.33, -0.08)), 0.012, pb)], leg_mat, verts=10, cap_start=True)
            eye(body,(s * 0.045, CY - 0.235, CZ + 0.10), 0.028)
            eye(body,(s * 0.095, CY - 0.21, CZ + 0.085), 0.018)
            eye(body,(s * 0.02, CY - 0.25, CZ + 0.075), 0.013)
        for spec in specs:
            # short hairs: the portrait's legs are hairy, not thorny (longer cones read as spikes in game)
            leg_tube(body, spec, leg_mat, verts=lay["leg_verts"], knee_bulge=1.08, bristles=5, bristle_len=(0.034, 0.016))
        # No rifle: neither the original portrait nor any of the 8-facing sprites shows a gun (nothing
        # sticks out past the head in any frame); the attack frames flash on the middle of the carapace,
        # so the sniper fires from its body.  (The first automated pass and the previous rebuild had put
        # a scoped rifle along the back with the barrel reaching 0.4 cells past the fangs.)
        preview_radius = 3.0
    else:  # missile
        body_mat, leg_mat = T, "M_MissileLeg"
        ball = hi_sphere(body, "body", T, (0, CY, CZ), 0.24, scale=(1.0, 1.0, 0.9), segments=28, rings=18)
        roughen(ball, 0.010, 0.08)
        ab = hi_sphere(body, "abdomen", T, (0, CY + 0.54, 0.36), 0.22, scale=(1.0, 1.4, 0.75), segments=28, rings=18)
        roughen(ab, 0.010, 0.08)
        # light-grey box launcher on the abdomen, rear-top edge chamfered, two big dark missile tubes
        # (the sprite shows two dark squares on the box, the portrait two openings on its rear face)
        bsz = (0.36, 0.42, 0.22)
        bc = (0, CY + 0.54, 0.585)
        body.chamfered_box("gun", "M_Launcher", bc, bsz, chamfer=0.13)
        nrm = Vector((0, 1, 1)).normalized()
        face_c = Vector((0, bc[1] + bsz[1] / 2 - 0.065, bc[2] + bsz[2] / 2 - 0.065))
        for sx in (-1, 1):
            p = face_c + Vector((sx * 0.085, 0, 0)) + nrm * 0.012
            t = body.cylinder("gun", "M_Black", tuple(p), 0.052, 0.07, rot=(math.radians(-45), 0, 0), verts=14)
            t["sa_no_subdiv"] = True
            rim = body.cylinder("gun", "M_Gun", tuple(p - nrm * 0.02), 0.062, 0.025, rot=(math.radians(-45), 0, 0), verts=14)
            rim["sa_no_subdiv"] = True
        for sx in (-1, 1):   # side rails
            body.cube("gun", "M_Gun", (sx * 0.185, CY + 0.52, 0.53), size=(0.02, 0.32, 0.03))
        body.cube("gun", "M_Gun", (0, CY + 0.33, 0.57), size=(0.16, 0.02, 0.11))            # front panel
        body.cube("gun", "M_Gun", (0, CY + 0.52, 0.70), size=(0.10, 0.16, 0.02))            # top plate
        for s in (+1, -1):
            fb = "fang.L" if s > 0 else "fang.R"
            base = Vector((s * 0.06, CY - 0.19, CZ - 0.08))
            body.tube([(base, 0.04, fb), (base + Vector((0, -0.06, -0.05)), 0.034, fb),
                       (base + Vector((0, -0.10, -0.11)), 0.026, fb)], leg_mat, verts=10, cap_start=True)
            ft = base + Vector((0, -0.10, -0.11))
            body.tube([(ft, 0.014, fb), (ft + Vector((-s * 0.01, -0.025, -0.04)), 0.009, fb),
                       (ft + Vector((-s * 0.022, -0.04, -0.075)), 0.003, fb)], "M_Fang", verts=8, cap_start=True)
            pb = "palp.L" if s > 0 else "palp.R"
            p0 = Vector((s * 0.12, CY - 0.17, CZ - 0.05))
            body.tube([(p0, 0.026, pb), (p0 + Vector((s * 0.10, -0.13, 0.10)), 0.022, pb),
                       (p0 + Vector((s * 0.17, -0.25, 0.02)), 0.016, pb),
                       (p0 + Vector((s * 0.16, -0.31, -0.09)), 0.008, pb)], leg_mat, verts=8, cap_start=True)
            eye(body,(s * 0.05, CY - 0.205, CZ + 0.07), 0.024)
            eye(body,(s * 0.095, CY - 0.18, CZ + 0.055), 0.017)
        for spec in specs:
            leg_tube(body, spec, leg_mat, verts=lay["leg_verts"], knee_bulge=1.05)
        preview_radius = 3.6

    mesh = body.join_spider()
    if kind == "sniper":
        groove_stripes(mats["M_Team"], mesh, ab_center, zscale=0.92, lobes=ab_lobes)
    tris = tri_count(mesh)
    salib.log(f"{variant}: {tris} triangles")
    assert tris < 8000, f"{variant} over budget: {tris} triangles"

    # ---- rig --------------------------------------------------------------------------------
    bones = [
        BoneDef("root", (0, 0, 0), (0, 0.25, 0)),
        BoneDef("body", (0, CY + 0.20, CZ), (0, CY - 0.25, CZ), parent="root"),
        BoneDef("abdomen", (0, CY + 0.24, CZ + 0.04), (0, CY + 0.90, CZ + 0.12), parent="body"),
        BoneDef("head", (0, CY - 0.10, CZ), (0, CY - 0.38, CZ - 0.06), parent="body"),
        BoneDef("fang.L", (0.06, CY - 0.19, CZ - 0.06), (0.06, CY - 0.33, CZ - 0.24), parent="head"),
        BoneDef("fang.R", (-0.06, CY - 0.19, CZ - 0.06), (-0.06, CY - 0.33, CZ - 0.24), parent="head"),
        BoneDef("palp.L", (0.12, CY - 0.18, CZ - 0.04), (0.28, CY - 0.44, CZ - 0.10), parent="head"),
        BoneDef("palp.R", (-0.12, CY - 0.18, CZ - 0.04), (-0.28, CY - 0.44, CZ - 0.10), parent="head"),
    ]
    if kind == "missile":
        bones.append(BoneDef("gun", (0, CY + 0.54, 0.48), (0, CY + 0.54, 0.72), parent="abdomen"))
    for spec in specs:
        bones += salib.leg_bones(spec, parent="body")
    rig = salib.build_armature("Rig", bones)
    salib.skin(mesh, rig)
    # no IK constraints: every clip keys the IK target bones (the feet) and solve_legs() turns them into
    # FK femur / tibia keys (analytic two-bone IK)

    # ---- clips ------------------------------------------------------------------------------
    clips = []
    c = Clip(rig, "idle", 40)
    salib.key_idle(c, specs, 40, body_bob=0.012)
    c.key("abdomen", 1, rot=(0, 0, 0), scale=(1, 1, 1))
    c.key("abdomen", 20, rot=(-3, 0, 0), scale=(1.02, 1.015, 1.02))
    c.key("abdomen", 40, rot=(0, 0, 0), scale=(1, 1, 1))
    for sgn, b in ((1, "palp.L"), (-1, "palp.R")):
        c.key(b, 1, rot=(0, 0, 0)); c.key(b, 12, rot=(10, 0, 6 * sgn)); c.key(b, 28, rot=(-6, 0, -4 * sgn)); c.key(b, 40, rot=(0, 0, 0))
    for sgn, b in ((1, "fang.L"), (-1, "fang.R")):
        c.key(b, 1, rot=(0, 0, 0)); c.key(b, 20, rot=(0, 0, 6 * sgn)); c.key(b, 40, rot=(0, 0, 0))
    act = c.finish()
    leg_report(f"{variant} idle", solve_legs(rig, specs, 1, 40))
    clips.append(act)

    # walk: frames 0..12 (frame 12 = frame 0) so the exported clip spans t = 0 .. 0.4 s and loops
    # seamlessly; 0.4 s -> stride 0.5 cells at the game's 2.5 cells/s
    move_frames = 12
    c = Clip(rig, "move", move_frames)
    lift = {"widow": 0.16, "sniper": 0.12, "missile": 0.15}[kind]
    key_walk(c, rig, specs, move_frames, stride=slide_free_stride(move_frames), lift=lift, body_bob=0.012, first=0)
    for sgn, b in ((1, "palp.L"), (-1, "palp.R")):
        c.key(b, 0, rot=(0, 0, 0)); c.key(b, move_frames // 2, rot=(12, 0, 0)); c.key(b, move_frames, rot=(0, 0, 0))
    act = c.finish()
    act.frame_range = (0, move_frames)
    leg_report(f"{variant} move", solve_legs(rig, specs, 0, move_frames))
    clips.append(act)

    c = Clip(rig, "attack", 12, loop=False)
    key_feet_rest(c, specs, 12)
    if kind == "widow":
        # rear up, lunge forward and bite: fangs spread then stab down; the front legs rise
        c.key("body", 1, loc=(0, 0, 0), rot=(0, 0, 0)); c.key("body", 4, loc=(0, -0.04, 0.05), rot=(16, 0, 0))
        c.key("body", 7, loc=(0, 0.12, -0.02), rot=(-4, 0, 0)); c.key("body", 12, loc=(0, 0, 0), rot=(0, 0, 0))
        for sgn, b in ((1, "fang.L"), (-1, "fang.R")):
            c.key(b, 1, rot=(0, 0, 0)); c.key(b, 4, rot=(-35, 0, 28 * sgn)); c.key(b, 7, rot=(25, 0, -8 * sgn)); c.key(b, 12, rot=(0, 0, 0))
        for sgn, b in ((1, "palp.L"), (-1, "palp.R")):
            c.key(b, 1, rot=(0, 0, 0)); c.key(b, 4, rot=(30, 0, 20 * sgn)); c.key(b, 12, rot=(0, 0, 0))
        for name in ("L1", "R1"):
            spec = next(s for s in specs if s.name == name)
            key_foot(c, rig, spec, 1, (0, 0, 0)); key_foot(c, rig, spec, 4, (0.08 * spec.side, -0.05, 0.42))
            key_foot(c, rig, spec, 8, (0, -0.10, 0.0)); key_foot(c, rig, spec, 12, (0, 0, 0))
    elif kind == "sniper":
        # the shot leaves the carapace (the sprite's flash): the body kicks back and up (body bone points
        # -Y, so local -Y is backward and +X pitch lifts the front), the abdomen and the palps follow
        c.key("body", 1, loc=(0, 0, 0), rot=(0, 0, 0)); c.key("body", 2, loc=(0, -0.05, 0.015), rot=(7, 0, 0))
        c.key("body", 5, loc=(0, -0.02, 0.005), rot=(2, 0, 0)); c.key("body", 10, loc=(0, 0, 0), rot=(0, 0, 0))
        c.key("abdomen", 1, rot=(0, 0, 0)); c.key("abdomen", 3, rot=(-5, 0, 0)); c.key("abdomen", 10, rot=(0, 0, 0))
        for sgn, b in ((1, "palp.L"), (-1, "palp.R")):
            c.key(b, 1, rot=(0, 0, 0)); c.key(b, 3, rot=(14, 0, 8 * sgn)); c.key(b, 10, rot=(0, 0, 0))
    else:
        # launcher kicks, the whole spider squats under the launch
        c.key("gun", 1, loc=(0, 0, 0), rot=(0, 0, 0)); c.key("gun", 2, loc=(0, -0.02, 0.0), rot=(-8, 0, 0)); c.key("gun", 8, loc=(0, 0, 0), rot=(0, 0, 0))
        c.key("body", 1, loc=(0, 0, 0), rot=(0, 0, 0)); c.key("body", 3, loc=(0, 0, -0.05), rot=(-5, 0, 0)); c.key("body", 10, loc=(0, 0, 0), rot=(0, 0, 0))
        c.key("abdomen", 1, rot=(0, 0, 0)); c.key("abdomen", 3, rot=(6, 0, 0)); c.key("abdomen", 10, rot=(0, 0, 0))
    act = c.finish()
    leg_report(f"{variant} attack", solve_legs(rig, specs, 1, 12))
    clips.append(act)

    c = Clip(rig, "death", 36, loop=False)
    # the body jerks up, then drops onto the ground and rolls part way onto its side while the legs go
    # limp and splay around it (below).  The drop puts the belly of the cephalothorax on the ground (its
    # underside is CZ - half its height above the ground at rest); the compact sniper / missile roll
    # less than the long-legged widow, else the hips of the low side end up so close to the ground
    # that no knee can clear it.
    drop, roll = {"widow": (0.134, 32.0), "sniper": (0.100, 16.0), "missile": (0.076, 16.0)}[kind]
    c.key("body", 1, loc=(0, 0, 0), rot=(0, 0, 0)); c.key("body", 10, loc=(0, 0, 0.04), rot=(10, 0, 0))
    c.key("body", 36, loc=(0, 0, -drop), rot=(0, roll, 0))
    c.key("abdomen", 1, rot=(0, 0, 0)); c.key("abdomen", 36, rot=(14, 0, 0))
    for sgn, b in ((1, "fang.L"), (-1, "fang.R")):
        c.key(b, 1, rot=(0, 0, 0)); c.key(b, 36, rot=(-20, 0, 15 * sgn))
    # legs: a spasm (feet twitch up), then they splay outward and settle flat on the ground around the
    # fallen body - the dead sprite's legs lie spread around the tipped body.  (A curled-up pose was
    # tried first: the game sinks a corpse 0.45 cells into the ground over 8 s, and the curled legs, knees
    # up to 0.9, stood out of the ground like a bundle of sticks for the whole time.)
    splay = {"widow": 0.16, "sniper": 0.11, "missile": 0.14}[kind]
    for spec in specs:
        out = Vector((spec.foot[0] - spec.root[0], spec.foot[1] - spec.root[1], 0.0)).normalized()
        key_foot(c, rig, spec, 1, (0, 0, 0))
        key_foot(c, rig, spec, 10, (0, 0, 0.06))
        key_foot(c, rig, spec, 22, tuple(out * (splay * 0.6) + Vector((0, 0, 0.04))))
        key_foot(c, rig, spec, 36, tuple(out * splay))
    act = c.finish()

    def death_twist(f, f0=10, f1=36, top=math.radians(70)):
        # after the spasm the legs go limp: the knees sag sideways and down as the feet splay
        t = min(1.0, max(0.0, (f - f0) / (f1 - f0)))
        return top * t * t * (3 - 2 * t)

    leg_report(f"{variant} death", solve_legs(rig, specs, 1, 36, twist=death_twist))
    clips.append(act)
    salib.bake_actions(rig, clips)

    path, s = salib.finalize_asset(variant, [rig, mesh], preview_radius=preview_radius, preview_center=(0, 0, 0.3),
                                   views=("front", "back", "left", "right", "threequarter", "top"))
    assert sorted(a["name"] for a in s["animations"]) == ["attack", "death", "idle", "move"]
    assert "M_Team" in s["materials"], s["materials"]
    return path


if __name__ == "__main__":
    args = [a for a in salib.script_args() if not a.startswith("-")] or list(VARIANTS)
    for v in args:
        build(v)
        print("BUILT", v, flush=True)
