//! Screenshots (F12 / `--screenshot-after`), timed quit for automated runs, quick save/load.

use bevy::app::AppExit;
use bevy::prelude::*;
use bevy::render::view::screenshot::{Screenshot, save_to_disk};

use crate::AppState;
use crate::CliOptions;
use crate::controls::Controls;
use crate::selection::Selection;
use crate::sim_plugin::GameSim;
use crate::views::{AnimStats, BitView, ColonyView, ProjectileView, UnitView, ViewIndex, reset_views};

pub struct ScreenshotPlugin;

impl Plugin for ScreenshotPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Update, (screenshot_system, quit_system)).add_systems(Update, quick_save_load.run_if(in_state(AppState::InGame)));
    }
}

fn screenshot_path(dir: &str, tag: &str) -> String {
    std::fs::create_dir_all(dir).ok();
    let n = std::fs::read_dir(dir).map(|d| d.count()).unwrap_or(0);
    format!("{dir}/screenshot_{n:03}_{tag}.png")
}

fn screenshot_system(mut commands: Commands, keys: Res<ButtonInput<KeyCode>>, controls: Res<Controls>, cli: Res<CliOptions>, time: Res<Time>, mut auto_done: Local<Vec<u32>>) {
    if controls.just_pressed(&keys, "screenshot") {
        let path = screenshot_path(&cli.screenshot_dir, "manual");
        info!("saving screenshot to {path}");
        commands.spawn(Screenshot::primary_window()).observe(save_to_disk(path));
    }
    if let Some(after) = cli.screenshot_after {
        // one shot at `after`, then every `after` seconds up to 6 shots (automated test runs)
        let n = (time.elapsed_secs() / after.max(0.5)) as u32;
        if n >= 1 && n <= 6 && !auto_done.contains(&n) {
            auto_done.push(n);
            let path = screenshot_path(&cli.screenshot_dir, &format!("t{:.0}s", n as f32 * after));
            info!("saving screenshot to {path}");
            commands.spawn(Screenshot::primary_window()).observe(save_to_disk(path));
        }
    }
}

fn quit_system(cli: Res<CliOptions>, time: Res<Time>, mut exit: MessageWriter<AppExit>, sim: Option<Res<GameSim>>, anim: Res<AnimStats>, mut frames: Local<u32>, state: Res<State<AppState>>) {
    *frames += 1;
    if let Some(q) = cli.quit_after
        && time.elapsed_secs() >= q
    {
        let el = time.elapsed_secs();
        if let Some(sim) = sim {
            info!("quit-after reached: tick {} sim-time {:.1}s wall {:.1}s frames {} ({:.1} fps avg) units {} shots {} kills {} captures {}", sim.world.tick, sim.world.time, el, *frames, *frames as f32 / el.max(0.1), sim.world.living_units().count(), sim.world.stats.shots, sim.world.stats.units_killed, sim.world.stats.captures);
            info!("animation: players bound {} clip starts {:?} turret rotation updates {}", anim.players_bound, anim.clip_starts, anim.turret_rotations);
        } else {
            info!("quit-after reached in state {:?} after {:.1}s and {} frames", state.get(), el, *frames);
        }
        exit.write(AppExit::Success);
    }
}

#[allow(clippy::type_complexity)]
fn quick_save_load(
    mut commands: Commands,
    keys: Res<ButtonInput<KeyCode>>,
    controls: Res<Controls>,
    mut sim: ResMut<GameSim>,
    mut index: ResMut<ViewIndex>,
    mut selection: ResMut<Selection>,
    views: Query<Entity, Or<(With<UnitView>, With<ColonyView>, With<BitView>, With<ProjectileView>)>>,
) {
    let path = std::path::PathBuf::from("saves/quicksave.ron");
    if controls.just_pressed(&keys, "quick_save") {
        match sa_sim::save::save(&sim.world, &path) {
            Ok(()) => info!("saved {}", path.display()),
            Err(e) => error!("save failed: {e}"),
        }
    }
    if controls.just_pressed(&keys, "quick_load") {
        match sa_sim::save::load(&path) {
            Ok(w) => {
                sim.world = w;
                sim.events.clear();
                selection.units.clear();
                selection.colony = None;
                reset_views(&mut commands, &mut index, &views);
                info!("loaded {}", path.display());
            }
            Err(e) => error!("load failed: {e}"),
        }
    }
}
