#!/usr/bin/env python3
"""Package the Blender sources, exported GLBs, baked textures and preview sheets of every model.

The output is split into zip parts of at most MAX_MIB each (download limits); every part holds the
same top-level folder, so extracting all parts into one place rebuilds the full set:

    SwarmAssault3D-models/README.txt, ASSET_NOTES.md, blender/README.md, blender/scripts/*.py
    SwarmAssault3D-models/blend/<asset>.blend      editable Blender files (textures packed)
    SwarmAssault3D-models/glb/<asset>.glb          game models with animation clips
    SwarmAssault3D-models/textures/<asset>/*.jpg   baked colour / ORM / normal maps
    SwarmAssault3D-models/previews/<asset>_sheet.jpg

Usage: tools/package_models.py [max_mib]   (default 28)
"""
import os
import sys
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MAX_MIB = float(sys.argv[1]) if len(sys.argv) > 1 else 28.0
TOP = "SwarmAssault3D-models"
OUT_DIR = os.path.join(ROOT, "dist")
os.makedirs(OUT_DIR, exist_ok=True)

ORDER = [
    "ant_soldier", "ant_grenadier", "ant_bazooka", "neutral_bull_ant", "neutral_pirate_grenadier",
    "beetle_ladybug", "beetle_shrapnel", "beetle_cannon",
    "spider_black_widow", "spider_sniper", "spider_missile",
    "scorpion_savage", "scorpion_spear_gun", "scorpion_ninja",
    "wasp_assault", "wasp_paralysis", "wasp_sonic",
    "neutral_dragonfly", "neutral_desert_fly", "neutral_spawn_moth", "neutral_flying_machine",
    "colony_ant", "colony_beetle", "colony_spider", "colony_scorpion", "colony_wasp",
    "turret_ant", "turret_beetle", "turret_spider", "turret_scorpion", "turret_wasp", "turret_tesla",
    "popcorn_plant", "booster_firepower", "booster_production",
    "rock_large", "rock_small", "mushroom", "flower", "grass_tuft", "colony_bit", "ant_hole",
    "candy_jelly_bean", "candy_gumnut", "candy_choc_chip", "candy_smarty", "candy_jaffa",
]

README = f"""Swarm Assault 3D - model pack (realism pass)

Extract every part of this pack into the same folder; they all share the "{TOP}" directory.

blend/      Blender files (Blender 4.2 or newer; built with 5.2.2). Each file holds the rigged model,
            the baked PBR materials (textures packed inside the file) and the procedural originals
            (materials named M_*_proc, fake users) used for the bake. Animation clips are NLA
            tracks: idle, move (fly for flyers), attack, death; colonies: idle, turret_fire. The
            IK rigs keep their *_ik actions for editing.
glb/        The same models exported for the game (glTF binary, +Y up, animations included,
            textures embedded). Drop into assets/models of the game to replace a model.
textures/   The baked maps as plain JPEG files: <object>_color.jpg (albedo, sRGB),
            <object>_orm.jpg (G = roughness, B = metallic), <object>_normal.jpg (tangent space).
previews/   Contact sheets rendered by Blender from the baked materials.
blender/    The scripts that generated everything (see blender/README.md); salib.py holds the
            realism layer (procedural materials, subdivision, bakes).
ASSET_NOTES.md  What each model is based on, what was inferred, and the realism-pass notes.

Team colour: M_Team / M_Colony textures are neutral; the colour is a multiply factor
(baseColorFactor in the GLB, the TeamTint RGB node in the *_proc materials).
"""


def asset_files(asset):
    files = []
    for rel in (f"blender/blend/{asset}.blend", f"assets/models/{asset}.glb", f"blender/previews/{asset}_sheet.jpg"):
        p = os.path.join(ROOT, rel)
        if os.path.exists(p):
            files.append(p)
    tdir = os.path.join(ROOT, "assets", "textures", asset)
    if os.path.isdir(tdir):
        files += [os.path.join(tdir, f) for f in sorted(os.listdir(tdir))]
    return files


def arc_path(p):
    rel = os.path.relpath(p, ROOT).replace(os.sep, "/")
    if rel.startswith("blender/blend/"):
        return f"{TOP}/blend/" + rel.split("/")[-1]
    if rel.startswith("assets/models/"):
        return f"{TOP}/glb/" + rel.split("/")[-1]
    if rel.startswith("assets/textures/"):
        return f"{TOP}/textures/" + "/".join(rel.split("/")[2:])
    if rel.startswith("blender/previews/"):
        return f"{TOP}/previews/" + rel.split("/")[-1]
    return f"{TOP}/" + rel


def main():
    limit = MAX_MIB * 1024 * 1024 * 0.97  # zip overhead margin
    shared = [os.path.join(ROOT, "docs", "ASSET_NOTES.md"), os.path.join(ROOT, "blender", "README.md")]
    shared += [os.path.join(ROOT, "blender", "scripts", f) for f in sorted(os.listdir(os.path.join(ROOT, "blender", "scripts"))) if f.endswith(".py")]
    groups = []  # list of (name, [files])
    missing = []
    for a in ORDER:
        fs = asset_files(a)
        if not any(f.endswith(".glb") for f in fs):
            missing.append(a)
        groups.append((a, fs))
    parts = []
    cur, cur_size = [], len(README) + sum(os.path.getsize(f) for f in shared)
    for name, fs in groups:
        size = sum(os.path.getsize(f) for f in fs)
        if cur and cur_size + size > limit:
            parts.append(cur)
            cur, cur_size = [], 0
        cur.append((name, fs))
        cur_size += size
    if cur:
        parts.append(cur)
    n = len(parts)
    written = []
    for i, part in enumerate(parts, 1):
        zpath = os.path.join(OUT_DIR, f"SwarmAssault3D-models-part{i}of{n}.zip")
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            if i == 1:
                z.writestr(f"{TOP}/README.txt", README)
                for f in shared:
                    z.write(f, arc_path(f))
            for name, fs in part:
                for f in fs:
                    z.write(f, arc_path(f))
        mib = os.path.getsize(zpath) / 1048576
        written.append((zpath, mib, [name for name, _ in part]))
        print(f"{os.path.basename(zpath)}  {mib:6.1f} MiB  {', '.join(name for name, _ in part)}")
    if missing:
        print("WARNING missing GLB for:", ", ".join(missing))
    return written


if __name__ == "__main__":
    main()
