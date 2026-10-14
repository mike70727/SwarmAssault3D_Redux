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
  the back, a harpoon sticking out of the muzzle.  Ninja: team-coloured tail with black bands ending
  in a grey launcher that holds a pale blue-white throwing star (flat, so it reads as a star from
  above like the sprite).
* Two big claws: thick arms going out to the side and forward (elbows ~0.6 cells out), hands
  curling inwards so the claws nearly close a ring in front of the head (tips ~0.5 cells ahead
  of the prosoma).  The movable finger opens/closes.
* Eight long legs splayed in a fan, knees above the back, feet ~1 cell out to each side.
* Team colour: everything except the weapon, the eyes and the lower legs (Savage / Spear Gun);
  Ninja = team-coloured body and tail beads, glossy black legs, claws and tail bands.
Sprite footprint from above: ~45 px wide (leg span) by ~48 px from the claw tips to the sting
(with the original camera tilt) -> about 1.9 x 2.0 cells; the rest pose fits that.

Attacks (attack crew, 2026-10-13), read from the original Game.ANI / Game.DDF frames of all eight
facings (qa/agents/scorpion_attacks/refsheets): every attack has two frames, the second carries the
hit ('Damage') or the launch ('Fire Point').
* Savage, UNSCOSA?_AT* (150 + 150 ms, Damage on frame 2).  Frame 1: the tail COCKED - raised almost
  vertical, the sting hooked forward above the rear of the body (sting ~0.4 cells behind the centre,
  ~1.1 high).  Frame 2: the STRIKE - the tail whipped forward over the back, the sting stabbing down
  in front of the head (~0.45 cells ahead of the centre).  The clip starts and ends in the cocked
  stance (the game restarts it at every sting, ~every 0.5 s), the strike lands at the shot moment.
* Spear Gun, UNSCOSG?_AT* (100 + 100 ms, Fire Point on frame 2).  Frame 1: the harpoon slides
  forward out of the launcher (~0.2 cells); frame 2: it is gone, the claws twitch.  Clip: the gun
  aims, the harpoon slides out and leaves at the shot moment while the launcher kicks back, a new
  harpoon grows out of the muzzle during the recovery.
* Ninja, UNSCOST?_AT* (20 + 100 ms, Fire Point on frame 2).  Frame 1: the star has left the tail tip
  and is over the middle of the body, the tail tip raised; frame 2: the star gone, the tail flicked
  up.  The Launch Points of the frames sit above the body centre (~0.9-1.0 cells high).  Clip: the
  tail winds back and flicks up / forward, the star leaves the launcher, flies forward over the body
  and is released above the centre at the shot moment; follow-through, a new star appears.
Timing contract (views.rs / world.rs): the game restarts `attack` at every shot (0.05 s blend in),
plays it at clip length / attack_anim_time and releases the shot fire_delay after the start on its
30 Hz ticks (tick 5 = 0.167 s for all three) - VARIANTS below; leaving the attack it blends to idle
or move in 0.15 s.  The build log prints each unit's MUZZLE (x right, y up, z ahead, cells).

Legs (attack crew): eight 4-joint legs (coxa ball, femur, knee ball, tibia, ankle ball, tarsus).
* The foot (ankle ball + tarsus) is its own deforming bone, leg.X.ik, a child of the root and the
  IK target: a planted foot cannot slide, tilt or sink whatever the femur / tibia do.  The soles are
  seated on the ground after the mesh is joined (lowest foot vertex at z = +0.0005).
* No IK constraints: solve_legs() (an analytic two-bone IK after the spider crew's) keys the femur /
  tibia as plain FK rotations on every frame, the knee kept in the leg's own modelled bend plane
  carried by the body.  salib.apply_leg_ik's fixed +-90 deg pole angles put the knees 0.07-0.44
  cells off their modelled positions (left knees on the ground); here the rest knee error is 0.
* Every clip keys every bone at rest on its first frame (key_rest_all), so no pose leaks from one
  clip into the next when salib.bake_actions bakes them one after another.
* All clips are keyed from frame 0: the GLB clips start at t = 0 and the loops (idle 0..48, move
  0..10, frame N = frame 0) wrap seamlessly in Bevy (a clip keyed from frame 1 starts at t = 1/30 s
  and Bevy holds that first key once per loop: a one-frame hitch and a foot slip at the seam).
* Walk = alternating tetrapod (L1 L3 R2 R4 / L2 L4 R1 R3), 10 frames (0.33 s, the original walk is
  3 x 100 ms), stride 0.42 matched to the game's nominal 2.5 cells/s playback so planted feet do not
  slide (the old 12-frame / 0.5-cell stride put the front and rear feet 0.06 cells out of the legs'
  reach); the feet are keyed in armature space through the foot bones' rest matrices (ik_local /
  key_walk).  STANCE_DY shifts the stance windows per leg pair to keep every foot within reach and
  neighbouring lower legs apart (closest approach 0.054 cells).
Checked on the exported GLBs with qa/agents/scorpion_attacks/tools/glb_legs.py.
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

# Game timing (assets/data/units.ron, read only) - the attack clip is scaled to attack_anim_time and
# the shot leaves fire_delay after the attack starts, on the sim's 30 Hz ticks.
VARIANTS = {
    "scorpion_savage": dict(kind="savage", attack_frames=14, attack_anim_time=0.45, fire_delay=0.15),
    "scorpion_spear_gun": dict(kind="spear", attack_frames=15, attack_anim_time=0.50, fire_delay=0.16),
    "scorpion_ninja": dict(kind="ninja", attack_frames=15, attack_anim_time=0.50, fire_delay=0.16),
}
SIM_HZ = 30.0

# Extra renders (top-down + game-camera angle) for the comparison sheets; skipped when the folder's
# parent does not exist (it is the crew's scratch folder, not part of the package).
EXTRA_RENDER_DIR = os.environ.get("SA_SCORPION_RENDERS", r"D:\SwarmAssault3D-complete\qa\agents\scorpion_attacks\renders")

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
# legs, left side (+X; the right side is mirrored): coxa on the body, knee above the back, toe on
# the ground; the ankle (foot bone head = IK target) sits ANKLE_T of the way from the knee to the toe
LEGS = [
    # name, root, knee, toe, walk phase (alternating tetrapod)
    ("L1", (0.20, -0.30, 0.19), (0.52, -0.52, 0.40), (0.80, -0.78, 0.0), 0.0),
    ("L2", (0.22, -0.12, 0.19), (0.58, -0.22, 0.42), (0.96, -0.36, 0.0), 0.5),
    ("L3", (0.22, 0.04, 0.19), (0.58, 0.12, 0.42), (0.96, 0.18, 0.0), 0.0),
    ("L4", (0.20, 0.20, 0.19), (0.52, 0.40, 0.40), (0.82, 0.62, 0.0), 0.5),
]
ANKLE_T = 0.70
# walk stance windows (armature +Y = backwards) per leg pair.  The legs reach 0.67-0.70 cells from
# hip to ankle; a symmetric window would stretch the front pair past its reach at the front of the
# stride and the rear pair at the back (a gap at the ankle), so the front pair steps a little behind
# its rest position and the rear pair a little ahead of it; the middle pairs are spread so that L2 /
# L3 (same distance out) never meet at the switch.
STANCE_DY = {"1": 0.04, "2": -0.03, "3": 0.05, "4": -0.03}
# 10 frames = 0.33 s per cycle (the original walk: 3 frames x 100 ms); an even count puts the
# stance / swing switch exactly on a key
MOVE_FRAMES = 10
# The game plays `move` at (unit speed / 2.5) x, i.e. the clip nominally covers 2.5 cells/s; a foot
# is planted for half the cycle, so a slide-free stride is 1.25 x the clip length in seconds.
MOVE_STRIDE = 1.25 * MOVE_FRAMES / salib.FPS
MOVE_LIFT = 0.12
KNEE_FLOOR = LEG_RADIUS * 0.98 + 0.015     # a knee (joint ball) never comes closer to the ground


def shot_frame(cfg):
    """Clip frame at which the game releases the shot: tick ceil(fire_delay * 30) after the start."""
    tick = math.ceil(cfg["fire_delay"] * SIM_HZ - 1e-6)
    return tick / SIM_HZ / cfg["attack_anim_time"] * cfg["attack_frames"]


def leg_specs():
    specs = []
    for name, root, knee, toe, phase in LEGS:
        ankle = tuple(Vector(knee).lerp(Vector(toe), ANKLE_T))
        for side, nm in ((+1, name), (-1, "R" + name[1:])):
            m = lambda p: (side * p[0], p[1], p[2])
            spec = LegSpec(nm, side, m(root), m(knee), m(ankle), phase=phase if side > 0 else (phase + 0.5) % 1.0,
                           radius=LEG_RADIUS)
            spec.toe = m(toe)
            spec.stance_dy = STANCE_DY[name[1]]
            specs.append(spec)
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
    """Coxa (ball + short stub), femur, knee ball, tibia (knee -> ankle); the ankle ball and the
    tarsus tapering to the toe belong to the foot bone (leg.X.ik)."""
    n = f"leg.{spec.name}"
    root, knee, ankle, toe = Vector(spec.root), Vector(spec.knee), Vector(spec.foot), Vector(spec.toe)
    mid = root.lerp(knee, 0.35)
    r = spec.radius
    small_sphere(body, f"{n}.coxa", mat, root, r * 1.35, scale=(1, 1, 0.8))
    body.segment(f"{n}.coxa", mat, tuple(root), tuple(mid), r * 1.2, r * 1.0, verts=10)
    body.segment(f"{n}.femur", mat, tuple(mid), tuple(knee), r * 1.0, r * 0.84, verts=10)
    small_sphere(body, f"{n}.femur", mat, knee, r * 0.98)
    body.segment(f"{n}.tibia", mat, tuple(knee), tuple(ankle), r * 0.86, r * 0.58, verts=10)
    small_sphere(body, f"{n}.ik", mat, ankle, r * 0.62)
    body.segment(f"{n}.ik", tip_mat or mat, tuple(ankle), tuple(toe), r * 0.56, r * 0.16, verts=10)


def seat_feet(mesh, specs, clearance=0.0005):
    """Lift every foot (vertex group leg.X.ik) so its lowest vertex sits just on the ground (the
    tapered toe and the realism displacement put the old soles 0.009 below it)."""
    me = mesh.data
    out = {}
    for spec in specs:
        g = mesh.vertex_groups[f"leg.{spec.name}.ik"].index
        vs = [v for v in me.vertices if any(e.group == g and e.weight > 0.5 for e in v.groups)]
        lo = min(v.co.z for v in vs)
        for v in vs:
            v.co.z += clearance - lo
        out[spec.name] = round(clearance - lo, 4)
    me.update()
    salib.log("feet seated (lift per foot):", out)


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
# rig
# --------------------------------------------------------------------------------------------
def leg_bones(spec, parent="body"):
    """coxa / femur / tibia FK chain (root -> knee -> ankle) and the foot bone (ankle -> toe,
    deforming, child of the root) that is also the IK target.  No pole bones: solve_legs() keeps the
    knee in the leg's own bend plane."""
    n = f"leg.{spec.name}"
    root, knee, ankle, toe = Vector(spec.root), Vector(spec.knee), Vector(spec.foot), Vector(spec.toe)
    mid = root.lerp(knee, 0.35)
    return [
        BoneDef(f"{n}.coxa", tuple(root), tuple(mid), parent=parent),
        BoneDef(f"{n}.femur", tuple(mid), tuple(knee), parent=f"{n}.coxa", connect=True),
        BoneDef(f"{n}.tibia", tuple(knee), tuple(ankle), parent=f"{n}.femur", connect=True),
        BoneDef(f"{n}.ik", tuple(ankle), tuple(toe), parent="root"),
    ]


# --------------------------------------------------------------------------------------------
# animation helpers
#   body bone (points -Y): pose loc +Y = forward, +Z = up; rot +X = front up, rot +Y = roll
#   tail bones / sting (in the YZ plane): rot +X curls the chain forward over the back
#   spear bone (points -Y from the muzzle to the harpoon tip): loc +Y = forward along the barrel
#   star bone (points +Z, the star's normal): rot Y spins the star in its plane
# --------------------------------------------------------------------------------------------
def ik_local(rig, bone_name, offset):
    m = rig.data.bones[bone_name].matrix_local.to_3x3()
    return tuple(m.inverted() @ Vector(offset))


def key_foot(clip, rig, spec, frame, offset):
    """Key a foot (IK target) by an ARMATURE-space offset from its rest position: +X = left,
    +Y = backwards (the scorpion faces -Y), +Z = up."""
    clip.key(f"leg.{spec.name}.ik", frame, loc=ik_local(rig, f"leg.{spec.name}.ik", offset))


def key_rest_all(clip, frame):
    """Key every bone's location / rotation / scale at rest: no channel of this clip is left to
    whatever pose the previously evaluated (baked) clip left behind."""
    for pb in clip.arm.pose.bones:
        pb.rotation_mode = "XYZ"
        pb.location = (0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
        pb.scale = (1, 1, 1)
        pb.keyframe_insert("location", frame=frame)
        pb.keyframe_insert("rotation_euler", frame=frame)
        pb.keyframe_insert("scale", frame=frame)


def loop_from_zero(act, frames):
    """Clip.finish() assumes frames 1..N; every clip here is keyed on 0..N."""
    act.frame_range = (0, frames)
    act.use_frame_range = True
    return act


def key_walk(clip, rig, specs, frames, stride, lift, body_bob=0.012):
    """Alternating-tetrapod walk keyed on every frame 0..frames (frame `frames` = frame 0): a
    planted foot slides straight back (+Y) at a constant rate for half the cycle - no sliding when
    the game plays the cycle at its nominal 2.5 cells/s - then swings forward in an arc of height
    `lift`."""
    for spec in specs:
        dy = getattr(spec, "stance_dy", 0.0)
        for i in range(frames + 1):
            ph = (i / frames + spec.phase) % 1.0
            if ph < 0.5:
                s = ph / 0.5
                y, z = -stride / 2 + stride * s, 0.0
            else:
                s = (ph - 0.5) / 0.5
                y, z = stride / 2 - stride * s, lift * math.sin(math.pi * s)
            key_foot(clip, rig, spec, i, (0.0, y + dy, z))
    for i in range(frames + 1):
        ph = (i / frames) * 2.0 * math.pi * 2.0      # two bobs per cycle (one per tetrapod step)
        clip.key("body", i, loc=(0, 0, body_bob * (0.5 - 0.5 * math.cos(ph))))


def key_tail(c, f, bends, sway_deg=0.0, weapon=None):
    """bends: one angle for every tail joint, or five (tail.1 -> tail.5); `weapon` = the sting /
    launcher bone's own bend (defaults to the last tail bend)."""
    b = list(bends) if isinstance(bends, (list, tuple)) else [bends] * 5
    for i in range(1, 6):
        c.key(f"tail.{i}", f, rot=(b[i - 1], 0, sway_deg))
    c.key("sting", f, rot=(b[4] if weapon is None else weapon, 0, 0))


def key_claws(c, f, open_deg):
    c.key("claw.L.finger", f, rot=(0, 0, open_deg))
    c.key("claw.R.finger", f, rot=(0, 0, -open_deg))


def key_arms(c, f, out_deg, lift_deg=0.0):
    c.key("claw.L.arm", f, rot=(lift_deg, 0, out_deg))
    c.key("claw.R.arm", f, rot=(lift_deg, 0, -out_deg))


def _align_y(carried, direction, head):
    """Armature-space bone matrix: the `carried` frame turned by the smallest rotation that points its
    Y axis (the bone axis) along `direction`, placed at `head` (no twist is introduced)."""
    r0 = carried.to_3x3()
    q = r0.col[1].normalized().rotation_difference(direction.normalized())
    m = (q.to_matrix() @ r0).to_4x4()
    m.translation = head
    return m


def solve_legs(rig, specs, first, last):
    """Analytic two-bone leg IK (after build_spider.py), keyed as plain FK femur / tibia rotations on
    every frame first..last of the action on the rig.  The foot bones (leg.X.ik, keyed by key_foot /
    key_walk) give the ankle targets; the coxa rides on the body.  The knee is placed in the leg's
    own modelled bend plane - the rest-pose knee offset from the hip-ankle line, carried along by
    the body's rotation - so at rest the knees are exactly where they were modelled and they never
    flip down or across the body; a knee that would come closer to the ground than KNEE_FLOOR is
    lifted by turning the bend plane about the hip-ankle line."""
    sc = bpy.context.scene
    vl = bpy.context.view_layer
    pbs, bones = rig.pose.bones, rig.data.bones
    body_rest_inv = bones["body"].matrix_local.inverted()
    legs = []
    for spec in specs:
        n = f"leg.{spec.name}"
        cox, fem, tib = bones[f"{n}.coxa"], bones[f"{n}.femur"], bones[f"{n}.tibia"]
        hip, knee, ankle = fem.head_local.copy(), fem.tail_local.copy(), tib.tail_local.copy()
        a, b = (knee - hip).length, (ankle - knee).length
        u = (ankle - hip).normalized()
        bend = (knee - hip) - u * (knee - hip).dot(u)
        legs.append(dict(n=n, a=a, b=b, bend=bend.normalized(),
                         fem_in_cox=cox.matrix_local.inverted() @ fem.matrix_local,
                         tib_in_fem=fem.matrix_local.inverted() @ tib.matrix_local, prev={}))
    report = {"unreachable": 0.0, "lifted": 0}
    for f in range(first, last + 1):
        sc.frame_set(f)
        vl.update()
        body_rot = (pbs["body"].matrix @ body_rest_inv).to_3x3()
        sol = []
        for L in legs:
            n = L["n"]
            hip = pbs[f"{n}.coxa"].tail.copy()
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

            k = knee_at(0.0)
            if k.z < KNEE_FLOOR:
                best = None
                for step in range(1, 181):
                    for sgn in (1, -1):
                        kk = knee_at(sgn * math.radians(step))
                        if kk.z >= KNEE_FLOOR:
                            best = kk
                            break
                    if best is not None:
                        break
                if best is None:
                    best = max((knee_at(math.radians(s)) for s in range(0, 360, 2)), key=lambda v: v.z)
                k = best
                report["lifted"] += 1
            sol.append((L, hip, k, hip + u * dc))
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
    sc.frame_set(first)
    vl.update()
    return report


def leg_report(variant, name, report):
    salib.log(f"legs {variant} {name}: knee lifted off the ground on {report['lifted']} leg-frames, "
              f"worst foot-target overshoot {report['unreachable']:.4f}")


def key_bone_matrix(rig, bone, frame, m, prev=None):
    """Pose `bone` to the armature-space matrix `m` on `frame` (the rig must already be evaluated at
    that frame) and key its location / rotation / scale; returns the Euler for continuity."""
    pb = rig.pose.bones[bone]
    pb.matrix = m
    bpy.context.view_layer.update()
    if prev is not None:
        e = pb.rotation_euler.copy()
        e.make_compatible(prev)
        pb.rotation_euler = e
    for path in ("location", "rotation_euler", "scale"):
        pb.keyframe_insert(path, frame=frame)
    return pb.rotation_euler.copy()


def weapon_point(rig, kind):
    """Armature-space point where the shot leaves: the savage's barb tip, the harpoon tip, the star."""
    pbs = rig.pose.bones
    if kind == "savage":
        return pbs["sting"].tail.copy()
    if kind == "spear":
        return pbs["spear"].tail.copy()
    return pbs["star"].head.copy()


def report_muzzle(variant, rig, kind, frame):
    sc = bpy.context.scene
    sc.frame_set(int(math.floor(frame)), subframe=frame - math.floor(frame))
    bpy.context.view_layer.update()
    p = weapon_point(rig, kind)
    # game convention: x to the unit's right (= -X here), y up, z ahead (= -Y here)
    salib.log(f"MUZZLE {variant}: shot at clip frame {frame:.2f}: point (blender) ({p.x:+.3f}, {p.y:+.3f}, {p.z:+.3f}) "
              f"-> muzzle (x right {-p.x:+.3f}, y up {p.z:+.3f}, z ahead {-p.y:+.3f}) cells")
    sc.frame_set(0)
    return (-p.x, p.z, -p.y)


# --------------------------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------------------------
def build(variant: str):
    cfg = VARIANTS[variant]
    kind = cfg["kind"]
    salib.reset_scene(variant)
    mats = salib.standard_materials("Y")
    mats["M_Sting"] = salib.material("M_Sting", (0.96, 0.50, 0.12), roughness=0.35, emission=(0.9, 0.4, 0.1),
                                     emission_strength=0.15, kind="glossy")
    mats["M_Brown"] = salib.material("M_Brown", (0.40, 0.22, 0.11), roughness=0.75, kind="wood")
    # pale blue-white star (sprites): mostly dielectric - the game has no environment map, so a metallic
    # star renders dark grey in game
    mats["M_Star"] = salib.material("M_Star", (0.86, 0.90, 0.98), roughness=0.3, metallic=0.15, kind="glossy")
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
    extra_bones = []
    if kind == "savage":
        ellipsoid(body, "sting", "M_Sting", tip + Vector((0, 0, 0.03)), 0.13, 0.15, (0, -0.2, 1.0))
        body.segment("sting", "M_Sting", (0, 0.975, 1.15), (0, 0.90, 1.27), 0.055, 0.022, verts=10)
        body.segment("sting", "M_Sting", (0, 0.905, 1.262), (0, 0.835, 1.335), 0.022, 0.003, verts=8)
        sting_tail = (0, 0.835, 1.335)                 # the barb tip
    elif kind == "spear":
        gz = 0.90
        body.cube("sting", "M_Brown", (0, 0.74, gz), size=(0.15, 0.56, 0.13))
        body.cube("sting", "M_Steel", (0, 0.58, gz), size=(0.165, 0.045, 0.145))
        body.cube("sting", "M_Steel", (0, 0.88, gz), size=(0.165, 0.045, 0.145))
        body.cube("sting", "M_Steel", (0, 0.49, gz + 0.02), size=(0.11, 0.07, 0.11))      # muzzle block
        # the harpoon: shaft + head on its own bone so it can slide out, leave and be reloaded
        body.cylinder("spear", "M_Accent", (0, 0.32, gz + 0.025), 0.018, 0.30, rot=(math.radians(90), 0, 0), verts=8)
        body.cone("spear", "M_Steel", (0, 0.12, gz + 0.025), 0.035, 0.0, 0.11, rot=(math.radians(90), 0, 0), verts=8)
        sting_tail = (0, 0.40, gz)
        # bone from the muzzle face to the harpoon tip: scaling it shrinks the harpoon into the muzzle
        extra_bones.append(BoneDef("spear", (0, 0.455, gz + 0.025), (0, 0.065, gz + 0.025), parent="sting"))
    else:
        nozzle_c = tip + tip_dir * 0.07
        body.cylinder("sting", "M_Accent", tuple(nozzle_c), 0.05, 0.16,
                      rot=tip_dir.to_track_quat("Z", "Y").to_euler(), verts=10)
        star_c = tip + tip_dir * 0.17
        # the sprites' star is 9-10 px (~0.4 cells) across, as wide as the body: r_out 0.20
        star_part(body, "star", "M_Star", tuple(star_c), 0.20, 0.064, 0.018, points=4, rot_deg=0.0)
        small_sphere(body, "star", "M_Accent", star_c, 0.03)
        sting_tail = tuple(tip + tip_dir * 0.22)
        # bone along the star's normal (+Z) through its centre: rot Y spins it in its plane
        extra_bones.append(BoneDef("star", tuple(star_c), tuple(star_c + Vector((0, 0, 0.12))), parent="sting"))

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
    seat_feet(mesh, specs)
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
    # weapon bone (sting / launcher): not connected, so the spear gun can kick back along its barrel
    bones.append(BoneDef("sting", TAIL[5], sting_tail, parent="tail.5"))
    bones += extra_bones
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
        bones += leg_bones(spec, parent="body")
    rig = salib.build_armature("Rig", bones)
    salib.skin(mesh, rig)
    # no IK constraints: every clip keys the foot bones and solve_legs() keys the femurs / tibias

    clips = []
    # ---- idle (1.6 s loop, frames 0..48): breathing bob, the tail sways, the claws open and close
    c = Clip(rig, "idle", 48)
    key_rest_all(c, 0)
    c.key("body", 0, loc=(0, 0, 0)); c.key("body", 24, loc=(0, 0, 0.01)); c.key("body", 48, loc=(0, 0, 0))
    for f, sw, bd in ((0, 0, 0), (12, 3, 1.5), (24, 0, 0), (36, -3, -1.5), (48, 0, 0)):
        key_tail(c, f, bd, sw)
    for f, o in ((0, 0), (16, 12), (32, 0), (48, 0)):
        key_claws(c, f, o)
    key_arms(c, 0, 0); key_arms(c, 24, 2); key_arms(c, 48, 0)
    act = loop_from_zero(c.finish(), 48)
    leg_report(variant, "idle", solve_legs(rig, specs, 0, 48))
    clips.append(act)

    # ---- move (0.33 s loop, frames 0..10): alternating-tetrapod walk, the tail bobs with each step
    c = Clip(rig, "move", MOVE_FRAMES)
    key_rest_all(c, 0)
    key_walk(c, rig, specs, MOVE_FRAMES, stride=MOVE_STRIDE, lift=MOVE_LIFT, body_bob=0.012)
    q = MOVE_FRAMES / 4.0
    for f, b in ((0, 0), (round(q), 3), (round(2 * q), 0), (round(3 * q), 3), (MOVE_FRAMES, 0)):
        key_tail(c, f, b)
    key_claws(c, 0, 8); key_claws(c, MOVE_FRAMES, 8)
    act = loop_from_zero(c.finish(), MOVE_FRAMES)
    leg_report(variant, "move", solve_legs(rig, specs, 0, MOVE_FRAMES))
    clips.append(act)

    # ---- attack (frames 0..N, the game scales it to attack_anim_time) ---------------------------
    n = cfg["attack_frames"]
    fs = shot_frame(cfg)
    salib.log(f"{variant}: attack clip {n} frames, played over {cfg['attack_anim_time']} s; the shot leaves at "
              f"clip frame {fs:.2f}")
    c = Clip(rig, "attack", n, loop=False)
    key_rest_all(c, 0)
    if kind == "savage":
        # COCKED (sprite attack frame 1) at both ends, so the restart at every sting is seamless:
        # tail almost vertical, sting hooked forward above the rear of the body, claws half open.
        # Bends solved for the sprite's sting positions (qa/agents/scorpion_attacks/tools/tail_solve.py):
        #   cocked: tail tip (y +0.44, z 1.14), barb (y +0.13, z 1.11)
        #   strike: tail tip (y -0.24, z 0.64), barb (y -0.45, z 0.41) + the body's lunge
        cocked = (11.4, 11.8, 12.3, 12.4, 12.3)
        windup = (5.0, 8.0, 12.0, 15.0, 17.0)
        strike = (44.5, 36.1, 25.0, 15.7, 10.9)
        stab = (47.0, 37.0, 25.0, 15.0, 10.0)
        for f, bends, w in ((0, cocked, 7.0), (3, windup, 14.0), (5, strike, -22.8), (6, stab, -26.0),
                            (8, strike, -22.0), (11, (24, 22, 18, 14, 12), -2.0), (n, cocked, 7.0)):
            key_tail(c, f, bends, weapon=w)
        # body: rears a little on the wind-up, lunges forward and dips its front on the strike
        for f, loc, rot in ((0, (0, 0, 0), (0, 0, 0)), (3, (0, -0.02, 0.012), (3, 0, 0)),
                            (5, (0, 0.06, -0.006), (-4, 0, 0)), (7, (0, 0.05, -0.004), (-3, 0, 0)),
                            (11, (0, 0.01, 0), (-0.5, 0, 0)), (n, (0, 0, 0), (0, 0, 0))):
            c.key("body", f, loc=loc, rot=rot)
        # claws: half open in the stance, wide open on the wind-up, snapped shut on the strike
        for f, o in ((0, 10), (3, 32), (5, -4), (8, -2), (11, 6), (n, 10)):
            key_claws(c, f, o)
        for f, out, lift in ((0, 4, 0), (3, 14, -4), (5, -6, 3), (9, 0, 1), (n, 4, 0)):
            key_arms(c, f, out, lift)
    elif kind == "spear":
        # aim: the tail lifts the launcher a little; the harpoon slides out of the muzzle (sprite
        # attack frame 1) and leaves at the shot (frame 2: gone) - it streaks forward and vanishes
        # between frames 4 and 5 - while the launcher kicks back along its barrel and the tail gives;
        # a new harpoon grows out of the muzzle during the recovery.
        for f, bends, w in ((0, 0, 0), (3, (2, 2, 1, 1, 0), -2), (5, (2, 2, 1, 1, 0), -2),
                            (7, (-4, -4, -3, -2, -2), 4), (11, (1, 1, 0, 0, 0), -1), (n, 0, 0)):
            key_tail(c, f, bends, weapon=w)
        c.key("sting", 0, loc=(0, 0, 0)); c.key("sting", 5, loc=(0, 0, 0))
        c.key("sting", 6, loc=(0, -0.07, 0)); c.key("sting", 10, loc=(0, -0.01, 0)); c.key("sting", n, loc=(0, 0, 0))
        c.key("spear", 0, loc=(0, 0, 0), scale=(1, 1, 1))
        c.key("spear", 2, loc=(0, 0.03, 0), scale=(1, 1, 1))
        c.key("spear", 4, loc=(0, 0.15, 0), scale=(1, 1, 1))
        c.key("spear", 5, loc=(0, 0.70, 0), scale=(0.02, 0.02, 0.02))       # fired: streaks off and vanishes
        c.key("spear", 6, loc=(0, -0.05, 0), scale=(0.02, 0.02, 0.02))      # hidden in the barrel
        c.key("spear", 9, loc=(0, -0.05, 0), scale=(0.02, 0.02, 0.02))
        c.key("spear", 13, loc=(0, 0, 0), scale=(1, 1, 1))                  # reloaded
        c.key("spear", n, loc=(0, 0, 0), scale=(1, 1, 1))
        for f, loc, rot in ((0, (0, 0, 0), (0, 0, 0)), (3, (0, 0.01, -0.01), (-1, 0, 0)), (5, (0, 0.01, -0.01), (-1, 0, 0)),
                            (7, (0, -0.03, 0.004), (2, 0, 0)), (11, (0, -0.005, 0), (0.3, 0, 0)), (n, (0, 0, 0), (0, 0, 0))):
            c.key("body", f, loc=loc, rot=rot)
        for f, o in ((0, 0), (3, 12), (6, -3), (9, 6), (n, 0)):
            key_claws(c, f, o)
    else:
        # ninja: the tail winds back, then flicks up and forward; the star leaves the launcher and
        # flies forward over the body (sprite attack frame 1), it is released above the body centre
        # at the shot (frame 2: gone, the tail flicked up), follow-through, a new star appears.
        for f, bends, w in ((0, 0, 0), (2, (-7, -6, -4, -3, -3), -4), (4, (6, 8, 10, 10, 10), 6),
                            (5, (10, 12, 14, 14, 12), 10), (7, (12, 15, 17, 17, 15), 14), (10, (5, 6, 6, 6, 5), 4),
                            (n, 0, 0)):
            key_tail(c, f, bends, weapon=w)
        for f, loc, rot in ((0, (0, 0, 0), (0, 0, 0)), (2, (0, -0.02, -0.005), (2, 0, 0)), (5, (0, 0.03, 0), (-2.5, 0, 0)),
                            (8, (0, 0.01, 0), (-1, 0, 0)), (n, (0, 0, 0), (0, 0, 0))):
            c.key("body", f, loc=loc, rot=rot)
        for f, o in ((0, 0), (2, 14), (5, -4), (10, 4), (n, 0)):
            key_claws(c, f, o)
    act = loop_from_zero(c.finish(), n)
    if kind == "ninja":
        # the star's flight: rides on the launcher to frame 3, then flies (spinning) forward to the
        # release point above the body centre (frame 5 = the shot), streaks on and vanishes; hidden on
        # the launcher until frame 9, regrown by frame 13
        sc = bpy.context.scene
        pbs = rig.pose.bones
        rest = rig.data.bones["star"].matrix_local.to_3x3()
        sc.frame_set(3)
        bpy.context.view_layer.update()
        p3 = pbs["star"].head.copy()
        release = Vector((0.0, -0.02, 0.95))
        ahead = release + Vector((0.0, -0.33, -0.02))         # one frame of flight at the projectile's speed
        path = {4: (p3.lerp(release, 0.5) + Vector((0, 0, 0.06)), 90.0, 1.0), 5: (release, 180.0, 1.0), 6: (ahead, 270.0, 0.02)}
        c.key("star", 3, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1))
        prev = None
        for f in (4, 5, 6):
            sc.frame_set(f)
            bpy.context.view_layer.update()
            pos, spin, s = path[f]
            m = (Matrix.Rotation(math.radians(spin), 3, "Z") @ rest).to_4x4() @ Matrix.Diagonal((s, s, s, 1.0))
            m.translation = pos
            prev = key_bone_matrix(rig, "star", f, m, prev)
        c.key("star", 7, loc=(0, 0, 0), rot=(0, 0, 0), scale=(0.02, 0.02, 0.02))
        c.key("star", 9, loc=(0, 0, 0), rot=(0, 0, 0), scale=(0.02, 0.02, 0.02))
        c.key("star", 13, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1))
        c.key("star", n, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1))
        sc.frame_set(0)
    leg_report(variant, "attack", solve_legs(rig, specs, 0, n))
    muzzle = report_muzzle(variant, rig, kind, fs if kind != "spear" else min(fs, 4.0))
    clips.append(act)

    # ---- death (1.2 s, frames 0..36): the body drops onto the ground, the legs splay out flat,
    # the tail falls back, the claws open (the dead sprite's first frame)
    c = Clip(rig, "death", 36, loop=False)
    key_rest_all(c, 0)
    sink = 0.10
    c.key("body", 0, loc=(0, 0, 0), rot=(0, 0, 0))
    c.key("body", 22, loc=(0, 0, -sink * 0.8), rot=(1.5, 2.0, 0))
    c.key("body", 36, loc=(0, -0.02, -sink), rot=(2, 3.0, 0))
    for spec in specs:
        key_foot(c, rig, spec, 0, (0, 0, 0))
        key_foot(c, rig, spec, 14, (0.07 * spec.side, 0.03, 0.025))
        key_foot(c, rig, spec, 36, (0.12 * spec.side, 0.07, 0.0))
    death_tail = {"savage": ((-24, -10, -8, -6, -4), -6), "spear": ((-14, -4, -2, -2, 0), 4),
                  "ninja": ((-22, -10, -8, -6, -4), -10)}[kind]
    key_tail(c, 0, 0, weapon=0)
    key_tail(c, 20, [b * 0.6 for b in death_tail[0]], 2, weapon=death_tail[1] * 0.6)
    key_tail(c, 36, death_tail[0], 4, weapon=death_tail[1])
    key_claws(c, 0, 0); key_claws(c, 36, 28)
    key_arms(c, 0, 0); key_arms(c, 36, 24, 4)
    act = loop_from_zero(c.finish(), 36)
    leg_report(variant, "death", solve_legs(rig, specs, 0, 36))
    clips.append(act)
    salib.bake_actions(rig, clips)

    path, s = salib.finalize_asset(variant, [rig, mesh], preview_radius=3.4, preview_center=(0, 0, 0.45))
    assert sorted(a["name"] for a in s["animations"]) == ["attack", "death", "idle", "move"]
    assert "M_Team" in s["materials"], s["materials"]
    salib.log(f"{variant}: muzzle (x right, y up, z ahead) = ({muzzle[0]:.2f}, {muzzle[1]:.2f}, {muzzle[2]:.2f})")

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
