# Gameplay research: verified mechanics vs. assumptions

Research date: 2026-10-13. The original game is *Swarm Assault* (Gee Whiz! Entertainment, 1999).
Items 1-14 come from the OpenSA re-implementation. Items 15-17 were later checked against the
player's own copy of the original game files (read as data; the original program was never run).

## Sources actually consulted

| Source | Status | What it provided |
|---|---|---|
| Reference pack `READ_ME.txt`, `Sources.txt`, `Unit_Roster.csv` | read | roster, naming, sprite prefixes, provenance |
| OpenSA (OpenRA mod re-creating Swarm Assault), git clone of commit `b61363d9` (2023-09-29), `mods/sa/rules`, `weapons`, `sequences`, `OpenRA.Mods.OpenSA/Traits` | read in full for ants, colonies, creeps; skimmed for the rest | unit/colony statistics as re-implemented by OpenSA, colony capture logic (source code), victory logic (source code), sprite sequence layout |
| swarm-assault.fandom.com wiki | **blocked** by the proxy (403) | nothing |
| mobygames.com screenshots | **blocked** (also noted as blocked in the pack) | nothing |
| Gameplay footage: YouTube uJoW0Qqd1Zk (campaign levels 1-10), frames in `reference/video` | watched | start-up, menus, loading screens, the in-game / game-over menu layout, sidebar, health bars |
| The player's copy of the original (Game.DDF/ANI/SDF, the level files, Text\English.txt, the program's strings) | read as data | creep roster, per-level creep counts, sprites, sounds, portraits, menu pictures and text |

Because the wiki could not be reached and the original program is never run here (the footage shows
the screens, not the numbers), the main source of mechanics is the OpenSA re-implementation. OpenSA is a fan project; its numbers are its authors' reconstruction and may have
been tuned. Every statistic in `assets/data/units.ron` and `assets/data/colonies.ron` is therefore
tagged `source: "opensa"` and must not be described as original Swarm Assault data.

## Verified (present in OpenSA source code or rules, consistent with the reference pack)

Conventions used by OpenSA/OpenRA: 1 cell = 1024 world units; one game tick = 40 ms (25 ticks/s)
at the default game speed; tile size 24x24 px. Our data files convert these into cells and seconds.

1. **Five playable families**: Ants, Beetles, Spiders, Scorpions, Wasps, each with exactly one colony
   building type and three units (light / medium / heavy). The roster in the pack matches
   OpenSA's `*_light/_medium/_heavy` actors. OpenSA's "Parasite" is the original "Paralysis" wasp.
2. **Neutral creatures**: Bull Ant and Pirate Grenadier (pirate ants spawned from ant holes),
   plus four neutral flyers that cannot be ordered (Dragonfly, Desert Fly, Spawn Moth, Flying Machine),
   each tied to a tileset (normal / desert / swamp / candy).
3. **Melee units cannot damage colonies**: Ant Soldier, Spider Black Widow and Scorpion Savage have
   `InvalidTargets: Colony`; their description says "Cannot harm colonies or creep flyers".
4. **Colonies have automatic turrets** that fire at enemy ground units (and air) in range and never
   at colonies. Turret count per family in OpenSA: Ant 2, Beetle 1, Spider 2, Scorpion 1 (two barrels),
   Wasp 1. Turrets rotate (16 facings in the sprites) and have a 2-frame firing animation.
5. **Colony capture flow** (`Colony.cs`, `DefeatedColony.cs`, `ColonyBit.cs`, `TakeColonyBitOnIdle.cs`):
   - A colony reduced to 0 HP is replaced by a neutral, invulnerable "defeated/unclaimed colony".
   - After `BitFireDelay` (75 ticks = 3.0 s) it launches `NumberOfBits` (9) colony bits to random free
     tiles in an annulus 5..10 cells away, with an explosion effect per bit.
   - Each bit lives 500..750 ticks (20..30 s). A unit walking over a bit collects it for its owner.
     Idle units automatically walk to bits within 10 cells.
   - When all 9 bits are resolved (collected or expired; expired bits count for the neutral
     "Creeps" player), the player with the most bits becomes the owner; ties go to neutral. The colony
     is re-created for the new owner with 25% HP.
6. **Colonies regenerate**: `ChangesHealth: Step 100` per tick while below 100% and not producing.
7. **Victory** (`ColonyConquestVictoryConditions.cs`): a player wins when every colony is owned by that
   player (or allies) *and* every enemy has no required units; neutral/defeated colonies must be captured
   first. A human player with no colonies and no units loses immediately.
8. **Production**: colonies produce units of their own family via a production queue with a per-unit
   build duration (Soldier 125 ticks = 5 s, Grenadier 200 ticks, Bazooka 350 ticks in OpenSA). Ant
   colonies get a -25% breeding time faction bonus. Produced units leave through an exit cell and go
   to a rally point.
9. **Sprite animation layout** (sequences yaml + decoded frames): 8 facings; faction units have
   idle (1 frame x 8), attack (2 x 8), move (3 x 8) and 2 death frames = 50 frames; wasp sonic has no
   separate attack frames (34); neutral flyers have 26 frames.
10. **Paralysis**: Wasp Paralysis arrows do no damage, paralyse ground units for 200 ticks (8 s) in a
    2-cell radius; paralysed units cannot move, attack or be targeted normally. Cannot target colonies,
    plants or other wasps.
11. **Beetle Shrapnel** fires 10 grenade-like projectiles around itself (3-cell range, 5000 inaccuracy).
12. **Terrain speed**: ground units move at 100% on clear ground, 75% on rock, 50% on vegetation;
    wasps ignore terrain (100% everywhere, can cross water).
13. **Neutral flyers**: Dragonfly drops bombs left/right while flying over; Desert Fly drops bouncing
    bombs that split; Spawn Moth drops puffs and seeds; Flying Machine drops gobstoppers and spawns a
    pirate grenadier pilot when shot down over land. They fly across the map and cannot be controlled.
14. **Pirate ants** spawn from ant holes in groups of 1..6 (45% bull ant, 45% grenadier, 10% bazooka).

## Neutral creeps: checked against the player's own copy of the original (2026-10-13)

Read from the original files (nothing executed, nothing copied into the package):

15. **The roster** (`Text\English.txt`): Bull Ant, Grenadier, Dragonfly, Desert Fly, Flying Machine,
    Choc Freckle, Death Lolly, Spawn Moth, Popcorn Plant, Seed Ball, Thorn Bush. OpenSA's Venus
    Flytrap, Gumnut and Poison Mushroom are not in it (the original's mushrooms, gumnuts and
    flowers are scenery), so this recreation leaves them out.
16. **Per-level creep counts**: every original level carries a row of "Misc" actors outside the
    playing area (the program's names: MiscWhipPlant 143, MiscDragonfly 101, MiscThornbush 157,
    MiscBigFly 161, MiscPuffball 169, MiscMoth 171, MiscFreckle 172, MiscLollyBomb 176,
    MiscFlyingMachine 180, MiscAntHole 147). Their number is how many of that creep the level has,
    e.g. "Bomber Paradise" 15 dragonflies, "Thorny Issue" 40 thorn bushes, "Weeds" 10 seed balls,
    "Rain" 30 flying machines; level 1 has none. `tools/add_creep_pools.py` writes the counts into
    each map's `rules.creeps`; a dead plant regrows elsewhere and a flyer makes another pass, so the
    level keeps up to that many (the spawn intervals are OpenSA's, which were tuned to these counts).
17. **Sprites, sounds and portraits** exist for each creep (OBWHIPPL, OBPUFFBL, OBTHORNB, FRECKLE,
    OBLOLLY*; WHIPFIRE, PUFFBALLSPAWN, FRECKLEFIRE, BOMBERBUZZ, FLYBUZZ, MOTHFLUTTER,
    FLYINGMACHINE; COLONYNEUTRAL*3D, NAMENEUTRAL*), and the game uses them.

Behaviour from OpenSA's creep-plants.yaml / creep-units.yaml and its C# traits (not verified
against the original program):

18. **Plants** grow for 4-5 s before they can attack, stop attacking below half health
    (OpenSA "injured") and heal 250 HP/s, and occupy their cell.
    - Popcorn Plant: eight homing pellets fired out in every direction at once (AttackRadial), range 6.
    - Thorn Bush: thorns at the nearest enemy, range 6.
    - Seed Ball: while an enemy creature or colony is within 5 cells it splits open every 0.8 s and
      throws six exploding puffs at random spots within 5 cells, plus one seed. A seed withers after
      10 s; one in five becomes a new Seed Ball.
    - Choc Freckle: three lobbed shots aimed round a circle that turns 211 degrees per second
      (AttackVortex), range 3.
    - Death Lolly: blows up (4500 damage to everything within 3 cells) when an enemy creature or
      colony comes within 2 cells, or when killed.
19. **Flyers** cross the map through a random cell on one of eight headings.
    - Dragonfly: brake bombs alternately to its right and left about every 0.4 s for 3.2 s, then a
      1.2 s rest. Each bomb lands about 1.1 cells behind and 1.1 to the side: 8500 damage.
    - Desert Fly: a pair of bouncing bombs every 2.5 s that split into four.
    - Spawn Moth: five puffs and a seed thrown 5 cells behind every 0.84 s.
    - Flying Machine: two bouncing gobstoppers 8.5 cells behind every 0.84 s; shot down over land,
      its pilot (a pirate grenadier) carries on.

## Health, damage and range: the original program's own values (2026-10-14)

Mike: "I want the range and damage to be the same as the base game. For the creatures and the turrets
on the buildings." The original program (`Swarm Assault.exe` of the player's copy, read as data and
decompiled with Ghidra 12.1.2; never run) keeps them in code, not in a data file:

* every creature has a routine that calls the damage routine `FUN_0041afb0(world, unit, damage, MAX
  HEALTH, ...)` (flyers `FUN_0041b8a0`) and starts its attacks with `FUN_004264f0(world, unit, target,
  RANGE)` (range in cells);
* a projectile that reaches its target turns into a damage actor (type 90000) carrying its DAMAGE in
  field 0x2c; bites send message 0x82 with the damage as its value;
* a colony starts at field 0xdb = health and heals +n every 500 ms while it is not breeding; its
  turrets test `FUN_00428da0(..., RANGE, 1)` and fire one of the creature weapons.

| Creature | Health | Range | Damage per hit |
|---|---|---|---|
| Ant Soldier | 100 | 1 | bite 4 |
| Ant Grenadier | 80 | 6 | grenade 30 |
| Ant Bazooka | 140 | 9 | rocket 40 |
| Lady Bug | 150 | 6 | minigun 8 |
| Shrapnel Beetle | 400 | 4 | 8 fragments of 15 |
| Cannon Beetle | 150 | 14 | cannon 40 |
| Black Widow | 300 | 1 | bite 8 |
| Spider Sniper | 120 | 14 | 30 |
| Missile Spider | 250 | 18 | homing missile 60 |
| Savage Scorpion | 350 | 1 | sting 12 |
| Spear Gun Scorpion | 170 | 15 | spear 30 |
| Ninja Scorpion | 250 | 12 | star 50 |
| Assault Wasp | 100 | 10 | gun 8 |
| Paralysis Wasp | 200 | 15 | paralysis for 8 s, no damage |
| Sonic Wasp | 300 | 8 | 20 |
| Bull Ant | 200 | 1 | bite 6 |
| Pirate Grenadier | 160 | 6 | grenade 30 |
| Dragonfly / Desert Fly / Spawn Moth / Flying Machine | 1200 / 600 / 600 / 500 | | brake bomb 160 / bouncing bomb 80 / puffball 15 / gobstopper 40 |
| Popcorn Plant / Thorn Bush / Seed Ball / Choc Freckle / Death Lolly | 600 / 500 / 100 / 700 / 200 | | whip 5 / thorn 20 / puffball 15 / freckle 15 / blast 80; plants heal 8 a second |

| Colony | Health | Heals while not breeding | Turret | Turret range |
|---|---|---|---|---|
| Ant | 2500 | 20 / s | machine gun 8 (the minigun round) | 10 |
| Beetle | 3500 | 24 / s | cannon 40 | 10 |
| Spider | 4000 | 28 / s | sniper 30 | 14 |
| Scorpion | 4500 | 30 / s | two spears of 30 | 18 |
| Wasp | 5000 | 32 / s | the Assault Wasp's chain gun, 8 (CHAINGUN sound; the ant turret's is TURRETMACHINEGUN) | 10 |

OpenSA's ranges were already the original's (except the Shrapnel Beetle: 3, the original 4); its
health and damage were about 50 times the original's with drifting ratios (Shrapnel Beetle 3.8 soldiers
of health instead of 4, colonies 100 000 each instead of 2500-5000). `tools/apply_original_stats.py`
writes the values above into `units.ron` and `colonies.ron`, noting the routine for each. The original's
turrets cannot be hit (they fall with their colony); our standalone level turrets, boosters and tesla coil
have no original counterpart and keep OpenSA's values scaled by the colonies' ratio (1/40). Reload times
are OpenSA's (they follow the original's attack animation timings) and speeds are unchanged.

## Assumptions / provisional behaviour (clearly labelled in code and data)

A1. **Statistic values**: health, damage and range are the original's (above). Speed, reload and build
    time are taken from OpenSA and converted to cells/seconds; they are not verified against the
    original. They can be edited in `assets/data/units.ron` and `assets/data/colonies.ron`.
A2. **Continuous breeding**: the original game (as remembered from descriptions) lets a colony breed a
    chosen unit type continuously. We implement "breed the selected type repeatedly while below the
    per-team unit cap". OpenSA uses a click-to-queue model; the original UI is not verifiable here.
A3. **Unit cap**: OpenSA has none that we found; we add a configurable cap (default 60 per team) to
    keep battles bounded. Provisional.
A4. **Colony bit pickup radius** is 0.6 cells (OpenRA crushing semantics use cell occupancy). Provisional.
A5. **Bit expiry ownership**: expired bits count for neutral exactly as in OpenSA.
A6. **Stage 2/3 demo map flag** `melee_can_damage_colonies: true` lets Ant Soldiers damage colonies so
    that the two-army Ant Soldier battle can actually end in a capture. This *contradicts* verified
    item 3 and is off by default on every other map; the flag is labelled PROVISIONAL in the map file.
A7. **AI**: the original AI behaviour is unknown; ours is a simple "breed, group, attack nearest,
    defend, collect bits" bot. Not claimed to be original.
A8. **Unit dimensions**: an Ant Soldier sprite is about 40 px long in a 24 px tile, so a soldier is
    modelled ~1.5 cells long; colonies occupy a 6x6-cell footprint (OpenSA `Dimensions: 6,6`).
A9. **Sim tick rate**: we simulate at a fixed 30 Hz (OpenSA/OpenRA uses 25 Hz). All OpenSA tick
    values are converted to seconds, so the rate does not change the balance.
A10. **Colony turret damage to air**: OpenSA allows colony turrets to hit air; we follow it.
A11. **Death handling**: dead units play a death animation and leave a corpse for a few seconds
    (original sprites have 2 death frames shown for a long time); duration is an assumption.
A12. **Team colours**: sampled from the Y/R/G/B sprite variants of the reference pack:
    yellow (184,168,72), red (136,40,40), green (56,120,24), blue (56,88,184); neutral units are
    near-black (40,40,40) and neutral colony bodies are grey (200,184,168). Which colour the human
    player gets in the original is not verified; our default is yellow.
