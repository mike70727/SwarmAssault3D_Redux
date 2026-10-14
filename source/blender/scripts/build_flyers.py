"""Builds every flying unit: the wasp family and the four neutral flyers.

References: Quick_References/Units/Wasp_* (UNWASPL*, UNWASPA*, UNWASSO*), Neutral_Dragonfly (UNDRABOB),
Neutral_Desert_Fly (UNFLYBIG), Neutral_Spawn_Moth (UNDEMOTH), Neutral_Flying_Machine (UNFLYMCH).
* Wasps: dark head/thorax, banded abdomen (team colour + black), two translucent wings, six tucked
  legs, antennae. Assault has a small gun under the thorax, Paralysis a longer body and a green arrow
  launcher, Sonic a stocky body with a horn-shaped emitter.
* Dragonfly: long thin blue-grey abdomen, four narrow wings, big green eyes.
* Desert Fly: round grey fly with huge green compound eyes and two wings.
* Spawn Moth: furry tan body, two large patterned wings per side, feathery antennae.
* Flying Machine: dark wooden hull with a four-blade pink rotor and a pirate-ant pilot.
Wings are driven by `wing.*` bones (flap = rotation about the wing root), rotors by a `rotor` bone.
Clips: idle (hover), fly, attack (recoil while flapping), death (wings fold).
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import salib  # noqa: E402
from salib import BoneDef, Body, Clip  # noqa: E402

VARIANTS = {
    "wasp_assault": dict(kind="wasp", weapon="gun", abdomen_len=1.0),
    "wasp_paralysis": dict(kind="wasp", weapon="arrow", abdomen_len=1.3),
    "wasp_sonic": dict(kind="wasp", weapon="sonic", abdomen_len=0.9),
    "neutral_dragonfly": dict(kind="dragonfly"),
    "neutral_desert_fly": dict(kind="fly"),
    "neutral_spawn_moth": dict(kind="moth"),
    "neutral_flying_machine": dict(kind="machine"),
}

LEGS6 = [(-0.18, 1), (0.0, 1), (0.16, 1), (-0.18, -1), (0.0, -1), (0.16, -1)]


def tucked_legs(body, mat, y_positions, z=0.42, reach=0.34, radius=0.016):
    for y, s in y_positions:
        a = (s * 0.08, y, z)
        b = (s * reach * 0.8, y - 0.10, z - 0.22)
        c = (s * reach, y + 0.05, z - 0.40)
        body.segment("body", mat, a, b, radius * 1.2, radius)
        body.segment("body", mat, b, c, radius, radius * 0.5)


def wing(body, bone, mat, root, tip, width, curve=0.05, thickness=0.006):
    body.plane_wing(bone, mat, root, tip, width, thickness=thickness, curve=curve)


def wing_flap_keys(c, frames, bones_signs, amp=40.0, idle_tilt=0.0, phase_offset=0.0):
    """Key wing bones with a sinusoidal flap (rotation about the local Y = wing root axis)."""
    for b, sgn in bones_signs:
        for i in range(frames + 1):
            f = 1 + i
            t = i / frames
            ang = amp * math.sin(2 * math.pi * (t * 2 + phase_offset))  # two flaps per clip
            c.key(b, f, rot=(0, sgn * (ang + idle_tilt), 0))


def build(variant: str):
    cfg = VARIANTS[variant]
    kind = cfg["kind"]
    salib.reset_scene(variant)
    neutral = kind != "wasp"
    mats = salib.standard_materials("Y", neutral=False)
    mats["M_Green"] = salib.material("M_Green", (0.25, 0.85, 0.25), roughness=0.3, emission=(0.1, 0.6, 0.1), emission_strength=0.5, kind="glossy")
    mats["M_Grey"] = salib.material("M_Grey", (0.55, 0.55, 0.52), roughness=0.7, kind="fur")
    mats["M_Tan"] = salib.material("M_Tan", (0.85, 0.62, 0.35), roughness=0.8, kind="fur")
    mats["M_MothWing"] = salib.material("M_MothWing", (0.90, 0.70, 0.40), roughness=0.9, alpha=0.95, kind="organic", variation=0.6, scale=4.0)
    mats["M_Blue"] = salib.material("M_Blue", (0.45, 0.62, 0.78), roughness=0.4, kind="chitin", coat=0.9, variation=0.5)
    mats["M_Wood"] = salib.material("M_Wood", (0.30, 0.18, 0.10), roughness=0.85, kind="wood")
    mats["M_Pink"] = salib.material("M_Pink", (0.85, 0.45, 0.80), roughness=0.5, kind="organic")
    body = Body(variant, mats)
    T, D = "M_Team", "M_Black"
    z = 0.45  # body centre height in the model (the sim adds the flight altitude)
    wing_bones = []
    extra_bones = []

    if kind == "wasp":
        L = cfg["abdomen_len"]
        body.sphere("head", D, (0, -0.42, z + 0.02), 0.15, scale=(1.0, 1.0, 0.9), segments=14, rings=10)
        for s in (+1, -1):
            body.sphere("head", "M_Eye", (s * 0.10, -0.50, z + 0.05), 0.05, segments=8, rings=5)
            ab = "antenna.L" if s > 0 else "antenna.R"
            body.segment(ab, D, (s * 0.06, -0.52, z + 0.14), (s * 0.20, -0.75, z + 0.30), 0.012, 0.008)
        body.sphere("body", D, (0, -0.15, z), 0.20, scale=(1.0, 1.2, 0.95), segments=16, rings=10)
        body.sphere("body", T, (0, -0.15, z + 0.12), 0.10, scale=(1.4, 0.6, 0.5), segments=12, rings=6)  # scutum stripe
        body.sphere("abdomen", D, (0, 0.12, z - 0.02), 0.06, segments=8, rings=5)  # petiole
        n_bands = 4
        for i in range(n_bands):
            y = 0.22 + i * 0.17 * L
            r = (0.17 if i < n_bands - 1 else 0.13) * (1.0 if L < 1.2 else 0.9)
            body.sphere("abdomen", T if i % 2 == 0 else D, (0, y, z - 0.03 - i * 0.02), r, scale=(1.0, 1.25, 0.9), segments=14, rings=10)
        body.cone("abdomen", D, (0, 0.22 + n_bands * 0.17 * L + 0.02, z - 0.12), 0.05, 0.0, 0.16, rot=(math.radians(-90), 0, 0), verts=8)  # stinger
        wing(body, "wing.L", "M_Wing", (0.10, -0.12, z + 0.18), (0.95, 0.55, z + 0.30), 0.16)
        wing(body, "wing.R", "M_Wing", (-0.10, -0.12, z + 0.18), (-0.95, 0.55, z + 0.30), 0.16)
        wing_bones = [("wing.L", (0.10, -0.12, z + 0.18), (0.95, 0.55, z + 0.30), 1), ("wing.R", (-0.10, -0.12, z + 0.18), (-0.95, 0.55, z + 0.30), -1)]
        tucked_legs(body, D, [(-0.22, 1), (-0.08, 1), (0.08, 1), (-0.22, -1), (-0.08, -1), (0.08, -1)], z=z - 0.1, reach=0.30)
        if cfg["weapon"] == "gun":
            body.cylinder("gun", "M_Accent", (0.0, -0.42, z - 0.16), 0.035, 0.36, rot=(math.radians(90), 0, 0))
            body.cube("gun", D, (0.0, -0.22, z - 0.16), size=(0.10, 0.12, 0.08))
        elif cfg["weapon"] == "arrow":
            body.cylinder("gun", "M_Accent", (0.0, -0.45, z - 0.14), 0.03, 0.42, rot=(math.radians(90), 0, 0))
            body.sphere("gun", "M_Green", (0.0, -0.68, z - 0.14), 0.05, segments=10, rings=6)
        else:
            body.cone("gun", "M_Accent", (0.0, -0.62, z - 0.08), 0.12, 0.04, 0.30, rot=(math.radians(-90), 0, 0), verts=14)
        extra_bones.append(BoneDef("gun", (0, -0.2, z - 0.15), (0, -0.7, z - 0.15), parent="body"))
        extra_bones.append(BoneDef("antenna.L", (0.06, -0.52, z + 0.14), (0.20, -0.75, z + 0.30), parent="head"))
        extra_bones.append(BoneDef("antenna.R", (-0.06, -0.52, z + 0.14), (-0.20, -0.75, z + 0.30), parent="head"))
    elif kind == "dragonfly":
        body.sphere("head", "M_Blue", (0, -0.50, z), 0.12, segments=12, rings=8)
        for s in (+1, -1):
            body.sphere("head", "M_Green", (s * 0.08, -0.55, z + 0.03), 0.07, segments=10, rings=6)
        body.sphere("body", "M_Blue", (0, -0.25, z), 0.16, scale=(1.0, 1.3, 1.0), segments=14, rings=10)
        for i in range(8):
            y = 0.02 + i * 0.19
            body.sphere("abdomen", "M_Blue" if i % 2 == 0 else D, (0, y, z), 0.065 - i * 0.003, scale=(1.0, 1.6, 1.0), segments=10, rings=6)
        for s in (+1, -1):
            for j, (y0, y1) in enumerate(((-0.30, 0.25), (-0.12, 0.55))):
                bn = f"wing.{'L' if s > 0 else 'R'}{j + 1}"
                root = (s * 0.08, y0 + 0.1, z + 0.12)
                tip = (s * 1.35, y1, z + 0.16)
                wing(body, bn, "M_Wing", root, tip, 0.11)
                wing_bones.append((bn, root, tip, s))
        tucked_legs(body, D, [(-0.36, 1), (-0.26, 1), (-0.14, 1), (-0.36, -1), (-0.26, -1), (-0.14, -1)], z=z - 0.05, reach=0.22)
    elif kind == "fly":
        body.sphere("head", "M_Grey", (0, -0.36, z), 0.17, segments=14, rings=10)
        for s in (+1, -1):
            body.sphere("head", "M_Green", (s * 0.11, -0.42, z + 0.03), 0.11, scale=(0.8, 1.0, 1.1), segments=12, rings=8)
        body.sphere("body", "M_Grey", (0, -0.05, z + 0.02), 0.25, scale=(1.0, 1.1, 0.95), segments=16, rings=10)
        body.sphere("abdomen", D, (0, 0.30, z - 0.02), 0.24, scale=(1.0, 1.3, 0.9), segments=16, rings=10)
        body.sphere("abdomen", "M_Grey", (0, 0.30, z + 0.10), 0.12, scale=(1.5, 1.6, 0.5), segments=10, rings=6)
        for s in (+1, -1):
            bn = f"wing.{'L' if s > 0 else 'R'}"
            root = (s * 0.12, -0.05, z + 0.20)
            tip = (s * 1.05, 0.55, z + 0.26)
            wing(body, bn, "M_Wing", root, tip, 0.20)
            wing_bones.append((bn, root, tip, s))
        tucked_legs(body, D, [(-0.25, 1), (-0.08, 1), (0.10, 1), (-0.25, -1), (-0.08, -1), (0.10, -1)], z=z - 0.08, reach=0.36)
    elif kind == "moth":
        body.sphere("head", "M_Tan", (0, -0.30, z), 0.12, segments=12, rings=8)
        for s in (+1, -1):
            body.sphere("head", "M_Eye", (s * 0.08, -0.36, z + 0.02), 0.04, segments=8, rings=5)
            ab = "antenna.L" if s > 0 else "antenna.R"
            body.segment(ab, "M_Tan", (s * 0.05, -0.36, z + 0.1), (s * 0.30, -0.62, z + 0.25), 0.03, 0.01)
        body.sphere("body", "M_Tan", (0, 0.0, z), 0.20, scale=(1.0, 1.4, 1.0), segments=14, rings=10)
        body.sphere("abdomen", "M_Tan", (0, 0.38, z - 0.03), 0.16, scale=(1.0, 1.8, 0.9), segments=14, rings=10)
        for s in (+1, -1):
            for j, (root, tip, w) in enumerate((((s * 0.10, -0.08, z + 0.1), (s * 1.30, -0.55, z + 0.12), 0.42), ((s * 0.10, 0.18, z + 0.08), (s * 1.05, 0.70, z + 0.10), 0.36))):
                bn = f"wing.{'L' if s > 0 else 'R'}{j + 1}"
                wing(body, bn, "M_MothWing", root, tip, w, thickness=0.012)
                wing_bones.append((bn, root, tip, s))
                # dark eye-spots on the forewing
                if j == 0:
                    body.sphere(bn, D, (s * 0.75, -0.30, z + 0.13), 0.09, scale=(1.0, 1.0, 0.2), segments=10, rings=6)
        extra_bones.append(BoneDef("antenna.L", (0.05, -0.36, z + 0.1), (0.30, -0.62, z + 0.25), parent="head"))
        extra_bones.append(BoneDef("antenna.R", (-0.05, -0.36, z + 0.1), (-0.30, -0.62, z + 0.25), parent="head"))
    else:  # flying machine
        body.sphere("body", "M_Wood", (0, 0.0, z - 0.05), 0.38, scale=(0.75, 1.3, 0.5), segments=16, rings=10)  # hull
        body.cube("body", "M_Wood", (0, 0.0, z + 0.05), size=(0.5, 0.9, 0.12))
        body.cylinder("body", "M_Accent", (0, 0.0, z + 0.35), 0.03, 0.6)  # mast
        body.cube("body", "M_Wood", (0, 0.62, z + 0.18), size=(0.06, 0.25, 0.3))  # tail fin
        body.cylinder("rotor", "M_Accent", (0, 0.0, z + 0.66), 0.06, 0.06)
        for k in range(4):
            ang = k * math.pi / 2
            body.cube("rotor", "M_Pink", (0.45 * math.cos(ang), 0.45 * math.sin(ang), z + 0.66), size=(0.8, 0.14, 0.02), rot=(0, 0, ang))
        # pilot: small black ant poking out
        body.sphere("body", D, (0, -0.15, z + 0.25), 0.11, segments=10, rings=6)
        body.sphere("body", D, (0, -0.30, z + 0.30), 0.08, segments=10, rings=6)
        for s in (+1, -1):
            body.sphere("body", "M_Blue", (s * 0.04, -0.36, z + 0.32), 0.02, segments=6, rings=4)
        extra_bones.append(BoneDef("rotor", (0, 0, z + 0.60), (0, 0, z + 0.8), parent="body"))
    mesh = body.join()

    bones = [
        BoneDef("root", (0, 0, 0), (0, 0.25, 0)),
        BoneDef("body", (0, 0.1, z), (0, -0.3, z), parent="root"),
        BoneDef("head", (0, -0.3, z), (0, -0.6, z), parent="body"),
        BoneDef("abdomen", (0, 0.1, z), (0, 0.9, z - 0.05), parent="body"),
    ]
    for bn, root, tip, _s in wing_bones:
        bones.append(BoneDef(bn, root, tip, parent="body"))
    bones += extra_bones
    rig = salib.build_armature("Rig", bones)
    salib.skin(mesh, rig)

    flap = [(bn, s) for bn, _r, _t, s in wing_bones]
    # the wing bone points outwards along its own Y axis; flapping rotates around that axis? No:
    # a bone's local Y runs root->tip, so rotating about local Y would twist. Flap about local X
    # instead (keyed below via rot=(ang,0,0)).
    def flap_keys(c, frames, amp, tilt=0.0, speed=2):
        for bn, s in flap:
            for i in range(frames + 1):
                f = 1 + i
                t = i / frames
                ang = amp * math.sin(2 * math.pi * t * speed)
                c.key(bn, f, rot=(ang + tilt, 0, 0))

    def rotor_keys(c, frames, turns=1.0):
        if kind != "machine":
            return
        for i in range(frames + 1):
            c.key("rotor", 1 + i, rot=(0, 0, 360.0 * turns * i / frames))

    clips = []
    c = Clip(rig, "idle", 12)
    flap_keys(c, 12, 35.0, tilt=5.0, speed=2)
    rotor_keys(c, 12, 1.0)
    c.key("body", 1, loc=(0, 0, 0)); c.key("body", 6, loc=(0, 0, 0.03)); c.key("body", 12, loc=(0, 0, 0))
    clips.append(c.finish())
    c = Clip(rig, "fly", 12)
    flap_keys(c, 12, 45.0, tilt=0.0, speed=2)
    rotor_keys(c, 12, 1.0)
    c.key("body", 1, rot=(8, 0, 0), loc=(0, 0, 0)); c.key("body", 6, rot=(8, 0, 0), loc=(0, 0, 0.02)); c.key("body", 12, rot=(8, 0, 0), loc=(0, 0, 0))
    c.key("abdomen", 1, rot=(-4, 0, 0)); c.key("abdomen", 12, rot=(-4, 0, 0))
    clips.append(c.finish())
    c = Clip(rig, "attack", 12, loop=False)
    flap_keys(c, 12, 40.0, tilt=0.0, speed=2)
    rotor_keys(c, 12, 1.0)
    c.key("body", 1, loc=(0, 0, 0), rot=(0, 0, 0)); c.key("body", 3, loc=(0, 0.08, 0.02), rot=(-8, 0, 0)); c.key("body", 12, loc=(0, 0, 0), rot=(0, 0, 0))
    if kind == "wasp":
        c.key("gun", 1, loc=(0, 0, 0)); c.key("gun", 2, loc=(0, 0.08, 0)); c.key("gun", 12, loc=(0, 0, 0))
    clips.append(c.finish())
    c = Clip(rig, "death", 36, loop=False)
    for bn, s in flap:
        c.key(bn, 1, rot=(0, 0, 0))
        c.key(bn, 36, rot=(70, 0, 0))
    if kind == "machine":
        c.key("rotor", 1, rot=(0, 0, 0)); c.key("rotor", 36, rot=(0, 0, 200))
    c.key("body", 1, loc=(0, 0, 0), rot=(0, 0, 0)); c.key("body", 36, loc=(0, 0, -0.3), rot=(40, 140, 0))
    c.key("abdomen", 1, rot=(0, 0, 0)); c.key("abdomen", 36, rot=(30, 0, 0))
    clips.append(c.finish())
    salib.bake_actions(rig, clips)

    path, s = salib.finalize_asset(variant, [rig, mesh], preview_radius=3.2, preview_center=(0, 0, z))
    assert sorted(a["name"] for a in s["animations"]) == ["attack", "death", "fly", "idle"], s["animations"]
    return path


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")] or list(VARIANTS)
    for v in args:
        build(v)
        print("BUILT", v, flush=True)
