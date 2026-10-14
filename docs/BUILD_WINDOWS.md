# Building and running on Windows

## Requirements

* Windows 10/11 64-bit with a Vulkan 1.1 or DirectX 12 capable GPU and current drivers.
* Rust toolchain 1.99.0 (the repository pins it in `rust-toolchain.toml`; `rustup` installs it
  automatically).
* Nothing else: Bevy's Windows backend needs no extra SDKs (the MSVC toolchain `x86_64-pc-windows-msvc`
  is the default on Windows and works with `cargo build`).

## Build on Windows (native, recommended)

```powershell
git clone <this repository>
cd z-waif-1.13-ST
cargo run --release -p swarm_assault_3d
```

The first build takes several minutes (Bevy). The executable is
`target\release\swarm_assault_3d.exe`; it looks for the `assets` folder next to the executable or in
the current directory (override with the `SA_ASSETS` environment variable).

## Cross-compile from Linux (what this repository's release zip was built with)

```bash
sudo apt install mingw-w64
rustup target add x86_64-pc-windows-gnu
CARGO_TARGET_DIR=target-win cargo build --release -p swarm_assault_3d --target x86_64-pc-windows-gnu
tools/package_windows.sh          # writes dist/SwarmAssault3D-windows-x64.zip
```

`tools/package_windows_parts.py` splits the staged folder into zip parts under 30 MiB (every part
carries the same top-level folder; extract all of them into one place). The loose baked textures
in `assets/textures` are left out of the game package because the GLBs embed them.

`.cargo/config.toml` already sets the mingw linker for that target. The cross-compiled executable
was **not executed** anywhere (no Windows machine was available while building it); it was verified
to link, to be a valid PE32+ GUI executable and to import only Windows system DLLs. Please run it on
real hardware and report problems. Release builds hide the console window; set `RUST_LOG` and run
from a terminal with `--help` style options if you need logs (they go to stdout, which is invisible
without a console - use a debug build for log output).

## Running

```
swarm_assault_3d.exe                      # main menu
swarm_assault_3d.exe --map five_families.ron
swarm_assault_3d.exe --bench 200          # autoplay benchmark, writes benchmarks\bench_200_<ts>.txt
swarm_assault_3d.exe --help
```

Settings: `assets\data\settings.ron` (resolution, fullscreen, vsync, MSAA, shadows).
Controls: `assets\data\controls.ron`. Unit/colony statistics: `assets\data\*.ron`.

## Manual test checklist (not automated here)

1. Main menu shows both maps; clicking starts the map; Esc opens the pause menu; Save/Load work
   (`saves\quicksave.ron`); "Main menu" returns and a second game starts cleanly.
2. Left click selects one own unit; drag box selects several; shift adds; clicking a colony selects
   it and 1/2/3 changes breeding; right click on ground moves, on an enemy attacks; T + click
   attack-moves; X stops.
3. Camera: WASD / arrows / screen edges pan, wheel zooms, Q/E rotate, middle-drag pans, Home centres.
4. F3 shows blocked cells and paths, F12 saves a screenshot, F5/F9 quick save/load.
5. Frame rate: F3 shows fps and simulation ms; `--bench N` writes a report.
6. Interface: the sidebar chrome (timer, insignia, radar, breeding buttons, bars, LED, selection
   screen) renders at the window's right edge at any resolution; clicking the insignia opens the
   options dialog; the breeding buttons toggle breeding and the bar fills; the cursor is the red
   arrow, a crosshair over enemies (and in attack-move mode) and a bracket while box-selecting.
7. Sound: weapons, impacts, deaths, colony events, unit ready, victory / defeat and the click on
   every button are audible (40 files in `assets\audio`; volume falls off with distance).
8. Settings (main menu or Options > Settings): the volume slider and the sound toggle take effect
   at once, fullscreen / vsync switch the window, and `assets\data\settings.ron` is rewritten;
   the values survive a restart.
