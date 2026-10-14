"""Builds every flying unit: the wasp family and the four neutral flyers (faithful-recreation pass).

References (reference/models/<asset>/ + _common loading/title screens of the 1999 original):
* Wasps are *thread-waisted* in the original renders: a big dark head with a team-coloured cap, a
  black hunched thorax with a team collar, a long thin petiole that rises to a small banded abdomen
  held high behind the body, two long narrow translucent wings swept back in a V, six long dangling
  legs (dark femora, tan tibiae) and the weapon slung under the thorax.
  - wasp_assault: compact, grey machine gun under the thorax.
  - wasp_paralysis: ~1.3x bigger, longer stalk and abdomen, smoky darker wings, a dark launcher tube
    with a glowing green paralysis-arrow tip under the thorax.
  - wasp_sonic: stocky hornet: team-coloured head with black eyes, short petiole, big boldly striped
    abdomen, team-coloured legs splayed sideways like a bee, a black bell-mouthed sonic horn under
    the head.
* neutral_dragonfly: long green abdomen with dark rings, teal thorax with green/orange stripes, two
  huge blue eyes, four long pale wings, black legs bunched forward, two grey brake bombs underneath.
* neutral_desert_fly: big dark fly, striped grey thorax dome, banded abdomen, huge green compound
  eyes, two broad cream wings, long black legs splayed out.
* neutral_spawn_moth: slim furry brown body, feathery antennae, four broad tan wings with dark
  radial streaks and an eye-spot bar on each (custom procedural wing material).
* neutral_flying_machine: wooden boat hull with a golden gunwale, mast + four-blade pink rotor,
  tail boom with a vertical pink tail prop, red wheels, grey gearbox and a black pirate-ant pilot.
Top-down silhouettes follow the in-game sprites (wings spread sideways, body a banded stick).

Rig: root > body > {head > antennae, petiole > abdomen, wing bones, leg.<side><n>.up > .low, gun}.
Wing beat = flap about the wing root's local X (up/down) + a fore/aft sweep about local Z so the
silhouette changes from above like the three sprite frames (swept back / lateral / forward).
Clips: idle (hover), fly (the game plays this for hovering and moving), attack (recoil), death
(wings fold, legs curl, body rolls over; the game lowers the flyer to the ground meanwhile).

Usage: blender -b --factory-startup --python build_flyers.py -- [--quick] asset...
  --quick: geometry + rig + clips only, EEVEE previews into qa/agents/wasps_flyers/quick (no bake,
  no export) for fast iteration.

Pose-bone sign conventions used below (roll-0 bones): body/head bones point forward (-Y), so
rot X > 0 = nose up and loc Y > 0 = forward; abdomen bones point backward, rot X > 0 = tip up;
a bone spins about its own axis with rot Y.
"""
import json
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import salib  # noqa: E402
from salib import BoneDef, Body, Clip  # noqa: E402

QUICK_DIR = r"D:\SwarmAssault3D-complete\qa\agents\wasps_flyers\quick"

VARIANTS = {
    "wasp_assault": dict(kind="wasp", style="thread", weapon="gun", S=0.92),
    "wasp_paralysis": dict(kind="wasp", style="thread", weapon="arrow", S=1.22),
    "wasp_sonic": dict(kind="wasp", style="stocky", weapon="sonic", S=1.05),
    "neutral_dragonfly": dict(kind="dragonfly"),
    "neutral_desert_fly": dict(kind="fly"),
    "neutral_spawn_moth": dict(kind="moth"),
    "neutral_flying_machine": dict(kind="machine"),
}

Z0 = 0.45  # body centre height in the model (the game adds the flight altitude)


def rad(a):
    return math.radians(a)


# --------------------------------------------------------------------------------------------
# extra primitives (local copies: salib is shared and must not be edited)
# --------------------------------------------------------------------------------------------
class BodyX(Body):
    """salib.Body plus banded ellipsoids, custom wing blades, stadium plates and bowl hulls."""

    def banded(self, bone, mats, center, radius, scale=(1, 1, 1), bands=(), axis="Y", segments=16, rings=12,
               tilt=0.0, subdiv=True):
        """UV sphere whose polygons get materials by position along its pole axis.

        `scale` is (width, height, length): width across X, height along Z, length along the pole
        axis.  `axis` "Y" puts the poles along the body axis (bands = rings around Y, transverse
        stripes), "X" puts them sideways (rings around X = fore/aft stripes seen from above).
        `bands` = [(lo, hi, material)] in -1..1 along the pole axis; +1 is the FRONT (-Y) for axis
        "Y" and the LEFT (+X) for axis "X".  `tilt` (degrees) pitches a "Y" ellipsoid nose-down.
        """
        bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, segments=segments, ring_count=rings, location=center)
        o = bpy.context.object
        w, h, length = scale
        if axis == "Y":
            o.scale = (w, h, length)
            o.rotation_euler = (rad(90.0 + tilt), 0, 0)  # local +Z -> global -Y (front)
        else:
            o.scale = (h, length, w)  # Ry(90): local X -> -Z, local Y -> Y, local Z -> +X
            o.rotation_euler = (0, rad(90.0), 0)
        self._finish(o, bone, mats[0])
        if not subdiv:
            o["sa_no_subdiv"] = True
        me = o.data
        for m in mats[1:]:
            if self.materials[m].name not in [s.name for s in me.materials]:
                me.materials.append(self.materials[m])
        slot = {s.name: i for i, s in enumerate(me.materials)}
        for p in me.polygons:
            t = p.center.z / radius
            for lo, hi, m in bands:
                if lo <= t < hi:
                    p.material_index = slot[self.materials[m].name]
                    break
        return o

    def blade(self, bone, mat, root, tip, width, profile="wasp", thickness=0.012, curve=0.0, segments=14, wing_id=0.0):
        """Flat wing from root to tip with a species-specific outline; `width` is the largest chord.

        The leading edge faces forward (-Y) on BOTH sides (the outline is not mirrored per side).
        Every vertex carries a `wingco` point attribute (x = t: 0 root .. 1 tip, y = s: -1 leading
        edge .. +1 trailing edge, z = wing_id) that the wing materials use for venation/patterns.
        profile: "wasp" (narrow strap, widest at 2/3, rounded tip), "sonic" (broader wasp wing),
        "dragon" (long, nearly parallel sides, rounded tip), "fly" (elongated ellipse, narrow root),
        "moth_fore"/"moth_hind" (broad, almost rectangular, rounded corners).
        """
        root, tip = Vector(root), Vector(tip)
        n = (tip - root).normalized()
        back = (Vector((0, 1, 0)) - n * n.y).normalized()  # +Y made perpendicular to the span

        def tip_round(t, t0, floor=0.10):
            if t <= t0:
                return 1.0
            return max(floor, math.sqrt(max(0.0, 1.0 - ((t - t0) / (1.0 - t0)) ** 2)))

        verts, faces, coords = [], [], []
        # uniform samples plus a few extra near the tip, where the outline rounds off
        ts = sorted({round(i / segments, 4) for i in range(segments + 1)} | {0.86, 0.92, 0.96, 0.985})
        segments = len(ts) - 1
        for t in ts:
            p = root.lerp(tip, t)
            if profile == "wasp":
                c = width * (0.30 + 0.70 * math.sin(0.5 * math.pi * min(1.0, t / 0.66))) * tip_round(t, 0.78)
                lead = 0.36
            elif profile == "sonic":
                c = width * (0.34 + 0.66 * math.sin(0.5 * math.pi * min(1.0, t / 0.60))) * tip_round(t, 0.70)
                lead = 0.40
            elif profile == "dragon":
                c = width * (0.62 + 0.38 * math.sin(0.5 * math.pi * min(1.0, t / 0.30))) * tip_round(t, 0.84)
                lead = 0.42
            elif profile == "fly":
                c = width * max(0.24, math.sin(math.pi * min(1.0, 0.03 + 0.97 * t)) ** 0.62)
                lead = 0.40
            elif profile == "moth_fore":
                c = width * (0.52 + 0.48 * math.sin(0.5 * math.pi * min(1.0, t / 0.22))) * tip_round(t, 0.82, 0.45)
                lead = 0.38
            else:  # moth_hind
                c = width * (0.50 + 0.50 * math.sin(0.5 * math.pi * min(1.0, t / 0.25))) * tip_round(t, 0.72, 0.30)
                lead = 0.50
            z = Vector((0, 0, curve * t * t))
            verts.append(p - back * (c * lead) + z)
            verts.append(p + back * (c * (1.0 - lead)) + z)
            coords += [(t, -1.0, wing_id), (t, 1.0, wing_id)]
        for i in range(segments):
            a = i * 2
            faces.append((a, a + 1, a + 3, a + 2))
        me = bpy.data.meshes.new(f"{self.name}_blade")
        me.from_pydata([tuple(v) for v in verts], [], faces)
        attr = me.attributes.new("wingco", "FLOAT_VECTOR", "POINT")
        for i, co in enumerate(coords):
            attr.data[i].vector = co
        me.update()
        o = bpy.data.objects.new(f"{self.name}_blade", me)
        salib.link(o)
        mod = o.modifiers.new("Solidify", "SOLIDIFY")
        mod.thickness = thickness
        mod.offset = 0.0
        bpy.context.view_layer.objects.active = o
        o.select_set(True)
        bpy.ops.object.modifier_apply(modifier=mod.name)
        o["sa_no_subdiv"] = True
        return self._finish(o, bone, mat)

    def plate(self, bone, mat, center, length, width, thickness, rot=(0, 0, 0), verts=10, corner=None):
        """Flat plate, length along local X: stadium-shaped (semicircular ends) or, with `corner`, a
        rectangle with corners rounded to that radius (paddle blades)."""
        pts = []
        if corner is None:
            r = width / 2
            half = max(0.0, length / 2 - r)
            for i in range(verts + 1):  # right cap
                a = -math.pi / 2 + math.pi * i / verts
                pts.append((half + r * math.cos(a), r * math.sin(a), 0.0))
            for i in range(verts + 1):  # left cap
                a = math.pi / 2 + math.pi * i / verts
                pts.append((-half + r * math.cos(a), r * math.sin(a), 0.0))
        else:
            r = min(corner, width / 2, length / 2)
            hx, hy = length / 2 - r, width / 2 - r
            for cx, cy, a0 in ((hx, -hy, -90.0), (hx, hy, 0.0), (-hx, hy, 90.0), (-hx, -hy, 180.0)):
                for i in range(4):
                    a = math.radians(a0 + 90.0 * i / 3)
                    pts.append((cx + r * math.cos(a), cy + r * math.sin(a), 0.0))
        me = bpy.data.meshes.new(f"{self.name}_plate")
        me.from_pydata(pts, [], [tuple(range(len(pts)))])
        me.update()
        o = bpy.data.objects.new(f"{self.name}_plate", me)
        salib.link(o)
        o.location = center
        o.rotation_euler = rot
        bpy.context.view_layer.objects.active = o
        o.select_set(True)
        mod = o.modifiers.new("Solidify", "SOLIDIFY")
        mod.thickness = thickness
        mod.offset = 0.0
        bpy.ops.object.modifier_apply(modifier=mod.name)
        o["sa_no_subdiv"] = True
        return self._finish(o, bone, mat)

    def bowl(self, bone, mat, center, radius, scale=(1, 1, 1), thickness=0.04, segments=20, rings=12):
        """Lower half of an ellipsoid with a solid wall (boat hull)."""
        bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, segments=segments, ring_count=rings, location=center)
        o = bpy.context.object
        o.scale = scale
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z > 1e-4], context="VERTS")
        bm.to_mesh(o.data)
        bm.free()
        mod = o.modifiers.new("Solidify", "SOLIDIFY")
        mod.thickness = thickness
        mod.offset = -1.0
        bpy.ops.object.modifier_apply(modifier=mod.name)
        return self._finish(o, bone, mat)

    def lowpoly(self, obj):
        obj["sa_no_subdiv"] = True
        return obj

    def join_at_origin(self):
        """Join the parts and move the object origin to the world origin (so Object texture
        coordinates equal rest-pose world coordinates and the glTF mesh node has no offset)."""
        obj = self.join()
        bpy.context.scene.cursor.location = (0, 0, 0)
        salib.select_only([obj])
        bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
        return obj


def leg(body, name, mat_up, mat_low, coxa, knee, foot, r=0.03, toe=None, mat_joint=None, verts=7, foot_k=0.72,
        mat_tarsus=None):
    """Jointed insect leg (low-poly, no subdivision): coxa ball + femur to the knee (bone .up);
    knee ball + tibia + ankle ball + tarsus + claw to the foot tip (bone .low).  `toe` is the claw's
    end point (defaults to a little forward and down of the foot); `mat_tarsus` colours the tarsus
    (defaults to the tibia's material)."""
    coxa, knee, foot = Vector(coxa), Vector(knee), Vector(foot)
    mj = mat_joint or mat_up
    up, low = f"{name}.up", f"{name}.low"
    ankle = knee.lerp(foot, foot_k)
    toe = Vector(toe) if toe else foot + Vector((0, -0.06, -0.02))
    body.lowpoly(body.sphere(up, mj, tuple(coxa), r * 1.35, segments=8, rings=5))
    body.lowpoly(body.segment(up, mat_up, tuple(coxa), tuple(knee), r * 1.0, r * 0.8, verts=verts))
    body.lowpoly(body.sphere(low, mj, tuple(knee), r * 1.05, segments=8, rings=5))
    body.lowpoly(body.segment(low, mat_low, tuple(knee), tuple(ankle), r * 0.75, r * 0.5, verts=verts))
    body.lowpoly(body.sphere(low, mj, tuple(ankle), r * 0.62, segments=8, rings=5))
    body.lowpoly(body.segment(low, mat_tarsus or mat_low, tuple(ankle), tuple(foot), r * 0.48, r * 0.3, verts=verts))
    body.lowpoly(body.segment(low, mj, tuple(foot), tuple(toe), r * 0.3, r * 0.05, verts=5))
    return [BoneDef(up, tuple(coxa), tuple(knee), parent="body"),
            BoneDef(low, tuple(knee), tuple(foot), parent=up, connect=True)]


# --------------------------------------------------------------------------------------------
# materials
# --------------------------------------------------------------------------------------------
def flyer_materials():
    m = salib.standard_materials("Y", neutral=False)
    mat = salib.material
    # wasps
    # wasp wings: smooth translucent grey-beige straps with a few dark veins (portraits / sprites)
    m["M_Wing"] = wing_material("M_Wing", (0.88, 0.86, 0.82), alpha=0.58, vein_color=(0.24, 0.21, 0.17), layout="wasp",
                                root_color=(0.62, 0.58, 0.52))
    m["M_WingDark"] = wing_material("M_WingDark", (0.80, 0.76, 0.72), alpha=0.62, vein_color=(0.18, 0.15, 0.12),
                                    layout="wasp", root_color=(0.50, 0.45, 0.40))
    m["M_Tan"] = mat("M_Tan", (0.74, 0.60, 0.30), roughness=0.5, kind="chitin", variation=0.3)
    m["M_Brown"] = mat("M_Brown", (0.22, 0.13, 0.08), roughness=0.5, kind="chitin", variation=0.3)
    m["M_Maroon"] = mat("M_Maroon", (0.32, 0.12, 0.09), roughness=0.45, kind="chitin", variation=0.3)
    m["M_LegBrown"] = mat("M_LegBrown", (0.40, 0.27, 0.16), roughness=0.5, kind="chitin", variation=0.3)
    m["M_EyeRed"] = mat("M_EyeRed", (0.32, 0.07, 0.05), roughness=0.1, kind="glossy")
    m["M_Green"] = mat("M_Green", (0.25, 0.95, 0.25), roughness=0.2, emission=(0.2, 0.9, 0.2), emission_strength=1.2,
                       kind="emissive")
    m["M_Gun"] = mat("M_Gun", (0.52, 0.52, 0.55), roughness=0.4, metallic=0.9, kind="metal")
    # dragonfly
    m["M_Teal"] = mat("M_Teal", (0.16, 0.42, 0.58), roughness=0.3, kind="chitin", coat=0.9, variation=0.5)
    m["M_DfGreen"] = mat("M_DfGreen", (0.42, 0.80, 0.22), roughness=0.3, kind="chitin", coat=0.9, variation=0.5)
    m["M_DfDark"] = mat("M_DfDark", (0.06, 0.10, 0.26), roughness=0.3, kind="chitin", coat=0.9, variation=0.3)
    m["M_DfOrange"] = mat("M_DfOrange", (0.85, 0.50, 0.18), roughness=0.3, kind="chitin", coat=0.9, variation=0.4)
    m["M_DfEye"] = mat("M_DfEye", (0.22, 0.58, 0.78), roughness=0.08, kind="glossy", emission=(0.1, 0.3, 0.45),
                       emission_strength=0.25)
    m["M_DfWing"] = wing_material("M_DfWing", (0.84, 0.80, 0.74), alpha=0.66, vein_color=(0.30, 0.25, 0.20),
                                  layout="dragon", root_color=(0.55, 0.50, 0.44))
    m["M_DfWingFore"] = wing_material("M_DfWingFore", (0.74, 0.68, 0.61), alpha=0.68, vein_color=(0.25, 0.20, 0.15),
                                      layout="dragon", root_color=(0.45, 0.40, 0.34))
    m["M_Bomb"] = mat("M_Bomb", (0.40, 0.42, 0.40), roughness=0.5, metallic=0.7, kind="metal")
    # desert fly
    # olive-brown body (sprite), mottled grey-brown thorax stripes (portrait)
    m["M_FlyGrey"] = mat("M_FlyGrey", (0.44, 0.38, 0.27), roughness=0.75, kind="fur", variation=0.4)
    m["M_FlyDark"] = mat("M_FlyDark", (0.15, 0.13, 0.10), roughness=0.7, kind="fur", variation=0.3)
    m["M_FlyRim"] = mat("M_FlyRim", (0.60, 0.30, 0.10), roughness=0.15, kind="glossy")
    m["M_FlyEye"] = mat("M_FlyEye", (0.25, 0.90, 0.22), roughness=0.1, kind="glossy", emission=(0.1, 0.5, 0.1),
                        emission_strength=0.35)
    # iridescent: greenish smoky root to a pale blue-grey tip (the sprite shows green / blue / white wings)
    m["M_FlyWing"] = wing_material("M_FlyWing", (0.80, 0.86, 0.90), alpha=0.68, vein_color=(0.20, 0.22, 0.18),
                                   layout="fly", root_color=(0.42, 0.52, 0.36), tip_color=(0.78, 0.84, 0.92))
    # moth
    m["M_MothBody"] = mat("M_MothBody", (0.42, 0.29, 0.16), roughness=0.85, kind="fur", variation=0.4)
    m["M_MothTan"] = mat("M_MothTan", (0.74, 0.58, 0.34), roughness=0.85, kind="fur", variation=0.4)
    m["M_MothWing"] = moth_wing_material("M_MothWing")
    # flying machine
    m["M_Wood"] = mat("M_Wood", (0.40, 0.24, 0.12), roughness=0.8, kind="wood")
    m["M_Gold"] = mat("M_Gold", (0.80, 0.60, 0.28), roughness=0.55, kind="wood")
    m["M_Pink"] = mat("M_Pink", (0.84, 0.62, 0.86), roughness=0.4, kind="organic", variation=0.15, coat=0.5)
    m["M_Red"] = mat("M_Red", (0.78, 0.12, 0.10), roughness=0.3, kind="glossy")
    m["M_PaleBlue"] = mat("M_PaleBlue", (0.70, 0.80, 0.95), roughness=0.1, kind="glossy")
    m["M_Frame"] = mat("M_Frame", (0.46, 0.45, 0.34), roughness=0.45, metallic=0.6, kind="metal")
    return m


# Venation layouts in wing space (t = 0 root .. 1 tip, s = -1 leading .. +1 trailing edge):
# longitudinal veins as lines s = s0 + k*t (t0..t1), cross-veins at t (s range), the costa (leading
# edge) width and the pterostigma (t, half-length) or None.
VEINS = {
    "wasp": dict(long=[(-0.55, 0.10, 0.0, 0.80), (-0.12, 0.22, 0.0, 0.88), (0.30, 0.22, 0.05, 0.85), (0.70, 0.10, 0.1, 0.62)],
                 cross=[(0.42, -0.55, 0.30), (0.58, -0.40, 0.55), (0.70, -0.45, 0.10)], costa=0.20, stigma=(0.64, 0.05),
                 width=0.045),
    "dragon": dict(long=[(-0.62, 0.0, 0.0, 0.96), (-0.30, 0.05, 0.0, 0.95), (0.05, 0.06, 0.0, 0.90), (0.42, 0.03, 0.0, 0.80)],
                   cross=[(0.30, -0.65, -0.30)], costa=0.14, stigma=(0.86, 0.035), width=0.028),
    "fly": dict(long=[(-0.45, 0.20, 0.0, 0.92), (-0.05, 0.25, 0.0, 0.95), (0.30, 0.18, 0.0, 0.90), (0.62, 0.05, 0.05, 0.70)],
                cross=[(0.38, -0.45, 0.30), (0.62, -0.05, 0.45)], costa=0.18, stigma=None, width=0.04),
    "moth": dict(long=[], cross=[], costa=0.08, stigma=None, width=0.025),
}


def _attr_node(nt, name):
    node = nt.nodes.new("ShaderNodeAttribute")
    node.attribute_type = "GEOMETRY"
    node.attribute_name = name
    return node


def _remap(nt, value, a, b):
    """Clamped linear step: 0 at value == a, 1 at value == b (a > b allowed).  Note salib._map_range
    is the opposite direction (0..1 -> lo..hi)."""
    m = nt.nodes.new("ShaderNodeMapRange")
    m.clamp = True
    m.inputs["From Min"].default_value = a
    m.inputs["From Max"].default_value = b
    m.inputs["To Min"].default_value = 0.0
    m.inputs["To Max"].default_value = 1.0
    nt.links.new(value, m.inputs["Value"])
    return m.outputs["Result"]


def _near(nt, value, center, half_width):
    """1 at |value - center| = 0 falling to 0 at half_width (clamped)."""
    d = salib._math(nt, "ABSOLUTE", salib._math(nt, "SUBTRACT", value, center))
    return _remap(nt, d, half_width, 0.0)


def _inside(nt, value, lo, hi, soft=0.03):
    """1 for lo < value < hi with soft edges (clamped)."""
    a = _remap(nt, value, lo - soft, lo + soft)
    b = _remap(nt, value, hi + soft, hi - soft)
    return salib._math(nt, "MULTIPLY", a, b)


def wing_venation(nt, t, s, layout):
    """0..1 vein mask from the wing-space coordinates (sockets t, s)."""
    lay = VEINS[layout]
    w = lay["width"]
    mask = _remap(nt, s, -1.0 + lay["costa"], -1.0)  # thick costa along the leading edge
    for s0, k, t0, t1 in lay["long"]:
        line = salib._math(nt, "ADD", s0, salib._math(nt, "MULTIPLY", t, k))
        v = salib._math(nt, "MULTIPLY", _near(nt, s, line, w), _inside(nt, t, t0, t1))
        mask = salib._math(nt, "MAXIMUM", mask, v)
    for tc, sa, sb in lay["cross"]:
        v = salib._math(nt, "MULTIPLY", _near(nt, t, tc, w * 0.35), _inside(nt, s, sa, sb))
        mask = salib._math(nt, "MAXIMUM", mask, salib._math(nt, "MULTIPLY", v, 0.8))
    if lay["stigma"]:
        tc, hl = lay["stigma"]
        v = salib._math(nt, "MULTIPLY", _inside(nt, t, tc - hl, tc + hl, 0.01), _remap(nt, s, -0.62, -0.78))
        mask = salib._math(nt, "MAXIMUM", mask, v)
    return mask


def wing_material(name, color, alpha=0.62, roughness=0.55, vein_color=(0.36, 0.29, 0.22), layout="wasp",
                  root_color=None, tip_color=None, bump=0.10):
    """Translucent insect wing: smooth membrane with a few dark veins laid out in wing space (costa,
    longitudinal veins, cross-veins, pterostigma; see VEINS), an optional root->tip colour gradient
    (smoky base / iridescent tint) and a faint bump.  No clearcoat: the export material would give it
    a sharp sun blob."""
    if not salib.REALISM:
        return salib.material(name, color, roughness=roughness, alpha=alpha)
    lin = salib._lin(color)
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.name = "Principled"
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    texco = nt.nodes.new("ShaderNodeTexCoord")
    coord = texco.outputs["Object"]
    wc = _attr_node(nt, "wingco")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(wc.outputs["Vector"], sep.inputs["Vector"])
    t, s = sep.outputs["X"], sep.outputs["Y"]
    # membrane: root -> tip gradient with a little cloudy variation
    grad = nt.nodes.new("ShaderNodeValToRGB")
    grad.color_ramp.elements[0].position = 0.0
    grad.color_ramp.elements[0].color = salib._lin(root_color) if root_color else salib._scale_color(lin, 0.86)
    grad.color_ramp.elements[1].position = 1.0
    grad.color_ramp.elements[1].color = salib._lin(tip_color) if tip_color else lin
    nt.links.new(t, grad.inputs["Fac"])
    n1 = salib._noise(nt, coord, 6.0, detail=3.0, roughness=0.5)
    cloud = salib._map_range(nt, n1.outputs["Factor"], 0.93, 1.05)
    base = salib._mix_rgb(nt, "MULTIPLY", grad.outputs["Color"], cloud, 1.0)
    vein = wing_venation(nt, t, s, layout)
    base = salib._mix_rgb(nt, "MIX", base, salib._lin(vein_color), 1.0)
    # the mix factor of that node is the vein mask (veins a little transparent-looking, not inked)
    nt.links.new(salib._math(nt, "MULTIPLY", vein, 0.8), base.node.inputs[0])
    nt.links.new(base, bsdf.inputs["Base Color"])
    bmp = nt.nodes.new("ShaderNodeBump")
    bmp.inputs["Strength"].default_value = bump
    bmp.inputs["Distance"].default_value = 0.01
    nt.links.new(vein, bmp.inputs["Height"])
    nt.links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Alpha"].default_value = alpha
    bsdf.inputs["Specular IOR Level"].default_value = 0.3
    bsdf.inputs["Coat Weight"].default_value = 0.0  # no clearcoat: the export material would give it a sharp sun blob
    mat.surface_render_method = "BLENDED" if alpha < 1.0 else "DITHERED"
    mat.diffuse_color = lin
    mat.roughness = roughness
    mat["sa_kind"] = "membrane"
    mat["sa_tint"] = False
    mat["sa_alpha"] = alpha
    mat["sa_metallic"] = 0.0
    mat["sa_coat"] = 0.0
    mat["sa_emission"] = [0.0, 0.0, 0.0, 1.0]
    mat["sa_emission_strength"] = 0.0
    mat["sa_color"] = list(lin)
    return mat


def moth_wing_material(name):
    """Golden-tan moth wing with dark brown stripes running along the wing (root to tip) and, on the
    forewings, a dark oval eye-spot in a pale ring (portrait + sprite).  Laid out in wing space
    (`wingco`: t, s, wing_id 1 = forewing / 0 = hindwing).  Built on the AO-free wing material:
    salib's "organic" kind bakes a thin double-sided wing almost black because its ambient-occlusion
    dirt term sees the opposite face."""
    mat = wing_material(name, (0.90, 0.72, 0.48), alpha=1.0, roughness=0.85, vein_color=(0.55, 0.40, 0.22),
                        layout="moth", root_color=(0.76, 0.58, 0.36), bump=0.0)
    if not salib.REALISM:
        return mat
    nt = mat.node_tree
    bsdf = salib._principled(mat)
    base_link = next((l for l in nt.links if l.to_socket == bsdf.inputs["Base Color"]), None)
    base_src = base_link.from_socket if base_link else None
    wc = _attr_node(nt, "wingco")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(wc.outputs["Vector"], sep.inputs["Vector"])
    t, s, fore = sep.outputs["X"], sep.outputs["Y"], sep.outputs["Z"]
    wob = salib._math(nt, "MULTIPLY", salib._math(nt, "SINE", salib._math(nt, "MULTIPLY", t, 9.0)), 0.05)

    def band(s0, hw, t0, t1, soft=0.06):
        """flat-topped band along the wing (|s - s0| < hw) with soft edges, between t0 and t1"""
        d = salib._math(nt, "ABSOLUTE", salib._math(nt, "SUBTRACT", s, salib._math(nt, "ADD", wob, s0)))
        return salib._math(nt, "MULTIPLY", _remap(nt, d, hw + soft, hw - soft), _inside(nt, t, t0, t1, 0.06))

    def union(*masks):
        m = masks[0]
        for x in masks[1:]:
            m = salib._math(nt, "MAXIMUM", m, x)
        return m

    # forewing (sprite): thin ochre-brown streaks along the leading part + the eye-spot in the inner third
    fore_m = union(band(-0.82, 0.05, 0.12, 0.97, 0.03), band(-0.62, 0.05, 0.18, 0.96, 0.03), band(-0.42, 0.04, 0.30, 0.92, 0.03))
    dt = salib._math(nt, "DIVIDE", salib._math(nt, "SUBTRACT", t, 0.34), 0.13)
    ds = salib._math(nt, "DIVIDE", salib._math(nt, "SUBTRACT", s, 0.16), 0.30)
    r = salib._math(nt, "SQRT", salib._math(nt, "ADD", salib._math(nt, "MULTIPLY", dt, dt), salib._math(nt, "MULTIPLY", ds, ds)))
    spot_core = _remap(nt, r, 0.85, 0.65)
    ring = salib._math(nt, "MULTIPLY", _remap(nt, r, 0.80, 0.95), _remap(nt, r, 1.30, 1.10))
    fore_m = salib._math(nt, "MAXIMUM", salib._math(nt, "MULTIPLY", fore_m, salib._math(nt, "SUBTRACT", 1.0, ring)), spot_core)
    # hindwing (sprite): one broad dark grey-brown band along the middle of the wing
    hind_m = salib._math(nt, "MULTIPLY", band(-0.06, 0.26, 0.04, 0.94, 0.08), 0.85)
    mask = salib._math(nt, "ADD", salib._math(nt, "MULTIPLY", fore_m, fore),
                       salib._math(nt, "MULTIPLY", hind_m, salib._math(nt, "SUBTRACT", 1.0, fore)))
    dark = salib._mix_rgb(nt, "MIX", (1, 1, 1, 1), salib._lin((0.36, 0.23, 0.12)), 1.0)
    nt.links.new(mask, dark.node.inputs[0])
    final = salib._mix_rgb(nt, "MULTIPLY", base_src, dark, 1.0) if base_src is not None else dark
    lift = salib._mix_rgb(nt, "MIX", final, salib._lin((0.96, 0.86, 0.62)), 1.0)  # pale ring around the spot
    nt.links.new(salib._math(nt, "MULTIPLY", salib._math(nt, "MULTIPLY", ring, fore), 0.75), lift.node.inputs[0])
    nt.links.new(lift, bsdf.inputs["Base Color"])
    return mat


# --------------------------------------------------------------------------------------------
# wasps
# --------------------------------------------------------------------------------------------
def build_wasp(body, cfg):
    """Returns (bones, wing_specs, leg_up_bone_names, extras) for the three wasps.

    Proportions are read off the top-down sprites (24 px = 1 unit, body lengths 24 / 39 / 31 px) and
    the original renders (selection portraits, loading screen 0, title screen):
    * assault: thread-waisted: black head with a team cap and dark-red eyes, black thorax with a team
      collar, a thin petiole rising steeply (~50 deg) to a small banded abdomen held up behind the
      thorax (from above it reads as the sprite's banded chain), long narrow wings, maroon femora and
      pale tibiae, gun under the head.
    * paralysis: big head with a team cap, big black thorax with team marks, a SHORT waist and a long,
      nearly horizontal abdomen with three team bands, very long narrow smoky wings, long brown legs
      splayed wide, the green-tipped arrow launcher tucked under the head.
    * sonic: stocky bee-like hornet: team head with a black face and eyes, team thorax with thin black
      stripes, no visible waist, big striped abdomen, broad wings, team legs with black joints and
      feet, the black sonic bell under the face.
    Legs dangle in flight: femora reach out sideways and down (they show beside the body from above,
    as in the sprites), knees bend, tibiae hang almost vertically (portraits).
    """
    weapon = cfg["weapon"]
    z = Z0
    T, K = "M_Team", "M_Black"

    def P(x, y, dz):
        return (x, y, z + dz)

    bones = []

    def antennae(pts, r):
        a0, a1, a2 = pts
        for s, nm in ((+1, "antenna.L"), (-1, "antenna.R")):
            q0, q1, q2 = P(s * a0[0], a0[1], a0[2]), P(s * a1[0], a1[1], a1[2]), P(s * a2[0], a2[1], a2[2])
            body.lowpoly(body.segment(nm, "M_Brown", q0, q1, r, r * 0.8, verts=6))
            body.lowpoly(body.segment(nm, "M_Brown", q1, q2, r * 0.85, r * 0.55, verts=6))
            bones.append(BoneDef(nm, q0, q2, parent="head"))

    def mandibles(hy, depth):
        for s in (+1, -1):
            body.lowpoly(body.segment("head", K, P(s * 0.035, hy - depth * 0.75, -0.06), P(s * 0.022, hy - depth * 1.35, -0.10),
                                      0.016, 0.005, verts=6))

    if weapon == "gun":  # ------------------------------------------------------- assault wasp
        hy, hr = -0.40, 0.115
        body.sphere("head", K, P(0, hy, 0.03), hr, scale=(1.0, 0.92, 0.95), segments=12, rings=8)
        body.sphere("head", T, P(0, hy - 0.005, 0.088), hr * 0.86, scale=(1.0, 0.95, 0.55), segments=10, rings=6)
        for s in (+1, -1):
            body.sphere("head", "M_EyeRed", P(s * 0.092, hy - 0.035, 0.03), 0.052, scale=(0.6, 1.0, 1.2), segments=8, rings=5)
        antennae(((0.04, hy - 0.08, 0.09), (0.085, hy - 0.20, 0.15), (0.15, hy - 0.31, 0.11)), 0.015)
        mandibles(hy, 0.10)
        ty = -0.15
        body.banded("body", [K, T], P(0, ty, 0.0), 0.17, scale=(0.74, 0.76, 1.0),
                    bands=[(0.55, 1.01, T), (-1.01, -0.72, T)], segments=14, rings=10)
        # thread waist rising steeply to the small abdomen held up behind the thorax
        p0, p1 = P(0, 0.0, 0.04), P(0, 0.17, 0.24)
        body.lowpoly(body.sphere("body", K, p0, 0.04, segments=8, rings=5))
        body.segment("petiole", K, p0, p1, 0.024, 0.021, verts=8)
        body.lowpoly(body.sphere("petiole", K, p1, 0.034, segments=8, rings=5))
        ay, ar, al = 0.31, 0.105, 1.45
        body.banded("abdomen", [K, T], P(0, ay, 0.30), ar, scale=(1.0, 0.95, al),
                    bands=[(0.45, 0.75, T), (-0.20, 0.20, T), (-0.60, -0.45, T)], segments=14, rings=14, tilt=6)
        end = ay + ar * al
        body.cone("abdomen", K, P(0, end + 0.015, 0.315), 0.022, 0.0, 0.07, rot=(rad(-95), 0, 0), verts=8)
        tip = P(0, end + 0.06, 0.31)
        wing = dict(root=(0.06, -0.22, 0.12), length=0.70, width=0.20, sweep=10, dihedral=8, profile="wasp", mat="M_Wing")
        rows = [  # coxa, knee, foot, toe (left side)
            ((0.06, -0.24, -0.09), (0.19, -0.35, -0.23), (0.24, -0.45, -0.46), (0.25, -0.51, -0.51)),
            ((0.07, -0.15, -0.11), (0.26, -0.16, -0.25), (0.33, -0.10, -0.52), (0.34, -0.08, -0.58)),
            ((0.07, -0.06, -0.10), (0.26, 0.06, -0.24), (0.35, 0.22, -0.50), (0.36, 0.28, -0.55)),
        ]
        leg_mats = dict(fem="M_Maroon", tib="M_Tan", joint="M_Maroon", tarsus="M_Brown", r=0.025)
        gz = -0.17
        g0, g1 = P(0, -0.20, gz), P(0, -0.58, gz)
        body.cylinder("gun", "M_Gun", P(0, -0.40, gz), 0.028, 0.34, rot=(rad(90), 0, 0), verts=10)
        body.cylinder("gun", K, P(0, -0.56, gz), 0.036, 0.05, rot=(rad(90), 0, 0), verts=10)  # muzzle
        body.cube("gun", K, P(0, -0.25, gz + 0.01), size=(0.08, 0.13, 0.07))
        body.cube("gun", "M_Gun", P(0, -0.30, gz - 0.035), size=(0.045, 0.05, 0.05))  # magazine
    elif weapon == "arrow":  # -------------------------------------------------- paralysis wasp
        hy, hr = -0.70, 0.15
        body.sphere("head", K, P(0, hy, 0.04), hr, scale=(1.12, 0.92, 0.95), segments=12, rings=8)
        body.sphere("head", T, P(0, hy + 0.01, 0.115), hr * 0.88, scale=(1.12, 0.88, 0.55), segments=10, rings=6)
        for s in (+1, -1):
            body.sphere("head", "M_Eye", P(s * 0.128, hy - 0.04, 0.04), 0.07, scale=(0.6, 1.0, 1.25), segments=8, rings=5)
        antennae(((0.05, hy - 0.10, 0.12), (0.11, hy - 0.24, 0.18), (0.19, hy - 0.34, 0.12)), 0.016)
        mandibles(hy, 0.13)
        ty = -0.33
        body.banded("body", [K, T], P(0, ty, 0.0), 0.23, scale=(1.0, 0.80, 1.05),
                    bands=[(0.62, 0.86, T)], segments=14, rings=10)
        p0, p1 = P(0, -0.10, 0.0), P(0, 0.06, 0.04)
        body.segment("petiole", K, p0, p1, 0.055, 0.048, verts=10)
        ay, ar, al = 0.40, 0.165, 2.05
        body.banded("abdomen", [K, T], P(0, ay, 0.09), ar, scale=(1.0, 0.92, al),
                    bands=[(0.60, 0.90, T), (-0.15, 0.15, T), (-0.80, -0.60, T)], segments=14, rings=16, tilt=6)
        end = ay + ar * al
        body.cone("abdomen", K, P(0, end + 0.02, 0.125), 0.03, 0.0, 0.10, rot=(rad(-95), 0, 0), verts=8)
        tip = P(0, end + 0.08, 0.12)
        wing = dict(root=(0.09, -0.46, 0.17), length=1.05, width=0.18, sweep=8, dihedral=6, profile="wasp",
                    mat="M_WingDark")
        rows = [
            ((0.08, -0.48, -0.13), (0.26, -0.64, -0.28), (0.31, -0.84, -0.52), (0.31, -0.92, -0.56)),
            ((0.09, -0.34, -0.15), (0.35, -0.36, -0.31), (0.42, -0.30, -0.62), (0.43, -0.27, -0.69)),
            ((0.09, -0.20, -0.14), (0.35, -0.04, -0.30), (0.43, 0.20, -0.60), (0.44, 0.27, -0.66)),
        ]
        leg_mats = dict(fem="M_Brown", tib="M_LegBrown", joint="M_Brown", tarsus="M_Brown", r=0.030)
        gz = -0.20
        g0, g1 = P(0, -0.34, gz), P(0, -0.80, gz)
        body.cylinder("gun", K, P(0, -0.55, gz), 0.034, 0.40, rot=(rad(90), 0, 0), verts=10)  # launcher tube
        body.cube("gun", "M_Gun", P(0, -0.40, gz + 0.02), size=(0.10, 0.14, 0.08))
        body.cylinder("gun", "M_Gun", P(0, -0.71, gz), 0.044, 0.05, rot=(rad(90), 0, 0), verts=10)  # muzzle ring
        body.sphere("gun", "M_Green", P(0, -0.77, gz), 0.055, segments=12, rings=8)  # glowing arrow tip under the head
    else:  # ------------------------------------------------------------------- sonic wasp
        hy, hr = -0.47, 0.16
        body.sphere("head", T, P(0, hy, 0.03), hr, scale=(1.0, 0.85, 0.92), segments=12, rings=8)
        body.sphere("head", K, P(0, hy - 0.085, -0.03), hr * 0.62, scale=(1.0, 0.7, 0.85), segments=10, rings=6)  # face
        for s in (+1, -1):
            body.sphere("head", "M_Eye", P(s * 0.118, hy - 0.04, 0.04), 0.062, scale=(0.62, 1.0, 1.18), segments=8, rings=5)
        antennae(((0.05, hy - 0.09, 0.12), (0.10, hy - 0.21, 0.17), (0.16, hy - 0.29, 0.12)), 0.016)
        ty = -0.17
        body.banded("body", [T, K], P(0, ty, 0.01), 0.21, scale=(1.0, 0.92, 0.95),
                    bands=[(0.70, 0.85, K), (0.05, 0.25, K), (-0.70, -0.50, K), (-1.01, -0.95, K)], segments=14, rings=12)
        p0, p1 = P(0, 0.01, -0.01), P(0, 0.08, -0.02)
        body.segment("petiole", K, p0, p1, 0.085, 0.075, verts=10)
        ay, ar, al = 0.38, 0.25, 1.32
        body.banded("abdomen", [T, K], P(0, ay, -0.04), ar, scale=(1.0, 0.84, al),
                    bands=[(0.98, 1.01, K), (0.78, 0.85, K), (0.38, 0.46, K), (-0.12, -0.05, K), (-0.60, -0.54, K),
                           (-1.01, -0.88, K)], segments=14, rings=18, tilt=-8)
        end = ay + ar * al
        body.cone("abdomen", K, P(0, end + 0.01, -0.085), 0.03, 0.0, 0.10, rot=(rad(-95), 0, 0), verts=8)
        tip = P(0, end + 0.08, -0.09)
        wing = dict(root=(0.08, -0.25, 0.17), length=0.92, width=0.32, sweep=12, dihedral=8, profile="sonic", mat="M_Wing")
        rows = [
            ((0.08, -0.28, -0.14), (0.23, -0.37, -0.28), (0.27, -0.45, -0.50), (0.28, -0.51, -0.55)),
            ((0.10, -0.17, -0.16), (0.31, -0.16, -0.31), (0.37, -0.10, -0.55), (0.38, -0.08, -0.62)),
            ((0.10, -0.05, -0.15), (0.31, 0.08, -0.30), (0.39, 0.22, -0.54), (0.40, 0.28, -0.59)),
        ]
        leg_mats = dict(fem=T, tib=T, joint=K, tarsus=K, r=0.032)
        gz = -0.10
        g0, g1 = P(0, -0.42, gz), P(0, -0.70, gz)
        body.cone("gun", K, P(0, -0.60, gz), 0.075, 0.03, 0.12, rot=(rad(-90), 0, 0), verts=14)  # bell, mouth forward
        body.cylinder("gun", "M_Gun", P(0, -0.51, gz), 0.032, 0.10, rot=(rad(90), 0, 0), verts=10)
        body.cube("gun", K, P(0, -0.45, gz - 0.02), size=(0.09, 0.08, 0.07))
    bones.append(BoneDef("petiole", p0, p1, parent="body"))
    bones.append(BoneDef("abdomen", p1, tip, parent="petiole"))
    # ---- wings: one long narrow wing per side (the sprites show one), swept back a little ----------
    wings = []
    sweep, dih = rad(wing["sweep"]), rad(wing["dihedral"])
    for s, nm in ((+1, "wing.L"), (-1, "wing.R")):
        rx, ry, rz = wing["root"]
        root = P(s * rx, ry, rz)
        length = wing["length"]
        tipv = (root[0] + s * length * math.cos(sweep) * math.cos(dih), root[1] + length * math.sin(sweep),
                root[2] + length * math.sin(dih))
        body.blade(nm, wing["mat"], root, tipv, wing["width"], profile=wing["profile"], thickness=0.012)
        wings.append((nm, root, tipv, s))
    # ---- legs ------------------------------------------------------------------------------------
    leg_bones = []
    for i, (c, k, f, toe) in enumerate(rows):
        for s, sd in ((+1, "L"), (-1, "R")):
            def X(v):
                return P(s * v[0], v[1], v[2])
            leg_bones += leg(body, f"leg.{sd}{i + 1}", leg_mats["fem"], leg_mats["tib"], X(c), X(k), X(f), r=leg_mats["r"],
                             mat_joint=leg_mats["joint"], toe=X(toe), mat_tarsus=leg_mats["tarsus"])
    bones += leg_bones
    bones.append(BoneDef("gun", g0, g1, parent="body"))
    extras = dict(head=(P(0, hy + 0.12, 0.0), P(0, hy - 0.16, 0.0)))
    return bones, wings, [b.name for b in leg_bones if b.name.endswith(".up")], extras


# --------------------------------------------------------------------------------------------
# neutral flyers
# --------------------------------------------------------------------------------------------
def build_dragonfly(body):
    """Dragonfly after the sprite (24 px = 1 unit): body 46 px (eyes 6, thorax 11, slim abdomen 29 x 5 px),
    four long wings straight out to the sides attached right behind the eyes (forewing chord 8 px,
    hindwing 6.5 px, span 85 px); loading screen 2 + portrait: big blue eyes, teal thorax with
    green / orange stripes, green segmented abdomen with dark rings, black legs bunched forward
    under the head, darker forewings; two grey brake bombs under the thorax."""
    z = Z0
    bones, wings = [], []
    body.sphere("head", "M_Teal", (0, -0.84, z - 0.01), 0.12, scale=(1.0, 0.9, 0.9), segments=12, rings=8)
    for s in (+1, -1):
        body.sphere("head", "M_DfEye", (s * 0.085, -0.86, z + 0.05), 0.11, scale=(0.9, 1.0, 1.0), segments=12, rings=8)
    body.lowpoly(body.sphere("head", "M_DfDark", (0, -0.93, z - 0.07), 0.05, segments=8, rings=5))  # mouthparts
    body.banded("body", ["M_Teal", "M_DfGreen", "M_DfOrange"], (0, -0.57, z + 0.01), 0.21, scale=(0.85, 0.95, 1.0),
                bands=[(0.35, 0.6, "M_DfGreen"), (-0.1, 0.1, "M_DfOrange"), (-0.6, -0.4, "M_DfGreen")], segments=16, rings=12)
    # abdomen: slim, ten segments with dark rings (no subdivision: 30 rings are smooth enough)
    bands = []
    for i in range(10):
        lo = -1.0 + i * 0.2
        bands.append((lo + 0.145, lo + 0.2, "M_DfDark"))
    bands.append((0.84, 1.01, "M_DfOrange"))
    ab_c, ab_r, ab_l = 0.29, 0.088, 7.6  # 1.34 long: y -0.38 .. 0.96
    body.banded("abdomen", ["M_DfGreen", "M_DfDark", "M_DfOrange"], (0, ab_c, z + 0.02), ab_r, scale=(1.0, 0.95, ab_l),
                bands=bands, segments=12, rings=30, subdiv=False)
    end = ab_c + ab_r * ab_l
    for s in (+1, -1):  # claspers
        body.lowpoly(body.cone("abdomen", "M_DfDark", (s * 0.035, end + 0.03, z + 0.02), 0.025, 0.0, 0.10,
                               rot=(rad(-90), 0, s * rad(12)), verts=6))
    # wings: two pairs straight out to the sides, nearly parallel (forewings a shade darker)
    for s, sd in ((+1, "L"), (-1, "R")):
        for j, (ry, ty, chord, mat) in enumerate(((-0.73, -0.75, 0.34, "M_DfWingFore"), (-0.41, -0.37, 0.28, "M_DfWing"))):
            nm = f"wing.{sd}{j + 1}"
            root = (s * 0.10, ry, z + 0.17 + j * 0.012)
            tip = (s * 1.78, ty, z + 0.22)
            body.blade(nm, mat, root, tip, chord, profile="dragon", thickness=0.012, segments=16)
            wings.append((nm, root, tip, s))
    # legs: six black jointed legs bunched under the thorax and held forward under the head (the
    # "basket" of the original render), hidden from above like the sprite
    leg_names = []
    rows = [(-0.74, 0.15, -0.86, 0.14, -0.96, -0.22, -0.44), (-0.66, 0.19, -0.75, 0.20, -0.85, -0.25, -0.50),
            (-0.56, 0.21, -0.61, 0.23, -0.69, -0.26, -0.54)]
    for i, (cy, kx, ky, fx, fy, kz, fz) in enumerate(rows):
        for s, sd in ((+1, "L"), (-1, "R")):
            b = leg(body, f"leg.{sd}{i + 1}", "M_DfDark", "M_DfDark", (s * 0.10, cy, z - 0.14), (s * kx, ky, z + kz),
                    (s * fx, fy, z + fz), r=0.024, toe=(s * fx, fy - 0.07, z + fz - 0.01))
            bones += b
            leg_names.append(b[0].name)
    # brake bombs slung under the thorax
    for s in (+1, -1):
        by = -0.44
        body.cylinder("body", "M_Bomb", (s * 0.10, by, z - 0.30), 0.052, 0.24, rot=(rad(90), 0, 0), verts=10)
        body.cone("body", "M_Bomb", (s * 0.10, by - 0.15, z - 0.30), 0.052, 0.015, 0.07, rot=(rad(-90), 0, 0), verts=10)
        body.cube("body", "M_Bomb", (s * 0.10, by + 0.14, z - 0.30), size=(0.012, 0.07, 0.13))
        body.cube("body", "M_Bomb", (s * 0.10, by + 0.14, z - 0.30), size=(0.13, 0.07, 0.012))
    bones.append(BoneDef("abdomen", (0, -0.36, z + 0.02), (0, end + 0.10, z + 0.02), parent="body"))
    extras = dict(head=((0, -0.72, z), (0, -0.98, z)), body=((0, -0.36, z), (0, -0.72, z)))
    return bones, wings, leg_names, extras


def build_fly(body):
    """Desert fly after the sprite: compact olive-brown body 27 x 9 px (big green orange-rimmed eyes,
    thorax with dark stripes along the body, banded abdomen), two elongated pale wings 20 x 8 px
    attached right behind the head (span 48 px), short dark legs beside the body; portrait: dark body,
    mottled grey-brown thorax top, smoky wings, long thin black legs."""
    z = Z0
    bones, wings = [], []
    K = "M_FlyDark"
    body.sphere("head", K, (0, -0.42, z), 0.135, scale=(1.0, 0.85, 0.95), segments=12, rings=8)
    for s in (+1, -1):
        body.lowpoly(body.sphere("head", "M_FlyRim", (s * 0.10, -0.42, z + 0.0), 0.118, scale=(0.75, 0.95, 1.05),
                                 segments=10, rings=6))
        body.sphere("head", "M_FlyEye", (s * 0.095, -0.465, z + 0.03), 0.112, scale=(0.75, 0.95, 1.05), segments=12, rings=8)
        body.lowpoly(body.segment("head", K, (s * 0.03, -0.55, z - 0.02), (s * 0.07, -0.63, z + 0.02), 0.012, 0.005, verts=6))
    body.lowpoly(body.sphere("head", K, (0, -0.52, z - 0.10), 0.045, scale=(1.0, 1.2, 1.3), segments=8, rings=5))  # proboscis
    # thorax dome: fore/aft dark stripes (rings around the X axis)
    body.banded("body", ["M_FlyGrey", K], (0, -0.17, z + 0.03), 0.20, scale=(0.95, 0.85, 1.0), axis="X",
                bands=[(-0.95, -0.72, K), (-0.44, -0.24, K), (-0.1, 0.1, K), (0.24, 0.44, K), (0.72, 0.95, K)],
                segments=16, rings=12)
    # abdomen: banded, tapering
    body.banded("abdomen", [K, "M_FlyGrey"], (0, 0.24, z - 0.01), 0.19, scale=(0.95, 0.80, 1.45),
                bands=[(0.35, 0.55, "M_FlyGrey"), (-0.1, 0.1, "M_FlyGrey"), (-0.55, -0.38, "M_FlyGrey")], segments=16, rings=12)
    for s, nm in ((+1, "wing.L"), (-1, "wing.R")):
        root = (s * 0.12, -0.25, z + 0.19)
        tip = (s * 0.94, -0.06, z + 0.25)
        body.blade(nm, "M_FlyWing", root, tip, 0.34, profile="fly", thickness=0.012, segments=14)
        wings.append((nm, root, tip, s))
    # six dark legs hanging under the thorax, the knees out beside the body (visible from above as in
    # the sprite), tarsi down
    leg_names = []
    rows = [((0.08, -0.29, -0.12), (0.22, -0.40, -0.19), (0.27, -0.50, -0.40), (0.28, -0.56, -0.44)),
            ((0.10, -0.18, -0.14), (0.29, -0.17, -0.21), (0.35, -0.09, -0.44), (0.36, -0.06, -0.50)),
            ((0.09, -0.07, -0.13), (0.27, 0.06, -0.20), (0.33, 0.22, -0.42), (0.34, 0.27, -0.47))]
    for i, (c, k, f, toe) in enumerate(rows):
        for s, sd in ((+1, "L"), (-1, "R")):
            def X(v):
                return (s * v[0], v[1], z + v[2])
            b = leg(body, f"leg.{sd}{i + 1}", K, K, X(c), X(k), X(f), r=0.028, toe=X(toe), foot_k=0.66)
            bones += b
            leg_names.append(b[0].name)
    bones.append(BoneDef("abdomen", (0, 0.03, z), (0, 0.56, z - 0.03), parent="body"))
    extras = dict(head=((0, -0.30, z), (0, -0.58, z)), body=((0, 0.03, z), (0, -0.30, z)))
    return bones, wings, leg_names, extras


def build_moth(body):
    """Spawn moth after the sprite: two wing pairs held straight out to the sides as one compact block
    52 px wide and ~19 px deep (forewings in front, hindwings close behind), golden tan with dark
    brown stripes running along the wings and a dark eye-spot on each forewing (portrait); thin furry
    brown body 25 px long; legs folded under the body (hidden by the wings from above)."""
    z = Z0
    bones, wings = [], []
    B = "M_MothBody"
    body.sphere("head", B, (0, -0.40, z), 0.075, segments=10, rings=7)
    for s in (+1, -1):
        body.lowpoly(body.sphere("head", "M_FlyEye", (s * 0.05, -0.44, z + 0.01), 0.028, segments=8, rings=5))
        # small feathery antenna: thin stalk with a narrow comb
        nm = "antenna.L" if s > 0 else "antenna.R"
        a0, a1 = (s * 0.03, -0.45, z + 0.04), (s * 0.17, -0.64, z + 0.08)
        body.lowpoly(body.segment(nm, B, a0, a1, 0.010, 0.005, verts=6))
        mid = ((a0[0] + a1[0]) / 2, (a0[1] + a1[1]) / 2, (a0[2] + a1[2]) / 2)
        body.lowpoly(body.sphere(nm, B, mid, 0.04, scale=(0.5, 2.6, 0.12), rot=(0, 0, s * rad(-36)), segments=8, rings=5))
        bones.append(BoneDef(nm, a0, a1, parent="head"))
    body.sphere("body", B, (0, -0.16, z), 0.13, scale=(0.80, 1.35, 0.82), segments=14, rings=9)
    body.banded("abdomen", ["M_MothTan", B], (0, 0.26, z - 0.02), 0.095, scale=(0.85, 0.8, 3.0),
                bands=[(0.3, 0.5, B), (-0.1, 0.1, B), (-0.5, -0.3, B), (-1.01, -0.75, B)], segments=12, rings=12)
    # wings: forewing almost straight out (a touch forward), hindwing close behind (a touch back)
    for s, sd in ((+1, "L"), (-1, "R")):
        root1, tip1 = (s * 0.07, -0.25, z + 0.07), (s * 1.06, -0.29, z + 0.10)
        body.blade(f"wing.{sd}1", "M_MothWing", root1, tip1, 0.46, profile="moth_fore", thickness=0.012, segments=14,
                   wing_id=1.0)
        wings.append((f"wing.{sd}1", root1, tip1, s))
        root2, tip2 = (s * 0.07, 0.03, z + 0.05), (s * 0.96, 0.14, z + 0.07)
        body.blade(f"wing.{sd}2", "M_MothWing", root2, tip2, 0.42, profile="moth_hind", thickness=0.012, segments=14,
                   wing_id=0.0)
        wings.append((f"wing.{sd}2", root2, tip2, s))
    # six slender legs folded under the body (hidden by the wings from above, as in the sprite)
    leg_names = []
    rows = [(-0.32, 0.15, -0.44, 0.17, -0.52, -0.12, -0.30), (-0.20, 0.17, -0.18, 0.19, -0.14, -0.12, -0.32),
            (-0.07, 0.16, 0.04, 0.18, 0.16, -0.12, -0.30)]
    for i, (cy, kx, ky, fx, fy, kz, fz) in enumerate(rows):
        for s, sd in ((+1, "L"), (-1, "R")):
            b = leg(body, f"leg.{sd}{i + 1}", B, B, (s * 0.07, cy, z - 0.08), (s * kx, ky, z + kz), (s * fx, fy, z + fz),
                    r=0.017, toe=(s * fx, fy - 0.04, z + fz - 0.01))
            bones += b
            leg_names.append(b[0].name)
    bones.append(BoneDef("abdomen", (0, 0.0, z), (0, 0.58, z - 0.04), parent="body"))
    extras = dict(head=((0, -0.30, z), (0, -0.50, z)), body=((0, 0.0, z), (0, -0.30, z)))
    return bones, wings, leg_names, extras


def build_machine(body):
    """Pirate flying machine after the portrait + sprite: a round wooden tub with a golden rim and the
    black pirate-ant pilot in its front half, a mast behind him carrying a four-paddle pink rotor
    (thin olive spokes with broad pink paddles on their outer two thirds, diameter 2.5), a tail boom to a
    small two-paddle pink tail propeller on a post, red wheels, grey gearbox."""
    z = Z0
    bones = []
    hull_c = (0, -0.38, z + 0.06)
    body.bowl("body", "M_Wood", hull_c, 0.48, scale=(0.92, 1.0, 0.62), thickness=0.045)
    body.lowpoly(body.torus("body", "M_Gold", hull_c, 0.47, 0.035, scale=(0.92, 1.0, 1.0)))  # gunwale
    body.cube("body", "M_Wood", (0, -0.15, z - 0.02), size=(0.62, 0.10, 0.05))  # cross beam
    body.cube("body", "M_Wood", (0, 0.0, z - 0.24), size=(0.05, 1.30, 0.05))  # keel runner
    mast_y = 0.04  # the mast stands at the back of the tub, the pilot sits in front (portrait, sprite)
    body.cylinder("body", "M_Accent", (0, mast_y, z + 0.42), 0.03, 0.84, verts=10)  # mast
    body.cube("body", "M_Gun", (0, mast_y + 0.04, z + 0.12), size=(0.18, 0.22, 0.16))  # gearbox
    body.cylinder("body", "M_Gun", (0.14, mast_y + 0.04, z + 0.12), 0.07, 0.06, rot=(0, rad(90), 0), verts=12)  # flywheel
    # tail boom + brace to the tail-propeller post
    body.segment("body", "M_Frame", (0, 0.10, z + 0.14), (0, 1.24, z + 0.30), 0.035, 0.025, verts=8)
    body.lowpoly(body.segment("body", "M_Frame", (0, 0.06, z - 0.20), (0, 1.12, z + 0.27), 0.018, 0.016, verts=6))
    body.segment("body", "M_Wood", (0, 1.26, z + 0.22), (0, 1.26, z + 0.52), 0.03, 0.025, verts=8)
    rz_tail = z + 0.54
    body.lowpoly(body.cylinder("tail_rotor", "M_Accent", (0, 1.26, rz_tail), 0.04, 0.05, verts=8))
    for k in range(2):
        a = k * math.pi
        body.plate("tail_rotor", "M_Pink", (0.30 * math.cos(a), 1.26 + 0.30 * math.sin(a), rz_tail + 0.01), 0.46, 0.14, 0.015,
                   rot=(rad(10), 0, a), corner=0.03)
    # main rotor: hub, four spokes with broad pink paddles on their outer part, olive cross-bracing
    rz = z + 0.86
    body.cylinder("rotor", "M_Accent", (0, mast_y, rz - 0.02), 0.055, 0.08, verts=10)
    body.lowpoly(body.sphere("rotor", "M_Red", (0, mast_y, rz + 0.03), 0.045, segments=8, rings=5))
    for k in range(4):
        a = k * math.pi / 2 + math.pi / 4
        ca, sa = math.cos(a), math.sin(a)
        body.lowpoly(body.segment("rotor", "M_Frame", (0.05 * ca, mast_y + 0.05 * sa, rz), (1.20 * ca, mast_y + 1.20 * sa, rz),
                                  0.022, 0.015, verts=6))
        body.plate("rotor", "M_Pink", (0.79 * ca, mast_y + 0.79 * sa, rz + 0.012), 0.92, 0.31, 0.02, rot=(rad(8), 0, a),
                   corner=0.05)
        b0 = a + math.pi / 2
        body.lowpoly(body.segment("rotor", "M_Frame", (0.30 * ca, mast_y + 0.30 * sa, rz),
                                  (0.30 * math.cos(b0), mast_y + 0.30 * math.sin(b0), rz), 0.013, 0.013, verts=5))
    bones.append(BoneDef("rotor", (0, mast_y, rz - 0.1), (0, mast_y, rz + 0.1), parent="body"))
    bones.append(BoneDef("tail_rotor", (0, 1.26, rz_tail - 0.1), (0, 1.26, rz_tail + 0.1), parent="body"))
    # wheels (two front, one rear): red wheels on struts
    for x, y in ((0.36, -0.56), (-0.36, -0.56), (0.0, 0.62)):
        body.lowpoly(body.cylinder("body", "M_Red", (x, y, z - 0.30), 0.10, 0.06, rot=(0, rad(90), 0), verts=14))
        body.lowpoly(body.cylinder("body", "M_Accent", (x, y, z - 0.30), 0.035, 0.09, rot=(0, rad(90), 0), verts=8))
        body.lowpoly(body.segment("body", "M_Accent", (x * 0.6, y, z - 0.10), (x, y, z - 0.30), 0.02, 0.015, verts=6))
    # pilot: black pirate ant sitting in the front of the tub, looking over the bow
    py = -0.56
    body.sphere("body", "M_Black", (0, py + 0.18, z + 0.15), 0.15, scale=(0.9, 1.2, 0.8), segments=10, rings=7)
    body.sphere("pilot", "M_Black", (0, py, z + 0.27), 0.115, segments=10, rings=7)
    body.sphere("pilot", "M_Black", (0, py - 0.16, z + 0.38), 0.11, scale=(1.0, 0.95, 0.9), segments=10, rings=7)
    for s in (+1, -1):
        body.lowpoly(body.sphere("pilot", "M_PaleBlue", (s * 0.06, py - 0.21, z + 0.38), 0.03, segments=8, rings=5))
        body.lowpoly(body.segment("pilot", "M_Black", (s * 0.04, py - 0.21, z + 0.44), (s * 0.15, py - 0.44, z + 0.60), 0.012, 0.006,
                                  verts=6))
        body.lowpoly(body.segment("pilot", "M_Black", (s * 0.08, py - 0.06, z + 0.24), (s * 0.16, py - 0.26, z + 0.14), 0.016, 0.01,
                                  verts=6))
    body.lowpoly(body.cylinder("pilot", "M_Wood", (0, py - 0.25, z + 0.14), 0.02, 0.22, rot=(rad(25), 0, 0), verts=6))  # tiller
    bones.append(BoneDef("pilot", (0, py + 0.08, z + 0.2), (0, py - 0.15, z + 0.40), parent="body"))
    extras = dict(body=((0, 0.3, z), (0, -0.3, z)))
    return bones, [], [], extras


# --------------------------------------------------------------------------------------------
# animation
# --------------------------------------------------------------------------------------------
def key_wings(c, wings, frames, flap, sweep, tilt=0.0, beats=2, phase=0.0, hind_lag=0.25):
    """Sinusoidal wing beat: flap about the root's local X (up/down) and sweep about local Z
    (fore/aft, mirrored per side: swept back on the upstroke, forward on the downstroke).  Hind
    wings (names ending in 2) beat `hind_lag` of a period behind."""
    for nm, _r, _t, s in wings:
        lag = hind_lag if nm.endswith("2") else 0.0
        for i in range(frames + 1):
            t = i / frames
            a = 2 * math.pi * (t * beats + phase + lag)
            fl = tilt + flap * math.sin(a)
            sw = sweep * math.cos(a)
            c.key(nm, 1 + i, rot=(fl, 0, s * sw))


def key_legs(c, legs, frames, amp=4.0, beats=1):
    """Gentle dangle: each leg swings in its own vertical plane with its own phase; the tibia
    follows a little behind the femur."""
    for i, nm in enumerate(legs):
        for f in range(frames + 1):
            t = f / frames
            a = amp * math.sin(2 * math.pi * (t * beats + 0.17 * i))
            b = amp * 0.8 * math.sin(2 * math.pi * (t * beats + 0.17 * i - 0.12))
            c.key(nm, 1 + f, rot=(a, 0, 0))
            c.key(nm.replace(".up", ".low"), 1 + f, rot=(b, 0, 0))


def make_clips(rig, kind, wings, legs, has_antennae, has_gun):
    clips = []
    is_machine = kind == "machine"
    pb = rig.pose.bones
    # (flap amplitude, fore/aft sweep amplitude, mean raise) per kind.  The sprites' flight frames
    # show the wings beating between raised (foreshortened from above) and flat out to the sides, so
    # the beat is mostly an up/down flap about a raised mean with only a small fore/aft sweep.
    wing_amp = {"wasp": (30.0, 10.0, 18.0), "dragonfly": (22.0, 4.0, 8.0), "fly": (30.0, 12.0, 12.0),
                "moth": (18.0, 4.0, 16.0), "machine": (0, 0, 0)}[kind]
    fly_amp = {"wasp": (38.0, 12.0, 22.0), "dragonfly": (28.0, 5.0, 6.0), "fly": (36.0, 14.0, 12.0),
               "moth": (22.0, 5.0, 18.0), "machine": (0, 0, 0)}[kind]
    hind_lag = {"dragonfly": 0.5, "moth": 0.0}.get(kind, 0.25)
    leg_amp = {"wasp": 5.0, "dragonfly": 3.0, "fly": 5.0, "moth": 4.0, "machine": 0.0}[kind]
    antennae = ["antenna.L", "antenna.R"] if has_antennae else []
    pitch = {"wasp": 4, "dragonfly": 2, "fly": 5, "moth": 4, "machine": 3}[kind]  # nose up while flying

    def rotor(c, frames, turns):
        if not is_machine:
            return
        for i in range(frames + 1):
            c.key("rotor", 1 + i, rot=(0, 360.0 * turns * i / frames, 0))
            c.key("tail_rotor", 1 + i, rot=(0, 360.0 * turns * 1.5 * i / frames, 0))

    # idle: hover ------------------------------------------------------------------------------
    c = Clip(rig, "idle", 12)
    key_wings(c, wings, 12, wing_amp[0], wing_amp[1], tilt=wing_amp[2], beats=2, hind_lag=hind_lag)
    key_legs(c, legs, 12, amp=leg_amp)
    rotor(c, 12, 1.0)
    c.key("body", 1, loc=(0, 0, 0), rot=(2, 0, 0)); c.key("body", 7, loc=(0, 0, 0.02), rot=(4, 0, 0)); c.key("body", 13, loc=(0, 0, 0), rot=(2, 0, 0))
    if "abdomen" in pb:
        c.key("abdomen", 1, rot=(0, 0, 0)); c.key("abdomen", 7, rot=(3, 0, 0)); c.key("abdomen", 13, rot=(0, 0, 0))
    for i, b in enumerate(antennae):
        c.key(b, 1, rot=(0, 0, 0)); c.key(b, 7, rot=(6, 0, 5 * (1 if i else -1))); c.key(b, 13, rot=(0, 0, 0))
    if is_machine:
        c.key("pilot", 1, rot=(0, 0, 0)); c.key("pilot", 7, rot=(4, 0, 0)); c.key("pilot", 13, rot=(0, 0, 0))
    clips.append(c.finish())
    # fly: the game plays this for hovering and travelling -----------------------------------------
    c = Clip(rig, "fly", 12)
    key_wings(c, wings, 12, fly_amp[0], fly_amp[1], tilt=fly_amp[2], beats=2, hind_lag=hind_lag)
    key_legs(c, legs, 12, amp=leg_amp * 0.8)
    rotor(c, 12, 1.0)
    c.key("body", 1, rot=(pitch, 0, 0), loc=(0, 0, 0)); c.key("body", 7, rot=(pitch + 1.5, 0, 0), loc=(0, 0, 0.015)); c.key("body", 13, rot=(pitch, 0, 0), loc=(0, 0, 0))
    if "abdomen" in pb:
        c.key("abdomen", 1, rot=(-3, 0, 0)); c.key("abdomen", 7, rot=(-5, 0, 0)); c.key("abdomen", 13, rot=(-3, 0, 0))
    for b in antennae:
        c.key(b, 1, rot=(-8, 0, 0)); c.key(b, 13, rot=(-8, 0, 0))
    if is_machine:
        c.key("pilot", 1, rot=(-5, 0, 0)); c.key("pilot", 13, rot=(-5, 0, 0))
    clips.append(c.finish())
    # attack: recoil (backwards, nose up) while the wings keep beating ----------------------------
    c = Clip(rig, "attack", 12, loop=False)
    key_wings(c, wings, 12, fly_amp[0], fly_amp[1], tilt=fly_amp[2], beats=2, hind_lag=hind_lag)
    key_legs(c, legs, 12, amp=leg_amp * 0.8)
    rotor(c, 12, 1.0)
    c.key("body", 1, loc=(0, 0, 0), rot=(pitch, 0, 0))
    c.key("body", 3, loc=(0, -0.07, 0.025), rot=(pitch + 9, 0, 0))
    c.key("body", 7, loc=(0, -0.02, 0.0), rot=(pitch + 2, 0, 0))
    c.key("body", 13, loc=(0, 0, 0), rot=(pitch, 0, 0))
    if "abdomen" in pb:
        c.key("abdomen", 1, rot=(-3, 0, 0)); c.key("abdomen", 4, rot=(8, 0, 0)); c.key("abdomen", 13, rot=(-3, 0, 0))
    if has_gun:
        c.key("gun", 1, loc=(0, 0, 0)); c.key("gun", 2, loc=(0, -0.06, 0)); c.key("gun", 6, loc=(0, 0, 0)); c.key("gun", 13, loc=(0, 0, 0))
    if "head" in pb:
        c.key("head", 1, rot=(0, 0, 0)); c.key("head", 3, rot=(10, 0, 0)); c.key("head", 13, rot=(0, 0, 0))
    if is_machine:
        c.key("pilot", 1, rot=(0, 0, 0)); c.key("pilot", 3, rot=(14, 0, 0)); c.key("pilot", 13, rot=(0, 0, 0))
    clips.append(c.finish())
    # death: wings fold, legs curl, body pitches down and rolls over while the game drops it --------
    c = Clip(rig, "death", 36, loop=False)
    for nm, _r, _t, s in wings:
        c.key(nm, 1, rot=(0, 0, 0))
        c.key(nm, 10, rot=(55, 0, s * 15))
        c.key(nm, 36, rot=(-48, 0, s * 62))  # swept back along the body and dropped
    # legs tuck: femora swing under the body, tibiae fold back against them (negative X in the
    # roll-0 bone frame = toward the body's underside)
    for i, nm in enumerate(legs):
        c.key(nm, 1, rot=(0, 0, 0)); c.key(nm, 14, rot=(-20, 0, 0)); c.key(nm, 36, rot=(-62 + 8 * (i % 3), 0, 0))
        low = nm.replace(".up", ".low")
        c.key(low, 1, rot=(0, 0, 0)); c.key(low, 14, rot=(-30, 0, 0)); c.key(low, 36, rot=(-100, 0, 0))
    if is_machine:
        for i in range(37):
            c.key("rotor", 1 + i, rot=(0, 420.0 * (1 - (1 - i / 36) ** 2), 0))
            c.key("tail_rotor", 1 + i, rot=(0, 300.0 * (1 - (1 - i / 36) ** 2), 0))
        c.key("pilot", 1, rot=(0, 0, 0)); c.key("pilot", 36, rot=(-40, 25, 0))
    roll = {"wasp": 100, "dragonfly": 150, "fly": 125, "moth": 140, "machine": 55}[kind]
    c.key("body", 1, loc=(0, 0, 0), rot=(0, 0, 0))
    c.key("body", 12, loc=(0, 0, -0.05), rot=(-18, roll * 0.3, 6))
    c.key("body", 36, loc=(0, 0, -0.22), rot=(-30, roll, 10))
    if "abdomen" in pb:
        c.key("abdomen", 1, rot=(0, 0, 0)); c.key("abdomen", 36, rot=(-30, 0, -10))
    if "petiole" in pb:
        c.key("petiole", 1, rot=(0, 0, 0)); c.key("petiole", 36, rot=(-25, 0, 0))
    if "head" in pb:
        c.key("head", 1, rot=(0, 0, 0)); c.key("head", 36, rot=(-30, 0, 15))
    for i, b in enumerate(antennae):
        c.key(b, 1, rot=(0, 0, 0)); c.key(b, 36, rot=(-40, 0, 25 * (1 if i else -1)))
    clips.append(c.finish())
    return clips


# --------------------------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------------------------
_salib_export_glb = salib.export_glb


def export_glb_single_sided_wings(asset, objects=None):
    """salib.export_glb, but the wing (membrane) materials export single-sided (glTF doubleSided =
    false).  The wings are closed thin shells (solidified blades), so culling back faces loses
    nothing, while a double-sided alpha-blended shell lets the game draw the unlit underside over the
    lit top in arbitrary order (the first in-game check showed one moth wing tan, the other dark
    brown).  Installed below as salib.export_glb for this script only; salib.py is not edited."""
    for o in (objects or bpy.context.scene.objects):
        if o.type != "MESH":
            continue
        for slot in o.material_slots:
            m = slot.material
            if m is None:
                continue
            proc = bpy.data.materials.get(m.get("sa_proc", ""))
            if (proc or m).get("sa_kind") == "membrane":
                m.use_backface_culling = True
    return _salib_export_glb(asset, objects=objects)


salib.export_glb = export_glb_single_sided_wings


def tri_count(path):
    with open(path, "rb") as f:
        f.read(12)
        chunk_len, _ = struct.unpack("<II", f.read(8))
        data = json.loads(f.read(chunk_len))
    tris = 0
    for m in data.get("meshes", []):
        for p in m.get("primitives", []):
            tris += data["accessors"][p["indices"]]["count"] // 3 if "indices" in p else 0
    return tris


def print_bounds(variant, mesh):
    xs = [v.co.x for v in mesh.data.vertices]
    ys = [v.co.y for v in mesh.data.vertices]
    zs = [v.co.z for v in mesh.data.vertices]
    print(f"BOUNDS {variant}: x {min(xs):.2f}..{max(xs):.2f} (span {max(xs)-min(xs):.2f})  "
          f"y {min(ys):.2f}..{max(ys):.2f} (span {max(ys)-min(ys):.2f})  z {min(zs):.2f}..{max(zs):.2f}", flush=True)


def eevee_id():
    sc = bpy.context.scene
    for eid in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            sc.render.engine = eid
            return eid
        except TypeError:
            continue
    return "CYCLES"


def quick_previews(variant, rig, radius, center):
    """EEVEE renders (front/left/top/threequarter at frame 4 of fly, plus the last death frame)."""
    os.makedirs(QUICK_DIR, exist_ok=True)
    engine = eevee_id()
    ad = rig.animation_data
    saved = salib.PREVIEW_DIR
    salib.PREVIEW_DIR = QUICK_DIR
    for track in ad.nla_tracks:
        track.mute = track.name != "fly"
    salib.render_previews(variant + "_fly", radius, center=center, size=448, samples=16,
                          views=("front", "left", "top", "threequarter"), engine=engine, frame=4)
    for f in (1, 2, 3, 4, 5, 6):  # wing-beat strip: one full beat
        salib.render_previews(f"{variant}_f{f:02d}", radius, center=center, size=320, samples=16,
                              views=("top", "front"), engine=engine, frame=f)
    for track in ad.nla_tracks:
        track.mute = track.name != "death"
    salib.render_previews(variant + "_death", radius, center=center, size=448, samples=16,
                          views=("threequarter", "top"), engine=engine, frame=36)
    for track in ad.nla_tracks:
        track.mute = False
    salib.PREVIEW_DIR = saved
    bpy.context.scene.frame_set(1)


def build(variant: str, quick=False):
    cfg = VARIANTS[variant]
    kind = cfg["kind"]
    salib.reset_scene(variant)
    mats = flyer_materials()
    body = BodyX(variant, mats)
    if kind == "wasp":
        bones, wings, legs, extras = build_wasp(body, cfg)
        radius, center = 3.0 * cfg["S"], (0, 0.15 * cfg["S"], Z0)
    elif kind == "dragonfly":
        bones, wings, legs, extras = build_dragonfly(body)
        radius, center = 4.2, (0, 0.0, Z0)
    elif kind == "fly":
        bones, wings, legs, extras = build_fly(body)
        radius, center = 3.4, (0, 0.0, Z0)
    elif kind == "moth":
        bones, wings, legs, extras = build_moth(body)
        radius, center = 3.6, (0, 0.0, Z0)
    else:
        bones, wings, legs, extras = build_machine(body)
        radius, center = 4.2, (0, 0.1, Z0 + 0.2)
    mesh = body.join_at_origin()
    print_bounds(variant, mesh)

    rig_bones = [BoneDef("root", (0, 0, 0), (0, 0.25, 0))]
    b_head, b_tail = extras.get("body", ((0, 0.1, Z0), (0, -0.3, Z0)))
    rig_bones.append(BoneDef("body", b_head, b_tail, parent="root"))
    if "head" in extras:
        h_head, h_tail = extras["head"]
        rig_bones.append(BoneDef("head", h_head, h_tail, parent="body"))
    for nm, root, tip, _s in wings:
        rig_bones.append(BoneDef(nm, root, tip, parent="body"))
    rig_bones += bones
    rig = salib.build_armature("Rig", rig_bones)
    salib.skin(mesh, rig)
    # every vertex group must match a bone
    bone_names = {b.name for b in rig_bones}
    missing = [vg.name for vg in mesh.vertex_groups if vg.name not in bone_names]
    assert not missing, f"vertex groups without bones: {missing}"

    clips = make_clips(rig, kind, wings, legs, has_antennae="antenna.L" in bone_names, has_gun="gun" in bone_names)
    salib.bake_actions(rig, clips)

    if quick:
        quick_previews(variant, rig, radius, center)
        n = sum(len(p.vertices) - 2 for p in mesh.data.polygons)
        print(f"QUICK {variant}: ~{n} triangles, {len(rig_bones)} bones", flush=True)
        return None
    path, s = salib.finalize_asset(variant, [rig, mesh], preview_radius=radius, preview_center=center,
                                   views=("front", "back", "left", "right", "threequarter", "top"))
    assert sorted(a["name"] for a in s["animations"]) == ["attack", "death", "fly", "idle"], s["animations"]
    assert "M_Team" in s["materials"] or kind != "wasp", s["materials"]
    tris = tri_count(path)
    print(f"TRIANGLES {variant} {tris}", flush=True)
    assert tris <= 9000, f"{variant}: {tris} triangles over budget"
    return path


if __name__ == "__main__":
    argv = salib.script_args()
    quick = "--quick" in argv
    args = [a for a in argv if not a.startswith("-")] or list(VARIANTS)
    for v in args:
        build(v, quick=quick)
        print("BUILT", v, flush=True)
