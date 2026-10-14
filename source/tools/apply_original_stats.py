#!/usr/bin/env python3
"""Set every creature's and colony's health, and every weapon's damage and range, to the original
Swarm Assault's own values (Mike, 2026-10-14: "I want the range and damage to be the same as the base
game. For the creatures and the turrets on the buildings.").

Found by decompiling the original program (Swarm Assault.exe of the player's copy, read as data,
never run) with Ghidra; the routine each value comes from is noted below and in the data files'
`source` strings. How the original keeps them:
  * a creature's routine calls the damage routine FUN_0041afb0(world, unit, damage, MAX HEALTH, ...)
    (flyers FUN_0041b8a0) and starts its attack with FUN_004264f0(world, unit, target, RANGE in cells);
  * a projectile that arrives turns itself into a damage actor (type 90000) carrying its DAMAGE in
    field 0x2c; bites send message 0x82 with the damage as its value;
  * a colony starts with field 0xdb = health and heals +n every 500 ms while not breeding; its
    turrets check FUN_00428da0(..., RANGE, 1) and fire one of the creature weapons.
Values without an original counterpart (our standalone level turrets, boosters, the tesla coil)
keep OpenSA's numbers scaled by the factor the colonies measured (original / OpenSA = 1/40).

usage: apply_original_stats.py [assets/data]   (edits units.ron and colonies.ron in place)
"""
import os
import re
import sys

DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "assets", "data")

# weapon id -> fields to set, and where the original keeps them
WEAPONS = {
    "ant_bite": ({"damage": 4, "range": 1.0}, "original: Ant Soldier FUN_00402e90 bites with message 0x82 value 4, attack range 1"),
    "ant_grenade": ({"damage": 30, "range": 6.0}, "original: WeaponGrenade FUN_00433190 damage 30; Ant Grenadier FUN_00402230 range 6"),
    "ant_rocket": ({"damage": 40, "range": 9.0}, "original: WeaponRocket FUN_00433ee0 damage 40; Ant Bazooka FUN_004015e0 range 9"),
    "beetle_mg": ({"damage": 8, "range": 6.0}, "original: WeaponMiniGun FUN_004335c0 damage 8; Lady Bug FUN_004046a0 range 6"),
    "beetle_shrapnel": ({"damage": 15, "range": 4.0, "volley": 8},
                        "original: WeaponShrapnel FUN_00433960 damage 15 a fragment; Shrapnel Beetle FUN_00405260 throws 8, range 4"),
    "beetle_cannon": ({"damage": 40, "range": 14.0}, "original: WeaponCannon FUN_004332f0 damage 40; Cannon Beetle FUN_004039e0 range 14"),
    "spider_bite": ({"damage": 8, "range": 1.0}, "original: Black Widow FUN_0040e8f0 bites with message 0x82 value 8, range 1"),
    "spider_sniper": ({"damage": 30, "range": 14.0}, "original: WeaponSniper FUN_00433860 damage 30; Spider Sniper FUN_00410090 range 14"),
    "spider_missile": ({"damage": 60, "range": 18.0}, "original: WeaponMissile FUN_00433b60 damage 60; Missile Spider FUN_0040f450 range 18"),
    "scorpion_sting": ({"damage": 12, "range": 1.0}, "original: Savage Scorpion FUN_0040bcd0 stings with message 0x82 value 12, range 1"),
    "scorpion_spear": ({"damage": 30, "range": 15.0}, "original: WeaponSpear FUN_00434680 damage 30; Spear Gun Scorpion FUN_0040c830 range 15"),
    "scorpion_star": ({"damage": 50, "range": 12.0}, "original: WeaponStar FUN_004348a0 damage 50; Ninja Scorpion FUN_0040d480 range 12"),
    "wasp_mg": ({"damage": 8, "range": 10.0}, "original: WeaponGun FUN_00433450 damage 8; Assault Wasp FUN_00410d50 range 10"),
    "wasp_paralysis": ({"damage": 0, "range": 15.0},
                       "original: WeaponArrow FUN_004342e0 carries 8000 (ms of paralysis), no damage; Paralysis Wasp FUN_004117c0 range 15"),
    "wasp_sonic": ({"damage": 20, "range": 8.0}, "original: WeaponSonic FUN_00434130 damage 20; Sonic Wasp FUN_004122e0 range 8"),
    "bull_bite": ({"damage": 6, "range": 1.0}, "original: Bull Ant FUN_004073a0 bites with message 0x82 value 6, range 1"),
    "pirate_grenade": ({"damage": 30, "range": 6.0}, "original: WeaponGrenade damage 30; Pirate Grenadier FUN_00406820 range 6"),
    "dragonfly_bomb": ({"damage": 160}, "original: WeaponBrakeBomb FUN_004344d0 damage 160"),
    "fly_bomb": ({"damage": 80}, "original: WeaponBounceBomb FUN_00434ed0 damage 80"),
    "moth_puff": ({"damage": 15}, "original: WeaponPuffball FUN_004351c0 damage 15"),
    "machine_gobstopper": ({"damage": 40}, "original: WeaponGobstopper FUN_00435830 damage 40"),
    "plant_popcorn": ({"damage": 5}, "original: WeaponWhip FUN_004355c0 damage 5"),
    "plant_thorn": ({"damage": 20}, "original: WeaponThorn FUN_00434b70 damage 20"),
    "plant_puff": ({"damage": 15}, "original: WeaponPuffball FUN_004351c0 damage 15"),
    "plant_freckle": ({"damage": 15}, "original: WeaponFreckle FUN_00434d60 damage 15"),
    "plant_lolly_blast": ({"damage": 80}, "original: Death Lolly FUN_00408dd0 blast damage 80"),
    "popcorn": ({"damage": 5}, "original: WeaponWhip damage 5 (the popcorn plant level structure)"),
    "tesla_bolt": ({"damage": 28}, "no original counterpart: OpenSA-scale value / 50 (the creatures' ratio)"),
    "colony_ant_mg": ({"damage": 8, "range": 10.0},
                      "original: ColonyAntWeapon FUN_00413000 / FUN_004133c0 fires WeaponMiniGun (8), range 10 (a machine gun)"),
    "colony_beetle_cannon": ({"damage": 40, "range": 10.0},
                             "original: ColonyBeetleWeapon FUN_00413d90 / FUN_00414110 fires WeaponCannon (40), range 10"),
    "colony_spider_sniper": ({"damage": 30, "range": 14.0},
                             "original: ColonySpiderWeapon FUN_004179c0 / FUN_00417d40 fires WeaponSniper (30), range 14"),
    "colony_scorpion_spear": ({"damage": 30, "range": 18.0},
                              "original: ColonyScorpionWeapon FUN_00416a20 / FUN_00416da0 fires two WeaponSpear (30 each), range 18"),
    "colony_wasp_mg": ({"damage": 8, "range": 10.0},
                       "original: ColonyWaspWeapon FUN_00418870 / FUN_00418c30 fires WeaponGun (8, the Assault Wasp's own chain gun), range 10"),
}

# unit id -> health (and for plants the decay that keeps their lifetime)
UNITS = {
    "ant_soldier": (100, "FUN_00402890 / FUN_00402e90"), "ant_grenadier": (80, "FUN_00401c50 / FUN_00402230"),
    "ant_bazooka": (140, "FUN_00401000 / FUN_004015e0"), "beetle_ladybug": (150, "FUN_00404060 / FUN_004046a0"),
    "beetle_shrapnel": (400, "FUN_00404c80 / FUN_00405260"), "beetle_cannon": (150, "FUN_00403400 / FUN_004039e0"),
    "spider_black_widow": (300, "FUN_0040e310 / FUN_0040e8f0"), "spider_sniper": (120, "FUN_0040fab0 / FUN_00410090"),
    "spider_missile": (250, "FUN_0040ee70 / FUN_0040f450"), "scorpion_savage": (350, "FUN_0040b6f0 / FUN_0040bcd0"),
    "scorpion_spear_gun": (170, "FUN_0040c250 / FUN_0040c830"), "scorpion_ninja": (250, "FUN_0040cea0 / FUN_0040d480"),
    "wasp_assault": (100, "FUN_00410710 / FUN_00410d50"), "wasp_paralysis": (200, "FUN_00411210 / FUN_004117c0"),
    "wasp_sonic": (300, "FUN_00411c90 / FUN_004122e0"), "neutral_bull_ant": (200, "FUN_00406e50 / FUN_004073a0"),
    "neutral_pirate_grenadier": (160, "FUN_004062c0 / FUN_00406820"), "neutral_dragonfly": (1200, "FUN_004078e0 / FUN_00407bd0"),
    "neutral_desert_fly": (600, "FUN_00405d40 / FUN_00406030"), "neutral_spawn_moth": (600, "FUN_004096f0 / FUN_004099e0"),
    "neutral_flying_machine": (500, "FUN_00407ef0 / FUN_00408280"), "plant_popcorn": (600, "FUN_0040af00 / FUN_0040b1d0"),
    "plant_thorn": (500, "FUN_0040a590"), "plant_seedball": (100, "FUN_00409c70 / FUN_0040a030"),
    "plant_freckle": (700, "FUN_00408610"), "plant_lolly_blue": (200, "FUN_00408dd0"), "plant_lolly_orange": (200, "FUN_00408dd0"),
    "plant_lolly_white": (200, "FUN_00408dd0"), "plant_lolly_red": (200, "FUN_00408dd0"),
    "plant_seed": (100, "no original value found: the Seed Ball's 100, withering in the same 10 s"),
}

# colony id -> (health, heal per second, note)
COLONIES = {
    "colony_ant": (2500, 20.0, "original FUN_004127a0: health 2500, +10 every 500 ms while not breeding"),
    "colony_beetle": (3500, 24.0, "original FUN_00413610: health 3500, +12 every 500 ms while not breeding"),
    "colony_spider": (4000, 28.0, "original FUN_00417160: health 4000, +14 every 500 ms while not breeding"),
    "colony_scorpion": (4500, 30.0, "original FUN_00416230: health 4500, +15 every 500 ms while not breeding"),
    "colony_wasp": (5000, 32.0, "original FUN_00418080: health 5000, +16 every 500 ms while not breeding"),
    "turret_ant": (1250, 31.25, None), "turret_beetle": (1250, 31.25, None), "turret_spider": (1250, 31.25, None),
    "turret_scorpion": (1250, 31.25, None), "turret_wasp": (1250, 31.25, None), "turret_tesla": (1250, 31.25, None),
    "popcorn_plant": (600, 8.0, "original: the Popcorn Plant's own 600 health, plants heal 8 a second"),
    "booster_firepower": (1875, 46.9, None), "booster_production": (1875, 46.9, None),
}
SCALED = "no original counterpart (the original's turrets cannot be hit and fall with their colony): OpenSA-scale / 40, the colonies' measured ratio"


def fmt(v):
    """RON float: 8 -> 8.0, 31.25 -> 31.25."""
    s = f"{float(v):.4f}".rstrip("0")
    return s + "0" if s.endswith(".") else s


def entry_span(text, key, section):
    """(start, end) of the `"key": ( ... ),` block inside the `section: {` map, matched by indentation
    (weapon and creature ids can be the same, e.g. beetle_shrapnel)."""
    start = re.search(rf"(?m)^\s*{section}: \{{", text).end()
    m = re.compile(rf'(?m)^(\s*)"{re.escape(key)}": \(\n').search(text, start)
    if not m:
        raise SystemExit(f"entry {key} not found")
    indent = m.group(1)
    end = text.index(f"\n{indent}),", m.end())
    return m.start(), end + len(f"\n{indent}),")


def set_field(block, field, value):
    v = f"{value}" if field == "volley" else fmt(value)
    new, n = re.subn(rf"\b{field}: [0-9.]+", f"{field}: {v}", block, count=1)
    if n == 0:
        raise SystemExit(f"field {field} missing in:\n{block[:200]}")
    return new


def add_source(block, note):
    def repl(m):
        old = m.group(1)
        base = re.split(r"; ORIGINAL VALUES: ", old)[0]
        return f'source: "{base}; ORIGINAL VALUES: {note}"'
    new, n = re.subn(r'source: "((?:[^"\\]|\\.)*)"', repl, block, count=1)
    return new if n else block


def patch(path, section, table, apply):
    raw = open(path, "rb").read()
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8").replace("\r\n", "\n")
    for key, spec in table.items():
        a, b = entry_span(text, key, section)
        text = text[:a] + apply(text[a:b], spec) + text[b:]
    if crlf:
        text = text.replace("\n", "\r\n")
    open(path, "wb").write(text.encode("utf-8"))


def weapon(block, spec):
    fields, note = spec
    for f, v in fields.items():
        block = set_field(block, f, v)
    return add_source(block, note)


def unit(block, spec):
    hp, note = spec
    block = set_field(block, "hp", hp)
    if "decay_per_s" in block:  # the seed: wither in the same 10 s
        block = set_field(block, "decay_per_s", hp / 10.0)
    return add_source(block, f"health {hp} ({note})")


def colony(block, spec):
    hp, regen, note = spec
    block = set_field(block, "hp", hp)
    block = set_field(block, "regen_per_s", regen)
    return add_source(block, note or f"health {hp}, heals {regen}/s: {SCALED}")


if __name__ == "__main__":
    patch(os.path.join(DATA, "units.ron"), "weapons", WEAPONS, weapon)
    patch(os.path.join(DATA, "units.ron"), "units", UNITS, unit)
    patch(os.path.join(DATA, "colonies.ron"), "colonies", COLONIES, colony)
    print(f"set {len(WEAPONS)} weapons, {len(UNITS)} creatures, {len(COLONIES)} colonies and structures to the original's values")
