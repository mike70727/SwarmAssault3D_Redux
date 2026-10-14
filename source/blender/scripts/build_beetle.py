"""Builds the beetle family: Lady Bug, Shrapnel, Cannon.

Rebuilt against the original art (reference/models/beetle_*: the developers' 3-D portraits, the
48-px top-down sprite sheets - 1 cell = 24 px - and the 1999 loading screens, which show the lady
bug and the shrapnel beetle rendered large).

* Lady Bug (UNBETLB): a classic ladybird.  One tall smooth oval dome, 27 x 31 px (1.12 x 1.29 cells)
  from above, with a thin dark centre seam and eight round black spots on top (two rows of four) plus
  one on each flank; a small, tall dark slate head block with a pale cream mouth band (portrait, loading
  screen) at the front of which the thin minigun barrel sticks out (the sprite's single front "line",
  with the muzzle flash on it in the attack frames); six short black legs under the dome's rim.
* Shrapnel (UNBETSH): a tick-like bug.  A flat, broad team-coloured shield (19 x 24 px -> 0.79 x
  1.0 cells, broadest at the front) carrying a black "skull" marking - a thick black brow band right
  behind the launcher with its ends drooping back, two thin dark lines converging from them to the
  middle, two small black eyes in the rear third and a black stroke from them to the rear tip; the
  pale grey shrapnel launcher is a short open cylinder standing on the front-centre of the shield; a
  glossy black head capsule in front with two short antennae; six long brown-black legs splayed wide
  (front pair forward, middle pair sideways, rear pair back: footprint 1.25 x 1.42 cells).
* Cannon (UNBETCA): an elongated dark ground beetle.  Dark brown head (antennae straight forward,
  amber mandible tips), dark pronotum, long team-coloured elytra (14 x 18 px -> 0.58 x 0.75 cells,
  centre seam) and a stubby grey cannon lying on the pronotum: wide breech at the elytra, barrel
  forward over the head.  Six long brown legs, body 1.45 cells long.
Team colour: only the dome / shield / elytra use M_Team; the markings are painted into that material
(black stays black when the game tints the base colour).  Everything else keeps its own colour.

Marking positions: the original sprites were rendered by a camera tilted from the south, which
shifts high details (spots on top of a dome) forward in the "faces up" frame and backward in the
"faces down" frame.  The positions here are the averages of the up/down facings (cross-checked with
the tilt-free left/right facings) - i.e. where the marks really are on the 3-D bug.  The game camera
is tilted the same way (45-76 deg pitch), so in game the model shows the same shift as the sprite.

Legs (all three): sturdy jointed legs - coxa ball, thick femur, knee ball, tibia tapering to an ankle
ball and a flat tarsus lying on the ground (the tarsus hangs from its own `leg.X.foot` bone, a child
of the IK target, so the feet stay level).  Rest positions come from the sprites' top-down frames
(how far each pair shows past the shell).
salib bugs worked around locally (salib.py is shared and must not be edited):
  * salib.apply_leg_ik() uses a fixed +-90 deg pole angle with the pole above the knee, which does
    not reproduce the modelled rest pose: the IK spun every leg chain around its hip-foot axis
    (knees of the previous build sat up to 7 cm UNDER the ground).  Here the pole sits in the leg's
    own plane beyond the knee and the pole angle is found numerically until the knee is exactly where
    it was modelled (same approach as build_spider.py).
  * salib.leg_bones() points the IK targets straight up, so salib.key_walk_cycle()/key_death() key
    bone-local offsets as if they were armature space (feet sink).  Here every IK offset goes through
    ik_local() (same as build_scorpion.py).
Walk = alternating tripod gait keyed on every frame (L1+R2+L3 against R1+L2+R3); stride = 1.25 x
clip seconds, so the planted feet do not slide at the game's nominal 2.5 cells/s playback; each leg's
stride window is shifted (when needed) so both ends of the stance stay within the leg's reach.
Death = the corpse of the sprites: the bug tips onto one side, turns and settles with the shell on the
ground, the legs splay and follow the body (feet never below the ground).  Every build appends a
numeric report (feet, knees, ankle gaps, planted-foot travel, shell ground contact) to
qa/agents/beetle_attacks/feet_check_report.txt.

Attack clips (beetle attack crew, 2026-10-13) - each one reproduces the original's two attack frames
(Game.ANI UNBET??Y_AT<facing>: frame 0 for 100 ms, then frame 1 = "Fire Point" for 100 ms, the
cannon's for 300 ms).  The game restarts `attack` at every shot at speed (clip length /
attack_anim_time) and releases the shot `fire_delay` after the start (units.ron: lady bug 0.3 s /
0.05 s, shrapnel and cannon 0.6 s / 0.2 s).  The glTF export puts frame f at f/30 s, so the clips have
9 / 18 frames (0.3 s / 0.6 s: played at speed 1) and the shot is on frame 2 / frame 6 (sim ticks 2 / 6):
* Lady Bug: the sprites show only a muzzle flash - frame 1 a 4 x 3 px orange star on the gun's mouth,
  frame 0 a 2 x 2 px flash 2 px ahead of it (the round leaving).  Here: the clip starts and ends in
  the idle stance (it is restarted every 10 sim ticks, so back-to-back shots read as continuous fire);
  on the shot frame an orange star flash opens on the gun's mouth, the barrel kicks back, the head
  jerks up, then the flash shrinks and flies ahead (the small detached flash) and goes out.
* Shrapnel: on the shield's front the pale launcher (stand: a pale knob) first rises (frame 0) and
  then shows an eight-armed pale star ~10 px across (frame 1).  Here the launcher is a dark core tube
  inside eight pale staves hinged at its top rim (from outside the portrait's short pale cylinder with
  the dark opening): the bug squats and the launcher rises, then the staves fling open into the
  eight-armed star around a pale burst flash as the volley leaves, the bug jolts up, and the staves
  fold shut again.
* Cannon: the pale barrel line on the pronotum shortens by ~3 px (frame 0 partly, frame 1 fully: the
  barrel recoils into the breech; no flash).  Here the beetle braces (body lowered, nose down), on the
  shot the barrel slams back 0.13 cells into the breech, the body rocks back and up on its planted
  legs, the antennae whip, and the barrel runs out again.  The barrel is medium-grey metal (the
  portrait's barrel; from above it reads as the sprites' grey line).
The muzzle flashes are modelled full size, the mesh is UV-unwrapped, and then the flash parts are
shrunk to 1/FLASH_SHRINK around their bone's head: invisible at rest and in the bind pose; the attack
clip scales the flash bone up by FLASH_SHRINK while it shows (finalize_unwrapped() = salib's
finalize_asset without the re-unwrap).  Each build appends the muzzle points measured on the posed
model (gun mouth / launcher top / cannon mouth, game axes: x right, y up, z ahead) to
qa/agents/beetle_attacks/muzzle_report.txt.

Usage:  blender -b --factory-startup --python build_beetle.py -- [beetle_ladybug beetle_shrapnel
beetle_cannon] [--quick]      (--quick: no bake/export; saves qa/agents/beetle_attacks/quick/
<asset>_quick.blend for the crew's render scripts)
"""
import math
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Euler, Matrix, Vector  # noqa: E402

import salib  # noqa: E402
from salib import BoneDef, Body, Clip, LegSpec  # noqa: E402

VARIANTS = {
    "beetle_ladybug": dict(kind="ladybug"),
    "beetle_shrapnel": dict(kind="shrapnel"),
    "beetle_cannon": dict(kind="cannon"),
}

CREW_DIR = r"D:\SwarmAssault3D-complete\qa\agents\beetle_attacks"
QUICK_DIR = os.path.join(CREW_DIR, "quick")
REPORT = os.path.join(CREW_DIR, "feet_check_report.txt")
MUZZLE_REPORT = os.path.join(CREW_DIR, "muzzle_report.txt")
FLASH_SHRINK = 40.0   # muzzle flashes: modelled full size, shrunk to 1/40 after the UV unwrap (see build())


# --------------------------------------------------------------------------------------------
# local helpers (salib.py is shared and must not be edited; these extend it for the beetles)
# --------------------------------------------------------------------------------------------
def shaped_sphere(body, bone, mat, center, half_axes, segments=24, rings=12, squash=1.0, taper=None,
                  subdiv=True, material_smooth=True, shape=None):
    """UV sphere remapped vertex by vertex: `half_axes` = (x, y, z) semi-axes, `squash` scales the
    lower half's z (0 = flat underside), `taper` = (width factor at the front, at the rear), `shape` =
    optional f(nx, ny, nz) -> (nx, ny, nz) applied last on the unit sphere.
    Vertices are written in world space (object at the origin)."""
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, segments=segments, ring_count=rings, location=(0, 0, 0))
    o = bpy.context.object
    cx, cy, cz = center
    ax, ay, az = half_axes
    for v in o.data.vertices:
        nx, ny, nz = v.co
        if nz < 0:
            nz *= squash
        if taper:
            w = taper[0] + (taper[1] - taper[0]) * (ny + 1.0) * 0.5
            nx *= w
        if shape:
            nx, ny, nz = shape(nx, ny, nz)
        v.co = (cx + ax * nx, cy + ay * ny, cz + az * nz)
    o.data.update()
    if not subdiv:
        o["sa_no_subdiv"] = True
    return body._finish(o, bone, mat, smooth=material_smooth)


def capsule(front=0.35, rear=0.6):
    """Shape function: blunt front cap (`front` of the semi-axis), straight middle, rounded rear."""
    def f(nx, ny, nz):
        ny = -1.0 + (1.0 + ny) * front if ny <= 0 else 1.0 - (1.0 - ny) * rear
        return nx, ny, nz
    return f


def dome_z(center, half_axes, x, y):
    """Height of the top of an ellipsoid shell at (x, y)."""
    cx, cy, cz = center
    ax, ay, az = half_axes
    q = 1.0 - ((x - cx) / ax) ** 2 - ((y - cy) / ay) ** 2
    return cz + az * math.sqrt(max(0.0, q))


FOOT_LEN = 0.08     # tarsus length (lies flat on the ground, pointing away from the body)
ANKLE_Z = 0.014     # tibia/tarsus joint height: the foot pad rests on the ground
FEMUR_SPLIT = 0.35  # salib.leg_bones(): the coxa bone ends (and the femur bone starts) 35 % along root->knee


def leg_mesh_beetle(body, spec, mat, joint_mat=None):
    """Sturdy jointed beetle leg (low poly, no subdivision): coxa ball + coxa stub, thick femur, knee
    ball, tibia tapering to the ankle, and a flat tarsus (foot) on the ground.  The tarsus belongs to
    the `leg.X.foot` bone (child of the IK target) so it stays level whatever the tibia does.
    Returns the toe point (tail of the foot bone)."""
    n = f"leg.{spec.name}"
    root, knee, foot = Vector(spec.root), Vector(spec.knee), Vector(spec.foot)
    mid = root.lerp(knee, FEMUR_SPLIT)          # where the coxa bone ends and the femur bone starts
    r = spec.radius
    ankle = Vector((foot.x, foot.y, ANKLE_Z))
    out = Vector((foot.x - knee.x, foot.y - knee.y, 0.0))
    out.normalize()
    toe = ankle + out * FOOT_LEN
    parts = [
        shaped_sphere(body, f"{n}.coxa", mat, tuple(root), (r * 1.6, r * 1.6, r * 1.6), segments=8, rings=5, subdiv=False),
        body.segment(f"{n}.coxa", mat, tuple(root), tuple(mid), r * 1.3, r * 1.15, verts=8),
        body.segment(f"{n}.femur", mat, tuple(mid), tuple(knee), r * 1.15, r * 0.9, verts=8),
        shaped_sphere(body, f"{n}.femur", joint_mat or mat, tuple(knee), (r * 1.2, r * 1.2, r * 1.2), segments=8, rings=5, subdiv=False),
        body.segment(f"{n}.tibia", mat, tuple(knee), tuple(ankle), r * 0.9, r * 0.42, verts=8),
        shaped_sphere(body, f"{n}.foot", mat, tuple(ankle), (r * 0.5, r * 0.5, r * 0.5), segments=6, rings=4, subdiv=False),
        body.segment(f"{n}.foot", mat, tuple(ankle), tuple(toe), r * 0.45, r * 0.2, verts=6),
    ]
    for p in parts:
        p["sa_no_subdiv"] = True
    return toe


def leg_bones_beetle(spec, parent="body"):
    """salib.leg_bones() with the knee pole moved into the leg's own plane, 0.4 beyond the knee (seen
    from the hip-foot line), so the IK keeps the knee bending the way it was modelled."""
    bones = salib.leg_bones(spec, parent=parent)
    root, knee, foot = Vector(spec.root), Vector(spec.knee), Vector(spec.foot)
    head = root.lerp(knee, FEMUR_SPLIT)
    axis = (foot - head).normalized()
    off = (knee - head) - axis * (knee - head).dot(axis)
    off = off.normalized() if off.length > 1e-6 else Vector((0.0, 0.0, 1.0))
    pole = knee + off * 0.4
    for b in bones:
        if b.name == f"leg.{spec.name}.pole":
            b.head = tuple(pole)
            b.tail = tuple(pole + Vector((0.0, 0.0, 0.1)))
    return bones


def foot_bones(specs, toes):
    return [BoneDef(f"leg.{s.name}.foot", (s.foot[0], s.foot[1], ANKLE_Z), tuple(t), parent=f"leg.{s.name}.ik")
            for s, t in zip(specs, toes)]


def _signed_angle(u, v, normal):
    a = u.angle(v)
    if u.cross(v).angle(normal) < 1.0:
        a = -a
    return a


def pole_angle_guess(rig, base_name, tip_name, pole_name):
    """Analytic first guess of the IK pole angle (signed angle between the chain base bone's X axis
    and the pole direction projected onto the plane perpendicular to the base bone)."""
    bb = rig.data.bones[base_name]
    tb = rig.data.bones[tip_name]
    pole = rig.data.bones[pole_name].head_local
    base_head, base_tail = bb.head_local, bb.tail_local
    x_axis = bb.matrix_local.to_3x3().col[0]
    pole_normal = (tb.tail_local - base_head).cross(pole - base_head)
    projected = pole_normal.cross(base_tail - base_head)
    return _signed_angle(x_axis, projected, base_tail - base_head)


def apply_leg_ik(rig, specs):
    """Replacement for salib.apply_leg_ik (fixed +-90 deg pole angle, which spun the beetle legs
    around their hip-foot axis and pushed knees through the ground): for each leg the pole angle is
    searched numerically (the depsgraph evaluates the IK) until the knee sits exactly where it was
    modelled (copied from build_spider.py)."""
    errors = {}
    for spec in specs:
        n = f"leg.{spec.name}"
        femur, tibia, ik, pole = f"{n}.femur", f"{n}.tibia", f"{n}.ik", f"{n}.pole"
        guess = pole_angle_guess(rig, femur, tibia, pole)
        con = salib.add_ik(rig, tibia, ik, chain=2, pole_bone=pole, pole_angle=guess)
        rest_knee = rig.data.bones[femur].tail_local.copy()

        def knee_error(angle):
            con.pole_angle = angle
            bpy.context.view_layer.update()
            return (rig.pose.bones[femur].tail - rest_knee).length

        best = (knee_error(guess), guess)
        for step, span in ((math.radians(10), math.pi), (math.radians(1), math.radians(12)),
                           (math.radians(0.1), math.radians(1.5))):
            centre = best[1]
            k = -span
            while k <= span + 1e-9:
                e = knee_error(centre + k)
                if e < best[0]:
                    best = (e, centre + k)
                k += step
        con.pole_angle = best[1]
        bpy.context.view_layer.update()
        errors[spec.name] = best[0]
        salib.log(f"{n}: pole angle {math.degrees(best[1]):.1f} deg (guess {math.degrees(guess):.1f}), knee error {best[0]:.4f}")
        assert best[0] < 0.005, f"{n}: IK cannot reproduce the rest pose (knee error {best[0]:.3f})"
    return errors


# salib.leg_bones() makes every IK target bone point straight up (+Z), so a pose-bone `location`
# keyed as (0, stride, lift) - what salib.key_walk_cycle() / key_death() do - moves the foot UP by
# `stride` and FORWARD by `lift`: feet sink through the ground and the stride is tiny (found by the
# scorpion crew).  These helpers convert armature-space offsets through the bone's rest matrix.
def ik_local(rig, bone_name, offset):
    m = rig.data.bones[bone_name].matrix_local.to_3x3()
    return tuple(m.inverted() @ Vector(offset))


def key_foot(clip, rig, spec, frame, offset):
    clip.key(f"leg.{spec.name}.ik", frame, loc=ik_local(rig, f"leg.{spec.name}.ik", offset))


def new_clip(rig, name, frames, loop=True):
    """salib.Clip with every channel of every bone keyed at rest on frame 1.  salib.bake_actions()
    bakes each action with visual keying, and a channel the action does not key keeps whatever value
    the previous clip left on the pose bone - so without this the corpse's tilted body and the moved
    knee poles of the death clip leaked into the idle/move/attack bakes."""
    c = Clip(rig, name, frames, loop=loop)
    for pb in rig.pose.bones:
        c.key(pb.name, 1, rot=(0, 0, 0), loc=(0, 0, 0), scale=(1, 1, 1))
    return c


def leg_reach(rig, spec):
    n = f"leg.{spec.name}"
    fb, tb = rig.data.bones[f"{n}.femur"], rig.data.bones[f"{n}.tibia"]
    return fb.head_local.copy(), fb.length + tb.length


def stride_offsets(rig, specs, stride, slack=0.97):
    """Per-leg shift of the stride window along Y so that both ends of the stance stay within the
    leg's reach (femur + tibia): otherwise the IK cannot reach the target there and the foot hovers
    and slides for a frame (the previous cannon rear legs did).  The smallest shift that keeps both
    ends within `slack` x reach; if none does, the shift that balances the two ends."""
    offs = {}
    for spec in specs:
        head, reach = leg_reach(rig, spec)
        foot = Vector(spec.foot)

        def need(o):
            return max((foot + Vector((0.0, y + o, 0.0)) - head).length for y in (-stride / 2.0, stride / 2.0)) / reach

        grid = sorted((k * 0.0025 for k in range(-48, 49)), key=abs)
        best = next((o for o in grid if need(o) <= slack), None)
        if best is None:
            best = min(grid, key=need)
        offs[spec.name] = best
        salib.log(f"leg.{spec.name}: stride window shift {best:+.4f}, stance ends at {need(best) * 100:.1f} % of reach")
    return offs


def key_walk(clip, rig, specs, frames, stride, lift, body_bob=0.01, offsets=None):
    """Alternating-tripod walk keyed on every frame (phases 0 / 0.5 from the LegSpecs): a planted
    foot slides straight back (+Y; the bug faces -Y) at a constant rate for half the cycle, then
    swings forward in an arc of height `lift`.  The game plays `move` at speed / 2.5, so with
    stride = 1.25 x (clip seconds) the planted feet do not slide over the ground."""
    offsets = offsets or {}
    for spec in specs:
        o = offsets.get(spec.name, 0.0)
        for i in range(frames):
            ph = (i / frames + spec.phase) % 1.0
            if ph < 0.5:
                s = ph / 0.5
                y, z = -stride / 2 + stride * s, 0.0
            else:
                s = (ph - 0.5) / 0.5
                y, z = stride / 2 - stride * s, lift * math.sin(math.pi * s)
            key_foot(clip, rig, spec, 1 + i, (0.0, y + o, z))
    for i in range(frames):
        ph = (i / frames) * 2.0 * math.pi * 2.0      # two bobs per cycle (one per tripod step)
        clip.key("body", 1 + i, loc=(0, 0, body_bob * (0.5 - 0.5 * math.cos(ph))))


def _smooth(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def shell_vertex_indices(mesh):
    """Vertices of everything that is not a leg or an antenna (rigid skinning: one group each)."""
    names = {g.index: g.name for g in mesh.vertex_groups}
    idx = []
    for v in mesh.data.vertices:
        if not v.groups:
            continue
        g = names[max(v.groups, key=lambda e: e.weight).group]
        if not (g.startswith("leg.") or g.startswith("antenna")):
            idx.append(v.index)
    return idx


def evaluated_min_z(mesh, idx):
    import numpy as np

    dg = bpy.context.evaluated_depsgraph_get()
    ev = mesh.evaluated_get(dg)
    me = ev.to_mesh()
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    ev.to_mesh_clear()
    z = co.reshape(-1, 3)[:, 2]
    return float(z[idx].min())


def key_death_settle(clip, rig, mesh, specs, frames, roll, pitch, yaw, splay, centre=(0.0, 0.0, 0.2)):
    """The corpse of the original death frames: the bug tips over onto one side by `roll`, dips its
    nose by `pitch`, turns by `yaw` (the dead sprites lie diagonally) and settles with its shell on
    the ground; the legs splay out by `splay` and follow the body (the IK targets and knee poles are
    carried along with it), feet never below the ground.
    The body bone pivots at its head (the rear of the bug); the location keys move the pivot to the
    body centre, and a per-frame pass lifts/lowers the body so that the lowest point of the shell
    (legs and antennae excluded) never goes under the ground and rests on it once fallen."""
    sc = bpy.context.scene
    pb = rig.pose.bones["body"]
    B = rig.data.bones["body"].matrix_local
    B3inv = B.to_3x3().inverted()
    q = B.inverted() @ Vector(centre)
    fall = int(frames * 0.38)
    plan = [(1, 0.0, 0.0), (int(frames * 0.17), 0.25, 0.15), (fall, 0.85, 1.12), (int(frames * 0.56), 0.97, 0.94), (frames, 1.0, 1.0)]
    for f, k, kr in plan:
        rot = (pitch * k, roll * kr, yaw * k)       # local X = pitch (+ = nose up), Y = roll, Z = yaw
        R = Euler([math.radians(a) for a in rot], "XYZ").to_matrix()
        clip.key("body", f, loc=tuple(q - R @ q), rot=rot)
    # shell on the ground: from standing height at frame 1 down to contact at the fall frame
    idx = shell_vertex_indices(mesh)
    sc.frame_set(1)
    rest_min = max(0.0, evaluated_min_z(mesh, idx))
    lows = []
    for f in range(1, frames + 1):
        sc.frame_set(f)
        m = evaluated_min_z(mesh, idx)
        target = rest_min * (1.0 - _smooth((f - 1) / max(1, fall - 1)))
        dz = target - m
        loc = pb.location.copy() + B3inv @ Vector((0.0, 0.0, dz))
        pb.location = loc
        pb.keyframe_insert("location", frame=f)
        lows.append(m + dz)
    # legs: carried by the body, splayed out, feet clamped to the ground
    for f in range(1, frames + 1):
        sc.frame_set(f)
        bpy.context.view_layer.update()
        M = pb.matrix @ B.inverted()                  # rest armature space -> posed armature space
        s = _smooth((f - 1) / max(1, int(frames * 0.6) - 1))
        for spec in specs:
            n = f"leg.{spec.name}"
            p0 = Vector(spec.foot)
            ydir = {"1": -0.35, "2": 0.0, "3": 0.35}[spec.name[1]]
            want = M @ (p0 + Vector((spec.side * splay * s, ydir * splay * s, 0.0)))
            want.z = max(want.z, 0.0)
            head_rest, reach = leg_reach(rig, spec)
            head = M @ head_rest
            if (want - head).length > reach * 0.96:
                want = head + (want - head).normalized() * reach * 0.96
                want.z = max(want.z, 0.0)
            key_foot(clip, rig, spec, f, tuple(want - p0))
            pole_rest = rig.data.bones[f"{n}.pole"].head_local
            clip.key(f"{n}.pole", f, loc=ik_local(rig, f"{n}.pole", tuple(M @ pole_rest - pole_rest)))
    return lows


def feet_report(variant, rig, mesh, specs, out_path):
    """Numeric check of the baked clips.  Per frame and leg: foot (tail of leg.X.tibia), knee (tail of
    leg.X.femur), IK target, the ankle gap |foot - target| (> 0 when the IK cannot reach), knee
    height, planted-foot travel per frame (constant = no sliding) and sideways drift; the rest-pose
    knee error (posed knee vs modelled knee in the idle pose) and the shell's lowest point."""
    sc = bpy.context.scene
    ad = rig.animation_data
    idx = shell_vertex_indices(mesh)
    rest_knees = {s.name: rig.matrix_world @ rig.data.bones[f"leg.{s.name}.femur"].tail_local for s in specs}
    lines = []
    for t in ad.nla_tracks:
        t.is_solo = True        # (setting is_solo=False on another track would clear the solo state)
        length = int(t.strips[0].frame_end)
        lines.append(f"=== {variant} {t.name} ({length} frames)")
        prev, stance_dy, stance_dx = {}, [], []
        fz, kz, gap, shell = [9.0, -9.0], 9.0, 0.0, [9.0, -9.0]
        knee_err = 0.0
        for f in range(1, length + 1):
            sc.frame_set(f)
            bpy.context.view_layer.update()
            pbs = rig.pose.bones
            mw = rig.matrix_world
            feet = {s.name: mw @ pbs[f"leg.{s.name}.tibia"].tail for s in specs}
            knees = {s.name: mw @ pbs[f"leg.{s.name}.femur"].tail for s in specs}
            tgts = {s.name: mw @ pbs[f"leg.{s.name}.ik"].head for s in specs}
            sz = evaluated_min_z(mesh, idx)
            shell = [min(shell[0], sz), max(shell[1], sz)]
            cells = []
            for s in specs:
                n = s.name
                p, k = feet[n], knees[n]
                fz = [min(fz[0], p.z), max(fz[1], p.z)]
                kz = min(kz, k.z)
                gap = max(gap, (p - tgts[n]).length)
                if t.name == "idle" and f == 1:
                    knee_err = max(knee_err, (k - rest_knees[n]).length)
                planted = p.z <= 0.005
                dy = (p.y - prev[n].y) if n in prev else 0.0
                dx = (p.x - prev[n].x) if n in prev else 0.0
                if t.name == "move" and planted and n in prev and prev[n].z <= 0.005:
                    stance_dy.append(dy)
                    stance_dx.append(abs(dx))
                cells.append(f"{n}:({p.x:+.2f},{p.y:+.2f},{p.z:.3f}) k{k.z:.2f} {'st' if planted else 'sw'}")
            if t.name == "move" or f in (1, length // 2, length):
                body = mw @ pbs["body"].head
                lines.append(f"f{f:02d} body_z={body.z:.3f} shell_min_z={sz:+.3f} | " + " | ".join(cells))
            prev = feet
        lines.append(f"  foot z range {fz[0]:+.3f} .. {fz[1]:.3f}; lowest knee z {kz:+.3f}; max ankle gap {gap:.3f}; "
                     f"shell lowest point {shell[0]:+.3f} .. {shell[1]:+.3f}")
        if t.name == "idle":
            lines.append(f"  rest-pose knee error (idle f1 vs modelled knees): {knee_err:.4f}")
        if stance_dy:
            lines.append(f"  planted-foot travel per frame: dy min {min(stance_dy):+.3f} max {max(stance_dy):+.3f}, "
                         f"sideways |dx| max {max(stance_dx):.3f} (constant dy, zero dx = no sliding)")
        lines.append(f"SUMMARY {variant} {t.name}: foot_z [{fz[0]:+.3f},{fz[1]:.3f}] knee_z_min {kz:+.3f} ankle_gap_max {gap:.3f} "
                     f"shell_z_min {shell[0]:+.3f}" + (f" knee_rest_err {knee_err:.4f}" if t.name == "idle" else "")
                     + (f" stance_dy [{min(stance_dy):+.3f},{max(stance_dy):+.3f}] stance_dx_max {max(stance_dx):.3f}" if stance_dy else ""))
        t.is_solo = False
    sc.frame_set(1)
    text = "\n".join(lines)
    print(text, flush=True)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "a", encoding="utf-8") as fh:
        fh.write(text + "\n")


# --------------------------------------------------------------------------------------------
# attack helpers (beetle attack crew)
# --------------------------------------------------------------------------------------------
def key_pose(clip, rig, bone, frame, rot_axis=None, angle=0.0, move=(0.0, 0.0, 0.0), pivot=None, scale=None):
    """Key a pose bone from armature-space quantities: a rotation of `angle` degrees about the armature-
    space axis `rot_axis` through `pivot` (default: the bone's head), then a translation `move`.  The
    vectors are converted through the bone's rest orientation, i.e. they are taken in its parent's
    frame as it is at rest (a child of a posed bone moves with it)."""
    b = rig.data.bones[bone]
    m3 = b.matrix_local.to_3x3()
    mi = m3.inverted()
    rw = Matrix.Rotation(math.radians(angle), 3, Vector(rot_axis).normalized()) if rot_axis and angle else Matrix.Identity(3)
    rb = mi @ rw @ m3
    loc = mi @ Vector(move)
    if pivot is not None:
        q0 = mi @ (Vector(pivot) - b.head_local)
        loc = loc + q0 - rb @ q0
    rot = tuple(math.degrees(a) for a in rb.to_euler("XYZ"))
    clip.key(bone, frame, rot=rot, loc=tuple(loc), scale=scale)


def shrink_group(mesh, group, center, factor):
    """Scale the vertices of the (rigidly skinned) part `group` toward `center` by 1/factor."""
    gi = mesh.vertex_groups[group].index
    c = Vector(center)
    n = 0
    for v in mesh.data.vertices:
        if any(g.group == gi and g.weight > 0.5 for g in v.groups):
            v.co = c + (v.co - c) / factor
            n += 1
    mesh.data.update()
    salib.log(f"{group}: {n} vertices shrunk 1/{factor:g} around {tuple(round(x, 3) for x in center)}")
    return n


def align_rolls(rig, z_axes):
    """Roll the named bones so that their local Z axis points along the given armature-space vector."""
    salib.select_only([rig])
    bpy.ops.object.mode_set(mode="EDIT")
    for name, z in z_axes.items():
        rig.data.edit_bones[name].align_roll(Vector(z))
    bpy.ops.object.mode_set(mode="OBJECT")


def finalize_unwrapped(asset, objects, preview_radius, preview_center, views):
    """salib.finalize_asset() minus its UV unwrap: the mesh was unwrapped right after the join, before the
    muzzle flashes were shrunk (a fresh unwrap would give the shrunken flash a speck of the texture)."""
    meshes = [o for o in objects if o.type == "MESH"]
    if salib.REALISM:
        for i, m in enumerate(meshes):
            images = salib.bake_object_textures(m, asset, size=1024 if i == 0 else 512)
            salib.build_baked_materials(m, asset, images)
    path = salib.export_glb(asset, objects=objects)
    summary = salib.print_summary(path)
    previews = salib.render_previews(asset, radius=preview_radius, center=preview_center, size=512, samples=64,
                                     views=views)
    salib.contact_sheet(asset, previews)
    salib.save_blend(asset)
    return path, summary


def muzzle_report(variant, rig, muzzle, out_path):
    """Where the shot leaves, measured on the baked attack clip: `muzzle` = (bone, rest point, shot frame).
    Game axes (units.ron `muzzle`): x to the unit's right (-X here), y up (Z), z ahead (-Y); cells."""
    bone, p_rest, shot = muzzle
    sc = bpy.context.scene
    t = next(t for t in rig.animation_data.nla_tracks if t.name == "attack")
    t.is_solo = True
    n = int(t.strips[0].frame_end)
    inv = rig.data.bones[bone].matrix_local.inverted()
    lines = [f"=== {variant} muzzle ({bone} at rest {tuple(round(x, 3) for x in p_rest)}), attack clip {n} frames"]
    for f in range(1, n + 1):
        sc.frame_set(f)
        bpy.context.view_layer.update()
        p = rig.matrix_world @ rig.pose.bones[bone].matrix @ inv @ Vector(p_rest)
        lines.append(f"  f{f:02d}  x {-p.x:+.3f}  y {p.z:.3f}  z {-p.y:+.3f}" + ("   <- shot" if f == shot else ""))
        if f == shot:
            lines.insert(1, f"SUMMARY {variant} muzzle at the shot (frame {shot}): ({-p.x:.2f}, {p.z:.2f}, {-p.y:.2f})")
    t.is_solo = False
    sc.frame_set(1)
    text = "\n".join(lines)
    print(text, flush=True)
    with open(out_path, "a", encoding="utf-8") as fh:
        fh.write(text + "\n")


def mirror_specs(left, radius):
    """Left-side leg table (name, root, knee, foot, phase) -> LegSpecs for both sides."""
    specs = []
    m = lambda p: (-p[0], p[1], p[2])  # noqa: E731
    for name, root, knee, foot, phase in left:
        specs.append(LegSpec(name, +1, root, knee, foot, phase=phase, radius=radius))
        specs.append(LegSpec("R" + name[1:], -1, m(root), m(knee), m(foot), phase=(phase + 0.5) % 1.0, radius=radius))
    return specs


def mask_image(path, size, draw_fn):
    """Greyscale marking mask (255 = untouched colour, 0 = black) drawn by draw_fn(draw, size)."""
    from PIL import Image, ImageDraw, ImageFilter

    im = Image.new("L", (size, size), 255)
    draw_fn(ImageDraw.Draw(im), size)
    im = im.filter(ImageFilter.GaussianBlur(size / 400.0))
    im.save(path)
    return path


def _base_color_source(mat):
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    sock = bsdf.inputs["Base Color"]
    src = sock.links[0].from_socket
    nt.links.remove(sock.links[0])
    return nt, src, sock


def _multiply_into(nt, src, factor, sock):
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 1.0
    nt.links.new(src, mix.inputs[6])
    nt.links.new(factor, mix.inputs[7])
    nt.links.new(mix.outputs[2], sock)


def attach_mask(mat, image_path, frame):
    """Multiply the material's base colour by a top-projected mask image.  `frame` = (x_left, y_front,
    width, length) in Blender units: the image's left edge is x_left, its TOP row is the front (y_front,
    the -Y end of the creature) and its bottom row is y_front + length."""
    x0, y0, w, l = frame
    nt, src, sock = _base_color_source(mat)
    img = bpy.data.images.load(image_path)
    img.colorspace_settings.name = "Non-Color"
    img.pack()
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.extension = "EXTEND"
    tex.interpolation = "Cubic"
    tex.label = "Markings"
    texco = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.vector_type = "POINT"
    mapping.inputs["Location"].default_value = (-x0 / w, 1.0 + y0 / l, 0.0)
    mapping.inputs["Scale"].default_value = (1.0 / w, -1.0 / l, 1.0)
    nt.links.new(texco.outputs["Object"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
    _multiply_into(nt, src, tex.outputs["Color"], sock)
    return img


def attach_spots(mat, spots, edge=0.006):
    """Round black spots in 3-D: a surface point is black within radius r of a spot centre (object
    space = world space at rest), so the spots stay round on the steep flanks of the dome (the planar
    top projection used before stretched them into streaks seen from the side)."""
    nt, src, sock = _base_color_source(mat)
    texco = nt.nodes.new("ShaderNodeTexCoord")
    fac = None
    for c, r in spots:
        d = nt.nodes.new("ShaderNodeVectorMath")
        d.operation = "DISTANCE"
        nt.links.new(texco.outputs["Object"], d.inputs[0])
        d.inputs[1].default_value = c
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.clamp = True
        mr.inputs["From Min"].default_value = r - edge
        mr.inputs["From Max"].default_value = r + edge
        mr.inputs["To Min"].default_value = 0.0
        mr.inputs["To Max"].default_value = 1.0
        nt.links.new(d.outputs["Value"], mr.inputs["Value"])
        if fac is None:
            fac = mr.outputs["Result"]
        else:
            mn = nt.nodes.new("ShaderNodeMath")
            mn.operation = "MINIMUM"
            nt.links.new(fac, mn.inputs[0])
            nt.links.new(mr.outputs["Result"], mn.inputs[1])
            fac = mn.outputs["Value"]
    _multiply_into(nt, src, fac, sock)


# --------------------------------------------------------------------------------------------
# Lady Bug
# --------------------------------------------------------------------------------------------
LB_DOME_C = (0.0, 0.03, 0.13)
LB_DOME_R = (0.5625, 0.60, 0.44)
LB_MUZZLE = (0.0, -0.885, 0.19)    # just in front of the gun's muzzle ring (its face is at y -0.88)


def ladybug_marks(d, S):
    """Planar mask over the dome box x [-0.5625, 0.5625], y [-0.57, 0.63] (front at the top): the
    centre seam and the dark notch where the pronotum shows between the shoulders (the spots are 3-D,
    see ladybug_spots)."""
    W, L = 1.125, 1.20

    def P(x, y):  # model coords -> image px
        return ((x + 0.5625) / W * S, (y + 0.57) / L * S)

    def spot(x, y, rx, ry, fill=0):
        x0, y0 = P(x - rx, y - ry)
        x1, y1 = P(x + rx, y + ry)
        d.ellipse([x0, y0, x1, y1], fill=fill)

    # centre seam (thin, dark grey) from behind the pronotum to the rear tip
    x0, y0 = P(-0.014, -0.46)
    x1, y1 = P(0.014, 0.63)
    d.rectangle([x0, y0, x1, y1], fill=55)
    # dark front notch: the pronotum shows between the elytra's shoulders
    spot(0.0, -0.58, 0.16, 0.11)


def ladybug_spots():
    """Two rows of four spots and one on each flank, positions in top view (x, y) from the sprites
    (up/down and left/right facings averaged: front row 0.18 ahead of, rear row 0.30 behind the dome
    centre; inner pair 0.17, outer pair 0.36 off the seam), lifted onto the dome surface."""
    top = [(0.17, -0.14, 0.066), (0.37, -0.15, 0.072), (0.17, 0.35, 0.066), (0.36, 0.29, 0.072), (0.50, 0.08, 0.056)]
    spots = []
    for x, y, r in top:
        for s in (1, -1):
            spots.append(((s * x, y, dome_z(LB_DOME_C, LB_DOME_R, s * x, y)), r))
    return spots


def build_ladybug(body, mats):
    T, K = "M_Team", "M_Black"
    # glossy shell
    salib.material(T, salib.TEAM_COLORS["Y"], roughness=0.28, kind="chitin", tint=True, coat=0.9, sss=0.1, variation=0.2)
    mats["M_Cream"] = salib.material("M_Cream", (0.86, 0.80, 0.56), roughness=0.4, kind="chitin", variation=0.15)
    # the head is dark slate grey in the portrait and the faces-down sprite (60..90 sRGB), not black
    mats["M_Slate"] = salib.material("M_Slate", (0.22, 0.22, 0.24), roughness=0.3, kind="chitin", coat=0.8, variation=0.2)
    # dome: one oval shell 1.125 wide x 1.20 long, top at z 0.57, flat-ish underside
    shaped_sphere(body, "body", T, LB_DOME_C, LB_DOME_R, segments=28, rings=14, squash=0.15)
    # dark belly plate under the rim
    shaped_sphere(body, "body", K, (0, 0.03, 0.09), (0.54, 0.575, 0.09), segments=16, rings=8, subdiv=False)
    # pronotum + head: one small tall dark slate block tucked under the dome's front; from above only
    # its tip shows (the sprite's 7 x 4 px dark nose; 0.4 cells wide in the faces-down frame)
    shaped_sphere(body, "head", "M_Slate", (0, -0.57, 0.13), (0.19, 0.17, 0.26), segments=16, rings=10, squash=0.45)
    # pale cream mouth band at the bottom of the head (portrait, loading screen)
    shaped_sphere(body, "head", "M_Cream", (0, -0.70, 0.075), (0.11, 0.05, 0.03), segments=12, rings=6, subdiv=False)
    # eyes
    for s in (1, -1):
        shaped_sphere(body, "head", "M_Eye", (s * 0.105, -0.68, 0.25), (0.026, 0.022, 0.026), segments=8, rings=5, subdiv=False)
        # tiny antennae (the portrait shows a thin feeler beside the head)
        body.segment("head", K, (s * 0.07, -0.70, 0.30), (s * 0.17, -0.80, 0.34), 0.01, 0.005, verts=6)["sa_no_subdiv"] = True
    # minigun barrel: the thin line in front of the sprite (muzzle flash there when attacking)
    body.cylinder("gun", "M_Accent", (0.0, -0.77, 0.19), 0.022, 0.18, rot=(math.radians(90), 0, 0), verts=8)["sa_no_subdiv"] = True
    body.cylinder("gun", K, (0.0, -0.86, 0.19), 0.03, 0.04, rot=(math.radians(90), 0, 0), verts=8)["sa_no_subdiv"] = True
    # muzzle flash (the attack frames' orange star on the gun's mouth, 4 x 3 px = 0.17 x 0.12 cells): a
    # core, a forward tongue and four side spikes; modelled full size, shrunk to nothing after the UV
    # unwrap and scaled up by the attack clip while it shows
    mats["M_Flash"] = salib.material("M_Flash", (1.0, 0.58, 0.20), roughness=0.6, emission=(1.0, 0.42, 0.08),
                                     emission_strength=2.0, kind="emissive", variation=0.05)
    m = Vector(LB_MUZZLE)
    core = m + Vector((0.0, -0.022, 0.0))
    shaped_sphere(body, "flash", "M_Flash", tuple(core), (0.036, 0.03, 0.034), segments=8, rings=5, subdiv=False)
    body.segment("flash", "M_Flash", tuple(m), tuple(m + Vector((0.0, -0.12, 0.0))), 0.03, 0.002, verts=6)["sa_no_subdiv"] = True
    for d, ln in (((1.0, -0.7, 0.0), 0.09), ((-1.0, -0.7, 0.0), 0.09), ((0.0, -0.75, 1.0), 0.06), ((0.0, -0.75, -1.0), 0.06)):
        tip = core + Vector(d).normalized() * ln
        body.segment("flash", "M_Flash", tuple(core), tuple(tip), 0.017, 0.001, verts=5)["sa_no_subdiv"] = True
    # legs: short and tucked under the rim - from above the sprite shows none; only the toes peek out
    # (as in the loading-screen renders).  Rim half-width: 0.37 at y -0.42, 0.56 at y 0, 0.44 at y 0.40.
    specs = mirror_specs([
        ("L1", (0.15, -0.40, 0.06), (0.30, -0.46, 0.11), (0.40, -0.44, 0.0), 0.0),
        ("L2", (0.20, -0.02, 0.06), (0.43, -0.02, 0.11), (0.57, -0.02, 0.0), 0.5),
        ("L3", (0.16, 0.36, 0.06), (0.33, 0.40, 0.11), (0.44, 0.40, 0.0), 0.0),
    ], radius=0.028)
    toes = [leg_mesh_beetle(body, spec, K) for spec in specs]
    bones = [
        BoneDef("root", (0, 0, 0), (0, 0.25, 0)),
        BoneDef("body", (0, 0.4, 0.2), (0, -0.3, 0.2), parent="root"),
        BoneDef("head", (0, -0.40, 0.18), (0, -0.74, 0.18), parent="body"),
        BoneDef("gun", (0, -0.66, 0.19), (0, -0.90, 0.19), parent="head"),
        BoneDef("flash", LB_MUZZLE, (0, -0.985, 0.19), parent="gun"),
    ]
    return specs, bones, dict(mask=ladybug_marks, frame=(-0.5625, -0.57, 1.125, 1.20), spots=ladybug_spots(), toes=toes,
                              flashes=[("flash", LB_MUZZLE)], muzzle=("gun", (0.0, -0.88, 0.19), 2),
                              preview_radius=2.8, preview_center=(0, 0, 0.25), antennae=(),
                              walk=dict(frames=6, lift=0.04, bob=0.006),     # 0.2 s scurry, stride 0.25
                              death=dict(roll=26, pitch=-10, yaw=28, splay=0.05))


# --------------------------------------------------------------------------------------------
# Shrapnel
# --------------------------------------------------------------------------------------------
SH_LX, SH_LY = 0.0, -0.27                       # launcher axis on the shield's front
SH_Z_TOP = 0.445                                # launcher top rim (= where the volley leaves)
SH_R_CORE, SH_R_IN, SH_R_OUT = 0.060, 0.064, 0.078
SH_STAVE_LEN = 0.15                             # opened flat: a star 0.45 across (the sprites' ~10 px)
SH_FLASH = (SH_LX, SH_LY, SH_Z_TOP + 0.005)


def stave_hinge(k):
    """Hinge of stave k (angle k x 45 deg around the launcher; k 0 = +X, k 6 = -Y = forward) on the top rim."""
    th = math.radians(45.0 * k)
    r = 0.5 * (SH_R_IN + SH_R_OUT)
    return Vector((SH_LX + r * math.cos(th), SH_LY + r * math.sin(th), SH_Z_TOP))


def launcher_stave(body, k, bone, mat):
    """Stave k of the shrapnel launcher: a curved plate (38 deg of the rim, 0.014 thick) hanging down the
    outside of the core tube from the top rim; the eight of them make the launcher's pale wall."""
    import bmesh

    th0 = math.radians(45.0 * k)
    steps, half = 4, math.radians(19.0)
    verts = []
    for i in range(steps + 1):
        a = th0 - half + 2.0 * half * i / steps
        for r in (SH_R_OUT, SH_R_IN):
            for z in (SH_Z_TOP, SH_Z_TOP - SH_STAVE_LEN):
                verts.append((SH_LX + r * math.cos(a), SH_LY + r * math.sin(a), z))

    def ix(i, ri, zi):
        return i * 4 + ri * 2 + zi

    faces = []
    for i in range(steps):
        faces += [(ix(i, 0, 0), ix(i, 0, 1), ix(i + 1, 0, 1), ix(i + 1, 0, 0)),      # outer face
                  (ix(i, 1, 0), ix(i + 1, 1, 0), ix(i + 1, 1, 1), ix(i, 1, 1)),      # inner face
                  (ix(i, 0, 0), ix(i + 1, 0, 0), ix(i + 1, 1, 0), ix(i, 1, 0)),      # top edge
                  (ix(i, 0, 1), ix(i, 1, 1), ix(i + 1, 1, 1), ix(i + 1, 0, 1))]      # bottom edge
    for i in (0, steps):
        faces.append((ix(i, 0, 0), ix(i, 1, 0), ix(i, 1, 1), ix(i, 0, 1)))           # side edges
    me = bpy.data.meshes.new(f"{body.name}_stave{k}")
    me.from_pydata(verts, [], faces)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(f"{body.name}_stave{k}", me)
    salib.link(o)
    o["sa_no_subdiv"] = True
    return body._finish(o, bone, mat)


def shrapnel_marks(d, S):
    """Skull marking over the shield box x [-0.39, 0.39], y [-0.42, 0.58]; (u, v) fractions, v from
    the front.  Traced from the sprites (up/down facings averaged for the along-body positions)."""
    def P(u, v):
        return (u * S, v * S)

    # brow: a thick straight black bar right behind the launcher (v 0.235..0.365, 0.62 wide, rounded
    # ends; the sprite's 10 x 3 px bar).  Its ends look drooped in the sprites - toward the rear in
    # "faces up" but toward the front in "faces down": that is the tilted camera seeing the bar's
    # lower ends on the curved shield, so the bar itself is straight.
    d.rectangle([P(0.25, 0.235), P(0.75, 0.365)], fill=0)
    for u in (0.25, 0.75):
        d.ellipse([P(u - 0.065, 0.235), P(u + 0.065, 0.365)], fill=0)
    # two thin dim lines from the brow's ends converging to the middle, down to the eyes
    for s in (-1, 1):
        a, b = (0.5 + s * 0.26, 0.36), (0.5 + s * 0.04, 0.69)
        w = 0.03
        d.polygon([P(a[0] - w, a[1]), P(a[0] + w, a[1]), P(b[0] + w, b[1]), P(b[0] - w, b[1])], fill=75)
    # two small black eyes in the rear third
    for u in (0.5 - 0.125, 0.5 + 0.125):
        d.ellipse([P(u - 0.066, 0.76 - 0.056), P(u + 0.066, 0.76 + 0.056)], fill=0)
    # black stroke from between the eyes to the rear tip
    d.rectangle([P(0.445, 0.79), P(0.555, 1.02)], fill=0)


def build_shrapnel(body, mats):
    T, K, B = "M_Team", "M_Black", "M_Brown"
    salib.material(T, salib.TEAM_COLORS["Y"], roughness=0.35, kind="chitin", tint=True, coat=0.7, sss=0.1, variation=0.35)
    # flat broad shield, broadest at the front
    shaped_sphere(body, "body", T, (0, 0.08, 0.14), (0.39, 0.50, 0.21), segments=28, rings=14, squash=0.35, taper=(1.0, 0.86))
    # belly (clear of the ground: the squat of the attack must not push it through)
    shaped_sphere(body, "body", K, (0, 0.08, 0.10), (0.36, 0.47, 0.065), segments=16, rings=8, subdiv=False)
    # glossy black head capsule
    shaped_sphere(body, "head", K, (0, -0.46, 0.15), (0.18, 0.14, 0.15), segments=16, rings=10, squash=0.5)
    for s in (1, -1):
        shaped_sphere(body, "head", "M_Eye", (s * 0.12, -0.55, 0.21), (0.032, 0.028, 0.032), segments=8, rings=5, subdiv=False)
        ab = "antenna.L" if s > 0 else "antenna.R"
        body.segment(ab, K, (s * 0.09, -0.57, 0.20), (s * 0.21, -0.74, 0.24), 0.013, 0.008, verts=6)["sa_no_subdiv"] = True
    # shrapnel launcher on the front-centre of the shield: a dark core tube inside eight pale staves hinged
    # at the top rim - from outside the portrait's short pale cylinder with the dark opening on top; the
    # attack throws the staves open into the eight-armed pale star of the sprites' Fire Point frames
    zb = 0.22
    body.cylinder("launcher", K, (SH_LX, SH_LY, (zb + SH_Z_TOP) / 2), SH_R_CORE, SH_Z_TOP - zb, verts=12)["sa_no_subdiv"] = True
    # staves: pale grey like the sprites' launcher and star, less metallic than the shared M_Pale (which reads
    # dark grey in game), no baked crevice dirt (their inner faces sit against the core tube and would bake
    # dark, then face up when the staves open)
    mats["M_Pale"] = salib.material("M_Pale", (0.80, 0.80, 0.78), roughness=0.4, metallic=0.35, kind="chitin", coat=0.4,
                                    sss=0.0, variation=0.1, bump=0.05, dirt=0.0)
    for k in range(8):
        launcher_stave(body, k, f"launcher.petal.{k}", "M_Pale")
    # burst flash in the opened launcher (pale yellow-white like the sprites' star), shrunk at rest
    mats["M_Flash"] = salib.material("M_Flash", (1.0, 0.93, 0.72), roughness=0.6, emission=(1.0, 0.85, 0.55),
                                     emission_strength=2.5, kind="emissive", variation=0.05)
    c = Vector((SH_LX, SH_LY, SH_Z_TOP + 0.035))
    shaped_sphere(body, "launcher.flash", "M_Flash", tuple(c), (0.06, 0.06, 0.05), segments=8, rings=5, subdiv=False)
    for k in range(8):
        a = math.radians(22.5 + 45.0 * k)
        tip = c + Vector((math.cos(a), math.sin(a), 0.35)).normalized() * 0.13
        body.segment("launcher.flash", "M_Flash", tuple(c), tuple(tip), 0.022, 0.002, verts=5)["sa_no_subdiv"] = True
    body.segment("launcher.flash", "M_Flash", tuple(c), tuple(c + Vector((0.0, 0.0, 0.11))), 0.025, 0.002, verts=5)["sa_no_subdiv"] = True
    # six long legs splayed wide, knees above the shield.  Sprite (faces up) toe positions: front
    # (+-0.65, -0.66), middle (+-0.60, -0.08), rear (+-0.52, +0.42); the shield's half-width is 0.39.
    specs = mirror_specs([
        ("L1", (0.17, -0.40, 0.09), (0.40, -0.55, 0.33), (0.58, -0.64, 0.0), 0.0),
        ("L2", (0.30, -0.12, 0.09), (0.50, -0.10, 0.36), (0.55, -0.07, 0.0), 0.5),
        ("L3", (0.27, 0.16, 0.09), (0.44, 0.33, 0.33), (0.47, 0.42, 0.0), 0.0),
    ], radius=0.034)
    toes = [leg_mesh_beetle(body, spec, "M_Leg", joint_mat=B) for spec in specs]
    bones = [
        BoneDef("root", (0, 0, 0), (0, 0.25, 0)),
        BoneDef("body", (0, 0.4, 0.2), (0, -0.3, 0.2), parent="root"),
        BoneDef("head", (0, -0.34, 0.15), (0, -0.62, 0.15), parent="body"),
        BoneDef("antenna.L", (0.09, -0.57, 0.20), (0.21, -0.74, 0.24), parent="head"),
        BoneDef("antenna.R", (-0.09, -0.57, 0.20), (-0.21, -0.74, 0.24), parent="head"),
        BoneDef("launcher", (0, -0.27, 0.27), (0, -0.27, 0.47), parent="body"),
    ]
    rolls = {}
    for k in range(8):
        th = math.radians(45.0 * k)
        h = stave_hinge(k)
        bones.append(BoneDef(f"launcher.petal.{k}", tuple(h), tuple(h - Vector((0.0, 0.0, 0.1))), parent="launcher"))
        rolls[f"launcher.petal.{k}"] = (-math.cos(th), -math.sin(th), 0.0)     # local X = the hinge's tangent
    bones.append(BoneDef("launcher.flash", SH_FLASH, (SH_LX, SH_LY, SH_Z_TOP + 0.105), parent="launcher"))
    return specs, bones, dict(mask=shrapnel_marks, frame=(-0.39, -0.42, 0.78, 1.0), toes=toes, rolls=rolls,
                              flashes=[("launcher.flash", SH_FLASH)], muzzle=("launcher", (SH_LX, SH_LY, SH_Z_TOP), 6),
                              preview_radius=2.8, preview_center=(0, 0, 0.2), antennae=("antenna.L", "antenna.R"),
                              walk=dict(frames=10, lift=0.10, bob=0.01),     # 0.33 s cycle, stride 0.42
                              death=dict(roll=32, pitch=-7, yaw=-24, splay=0.16))


# --------------------------------------------------------------------------------------------
# Cannon
# --------------------------------------------------------------------------------------------
def cannon_marks(d, S):
    """Elytra box x [-0.29, 0.29], y [-0.02, 0.74]: centre seam + faint elytron edge lines."""
    def P(u, v):
        return (u * S, v * S)

    d.rectangle([P(0.485, 0.0), P(0.515, 0.97)], fill=55)
    for u in (0.5 - 0.2, 0.5 + 0.2):
        d.rectangle([P(u - 0.012, 0.04), P(u + 0.012, 0.9)], fill=175)


def build_cannon(body, mats):
    T, B = "M_Team", "M_Brown"
    salib.material(T, salib.TEAM_COLORS["Y"], roughness=0.4, kind="chitin", tint=True, coat=0.5, sss=0.1, variation=0.35)
    # long team-coloured elytra: blunt front edge, straight sides, rounded rear (y -0.02 .. 0.74)
    shaped_sphere(body, "body", T, (0, 0.36, 0.20), (0.29, 0.38, 0.22), segments=24, rings=14, squash=0.3,
                  taper=(1.0, 0.92), shape=capsule(front=0.35, rear=0.62))
    # dark pronotum (flat shield) and head
    shaped_sphere(body, "body", B, (0, -0.22, 0.17), (0.22, 0.25, 0.14), segments=18, rings=10, squash=0.5)
    shaped_sphere(body, "head", B, (0, -0.57, 0.165), (0.21, 0.15, 0.145), segments=18, rings=10, squash=0.5)
    for s in (1, -1):
        shaped_sphere(body, "head", "M_Eye", (s * 0.17, -0.60, 0.25), (0.035, 0.03, 0.035), segments=8, rings=5, subdiv=False)
        mb = "mandible.L" if s > 0 else "mandible.R"
        body.segment(mb, B, (s * 0.12, -0.66, 0.11), (s * 0.08, -0.77, 0.10), 0.035, 0.022, verts=8)["sa_no_subdiv"] = True
        body.segment(mb, "M_Amber", (s * 0.08, -0.77, 0.10), (s * 0.03, -0.84, 0.09), 0.022, 0.008, verts=8)["sa_no_subdiv"] = True
        # long segmented antennae straight forward (the portrait's dashed feelers)
        ab = "antenna.L" if s > 0 else "antenna.R"
        pts = [(s * 0.15, -0.70, 0.24), (s * 0.19, -0.84, 0.28), (s * 0.21, -0.96, 0.31), (s * 0.22, -1.05, 0.33)]
        for i in range(3):
            body.segment(ab, B, pts[i], pts[i + 1], 0.016 - 0.003 * i, 0.012 - 0.003 * i, verts=6)["sa_no_subdiv"] = True
            if i < 2:
                shaped_sphere(body, ab, "M_Amber", pts[i + 1], (0.016,) * 3, segments=6, rings=4, subdiv=False)
    # cannon: saddle, wide pale breech over the elytra/pronotum junction, grey barrel forward over the head
    # (saddle in the same metal as the barrel: one material / draw call fewer)
    shaped_sphere(body, "cannon", "M_Accent", (0.0, -0.08, 0.30), (0.13, 0.15, 0.09), segments=12, rings=6, subdiv=False)
    body.cylinder("cannon", "M_Pale", (0.0, -0.09, 0.41), 0.105, 0.24, rot=(math.radians(90), 0, 0), verts=12)["sa_no_subdiv"] = True
    # barrel + black muzzle ring on their own bone: the attack's recoil slides them 0.13 back into the breech
    # (the sprites' grey barrel line shortens by ~3 px).  Medium-grey metal - the portrait's barrel is grey,
    # darker than the pale breech, and from above it reads as the sprites' grey line.
    body.cylinder("barrel", "M_Accent", (0.0, -0.34, 0.42), 0.072, 0.32, rot=(math.radians(90), 0, 0), verts=10)["sa_no_subdiv"] = True
    body.cylinder("barrel", "M_Black", (0.0, -0.49, 0.42), 0.086, 0.05, rot=(math.radians(90), 0, 0), verts=10)["sa_no_subdiv"] = True
    # six long legs: front pair forward, middle pair out, rear pair back past the elytra.  Sprite toe
    # positions: front (+-0.46, -0.44), middle (+-0.67, +0.27), rear (+-0.50, +0.83); 2-px femurs.
    # Plain medium-brown legs with dark joints (the sprite's leg pixels are ~(100, 75, 58) sRGB, no amber).
    specs = mirror_specs([
        ("L1", (0.20, -0.30, 0.11), (0.36, -0.42, 0.30), (0.42, -0.47, 0.0), 0.0),
        ("L2", (0.21, -0.10, 0.11), (0.50, 0.06, 0.33), (0.60, 0.24, 0.0), 0.5),
        ("L3", (0.22, 0.10, 0.11), (0.44, 0.40, 0.33), (0.48, 0.68, 0.0), 0.0),
    ], radius=0.036)
    toes = [leg_mesh_beetle(body, spec, "M_Leg", joint_mat=B) for spec in specs]
    bones = [
        BoneDef("root", (0, 0, 0), (0, 0.25, 0)),
        BoneDef("body", (0, 0.4, 0.2), (0, -0.3, 0.2), parent="root"),
        BoneDef("head", (0, -0.42, 0.18), (0, -0.72, 0.18), parent="body"),
        BoneDef("mandible.L", (0.12, -0.66, 0.11), (0.03, -0.84, 0.09), parent="head"),
        BoneDef("mandible.R", (-0.12, -0.66, 0.11), (-0.03, -0.84, 0.09), parent="head"),
        BoneDef("antenna.L", (0.15, -0.70, 0.24), (0.22, -1.05, 0.33), parent="head"),
        BoneDef("antenna.R", (-0.15, -0.70, 0.24), (-0.22, -1.05, 0.33), parent="head"),
        BoneDef("cannon", (0, 0.03, 0.41), (0, -0.50, 0.41), parent="body"),
        BoneDef("barrel", (0, -0.18, 0.42), (0, -0.52, 0.42), parent="cannon"),
    ]
    return specs, bones, dict(mask=cannon_marks, frame=(-0.29, -0.02, 0.58, 0.76), toes=toes,
                              muzzle=("barrel", (0.0, -0.515, 0.42), 6),
                              preview_radius=3.0, preview_center=(0, 0, 0.2), antennae=("antenna.L", "antenna.R"),
                              walk=dict(frames=10, lift=0.10, bob=0.012),    # 0.33 s cycle, stride 0.42
                              death=dict(roll=20, pitch=-5, yaw=30, splay=0.14))


BUILDERS = {"ladybug": build_ladybug, "shrapnel": build_shrapnel, "cannon": build_cannon}


# --------------------------------------------------------------------------------------------
# attack clips (see the module docstring)
# --------------------------------------------------------------------------------------------
NOSE_UP = (-1.0, 0.0, 0.0)      # armature-space axis: a positive angle about it lifts the front (-Y) end


def key_attack(kind, rig, specs, info):
    """The `attack` clip.  The exporter writes frame f at f/30 s, so 9 frames = 0.3 s (lady bug) and 18 frames
    = 0.6 s (shrapnel, cannon): speed 1 at the units.ron attack_anim_time.  The sim releases the shot
    fire_delay after the start, on its 30 Hz tick 2 (lady bug, 0.05 s) / tick 6 (0.2 s) = frame 2 / frame 6.
    Feet stay planted (IK targets at rest)."""
    n = 9 if kind == "ladybug" else 18
    c = new_clip(rig, "attack", n, loop=False)
    for spec in specs:
        c.key(f"leg.{spec.name}.ik", n, loc=(0, 0, 0))
    S = FLASH_SHRINK
    if kind == "ladybug":
        # frame: (flash size x the modelled star (0 = out), flash distance ahead of the mouth, barrel kick
        # back, head jerk (deg, nose up), body pushed back).  Frames 1 and 9 are the idle stance (the clip
        # restarts every 0.33 s while it fires: continuous fire); on the shot (frame 2) the star opens on the
        # gun's mouth (sprite frame 1), then it shrinks and drifts ahead as the sprites' small detached flash
        # (frame 0) and goes out: lit for about half of each shot, like the sprites' looping two frames.
        plan = {1: (0, 0, 0, 0, 0), 2: (1.35, 0.0, 0.0, 0.0, 0.0), 3: (1.2, 0.02, 0.03, 2.0, 0.010),
                4: (0.8, 0.06, 0.022, 1.2, 0.007), 5: (0.6, 0.09, 0.012, 0.5, 0.004),
                6: (0.45, 0.12, 0.005, 0.2, 0.002), 7: (0, 0.12, 0, 0, 0), 8: (0, 0, 0, 0, 0), 9: (0, 0, 0, 0, 0)}
        for f, (fs, ahead, kick, jerk, push) in plan.items():
            s = S * fs if fs else 1.0
            key_pose(c, rig, "flash", f, move=(0.0, -ahead, 0.0), scale=(s, s, s))
            key_pose(c, rig, "gun", f, move=(0.0, kick, 0.0))
            key_pose(c, rig, "head", f, rot_axis=NOSE_UP, angle=jerk)
            key_pose(c, rig, "body", f, move=(0.0, push, 0.0))
    elif kind == "shrapnel":
        # frame: (body squat, body pitch (deg, nose up), launcher rise, staves opened (deg from hanging),
        # burst flash size).  Wind-up: the bug squats and the launcher rises (sprite frame 0); the shot on
        # frame 6: the staves fling open into the eight-armed star round the burst (sprite frame 1) and the
        # bug jolts up; the staves fold shut and the bug settles by frame 16.
        plan = {1: (0, 0, 0, 0, 0), 2: (-0.006, -0.4, 0.008, 1, 0), 4: (-0.016, -1.1, 0.026, 6, 0),
                5: (-0.020, -1.5, 0.036, 12, 0), 6: (-0.020, -1.5, 0.040, 70, 0.8),
                7: (0.012, 1.5, 0.025, 100, 1.15), 8: (0.004, 0.8, 0.025, 106, 0.6),
                9: (0.0, 0.3, 0.030, 100, 0), 10: (0, 0, 0.030, 100, 0), 11: (0, 0, 0.028, 92, 0),
                12: (0, 0, 0.024, 75, 0), 13: (0, 0, 0.018, 50, 0), 14: (0, 0, 0.011, 25, 0),
                15: (0, 0, 0.004, 8, 0), 16: (0, 0, 0, 0, 0), 18: (0, 0, 0, 0, 0)}
        for f, (dz, pitch, rise, opened, fs) in plan.items():
            key_pose(c, rig, "body", f, rot_axis=NOSE_UP, angle=pitch, move=(0.0, 0.0, dz), pivot=(0.0, 0.05, 0.2))
            key_pose(c, rig, "launcher", f, move=(0.0, 0.0, rise))
            for k in range(8):
                th = math.radians(45.0 * k)
                # axis = the hanging stave's direction (down) x its outward radius: + swings the stave out
                key_pose(c, rig, f"launcher.petal.{k}", f, rot_axis=(math.sin(th), -math.cos(th), 0.0), angle=opened)
            s = S * fs if fs else 1.0
            key_pose(c, rig, "launcher.flash", f, scale=(s, s, s))
        for b in info["antennae"]:
            for f, a in ((1, 0), (6, 0), (8, 10), (12, 0), (18, 0)):
                key_pose(c, rig, b, f, rot_axis=NOSE_UP, angle=a)
    else:
        # frame: (body back (+Y), body squat, body pitch (nose up), head pitch, barrel recoil, antenna whip).
        # Brace (frames 2-6: lowered, nose down, aiming); the shot on frame 6; the barrel slams 0.13 back into
        # the breech by frame 7 (sprite frame 1: the grey line ~3 px shorter, held 300 ms) and runs out again
        # by frame 17; the body rocks back and up on its planted legs and the antennae whip.
        plan = {1: (0, 0, 0, 0, 0, 0), 2: (0, -0.005, -0.5, -0.6, 0, 0), 4: (0, -0.012, -1.2, -1.6, 0, 0),
                5: (0, -0.015, -1.5, -2.0, 0, 0), 6: (0, -0.015, -1.5, -2.0, 0.0, 0),
                7: (0.035, -0.006, 3.0, 3.0, 0.13, 10), 8: (0.040, -0.003, 3.5, 4.0, 0.13, 12),
                9: (0.032, 0, 2.6, 2.5, 0.125, 8), 10: (0.022, 0, 1.6, 1.0, 0.11, 4),
                11: (0.013, 0, 0.7, 0.0, 0.085, 0), 12: (0.006, 0, 0.2, 0, 0.06, 0), 13: (0.002, 0, 0, 0, 0.04, 0),
                14: (0, 0, 0, 0, 0.022, 0), 15: (0, 0, 0, 0, 0.010, 0), 16: (0, 0, 0, 0, 0.003, 0),
                17: (0, 0, 0, 0, 0, 0), 18: (0, 0, 0, 0, 0, 0)}
        for f, (back, dz, pitch, hp, recoil, whip) in plan.items():
            key_pose(c, rig, "body", f, rot_axis=NOSE_UP, angle=pitch, move=(0.0, back, dz), pivot=(0.0, 0.1, 0.2))
            key_pose(c, rig, "head", f, rot_axis=NOSE_UP, angle=hp)
            key_pose(c, rig, "barrel", f, move=(0.0, recoil, 0.0))
            for b in info["antennae"]:
                key_pose(c, rig, b, f, rot_axis=NOSE_UP, angle=whip)
    return c.finish()


# --------------------------------------------------------------------------------------------
def build(variant: str, quick=False):
    kind = VARIANTS[variant]["kind"]
    salib.reset_scene(variant)
    mats = salib.standard_materials("Y")
    mats["M_Brown"] = salib.material("M_Brown", (0.17, 0.11, 0.075), roughness=0.42, kind="chitin", coat=0.55, variation=0.3)
    mats["M_Amber"] = salib.material("M_Amber", (0.80, 0.48, 0.14), roughness=0.3, kind="glossy")
    mats["M_Pale"] = salib.material("M_Pale", (0.74, 0.74, 0.72), roughness=0.35, metallic=0.85, kind="metal")
    # legs of the shrapnel and cannon beetles: medium brown like the sprites' legs (lit ~(100, 75, 58))
    mats["M_Leg"] = salib.material("M_Leg", (0.32, 0.22, 0.15), roughness=0.45, kind="chitin", coat=0.4, variation=0.25)
    body = Body(variant, mats)
    specs, bones, info = BUILDERS[kind](body, mats)

    # markings painted into the team material (top projection; the lady bug's spots in 3-D)
    tmp_dir = tempfile.mkdtemp(prefix="sa_beetle_")
    mask_path = mask_image(os.path.join(tmp_dir, f"{variant}_marks.png"), 1024, info["mask"])
    attach_mask(mats["M_Team"], mask_path, info["frame"])
    if info.get("spots"):
        attach_spots(mats["M_Team"], info["spots"])
    if quick:
        os.makedirs(QUICK_DIR, exist_ok=True)
        shutil.copy(mask_path, os.path.join(QUICK_DIR, f"{variant}_marks.png"))

    mesh = body.join()
    # UV unwrap now, with the muzzle flashes at full size (they get a proper patch of the texture), then
    # shrink them to nothing around their bone's head: hidden at rest / in the bind pose, the attack clip
    # scales the bone up by FLASH_SHRINK while the flash shows (finalize_unwrapped() does not re-unwrap)
    if salib.REALISM:
        salib.uv_unwrap(mesh)
    for group, head in info.get("flashes", ()):
        shrink_group(mesh, group, head, FLASH_SHRINK)
    for spec in specs:
        bones += leg_bones_beetle(spec, parent="body")
    bones += foot_bones(specs, info["toes"])      # after the IK targets they hang from
    rig = salib.build_armature("Rig", bones)
    if info.get("rolls"):
        align_rolls(rig, info["rolls"])
    salib.skin(mesh, rig)
    apply_leg_ik(rig, specs)

    # ---- animations -----------------------------------------------------------------------
    clips = []
    c = new_clip(rig, "idle", 36)
    salib.key_idle(c, specs, 36, body_bob=0.01, antenna_bones=info["antennae"])   # IK offsets 0 only
    clips.append(c.finish())

    w = info["walk"]
    frames = w["frames"]
    stride = 1.25 * frames / salib.FPS      # slide-free at the game's nominal 2.5 cells/s playback
    offs = stride_offsets(rig, specs, stride)
    salib.log(f"{variant}: move clip {frames} frames, stride {stride:.3f} cells, stride-window shifts "
              + ", ".join(f"{k} {v:+.3f}" for k, v in offs.items()))
    c = new_clip(rig, "move", frames)
    key_walk(c, rig, specs, frames, stride=stride, lift=w["lift"], body_bob=w["bob"], offsets=offs)
    if kind == "cannon":
        for f, ang in ((1, 0), (3, 3), (5, 0), (8, -3), (10, 0)):
            c.key("antenna.L", f, rot=(ang * 2, 0, 0))
            c.key("antenna.R", f, rot=(-ang * 2, 0, 0))
    clips.append(c.finish())

    # attack: each beetle's own weapon, after the original attack frames (key_attack)
    clips.append(key_attack(kind, rig, specs, info))

    # death: the sprites' corpse - tipped onto one side, turned, shell on the ground, legs splayed
    c = new_clip(rig, "death", 36, loop=False)
    dd = info["death"]
    c.key("head", 1, rot=(0, 0, 0)); c.key("head", 36, rot=(-12, 0, 0))     # (before the ground pass)
    for b in info["antennae"]:
        c.key(b, 1, rot=(0, 0, 0)); c.key(b, 36, rot=(-15, 0, 0))
    lows = key_death_settle(c, rig, mesh, specs, 36, dd["roll"], dd["pitch"], dd["yaw"], dd["splay"])
    salib.log(f"{variant}: death shell lowest point per frame min {min(lows):+.4f} max {max(lows):+.4f}")
    clips.append(c.finish())
    salib.bake_actions(rig, clips)
    feet_report(variant, rig, mesh, specs, REPORT)
    muzzle_report(variant, rig, info["muzzle"], MUZZLE_REPORT)

    if quick:
        # no bake/export: the scene is saved for the crew's render scripts (qa/agents/beetle_attacks/tools)
        os.makedirs(QUICK_DIR, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(QUICK_DIR, f"{variant}_quick.blend"), compress=True)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None
    path, s = finalize_unwrapped(variant, [rig, mesh], preview_radius=info["preview_radius"],
                                 preview_center=info["preview_center"],
                                 views=("front", "back", "left", "right", "threequarter", "top"))
    shutil.rmtree(tmp_dir, ignore_errors=True)
    assert sorted(a["name"] for a in s["animations"]) == ["attack", "death", "idle", "move"]
    assert "M_Team" in s["materials"]
    return path


if __name__ == "__main__":
    flags = [a for a in salib.script_args() if a.startswith("-")]
    args = [a for a in salib.script_args() if not a.startswith("-")] or list(VARIANTS)
    for v in args:
        if v not in VARIANTS:
            raise SystemExit(f"unknown variant {v}; choose from {list(VARIANTS)}")
        build(v, quick="--quick" in flags)
        print("BUILT", v, flush=True)
