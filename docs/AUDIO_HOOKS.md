# Audio hooks

No original Swarm Assault audio is shipped (the original `.SDF` sounds are not redistributable).
The game plays `assets/audio/<id>.ogg` (or `.wav`) whenever an event with that id happens and does
nothing if the file is missing, so dropping files into `assets/audio/` is all that is needed.

## Shipped sound set

Every hook below has a file: `tools/make_sounds.py` synthesizes all 40 effects with numpy (gun
pops, filtered-noise explosions, pitch-swept squeals for the deaths, chimes for unit ready /
colony captured, a four-note fanfare for victory, a falling minor line for defeat, a short click
for the interface) and encodes them to Ogg Vorbis with ffmpeg (`-q:a 4`, 488 KB in all). They are
original work, not samples. To replace any of them, drop a file with the same stem into
`assets/audio/` (the loader logs `audio: N sound files found`). The interface click plays on
every button press (`ui.rs`, `click_sound`).

| Hook id | Fired by | Original sound (OpenSA reference name) |
|---|---|---|
| `ant_crunch` | Ant Soldier / Black Widow bite, Bull Ant bite | ANTCRUNCH |
| `savage_attack` | Savage Scorpion sting | SAVAGEATTACK |
| `rocket_launch` | Ant Bazooka fire | ROCKETLAUNCH |
| `minigun` | Lady Bug fire | MINIGUN |
| `shrapnel_fire` | Shrapnel Beetle fire | SHRAPNELFIRE |
| `cannon` | Cannon Beetle / Beetle colony fire | CANNON |
| `sniper_fire` | Spider Sniper / Spider colony fire | SNIPERFIRE |
| `missile_launch` | Missile Spider fire | MISSILELAUNCH |
| `spear` | Spear Gun Scorpion / Scorpion colony fire | SPEAR |
| `star_launch` / `star_hit` | Ninja Scorpion fire / impact | STARLAUNCH / STARHIT |
| `machinegun` | Assault Wasp fire | MACHINEGUN |
| `arrow` / `paralysis` | Paralysis Wasp fire / paralyse impact | ARROW / PARALYSIS |
| `sonic` | Sonic Wasp fire | SONIC |
| `turret_mg` | Ant / Wasp colony turret fire | TURRETMACHINEGUN |
| `explosion1` `explosion2` `explosion3` | grenade / cannon / rocket impacts | EXPLOSION1-3 |
| `ricochet` | machine-gun impacts | RIC1-4 |
| `sniper_hit` | spear impact | SNIPERHIT |
| `brakebomb_explode` `bouncebomb_explode` `gobstopper_explode` `bounce` | neutral flyer weapons | BRAKEBOMBEXPLODE, BOUNCEBOMBEXPLODE, GOBSTOPPEREXPLODE, BOUNCE |
| `colony_lost` | colony defeated | POWERDOWN |
| `colony_explode` | bits scattered | COLONYEXPLODE |
| `colony_captured` | ownership resolved | POWERUP |
| `bit_pickup` | bit collected | COLONYPICKUP |
| `ant_hole` | pirates emerge | – |
| `death_ant` `death_beetle` `death_spider` `death_scorpion` `death_wasp` `death_neutral` | unit death by family | – |
| `unit_ready` | own unit bred | UnitReady |
| `victory` / `defeat` | end of game | – |
| `ui_click` | menu buttons | – |

Volume falls off with distance from the camera focus; at most 12 sounds start per frame.
