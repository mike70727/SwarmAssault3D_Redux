"""Builds the ant family: Ant Soldier (+ Grenadier, Bazooka, Bull Ant, Pirate Grenadier variants).

Reference: Quick_References/Units/Ant_Soldier (overhead sprites UNANTSO*, 3-D portrait COLONYANTA3D*).
The sprites show a round head with two large curved mandibles, two antennae, a small thorax carrying
six splayed legs, a thin petiole and a large oval gaster, all in the team colour with darker leg
tips. Geometry that the 48x48 sprites cannot show (leg joint counts, eye placement, underside) is
inferred from real ants and listed in docs/ASSET_NOTES.md.

Usage:  python build_ant.py [variant ...]   (default: ant_soldier)
Variants: ant_soldier ant_grenadier ant_bazooka neutral_bull_ant neutral_pirate_grenadier
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import salib  # noqa: E402
from salib import BoneDef, Body, Clip, LegSpec  # noqa: E402

VARIANTS = {
    # name: dict(team, neutral, scale, mandible, weapon)
    "ant_soldier": dict(neutral=False, scale=1.0, mandible=1.0, weapon=None),
    "ant_grenadier": dict(neutral=False, scale=1.0, mandible=0.7, weapon="grenade"),
    "ant_bazooka": dict(neutral=False, scale=1.0, mandible=0.7, weapon="bazooka"),
    "neutral_bull_ant": dict(neutral=True, scale=1.12, mandible=1.35, weapon=None),
    "neutral_pirate_grenadier": dict(neutral=True, scale=1.0, mandible=0.7, weapon="grenade"),
}

# leg layout (left side; right side is mirrored).  root on thorax underside, knee up/out, foot down.
LEGS = [
    # name, root, knee, foot, phase
    ("L1", (0.12, -0.20, 0.28), (0.40, -0.44, 0.50), (0.52, -0.62, 0.0), 0.0),
    ("L2", (0.13, -0.03, 0.28), (0.52, -0.02, 0.52), (0.74, 0.04, 0.0), 0.5),
    ("L3", (0.12, 0.14, 0.28), (0.44, 0.40, 0.50), (0.58, 0.66, 0.0), 0.0),
]


def leg_specs():
    specs = []
    for name, root, knee, foot, phase in LEGS:
        specs.append(LegSpec(name, +1, root, knee, foot, phase=phase, radius=0.03))
        m = lambda p: (-p[0], p[1], p[2])
        rname = "R" + name[1:]
        specs.append(LegSpec(rname, -1, m(root), m(knee), m(foot), phase=(phase + 0.5) % 1.0, radius=0.03))
    return specs


def build(variant: str):
    cfg = VARIANTS[variant]
    salib.reset_scene(variant)
    mats = salib.standard_materials("Y", neutral=cfg["neutral"])
    body = Body(variant, mats)
    T = "M_Team"
    mand = cfg["mandible"]

    # ---- body segments --------------------------------------------------------------
    body.sphere("abdomen", T, (0, 0.46, 0.33), 0.30, scale=(1.0, 1.28, 0.9), segments=20, rings=12)
    body.sphere("body", T, (0, 0.14, 0.30), 0.08, segments=10, rings=6)            # petiole
    body.sphere("body", T, (0, -0.05, 0.33), 0.20, scale=(0.9, 1.35, 0.9), segments=16, rings=10)  # thorax
    body.sphere("body", T, (0, -0.30, 0.32), 0.07, segments=10, rings=6)           # neck
    body.sphere("head", T, (0, -0.50, 0.35), 0.22, scale=(1.1, 1.0, 0.9), segments=16, rings=10)
    for s in (+1, -1):
        body.sphere("head", "M_Eye", (s * 0.15, -0.60, 0.42), 0.05, segments=8, rings=5)
        # mandibles: two tapered segments curving inwards
        a = (s * 0.12, -0.66, 0.30)
        b = (s * 0.24 * mand, -0.66 - 0.18 * mand, 0.28)
        c = (s * 0.07, -0.66 - 0.36 * mand, 0.26)
        mb = "mandible.L" if s > 0 else "mandible.R"
        body.segment(mb, T, a, b, 0.045, 0.035)
        body.sphere(mb, T, b, 0.036, segments=8, rings=5)
        body.segment(mb, "M_Dark", b, c, 0.034, 0.012)
        # antennae
        ab = "antenna.L" if s > 0 else "antenna.R"
        a0 = (s * 0.08, -0.62, 0.50)
        a1 = (s * 0.22, -0.84, 0.70)
        a2 = (s * 0.34, -1.02, 0.60)
        body.segment(ab, T, a0, a1, 0.022, 0.018)
        body.sphere(ab, T, a1, 0.02, segments=8, rings=5)
        body.segment(ab, T, a1, a2, 0.018, 0.012)

    # ---- legs -------------------------------------------------------------------------
    specs = leg_specs()
    for spec in specs:
        salib.leg_mesh(body, spec, mat=T, tip_mat="M_Dark")

    # ---- weapons (grenadier backpack / bazooka tube) ------------------------------------
    if cfg["weapon"] == "grenade":
        # portrait shows a grey pack/launcher on the thorax; sprite shows a dark box on the back
        body.cube("body", "M_Accent", (0.0, 0.02, 0.58), size=(0.22, 0.26, 0.16))
        body.cylinder("body", "M_Accent", (0.12, -0.12, 0.62), 0.045, 0.24, rot=(math.radians(90), 0, 0))
    elif cfg["weapon"] == "bazooka":
        # long tube along the right side of the body, muzzle forward
        body.cylinder("body", "M_Accent", (0.24, -0.15, 0.55), 0.055, 0.95, rot=(math.radians(90), 0, 0))
        body.cylinder("body", "M_Dark", (0.24, -0.62, 0.55), 0.07, 0.06, rot=(math.radians(90), 0, 0))
        body.cube("body", "M_Accent", (0.16, 0.05, 0.50), size=(0.12, 0.12, 0.12))

    mesh = body.join()

    # ---- rig --------------------------------------------------------------------------
    bones = [
        BoneDef("root", (0, 0, 0), (0, 0.25, 0)),
        BoneDef("body", (0, 0.14, 0.33), (0, -0.30, 0.33), parent="root"),
        BoneDef("abdomen", (0, 0.14, 0.33), (0, 0.75, 0.33), parent="body"),
        BoneDef("head", (0, -0.30, 0.33), (0, -0.70, 0.36), parent="body"),
        BoneDef("mandible.L", (0.12, -0.66, 0.30), (0.07, -0.66 - 0.36 * mand, 0.26), parent="head"),
        BoneDef("mandible.R", (-0.12, -0.66, 0.30), (-0.07, -0.66 - 0.36 * mand, 0.26), parent="head"),
        BoneDef("antenna.L", (0.08, -0.62, 0.50), (0.34, -1.02, 0.60), parent="head"),
        BoneDef("antenna.R", (-0.08, -0.62, 0.50), (-0.34, -1.02, 0.60), parent="head"),
    ]
    for spec in specs:
        bones += salib.leg_bones(spec, parent="body")
    rig = salib.build_armature("Rig", bones)
    salib.skin(mesh, rig)
    salib.apply_leg_ik(rig, specs)

    # ---- animations ---------------------------------------------------------------------
    clips = []
    # idle: 1.2 s breathing bob, antennae wave, mandibles twitch
    c = Clip(rig, "idle", 36)
    salib.key_idle(c, specs, 36, body_bob=0.012, antenna_bones=("antenna.L", "antenna.R"))
    for f, ang in ((1, 0), (12, 6), (24, -3), (36, 0)):
        c.key("mandible.L", f, rot=(0, 0, ang))
        c.key("mandible.R", f, rot=(0, 0, -ang))
    c.key("abdomen", 1, rot=(0, 0, 0)); c.key("abdomen", 18, rot=(3, 0, 0)); c.key("abdomen", 36, rot=(0, 0, 0))
    clips.append(c.finish())
    # move: tripod gait, 0.6 s per cycle
    c = Clip(rig, "move", 18)
    salib.key_walk_cycle(c, specs, 18, stride=0.30, lift=0.12, body_bob=0.015)
    for f, ang in ((1, 0), (5, 4), (9, 0), (14, -4), (18, 0)):
        c.key("head", f, rot=(0, 0, ang))
        c.key("antenna.L", f, rot=(ang * 1.5, 0, 0))
        c.key("antenna.R", f, rot=(-ang * 1.5, 0, 0))
    clips.append(c.finish())
    # attack: lunge and bite, 0.4 s
    c = Clip(rig, "attack", 12, loop=False)
    for spec in specs:
        c.key(f"leg.{spec.name}.ik", 1, loc=(0, 0, 0))
        c.key(f"leg.{spec.name}.ik", 12, loc=(0, 0, 0))
    c.key("body", 1, loc=(0, 0, 0), rot=(0, 0, 0))
    c.key("body", 4, loc=(0, -0.10, -0.02), rot=(8, 0, 0))
    c.key("body", 8, loc=(0, -0.06, 0.0), rot=(-4, 0, 0))
    c.key("body", 12, loc=(0, 0, 0), rot=(0, 0, 0))
    c.key("head", 1, rot=(0, 0, 0)); c.key("head", 4, rot=(-12, 0, 0)); c.key("head", 8, rot=(10, 0, 0)); c.key("head", 12, rot=(0, 0, 0))
    for sgn, b in ((1, "mandible.L"), (-1, "mandible.R")):
        c.key(b, 1, rot=(0, 0, 0))
        c.key(b, 4, rot=(0, 0, 38 * sgn))
        c.key(b, 7, rot=(0, 0, -12 * sgn))
        c.key(b, 12, rot=(0, 0, 0))
    clips.append(c.finish())
    # death: collapse, roll onto the side, legs curl, 1.2 s
    c = Clip(rig, "death", 36, loop=False)
    salib.key_death(c, specs, 36, fall_axis_deg=(0, 75, 0), sink=0.14)
    c.key("head", 1, rot=(0, 0, 0)); c.key("head", 36, rot=(25, 0, 10))
    c.key("mandible.L", 1, rot=(0, 0, 0)); c.key("mandible.L", 36, rot=(0, 0, 30))
    c.key("mandible.R", 1, rot=(0, 0, 0)); c.key("mandible.R", 36, rot=(0, 0, -30))
    c.key("antenna.L", 1, rot=(0, 0, 0)); c.key("antenna.L", 36, rot=(40, 0, 20))
    c.key("antenna.R", 1, rot=(0, 0, 0)); c.key("antenna.R", 36, rot=(40, 0, -20))
    clips.append(c.finish())

    salib.bake_actions(rig, clips)

    # ---- scale, export, previews, save ----------------------------------------------------
    scale = cfg["scale"]
    if scale != 1.0:
        rig.scale = (scale, scale, scale)
        bpy.ops.object.select_all(action="DESELECT")
        rig.select_set(True)
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    path, summary = salib.finalize_asset(variant, [rig, mesh], preview_radius=2.6, preview_center=(0, 0, 0.3))
    names = sorted(a["name"] for a in summary["animations"])
    assert names == ["attack", "death", "idle", "move"], names
    assert "M_Team" in summary["materials"]
    return path


if __name__ == "__main__":
    flags = [a for a in salib.script_args() if a.startswith("-")]
    args = [a for a in salib.script_args() if not a.startswith("-")] or (list(VARIANTS) if "--all" in flags else ["ant_soldier"])
    for v in args:
        if v not in VARIANTS:
            raise SystemExit(f"unknown variant {v}; choose from {list(VARIANTS)}")
        build(v)
        print("BUILT", v, flush=True)
