# Implementation plan

## Environment that was confirmed to run (2026-10-13)

| Tool | Version | Status |
|---|---|---|
| Rust toolchain | rustc/cargo 1.99.0 (`rust-toolchain.toml`), target `x86_64-pc-windows-gnu` installed | works |
| Bevy | 0.20.0 (released 2026-10-08, MSRV 1.97.1) pinned in `Cargo.toml`, `Cargo.lock` committed | downloads/builds |
| Blender | **5.2.2 LTS as the `bpy` Python module** (pip wheel) in a venv, headless | Cycles (CPU), Workbench and EEVEE renders verified; glTF export verified; `.blend` save verified |
| Blender GUI binary | not installable (download.blender.org blocked by the proxy) | all Blender work is done through repeatable `bpy` scripts |
| Windows cross linker | mingw-w64 11 (`x86_64-w64-mingw32-gcc`) | installed via apt |
| GPU | none; Mesa lavapipe (software Vulkan) + Xvfb for running the game headless | to be verified in Stage 3 |
| Network | crates.io, PyPI, GitHub clone OK; docs.rs, fandom wiki, mobygames, video sites blocked | Bevy API verified by reading the crate sources in the cargo registry |

## Architecture

```
Cargo workspace
├── crates/sa_sim    pure-Rust deterministic simulation (no Bevy): map/nav grid, units, weapons,
│                    projectiles, colonies + capture, AI, orders, victory, save/load, RON data loading
└── crates/sa_game   Bevy 0.20 application: camera, input/selection, HUD/menus, glTF asset loading,
                     animation state machine, team-colour materials, audio hooks, screenshots, benchmark
assets/data/*.ron    editable unit stats, colony settings, maps, controls
assets/models/*.glb  exported Blender assets (one file per unit/colony/environment object)
blender/scripts/     repeatable bpy scripts (library + per-asset builders + export + preview renders)
blender/blend/       editable .blend sources written by the scripts
blender/previews/    front/back/left/right/three-quarter renders per asset
docs/                plan, research, asset notes, test and benchmark reports, Windows build guide
tools/               build/package helper scripts
```

Simulation/rendering separation: `sa_sim::World` advances with `step(dt)` at a fixed 30 Hz inside
Bevy's `FixedUpdate`; the game crate only *reads* sim state to place/animate entities and only
*writes* orders through `sa_sim::Order`. Rendering interpolates positions between the last two
sim states using the fixed-timestep overstep fraction. The sim crate has its own unit tests which run
without a GPU.

Coordinate conventions: 1 world unit = 1 map cell (OpenSA cell). Sim is 2-D (x, y) on the ground
plane; Bevy maps sim (x, y) to (x, 0, y)... i.e. sim +y is Bevy +z. Headings are radians, 0 = sim +y
(Bevy +z); the glTF assets face Bevy +z in their rest pose (Blender -Y), so the render rotation is
`Quat::from_rotation_y(-heading)`.

Navigation: blocked-cell grid built from the map (colony footprints, rocks, plants). A* with
8-connectivity (no corner cutting) plus line-of-sight string pulling, path caching per unit, straight
steering when the target is visible, and local avoidance by separation forces between nearby units
(spatial hash) plus wall sliding against blocked cells. Flow fields for large group orders are a
Stage 5 optimisation.

## Stages and deliverables

1. **Inspection + plan** (this document, `ASSET_CHECKLIST.md`, `GAMEPLAY_RESEARCH.md`).
2. **Small playable battle**: one grass map, Ant Soldiers for two teams, one Ant colony per team,
   Blender ant soldier + ant colony assets with animations, selection, movement, path-finding, combat,
   damage, death, colony capture (bits), basic AI, win/lose.
3. **Run + verify**: compile, run under Xvfb/lavapipe, screenshots, automated sim tests, test report.
4. **Full roster**: 21 units, 5 colony families with turrets, weapons/behaviours (projectiles,
   splash, paralysis, shrapnel, missiles, bombs), neutral flyers, pirates/ant holes, plants and
   decorations, team colours, data files for everything.
5. **Polish**: menus, pause, audio hooks, save/load, configurable controls, performance work,
   benchmarks with measured frame rates on this hardware, Windows release package.

## Status (2026-10-13)

| Stage | Status |
|---|---|
| 1 Inspection + plan | done |
| 2 Small playable battle (ants) | done – `assets/data/maps/ants_skirmish.ron` |
| 3 Run + verify | done – `docs/TEST_REPORT.md`, 15 headless tests, Xvfb/lavapipe screenshots |
| 4 Full roster | done – 21 units, 5 colonies, flyers, pirates, props; `five_families.ron` |
| 5 Polish | done except for execution on real Windows hardware: menus, pause, audio hooks, save/load, settings, controls, benchmarks (software renderer), cross-compiled Windows package |

Navigation ended up as A* + string pulling with per-unit caching and LOS shortcuts (no flow fields);
the headless benchmark shows 4,000 units at ~4 ms per tick, so flow fields were not needed.

## Risks noted up front

* Bevy 0.20.0 is five days old; the API is read from the crate source, not from memory.
* The container has no GPU. Frame-rate numbers reported from here are from a software Vulkan driver
  and are a lower bound; real Windows numbers must be measured on real hardware.
* The Windows build is cross-compiled and cannot be executed here; it is verified only to link and
  to be a valid PE executable.
