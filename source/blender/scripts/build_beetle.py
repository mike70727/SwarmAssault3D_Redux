"""Builds the beetle family: Lady Bug, Shrapnel, Cannon.

References: Quick_References/Units/Beetle_* (sprites UNBETLB*, UNBETSH*, UNBETCA* and portraits).
* Lady Bug: team-coloured dome shell with ~7 black spots, small black head, short legs mostly hidden.
* Shrapnel: team-coloured dome with a black Y/arrow pattern, a grey launcher cylinder on top, long legs.
* Cannon: elongated ground-beetle body, long team-coloured elytra, black thorax/head, long legs and a
  grey cannon tube lying along the back with the barrel pointing forward.
Inferred: leg joints (3 per leg), underside, antennae; the sprites only show the shell from above.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import salib  # noqa: E402
from salib import BoneDef, Body, Clip, LegSpec  # noqa: E402

VARIANTS = {
    "beetle_ladybug": dict(kind="ladybug"),
    "beetle_shrapnel": dict(kind="shrapnel"),
    "beetle_cannon": dict(kind="cannon"),
}


def leg_specs(long_legs: bool, length_scale=1.0):
    k = 1.0 if long_legs else 0.72
    base = [
        ("L1", (0.16, -0.26, 0.22), (0.46 * k, -0.52 * k, 0.42), (0.58 * k, -0.70 * k, 0.0), 0.0),
        ("L2", (0.20, -0.02, 0.22), (0.60 * k, 0.00, 0.44), (0.80 * k, 0.04, 0.0), 0.5),
        ("L3", (0.17, 0.24, 0.22), (0.50 * k, 0.48 * k, 0.42), (0.62 * k, 0.72 * k, 0.0), 0.0),
    ]
    specs = []
    for name, root, knee, foot, phase in base:
        root = (root[0], root[1] * length_scale, root[2])
        knee = (knee[0], knee[1] * length_scale, knee[2])
        foot = (foot[0], foot[1] * length_scale, foot[2])
        m = lambda p: (-p[0], p[1], p[2])
        specs.append(LegSpec(name, +1, root, knee, foot, phase=phase, radius=0.03))
        specs.append(LegSpec("R" + name[1:], -1, m(root), m(knee), m(foot), phase=(phase + 0.5) % 1.0, radius=0.03))
    return specs


def build(variant: str):
    kind = VARIANTS[variant]["kind"]
    salib.reset_scene(variant)
    mats = salib.standard_materials("Y")
    body = Body(variant, mats)
    T, D = "M_Team", "M_Black"
    long_legs = kind != "ladybug"
    length_scale = 1.35 if kind == "cannon" else 1.0

    if kind == "cannon":
        # elongated elytra + narrow pronotum, dark head
        body.sphere("body", T, (0, 0.18, 0.30), 0.30, scale=(0.95, 1.9, 0.72), segments=22, rings=14)   # elytra
        body.sphere("body", D, (0, -0.42, 0.28), 0.20, scale=(0.9, 1.0, 0.75), segments=16, rings=10)   # pronotum
        body.sphere("head", D, (0, -0.68, 0.26), 0.15, scale=(1.0, 1.1, 0.8), segments=14, rings=8)
        # cannon: mount box + long barrel pointing forward over the head
        body.cube("cannon", "M_Accent", (0.0, -0.05, 0.60), size=(0.22, 0.34, 0.18))
        body.cylinder("cannon", "M_Accent", (0.0, -0.75, 0.62), 0.06, 1.3, rot=(math.radians(90), 0, 0))
        body.cylinder("cannon", D, (0.0, -1.38, 0.62), 0.075, 0.08, rot=(math.radians(90), 0, 0))
    else:
        # dome shell on a flat underside
        body.sphere("body", T, (0, 0.05, 0.22), 0.46, scale=(1.0, 1.18, 0.62), segments=24, rings=14)
        body.cylinder("body", D, (0, 0.05, 0.12), 0.40, 0.08, verts=24, scale=(1.0, 1.18, 1.0))
        body.sphere("head", D, (0, -0.52, 0.18), 0.14, scale=(1.1, 0.9, 0.8), segments=14, rings=8)
        if kind == "ladybug":
            # spots: flattened dark spheres pushed into the shell surface (positions from the sprite)
            for (x, y) in [(0.0, -0.18), (0.22, -0.10), (-0.22, -0.10), (0.26, 0.20), (-0.26, 0.20), (0.10, 0.42), (-0.10, 0.42)]:
                z = 0.22 + 0.62 * 0.46 * math.sqrt(max(0.0, 1 - (x / 0.46) ** 2 - (y / 0.54) ** 2))
                body.sphere("body", D, (x, y + 0.05, z - 0.02), 0.075, scale=(1.0, 1.0, 0.35), segments=10, rings=6)
            # centre seam between the elytra
            body.cube("body", D, (0.0, 0.14, 0.50), size=(0.02, 0.8, 0.02))
        else:
            # Y-shaped dark marking + grey launcher on top
            body.cube("body", D, (0.0, 0.28, 0.46), size=(0.07, 0.42, 0.04))
            for s in (+1, -1):
                body.cube("body", D, (s * 0.13, -0.04, 0.47), size=(0.07, 0.34, 0.04), rot=(0, 0, s * math.radians(35)))
            body.cylinder("launcher", "M_Accent", (0.0, 0.02, 0.56), 0.11, 0.18, verts=16)
            body.cylinder("launcher", D, (0.0, 0.02, 0.66), 0.08, 0.04, verts=16)
    # eyes + antennae
    for s in (+1, -1):
        hy = -0.74 if kind == "cannon" else -0.60
        hz = 0.30 if kind == "cannon" else 0.22
        body.sphere("head", "M_Eye", (s * 0.09, hy, hz + 0.02), 0.035, segments=8, rings=5)
        ab = "antenna.L" if s > 0 else "antenna.R"
        body.segment(ab, D, (s * 0.06, hy - 0.02, hz + 0.05), (s * 0.22, hy - 0.26, hz + 0.18), 0.014, 0.01)

    specs = leg_specs(long_legs, length_scale)
    for spec in specs:
        salib.leg_mesh(body, spec, mat=D, tip_mat=D)
    mesh = body.join()

    hy = -0.5 if kind == "cannon" else -0.4
    bones = [
        BoneDef("root", (0, 0, 0), (0, 0.25, 0)),
        BoneDef("body", (0, 0.3, 0.25), (0, hy, 0.25), parent="root"),
        BoneDef("head", (0, hy, 0.25), (0, hy - 0.35, 0.25), parent="body"),
        BoneDef("antenna.L", (0.06, hy - 0.22, 0.27), (0.22, hy - 0.46, 0.40), parent="head"),
        BoneDef("antenna.R", (-0.06, hy - 0.22, 0.27), (-0.22, hy - 0.46, 0.40), parent="head"),
    ]
    if kind == "cannon":
        bones.append(BoneDef("cannon", (0, -0.05, 0.60), (0, -1.4, 0.62), parent="body"))
    if kind == "shrapnel":
        bones.append(BoneDef("launcher", (0, 0.02, 0.5), (0, 0.02, 0.75), parent="body"))
    for spec in specs:
        bones += salib.leg_bones(spec, parent="body")
    rig = salib.build_armature("Rig", bones)
    salib.skin(mesh, rig)
    salib.apply_leg_ik(rig, specs)

    clips = []
    c = Clip(rig, "idle", 36)
    salib.key_idle(c, specs, 36, body_bob=0.01, antenna_bones=("antenna.L", "antenna.R"))
    clips.append(c.finish())
    c = Clip(rig, "move", 20 if long_legs else 16)
    salib.key_walk_cycle(c, specs, 20 if long_legs else 16, stride=0.28 if long_legs else 0.18, lift=0.10, body_bob=0.012)
    clips.append(c.finish())
    c = Clip(rig, "attack", 12, loop=False)
    for spec in specs:
        c.key(f"leg.{spec.name}.ik", 1, loc=(0, 0, 0))
        c.key(f"leg.{spec.name}.ik", 12, loc=(0, 0, 0))
    if kind == "cannon":
        c.key("cannon", 1, loc=(0, 0, 0)); c.key("cannon", 3, loc=(0, 0.16, 0)); c.key("cannon", 12, loc=(0, 0, 0))
        c.key("body", 1, loc=(0, 0, 0), rot=(0, 0, 0)); c.key("body", 3, loc=(0, 0.06, 0.02), rot=(-6, 0, 0)); c.key("body", 12, loc=(0, 0, 0), rot=(0, 0, 0))
    elif kind == "shrapnel":
        c.key("launcher", 1, loc=(0, 0, 0), scale=(1, 1, 1)); c.key("launcher", 3, loc=(0, 0, -0.06), scale=(1.3, 1.3, 0.8)); c.key("launcher", 12, loc=(0, 0, 0), scale=(1, 1, 1))
        c.key("body", 1, loc=(0, 0, 0)); c.key("body", 3, loc=(0, 0, -0.04)); c.key("body", 7, loc=(0, 0, 0.03)); c.key("body", 12, loc=(0, 0, 0))
    else:
        # lady bug machine gun: rapid shake
        for f, x in ((1, 0), (3, 0.02), (5, -0.02), (7, 0.02), (9, -0.015), (12, 0)):
            c.key("body", f, loc=(x, 0, 0), rot=(0, 0, x * 60))
    c.key("head", 1, rot=(0, 0, 0)); c.key("head", 4, rot=(-8, 0, 0)); c.key("head", 12, rot=(0, 0, 0))
    clips.append(c.finish())
    c = Clip(rig, "death", 36, loop=False)
    # beetles flip onto their back
    salib.key_death(c, specs, 36, fall_axis_deg=(0, 160, 0), sink=0.10)
    c.key("head", 1, rot=(0, 0, 0)); c.key("head", 36, rot=(20, 0, 0))
    clips.append(c.finish())
    salib.bake_actions(rig, clips)

    path, s = salib.finalize_asset(variant, [rig, mesh], preview_radius=3.0, preview_center=(0, 0, 0.3))
    assert sorted(a["name"] for a in s["animations"]) == ["attack", "death", "idle", "move"]
    return path


if __name__ == "__main__":
    args = [a for a in salib.script_args() if not a.startswith("-")] or list(VARIANTS)
    for v in args:
        build(v)
        print("BUILT", v, flush=True)
