"""Builds the ant family: Ant Soldier (+ Grenadier, Bazooka, Bull Ant, Pirate Grenadier variants).

Faithful rebuild from the original art (reference/models/<asset>/, measured in
qa/agents/ants/measure_sprites.py + profile_sprite.py; 24 sprite px = 1 cell):

* Soldier sprite UNANTSO, top-down STAND frame 26 x 39 px (1.08 x 1.62 cells): the closed mandibles
  form a big elliptical RING in front of the head (15 px across, ~9.5 px along the body axis), then a
  round head (12 px wide, ~9 px long), a narrow elongated thorax (7 x ~10 px) carrying three pairs
  of long legs (2 px thick, front pair sweeping forward, middle pair straight out, rear pair
  sweeping back, 26 px total spread), a petiole and a big round gaster (12.5 px).  In ATTACK1 the
  body rears up and each mandible swings outward ~65 deg into a sickle; ATTACK2 snaps them shut.
  DEATH: the ant lies flattened with the legs splayed out to both sides.
* The 3-D portrait (COLONYANTA3D): smooth glossy chitin, big black glossy eyes, thin antennae and
  chunky legs (femur and tibia nearly as thick as each other, about a third of the thorax width)
  with the femur rising above the body to a high knee and the tibia angling down and out to the
  ground.
* team_colour_regions: the WHOLE ant takes the team colour (legs and mandibles included); only the
  eyes keep their own colour.
* Grenadier (UNANTRG, COLONYANTB3D): a smaller ant (28 px body vs the soldier's 32 -> 0.88),
  small pincer mandibles, a plain light-grey rounded pack (6-7 px) on the thorax right behind the
  head; 24 x 33 px overall.  The bold V of "prongs" in front are the antennae seen from above (2-3
  px thick, as thick as the legs; the portrait shows long thick feelers).
* Bazooka (UNANTBZ, COLONYANTC3D): the grenadier-size body (26 x 34 px -> 0.91) with a grey tube
  lying diagonally over the back from the gaster's left to past the head's right (the portrait
  shows it about as long as the body); thick antennae like the grenadier.
* Bull Ant (UNANTSOX, 30 x 45 px = the soldier sprite x 1.154 in both directions) = soldier body
  in neutral black with dark-blue eyes; Pirate Grenadier (UNANTRGX, 24 x 33 px) = grenadier body in
  black with dark-blue eyes (portraits: black eyes with a blue glint).

Legs (rebuilt by the second ant crew, see qa/agents/ants/shift2/):
* Six legs rooted on the thorax (pronotum / mesonotum / propodeum), each a coxa ball + stub, a
  bowed femur rising to a high knee, a tibia coming down to the ankle and a tarsus (foot) lying on
  the ground.  The foot is its own deforming bone and IS the IK target (child of the root): a
  planted foot cannot slide, tilt or sink, whatever the femur / tibia do.
* salib.apply_leg_ik uses fixed +-90 deg pole angles that do not reproduce the modelled pose for
  these bone directions (knees 0.2-0.45 cells off); here every leg gets an in-plane pole above
  its knee and a pole angle fitted numerically so the IK rest pose equals the modelled pose.
* salib.key_walk_cycle / key_death key the IK targets as if bone-local were world space; this
  script uses the scorpion crew's ik_local() / key_walk() / key_death_splay() (armature-space
  offsets through the IK bones' rest matrices).
* Blender's IK solver starts from the FK pose, and salib.bake_actions bakes the clips one after
  another, so every clip keys the leg chains' FK channels at rest (key_chain_rest); otherwise a
  clip inherits the previous clip's last baked rotations and knees can flip (seen in attack).
* Walk = alternating tripod (L1 R2 L3 / R1 L2 R3), 8 frames, duty factor 0.5.  The game plays
  `move` at unit speed / 2.5 (views.rs), so a slide-free stride is 1.25 x the cycle length in
  seconds, divided by units.ron's model_scale (VARIANTS game_scale).  The front / rear stance
  windows are offset (STANCE_DY) so neighbouring feet never touch at the tripod switch.  Looping
  clips are keyed on frames 0..N with frame N = frame 0, so the GLB clip starts at t = 0 and its
  last sample equals its first (seamless loop in Bevy; with frames 1..N Bevy holds frame 1 for
  1/30 s and jumps from frame N back to frame 1, a one-step foot slip per cycle).
* Checked numerically on the exported GLBs: qa/agents/ants/shift2/glb_feet.py (numpy glTF
  skinning, what the game plays) and check_legs.py (deformed mesh in Blender).

Attack clips (attack crew, qa/agents/ant_attacks/; studied from all eight facings of the original
UNANT??_AT* frames in Game.ANI / Game.DDF - two frames each, frame 2 carries the original's
[Damage] / [Fire Point] script and the "Launch Point" - and timed to the game: views.rs restarts
`attack` at every shot, sa_sim fires `fire_delay` s after the start and units.ron sets the playback
length `attack_anim_time`):
* Soldier / Bull Ant (UNANTSO?_AT, 150 + 150 ms): frame 1 the ring mandibles swing open into two
  sickles (~40 deg each: tips 15 px apart, 19-20 px overall, against the closed ring's 13-15 px),
  frame 2 [Damage] they snap back into the ring; the body lunges forward ~2-3 px (0.1 cell) over
  its planted feet.  Bites repeat every 0.32 s reload, so the clip starts and ends in the attack
  stance (lunged, mandibles half open); the snap lands at clip frame 4 = the bite's fire_delay
  0.15 s (attack_anim_time 0.4-0.45).
* Grenadier / Pirate Grenadier (UNANTRG?_AT, 400 + 400 ms): frame 1 the RIGHT foreleg is raised
  with a blue grenade (sprite colour 73,86,128) beside the head, frame 2 [Fire Point] it has swung
  forward and the grenade leaves at the Launch Point (sprite px, all facings: ~8 px ahead, ~7 px to
  the right).  Here: the foreleg rises, the grenade comes out of the pack into its claw, cocks back,
  swings forward and is released at clip frame 12 = fire_delay 0.4 s (the game's projectile takes
  over; the held grenade vanishes and returns to the pack), the leg plants again by the end.
* Bazooka (UNANTBZ?_AT, 200 + 400 ms): the tube that lies diagonally over the back in stand / walk
  is shouldered on the RIGHT side, parallel to the body and pointing ahead (Launch Point ~11 px
  ahead, ~7 px right); the body stands up taller with the legs drawn in; frame 2 [Fire Point] adds
  a bright back-blast at the tube's rear end (248,247,161 / 249,194,96).  Here: shoulder, aim,
  fire at clip frame 11 = fire_delay 0.36 s with the back-blast flash (an emissive cone that is
  scaled up from inside the breech), recoil, swing the tube back onto the back by the end.

Conventions: 1 unit = 1 cell, Z up, rest pose faces -Y, origin on the ground at the body centre.
Materials: M_Team (whole body), M_Eye, M_Pack (grenade pack), M_Grenade (held grenade),
M_Accent / M_Black (bazooka tube), M_Flash (bazooka back-blast, emissive).
Clips: idle / move / attack / death.

Usage:  blender -b --factory-startup --python build_ant.py -- [variant ...]   (default: ant_soldier)
Variants: ant_soldier ant_grenadier ant_bazooka neutral_bull_ant neutral_pirate_grenadier
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402
import salib  # noqa: E402
from salib import BoneDef, Body, Clip, LegSpec  # noqa: E402

VARIANTS = {
    # ring: big closed-mandible ring (soldier type) else small pincers; yshift re-centres the
    # ring-less bodies.  scale, from the STAND sprites (qa/agents/ants/profile_sprite.py): the
    # soldier body (head to gaster end) is 32 px, the grenadier / bazooka / pirate bodies 28 px
    # (33-34 px overall with the antenna prongs) -> 0.88 (the bazooka sprite is a little larger,
    # 26 x 34 px vs 24 x 33 -> 0.91); the Bull Ant sprite (30 x 45 px) is the
    # soldier's (26 x 39) x 1.154 in both directions and units.ron applies model_scale 1.1 -> 1.05.
    # game_scale: units.ron model_scale (the walk stride is divided by it so feet do not slide).
    "ant_soldier": dict(neutral=False, scale=1.0, ring=True, mandible=1.0, weapon=None, yshift=0.0, attack_frames=12, game_scale=1.0),
    "ant_grenadier": dict(neutral=False, scale=0.88, ring=False, mandible=1.0, weapon="grenade", yshift=-0.10, attack_frames=21, game_scale=1.0),
    "ant_bazooka": dict(neutral=False, scale=0.91, ring=False, mandible=1.0, weapon="bazooka", yshift=-0.10, attack_frames=18, game_scale=1.0),
    "neutral_bull_ant": dict(neutral=True, scale=1.05, ring=True, mandible=1.0, weapon=None, yshift=0.0, attack_frames=12, game_scale=1.1),
    "neutral_pirate_grenadier": dict(neutral=True, scale=0.88, ring=False, mandible=1.0, weapon="grenade", yshift=-0.10, attack_frames=21, game_scale=1.0),
}

# leg layout, left side (+X); the right side is mirrored.  Three pairs rooted along the thorax
# (pronotum / mesonotum / propodeum - never the head or the gaster), knee high and outside (the
# femur rises above the body like the portrait), ankle just above the ground and a flat tarsus
# (foot) on it.  Sprite: front pair sweeps forward, middle pair straight out, rear pair sweeps
# back, 26 px (1.08 cells) total spread.  The feet are spaced along Y so that a stride of 0.33
# never lets a front / rear foot touch the middle foot at the tripod switch.
LEGS = [
    # name, root (coxa), knee, ankle (IK target), toe tip, phase (tripod gait)
    ("L1", (0.09, -0.06, 0.25), (0.26, -0.25, 0.47), (0.40, -0.22, 0.038), (0.47, -0.28, 0.0), 0.0),
    ("L2", (0.11, 0.12, 0.24), (0.31, 0.12, 0.50), (0.47, 0.16, 0.038), (0.545, 0.18, 0.0), 0.5),
    ("L3", (0.09, 0.27, 0.24), (0.26, 0.43, 0.46), (0.40, 0.60, 0.038), (0.46, 0.67, 0.0), 0.0),
]
LEG_RADIUS = 0.050   # femur radius: the portrait's legs are a third of the thorax width (sprite: 2 px)
MOVE_FRAMES = 8      # walk cycle (0.267 s at 30 fps); the game rescales it by unit speed / 2.5
MOVE_LIFT = 0.085    # swing height of a foot
# stance windows of the front / rear pairs pushed forward / back so a landing middle foot never
# meets the front / rear foot of the same side at the tripod switch (matters for the 0.88 bodies)
STANCE_DY = {"1": -0.03, "2": 0.0, "3": 0.03}

# ---- attack timing (units.ron / weapons, read only): the game restarts `attack` at every shot,
# plays it over attack_anim_time and fires fire_delay s after the start.  Each clip is keyed on
# frames 0..n (n / 30 s long) and puts its strike / release on the frame that is fire_delay into
# the clip at the default attack_anim_time:
#   soldier / bull ant: bite fire_delay 0.15 of attack_anim_time 0.4  -> snap shut on frame 4 of 12
#   grenadier / pirate: grenade fire_delay 0.40 of 0.7                -> release on frame 12 of 21
#   bazooka:            rocket fire_delay 0.36 of 0.6                 -> fire on frame 11 of 18
ATTACK_HIT_FRAME = {"bite": 4, "grenade": 12, "bazooka": 11}
GRENADE_R = 0.066                                  # held grenade radius (x scale): a ~3 px ball


def GRENADE_REST(V):
    """The grenade waits inside the pack (the pack's centre)."""
    return V(0.0, 0.11, 0.50)


def BAZOOKA_REST(V):
    """Bazooka tube at rest: (rear, front) - diagonal over the back like the stand / walk sprites.
    0.72 cell long (x0.91): the shouldered tube in the attack frames is 14-18 px (0.6-0.75 cell) and
    the portrait shows it a little over half the body length (it was 0.89 before the attack crew)."""
    return V(0.04, 0.16, 0.55), V(-0.17, -0.60, 0.50)


FLASH_GROW = 12.0                                  # the back-blast cone is modelled this much smaller


def FLASH_HEAD(rear, d, R):
    """Pivot of the back-blast (bone "flash"): just inside the breech cap, which runs from
    rear - 0.02 to rear + 0.12 along the tube, so the shrunken cone hides inside it at rest and
    scaled up it reaches ~0.18 cell out of the tube's back end."""
    return rear + d * R(0.005)


# ------------------------------------------------------------------------------------------------
# geometry helpers
# ------------------------------------------------------------------------------------------------
def tube(body: Body, bone, mat, pts, radii, sides=8, flat=(1.0, 1.0), up=(0, 0, 1)):
    """A tapered tube swept along the polyline `pts` (per-point `radii`), elliptical cross-section
    (`flat` = (in-plane, out-of-plane) factors), parallel-transported frame, capped ends.  Built at
    its final resolution (no subdivision pass) so the triangle count stays predictable."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    tangents = []
    for i in range(n):
        if i == 0:
            t = pts[1] - pts[0]
        elif i == n - 1:
            t = pts[-1] - pts[-2]
        else:
            t = pts[i + 1] - pts[i - 1]
        tangents.append(t.normalized())
    nrm = Vector(up).cross(tangents[0])
    if nrm.length < 1e-4:
        nrm = Vector((1, 0, 0)).cross(tangents[0])
    nrm.normalize()
    verts, faces = [], []
    for i, (p, t) in enumerate(zip(pts, tangents)):
        nrm = nrm - t * nrm.dot(t)
        if nrm.length < 1e-6:
            nrm = Vector(up).cross(t)
        nrm.normalize()
        b = t.cross(nrm).normalized()
        r = radii[i] if isinstance(radii, (list, tuple)) else radii
        for j in range(sides):
            a = 2 * math.pi * j / sides
            verts.append(p + nrm * (r * flat[0] * math.cos(a)) + b * (r * flat[1] * math.sin(a)))
    for i in range(n - 1):
        for j in range(sides):
            a0 = i * sides + j
            a1 = i * sides + (j + 1) % sides
            faces.append((a0, a1, a1 + sides, a0 + sides))
    faces.append(tuple(reversed(range(sides))))
    faces.append(tuple(range((n - 1) * sides, n * sides)))
    me = bpy.data.meshes.new(f"{body.name}_tube")
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    o = bpy.data.objects.new(me.name, me)
    salib.link(o)
    o["sa_no_subdiv"] = True
    return body._finish(o, bone, mat)


def ring_mandible_points(side, m=1.0, base_x=0.15, base_y=-0.37, z0=0.28, z1=0.25, n=13):
    """Half-ellipse arc from the head's front corner, out to +-half_width and forward to the tip on
    the centre line: the two arcs together form the sprite's mandible ring (`m` enlarges it)."""
    # sprite ring: 15 px across x 9.5 px along the axis OUTSIDE edge; the arc path runs one tube
    # radius inside that
    half_width = 0.27 * m
    tip_y = base_y - 0.40 * m
    th0 = math.acos(base_x / half_width)                  # parameter at the base corner
    b = (base_y - tip_y) / (1.0 + math.sin(th0))          # semi-axis along Y
    cy = tip_y + b                                        # ellipse centre
    th_start = th0 + math.radians(7)                      # start a little inside the head (no seam)
    th_end = math.radians(-89)                            # the two tips meet on the centre line
    pts, radii = [], []
    for i in range(n):
        u = i / (n - 1)
        th = th_start + (th_end - th_start) * u
        x = side * half_width * math.cos(th)
        y = cy + b * math.sin(th)
        z = z0 + (z1 - z0) * u
        pts.append((x, y, z))
        radii.append(0.056 * (1 - u) ** 0.4 + 0.012 * u)
    return pts, radii


def pincer_points(side):
    """Small forward-pointing pincer for the grenadier / bazooka heads."""
    pts = [(side * 0.12, -0.39, 0.26), (side * 0.13, -0.49, 0.25), (side * 0.09, -0.56, 0.24), (side * 0.04, -0.60, 0.235)]
    return pts, [0.034, 0.030, 0.020, 0.010]


ANTENNA = {  # base on the head top, elbow high in front, flagellum forward-out-down (portrait)
    "base": (0.07, -0.37, 0.42), "elbow": (0.16, -0.52, 0.63), "tip": (0.30, -0.72, 0.50),
}


def antenna_mesh(body: Body, bone, mat, side, V, R, thick=1.0):
    """Elbowed antenna: straight scape up to an elbow ball, straight flagellum forward.  `thick`:
    the grenadier / bazooka sprites show the antennae as a bold V of leg-thick prongs in front of
    the head (2-3 px), the portraits as long thick feelers."""
    sx = lambda p: (side * p[0], p[1], p[2])
    base, elbow, tip = (V(*sx(ANTENNA[k])) for k in ("base", "elbow", "tip"))
    tube(body, bone, mat, [base, elbow], [R(0.021 * thick), R(0.016 * thick)], sides=6)
    o = body.sphere(bone, mat, elbow, R(0.019 * thick), segments=7, rings=4)
    o["sa_no_subdiv"] = True
    tube(body, bone, mat, [elbow, tip], [R(0.015 * thick), R(0.008 * thick)], sides=6)


# ------------------------------------------------------------------------------------------------
# legs: specs, mesh, rig (local replacements for salib.leg_bones / leg_mesh / apply_leg_ik)
# ------------------------------------------------------------------------------------------------
def leg_specs(scale=1.0, yshift=0.0):
    specs = []
    for name, root, knee, ankle, toe, phase in LEGS:
        for side, nm in ((+1, name), (-1, "R" + name[1:])):
            m = lambda p: (side * p[0] * scale, (p[1] + yshift) * scale, p[2] * scale)
            spec = LegSpec(nm, side, m(root), m(knee), m(ankle),
                           phase=phase if side > 0 else (phase + 0.5) % 1.0, radius=LEG_RADIUS * scale)
            spec.toe = m(toe)
            spec.stance_dy = STANCE_DY[name[1]]
            specs.append(spec)
    return specs


def leg_mid(spec):
    """Coxa / femur joint (trochanter): 35 % of the way from the root to the knee (as in salib)."""
    return Vector(spec.root).lerp(Vector(spec.knee), 0.35)


def leg_mesh(body: Body, spec: LegSpec, mat):
    """Jointed leg: coxa ball on the thorax + stub, trochanter ball, bowed femur, knee ball, tibia,
    ankle ball and a flat tarsus (foot) whose sole touches the ground (z = 0).  The ankle ball and
    the foot belong to the foot bone (leg.X.ik), everything else to coxa / femur / tibia."""
    n = f"leg.{spec.name}"
    root, knee, ankle, toe = Vector(spec.root), Vector(spec.knee), Vector(spec.foot), Vector(spec.toe)
    mid = leg_mid(spec)
    r = spec.radius
    k = r / LEG_RADIUS                     # variant scale

    def ball(bone, p, f, seg=8, rings=5):
        o = body.sphere(bone, mat, tuple(p), r * f, segments=seg, rings=rings)
        o["sa_no_subdiv"] = True

    ball(f"{n}.coxa", root, 1.25)
    tube(body, f"{n}.coxa", mat, [root, mid], [r * 1.12, r * 1.0], sides=8)
    ball(f"{n}.coxa", mid, 1.0)                                                    # trochanter
    bow = (mid + knee) * 0.5 + Vector((0, 0, 0.035 * k))
    tube(body, f"{n}.femur", mat, [mid, bow, knee], [r * 0.98, r * 1.06, r * 0.88], sides=8)
    ball(f"{n}.femur", knee, 0.93)                                                 # knee
    out = Vector((spec.side, 0, 0))
    mid2 = knee.lerp(ankle, 0.5) + out * (0.015 * k)
    tube(body, f"{n}.tibia", mat, [knee, mid2, ankle], [r * 0.84, r * 0.74, r * 0.62], sides=8)
    ball(f"{n}.ik", ankle, 0.64, seg=8, rings=5)                                   # ankle
    # tarsus: from the ankle down to the toe; the toe's tube centre sits one radius above z = 0
    toe_r = r * 0.36
    toe_c = Vector((toe.x, toe.y, toe_r))
    foot_mid = ankle.lerp(toe_c, 0.55) + Vector((0, 0, -0.004 * k))
    tube(body, f"{n}.ik", mat, [ankle, foot_mid, toe_c], [r * 0.56, r * 0.46, toe_r], sides=7)


def leg_bones(spec: LegSpec, parent="body"):
    """coxa / femur / tibia FK chain, the foot bone (ankle -> toe, deforming, child of the root) that
    is also the IK target, and a pole placed in the leg's bending plane above the knee."""
    n = f"leg.{spec.name}"
    root, knee, ankle, toe = Vector(spec.root), Vector(spec.knee), Vector(spec.foot), Vector(spec.toe)
    mid = leg_mid(spec)
    axis = (ankle - mid).normalized()
    bend = (knee - mid) - axis * (knee - mid).dot(axis)          # from the hip-ankle line to the knee
    pole = knee + bend.normalized() * 0.45
    return [
        BoneDef(f"{n}.coxa", tuple(root), tuple(mid), parent=parent),
        BoneDef(f"{n}.femur", tuple(mid), tuple(knee), parent=f"{n}.coxa", connect=True),
        BoneDef(f"{n}.tibia", tuple(knee), tuple(ankle), parent=f"{n}.femur", connect=True),
        BoneDef(f"{n}.ik", tuple(ankle), (toe.x, toe.y, toe.z + spec.radius * 0.36), parent="root"),
        BoneDef(f"{n}.pole", tuple(pole), tuple(pole + Vector((0, 0, 0.08))), parent=parent, deform=False),
    ]


def knee_error(rig, spec):
    bpy.context.view_layer.update()
    k = rig.matrix_world @ rig.pose.bones[f"leg.{spec.name}.femur"].tail
    return (k - Vector(spec.knee)).length


def apply_leg_ik(rig, specs):
    """IK (femur + tibia) to the foot bone with the pole above the knee.  The pole angle depends on
    each femur's roll, so it is fitted: the angle whose solved knee lands on the modelled knee."""
    errs = {}
    for spec in specs:
        n = f"leg.{spec.name}"
        c = salib.add_ik(rig, f"{n}.tibia", f"{n}.ik", chain=2, pole_bone=f"{n}.pole", pole_angle=0.0)
        best = (1e9, 0.0)
        for a in range(-180, 180, 2):
            c.pole_angle = math.radians(a)
            e = knee_error(rig, spec)
            if e < best[0]:
                best = (e, float(a))
        step = 1.0
        while step > 0.01:
            for a in (best[1] - step, best[1] + step):
                c.pole_angle = math.radians(a)
                e = knee_error(rig, spec)
                if e < best[0]:
                    best = (e, a)
            step *= 0.5
        c.pole_angle = math.radians(best[1])
        errs[spec.name] = (round(best[0], 5), round(best[1], 2))
    salib.log("leg IK rest knee error / fitted pole angle:", errs)
    worst = max(e for e, _ in errs.values())
    assert worst < 0.01, f"IK does not reproduce the modelled knees ({worst:.4f})"
    return errs


# ------------------------------------------------------------------------------------------------
# materials: smooth glossy chitin like the original portrait renders
# ------------------------------------------------------------------------------------------------
def ant_materials(neutral: bool):
    mats = salib.standard_materials("Y", neutral=neutral)
    base = salib.TEAM_COLORS["X" if neutral else "Y"]
    mats["M_Team"] = salib.material("M_Team", base, roughness=0.30, kind="chitin", tint=True, sss=0.06,
                                    variation=0.14, bump=0.05, dirt=0.22, cell_scale=5.0, scale=4.0)
    # neutral pirates: dark blue glossy eyes (portrait: black eye with a blue glint; sprite: dark-blue pixels)
    eye = (0.16, 0.27, 0.62) if neutral else (0.02, 0.02, 0.02)
    mats["M_Eye"] = salib.material("M_Eye", eye, roughness=0.06, kind="glossy")
    mats["M_Pack"] = salib.material("M_Pack", (0.70, 0.66, 0.61), roughness=0.60, kind="chitin", coat=0.10,
                                    variation=0.10, bump=0.05, dirt=0.30, cell_scale=4.0)
    # bazooka tube: painted gun-metal grey that reads light grey from above like the sprite's line
    # ("metal" would force metallic >= 0.8, which renders near-black in the game without reflections)
    mats["M_Accent"] = salib.material("M_Accent", (0.52, 0.53, 0.56), roughness=0.36, metallic=0.35, kind="glossy")
    mats["M_Black"] = salib.material("M_Black", (0.05, 0.05, 0.06), roughness=0.35, kind="chitin", coat=0.8, variation=0.15)
    # the grenade the grenadier throws: the original's dark slate blue (sprite 73,86,128 / 48,54,88)
    mats["M_Grenade"] = salib.material("M_Grenade", (0.27, 0.32, 0.52), roughness=0.32, kind="glossy")
    # bazooka back-blast: the sprite's hot pale yellow / orange flash, emissive so it glows in game
    mats["M_Flash"] = salib.material("M_Flash", (1.0, 0.86, 0.45), roughness=0.5, kind="emissive",
                                     emission=(1.0, 0.78, 0.32), emission_strength=2.5)
    return mats


# ------------------------------------------------------------------------------------------------
# leg animation: the scorpion crew's local replacements for salib.key_walk_cycle / key_death
# (copied from build_scorpion.py; key_walk keys frames 0..N for a seamless GLB loop and supports a
# per-leg stance offset).  salib.leg_bones() / this script's foot bones are not world-aligned, so a
# pose-bone `location` must be converted from armature space through the bone's rest matrix.
#   body / head bones point -Y:    local +X rotation pitches the front UP, loc +Y = forward, loc +Z = up
#   abdomen bone points +Y:        local +X rotation lifts the gaster tip
#   mandible bones:                local +Z rotation opens the left one outward (negate for the right)
# ------------------------------------------------------------------------------------------------
def ik_local(rig, bone_name, offset):
    m = rig.data.bones[bone_name].matrix_local.to_3x3()
    return tuple(m.inverted() @ Vector(offset))


def key_foot(clip, rig, spec, frame, offset):
    """Key a foot (IK target) by an ARMATURE-space offset from its rest position: +X = left,
    +Y = backwards (the ant faces -Y), +Z = up."""
    clip.key(f"leg.{spec.name}.ik", frame, loc=ik_local(rig, f"leg.{spec.name}.ik", offset))


def key_walk(clip, rig, specs, frames, stride, lift, body_bob=0.012):
    """Alternating-tripod walk keyed on every frame 0..frames (frame `frames` = frame 0): a planted
    foot moves straight back (+Y) at a constant rate for half the cycle - no sliding when the game
    plays the cycle at its nominal speed - then swings forward in an arc of height `lift`."""
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
        ph = (i / frames) * 2.0 * math.pi * 2.0      # two bobs per cycle (one per tripod step)
        clip.key("body", i, loc=(0, 0, body_bob * (0.5 - 0.5 * math.cos(ph))))


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


def key_feet_rest(clip, rig, specs, frames):
    for spec in specs:
        key_foot(clip, rig, spec, frames[0], (0, 0, 0))
        key_foot(clip, rig, spec, frames[1], (0, 0, 0))


def key_chain_rest(clip, specs, frame):
    """Hold the leg chains' FK channels at rest in every clip.  Blender's IK solver starts from the
    FK pose; without these keys a clip's bake inherits the previous clip's last baked rotations and
    the solver can land on the flipped-knee solution (seen: L1 / L3 knees at z 0.1-0.2 in attack)."""
    for spec in specs:
        for part in ("coxa", "femur", "tibia"):
            clip.key(f"leg.{spec.name}.{part}", frame, rot=(0, 0, 0))


def loop_from_zero(act, frames):
    """A looping clip keyed on 0..frames: frame range 0..frames so the bake and the GLB start at
    t = 0 and the last sample equals the first (Clip.finish() assumes frames 1..N)."""
    act.frame_range = (0, frames)
    act.use_frame_range = True
    return act


def from_zero(act, frames):
    """A one-shot clip keyed on 0..frames (the attack): the GLB clip starts at t = 0 on its first
    pose, which matters because the game restarts it at every shot."""
    act.frame_range = (0, frames)
    act.use_frame_range = True
    act.use_cyclic = False
    return act


# ------------------------------------------------------------------------------------------------
# attack helpers (attack crew)
# ------------------------------------------------------------------------------------------------
def hand_point(spec, s):
    """Where the right foreleg's claw holds the grenade: just past the toe tip and a little up."""
    ankle, toe = Vector(spec.foot), Vector(spec.toe)
    tip = Vector((toe.x, toe.y, toe.z + spec.radius * 0.36))
    d = (tip - ankle).normalized()
    return tip + d * (0.040 * s) + Vector((0, 0, 0.040 * s))


def add_copy_location(rig, bone, target, name):
    salib.select_only([rig])
    bpy.ops.object.mode_set(mode="POSE")
    c = rig.pose.bones[bone].constraints.new("COPY_LOCATION")
    c.name = name
    c.target = rig
    c.subtarget = target
    c.influence = 0.0
    bpy.ops.object.mode_set(mode="OBJECT")
    return c


def key_influence(con, frame, value):
    con.influence = value
    con.keyframe_insert("influence", frame=frame)


def key_bone_matrix(clip, rig, bone, frame, desired):
    """Key `bone` (loc + rot) so that - with its parent at rest - its armature-space matrix is
    `desired`; the bone follows its parent's animation on top of that."""
    basis = rig.data.bones[bone].matrix_local.inverted() @ desired
    loc, rot, _ = basis.decompose()
    clip.key(bone, frame, loc=tuple(loc), rot=tuple(math.degrees(a) for a in rot.to_euler("XYZ")))


def tube_pose(rig, rest_rear, rest_front, muzzle, axis):
    """Armature-space matrix of bone "bazooka" (head = rear, tail = front) with its tail (the
    muzzle) at `muzzle` and the tube along `axis` (minimal rotation from the rest direction)."""
    rest_rear, rest_front, muzzle, axis = (Vector(v) for v in (rest_rear, rest_front, muzzle, axis))
    axis.normalize()
    L = (rest_front - rest_rear).length
    q = (rest_front - rest_rear).normalized().rotation_difference(axis)
    new_rear = muzzle - axis * L
    return (Matrix.Translation(new_rear) @ q.to_matrix().to_4x4() @ Matrix.Translation(-rest_rear)
            @ rig.data.bones["bazooka"].matrix_local)


def ik_reach_report(rig, spec, offsets):
    """For a foot path given as armature-space offsets, the hip-to-ankle distance vs the leg's
    femur + tibia reach (min |f - t| .. max f + t): a key outside it would leave a gap."""
    mid, knee, ankle = leg_mid(spec), Vector(spec.knee), Vector(spec.foot)
    f, t = (knee - mid).length, (ankle - knee).length
    out = []
    for frame, off in offsets:
        d = (ankle + Vector(off) - mid).length
        out.append((frame, round(d, 3)))
    salib.log(f"{spec.name} reach {abs(f - t):.3f}..{f + t:.3f}: hip-ankle per key (body at rest)", out)


def key_attack_bite(c, rig, specs, s, n):
    """Soldier / Bull Ant bite (UNANTSO?_AT): starts and ends in the attack stance (lunged forward,
    mandibles half open) so back-to-back restarts read as continuous biting; the mandibles swing
    open into sickles (~40 deg each) and snap shut into the ring on the hit frame while the body
    lunges forward over its planted feet."""
    hit = ATTACK_HIT_FRAME["bite"]
    key_chain_rest(c, specs, 0)
    key_feet_rest(c, rig, specs, (0, n))
    # frame: body forward, up, pitch (front up), head pitch, mandible opening (deg, each side)
    poses = [
        (0, 0.045, 0.012, 3.0, 4.0, 20.0),
        (2, 0.005, 0.030, 7.0, 10.0, 40.0),
        (hit - 1, 0.015, 0.026, 6.0, 9.0, 41.0),
        (hit, 0.110, 0.000, -3.0, -9.0, -4.0),
        (hit + 1, 0.105, 0.000, -2.0, -7.0, 0.0),
        (hit + 3, 0.085, 0.004, 0.0, -3.0, 2.0),
        (hit + 5, 0.060, 0.008, 2.0, 2.0, 9.0),
        (n, 0.045, 0.012, 3.0, 4.0, 20.0),
    ]
    for f, fwd, up, pitch, head, mand in poses:
        c.key("body", f, loc=(0, fwd * s, up * s), rot=(pitch, 0, 0))
        c.key("head", f, rot=(head, 0, 0))
        c.key("mandible.L", f, rot=(0, 0, mand))
        c.key("mandible.R", f, rot=(0, 0, -mand))
    for f, (x, z) in ((0, (-14, 9)), (2, (-24, 15)), (hit, (-10, 7)), (n, (-14, 9))):
        c.key("antenna.L", f, rot=(x, 0, z))
        c.key("antenna.R", f, rot=(x, 0, -z))
    c.key("abdomen", 0, rot=(2, 0, 0)); c.key("abdomen", hit, rot=(-3, 0, 0)); c.key("abdomen", n, rot=(2, 0, 0))


def key_attack_throw(c, rig, specs, s, n, hold):
    """Grenadier / Pirate Grenadier throw (UNANTRG?_AT): the right foreleg lifts, takes the grenade
    out of the pack, cocks it up beside the head and swings it forward; the grenade is released on
    the hit frame (the game's projectile takes over: the held one shrinks away and goes back into
    the pack) and the leg plants again.  The other five feet stay planted."""
    hit = ATTACK_HIT_FRAME["grenade"]
    key_chain_rest(c, specs, 0)
    r1 = next(sp for sp in specs if sp.name == "R1")
    key_feet_rest(c, rig, [sp for sp in specs if sp.name != "R1"], (0, n))
    h0 = hand_point(r1, s)
    k = s / 0.88                                    # the grenadier sizes below are for x0.88

    def P(right, ahead, up):                        # unit frame (cells) -> armature space
        return Vector((-right * k, -ahead * k, up * k))

    # the claw (grenade) path: absolute targets in the unit's frame, or offsets from the rest.  The
    # foreleg is raised high (seen from above the original's raised leg is short: the grenade sits
    # only ~0.15 cell in front of the hip), so it stays well extended (hip-ankle 0.32-0.50 of its
    # 0.21-0.59 reach) and the knee bends out to the right like an elbow.
    path = [
        (0, Vector((0, 0, 0))),
        (2, Vector((0.0, 0.02 * k, 0.15 * k))),
        (3, P(0.46, 0.16, 0.38) - h0),               # swings up and out round the shoulder
        (4, P(0.28, 0.00, 0.50) - h0),               # at the pack's right side: grab
        (6, P(0.36, 0.04, 0.64) - h0),               # lifts it out
        (9, P(0.42, 0.12, 0.76) - h0),               # cocked high beside the head (sprite frame 1)
        (hit - 1, P(0.38, 0.26, 0.76) - h0),
        (hit, P(0.32, 0.38, 0.70) - h0),             # release (sprite frame 2 Launch Point)
        (hit + 2, P(0.40, 0.58, 0.40) - h0),         # follow-through
        (hit + 5, Vector((0.0, -0.03 * k, 0.10 * k))),
        (n - 1, Vector((0, 0, 0.012 * k))),
        (n, Vector((0, 0, 0))),
    ]
    for f, off in path:
        key_foot(c, rig, r1, f, tuple(off))
    ik_reach_report(rig, r1, [(f, tuple(o)) for f, o in path])
    # the knee bends towards its pole (it rides with the body; at rest above the knee): while the
    # leg is raised the pole sits out to the right of the hip, so the knee points out like an elbow
    pole = "leg.R1.pole"
    p0 = rig.data.bones[pole].head_local
    out = P(0.78, 0.16, 0.36) - p0
    for f, off in ((0, Vector()), (2, out * 0.5), (4, out), (hit + 2, out), (hit + 5, out * 0.4), (n, Vector())):
        c.key(pole, f, loc=ik_local(rig, pole, tuple(off)))
    # the grenade: inside the pack -> pulled into the claw -> released (shrinks) -> back in the pack
    # (shown in the claw on the release frame like the original's frame 2, gone one frame later)
    for f, infl in ((0, 0.0), (4, 0.0), (6, 1.0), (hit + 1, 1.0), (hit + 2, 0.0), (n, 0.0)):
        key_influence(hold, f, infl)
    for f, sc in ((0, 1.0), (hit, 1.0), (hit + 1, 0.02), (hit + 2, 0.02), (hit + 3, 1.0), (n, 1.0)):
        c.key("grenade", f, scale=(sc, sc, sc))
    # body: lean back while cocking (weight off the throwing side), then into the throw
    for f, fwd, up, pitch, roll in ((0, 0, 0, 0, 0), (4, -0.010, 0.012, 2.0, -1.5), (9, -0.030, 0.030, 5.0, -3.0),
                                    (hit, 0.070, 0.005, -5.0, -1.0), (hit + 3, 0.045, 0.0, -2.0, 0.0), (n, 0, 0, 0, 0)):
        c.key("body", f, loc=(0, fwd * s, up * s), rot=(pitch, roll, 0))
    for f, ang in ((0, 0), (9, 7), (hit, -5), (n, 0)):
        c.key("head", f, rot=(ang, 0, 0))
    for f, ang in ((0, 0), (9, -5), (hit, 6), (n, 0)):
        c.key("abdomen", f, rot=(ang, 0, 0))
    for sgn, b in ((1, "mandible.L"), (-1, "mandible.R")):
        c.key(b, 0, rot=(0, 0, 0)); c.key(b, 9, rot=(0, 0, 14 * sgn)); c.key(b, hit + 1, rot=(0, 0, 0)); c.key(b, n, rot=(0, 0, 0))
    for sgn, b in ((1, "antenna.L"), (-1, "antenna.R")):
        c.key(b, 0, rot=(0, 0, 0)); c.key(b, 9, rot=(-18, 0, 10 * sgn)); c.key(b, hit + 2, rot=(6, 0, -4 * sgn)); c.key(b, n, rot=(0, 0, 0))


def key_attack_bazooka(c, rig, specs, s, n, V):
    """Bazooka shot (UNANTBZ?_AT): the tube swings from the back onto the right shoulder, parallel
    to the body and pointing ahead; the ant stands up taller (feet planted, legs drawn in under the
    raised body), fires on the hit frame with a back-blast flash from the breech and a recoil
    kick, then lowers the tube onto its back again."""
    hit = ATTACK_HIT_FRAME["bazooka"]
    key_chain_rest(c, specs, 0)
    key_feet_rest(c, rig, specs, (0, n))
    rear, front = BAZOOKA_REST(V)
    k = s / 0.91                                    # the bazooka sizes below are for x0.91

    def P(right, ahead, up):
        return Vector((-right * k, -ahead * k, up * k))

    def axis(elev):
        e = math.radians(elev)
        return Vector((0.0, -math.cos(e), math.sin(e)))

    rest = rig.data.bones["bazooka"].matrix_local.copy()
    shoulder = tube_pose(rig, rear, front, P(0.25, 0.44, 0.47), axis(3.0))
    kick = tube_pose(rig, rear, front, P(0.25, 0.37, 0.49), axis(9.0))
    kick2 = tube_pose(rig, rear, front, P(0.25, 0.40, 0.48), axis(6.0))
    # aimed and steady on the fire frame (the rocket leaves the muzzle there), the kick follows
    for f, m in ((0, rest), (2, rest.lerp(shoulder, 0.35)), (5, shoulder), (hit, shoulder), (hit + 1, kick),
                 (hit + 2, kick2), (hit + 4, shoulder), (n - 1, rest.lerp(shoulder, 0.15)), (n, rest)):
        key_bone_matrix(c, rig, "bazooka", f, m)
    for f, sc in ((0, 1.0), (hit - 1, 1.0), (hit, FLASH_GROW), (hit + 1, FLASH_GROW * 1.15), (hit + 2, FLASH_GROW * 0.55),
                  (hit + 3, 1.0), (n, 1.0)):
        c.key("flash", f, scale=(sc, sc, sc))
    # stand up taller (legs drawn in under the body), brace, recoil back, settle
    for f, fwd, up, pitch in ((0, 0, 0, 0), (4, 0.0, 0.060, 1.5), (hit - 1, 0.005, 0.070, 2.0), (hit, 0.005, 0.070, 2.5),
                              (hit + 1, -0.040, 0.066, 4.5), (hit + 2, -0.036, 0.065, 3.8), (hit + 4, -0.015, 0.060, 2.0),
                              (n, 0, 0, 0)):
        c.key("body", f, loc=(0, fwd * s, up * s), rot=(pitch, 0, 0))
    for f, ang in ((0, 0), (5, 3), (hit + 1, 7), (hit + 4, 2), (n, 0)):
        c.key("head", f, rot=(ang, 0, 0))
    for f, ang in ((0, 0), (hit + 1, -4), (n, 0)):
        c.key("abdomen", f, rot=(ang, 0, 0))
    for sgn, b in ((1, "antenna.L"), (-1, "antenna.R")):
        c.key(b, 0, rot=(0, 0, 0)); c.key(b, 5, rot=(-12, 0, 6 * sgn)); c.key(b, hit + 1, rot=(-24, 0, 14 * sgn)); c.key(b, n, rot=(0, 0, 0))


# ------------------------------------------------------------------------------------------------
def build(variant: str):
    cfg = VARIANTS[variant]
    salib.reset_scene(variant)
    mats = ant_materials(cfg["neutral"])
    body = Body(variant, mats)
    T = "M_Team"
    s = cfg["scale"]
    ys = cfg["yshift"]

    def V(x, y, z):
        return (x * s, (y + ys) * s, z * s)

    def VS(pts):
        return [V(*p) for p in pts]

    def R(r):
        return r * s

    def sc3(v):
        return (v[0] * s, v[1] * s, v[2] * s)

    # ---- body segments (sizes from the sprite / portrait, see module docstring) ------------------
    body.sphere("abdomen", T, V(0, 0.60, 0.33), R(1.0), scale=sc3((0.25, 0.265, 0.235)), segments=12, rings=8)   # gaster
    body.sphere("body", T, V(0, 0.37, 0.26), R(0.058), segments=8, rings=5)                                       # petiole
    body.sphere("body", T, V(0, 0.26, 0.30), R(1.0), scale=sc3((0.105, 0.10, 0.105)), segments=10, rings=6)      # propodeum
    body.sphere("body", T, V(0, 0.11, 0.33), R(1.0), scale=sc3((0.145, 0.19, 0.15)), segments=12, rings=8)       # mesonotum
    body.sphere("body", T, V(0, -0.02, 0.33), R(1.0), scale=sc3((0.135, 0.13, 0.13)), segments=10, rings=6)      # pronotum
    body.sphere("body", T, V(0, -0.10, 0.32), R(0.07), segments=8, rings=5)                                       # neck
    body.sphere("head", T, V(0, -0.255, 0.33), R(1.0), scale=sc3((0.21, 0.18, 0.17)), segments=12, rings=8)      # head
    for side in (+1, -1):
        body.sphere("head", "M_Eye", V(side * 0.19, -0.30, 0.38), R(0.06), segments=8, rings=5)
        mb = "mandible.L" if side > 0 else "mandible.R"
        if cfg["ring"]:
            pts, radii = ring_mandible_points(side, cfg["mandible"])
            tube(body, mb, T, VS(pts), [R(r) for r in radii], sides=8, flat=(1.0, 0.8))
        else:
            pts, radii = pincer_points(side)
            tube(body, mb, T, VS(pts), [R(r) for r in radii], sides=7)
        antenna_mesh(body, "antenna.L" if side > 0 else "antenna.R", T, side, V, R, thick=1.0 if cfg["ring"] else 1.6)

    # ---- legs ----------------------------------------------------------------------------------
    specs = leg_specs(s, ys)
    for spec in specs:
        leg_mesh(body, spec, T)

    # ---- weapons -------------------------------------------------------------------------------
    if cfg["weapon"] == "grenade":
        # light-grey rounded pack on the thorax right behind the head (sprite: a plain light-grey
        # 6-7 px oval; portrait: a pillow-like grey block, no visible launcher)
        pack = body.cube("body", "M_Pack", V(0.0, 0.11, 0.50), size=sc3((0.30, 0.31, 0.22)))
        pack["sa_bevel"] = R(0.075)                                                            # pillow-like
        # the grenade (sprite: a ~3 px dark-blue ball): at rest it sits hidden inside the pack; the
        # attack clip pulls it out into the right foreleg's claw (bone "grenade", see key_attack_throw)
        g = body.sphere("grenade", "M_Grenade", GRENADE_REST(V), R(GRENADE_R), scale=(1.0, 1.12, 0.94), segments=10, rings=7)
        g["sa_no_subdiv"] = True
    elif cfg["weapon"] == "bazooka":
        # thin dark tube over the back: rear over the gaster's LEFT (+X), muzzle past the head's RIGHT
        # (sprite UNANTBZ facing up: the tube runs from the lower-left to the upper-right).  The tube
        # is its own bone ("bazooka"): the attack clip shoulders it on the right side.
        rear, front = (Vector(p) for p in BAZOOKA_REST(V))
        d = (front - rear).normalized()
        tube(body, "bazooka", "M_Accent", [tuple(rear), tuple(front - d * R(0.07))], [R(0.034), R(0.034)], sides=10)
        tube(body, "bazooka", "M_Black", [tuple(front - d * R(0.08)), tuple(front)], [R(0.052), R(0.046)], sides=10)   # muzzle
        tube(body, "bazooka", "M_Black", [tuple(rear - d * R(0.02)), tuple(rear + d * R(0.12))], [R(0.048), R(0.046)], sides=10)  # breech
        # two short mounting feet under the tube (rest on the back; grips when it is shouldered)
        for u in (0.26, 0.62):
            top = rear.lerp(front, u)
            tube(body, "bazooka", "M_Accent", [tuple(top + Vector((0, 0, -R(0.095)))), tuple(top)], [R(0.022), R(0.02)], sides=6)
        # back-blast flash at the breech: modelled at 1/FLASH_GROW size so it hides inside the breech
        # cap; the attack clip scales bone "flash" up by FLASH_GROW for a few frames when it fires
        h = FLASH_HEAD(rear, d, R)
        k = 1.0 / FLASH_GROW
        tube(body, "flash", "M_Flash", [tuple(h - d * R(t) * k) for t in (-0.005, 0.07, 0.17, 0.225)],
             [R(0.036) * k, R(0.060) * k, R(0.046) * k, R(0.010) * k], sides=8)

    mesh = body.join()

    # ---- rig -----------------------------------------------------------------------------------
    bones = [
        BoneDef("root", (0, 0, 0), (0, 0.25 * s, 0)),
        BoneDef("body", V(0, 0.33, 0.32), V(0, -0.09, 0.32), parent="root"),
        BoneDef("abdomen", V(0, 0.33, 0.30), V(0, 0.88, 0.33), parent="body"),
        BoneDef("head", V(0, -0.09, 0.32), V(0, -0.45, 0.32), parent="body"),
        BoneDef("mandible.L", V(0.15, -0.37, 0.28), V(0.02, -0.37 - 0.40 * cfg["mandible"], 0.25), parent="head"),
        BoneDef("mandible.R", V(-0.15, -0.37, 0.28), V(-0.02, -0.37 - 0.40 * cfg["mandible"], 0.25), parent="head"),
        BoneDef("antenna.L", V(*ANTENNA["base"]), V(*ANTENNA["tip"]), parent="head"),
        BoneDef("antenna.R", V(-ANTENNA["base"][0], *ANTENNA["base"][1:]), V(-ANTENNA["tip"][0], *ANTENNA["tip"][1:]), parent="head"),
    ]
    for spec in specs:
        bones += leg_bones(spec, parent="body")
    if cfg["weapon"] == "grenade":
        gp = Vector(GRENADE_REST(V))
        bones.append(BoneDef("grenade", tuple(gp), tuple(gp + Vector((0, 0, R(0.10)))), parent="body"))
        hp = hand_point(next(sp for sp in specs if sp.name == "R1"), s)
        bones.append(BoneDef("hand.R1", tuple(hp), tuple(hp + Vector((0, 0, R(0.06)))), parent="leg.R1.ik", deform=False))
    elif cfg["weapon"] == "bazooka":
        rear, front = (Vector(p) for p in BAZOOKA_REST(V))
        d = (front - rear).normalized()
        h = FLASH_HEAD(rear, d, R)
        bones.append(BoneDef("bazooka", tuple(rear), tuple(front), parent="body"))
        bones.append(BoneDef("flash", tuple(h), tuple(h - d * R(0.12)), parent="bazooka"))
    rig = salib.build_armature("Rig", bones)
    salib.skin(mesh, rig)
    apply_leg_ik(rig, specs)
    # the held grenade follows the right foreleg's claw while the attack clip says so
    hold = add_copy_location(rig, "grenade", "hand.R1", "GrenadeHold") if cfg["weapon"] == "grenade" else None

    # ---- animations ----------------------------------------------------------------------------
    clips = []
    # idle: 1.2 s loop (frames 0..36) - breathing gaster, antennae feel around, mandibles twitch
    c = Clip(rig, "idle", 36)
    key_chain_rest(c, specs, 0)
    key_feet_rest(c, rig, specs, (0, 36))
    if hold:
        key_influence(hold, 0, 0.0)                 # grenade stays in the pack
    c.key("body", 0, loc=(0, 0, 0)); c.key("body", 18, loc=(0, 0, 0.010 * s)); c.key("body", 36, loc=(0, 0, 0))
    c.key("abdomen", 0, rot=(0, 0, 0)); c.key("abdomen", 18, rot=(3, 0, 0)); c.key("abdomen", 36, rot=(0, 0, 0))
    c.key("head", 0, rot=(0, 0, 0)); c.key("head", 14, rot=(2, 0, 4)); c.key("head", 26, rot=(-1, 0, -3)); c.key("head", 36, rot=(0, 0, 0))
    for sgn, b in ((1, "antenna.L"), (-1, "antenna.R")):
        c.key(b, 0, rot=(0, 0, 0)); c.key(b, 10, rot=(10, 0, 8 * sgn)); c.key(b, 22, rot=(-6, 0, -7 * sgn)); c.key(b, 36, rot=(0, 0, 0))
    open_idle = 5 if cfg["ring"] else 8
    for sgn, b in ((1, "mandible.L"), (-1, "mandible.R")):
        c.key(b, 0, rot=(0, 0, 0)); c.key(b, 12, rot=(0, 0, open_idle * sgn)); c.key(b, 20, rot=(0, 0, 0)); c.key(b, 36, rot=(0, 0, 0))
    clips.append(loop_from_zero(c.finish(), 36))

    # move: alternating tripod, 8 frames (0..8), stride matched to the game's playback speed
    n = MOVE_FRAMES
    stride = 1.25 * n / salib.FPS / cfg["game_scale"]
    c = Clip(rig, "move", n)
    key_chain_rest(c, specs, 0)
    if hold:
        key_influence(hold, 0, 0.0)
    key_walk(c, rig, specs, n, stride=stride, lift=MOVE_LIFT * s, body_bob=0.010 * s)
    for f, ang in ((0, 0), (n // 4, 2.5), (n // 2, 0), (3 * n // 4, -2.5), (n, 0)):
        c.key("head", f, rot=(0, 0, ang))
        c.key("abdomen", f, rot=(0, 0, -ang * 0.8))
        c.key("antenna.L", f, rot=(ang * 2.0, 0, 0))
        c.key("antenna.R", f, rot=(-ang * 2.0, 0, 0))
    clips.append(loop_from_zero(c.finish(), n))

    # attack (frames 0..n, see ATTACK_HIT_FRAME and the module docstring)
    n = cfg["attack_frames"]
    c = Clip(rig, "attack", n, loop=False)
    if cfg["weapon"] is None:
        key_attack_bite(c, rig, specs, s, n)
    elif cfg["weapon"] == "grenade":
        key_attack_throw(c, rig, specs, s, n, hold)
    else:
        key_attack_bazooka(c, rig, specs, s, n, V)
    c.finish()
    clips.append(from_zero(c.action, n))

    # death (1.2 s, frames 1..36): the legs give way and splay out flat on the ground while the
    # body drops onto it (DEATH sprite: flattened, legs splayed to both sides); mandibles fall
    # open, antennae droop, the gaster sags
    c = Clip(rig, "death", 36, loop=False)
    key_chain_rest(c, specs, 1)
    if hold:
        key_influence(hold, 1, 0.0)
    key_death_splay(c, rig, specs, 36, sink=0.115 * s, splay=0.24 * s, roll_deg=5.0)
    c.key("head", 1, rot=(0, 0, 0)); c.key("head", 36, rot=(-10, 0, 8))
    c.key("abdomen", 1, rot=(0, 0, 0)); c.key("abdomen", 36, rot=(8, 0, -6))
    open_death = 40 if cfg["ring"] else 25
    for sgn, b in ((1, "mandible.L"), (-1, "mandible.R")):
        c.key(b, 1, rot=(0, 0, 0)); c.key(b, 36, rot=(0, 0, open_death * sgn))
    for sgn, b in ((1, "antenna.L"), (-1, "antenna.R")):
        c.key(b, 1, rot=(0, 0, 0)); c.key(b, 36, rot=(30, 0, 25 * sgn))
    clips.append(c.finish())

    salib.bake_actions(rig, clips)

    # ---- export, previews, save --------------------------------------------------------------------
    path, summary = salib.finalize_asset(variant, [rig, mesh], preview_radius=2.9 * s, preview_center=(0, 0, 0.28 * s),
                                         views=("front", "back", "left", "right", "threequarter", "top"))
    names = sorted(a["name"] for a in summary["animations"])
    assert names == ["attack", "death", "idle", "move"], names
    assert "M_Team" in summary["materials"]
    tris = sum(len(p.vertices) - 2 for p in mesh.data.polygons)
    salib.log(f"{variant}: {len(mesh.data.vertices)} verts, ~{tris} triangles")
    assert tris < 8000, f"{variant}: {tris} triangles exceed the 8k budget"
    return path


if __name__ == "__main__":
    flags = [a for a in salib.script_args() if a.startswith("-")]
    args = [a for a in salib.script_args() if not a.startswith("-")] or (list(VARIANTS) if "--all" in flags else ["ant_soldier"])
    for v in args:
        if v not in VARIANTS:
            raise SystemExit(f"unknown variant {v}; choose from {list(VARIANTS)}")
        build(v)
        print("BUILT", v, flush=True)
