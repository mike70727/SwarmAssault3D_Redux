//! Swarm Assault 3D – Bevy application. The gameplay lives in the `sa_sim` crate; this crate only
//! renders the simulation, collects input and turns it into orders.
// Release builds on Windows run without a console window (logs still go to RUST_LOG targets).
#![cfg_attr(all(not(debug_assertions), target_os = "windows"), windows_subsystem = "windows")]

mod assets;
mod audio;
mod bench;
mod camera;
mod controls;
mod hud;
mod menu;
mod console;
mod progress;
mod screenshot;
mod selection;
mod settings;
mod settings_menu;
mod sim_plugin;
mod terrain;
mod ui;
mod views;

use bevy::diagnostic::SystemInformationDiagnosticsPlugin;
use bevy::prelude::*;
use bevy::window::{MonitorSelection, PresentMode, WindowMode, WindowResolution};

/// Command-line options (all optional).
#[derive(Resource, Clone, Debug)]
pub struct CliOptions {
    /// Map file inside `assets/data/maps`.
    pub map: String,
    /// Take a screenshot N seconds after start (used by the automated Stage 3 run).
    pub screenshot_after: Option<f32>,
    /// Screenshot output directory.
    pub screenshot_dir: String,
    /// Quit after N seconds (automated runs).
    pub quit_after: Option<f32>,
    /// Let the human team be driven by the bot too (demo / automated runs).
    pub autoplay: bool,
    /// Benchmark: spawn N extra soldiers per team and log frame times.
    pub bench_units: Option<u32>,
    /// Simulation speed multiplier.
    pub speed: f32,
    /// Load a save file instead of a map.
    pub load: Option<String>,
    /// Force the main menu even when automated options are given (menu smoke test).
    pub menu: bool,
    /// Initial camera focus "x,y" in map cells (documentation screenshots).
    pub focus: Option<(f32, f32)>,
    /// Automated runs: seconds after the end-of-level screen before the next level loads.
    pub auto_end: Option<f32>,
    /// Automated runs: a console command executed 3 s after the level starts.
    pub console_cmd: Option<String>,
    /// Automated runs: click the first level in the main menu after one second.
    pub auto_start: bool,
    /// Initial camera distance.
    pub zoom: Option<f32>,
}

impl Default for CliOptions {
    fn default() -> Self {
        Self {
            map: "ants_skirmish.ron".into(),
            screenshot_after: None,
            screenshot_dir: "screenshots".into(),
            quit_after: None,
            autoplay: false,
            bench_units: None,
            speed: 1.0,
            load: None,
            menu: false,
            focus: None,
            auto_end: None,
            console_cmd: None,
            auto_start: false,
            zoom: None,
        }
    }
}

fn parse_cli() -> CliOptions {
    let mut o = CliOptions::default();
    let args: Vec<String> = std::env::args().skip(1).collect();
    let mut i = 0;
    while i < args.len() {
        let a = args[i].as_str();
        let next = |i: &mut usize| -> Option<String> {
            *i += 1;
            args.get(*i).cloned()
        };
        match a {
            "--map" => o.map = next(&mut i).unwrap_or(o.map.clone()),
            "--screenshot-after" => o.screenshot_after = next(&mut i).and_then(|v| v.parse().ok()),
            "--screenshot-dir" => o.screenshot_dir = next(&mut i).unwrap_or(o.screenshot_dir.clone()),
            "--quit-after" => o.quit_after = next(&mut i).and_then(|v| v.parse().ok()),
            "--autoplay" => o.autoplay = true,
            "--bench" => o.bench_units = next(&mut i).and_then(|v| v.parse().ok()),
            "--speed" => o.speed = next(&mut i).and_then(|v| v.parse().ok()).unwrap_or(1.0),
            "--load" => o.load = next(&mut i),
            "--menu" => o.menu = true,
            "--focus" => {
                o.focus = next(&mut i).and_then(|v| {
                    let mut it = v.split(',').filter_map(|p| p.trim().parse::<f32>().ok());
                    Some((it.next()?, it.next()?))
                })
            }
            "--zoom" => o.zoom = next(&mut i).and_then(|v| v.parse().ok()),
            "--auto-end" => o.auto_end = next(&mut i).and_then(|v| v.parse().ok()),
            "--console-cmd" => o.console_cmd = next(&mut i),
            "--auto-start" => o.auto_start = true,
            "--help" | "-h" => {
                println!("swarm_assault_3d [--map FILE] [--load SAVE] [--screenshot-after SECS] [--screenshot-dir DIR] [--quit-after SECS] [--autoplay] [--bench N] [--speed X] [--focus X,Y] [--zoom D] [--auto-end SECS] [--console-cmd CMD] [--auto-start] [--menu]");
                std::process::exit(0);
            }
            _ => eprintln!("unknown argument {a}"),
        }
        i += 1;
    }
    o
}

/// High-level application state.
#[derive(States, Debug, Clone, Copy, PartialEq, Eq, Hash, Default)]
pub enum AppState {
    #[default]
    Menu,
    Loading,
    InGame,
}

/// Folder of the executable (where crash.log and log.txt are written).
fn exe_dir() -> std::path::PathBuf {
    std::env::current_exe().ok().and_then(|e| e.parent().map(|p| p.to_path_buf())).unwrap_or_else(|| std::path::PathBuf::from("."))
}

/// Release builds on Windows have no console: a panic would close the window silently, so the
/// message and a backtrace go to crash.log next to the executable.
fn install_crash_log() {
    let default = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        let msg = format!("Swarm Assault 3D crashed:\n{info}\n\nbacktrace:\n{}\n", std::backtrace::Backtrace::force_capture());
        let _ = std::fs::write(exe_dir().join("crash.log"), &msg);
        default(info);
    }));
}

/// Mirrors the log into log.txt next to the executable (the Windows release build has no console).
fn file_log_layer(_app: &mut App) -> Option<bevy::log::BoxedLayer> {
    use bevy::log::tracing_subscriber::Layer as _;
    let file = std::fs::OpenOptions::new().create(true).write(true).truncate(true).open(exe_dir().join("log.txt")).ok()?;
    Some(bevy::log::tracing_subscriber::fmt::layer().with_ansi(false).with_writer(std::sync::Mutex::new(file)).boxed())
}

fn main() {
    install_crash_log();
    let mut cli = parse_cli();
    let settings = settings::Settings::load();
    // automated runs (screenshots, benchmarks, explicit map/save) skip the menu
    let direct = !cli.menu && (cli.screenshot_after.is_some() || cli.quit_after.is_some() || cli.autoplay || cli.bench_units.is_some() || cli.load.is_some() || std::env::args().any(|a| a == "--map"));
    if cli.bench_units.is_some() {
        cli.autoplay = true;
        if cli.quit_after.is_none() {
            cli.quit_after = Some(90.0);
        }
    }
    let initial = if direct { AppState::Loading } else { AppState::Menu };
    let mode = if settings.fullscreen { WindowMode::BorderlessFullscreen(MonitorSelection::Primary) } else { WindowMode::Windowed };
    App::new()
        .insert_resource(cli)
        .insert_resource(settings.clone())
        .insert_resource(progress::Progress::load())
        .add_plugins(
            DefaultPlugins
                .set(WindowPlugin {
                    primary_window: Some(Window {
                        title: "Swarm Assault 3D".into(),
                        resolution: WindowResolution::new(settings.width.max(640), settings.height.max(480)),
                        present_mode: if settings.vsync { PresentMode::AutoVsync } else { PresentMode::AutoNoVsync },
                        mode,
                        ..default()
                    }),
                    ..default()
                })
                .set(AssetPlugin { file_path: asset_root(), ..default() })
                .set(bevy::log::LogPlugin { custom_layer: file_log_layer, ..default() }),
        )
        .add_plugins(SystemInformationDiagnosticsPlugin)
        .insert_state(initial)
        .add_plugins((
            controls::ControlsPlugin,
            assets::GameAssetsPlugin,
            sim_plugin::SimPlugin,
            camera::CameraPlugin,
            terrain::TerrainPlugin,
            views::ViewsPlugin,
            selection::SelectionPlugin,
            ui::UiPlugin,
            settings_menu::SettingsMenuPlugin,
            hud::HudPlugin,
            console::ConsolePlugin,
            screenshot::ScreenshotPlugin,
            menu::MenuPlugin,
            audio::GameAudioPlugin,
            bench::BenchPlugin,
        ))
        .run();
}

/// Locate the `assets` directory: next to the executable (release package) or the repo root
/// (cargo run), overridable with `SA_ASSETS`.
pub fn asset_root() -> String {
    if let Ok(p) = std::env::var("SA_ASSETS") {
        return p;
    }
    let candidates = [
        std::env::current_dir().ok().map(|d| d.join("assets")),
        std::env::current_exe().ok().and_then(|e| e.parent().map(|d| d.join("assets"))),
        Some(std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../assets")),
    ];
    for c in candidates.into_iter().flatten() {
        if c.join("data").join("units.ron").exists() {
            return c.to_string_lossy().to_string();
        }
    }
    "assets".into()
}
