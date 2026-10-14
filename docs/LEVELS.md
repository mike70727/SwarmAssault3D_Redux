# Levels

The game ships the complete level set of the original as reconstructed by the OpenSA project
(an OpenRA-based re-implementation): the 100 campaign levels, 13 custom missions and 11 skirmish
maps, plus the two demo maps made for the early stages. Every level is a plain text file in
`assets/data/maps/` and can be edited.

## How the levels were converted

`tools/convert_opensa_maps.py <OpenSA>/mods/sa` reads each OpenRA map folder (`map.yaml`,
`map.bin`, `rules.yaml`, `script.lua`) and writes one RON map:

* **Terrain**: every cell of the playable area (the map bounds) is converted through the tileset
  templates to Clear / Rock / Vegetation / Water and stored in the map's `cells` grid, so the
  shapes (islands, mazes, rivers, the spiral of level 18) are exact. Water blocks ground units;
  rock and vegetation slow them down as in OpenSA (75 % / 50 %). The ground palette follows the
  tileset (normal, desert, swamp, candy).
* **Players** become teams: the playable player is the human, every `*-ai` player a bot, with the
  OpenSA player colours (hex) and factions; "random" factions are picked deterministically per map.
  On skirmish maps (`Multi0..n`) you are the first player and the others are bots; each player
  starts with a colony of its faction at its start position, as OpenSA's starting-units rule does.
* **Actors**: colonies (`ants_colony` ...), colony turrets (`*_colony_turret`, tesla coils),
  firepower / production boosters, popcorn plants, every placed unit (light / medium / heavy of each
  family, pirates as neutral units), plants as blocking props (grass, flowers, mushrooms and the
  candy decorations), the start camera. Colony positions are the centre of the 6x6 footprint.
* **Rules**: pirate ant holes unless the map removes the spawner, the creep flyers of the map's
  tileset (dragonflies, desert flies, moths, flying machines) with the map's additions and removals,
  and the bot start delay of the mission script (6 s on normal difficulty). Unit cap 150.
* **Victory** follows OpenSA's colony-conquest rule: own every colony, turret and booster on the map
  and destroy every enemy unit; you lose with no colonies and no units. Popcorn plants are neutral
  creatures and do not count.

What is **not** reproduced: the plant spawner (plants growing over time), mission videos, the
difficulty dropdown (bots use the game's "medium" profile; edit `bot_profile` in a map to change
it), special lobby options, and the exact unit mix the OpenSA bots prefer per map (bots breed from
the game's own choice).

Structures added for the levels (see `docs/ASSET_NOTES.md`): stand-alone turrets for each family
(HP 50 000, capturable), the tesla coil (weapon values assumed), the popcorn plant (HP 30 000,
shoots everything within 6 cells, regrows neutral), and the boosters (HP 75 000, 3x2 cells,
+10 % firepower or -10 % breeding time per booster owned).

## Level list

| # | Level | File | Tileset | Size | Teams | Colonies | Turrets | Boosters | Popcorn | Units | Plants |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Colony Defence | `001_colony_defence.ron` | normal | 64x64 | 2 | 1 | 0 | 0 | 0 | 44 | 43 |
| 2 | Defend Your Colony | `002_defend_your_colony.ron` | normal | 64x96 | 2 | 1 | 0 | 0 | 0 | 26 | 40 |
| 3 | Take Neutral Colony | `003_take_neutral_colony.ron` | normal | 64x64 | 1 | 2 | 0 | 0 | 0 | 9 | 50 |
| 4 | Expand Your Empire | `004_expand_your_empire.ron` | desert | 96x64 | 1 | 3 | 0 | 0 | 0 | 8 | 60 |
| 5 | Destroy Enemy | `005_destroy_enemy.ron` | desert | 64x64 | 2 | 3 | 0 | 0 | 0 | 17 | 43 |
| 6 | Expand And Destroy | `006_expand_and_destroy.ron` | normal | 64x96 | 2 | 3 | 0 | 0 | 0 | 21 | 48 |
| 7 | Destroy Enemies | `007_destroy_enemies.ron` | normal | 96x64 | 3 | 5 | 0 | 0 | 0 | 26 | 58 |
| 8 | Little Battle | `008_little_battle.ron` | desert | 128x64 | 3 | 6 | 0 | 0 | 0 | 22 | 122 |
| 9 | Four Teams | `009_four_teams.ron` | normal | 96x96 | 4 | 11 | 0 | 0 | 0 | 20 | 124 |
| 10 | Training Complete | `010_training_complete.ron` | desert | 64x128 | 4 | 13 | 0 | 0 | 0 | 0 | 112 |
| 11 | New World | `011_new_world.ron` | swamp | 96x64 | 3 | 8 | 0 | 0 | 0 | 4 | 59 |
| 12 | Desert Foray | `012_desert_foray.ron` | desert | 96x64 | 4 | 7 | 0 | 0 | 0 | 7 | 38 |
| 13 | Coastal Battle | `013_coastal_battle.ron` | normal | 64x96 | 3 | 5 | 0 | 0 | 0 | 9 | 43 |
| 14 | Road To Victory | `014_road_to_victory.ron` | swamp | 64x128 | 4 | 7 | 0 | 0 | 0 | 20 | 113 |
| 15 | Smiley | `015_smiley.ron` | normal | 96x96 | 2 | 10 | 0 | 0 | 0 | 0 | 116 |
| 16 | Compact | `016_compact.ron` | desert | 64x64 | 4 | 8 | 0 | 0 | 0 | 0 | 38 |
| 17 | Sandwich | `017_sandwich.ron` | desert | 128x64 | 3 | 11 | 0 | 0 | 0 | 0 | 138 |
| 18 | Spiral | `018_spiral.ron` | swamp | 128x128 | 2 | 8 | 0 | 0 | 0 | 12 | 175 |
| 19 | Skirmish | `019_skirmish.ron` | normal | 64x128 | 4 | 11 | 0 | 0 | 0 | 0 | 119 |
| 20 | Yummy | `020_yummy.ron` | candy | 96x96 | 3 | 11 | 0 | 0 | 0 | 0 | 119 |
| 21 | North And South | `021_north_and_south.ron` | desert | 128x96 | 2 | 11 | 0 | 0 | 0 | 0 | 162 |
| 22 | Humble Beginnings | `022_humble_beginnings.ron` | normal | 64x96 | 3 | 8 | 0 | 0 | 0 | 13 | 49 |
| 23 | Weeds | `023_weeds.ron` | swamp | 64x64 | 2 | 7 | 0 | 0 | 0 | 18 | 58 |
| 24 | Circuit | `024_circuit.ron` | normal | 96x96 | 2 | 6 | 0 | 0 | 0 | 0 | 114 |
| 25 | Black Ants! | `025_black_ants.ron` | candy | 64x128 | 4 | 8 | 0 | 0 | 0 | 0 | 143 |
| 26 | Landbridge | `026_landbridge.ron` | desert | 64x128 | 4 | 10 | 0 | 0 | 0 | 0 | 114 |
| 27 | Island Paradise | `027_island_paradise.ron` | swamp | 128x128 | 2 | 10 | 0 | 0 | 0 | 4 | 161 |
| 28 | Into The Fray | `028_into_the_fray.ron` | normal | 96x96 | 3 | 11 | 0 | 0 | 0 | 6 | 124 |
| 29 | Ant Crazy | `029_ant_crazy.ron` | normal | 64x96 | 4 | 10 | 0 | 0 | 0 | 0 | 46 |
| 30 | The Fifth Force | `030_the_fifth_force.ron` | desert | 64x128 | 4 | 9 | 0 | 0 | 0 | 18 | 124 |
| 31 | Ground Warfare | `031_ground_warfare.ron` | desert | 96x128 | 3 | 9 | 0 | 0 | 0 | 0 | 192 |
| 32 | Labyrinth | `032_labyrinth.ron` | candy | 128x128 | 4 | 9 | 0 | 0 | 0 | 0 | 163 |
| 33 | Conquest Of Paradise | `033_conquest_of_paradise.ron` | normal | 128x96 | 2 | 9 | 0 | 0 | 0 | 17 | 82 |
| 34 | A Day In The Field | `034_a_day_in_the_field.ron` | normal | 96x96 | 3 | 9 | 0 | 0 | 0 | 12 | 143 |
| 35 | Love Theme | `035_love_theme.ron` | candy | 128x128 | 2 | 12 | 0 | 0 | 0 | 0 | 153 |
| 36 | Start From Scratch | `036_start_from_scratch.ron` | swamp | 64x128 | 3 | 9 | 0 | 0 | 0 | 34 | 125 |
| 37 | Terror Island | `037_terror_island.ron` | swamp | 64x64 | 2 | 5 | 0 | 0 | 0 | 36 | 58 |
| 38 | They're Everywhere | `038_they_re_everywhere.ron` | normal | 64x96 | 4 | 12 | 0 | 0 | 0 | 0 | 47 |
| 39 | Outpost | `039_outpost.ron` | desert | 128x96 | 2 | 7 | 0 | 0 | 0 | 0 | 166 |
| 40 | The Castle | `040_the_castle.ron` | desert | 96x128 | 2 | 11 | 0 | 0 | 0 | 98 | 154 |
| 41 | The Charge | `041_the_charge.ron` | candy | 64x128 | 2 | 3 | 0 | 0 | 0 | 104 | 129 |
| 42 | Brief Battle | `042_brief_battle.ron` | candy | 128x64 | 3 | 12 | 0 | 0 | 0 | 0 | 148 |
| 43 | Mind Wars | `043_mind_wars.ron` | swamp | 128x128 | 4 | 12 | 0 | 0 | 0 | 0 | 172 |
| 44 | Yin-Yang | `044_yin_yang.ron` | normal | 128x128 | 2 | 12 | 0 | 0 | 0 | 0 | 172 |
| 45 | Highland Battle | `045_highland_battle.ron` | swamp | 128x96 | 3 | 13 | 0 | 0 | 0 | 0 | 226 |
| 46 | Primary Colours | `046_primary_colours.ron` | desert | 64x128 | 3 | 11 | 0 | 0 | 0 | 0 | 119 |
| 47 | Inner Circle | `047_inner_circle.ron` | candy | 96x96 | 4 | 9 | 0 | 0 | 0 | 0 | 106 |
| 48 | Footprints | `048_footprints.ron` | swamp | 64x128 | 2 | 9 | 0 | 0 | 0 | 4 | 169 |
| 49 | Swamp War | `049_swamp_war.ron` | swamp | 96x64 | 2 | 10 | 0 | 0 | 0 | 0 | 94 |
| 50 | The Long March | `050_the_long_march.ron` | normal | 64x128 | 1 | 1 | 0 | 0 | 0 | 14 | 173 |
| 51 | Double Trouble | `051_double_trouble.ron` | candy | 64x96 | 2 | 9 | 0 | 0 | 0 | 14 | 93 |
| 52 | The Web | `052_the_web.ron` | desert | 128x128 | 2 | 17 | 0 | 0 | 0 | 12 | 182 |
| 53 | Morning Melee | `053_morning_melee.ron` | candy | 128x128 | 3 | 15 | 0 | 0 | 0 | 0 | 183 |
| 54 | Memories Of Green | `054_memories_of_green.ron` | swamp | 128x96 | 2 | 4 | 0 | 0 | 0 | 169 | 186 |
| 55 | River Cruise | `055_river_cruise.ron` | desert | 96x128 | 4 | 9 | 0 | 0 | 0 | 2 | 159 |
| 56 | Bomber Paradise | `056_bomber_paradise.ron` | normal | 128x128 | 3 | 13 | 0 | 0 | 0 | 0 | 163 |
| 57 | Blitz | `057_blitz.ron` | swamp | 96x64 | 2 | 14 | 0 | 0 | 0 | 0 | 124 |
| 58 | War Front | `058_war_front.ron` | candy | 64x128 | 2 | 12 | 0 | 0 | 0 | 40 | 193 |
| 59 | Vertical Islands | `059_vertical_islands.ron` | swamp | 96x96 | 3 | 14 | 0 | 0 | 0 | 0 | 130 |
| 60 | Beetle Mania | `060_beetle_mania.ron` | desert | 96x96 | 4 | 8 | 0 | 0 | 0 | 177 | 146 |
| 61 | Retreat | `061_retreat.ron` | normal | 96x128 | 2 | 15 | 0 | 0 | 0 | 0 | 166 |
| 62 | Air Power | `062_air_power.ron` | candy | 128x128 | 3 | 10 | 0 | 0 | 0 | 0 | 194 |
| 63 | Arena | `063_arena.ron` | candy | 96x96 | 4 | 4 | 0 | 0 | 0 | 120 | 119 |
| 64 | Ant Season | `064_ant_season.ron` | swamp | 96x96 | 2 | 0 | 0 | 0 | 0 | 74 | 141 |
| 65 | Thorny Issue | `065_thorny_issue.ron` | desert | 128x64 | 2 | 2 | 0 | 0 | 0 | 19 | 146 |
| 66 | Combat Engineering | `066_combat_engineering.ron` | normal | 128x128 | 3 | 16 | 0 | 0 | 0 | 0 | 183 |
| 67 | Forbidden Planet | `067_forbidden_planet.ron` | candy | 96x128 | 2 | 13 | 0 | 0 | 0 | 96 | 180 |
| 68 | Fortress | `068_fortress.ron` | desert | 128x96 | 2 | 9 | 0 | 0 | 0 | 85 | 152 |
| 69 | Checkmate | `069_checkmate.ron` | swamp | 128x128 | 2 | 16 | 0 | 0 | 0 | 0 | 188 |
| 70 | X | `070_x.ron` | normal | 128x128 | 4 | 20 | 0 | 0 | 0 | 24 | 173 |
| 71 | Microcosm | `071_microcosm.ron` | desert | 64x64 | 2 | 10 | 0 | 0 | 0 | 0 | 55 |
| 72 | Natural Selection | `072_natural_selection.ron` | desert | 64x128 | 3 | 14 | 0 | 0 | 0 | 0 | 138 |
| 73 | The Journey | `073_the_journey.ron` | candy | 128x64 | 2 | 5 | 0 | 0 | 0 | 5 | 148 |
| 74 | Crater | `074_crater.ron` | swamp | 128x128 | 3 | 12 | 0 | 0 | 0 | 0 | 194 |
| 75 | Beetles vs Ants | `075_beetles_vs_ants.ron` | candy | 128x128 | 2 | 16 | 0 | 0 | 0 | 0 | 207 |
| 76 | Amazing! | `076_amazing.ron` | swamp | 96x96 | 2 | 0 | 0 | 0 | 0 | 55 | 147 |
| 77 | Ant Warfare | `077_ant_warfare.ron` | normal | 96x128 | 3 | 12 | 0 | 0 | 0 | 0 | 162 |
| 78 | Carrier Strike | `078_carrier_strike.ron` | normal | 128x96 | 2 | 15 | 0 | 0 | 0 | 129 | 183 |
| 79 | Scorpions vs Beetles | `079_scorpions_vs_beetles.ron` | desert | 128x128 | 2 | 14 | 0 | 0 | 0 | 16 | 166 |
| 80 | Cryptography | `080_cryptography.ron` | candy | 128x96 | 3 | 4 | 0 | 0 | 0 | 49 | 177 |
| 81 | Frozen | `081_frozen.ron` | swamp | 64x128 | 3 | 6 | 0 | 0 | 0 | 40 | 123 |
| 82 | Beetles vs Spiders | `082_beetles_vs_spiders.ron` | candy | 128x128 | 2 | 13 | 0 | 0 | 0 | 0 | 211 |
| 83 | The Gathering | `083_the_gathering.ron` | desert | 96x96 | 4 | 30 | 0 | 0 | 0 | 0 | 138 |
| 84 | Spiders vs Scorpions | `084_spiders_vs_scorpions.ron` | normal | 128x128 | 2 | 16 | 0 | 0 | 0 | 0 | 172 |
| 85 | Rain | `085_rain.ron` | candy | 128x64 | 1 | 2 | 0 | 0 | 0 | 20 | 123 |
| 86 | Memories of Blue | `086_memories_of_blue.ron` | swamp | 128x128 | 2 | 14 | 0 | 0 | 0 | 62 | 154 |
| 87 | Scorpions vs Wasps | `087_scorpions_vs_wasps.ron` | normal | 128x128 | 2 | 13 | 0 | 0 | 0 | 20 | 166 |
| 88 | Wasps vs Spiders | `088_wasps_vs_spiders.ron` | desert | 128x128 | 2 | 13 | 0 | 0 | 0 | 9 | 173 |
| 89 | Vulture Tactics | `089_vulture_tactics.ron` | candy | 96x128 | 3 | 6 | 0 | 0 | 0 | 4 | 151 |
| 90 | Beetles vs Wasps | `090_beetles_vs_wasps.ron` | swamp | 128x128 | 2 | 12 | 0 | 0 | 0 | 8 | 152 |
| 91 | Red Juggernaut | `091_red_juggernaut.ron` | candy | 96x128 | 4 | 18 | 0 | 0 | 0 | 11 | 192 |
| 92 | Ants vs Scorpions | `092_ants_vs_scorpions.ron` | normal | 128x128 | 2 | 13 | 0 | 0 | 0 | 54 | 171 |
| 93 | Serious Danger | `093_serious_danger.ron` | desert | 128x128 | 2 | 11 | 0 | 0 | 0 | 123 | 152 |
| 94 | Ants vs Wasps | `094_ants_vs_wasps.ron` | normal | 128x128 | 2 | 14 | 0 | 0 | 0 | 56 | 210 |
| 95 | Ants vs Spiders | `095_ants_vs_spiders.ron` | swamp | 128x128 | 2 | 13 | 0 | 0 | 0 | 50 | 246 |
| 96 | Eye Of The Storm | `096_eye_of_the_storm.ron` | candy | 96x96 | 4 | 19 | 0 | 0 | 0 | 96 | 119 |
| 97 | Patient Enemy | `097_patient_enemy.ron` | desert | 128x64 | 3 | 16 | 0 | 0 | 0 | 7 | 116 |
| 98 | Apocalypse Now | `098_apocalypse_now.ron` | swamp | 96x128 | 2 | 14 | 0 | 0 | 0 | 109 | 177 |
| 99 | Super Colony | `099_super_colony.ron` | swamp | 128x128 | 2 | 19 | 0 | 0 | 0 | 15 | 201 |
| 100 | Farewell | `100_farewell.ron` | candy | 128x64 | 4 | 0 | 0 | 0 | 0 | 120 | 143 |
| custom | Candy Siege | `custom_candy_siege.ron` | candy | 128x128 | 4 | 49 | 52 | 0 | 0 | 48 | 73 |
| custom | En Garde | `custom_en_garde.ron` | normal | 96x64 | 2 | 6 | 0 | 0 | 0 | 125 | 93 |
| custom | Firepower Boosters | `custom_firepower_boosters.ron` | swamp | 128x128 | 4 | 12 | 34 | 8 | 0 | 65 | 503 |
| custom | Maze | `custom_maze.ron` | desert | 64x64 | 3 | 0 | 4 | 4 | 0 | 48 | 101 |
| custom | Powimang | `custom_powimang.ron` | swamp | 128x128 | 5 | 23 | 6 | 9 | 0 | 12 | 249 |
| custom | Puck-Man | `custom_puck_man.ron` | swamp | 256x256 | 4 | 41 | 22 | 0 | 0 | 17 | 156 |
| custom | Skull | `custom_skull.ron` | normal | 128x128 | 2 | 22 | 14 | 0 | 0 | 26 | 118 |
| custom | Sticks And Stones | `custom_sticks_and_stones.ron` | desert | 40x70 | 2 | 6 | 0 | 0 | 0 | 52 | 29 |
| custom | Sunken Snake | `custom_sunken_snake.ron` | swamp | 128x128 | 4 | 10 | 10 | 0 | 0 | 37 | 335 |
| custom | Swarm Assault | `custom_swarm_assault.ron` | candy | 130x130 | 5 | 25 | 25 | 16 | 0 | 0 | 143 |
| custom | Tough Enemies | `custom_tough_enemies.ron` | swamp | 128x128 | 3 | 18 | 11 | 0 | 0 | 52 | 228 |
| custom | Usual Brawl | `custom_usual_brawl.ron` | normal | 148x148 | 4 | 21 | 14 | 0 | 0 | 53 | 272 |
| skirmish | Boundary Line | `skirmish_boundary_line.ron` | normal | 128x96 | 2 | 9 | 16 | 4 | 0 | 4 | 163 |
| skirmish | Candyland Battleground | `skirmish_candyland_battleground.ron` | candy | 128x128 | 2 | 16 | 0 | 0 | 0 | 0 | 212 |
| skirmish | Desert Battleground | `skirmish_desert_battleground.ron` | desert | 128x128 | 2 | 18 | 0 | 0 | 0 | 0 | 200 |
| skirmish | Narrow Passage | `skirmish_narrow_passage.ron` | normal | 128x128 | 2 | 16 | 0 | 0 | 0 | 0 | 181 |
| skirmish | Skirmish | `skirmish_skirmish.ron` | normal | 125x125 | 2 | 10 | 0 | 0 | 0 | 0 | 166 |
| skirmish | Suprise | `skirmish_suprise.ron` | swamp | 128x128 | 2 | 21 | 0 | 0 | 0 | 0 | 160 |
| skirmish | Swamp Battleground | `skirmish_swamp_battleground.ron` | swamp | 128x128 | 2 | 16 | 0 | 0 | 0 | 0 | 154 |
| skirmish | Swamp Skirmish | `skirmish_swamp_skirmish.ron` | swamp | 128x128 | 2 | 15 | 0 | 0 | 0 | 0 | 219 |
| skirmish | Sweetness | `skirmish_sweetness.ron` | candy | 128x128 | 3 | 23 | 0 | 0 | 0 | 0 | 184 |
| skirmish | Team Battle | `skirmish_team_battle.ron` | swamp | 128x128 | 4 | 17 | 0 | 0 | 0 | 0 | 209 |
| skirmish | Team Brawl | `skirmish_team_brawl.ron` | desert | 128x128 | 4 | 22 | 0 | 0 | 0 | 0 | 216 |
| skirmish | Two Armies | `skirmish_two_armies.ron` | normal | 128x128 | 2 | 12 | 2 | 0 | 0 | 0 | 145 |
| demo | Ant Skirmish | `ants_skirmish.ron` | normal | 64x64 | 2 | 2 | 0 | 0 | 0 | 2 | 23 |
| demo | Five Families | `five_families.ron` | normal | 96x96 | 2 | 5 | 0 | 0 | 0 | 6 | 27 |
