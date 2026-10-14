# Asset checklist

Conventions for every asset (enforced by `blender/scripts/salib.py`):

* Units: 1 Blender unit = 1 map cell. Origin at the ground point under the body centre. Rest pose faces
  Blender -Y (becomes Bevy +Z after the glTF Y-up conversion). Z is up.
* Material names: `M_Team` (team-coloured body parts), `M_Dark` (chitin/legs), `M_Accent` (weapons,
  metal), `M_Eye`, `M_Wing` (translucent), `M_Ground` (colony base rock), `M_Colony` (colony team
  colour), `M_Neutral`.
* Armature name `Rig`, root bone `root`, body bone `body`, head `head`, legs `leg.L1..L3`/`leg.R1..R3`
  (coxa→femur→tibia chain: `legXN`, `legXN.femur`, `legXN.tibia`), wings `wing.L`/`wing.R`, turret
  parts are separate objects named `Turret_N` with child `Barrel_N`.
* Animation names (actions and glTF clips): `idle`, `move` (walking bugs) or `fly` (flying bugs),
  `attack`, `death`. Colonies: `idle`, `produce` (optional), `turret_fire` on turret objects.
* Rig constraints (IK for legs) are baked to FK keyframes before export; exported GLB files contain
  only baked transforms.
* Previews: `blender/previews/<asset>_{front,back,left,right,threequarter}.jpg`, Cycles CPU, 512 px.
* Exports: `assets/models/<asset>.glb` (GLB, +Y up, animations included, no draco).

| # | Asset | Type | Reference | Rig | Clips | Status |
|---|---|---|---|---|---|---|
| 1 | ant_soldier | unit (melee) | UNANTSO*, COLONYANTA3D* | ant rig (6 legs, head, mandibles, abdomen) | idle, move, attack, death | done |
| 2 | ant_grenadier | unit (grenade) | UNANTRG*, COLONYANTB3D* | ant rig + backpack/launcher | idle, move, attack, death | done |
| 3 | ant_bazooka | unit (rocket) | UNANTBZ*, COLONYANTC3D* | ant rig + shoulder tube | idle, move, attack, death | done |
| 4 | beetle_ladybug | unit (MG) | UNBETLB*, COLONYBEETLEA3D* | beetle rig (dome shell, 6 legs) | idle, move, attack, death | done |
| 5 | beetle_shrapnel | unit (shrapnel) | UNBETSH*, COLONYBEETLEB3D* | beetle rig | idle, move, attack, death | done |
| 6 | beetle_cannon | unit (artillery) | UNBETCA*, COLONYBEETLEC3D* | beetle rig + barrel | idle, move, attack, death | done |
| 7 | spider_black_widow | unit (melee) | UNSPIBW*, COLONYSPIDERA3D* | spider rig (8 legs) | idle, move, attack, death | done |
| 8 | spider_sniper | unit (sniper) | UNSPISN*, COLONYSPIDERB3D* | spider rig + rifle | idle, move, attack, death | done |
| 9 | spider_missile | unit (missiles) | UNSPIRK*, COLONYSPIDERC3D* | spider rig + launcher | idle, move, attack, death | done |
| 10 | scorpion_savage | unit (melee) | UNSCOSA*, COLONYSCORPIONA3D* | scorpion rig (8 legs, claws, tail) | idle, move, attack, death | done |
| 11 | scorpion_spear_gun | unit (harpoon) | UNSCOSG*, COLONYSCORPIONB3D* | scorpion rig + spear gun | idle, move, attack, death | done |
| 12 | scorpion_ninja | unit (stars) | UNSCOST*, COLONYSCORPIONC3D* | scorpion rig + star thrower | idle, move, attack, death | done |
| 13 | wasp_assault | flyer (MG) | UNWASPL*, COLONYWASPA3D* | wasp rig (wings, 6 legs) | idle, fly, attack, death | done |
| 14 | wasp_paralysis | flyer (arrows) | UNWASPA*, COLONYWASPB3D* | wasp rig | idle, fly, attack, death | done |
| 15 | wasp_sonic | flyer (sonic) | UNWASSO*, COLONYWASPC3D* | wasp rig | idle, fly, attack, death | done |
| 16 | neutral_dragonfly | flyer (bombs) | UNDRABOB, COLONYNEUTRALDRAGONFLY3D | flyer rig (4 wings) | fly, death | done |
| 17 | neutral_desert_fly | flyer (bouncing bombs) | UNFLYBIG, COLONYNEUTRALFLY3D | flyer rig (2 wings) | fly, death | done |
| 18 | neutral_spawn_moth | flyer (puffs/seeds) | UNDEMOTH, COLONYNEUTRALMOTH3D | flyer rig (2 large wings) | fly, death | done |
| 19 | neutral_flying_machine | flyer (gobstoppers) | UNFLYMCH, COLONYNEUTRALFLYINGMACHINE3D | machine rig (rotors) | fly, death | done |
| 20 | neutral_bull_ant | unit (melee) | UNANTSOX, COLONYNEUTRALANTBULL3D | ant rig, black | idle, move, attack, death | done |
| 21 | neutral_pirate_grenadier | unit (grenade) | UNANTRGX, COLONYNEUTRALANTGRENADIER3D | ant rig + launcher, black | idle, move, attack, death | done |
| C1 | colony_ant | colony | STCLYAN*, Quick_References/Buildings/Ant_Colony_* | body + 2 turrets | idle, turret_fire | done |
| C2 | colony_beetle | colony | STCLYBT* | body + 1 turret | idle, turret_fire | done |
| C3 | colony_spider | colony | STCLYSP* | body + 2 turrets | idle, turret_fire | done |
| C4 | colony_scorpion | colony | STCLYSC* | body + 1 twin turret | idle, turret_fire | done |
| C5 | colony_wasp | colony | STCLYWA* | body + 1 turret | idle, turret_fire | done |
| E1 | colony_bit | pickup | OpenSA colonybit sequence | none | spin | done |
| E2 | rocks / grass tufts / flowers / mushrooms / ant hole / plants | environment | OB*, ANTHOLE* | none | (grow optional) | done (rocks, mushroom, flower, grass tuft, ant hole; other tileset plants not modelled) |
| E3 | projectiles (grenade, rocket, spear, star, arrow, bullet, bomb) | effects | OpenSA projectile sequences | none | none | done |

All rows are produced by the scripts in `blender/scripts/`; per-asset notes and uncertainties are in `docs/ASSET_NOTES.md`.
