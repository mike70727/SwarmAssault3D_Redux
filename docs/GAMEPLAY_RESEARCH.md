# Gameplay research: verified mechanics vs. assumptions

Research date: 2026-10-13. The original game is *Swarm Assault* (Gee Whiz! Entertainment, 1999).
No copy of the original executable or its data files is available in this environment, so nothing
below was measured in the original game itself.

## Sources actually consulted

| Source | Status | What it provided |
|---|---|---|
| Reference pack `READ_ME.txt`, `Sources.txt`, `Unit_Roster.csv` | read | roster, naming, sprite prefixes, provenance |
| OpenSA (OpenRA mod re-creating Swarm Assault), git clone of commit `b61363d9` (2023-09-29), `mods/sa/rules`, `weapons`, `sequences`, `OpenRA.Mods.OpenSA/Traits` | read in full for ants, colonies, creeps; skimmed for the rest | unit/colony statistics as re-implemented by OpenSA, colony capture logic (source code), victory logic (source code), sprite sequence layout |
| swarm-assault.fandom.com wiki | **blocked** by the proxy (403) | nothing |
| mobygames.com screenshots | **blocked** (also noted as blocked in the pack) | nothing |
| Gameplay footage (YouTube etc.) | **not reachable** from this environment | nothing |

Because the wiki and footage could not be reached, the main source of mechanics is the OpenSA
re-implementation. OpenSA is a fan project; its numbers are its authors' reconstruction and may have
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

## Assumptions / provisional behaviour (clearly labelled in code and data)

A1. **Statistic values** (HP, speed, damage, range, reload, build time) are taken from OpenSA and
    converted to cells/seconds. They are *not* verified against the original. They can be edited in
    `assets/data/units.ron` and `assets/data/colonies.ron`.
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
