"""Write each level's neutral creeps (plants and flyers) into the map files as `rules.creeps`.

How many of a creep a level can have comes from the original level file: the original levels carry a
row of "Misc" actors outside the playing area (MiscWhipPlant, MiscPuffball, MiscDragonfly, ...), one
per creep the level allows. This tool counts them in the player's own copy of the original game. The
spawn intervals come from OpenSA's per-map rules (or its defaults in mods/sa/rules/misc.yaml), which
were tuned to those counts. Only numbers are written; nothing of the original files is copied.

Maps without an original level (OpenSA's custom and skirmish maps) get OpenSA's plant and flyer
spawner settings instead.

usage: python add_creep_pools.py <assets/data/maps> <OpenSA mods/sa/maps> [<original Game folder>]
"""
import re
import struct
import sys
from pathlib import Path

TICK = 25.0  # OpenSA ticks per second
CRLF = chr(13) + chr(10)
LF = chr(10)

# original level actor type -> (creep key, pool units)
MISC = {
    143: ("popcorn", ["plant_popcorn"]),  # MiscWhipPlant
    101: ("dragonfly", ["neutral_dragonfly"]),  # MiscDragonfly
    157: ("thorn", ["plant_thorn"]),  # MiscThornbush
    161: ("fly", ["neutral_desert_fly"]),  # MiscBigFly
    169: ("puff", ["plant_seedball"]),  # MiscPuffball
    171: ("moth", ["neutral_spawn_moth"]),  # MiscMoth
    172: ("freckle", ["plant_freckle"]),  # MiscFreckle
    176: ("lolly", ["plant_lolly_blue", "plant_lolly_orange", "plant_lolly_white", "plant_lolly_red"]),  # MiscLollyBomb
    180: ("flyingmachine", ["neutral_flying_machine"]),  # MiscFlyingMachine
}
PLANTS = {"normal": ["popcorn"], "desert": ["thorn"], "swamp": ["puff"], "candy": ["freckle", "lolly"]}
FLYER = {"normal": "dragonfly", "desert": "fly", "swamp": "moth", "candy": "flyingmachine"}
UNITS = {v[0]: v[1] for v in MISC.values()}

# OpenSA mods/sa/rules/misc.yaml defaults: (Maximum, SpawnInterval, InitialSpawnDelay) in ticks
PLANT_DEFAULTS = {"normal": (15, (375, 750), (375, 750)), "desert": (15, (300, 500), (300, 500)),
                  "swamp": (20, (325, 525), (325, 525)), "candy": (15, (375, 875), (375, 875))}
FLYER_DEFAULTS = {"dragonfly": ((1000, 1500), (1000, 1500)), "fly": ((625, 875), (625, 875)),
                  "moth": ((625, 750), (625, 750)), "flyingmachine": ((625, 1000), (625, 1000))}


def slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()


def lvl_counts(path):
    """Misc actor counts of an original .LVL (layout per OpenSA MapImporter.cs)."""
    d = Path(path).read_bytes()
    w, h = struct.unpack_from("<ii", d, 400)
    n = struct.unpack_from("<i", d, 424)[0]
    p = 428 + w * h * 2
    counts = {}
    for _ in range(n):
        _aid, atype, _x, _y = struct.unpack_from("<iiii", d, p)
        p += 20
        nprops = struct.unpack_from("<i", d, p)[0]
        p += 8 + nprops * 132
        if atype in MISC:
            key = MISC[atype][0]
            counts[key] = counts.get(key, 0) + 1
    return counts


def ticks(text):
    vals = [int(v) for v in re.findall(r"\d+", text)]
    return (vals[0], vals[-1]) if vals else None


def opensa_rules(folder, tileset):
    """Plant spawner (on, max, interval, first) and flyer spawners {name: (enabled, interval, first)}."""
    rules = ""
    if folder and (folder / "rules.yaml").exists():
        rules = (folder / "rules.yaml").read_text(encoding="utf-8").replace(CRLF, LF)
    ts = tileset.upper()
    mx, iv, first = PLANT_DEFAULTS[tileset]
    plant_on = True
    m = re.search(r"^\t(-?)PlantSpawner@%s:\n((?:\t\t.*\n)*)" % ts, rules, re.M)
    if m:
        if m.group(1) == "-":
            plant_on = False
        body = m.group(2)
        if (v := re.search(r"Maximum:\s*(\d+)", body)):
            mx = int(v.group(1))
        if (v := re.search(r"SpawnInterval:\s*([\d, ]+)", body)):
            iv = ticks(v.group(1))
        if (v := re.search(r"InitialSpawnDelay:\s*([\d, ]+)", body)):
            first = ticks(v.group(1))
    flyers = {}
    for name, (fiv, ffirst) in FLYER_DEFAULTS.items():
        enabled = FLYER[tileset] == name
        m = re.search(r"^\t(-?)CreepFlyerSpawner@%s:\n((?:\t\t.*\n)*)" % name, rules, re.M)
        if m:
            enabled = m.group(1) != "-"
            body = m.group(2)
            if (v := re.search(r"SpawnInterval:\s*([\d, ]+)", body)):
                fiv = ticks(v.group(1))
            if (v := re.search(r"InitialSpawnDelay:\s*([\d, ]+)", body)):
                ffirst = ticks(v.group(1))
        flyers[name] = (enabled, fiv, ffirst)
    return (plant_on, mx, iv, first), flyers


def secs(pair):
    return "(%.1f, %.1f)" % (pair[0] / TICK, pair[1] / TICK)


def pool(key, count, interval, first):
    units = ", ".join('"%s"' % u for u in UNITS[key])
    return "(units: [%s], count: %d, interval: %s, first: %s)" % (units, count, secs(interval), secs(first))


def main():
    maps_dir = Path(sys.argv[1])
    opensa_dir = Path(sys.argv[2])
    game_dir = Path(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else None
    folders = {}
    for f in opensa_dir.iterdir():
        if f.is_dir():
            m = re.match(r"^(\d{3})_", f.name)
            if m:
                folders[("num", int(m.group(1)))] = f
            folders[("slug", slug(f.name.replace("Custom_Mission_", "")))] = f
    levels = {}
    if game_dir:
        for lv in game_dir.glob("*.LVL"):
            m = re.match(r"^(\d{3})\)", lv.name)
            if m:
                levels[int(m.group(1))] = lv
    for path in sorted(maps_dir.glob("*.ron")):
        raw = open(path, encoding="utf-8", newline="").read()
        eol = CRLF if CRLF in raw else LF
        text = raw.replace(CRLF, LF)
        if "tiles: Some(" not in text:
            continue  # hand-made demo maps keep their own rules
        tileset = re.search(r'^\s*tileset:\s*"(\w+)"', text, re.M).group(1)
        num = re.search(r"^\s*number:\s*Some\((\d+)\)", text, re.M)
        num = int(num.group(1)) if num else None
        if num is not None:
            folder = folders.get(("num", num))
        else:
            stem = re.sub(r"^(custom|skirmish)_", "", path.stem)
            folder = folders.get(("slug", stem))
        (plant_on, mx, iv, first), flyers = opensa_rules(folder, tileset)
        pools = []
        source = "OpenSA spawner settings"
        if num is not None and num in levels:
            counts = lvl_counts(levels[num])
            source = "original level's Misc actors"
            for key in PLANTS[tileset]:
                if counts.get(key):
                    pools.append(pool(key, counts[key], iv, first))
            fkey = FLYER[tileset]
            if counts.get(fkey):
                _, fiv, ffirst = flyers[fkey]
                pools.append(pool(fkey, counts[fkey], fiv, ffirst))
        else:
            if plant_on:
                keys = PLANTS[tileset]
                for key in keys:
                    pools.append(pool(key, max(1, mx // len(keys)), iv, first))
            for name, (enabled, fiv, ffirst) in flyers.items():
                if enabled:
                    pools.append(pool(name, 1, fiv, ffirst))
        if pools:
            block = ("        // neutral creeps (%s): up to `count` at once, one more every `interval` seconds" + LF
                     + "        creeps: [" + LF + "%s" + "        ]," + LF) % (source, "".join("            %s," % p + LF for p in pools))
        else:
            block = "        // neutral creeps (%s): none in this level" % source + LF + "        creeps: []," + LF
        # drop an earlier run's block, then insert after unit_cap; the old flyer switch is superseded
        text = re.sub(r"        // neutral creeps \([^\n]*\n        creeps: \[\],\n", "", text)
        text = re.sub(r"        // neutral creeps \([^\n]*\n        creeps: \[\n(?:            [^\n]*\n)*        \],\n", "", text)
        text, n = re.subn(r"(    rules: \(\n(?:        [^\n]*\n)*?        unit_cap: [^\n]*\n)", lambda mm: mm.group(1) + block, text, count=1)
        if n != 1:
            print("!! no rules block in", path.name)
            continue
        text = re.sub(r"(\n        flyers: )true,", r"\1false,", text, count=1)
        open(path, "w", encoding="utf-8", newline="").write(text.replace(LF, eol))
        summary = "; ".join(re.sub(r'\(units: \[([^\]]*)\], count: (\d+).*', r'\1 x\2', p).replace('"', '') for p in pools)
        print(f"{path.name:<44} {tileset:<7} {source:<30} {summary}")


if __name__ == "__main__":
    main()
