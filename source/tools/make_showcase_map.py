#!/usr/bin/env python3
"""Write the model showcase map: every unit in the four team colours, every colony, every prop.

Usage: tools/make_showcase_map.py [out.ron]   (default: tools/qa/showcase.ron)

Run the game on it with the simulation paused, then point the camera at a row:
    swarm_assault_3d --map tools/qa/showcase.ron --paused --focus X,Y --zoom 9 --screenshot-after 3 --quit-after 4
The map is not in assets/data/maps, so it never shows up in the level list. `showcase_positions.txt`
next to it lists the focus point of every model.
"""
import os
import sys

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa", "showcase.ron")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

UNITS = [
    "ant_soldier", "ant_grenadier", "ant_bazooka",
    "beetle_ladybug", "beetle_shrapnel", "beetle_cannon",
    "spider_black_widow", "spider_sniper", "spider_missile",
    "scorpion_savage", "scorpion_spear_gun", "scorpion_ninja",
    "wasp_assault", "wasp_paralysis", "wasp_sonic",
]
NEUTRALS = ["neutral_bull_ant", "neutral_pirate_grenadier", "neutral_dragonfly", "neutral_desert_fly", "neutral_spawn_moth", "neutral_flying_machine"]
COLONIES = ["colony_ant", "colony_beetle", "colony_spider", "colony_scorpion", "colony_wasp"]
PROPS = ["rock_large", "rock_small", "mushroom", "flower", "grass_tuft", "candy_jelly_bean", "candy_gumnut", "candy_choc_chip", "candy_smarty", "candy_jaffa"]
TEAMS = [(1, "Yellow", "#E8C547"), (2, "Red", "#CA3131"), (3, "Green", "#57AC49"), (4, "Blue", "#4E7FD1")]

W, H = 120, 120
units, colonies, obstacles, positions = [], [], [], []
# faction units: one row per unit, one column per team colour (4 cells apart)
for r, u in enumerate(UNITS):
    y = 6 + r * 4
    for c, (tid, _, _) in enumerate(TEAMS):
        x = 6 + c * 4
        units.append((u, tid, x, y))
    positions.append((u, 12.0, y))
# neutrals (team 0) in a fifth column block
for r, u in enumerate(NEUTRALS):
    y = 6 + r * 4
    units.append((u, 0, 26, y))
    positions.append((u, 26.0, y))
# colonies: one row per family, one column per team colour, plus the neutral one (team 0)
for r, col in enumerate(COLONIES):
    y = 10 + r * 12
    for c, (tid, _, _) in enumerate(TEAMS + [(0, "Neutral", "")]):
        colonies.append((col, tid, 44 + c * 12, y))
    positions.append((col, 68.0, y))
# props in a row along the bottom
for i, p in enumerate(PROPS):
    x, y = 6 + i * 5, 72
    obstacles.append((p, x, y))
positions.append(("props (rock_large ... candy_jaffa, 5 cells apart)", 28.0, 72))

lines = [
    "// Model showcase map written by tools/make_showcase_map.py: every unit in the four team colours,",
    "// every colony and every prop. Run with --paused (see the script) - nothing here is a level.",
    "(",
    '    name: "Model Showcase",',
    f"    width: {W},",
    f"    height: {H},",
    '    tileset: "normal",',
    "    seed: 7,",
    '    category: "demo",',
    "    number: None,",
    '    author: "tools/make_showcase_map.py",',
    '    description: "Every model of the game, for screenshots.",',
    "    camera: Some((12.5, 10.5)),",
    "    terrain: [],",
    "    obstacles: [",
]
for kind, x, y in obstacles:
    lines.append(f'        (kind: "{kind}", pos: ({x + 0.5:.1f}, {y + 0.5:.1f}), radius: 0.5, yaw: 0.0, scale: 1.0, blocking: true),')
lines += ["    ],", "    colonies: ["]
for kind, team, x, y in colonies:
    lines.append(f'        (colony: "{kind}", team: {team}, pos: ({x + 0.5:.1f}, {y + 0.5:.1f})),')
lines += ["    ],", "    units: ["]
for kind, team, x, y in units:
    lines.append(f'        (unit: "{kind}", team: {team}, pos: ({x + 0.5:.1f}, {y + 0.5:.1f}), count: 1, spread: 0.0),')
lines += ["    ],", "    teams: ["]
for tid, name, color in TEAMS:
    ctrl = "Human" if tid == 1 else "Bot"
    lines.append(f'        (id: {tid}, name: "{name}", color: "{color}", controller: {ctrl}, bot_profile: "{"" if tid == 1 else "medium"}"),')
lines += [
    "    ],",
    "    rules: (",
    "        melee_can_damage_colonies: false,",
    "        unit_cap: Some(400),",
    "        flyers: false,",
    "        flyer_kinds: [],",
    "        flyer_interval: 45.0,",
    "        pirates: false,",
    "        pirate_interval: 50.0,",
    "        bot_delay: 9999.0,",
    "    ),",
    ")",
]
with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(lines) + "\n")
with open(os.path.join(os.path.dirname(OUT), "showcase_positions.txt"), "w", encoding="utf-8", newline="\n") as f:
    f.write("model  focus_x,focus_y   (pass as --focus X,Y; --zoom 7..12 for units, 18..24 for colonies)\n")
    for name, x, y in positions:
        f.write(f"{name}  {x:.1f},{y:.1f}\n")
print("wrote", OUT, len(units), "units", len(colonies), "colonies", len(obstacles), "props")
