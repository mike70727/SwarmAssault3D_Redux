"""Builds the scorpion family: Savage, Spear Gun, Ninja.

References: Quick_References/Units/Scorpion_* (UNSCOSA*, UNSCOSG*, UNSCOST* + portraits).
* Savage: team-coloured scorpion, two big claws, eight legs, segmented tail arching over the body
  with an orange sting.
* Spear Gun: same body, the tail carries a brown harpoon gun instead of the sting.
* Ninja: dark legs/claws (the sprites use the dark palette), team-coloured body, the tail ends in a
  light grey ninja-star launcher.
Inferred: segment counts (5 tail segments, 3-joint legs, 3-joint claws) and the underside.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import salib  # noqa: E402
from salib import BoneDef, Body, Clip, LegSpec  # noqa: E402
from mathutils import Vector  # noqa: E402

VARIANTS = {
    "scorpion_savage": dict(kind="savage"),
    "scorpion_spear_gun": dict(kind="spear"),
    "scorpion_ninja": dict(kind="ninja"),
}

TAIL = [(0, 0.42, 0.26), (0, 0.66, 0.40), (0, 0.80, 0.64), (0, 0.76, 0.90), (0, 0.58, 1.08), (0, 0.36, 1.12)]


def leg_specs():
    base = [
        ("L1", (0.18, -0.22, 0.22), (0.46, -0.44, 0.40), (0.56, -0.62, 0.0), 0.0),
        ("L2", (0.20, -0.08, 0.22), (0.56, -0.16, 0.42), (0.74, -0.18, 0.0), 0.5),
        ("L3", (0.20, 0.06, 0.22), (0.56, 0.16, 0.42), (0.74, 0.22, 0.0), 0.0),
        ("L4", (0.18, 0.20, 0.22), (0.46, 0.42, 0.40), (0.56, 0.62, 0.0), 0.5),
    ]
    specs = []
    for name, root, knee, foot, phase in base:
        m = lambda p: (-p[0], p[1], p[2])
        specs.append(LegSpec(name, +1, root, knee, foot, phase=phase, radius=0.03))
        specs.append(LegSpec("R" + name[1:], -1, m(root), m(knee), m(foot), phase=(phase + 0.5) % 1.0, radius=0.03))
    return specs


def claw_points(s):
    return {
        "shoulder": (s * 0.20, -0.30, 0.26),
        "elbow": (s * 0.50, -0.58, 0.26),
        "hand": (s * 0.40, -0.90, 0.26),
        "fixed_tip": (s * 0.22, -1.18, 0.26),
        "finger_tip": (s * 0.52, -1.16, 0.26),
    }


def build(variant: str):
    kind = VARIANTS[variant]["kind"]
    salib.reset_scene(variant)
    mats = salib.standard_materials("Y")
    mats["M_Sting"] = salib.material("M_Sting", (0.95, 0.45, 0.10), roughness=0.4, emission=(0.9, 0.4, 0.1), emission_strength=0.6, kind="glossy")
    mats["M_Brown"] = salib.material("M_Brown", (0.42, 0.28, 0.16), roughness=0.8, kind="wood")
    mats["M_Star"] = salib.material("M_Star", (0.80, 0.84, 0.92), roughness=0.3, metallic=0.7, kind="metal")
    body = Body(variant, mats)
    T, D = "M_Team", "M_Dark"
    limb_mat = "M_Black" if kind == "ninja" else T

    # prosoma + 3 mesosoma plates
    body.sphere("body", T, (0, -0.12, 0.26), 0.26, scale=(1.05, 1.1, 0.7), segments=18, rings=12)
    for i, y in enumerate((0.12, 0.28, 0.42)):
        body.sphere("body", T, (0, y, 0.25), 0.22 - i * 0.03, scale=(1.0, 0.9, 0.65), segments=16, rings=10)
    for s in (+1, -1):
        body.sphere("body", "M_Eye", (s * 0.06, -0.32, 0.40), 0.03, segments=8, rings=5)
    # tail segments
    for i in range(5):
        a, b = Vector(TAIL[i]), Vector(TAIL[i + 1])
        r = 0.11 - i * 0.012
        body.sphere(f"tail.{i + 1}", T, tuple(a), r * 1.05, segments=12, rings=8)
        body.segment(f"tail.{i + 1}", T, tuple(a), tuple(b), r, r * 0.85)
    tip = Vector(TAIL[5])
    if kind == "savage":
        body.sphere("sting", T, tuple(tip), 0.085, segments=12, rings=8)
        body.segment("sting", "M_Sting", tuple(tip), (0, 0.18, 0.95), 0.06, 0.005)
    elif kind == "spear":
        body.cube("sting", "M_Brown", (0, 0.30, 1.10), size=(0.16, 0.34, 0.14))
        body.cylinder("sting", "M_Accent", (0, 0.02, 1.12), 0.03, 0.55, rot=(math.radians(90), 0, 0))
        body.cone("sting", "M_Accent", (0, -0.30, 1.12), 0.05, 0.0, 0.12, rot=(math.radians(-90), 0, 0), verts=8)
    else:
        body.cylinder("sting", "M_Star", (0, 0.30, 1.10), 0.12, 0.08, verts=16, rot=(math.radians(90), 0, 0))
        body.cylinder("sting", D, (0, 0.30, 1.10), 0.05, 0.14, verts=10, rot=(math.radians(90), 0, 0))
        for k in range(4):
            ang = k * math.pi / 2 + math.pi / 4
            body.cone("sting", "M_Star", (0.18 * math.cos(ang), 0.18, 1.10 + 0.18 * math.sin(ang)), 0.03, 0.0, 0.12, rot=(0, -ang + math.pi / 2, 0), verts=4)
    # claws
    for s in (+1, -1):
        p = claw_points(s)
        side = "L" if s > 0 else "R"
        body.segment(f"claw.{side}.arm", limb_mat, p["shoulder"], p["elbow"], 0.06, 0.055)
        body.sphere(f"claw.{side}.arm", limb_mat, p["elbow"], 0.06, segments=10, rings=6)
        body.segment(f"claw.{side}.fore", limb_mat, p["elbow"], p["hand"], 0.055, 0.07)
        body.sphere(f"claw.{side}.hand", limb_mat, p["hand"], 0.10, scale=(1.0, 1.1, 0.7), segments=12, rings=8)
        body.segment(f"claw.{side}.hand", limb_mat, p["hand"], p["fixed_tip"], 0.055, 0.012)
        body.segment(f"claw.{side}.finger", limb_mat, p["hand"], p["finger_tip"], 0.05, 0.012)
    specs = leg_specs()
    for spec in specs:
        salib.leg_mesh(body, spec, mat=limb_mat, tip_mat=D)
    mesh = body.join()

    bones = [
        BoneDef("root", (0, 0, 0), (0, 0.25, 0)),
        BoneDef("body", (0, 0.42, 0.26), (0, -0.30, 0.26), parent="root"),
    ]
    for i in range(5):
        bones.append(BoneDef(f"tail.{i + 1}", TAIL[i], TAIL[i + 1], parent="body" if i == 0 else f"tail.{i}", connect=i > 0))
    bones.append(BoneDef("sting", TAIL[5], (0, 0.15, 0.95), parent="tail.5", connect=True))
    for s in (+1, -1):
        p = claw_points(s)
        side = "L" if s > 0 else "R"
        bones += [
            BoneDef(f"claw.{side}.arm", p["shoulder"], p["elbow"], parent="body"),
            BoneDef(f"claw.{side}.fore", p["elbow"], p["hand"], parent=f"claw.{side}.arm", connect=True),
            BoneDef(f"claw.{side}.hand", p["hand"], p["fixed_tip"], parent=f"claw.{side}.fore", connect=True),
            BoneDef(f"claw.{side}.finger", p["hand"], p["finger_tip"], parent=f"claw.{side}.fore"),
        ]
    for spec in specs:
        bones += salib.leg_bones(spec, parent="body")
    rig = salib.build_armature("Rig", bones)
    salib.skin(mesh, rig)
    salib.apply_leg_ik(rig, specs)

    def key_claws(c, f, open_deg):
        c.key("claw.L.finger", f, rot=(0, 0, open_deg))
        c.key("claw.R.finger", f, rot=(0, 0, -open_deg))

    def key_tail(c, f, bend_deg, sway_deg=0.0):
        for i in range(1, 6):
            c.key(f"tail.{i}", f, rot=(bend_deg, 0, sway_deg))

    clips = []
    c = Clip(rig, "idle", 48)
    salib.key_idle(c, specs, 48, body_bob=0.01)
    for f, sw in ((1, 0), (12, 4), (24, 0), (36, -4), (48, 0)):
        key_tail(c, f, 0, sw)
    for f, o in ((1, 0), (16, 14), (32, 0), (48, 0)):
        key_claws(c, f, o)
    clips.append(c.finish())
    c = Clip(rig, "move", 18)
    salib.key_walk_cycle(c, specs, 18, stride=0.26, lift=0.10, body_bob=0.015)
    for f, b in ((1, 0), (9, 3), (18, 0)):
        key_tail(c, f, b)
    key_claws(c, 1, 6); key_claws(c, 18, 6)
    clips.append(c.finish())
    c = Clip(rig, "attack", 14, loop=False)
    for spec in specs:
        c.key(f"leg.{spec.name}.ik", 1, loc=(0, 0, 0))
        c.key(f"leg.{spec.name}.ik", 14, loc=(0, 0, 0))
    if kind == "savage":
        # tail whips forward over the head, claws snap shut
        key_tail(c, 1, 0); key_tail(c, 3, -8); key_tail(c, 6, 32); key_tail(c, 14, 0)
        key_claws(c, 1, 0); key_claws(c, 3, 30); key_claws(c, 6, -5); key_claws(c, 14, 0)
        c.key("body", 1, loc=(0, 0, 0), rot=(0, 0, 0)); c.key("body", 6, loc=(0, -0.08, 0), rot=(6, 0, 0)); c.key("body", 14, loc=(0, 0, 0), rot=(0, 0, 0))
    else:
        # ranged: the tail weapon aims forward, recoils
        key_tail(c, 1, 0); key_tail(c, 2, 10); key_tail(c, 4, -6); key_tail(c, 14, 0)
        c.key("sting", 1, loc=(0, 0, 0)); c.key("sting", 2, loc=(0, -0.10, 0)); c.key("sting", 14, loc=(0, 0, 0))
    clips.append(c.finish())
    c = Clip(rig, "death", 36, loop=False)
    salib.key_death(c, specs, 36, fall_axis_deg=(0, 0, 0), sink=0.12)
    key_tail(c, 1, 0); key_tail(c, 36, -22, 10)
    key_claws(c, 1, 0); key_claws(c, 36, 25)
    c.key("claw.L.arm", 1, rot=(0, 0, 0)); c.key("claw.L.arm", 36, rot=(0, 0, 25))
    c.key("claw.R.arm", 1, rot=(0, 0, 0)); c.key("claw.R.arm", 36, rot=(0, 0, -25))
    clips.append(c.finish())
    salib.bake_actions(rig, clips)

    path, s = salib.finalize_asset(variant, [rig, mesh], preview_radius=3.4, preview_center=(0, 0, 0.45))
    assert sorted(a["name"] for a in s["animations"]) == ["attack", "death", "idle", "move"]
    return path


if __name__ == "__main__":
    args = [a for a in salib.script_args() if not a.startswith("-")] or list(VARIANTS)
    for v in args:
        build(v)
        print("BUILT", v, flush=True)
