"""Builds the scorpion family: Savage, Spear Gun, Ninja - rebuilt from the original 1999 art.

References (reference/models/scorpion_*): original_3d_portrait.png (the developers' own render),
sprite_actions_Y.png (top-down sprites, 8 facings), team_colour_regions.png, and
_common/original_loading_screen_2.png (red scorpions, the clearest original render).

What the originals look like (all three share the body):
* A low, flat, lobster-like body: a flattened prosoma shield with a small face (two eyes, mouth
  parts) and a mesosoma of five ridged plates narrowing towards the tail.  Body ~0.9 cells long,
  ~0.5 wide, ~0.3 tall, carried low between the legs.
* The tail rises from the rear of the body backwards AND up (it is not curled over the head): five
  bead-like segments tapering to the tip, which is the rear-most and highest point (~1 cell up and
  ~0.6 cells behind the body).  Savage: a big orange teardrop sting.  Spear Gun: a brown wooden
  harpoon launcher with pale metal bands lying horizontally on a shorter tail, barrel forward over
  the back.  Ninja: team-coloured tail with black bands ending in a grey launcher that holds a pale
  blue-white throwing star (flat, so it reads as a star from above like the sprite).
* Two big claws: thick arms going out to the side and forward (elbows ~0.6 cells out), hands
  curling inwards so the claws nearly close a ring in front of the head (tips ~0.5 cells ahead
  of the prosoma).  The movable finger opens/closes.
* Eight long legs splayed in a fan, knees above the back, feet ~1 cell out to each side.
* Team colour: everything except the weapon, the eyes and the lower legs (Savage / Spear Gun);
  Ninja = team-coloured body and tail beads, glossy black legs, claws and tail bands.
Sprite footprint from above: ~45 px wide (leg span) by ~48 px from the claw tips to the sting
(with the original camera tilt) -> about 1.9 x 2.0 cells; the rest pose fits that.
Attack (sprites): Savage whips the tail forward over the head so the sting strikes in front;
Ninja flicks the tail to throw the star; Spear Gun fires the launcher (recoil only).
Legs: eight 4-joint legs (coxa ball, femur, knee ball, tibia, ankle ball, tarsus) behind the
pedipalps, the fan of the "faces down" sprite (front pair forward, rear pair back), knees above the
back, feet 0.8-0.96 cells out.  Walk = alternating tetrapod (L1 L3 R2 R4 / L2 L4 R1 R3), 12 frames,
stride matched to the game's nominal 2.5 cells/s playback so planted feet do not slide; the feet
are keyed in world space through the IK bones' rest matrices (see key_walk).  Death = the body
drops flat, the legs splay out on the ground like the dead sprite's first frame.
Inferred: joint counts, body height and underside, the darkening of the leg tips (baked as a
height gradient in the team material so it works in every team colour).
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import salib  # noqa: E402
from salib import BoneDef, Body, Clip, LegSpec  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

VARIANTS = {
    "scorpion_savage": dict(kind="savage"),
    "scorpion_spear_gun": dict(kind="spear"),
    "scorpion_ninja": dict(kind="ninja"),
}

# Extra renders (top-down + game-camera angle) for the comparison sheets; skipped when the folder
# does not exist (it is the scorpion crew's scratch folder, not part of the package).
EXTRA_RENDER_DIR = os.environ.get("SA_SCORPION_RENDERS", r"D:\SwarmAssault3D-complete\qa\agents\scorpions\renders")

# --------------------------------------------------------------------------------------------
# geometry (Blender units = map cells, rest pose faces -Y, Z up)
# --------------------------------------------------------------------------------------------
# tail joints, rear of the body -> tip (the sting / weapon attaches at the last point)
TAIL_HIGH = [(0, 0.40, 0.26), (0, 0.57, 0.40), (0, 0.72, 0.55), (0, 0.85, 0.71), (0, 0.94, 0.88), (0, 0.985, 1.05)]
TAIL_LOW = [(0, 0.40, 0.26), (0, 0.56, 0.37), (0, 0.70, 0.48), (0, 0.82, 0.60), (0, 0.91, 0.72), (0, 0.96, 0.84)]
TAIL_R = [0.15, 0.135, 0.12, 0.105, 0.095, 0.085]       # radius at each joint

PROSOMA_C = (0, -0.20, 0.215)
PROSOMA_S = (0.26, 0.27, 0.105)
# mesosoma plates: (y, rx, ry, rz), all centred at z = 0.205
PLATES = [
    (0.03, 0.225, 0.095, 0.095),
    (0.13, 0.215, 0.090, 0.092),
    (0.225, 0.200, 0.085, 0.088),
    (0.31, 0.185, 0.080, 0.084),
    (0.39, 0.170, 0.075, 0.080),
]
PLATE_Z = 0.205
LEG_RADIUS = 0.056
MOVE_FRAMES = 12
# The game plays `move` at (unit speed / 2.5) x, i.e. the clip nominally covers 2.5 cells/s; a foot
# is planted for half the cycle, so a slide-free stride is 1.25 x the clip length in seconds.
MOVE_STRIDE = 1.25 * MOVE_FRAMES / salib.FPS


def leg_specs():
    # (name, root, knee, foot, walk phase) for the left side; the right side is mirrored
    base = [
        ("L1", (0.20, -0.30, 0.19), (0.52, -0.52, 0.40), (0.80, -0.78, 0.0), 0.0),
        ("L2", (0.22, -0.12, 0.19), (0.58, -0.22, 0.42), (0.96, -0.36, 0.0), 0.5),
        ("L3", (0.22, 0.04, 0.19), (0.58, 0.12, 0.42), (0.96, 0.18, 0.0), 0.0),
        ("L4", (0.20, 0.20, 0.19), (0.52, 0.40, 0.40), (0.82, 0.62, 0.0), 0.5),
    ]
    specs = []
    for name, root, knee, foot, phase in base:
        m = lambda p: (-p[0], p[1], p[2])
        specs.append(LegSpec(name, +1, root, knee, foot, phase=phase, radius=LEG_RADIUS))
        specs.append(LegSpec("R" + name[1:], -1, m(root), m(knee), m(foot), phase=(phase + 0.5) % 1.0, radius=LEG_RADIUS))
    return specs


def claw_points(s):
    return {
        "shoulder": (s * 0.22, -0.34, 0.20),
        "elbow": (s * 0.62, -0.54, 0.23),
        "wrist": (s * 0.64, -0.82, 0.18),
        "fixed_tip": (s * 0.22, -1.00, 0.13),
        "finger_tip": (s * 0.36, -1.10, 0.13),
    }


# --------------------------------------------------------------------------------------------
# mesh helpers (local copies / additions - salib is shared and must not be edited)
# --------------------------------------------------------------------------------------------
def ellipsoid(body, bone, mat, center, radial, axial, direction, segments=14, rings=8):
    """A sphere stretched along `direction` (bead / hand / plate)."""
    rot = Vector(direction).to_track_quat("Z", "Y").to_euler()
    return body.sphere(bone, mat, tuple(center), 1.0, scale=(radial, radial, axial), rot=rot,
                       segments=segments, rings=rings)


def small_sphere(body, bone, mat, center, r, scale=(1, 1, 1)):
    o = body.sphere(bone, mat, tuple(center), r, scale=scale, segments=10, rings=6)
    o["sa_no_subdiv"] = True
    return o


def star_part(body, bone, mat, center, r_out, r_in, thick, points=4, rot_deg=0.0):
    """A flat throwing star in the XY plane (fan-triangulated so the concave outline exports)."""
    n = points * 2
    cx, cy, cz = center
    top, bot = [], []
    for k in range(n):
        ang = math.radians(rot_deg) + k * math.pi / points
        r = r_out if k % 2 == 0 else r_in
        top.append((cx + r * math.cos(ang), cy + r * math.sin(ang), cz + thick / 2))
        bot.append((cx + r * math.cos(ang), cy + r * math.sin(ang), cz - thick / 2))
    verts = top + bot + [(cx, cy, cz + thick / 2), (cx, cy, cz - thick / 2)]
    ct, cb = 2 * n, 2 * n + 1
    faces = []
    for k in range(n):
        k2 = (k + 1) % n
        faces.append((ct, k, k2))                 # top fan, normal +Z
        faces.append((cb, k2 + n, k + n))         # bottom fan, normal -Z
        faces.append((k, k + n, k2 + n, k2))      # outward sides
    me = bpy.data.meshes.new(f"{body.name}_star")
    me.from_pydata(verts, [], faces)
    me.update()
    o = bpy.data.objects.new(f"{body.name}_star", me)
    salib.link(o)
    o["sa_no_subdiv"] = True
    return body._finish(o, bone, mat, smooth=False)


def leg_mesh(body, spec, mat, tip_mat=None):
    """Coxa (ball + short stub), femur, knee ball, tibia, ankle ball, tarsus tapering to the foot."""
    n = f"leg.{spec.name}"
    root, knee, foot = Vector(spec.root), Vector(spec.knee), Vector(spec.foot)
    mid = root.lerp(knee, 0.35)
    r = spec.radius
    small_sphere(body, f"{n}.coxa", mat, root, r * 1.35, scale=(1, 1, 0.8))
    body.segment(f"{n}.coxa", mat, tuple(root), tuple(mid), r * 1.2, r * 1.0, verts=10)
    body.segment(f"{n}.femur", mat, tuple(mid), tuple(knee), r * 1.0, r * 0.84, verts=10)
    small_sphere(body, f"{n}.femur", mat, knee, r * 0.98)
    ankle = knee.lerp(foot, 0.70)
    body.segment(f"{n}.tibia", mat, tuple(knee), tuple(ankle), r * 0.86, r * 0.58, verts=10)
    small_sphere(body, f"{n}.tibia", mat, ankle, r * 0.62)
    body.segment(f"{n}.tibia", tip_mat or mat, tuple(ankle), tuple(foot), r * 0.56, r * 0.16, verts=10)


# --------------------------------------------------------------------------------------------
# leg animation (local replacements for salib.key_walk_cycle / key_death)
# --------------------------------------------------------------------------------------------
# salib.leg_bones() makes every IK target bone point straight up (+Z), so a pose-bone `location`
# keyed as (0, stride, lift) - what salib.key_walk_cycle does - moves the foot UP by `stride` and
# FORWARD by `lift`: the feet sink through the ground and the stride is tiny.  The helpers below
# convert armature-space offsets through the bone's rest matrix so stride/lift mean what they say.
def ik_local(rig, bone_name, offset):
    m = rig.data.bones[bone_name].matrix_local.to_3x3()
    return tuple(m.inverted() @ Vector(offset))


def key_foot(clip, rig, spec, frame, offset):
    clip.key(f"leg.{spec.name}.ik", frame, loc=ik_local(rig, f"leg.{spec.name}.ik", offset))


def key_walk(clip, rig, specs, frames, stride, lift, body_bob=0.012):
    """Alternating-tetrapod walk keyed on every frame: a planted foot slides straight back (+Y, the
    creature faces -Y) at a constant rate for half the cycle - no sliding when the game plays the
    cycle at its nominal 2.5 cells/s - then swings forward in an arc of height `lift`."""
    for spec in specs:
        for i in range(frames):
            ph = (i / frames + spec.phase) % 1.0
            if ph < 0.5:
                s = ph / 0.5
                y, z = -stride / 2 + stride * s, 0.0
            else:
                s = (ph - 0.5) / 0.5
                y, z = stride / 2 - stride * s, lift * math.sin(math.pi * s)
            key_foot(clip, rig, spec, 1 + i, (0.0, y, z))
    for i in range(frames):
        ph = (i / frames) * 2.0 * math.pi * 2.0      # two bobs per cycle (one per tetrapod step)
        clip.key("body", 1 + i, loc=(0, 0, body_bob * (0.5 - 0.5 * math.cos(ph))))


def key_death_splay(clip, rig, specs, frames, sink=0.11, splay=0.18, roll_deg=6.0):
    """Collapse like the dead sprite: the body drops onto the ground, the legs splay outward and
    flatten (feet stay on the ground), the knees drop with the body."""
    clip.key("body", 1, loc=(0, 0, 0), rot=(0, 0, 0))
    clip.key("body", int(frames * 0.6), loc=(0, 0, -sink * 0.8), rot=(2, 0, roll_deg * 0.7))
    clip.key("body", frames, loc=(0, 0.02, -sink), rot=(3, 0, roll_deg))
    for spec in specs:
        key_foot(clip, rig, spec, 1, (0, 0, 0))
        key_foot(clip, rig, spec, int(frames * 0.4), (splay * 0.6 * spec.side, 0.04, 0.03))
        key_foot(clip, rig, spec, frames, (splay * spec.side, 0.10, 0.0))


def tail_mesh(body, T, R, bead_mat, joint_mat):
    for i in range(5):
        a, b = Vector(T[i]), Vector(T[i + 1])
        d = b - a
        mid = (a + b) * 0.5
        rb = (R[i] + R[i + 1]) * 0.5
        ellipsoid(body, f"tail.{i + 1}", bead_mat, mid, rb * 1.04, d.length * 0.70, d, segments=12, rings=7)
        body.segment(f"tail.{i + 1}", joint_mat, tuple(a), tuple(b), R[i] * 0.8, R[i + 1] * 0.8, verts=12)


def add_height_darkening(mat, z0=0.0, z1=0.12, dark=0.45):
    """Multiply the (procedural) base colour by a height ramp so the lower legs bake darker, as in the
    sprites, in any team colour.  Object-space Z = world Z because the mesh origin is reset to the
    world origin after joining."""
    p = salib._principled(mat)
    if p is None or not p.inputs["Base Color"].links:
        return
    nt = mat.node_tree
    src = p.inputs["Base Color"].links[0].from_socket
    texco = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(texco.outputs["Object"], sep.inputs["Vector"])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.clamp = True
    mr.inputs["From Min"].default_value = z0
    mr.inputs["From Max"].default_value = z1
    mr.inputs["To Min"].default_value = dark
    mr.inputs["To Max"].default_value = 1.0
    nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
    out = salib._mix_rgb(nt, "MULTIPLY", src, mr.outputs["Result"], 1.0)
    nt.links.new(out, p.inputs["Base Color"])


def reset_origin(obj):
    """Bake the object transform into the mesh so the origin is the world origin."""
    obj.data.transform(obj.matrix_world)
    obj.matrix_world = Matrix.Identity(4)


def triangle_count(obj):
    return sum(max(0, len(p.vertices) - 2) for p in obj.data.polygons)


# --------------------------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------------------------
def build(variant: str):
    kind = VARIANTS[variant]["kind"]
    salib.reset_scene(variant)
    mats = salib.standard_materials("Y")
    mats["M_Sting"] = salib.material("M_Sting", (0.96, 0.50, 0.12), roughness=0.35, emission=(0.9, 0.4, 0.1),
                                     emission_strength=0.15, kind="glossy")
    mats["M_Brown"] = salib.material("M_Brown", (0.40, 0.22, 0.11), roughness=0.75, kind="wood")
    mats["M_Star"] = salib.material("M_Star", (0.82, 0.87, 0.96), roughness=0.25, metallic=0.6, kind="metal")
    mats["M_Steel"] = salib.material("M_Steel", (0.76, 0.77, 0.80), roughness=0.3, metallic=0.8, kind="metal")
    # the sprites' lower legs are darker: bake a ramp over the lowest 0.12 cells (below the claws)
    add_height_darkening(mats["M_Team"], z0=0.0, z1=0.12, dark=0.45)

    body = Body(variant, mats)
    T = "M_Team"
    limb_mat = "M_Black" if kind == "ninja" else T
    tail_joint_mat = "M_Black" if kind == "ninja" else T
    TAIL = TAIL_LOW if kind == "spear" else TAIL_HIGH

    # ---- body: prosoma shield + five mesosoma plates + face ----------------------------------
    body.sphere("body", T, PROSOMA_C, 1.0, scale=PROSOMA_S, segments=18, rings=10)
    for (y, rx, ry, rz) in PLATES:
        body.sphere("body", T, (0, y, PLATE_Z), 1.0, scale=(rx, ry, rz), segments=14, rings=7)
    for s in (+1, -1):
        small_sphere(body, "body", "M_Eye", (s * 0.065, -0.40, 0.305), 0.024)
        # chelicerae (small mouth parts under the front edge)
        body.segment("body", limb_mat, (s * 0.05, -0.42, 0.17), (s * 0.075, -0.53, 0.14), 0.028, 0.008, verts=8)

    # ---- tail ---------------------------------------------------------------------------------
    tail_mesh(body, TAIL, TAIL_R, T, tail_joint_mat)
    tip = Vector(TAIL[5])
    tip_dir = (tip - Vector(TAIL[4])).normalized()
    if kind == "savage":
        ellipsoid(body, "sting", "M_Sting", tip + Vector((0, 0, 0.03)), 0.13, 0.15, (0, -0.2, 1.0))
        body.segment("sting", "M_Sting", (0, 0.975, 1.15), (0, 0.90, 1.27), 0.055, 0.022, verts=10)
        body.segment("sting", "M_Sting", (0, 0.905, 1.262), (0, 0.835, 1.335), 0.022, 0.003, verts=8)
        sting_tail = (0, 0.84, 1.33)
    elif kind == "spear":
        gz = 0.90
        body.cube("sting", "M_Brown", (0, 0.74, gz), size=(0.15, 0.56, 0.13))
        body.cube("sting", "M_Steel", (0, 0.58, gz), size=(0.165, 0.045, 0.145))
        body.cube("sting", "M_Steel", (0, 0.88, gz), size=(0.165, 0.045, 0.145))
        body.cube("sting", "M_Steel", (0, 0.49, gz + 0.02), size=(0.11, 0.07, 0.11))      # muzzle block
        body.cylinder("sting", "M_Accent", (0, 0.32, gz + 0.025), 0.018, 0.30, rot=(math.radians(90), 0, 0), verts=8)
        body.cone("sting", "M_Steel", (0, 0.12, gz + 0.025), 0.035, 0.0, 0.11, rot=(math.radians(90), 0, 0), verts=8)
        sting_tail = (0, 0.40, gz)
    else:
        nozzle_c = tip + tip_dir * 0.07
        body.cylinder("sting", "M_Accent", tuple(nozzle_c), 0.05, 0.16,
                      rot=tip_dir.to_track_quat("Z", "Y").to_euler(), verts=10)
        star_c = tip + tip_dir * 0.17
        star_part(body, "sting", "M_Star", tuple(star_c), 0.17, 0.055, 0.016, points=4, rot_deg=0.0)
        small_sphere(body, "sting", "M_Accent", star_c, 0.03)
        sting_tail = tuple(tip + tip_dir * 0.22)

    # ---- claws --------------------------------------------------------------------------------
    for s in (+1, -1):
        p = claw_points(s)
        side = "L" if s > 0 else "R"
        small_sphere(body, f"claw.{side}.arm", limb_mat, p["shoulder"], 0.086, scale=(1, 1, 0.8))
        body.segment(f"claw.{side}.arm", limb_mat, p["shoulder"], p["elbow"], 0.085, 0.078, verts=10)
        small_sphere(body, f"claw.{side}.arm", limb_mat, p["elbow"], 0.084)
        body.segment(f"claw.{side}.fore", limb_mat, p["elbow"], p["wrist"], 0.080, 0.095, verts=10)
        body.sphere(f"claw.{side}.hand", limb_mat, p["wrist"], 0.12, scale=(1.0, 1.0, 0.72), segments=12, rings=8)
        body.segment(f"claw.{side}.hand", limb_mat, p["wrist"], p["fixed_tip"], 0.10, 0.02, verts=10)
        body.segment(f"claw.{side}.finger", limb_mat, p["wrist"], p["finger_tip"], 0.07, 0.016, verts=10)

    # ---- legs ---------------------------------------------------------------------------------
    specs = leg_specs()
    for spec in specs:
        leg_mesh(body, spec, mat=limb_mat)
    # The realism pass would Catmull-Clark every part (3x the budget); the primitives here are
    # built at their final resolution (10-12 sided, smooth shaded), so only the bevels stay on.
    for p in body.parts:
        if not p.obj.get("sa_bevel"):
            p.obj["sa_no_subdiv"] = True
    mesh = body.join()
    reset_origin(mesh)
    tris = triangle_count(mesh)
    salib.log(variant, "triangles", tris)
    assert tris < 8000, f"{variant}: {tris} triangles exceed the 8k budget"

    # ---- rig ----------------------------------------------------------------------------------
    bones = [
        BoneDef("root", (0, 0, 0), (0, 0.25, 0)),
        BoneDef("body", (0, 0.42, 0.24), (0, -0.40, 0.24), parent="root"),
    ]
    for i in range(5):
        bones.append(BoneDef(f"tail.{i + 1}", TAIL[i], TAIL[i + 1], parent="body" if i == 0 else f"tail.{i}", connect=i > 0))
    bones.append(BoneDef("sting", TAIL[5], sting_tail, parent="tail.5", connect=True))
    for s in (+1, -1):
        p = claw_points(s)
        side = "L" if s > 0 else "R"
        bones += [
            BoneDef(f"claw.{side}.arm", p["shoulder"], p["elbow"], parent="body"),
            BoneDef(f"claw.{side}.fore", p["elbow"], p["wrist"], parent=f"claw.{side}.arm", connect=True),
            BoneDef(f"claw.{side}.hand", p["wrist"], p["fixed_tip"], parent=f"claw.{side}.fore", connect=True),
            BoneDef(f"claw.{side}.finger", p["wrist"], p["finger_tip"], parent=f"claw.{side}.fore"),
        ]
    for spec in specs:
        bones += salib.leg_bones(spec, parent="body")
    rig = salib.build_armature("Rig", bones)
    salib.skin(mesh, rig)
    salib.apply_leg_ik(rig, specs)

    # ---- animation ----------------------------------------------------------------------------
    def key_claws(c, f, open_deg):
        c.key("claw.L.finger", f, rot=(0, 0, open_deg))
        c.key("claw.R.finger", f, rot=(0, 0, -open_deg))

    def key_arms(c, f, out_deg, lift_deg=0.0):
        c.key("claw.L.arm", f, rot=(lift_deg, 0, out_deg))
        c.key("claw.R.arm", f, rot=(lift_deg, 0, -out_deg))

    def key_tail(c, f, bend_deg, sway_deg=0.0, sting_deg=None):
        """bend_deg: one angle for every joint, or a sequence of five (base -> tip)."""
        bends = list(bend_deg) if isinstance(bend_deg, (list, tuple)) else [bend_deg] * 5
        for i in range(1, 6):
            c.key(f"tail.{i}", f, rot=(bends[i - 1], 0, sway_deg))
        c.key("sting", f, rot=(bends[-1] if sting_deg is None else sting_deg, 0, 0))

    clips = []
    # idle: breathing bob, the tail sways and flexes a little, the claws open and close
    c = Clip(rig, "idle", 48)
    salib.key_idle(c, specs, 48, body_bob=0.01)
    for f, sw, bd in ((1, 0, 0), (12, 3, 1.5), (24, 0, 0), (36, -3, -1.5), (48, 0, 0)):
        key_tail(c, f, bd, sw)
    for f, o in ((1, 0), (16, 12), (32, 0), (48, 0)):
        key_claws(c, f, o)
    key_arms(c, 1, 0); key_arms(c, 24, 2); key_arms(c, 48, 0)
    clips.append(c.finish())
    # move: alternating-tetrapod walk, the tail bobs with each step, the claws held slightly open
    c = Clip(rig, "move", MOVE_FRAMES)
    key_walk(c, rig, specs, MOVE_FRAMES, stride=MOVE_STRIDE, lift=0.12, body_bob=0.012)
    for f, b in ((1, 0), (4, 3), (7, 0), (10, 3), (MOVE_FRAMES, 0)):
        key_tail(c, f, b)
    key_claws(c, 1, 8); key_claws(c, MOVE_FRAMES, 8)
    clips.append(c.finish())
    # attack
    c = Clip(rig, "attack", 14, loop=False)
    for spec in specs:
        key_foot(c, rig, spec, 1, (0, 0, 0))
        key_foot(c, rig, spec, 14, (0, 0, 0))
    if kind == "savage":
        # the tail winds back, whips forward over the head and the sting strikes in front; the
        # claws open wide and snap shut; the body lunges forward
        strike = (54, 40, 28, 20, 14)
        hold = (50, 38, 26, 18, 12)
        key_tail(c, 1, 0); key_tail(c, 3, -10); key_tail(c, 6, strike, 0, 24); key_tail(c, 8, hold, 0, 22); key_tail(c, 14, 0)
        key_claws(c, 1, 0); key_claws(c, 3, 32); key_claws(c, 6, -4); key_claws(c, 10, 6); key_claws(c, 14, 0)
        key_arms(c, 1, 0); key_arms(c, 3, 14, -6); key_arms(c, 6, -6, 4); key_arms(c, 14, 0)
        c.key("body", 1, loc=(0, 0, 0), rot=(0, 0, 0))
        c.key("body", 6, loc=(0, -0.09, 0.01), rot=(5, 0, 0))
        c.key("body", 14, loc=(0, 0, 0), rot=(0, 0, 0))
    elif kind == "spear":
        # the launcher fires forward: recoil along the barrel, the tail gives a little, then resets
        key_tail(c, 1, 0); key_tail(c, 2, -5); key_tail(c, 5, 2); key_tail(c, 14, 0)
        c.key("sting", 1, loc=(0, 0, 0)); c.key("sting", 2, loc=(0, -0.10, 0)); c.key("sting", 6, loc=(0, 0, 0))
        c.key("sting", 14, loc=(0, 0, 0))
        c.key("body", 1, loc=(0, 0, 0)); c.key("body", 3, loc=(0, 0.03, 0)); c.key("body", 14, loc=(0, 0, 0))
    else:
        # ninja: the tail flicks forward to throw the star, then springs back
        key_tail(c, 1, 0); key_tail(c, 2, -8); key_tail(c, 5, 20, 0, 30); key_tail(c, 9, 4); key_tail(c, 14, 0)
        c.key("body", 1, loc=(0, 0, 0)); c.key("body", 5, loc=(0, -0.03, 0)); c.key("body", 14, loc=(0, 0, 0))
        key_claws(c, 1, 0); key_claws(c, 5, 10); key_claws(c, 14, 0)
    clips.append(c.finish())
    # death: the body drops to the ground, the legs splay out flat, the tail falls back, the claws open
    c = Clip(rig, "death", 36, loop=False)
    key_death_splay(c, rig, specs, 36, sink=0.11, splay=0.18)
    key_tail(c, 1, 0)
    for i, bd in enumerate((-30, -18, -14, -10, -8), start=1):
        c.key(f"tail.{i}", 36, rot=(bd, 0, 6))
    c.key("sting", 36, rot=(-10, 0, 0))
    key_claws(c, 1, 0); key_claws(c, 36, 28)
    key_arms(c, 1, 0); key_arms(c, 36, 28, 6)
    clips.append(c.finish())
    salib.bake_actions(rig, clips)

    path, s = salib.finalize_asset(variant, [rig, mesh], preview_radius=3.4, preview_center=(0, 0, 0.45))
    assert sorted(a["name"] for a in s["animations"]) == ["attack", "death", "idle", "move"]

    # extra study renders (top-down like the sprite, and the game camera angle) into the crew folder
    if os.path.isdir(os.path.dirname(EXTRA_RENDER_DIR)):
        os.makedirs(EXTRA_RENDER_DIR, exist_ok=True)
        old = salib.PREVIEW_DIR
        salib.PREVIEW_DIR = EXTRA_RENDER_DIR
        salib.PREVIEW_VIEWS["game"] = (0.0, 58.0)
        try:
            salib.render_previews(variant, radius=4.2, center=(0, 0, 0.35), views=("top", "game"), samples=48)
        finally:
            salib.PREVIEW_DIR = old
    return path


if __name__ == "__main__":
    args = [a for a in salib.script_args() if not a.startswith("-")] or list(VARIANTS)
    for v in args:
        build(v)
        print("BUILT", v, flush=True)
