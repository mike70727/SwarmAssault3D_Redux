"""Builds the spider family: Black Widow, Sniper, Missile.

References: Quick_References/Units/Spider_* (UNSPIBW*, UNSPISN*, UNSPIRK* + portraits).
* Black Widow: glossy black spider, very long legs, team-coloured hourglass mark on the abdomen.
* Sniper: dark brown hairy spider, team-coloured round abdomen, long rifle on the back.
* Missile: dark spider, team-coloured abdomen, grey box launcher on the back.
Spiders have eight legs (four per side) with high knees; chelicerae (fangs) animate the bite.
Inferred: leg joint positions, eyes, fang shape (sprites show 1-px legs only).
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import salib  # noqa: E402
from salib import BoneDef, Body, Clip, LegSpec  # noqa: E402

VARIANTS = {
    "spider_black_widow": dict(kind="widow"),
    "spider_sniper": dict(kind="sniper"),
    "spider_missile": dict(kind="missile"),
}


def leg_specs(reach=1.0):
    r = reach
    base = [
        ("L1", (0.14, -0.22, 0.30), (0.46 * r, -0.62 * r, 0.62), (0.62 * r, -0.95 * r, 0.0), 0.0),
        ("L2", (0.16, -0.10, 0.30), (0.62 * r, -0.30 * r, 0.64), (0.92 * r, -0.42 * r, 0.0), 0.5),
        ("L3", (0.16, 0.04, 0.30), (0.62 * r, 0.22 * r, 0.64), (0.92 * r, 0.40 * r, 0.0), 0.0),
        ("L4", (0.14, 0.16, 0.30), (0.46 * r, 0.60 * r, 0.62), (0.60 * r, 0.95 * r, 0.0), 0.5),
    ]
    specs = []
    for name, root, knee, foot, phase in base:
        m = lambda p: (-p[0], p[1], p[2])
        specs.append(LegSpec(name, +1, root, knee, foot, phase=phase, radius=0.026))
        specs.append(LegSpec("R" + name[1:], -1, m(root), m(knee), m(foot), phase=(phase + 0.5) % 1.0, radius=0.026))
    return specs


def build(variant: str):
    kind = VARIANTS[variant]["kind"]
    salib.reset_scene(variant)
    mats = salib.standard_materials("Y")
    mats["M_Brown"] = salib.material("M_Brown", (0.30, 0.22, 0.16), roughness=0.8, kind="fur")
    body = Body(variant, mats)
    T, D = "M_Team", "M_Dark"
    body_mat = "M_Black" if kind != "sniper" else "M_Brown"
    abdomen_mat = "M_Black" if kind == "widow" else T

    # cephalothorax + abdomen
    body.sphere("body", body_mat, (0, -0.10, 0.34), 0.24, scale=(1.0, 1.15, 0.8), segments=18, rings=12)
    body.sphere("abdomen", abdomen_mat, (0, 0.36, 0.40), 0.33, scale=(1.0, 1.15, 0.95), segments=20, rings=14)
    if kind == "widow":
        # hourglass marking: two flattened team-coloured pyramids tip to tip on top of the abdomen
        for s in (+1, -1):
            body.cone("abdomen", T, (0, 0.36 + s * 0.08, 0.70), 0.09, 0.0, 0.16, rot=(math.radians(90) * (1 if s > 0 else -1), 0, 0), verts=4)
    elif kind == "sniper":
        # rifle lying along the back, scope and muzzle forward (-Y)
        body.cylinder("gun", "M_Accent", (0.06, -0.15, 0.66), 0.035, 1.25, rot=(math.radians(90), 0, 0))
        body.cube("gun", "M_Brown", (0.06, 0.10, 0.66), size=(0.08, 0.30, 0.10))
        body.cylinder("gun", "M_Accent", (0.06, -0.05, 0.74), 0.03, 0.16, rot=(math.radians(90), 0, 0))
        body.cylinder("gun", D, (0.06, -0.78, 0.66), 0.045, 0.05, rot=(math.radians(90), 0, 0))
    else:
        # box launcher with two tubes
        body.cube("gun", "M_Accent", (0.0, 0.30, 0.78), size=(0.34, 0.36, 0.18))
        for s in (+1, -1):
            body.cylinder("gun", D, (s * 0.09, 0.10, 0.78), 0.05, 0.08, rot=(math.radians(90), 0, 0))
    # eyes (front of cephalothorax) and chelicerae / fangs
    for s in (+1, -1):
        body.sphere("head", "M_Eye", (s * 0.08, -0.35, 0.40), 0.035, segments=8, rings=5)
        body.sphere("head", "M_Eye", (s * 0.15, -0.31, 0.37), 0.025, segments=8, rings=5)
        fb = "fang.L" if s > 0 else "fang.R"
        body.segment(fb, body_mat, (s * 0.07, -0.34, 0.28), (s * 0.08, -0.52, 0.18), 0.04, 0.012)
        # pedipalps
        body.segment("head", body_mat, (s * 0.12, -0.32, 0.30), (s * 0.24, -0.55, 0.26), 0.022, 0.014)

    specs = leg_specs()
    for spec in specs:
        salib.leg_mesh(body, spec, mat=body_mat, tip_mat="M_Black")
    mesh = body.join()

    bones = [
        BoneDef("root", (0, 0, 0), (0, 0.25, 0)),
        BoneDef("body", (0, 0.10, 0.34), (0, -0.30, 0.34), parent="root"),
        BoneDef("abdomen", (0, 0.10, 0.36), (0, 0.70, 0.40), parent="body"),
        BoneDef("head", (0, -0.30, 0.34), (0, -0.50, 0.32), parent="body"),
        BoneDef("fang.L", (0.07, -0.34, 0.28), (0.08, -0.52, 0.18), parent="head"),
        BoneDef("fang.R", (-0.07, -0.34, 0.28), (-0.08, -0.52, 0.18), parent="head"),
    ]
    if kind != "widow":
        bones.append(BoneDef("gun", (0.0, 0.3, 0.7), (0.0, -0.8, 0.7), parent="body"))
    for spec in specs:
        bones += salib.leg_bones(spec, parent="body")
    rig = salib.build_armature("Rig", bones)
    salib.skin(mesh, rig)
    salib.apply_leg_ik(rig, specs)

    clips = []
    c = Clip(rig, "idle", 40)
    salib.key_idle(c, specs, 40, body_bob=0.015)
    c.key("abdomen", 1, rot=(0, 0, 0)); c.key("abdomen", 20, rot=(-5, 0, 0)); c.key("abdomen", 40, rot=(0, 0, 0))
    c.key("fang.L", 1, rot=(0, 0, 0)); c.key("fang.L", 20, rot=(0, 0, 8)); c.key("fang.L", 40, rot=(0, 0, 0))
    c.key("fang.R", 1, rot=(0, 0, 0)); c.key("fang.R", 20, rot=(0, 0, -8)); c.key("fang.R", 40, rot=(0, 0, 0))
    clips.append(c.finish())
    c = Clip(rig, "move", 16)
    salib.key_walk_cycle(c, specs, 16, stride=0.34, lift=0.14, body_bob=0.02)
    clips.append(c.finish())
    c = Clip(rig, "attack", 12, loop=False)
    for spec in specs:
        c.key(f"leg.{spec.name}.ik", 1, loc=(0, 0, 0))
        c.key(f"leg.{spec.name}.ik", 12, loc=(0, 0, 0))
    if kind == "widow":
        c.key("body", 1, loc=(0, 0, 0), rot=(0, 0, 0)); c.key("body", 4, loc=(0, -0.14, -0.06), rot=(14, 0, 0)); c.key("body", 12, loc=(0, 0, 0), rot=(0, 0, 0))
        for sgn, b in ((1, "fang.L"), (-1, "fang.R")):
            c.key(b, 1, rot=(0, 0, 0)); c.key(b, 4, rot=(-30, 0, 25 * sgn)); c.key(b, 7, rot=(20, 0, -10 * sgn)); c.key(b, 12, rot=(0, 0, 0))
    else:
        c.key("gun", 1, loc=(0, 0, 0)); c.key("gun", 3, loc=(0, 0.10, 0.0)); c.key("gun", 12, loc=(0, 0, 0))
        c.key("body", 1, loc=(0, 0, 0), rot=(0, 0, 0)); c.key("body", 3, loc=(0, 0.04, 0.0), rot=(-5, 0, 0)); c.key("body", 12, loc=(0, 0, 0), rot=(0, 0, 0))
    clips.append(c.finish())
    c = Clip(rig, "death", 36, loop=False)
    # spiders curl their legs under the body
    c.key("body", 1, loc=(0, 0, 0), rot=(0, 0, 0)); c.key("body", 36, loc=(0, 0, -0.22), rot=(0, 25, 0))
    c.key("abdomen", 1, rot=(0, 0, 0)); c.key("abdomen", 36, rot=(15, 0, 0))
    for spec in specs:
        n = f"leg.{spec.name}.ik"
        c.key(n, 1, loc=(0, 0, 0))
        c.key(n, 36, loc=(-0.45 * spec.side, -spec.foot[1] * 0.4, 0.25))
    clips.append(c.finish())
    salib.bake_actions(rig, clips)

    path, s = salib.finalize_asset(variant, [rig, mesh], preview_radius=3.2, preview_center=(0, 0, 0.35))
    assert sorted(a["name"] for a in s["animations"]) == ["attack", "death", "idle", "move"]
    return path


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")] or list(VARIANTS)
    for v in args:
        build(v)
        print("BUILT", v, flush=True)
