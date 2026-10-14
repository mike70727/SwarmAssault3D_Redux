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
3. **Melee bugs attack colonies single file** (corrected 2026-10-14; OpenSA's
   `InvalidTargets: Colony` and its "Cannot harm colonies" description are OpenSA's own, not the
   original's). In the original program the four biters (Ant Soldier FUN_00402e90, Bull Ant
   FUN_004073a0, Savage Scorpion FUN_0040bcd0, Black Widow FUN_0040e8f0) handle an attack order on
   a colony (type flag 0xffff, set by every colony's start-up routine) by walking to it in their
   "mode 20" instead of spreading round it, so an attack forms a line at one stretch of wall that
   the turrets pick off one by one (Mike, from playing it: "they all lined up in a straight line").
   No code of the biters damages the colony there, though: a colony takes damage only from impact
   objects (see the audit below), so in the original the line mostly stood and was shot. Ours (a
   hybrid, Mike's choice): each team's melee bugs share one spot per colony (`World::siege_slot`);
   the three nearest bite side by side, the rest wait in a straight line behind and step up as the
   front falls.
4. **Colonies have automatic turrets** that fire at enemy ground units (and air) in range and never
   at colonies. Turret count per family in OpenSA: Ant 2, Beetle 1, Spider 2, Scorpion 1 (two barrels),
   Wasp 1. Turrets rotate (16 facings in the sprites) and have a 2-frame firing animation.
5. **Colony capture flow** (`Colony.cs`, `DefeatedColony.cs`, `ColonyBit.cs`, `TakeColonyBitOnIdle.cs`):
   - A colony reduced to 0 HP is replaced by a neutral, invulnerable "defeated/unclaimed colony".
   - After `BitFireDelay` (75 ticks = 3.0 s) it launches `NumberOfBits` (9; the original: 11, used
     since 2026-10-14) colony bits to random free tiles in an annulus 5..10 cells away, with an
     explosion effect per bit.
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
   build duration (Soldier 125 ticks = 5 s, Grenadier 200 ticks, Bazooka 350 ticks in OpenSA). OpenSA
   gives ant colonies a -25% breeding time bonus; the original does not (see the audit below: each
   team colour breeds one family faster, and a colony rests 2 s after each bug). Produced units leave
   through an exit cell and go to a rally point.
9. **Sprite animation layout** (sequences yaml + decoded frames): 8 facings; faction units have
   idle (1 frame x 8), attack (2 x 8), move (3 x 8) and 2 death frames = 50 frames; wasp sonic has no
   separate attack frames (34); neutral flyers have 26 frames.
10. **Paralysis**: Wasp Paralysis arrows do no damage, paralyse ground units for 200 ticks (8 s) in a
    2-cell radius; paralysed units cannot move, attack or be targeted normally. Cannot target colonies,
    plants or other wasps.
11. **Beetle Shrapnel** fires 10 grenade-like projectiles around itself (3-cell range, 5000 inaccuracy).
12. **Terrain speed**: ground units move at 100% on clear ground, 75% on rock, 50% on vegetation;
    wasps ignore terrain (100% everywhere, can cross water). The original does the same (part 2
    of the audit below).
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

## OpenSA against the original program (2026-10-14)

Mike: "we're trying to be original, go with the original game, not the OpenSA" - and keep a hybrid
where OpenSA's rule makes the better game. Each OpenSA rule we used, checked against the decompiled
original (`qa/re`), with the decision:

| Rule | OpenSA (what we had) | The original | Decision |
|---|---|---|---|
| Walking speed | close to the original, 1-15% fast (Pirate Grenadier 35%) | each unit's start-up routine sets it: `FUN_00425d70(unit, speed px/s, ...)`, 24 px a cell: Ant Soldier 60, Grenadier 50, Bazooka 40, Lady Bug 50, Shrapnel Beetle 45, Cannon Beetle 30, Black Widow 80, Spider Sniper 50, Missile Spider 50, Savage Scorpion 55, Spear Gun 45, Ninja 60, Assault Wasp 110, Paralysis Wasp 75, Sonic Wasp 90, Bull Ant 60, Pirate Grenadier 40; diagonals x0.707 | original |
| Breeding time | the original's, but Ant Soldier 5 s | table at 0x47bb28 (ms per colour, family, button): ants 4/8/14, beetles 8/18/28, spiders 8/18/22, scorpions 10/20/30, wasps 10/14/22 | original |
| Breeding bonus | every ant colony 25% faster | none for ants; each team colour breeds one family faster: yellow wasps 7/10/16, red spiders 6/14/17, green ants 3/6/10, blue beetles 6/12/21, scorpions never (team index 0-3 = yellow, red, green, blue: the colony name table at 0x4900c0) | original (`rules.breeding_specialities`, `build_time_speciality`) |
| Pause after each bug | none | 2000 ms (`FUN_00414d90`); a new bug appears at the colony's Creation Point and walks to its Exit Point | original (`rules.breed_pause`) |
| Bits of a fallen colony | 9 | the owner is decided after 11 bits (`FUN_00414b70`) | original (the five colonies; OpenSA's boosters keep 9) |
| Tied bits | neutral | the earliest colour of yellow, red, green, blue, neutral wins | **hybrid: OpenSA's neutral** (no colour favoured) |
| Melee against colonies | barred | biters walk to the wall and line up (mode 20) but no code of theirs damages a colony: a colony takes damage only from impact objects (type 90000, message 12000/13100) | **hybrid: they line up and the front bites** (Mike's choice) |
| Health of a captured colony | 25% | apparently none refilled: it comes back empty and heals while not breeding (not certain) | **hybrid: OpenSA's 25%** |
| Unit cap | none (ours: 60 a team) | none found in the breeding code | **kept: 60** |
| Turrets against flyers | yes | yes: turrets skip only colonies and their own team | same |

## OpenSA against the original program, part 2 (2026-10-14)

The rest of the rules, checked the same way (decompiled program; frame timings and script lines of
`Game\Game.ANI`; notes with function names and line numbers in `qa/re/audit_part2_findings.md`):

| Rule | OpenSA (what we had) | The original | Decision |
|---|---|---|---|
| Attack rate | a fixed reload per weapon; our longer 3-D attack clips slowed biters to a bite every 0.45 s | `Game.ANI` frames carry a duration in ms and script lines; a "Damage" or "Fire Point" frame delivers one hit. Biters and machine guns loop their 2-frame attack animation (Ant Soldier 150+150 ms: a bite every 0.3 s; Lady Bug 0.2 s; Assault Wasp 0.1 s; Sonic Wasp 0.14 s). Every other shooter plays it once and then waits `rand() % A + B` ms: Grenadier 1.0-1.4 s a shot, Bazooka 1.1-2.1, Cannon Beetle 0.8-1.5, Shrapnel Beetle 0.3-0.8, Sniper 0.4-1.1, Missile Spider 0.7-2.2, Spear Gun 0.6-1.4, Ninja 0.22-0.62, Paralysis Wasp 0.9-2.4, Pirate Grenadier 1.0-1.3; turrets: ant 0.2, wasp 0.12, beetle 0.65-1.65, spider 0.6-1.2, scorpion 0.6-1.1 | **original** (`reload` + `reload_jitter`; the 3-D attack clip plays faster when the original hits sooner: `UnitDef::attack_time`) |
| Terrain slowing | 75% on rough ground, 50% in vegetation, wasps unaffected | the same: `FUN_00428b10` (x0.75 / x0.5 by cell class) in the ground units' mover; the wasps' mover never calls it | same |
| Idle units | scanned 4 times a second; only "aggressive" units (biters) chased, within a leash; the others scanned half their range and held their ground | every unit has a sensor of its own radius (Soldier 9 cells, Grenadier 7, Bazooka 9, Lady Bug 8, Shrapnel 8, Cannon 14, Black Widow 12, Sniper 16, Missile 18, Savage 10, Spear Gun 16, Ninja 14, Assault Wasp 15, Paralysis 15, Sonic 10, Bull Ant 9, Pirate Grenadier 7) that looks once a second while the unit is idle. Biters take on bugs and creatures, never a colony or a flyer; every other unit takes on whatever its sensor finds, enemy colonies and flyers too; colony turrets anything but colonies. A unit chases what it took on until it is dead or gone | **original** (`scan_range`, `rules.auto_target_interval` 1 s; no leash) |
| Friendly fire | splash skipped the shooter's own side (but for the creatures') | the collision system pairs objects by their collision boxes and never tests teams, and a unit takes the damage of any impact that touches it (a paralysis impact freezes it): your own grenades, shells, shrapnel and paralysis arrows hurt your own bugs. OpenSA does the same (OpenRA's warheads hit every side by default) | **original** for bugs. Colonies take any impact too, their own side's included; ours still spare their own colony (left to Mike) |
| Neutral flyers | can be shot down | can be shot while over the map (the "untouchable" flag is cleared at the start of a pass and set again off the map), by shooters and colony turrets; biters ignore them (Mike, who played it: "the shooters did shoot down the bugs"). Each of the level's flyers waits off the map between passes (Dragonfly 30-60 s, Desert Fly 20-40, Spawn Moth 15-35, Flying Machine 10-40, the first pass alike); one shot down never comes back. The Flying Machine drops a gobstopper every 0.5-2.0 s | **original** (`FlyerDef::pass_wait`, `first_pass`, `interval_jitter`; per-flyer slots in the level's pools) |
| Death Lolly / Seed Ball | set off within 2 / 5 cells by creatures and colonies | sensor 1 (the cells next to it) / 6, creatures only | **original** |
| Thorn Bush, Popcorn Plant | range 6, a thorn every 1.2 s; both shot colonies | Thorn Bush sensor 7, a thorn every 0.4-1.2 s; neither takes on colonies (the Choc Freckle does) | **original** |
| Ant hole | 1-6 pirates every ~50 s from the start: 45% Bull Ant, 45% Pirate Grenadier, 10% Bazooka | the first group 30-60 s in, then every 30-90 s; 1-6 a group, Bull Ant or Pirate Grenadier at even odds | **original** (one ant hole a level: our levels do not record how many holes the original level had) |
| Plants placed by the level / spawned | a pool tops itself up every few seconds | a placed plant is there from the start; the level's spawner plants each appear 10-30 s in (10-40 s for the Choc Freckle and Death Lolly), regrow 10-30 s after dying, and a spawner Thorn Bush plants a new bush nearby (49% every 10-30 s) | **not yet** (the pools keep OpenSA's timing) |
| Victory | one team owns every colony and the others have no units left | the same: an 8x8-cell grid counts each team's colonies and units; a team wins when no other team has either (neutral colonies count, creatures do not); the sign comes 5 s later | same |
| Defeat | told at once ("Keep watching" offered) | no defeat of its own: a wiped-out player watches until one team is left | **kept: told at once** (waiting for the computer players helps nobody) |

## Assumptions / provisional behaviour (clearly labelled in code and data)

A1. **Statistic values**: health, damage, range, speed, breeding time, attack rate and sensor radius
    are the original's (above). The rest (projectile speeds, inaccuracy, splash radii) comes from
    OpenSA, converted to cells/seconds. Everything can be edited in `assets/data/units.ron` and
    `assets/data/colonies.ron`.
A2. **Continuous breeding**: the original game (as remembered from descriptions) lets a colony breed a
    chosen unit type continuously. We implement "breed the selected type repeatedly while below the
    per-team unit cap". OpenSA uses a click-to-queue model; the original UI is not verifiable here.
A3. **Unit cap**: neither OpenSA nor the original's breeding code has one; we add a configurable cap
    (default 60 per team) to keep battles bounded (kept on purpose, 2026-10-14).
A4. **Colony bit pickup radius** is 0.6 cells (OpenRA crushing semantics use cell occupancy). Provisional.
A5. **Bit expiry ownership**: expired bits count for neutral exactly as in OpenSA.
A6. **Map flag** `melee_can_damage_colonies` (the Stage 2/3 demo maps set it) is no longer needed:
    melee weapons may target colonies everywhere since 2026-10-14 (item 3). The flag still lets any
    other weapon without `colony: true` hurt colonies on the maps that set it.
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
