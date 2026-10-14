#!/usr/bin/env python3
"""Convert OpenSA (OpenRA mod) maps into this game's RON map files.

Usage: tools/convert_opensa_maps.py <path/to/OpenSA/mods/sa> [--out assets/data/maps] [--only NAME ...]

For every map folder (map.yaml + map.bin + rules.yaml + script.lua) it writes one
`<NNN>_<slug>.ron` (campaign), `custom_<slug>.ron` or `skirmish_<slug>.ron` with:
  * the per-cell terrain (tile -> Clear/Rock/Vegetation/Water through the tileset templates), cropped to
    the map bounds,
  * colonies, colony turrets, tesla coils, popcorn plants and boosters with their owners,
  * every placed unit (pirates become neutral units), plants as blocking props,
  * the players as teams (human = the playable player, bots per faction, OpenSA colours),
  * creep flyers / pirate spawners from the map's rule overrides, the bot start delay from the script,
  * the start camera.
Run `--report` to print the actor types that were not converted.
"""
import hashlib
import os
import re
import struct
import sys

ARGS = sys.argv[1:]
if not ARGS or ARGS[0].startswith("-"):
    sys.exit(__doc__)
MOD = ARGS[0]
OUT = "assets/data/maps"
ONLY = []
REPORT = "--report" in ARGS
i = 1
while i < len(ARGS):
    if ARGS[i] == "--out":
        OUT = ARGS[i + 1]
        i += 2
    elif ARGS[i] == "--only":
        i += 1
        while i < len(ARGS) and not ARGS[i].startswith("-"):
            ONLY.append(ARGS[i])
            i += 1
    else:
        i += 1
os.makedirs(OUT, exist_ok=True)

FACTION_COLONY = {"ants": "colony_ant", "beetles": "colony_beetle", "spiders": "colony_spider", "scorpions": "colony_scorpion", "wasps": "colony_wasp"}
FACTION_UNITS = {
    "ants": ["ant_soldier", "ant_grenadier", "ant_bazooka"],
    "beetles": ["beetle_ladybug", "beetle_shrapnel", "beetle_cannon"],
    "spiders": ["spider_black_widow", "spider_sniper", "spider_missile"],
    "scorpions": ["scorpion_savage", "scorpion_spear_gun", "scorpion_ninja"],
    "wasps": ["wasp_assault", "wasp_paralysis", "wasp_sonic"],
}
TIERS = {"light": 0, "medium": 1, "heavy": 2}
PIRATES = {"ants_grenadier_pirate": "neutral_pirate_grenadier", "ant_bull_pirate": "neutral_bull_ant", "ants_bazooka_pirate": "neutral_pirate_grenadier"}
TURRETS = {"ants_colony_turret": "turret_ant", "beetles_colony_turret": "turret_beetle", "spiders_colony_turret": "turret_spider",
           "scorpions_colony_turret": "turret_scorpion", "scorpions_colony_turret_small": "turret_scorpion", "wasps_colony_turret": "turret_wasp",
           "tesla_coil_turret": "turret_tesla"}
BOOSTERS = {"firepowerbooster": "booster_firepower", "productionbooster": "booster_production"}
PLANTS = {
    "plant_clover": "grass_tuft", "plant_broad_leaf_grass": "grass_tuft", "plant_desert_grass": "grass_tuft", "plant_serata": "grass_tuft",
    "plant_flower": "flower", "plant_cherry_flower": "flower", "plant_moon_flower": "flower", "plant_desert_flower": "flower",
    "plant_moon_mushroom": "mushroom", "plant_brown_mushroom": "mushroom", "plant_toad_stool": "mushroom",
    "plant_jelly_bean": "candy_jelly_bean", "plant_gumnut": "candy_gumnut", "plant_choc_chip": "candy_choc_chip",
    "plant_smarty": "candy_smarty", "plant_jaffa": "candy_jaffa",
}
PLANT_RADIUS = {"grass_tuft": 0.4, "flower": 0.4, "mushroom": 0.45, "candy_jelly_bean": 0.45, "candy_gumnut": 0.45, "candy_choc_chip": 0.45, "candy_smarty": 0.45, "candy_jaffa": 0.45}
FLYERS = {"dragonfly": "neutral_dragonfly", "fly": "neutral_desert_fly", "moth": "neutral_spawn_moth", "flyingmachine": "neutral_flying_machine"}
TILESET_FLYER = {"normal": "dragonfly", "desert": "fly", "swamp": "moth", "candy": "flyingmachine"}
DEFAULT_COLORS = ["#E8C547", "#CA3131", "#4E7FD1", "#57AC49", "#B05FC9", "#E08A2E", "#3CB8B2", "#8C6E4A"]
FACTIONS = list(FACTION_COLONY)

skipped = {}


def parse_tileset(name):
    tiles = {}
    cur = None
    for line in open(os.path.join(MOD, "tilesets", f"{name}.yaml"), encoding="utf-8"):
        m = re.match(r"\tTemplate@(\d+):", line)
        if m:
            cur = int(m.group(1))
            continue
        m = re.match(r"\t\t\t(\d+): (\w+)", line)
        if m and cur is not None:
            tiles[(cur, int(m.group(1)))] = m.group(2)
    return tiles


TILESETS = {t: parse_tileset(t) for t in ("normal", "desert", "swamp", "candy")}
TERRAIN_CHAR = {"Clear": ".", "Rock": "r", "Vegetation": "v", "Water": "w"}


def parse_bin(path):
    d = open(path, "rb").read()
    w, h = struct.unpack("<HH", d[1:5])
    tiles = [struct.unpack("<HB", d[5 + 3 * i:8 + 3 * i]) for i in range(w * h)]
    return w, h, tiles  # column-major: index = x * h + y


def parse_yaml_blocks(text, header):
    """Return [(name, {key: value})] for the indented blocks under a top-level `header:` line."""
    out = []
    lines = text.splitlines()
    try:
        start = lines.index(header + ":")
    except ValueError:
        return out
    cur = None
    for line in lines[start + 1:]:
        if line and not line.startswith("\t"):
            break
        m = re.match(r"\t([^\t:]+): ?(.*)$", line)
        if m:
            cur = (m.group(1), m.group(2).strip(), {})
            out.append(cur)
            continue
        m = re.match(r"\t\t([^\t:]+): ?(.*)$", line)
        if m and cur is not None:
            cur[2][m.group(1)] = m.group(2).strip()
    return out


def hashf(*parts):
    h = hashlib.md5("|".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(h[:4], "little") / 2**32


def slug(title):
    s = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_").lower()
    return s or "map"


def ron_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def convert(folder):
    name = os.path.basename(folder)
    y = open(os.path.join(folder, "map.yaml"), encoding="utf-8").read()
    title = re.search(r"^Title: (.*)$", y, re.M).group(1).strip()
    tileset = re.search(r"^Tileset: (\w+)", y, re.M).group(1).lower()
    author = (re.search(r"^Author: (.*)$", y, re.M) or [None, ""])[1].strip() if re.search(r"^Author:", y, re.M) else ""
    category = (re.search(r"^Categories: (.*)$", y, re.M) or [None, ""])[1].strip().lower() if re.search(r"^Categories:", y, re.M) else ""
    bx, by, bw, bh = [int(v) for v in re.search(r"^Bounds: (.*)$", y, re.M).group(1).split(",")]
    w, h, tiles = parse_bin(os.path.join(folder, "map.bin"))
    ts = TILESETS[tileset]
    rows = []
    unknown = 0
    for yy in range(by, by + bh):
        row = []
        for xx in range(bx, bx + bw):
            k = ts.get(tiles[xx * h + yy])
            if k is None:
                unknown += 1
                k = "Clear"
            row.append(TERRAIN_CHAR[k])
        rows.append("".join(row))
    cells = "\n".join(rows)

    # players -> teams
    players = parse_yaml_blocks(y, "Players")
    teams = []  # dicts: id, name, faction, color, human, pname
    for pname, _, kv in players:
        pn = kv.get("Name", pname.split("@")[-1])
        if kv.get("NonCombatant", "False") == "True" or kv.get("OwnsWorld", "False") == "True":
            continue
        teams.append({"pname": pn, "faction": kv.get("Faction", "Random").lower(), "bot": kv.get("Bot"), "playable": kv.get("Playable", "False") == "True", "color": kv.get("Color")})
    humans = [t for t in teams if t["playable"] and not t["bot"]]
    if not humans and teams:
        teams[0]["playable"] = True
        humans = [teams[0]]
    human = humans[0]
    used = set()
    for i, t in enumerate(teams):
        t["id"] = i + 1
        if t["faction"] not in FACTION_COLONY:
            # random faction: deterministic, distinct where possible
            order = sorted(FACTIONS, key=lambda f: hashf(name, i, f))
            pick = next((f for f in order if f not in used), order[0])
            t["faction"] = pick
        used.add(t["faction"])
        t["human"] = t is human
        if not t["color"]:
            t["color"] = DEFAULT_COLORS[i % len(DEFAULT_COLORS)]
        else:
            t["color"] = "#" + t["color"]
        base = t["pname"] if not t["pname"].startswith("Multi") else t["faction"].capitalize()
        t["name"] = base
    by_pname = {t["pname"]: t for t in teams}

    def team_of(owner):
        t = by_pname.get(owner)
        return t["id"] if t else 0

    # actors
    actors = parse_yaml_blocks(y, "Actors")
    colonies, units, obstacles, spawns, camera = [], [], [], [], None
    for aname, atype, kv in actors:
        loc = kv.get("Location")
        if not loc:
            continue
        lx, ly = [int(v) for v in loc.split(",")]
        px, py = lx - bx, ly - by
        owner = kv.get("Owner", "Neutral")
        team = team_of(owner)
        if atype in FACTION_COLONY.values() or atype.endswith("_colony") and atype.split("_")[0] in FACTION_COLONY:
            fam = atype.split("_")[0]
            colonies.append((FACTION_COLONY[fam], team, px + 2.5, py + 2.5))
        elif atype == "randomcolony":
            t = by_pname.get(owner)
            fam = t["faction"] if t else sorted(FACTIONS, key=lambda f: hashf(name, aname, f))[0]
            colonies.append((FACTION_COLONY[fam], team, px + 2.5, py + 2.5))
        elif atype in TURRETS:
            colonies.append((TURRETS[atype], team, px + 0.5, py + 0.5))
        elif atype == "popcorn":
            colonies.append(("popcorn_plant", 0, px + 0.5, py + 0.5))
        elif atype in BOOSTERS:
            colonies.append((BOOSTERS[atype], team, px + 1.5, py + 1.0))
        elif atype in PIRATES:
            units.append((PIRATES[atype], 0, px + 0.5, py + 0.5))
        elif "_" in atype and atype.split("_")[0] in FACTION_UNITS and atype.split("_")[1] in TIERS:
            fam, tier = atype.split("_")[0], atype.split("_")[1]
            units.append((FACTION_UNITS[fam][TIERS[tier]], team, px + 0.5, py + 0.5))
        elif atype in PLANTS:
            kind = PLANTS[atype]
            obstacles.append((kind, px + 0.5, py + 0.5, PLANT_RADIUS[kind], hashf(name, aname) * 6.283, 0.85 + 0.3 * hashf(aname, name)))
        elif atype == "mpspawn":
            spawns.append((px + 0.5, py + 0.5))
        elif atype == "startcamera":
            camera = (px + 0.5, py + 0.5)
        else:
            skipped[atype] = skipped.get(atype, 0) + 1
    # skirmish maps: every player starts with a colony of its faction at a spawn point
    for t, (sx, sy) in zip(teams, spawns):
        colonies.append((FACTION_COLONY[t["faction"]], t["id"], sx, sy))

    # rule overrides
    rules_txt = open(os.path.join(folder, "rules.yaml"), encoding="utf-8").read() if os.path.exists(os.path.join(folder, "rules.yaml")) else ""
    pirates = "-PirateSpawner:" not in rules_txt
    flyers = set()
    if TILESET_FLYER.get(tileset):
        flyers.add(TILESET_FLYER[tileset])
    for m in re.finditer(r"^\t(-?)CreepFlyerSpawner@(\w+):", rules_txt, re.M):
        if m.group(1) == "-":
            flyers.discard(m.group(2))
        else:
            flyers.add(m.group(2))
    flyer_kinds = [FLYERS[f] for f in sorted(flyers) if f in FLYERS]
    bot_delay = 6.0
    sp = os.path.join(folder, "script.lua")
    if os.path.exists(sp):
        m = re.search(r"normal = (\d+)", open(sp, encoding="utf-8").read())
        if m:
            bot_delay = float(m.group(1))

    # naming
    m = re.match(r"^(\d+)\) ?(.*)$", title)
    if m:
        number = int(m.group(1))
        display = m.group(2).strip()
        cat = "campaign"
        fname = f"{number:03d}_{slug(display)}.ron"
    elif category == "conquest":
        number = None
        display = title
        cat = "conquest"
        fname = f"skirmish_{slug(display)}.ron"
    else:
        number = None
        display = title
        cat = "custom"
        fname = f"custom_{slug(display)}.ron"
    bots = [t for t in teams if not t["human"]]
    desc = {
        "campaign": f"Campaign level {number}: {display}. You play {human['name']} ({human['faction']}) against " + ", ".join(f"{t['name']} ({t['faction']})" for t in bots) + ".",
        "conquest": f"Skirmish map {display}: you are the {human['faction']} at the first start position against {len(bots)} bots.",
        "custom": f"Custom mission {display}. You play {human['name']} ({human['faction']}) against " + ", ".join(f"{t['name']} ({t['faction']})" for t in bots) + ".",
    }[cat]
    desc += f" Converted from the OpenSA map by {author}." if author else " Converted from OpenSA map data."
    seed = int(hashf(name) * 2**31) + 1

    lines = ["// Converted from OpenSA mods/sa/maps/%s by tools/convert_opensa_maps.py - edit freely." % name, "("]
    lines.append(f"    name: {ron_str(display)},")
    lines.append(f"    width: {bw},")
    lines.append(f"    height: {bh},")
    lines.append(f"    tileset: {ron_str(tileset)},")
    lines.append(f"    seed: {seed},")
    lines.append(f"    category: {ron_str(cat)},")
    lines.append(f"    number: {'Some(%d)' % number if number is not None else 'None'},")
    lines.append(f"    author: {ron_str(author)},")
    lines.append(f"    description: {ron_str(desc)},")
    if camera:
        lines.append(f"    camera: Some(({camera[0]:.1f}, {camera[1]:.1f})),")
    lines.append("    terrain: [],")
    lines.append("    obstacles: [")
    for kind, px, py, r, yaw, sc in obstacles:
        lines.append(f"        (kind: {ron_str(kind)}, pos: ({px:.1f}, {py:.1f}), radius: {r}, yaw: {yaw:.2f}, scale: {sc:.2f}, blocking: true),")
    lines.append("    ],")
    lines.append("    colonies: [")
    for kind, team, px, py in colonies:
        lines.append(f"        (colony: {ron_str(kind)}, team: {team}, pos: ({px:.1f}, {py:.1f})),")
    lines.append("    ],")
    lines.append("    units: [")
    for kind, team, px, py in units:
        lines.append(f"        (unit: {ron_str(kind)}, team: {team}, pos: ({px:.1f}, {py:.1f}), count: 1, spread: 0.0),")
    lines.append("    ],")
    lines.append("    teams: [")
    for t in teams:
        ctrl = "Human" if t["human"] else "Bot"
        lines.append(f"        (id: {t['id']}, name: {ron_str(t['name'])}, color: {ron_str(t['color'])}, controller: {ctrl}, bot_profile: {ron_str('' if t['human'] else 'medium')}),")
    lines.append("    ],")
    lines.append("    rules: (")
    lines.append("        melee_can_damage_colonies: false,")
    lines.append("        unit_cap: Some(150),")
    lines.append(f"        flyers: {'true' if flyer_kinds else 'false'},")
    lines.append("        flyer_kinds: [" + ", ".join(ron_str(k) for k in flyer_kinds) + "],")
    lines.append("        flyer_interval: 45.0,")
    lines.append(f"        pirates: {'true' if pirates else 'false'},")
    lines.append("        pirate_interval: 50.0,")
    lines.append(f"        bot_delay: {bot_delay:.1f},")
    lines.append("    ),")
    lines.append("    // per-cell terrain: '.' clear, 'r' rock, 'v' vegetation, 'w' water (one row per line)")
    lines.append("    cells: Some(\"" + "\\n".join(rows) + "\"),")
    lines.append(")")
    with open(os.path.join(OUT, fname), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return fname, display, cat, len(colonies), len(units), len(obstacles), len(teams), unknown


maps_dir = os.path.join(MOD, "maps")
done = []
for folder in sorted(os.listdir(maps_dir)):
    if folder == "shellmap" or (ONLY and folder not in ONLY):
        continue
    path = os.path.join(maps_dir, folder)
    if not os.path.exists(os.path.join(path, "map.bin")):
        continue
    res = convert(path)
    done.append(res)
    print(f"{res[0]:<44} colonies {res[3]:>3} units {res[4]:>3} plants {res[5]:>4} teams {res[6]} unknown-tiles {res[7]}")
print(f"{len(done)} maps written to {OUT}")
if skipped:
    print("actor types not converted:", skipped)
