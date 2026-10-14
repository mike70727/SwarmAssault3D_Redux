# Test report

All results below were produced in this environment on 2026-10-13. Nothing here was run on Windows
or on a GPU (see "Hardware").

## Hardware / software used for every measurement

| Item | Value |
|---|---|
| CPU | Intel Xeon @ 2.10 GHz, 4 vCPUs (cloud container) |
| RAM | 15 GB |
| GPU | **none** – Mesa `lavapipe` software Vulkan driver (`VK_ICD_FILENAMES=.../lvp_icd.json`) under Xvfb 1280x720 |
| OS | Linux 6.18 (container), Ubuntu 24.04 userland |
| Rust / Bevy | rustc 1.99.0, Bevy 0.20.0, debug profile with `opt-level = 1` (deps at 3) |
| Blender | 5.2.2 LTS `bpy` module, Cycles CPU |

Frame rates measured here are software-rendering numbers and only show that the renderer works; they
say nothing about performance on a Windows PC with a GPU.

## Stage 3 – the Stage 2 battle (ants only)

### Automated simulation tests (`cargo test -p sa_sim`, no rendering)

13 tests, all passing (0.3 s):

| Test | What it checks | Result |
|---|---|---|
| grid::path_around_wall / unreachable_goal / straight_when_visible | A* + string pulling, unreachable detection, LOS shortcut | pass |
| data_files_load_and_every_model_is_named | 21 units, 5 colonies, weapons resolved | pass |
| units_walk_to_a_move_order_around_obstacles | 8 soldiers ordered across the map; all arrive within 20 s, no unit ever enters a blocked cell | pass (slowest 15.3 s) |
| soldiers_fight_and_die | 8 v 8 melee; attack events and deaths | pass (>20 attacks, >=4 deaths) |
| colony_turrets_shoot_intruders | enemy soldiers near a colony get shot by the twin turrets | pass (>10 turret shots, kills) |
| colony_capture_flow_bits_and_ownership | defeat → 3 s delay → 9 bits scattered (5–10 cells) → soldiers collect them → owner changes, HP 25 % | pass (captured by yellow, HP 25000) |
| massed_soldiers_can_crack_and_capture_a_colony_under_the_stage2_rule | 40 soldiers attack a full-health turret-defended colony and capture it | pass |
| colonies_breed_units_up_to_the_cap | bot colony breeds soldiers, never exceeds the cap | pass |
| bot_wins_against_an_idle_human_or_the_game_keeps_going | bot issues attack orders, no panics over 4 min | pass |
| paralysis_and_projectiles_from_the_full_roster | wasp paralysis arrow paralyses, grenades fly and impact | pass |
| save_and_load_round_trip_is_deterministic | RON save/load, identical positions and shot counts after 10 s | pass |

### Rendered run (`swarm_assault_3d --autoplay --speed 2 --screenshot-after 15 --quit-after 92`)

Both teams were driven by the bot ("autoplay") so the battle plays itself. Output of the run:

```
map 'Ant Skirmish' loaded: 16 units, 2 colonies
model ant_soldier ready (4 clips: ["death", "idle", "attack", "move"])
model colony_ant ready (2 clips: ["turret_fire", "idle"])
quit-after reached: tick 5529 sim-time 184.3s wall 92.2s frames 436 (4.7 fps avg)
   units 18 shots 1505 kills 94 captures 0
animation: players bound 112 clip starts {"move": 418, "attack": 1203, "idle": 336, "death": 94}
   turret rotation updates 108
```

What this verifies:

* **Animation playback**: 112 glTF `AnimationPlayer`s were bound to the exported ant rig; the state
  machine started `move`, `attack`, `idle` and `death` clips (one `death` per kill). Attack clips are
  re-triggered per bite (1203 starts for 1505 shots: turret shots have no unit clip).
* **Navigation**: units bred at both colonies walked to the rally points and across the map
  (418 move-clip starts, sim test above confirms obstacle avoidance).
* **Combat**: 1505 shots, 94 kills in 184 s of simulated time.
* **Colony interaction**: turrets tracked targets (108 rotation updates) and fired; no capture happened
  in this run because squads of ~10 soldiers die to the twin turrets (690 damage every 0.24 s each,
  OpenSA values) before they can bite the colony. The capture flow itself is proven by the two
  headless tests; a 40-unit push captures the colony.
* **Rendering**: 436 frames in 92 s on the software driver (4.7 fps; the simulation itself costs
  0.6–1.0 ms per frame at 2x speed). Screenshots: `docs/screenshots/stage3_battle_t{30,60,90}s.jpg`.

### Manual input

Mouse/keyboard interaction could not be exercised here (no human at the Xvfb display). The selection,
drag box and order code paths are exercised by the same systems that the bot uses for orders, but
the click-to-select and drag-rectangle screen-space tests remain **untested by a human**; see
`docs/BUILD_WINDOWS.md` for the manual checklist.

## Stage 4 – full roster, five colonies, flyers and pirates

### Simulation tests

`cargo test -p sa_sim` now runs 15 tests (12 battle + 3 grid), all passing. New since Stage 3:

| Test | What it checks | Result |
|---|---|---|
| five_families_map_runs_with_flyers_pirates_and_ranged_capture | all five colony families load; a dragonfly and a pirate group spawn; 30 grenadiers/bazookas destroy and capture a neutral beetle colony; a melee soldier is never allowed to target the colony (original rule) | pass |
| neutral_flyers_cross_the_map_and_leave | a spawn moth crosses the 96x96 map on a fixed heading and is removed at the far edge (regression test for flyers piling up at the border) | pass |

### Asset loading

Every one of the 27 GLB files is reported as ready by the Bevy loader with its clip names, e.g.

```
model wasp_sonic ready (4 clips: ["idle", "fly", "attack", "death"])
model colony_spider ready (2 clips: ["idle", "turret_fire"])
```

### Rendered run on the five-family map (`--map five_families.ron --autoplay --speed 2 --quit-after 125`)

```
map 'Five Families' loaded: 23 units, 5 colonies
quit-after reached: tick 7503 sim-time 250.1s wall 125.1s frames 505 (4.0 fps avg)
   units 23 shots 2442 kills 118 captures 0
animation: players bound 141 clip starts {"fly": 6, "idle": 262, "death": 117, "attack": 454, "move": 317}
   turret rotation updates 284
```

Observed in the screenshots (`docs/screenshots/stage4_*.jpg`): the five colony models with their
turrets, ant and spider armies fighting with projectiles (grenades, rockets, sniper shots, missiles),
neutral flyers crossing, pirate ants emerging from ant holes. No colony
was captured within four simulated minutes: both bots lose their squads to the colony turrets, and
the human side was bot-driven. The headless test above proves capture with a concentrated ranged
push.

### Menu smoke test (`--menu --quit-after 10 --screenshot-after 5`)

The main menu rendered (map list from `assets/data/maps`, Load quicksave, Quit) for 10 s / 382
frames and quit cleanly: `docs/screenshots/stage5_menu.jpg`. Button clicks could not be exercised
without a human; the pause menu uses the same widget code path.

## Stage 5 – benchmarks

### Simulation only (`cargo run --release -p sa_sim --example bench_sim`, release build)

Five-family map, two bot teams ordered to attack-move into each other, 1800 ticks (60 s of game time):

| units per team | living units at start | ms per tick | ticks/s possible | shots | kills |
|---|---|---|---|---|---|
| 50 | 102 | 0.099 | 10124 | 1053 | 105 |
| 200 | 402 | 0.456 | 2194 | 2621 | 322 |
| 500 | 1002 | 1.061 | 942 | 6684 | 913 |
| 1000 | 2004 | 1.877 | 533 | 9696 | 1536 |
| 2000 | 4002 | 4.087 | 245 | 20093 | 3333 |

At the game's 30 ticks/s a 4,000-unit battle uses ~12 % of one core for simulation on this CPU.

### Rendered (`swarm_assault_3d --map five_families.ron --bench N --quit-after 60`)

| extra units per team (`--bench`) | living units avg / max | average fps | 1 % low fps | sim ms per frame avg / max | frames in 60 s |
|---|---|---|---|---|---|
| 0 (map default) | 23 / 28 | 5.0 | 4.0 | 0.43 / 3.26 | 298 |
| 25 | 106 / 179 | 4.1 | 4.0 | 1.96 / 11.77 | 241 |
| 50 | 177 / 325 | 4.1 | 4.0 | 3.28 / 9.25 | 241 |
| 100 | 321 / 628 | 4.0 | 4.0 | 5.36 / 15.53 | 237 |
| 200 | 678 / 1230 | 4.0 | 4.0 | 13.12 / 29.55 | 237 |
| 500 | – | – | – | – | killed by the 280 s watchdog: spawning ~3,000 skinned bugs took longer than that on the software renderer |

(Measured after the event-accumulation fix described below; the earlier numbers were discarded.)

Hardware for these rows: Intel Xeon @ 2.10 GHz, 4 vCPUs, 15 GB RAM, **no GPU** (Mesa lavapipe
software Vulkan, Xvfb 1280x720), Linux container, debug build (`opt-level = 1`, dependencies at
`opt-level = 3`). The frame rate is pinned at ~4 fps by software rasterisation of the 1280x720
frame (ground, shadows, UI) regardless of unit count, so the useful signal here is the simulation
column: it grows linearly with the number of living units (1,230 units: 13 ms per rendered frame,
i.e. the two 30 Hz ticks that fit in a 250 ms frame, ~6.5 ms per tick with everyone fighting). The
bots captured neutral colonies in the larger runs (1 and 2 captures).

Real frame-rate figures must be taken on Windows hardware with a GPU:
`swarm_assault_3d.exe --bench N` (autoplay, 90 s, writes `benchmarks\bench_N_<timestamp>.txt` with the
machine's CPU/OS from Bevy's system-information diagnostics).

## Stage 5 – Windows package

* `CARGO_TARGET_DIR=target-win cargo build --release -p swarm_assault_3d --target x86_64-pc-windows-gnu`
  linked successfully with mingw-w64 (3 m 50 s incremental, ~13 min clean).
* `file` reports `PE32+ executable (GUI) x86-64, for MS Windows`; `objdump -p` lists only Windows
  system DLLs (kernel32, user32, dxgi, …), i.e. no mingw runtime DLLs are needed.
* `tools/package_windows.sh` produced `dist/SwarmAssault3D-windows-x64.zip` (49 MB) containing the
  executable, `assets/`, `docs/`, `RUN.txt` and the editable sources (`source/crates`, `source/blender`
  with scripts and `.blend` files). After the realism pass the executable was rebuilt with the
  `jpeg` feature (23 min) and `--lite` packaging gives a 73 MB zip (textured models).
* **The executable was not run**: no Windows machine or Wine is available in this environment.
  `docs/BUILD_WINDOWS.md` lists the manual checks to perform on real hardware.

Screenshots of the five colony families in the game (`--focus` option, autoplay bots):
`docs/screenshots/stage4_{wasp,beetle,scorpion,spider}_colony.jpg`; main menu: `docs/screenshots/stage5_menu.jpg`.

## Realism pass (second iteration of all models)

Every model was rebuilt with the realism layer described in `docs/ASSET_NOTES.md` (subdivided
geometry, procedural PBR surfaces, Cycles bakes to colour / ORM / normal JPEG textures embedded in
the GLBs and packed into the `.blend` files).

What was verified:

* **Bake and export** – each build asserts the clip names of its GLB (`idle`, `move`/`fly`,
  `attack`, `death`; colonies `idle` + `turret_fire`) and that the `M_Team` / `M_Colony` materials
  are present. The GLB JSON of `ant_soldier` was inspected: `baseColorTexture`,
  `metallicRoughnessTexture` (the baked ORM JPEG is used as-is, no PNG re-encode) and
  `normalTexture` on every material, `baseColorFactor` = team colour on `M_Team`, no tangents
  (Bevy generates them).
* **Game loading** – Bevy initially refused the textures (`feature "jpeg" is not enabled`); the
  `jpeg` feature was added and the loader now reports every model as ready with its clips.
* **Runtime team tint over textures** – `views.rs::tinted_material` clones the loaded glTF
  material per team and replaces only `base_color`; headless screenshots at zoom 7–10 show yellow
  ants and the yellow colony (`docs/screenshots/realism_ant_soldier_ingame.jpg`,
  `realism_colony_ant_yellow_ingame.jpg`) and the red team with the same textures tinted red
  (`realism_colony_ant_red_ingame.jpg`; the colony's second and third objects carry
  `M_Colony.001` / `.002`, matched on the name before the dot).
* **Full roster** – `--map five_families.ron --autoplay --speed 2 --quit-after 48` after the rebuild:
  all 33 models reported ready, 67 animation players bound, clip starts
  `{"idle": 140, "fly": 2, "move": 134, "attack": 149, "death": 43}`, 107 turret rotation updates,
  398 frames in 48 s (8.3 fps on the software renderer, the container was otherwise idle). Screenshot:
  `docs/screenshots/realism_five_families_ingame.jpg`.
* **Simulation** – unchanged (`cargo test -p sa_sim`: 15 tests pass).

Sizes after the pass (JPEG textures; previous flat models were 60–400 KB each):

| Group | Models | GLB (textures embedded) | `.blend` (textures packed) | baked JPEGs |
|---|---|---|---|---|
| 21 units | 21 | 26.0 MB (792–1890 KB each) | 21.4 MB | 10.7 MB |
| 5 colonies | 5 | 9.1 MB (1548–2230 KB each) | 8.7 MB | 6.0 MB |
| 7 props | 7 | 2.0 MB (65–427 KB each) | 2.6 MB | 1.5 MB |
| **all 33** | 33 | **37.2 MB** | **32.7 MB** | **18.3 MB** |

Build time for the full set: about 75 minutes of CPU on the 4-core container (two parallel chains,
2.5–8 min per model). The 33 models were rebuilt without a single failed assertion.

Limitations: no mip-maps for glTF textures in Bevy 0.20 (fine grain can shimmer at the far zoom
levels on a real GPU; not visible at the ~4 fps software-rendered checks here), automatic UV
layouts, and the frame-rate figures above were not re-measured with the textured models (the
software renderer is bound by rasterisation, not by materials; GPU figures still need a Windows
machine).

## Levels (OpenSA level set)

* `cargo test -p sa_sim --test levels`: every one of the 126 map files parses, builds a world (all
  unit / colony / structure ids resolve), gives the human something to fight or capture, and runs
  120 ticks without a panic or an early game over; the 100 campaign levels are all present with
  their numbers and cell terrain (1.0 s for the whole set).
* Headless runs with the autoplay bots on levels 1 (normal tileset), 4 (desert), 11 (swamp), 20
  (candy), the Team Battle skirmish map and the Firepower Boosters mission: each loads with its
  start camera, terrain, plants, colonies and units; screenshots in
  `docs/screenshots/levels_*.jpg`. The structure models (turrets, boosters, popcorn) were built
  after the first of these runs and verified in a second run of the Firepower Boosters mission.
* Not verified: the balance of the converted levels against the original (bots use the game's own
  profile), and the original mission scripts' special cases, which the converter does not carry.

## Interface, progression and console (headless checks)

* `--map 001_colony_defence.ron --autoplay`: the sidebar renders (level title, minimap with terrain,
  unit and colony dots and the camera rectangle, empty selection panel, hidden breeding buttons),
  no statistics text on the map; `docs/screenshots/ui_sidebar.jpg`.
* `--console-cmd win --auto-end 3`: the console's `win` command ends level 1, the level-complete
  screen appears, `saves/progress.ron` records `completed: 1`, and three seconds later level 2
  ("Defend Your Colony") loads through the Next-level action (`docs/screenshots/ui_next_level.jpg`).
* `--console-cmd cheat`: the cheat menu opens over the game (`docs/screenshots/ui_cheat_menu.jpg`).
* Rebuilt colonies: close-ups of all five families on the five-family map
  (`docs/screenshots/colony2_*_ingame.jpg`); the first mirrored build rendered black in the game
  (inward normals after the negative scale, invisible in Cycles previews) and was fixed by
  recalculating outward normals before the bake.
* Not exercised without a human: typing in the console bar, clicking the breeding buttons and the
  minimap, the locked entries in the level list (logic covered by `Progress::is_unlocked`).

## Interface v2 (rendered chrome) and sounds (headless checks)

* Chrome: `blender/scripts/build_ui_chrome.py` rendered the sidebar, buttons, bars, LEDs, dialog
  frame, black bar and the five insignia (Cycles, 128 samples, 2x then downsampled) in about four
  minutes on the CPU; `docs/screenshots/ui2_chrome.jpg` shows the pieces next to each other.
* Main menu (`--menu --screenshot-after 3`): the level list in a stone dialog with bronze buttons
  and the bold font, locked levels greyed (`docs/screenshots/ui2_menu.jpg`). The first run of
  this test crashed: `setup_menu` ran at the first state transition before the `Startup` system
  that loaded the interface assets; the assets are now loaded while the app is built.
* In game with a colony selected (`--map 001_colony_defence.ron --console-cmd select`, shot at
  10 s): timer in the pill, ant insignia on the plate, radar with the terrain and the camera
  rectangle, the three breeding buttons with the unit icons (the active one pressed), the lit red
  bar growing with the breeding progress next to two dim bars, the green LED, and the selection
  screen with the colony's portrait, name, red health bar and details
  (`docs/screenshots/ui2_sidebar_colony.jpg`). The loader logs `audio: 40 sound files found`.
* Options dialog (`--console-cmd options`), cheat menu (`--console-cmd cheat`) and level-complete
  screen (`--console-cmd win`): stone dialogs with bronze buttons over the paused game
  (`docs/screenshots/ui2_options.jpg`, `ui2_cheats.jpg`, `ui2_level_complete.jpg`). The first
  shots showed the content sitting on the frame's rim: Bevy draws an image node inside its
  content box by default, so the padded frame was squeezed inside the padding; the dialogs,
  buttons and bars now draw over the whole node (`VisualBox::BorderBox`).
* Settings dialog (`--console-cmd settings`): volume slider with the red bar, sound / fullscreen /
  vsync toggles over the paused game (`docs/screenshots/ui2_settings.jpg`); opening it does not
  write the settings file (only a change does).
* Not exercised without a human: hovering (button art swaps), the custom cursors (the screenshot
  pipeline does not capture the cursor; the cursor images are set through
  `CursorIcon::Custom`), the interface click sound (no audio device in the container), changing
  a setting with the mouse (the observer and the track-click system are the only paths; the
  save path is the same `Settings::save` used by the file format test).

## Bugs found by the test runs (and fixed)

* **Clicking any main-menu button closed the game** (reported from the Windows build after the
  interface update). Every `Activate` observer runs for every button press; the new breeding and
  cheat-menu observers required the in-game simulation resource, which does not exist while the
  menu is open, so Bevy's parameter validation failed and the panic closed the window. Found by
  adding `--auto-start` (an automated press of the first level button) to the headless runs, which
  had only ever started levels directly. The simulation is now optional in those observers, and the
  menu path (menu, press, load, play) is part of the headless checks. Release builds now write
  `crash.log` and `log.txt` next to the executable so a crash on Windows can be reported.

* **Flyers piling up at the map border** (Stage 4 screenshots): cruising neutral flyers were clamped
  to the map like every other unit, so they never left. Fixed in `integrate_movement`; regression
  test `neutral_flyers_cross_the_map_and_leave`.
* **Ranged units chasing a dragonfly across the map** (five-family capture test): auto-acquired
  targets are now subject to stand-ground / leash rules (`docs/GAMEPLAY_RESEARCH.md` A7 behaviour).
* **Simulation events were never cleared** (orange blobs in the Stage 4 colony screenshots): the
  view layer re-spawned an impact effect for every past event on every frame, which also made the
  200/500-unit rendered benchmarks collapse. Fixed with a `Last`-schedule clear; the Stage 3 frame
  rates above were measured with the bug present (their simulation counters are unaffected).

* **Units walked and flew backwards when moving east or west** (reported from play). The view
  rotated models by `-heading` about Y; a heading `h` is the direction `(sin h, cos h)` and a
  right-handed rotation by `-h` points the model's +z forward axis at `(-sin h, cos h)`: correct
  only for north/south movement and exactly reversed for east/west (turrets and projectiles used
  the same mapping). Fixed in `views.rs` (`heading_to_quat`, now `+heading`) with a unit test
  pinning the convention (`facing_tests`), and checked with the new console command `march`
  (`--console-cmd "spawn 8;march 25 0" --focus 48,48 --zoom 10`): the spawned ants walk east
  around the central colony with their heads leading (`docs/screenshots/facing_march.jpg`,
  `facing_march_zoom.jpg`); before the fix they walked the same route backwards.

## Known limitations found during Stage 3

* Corpse pose: the `death` clip rolls the ant on its side; from the top-down camera corpses read as
  yellow/red lumps. Cosmetic.
* The software renderer runs at ~5 fps, so the Xvfb screenshots show the state at coarse time steps.
