//! Benchmark mode (`--bench N`): records frame times and simulation cost for the whole run and
//! writes `benchmarks/bench_<units>_<timestamp>.txt` (plus a log line) when the app quits.

use bevy::app::AppExit;
use bevy::diagnostic::SystemInfo;
use bevy::prelude::*;

use crate::AppState;
use crate::CliOptions;
use crate::sim_plugin::GameSim;

#[derive(Resource, Default)]
pub struct BenchStats {
    pub frame_times: Vec<f32>,
    pub sim_ms: Vec<f32>,
    pub units: Vec<u32>,
    pub written: bool,
}

pub struct BenchPlugin;

impl Plugin for BenchPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<BenchStats>().add_systems(Update, (record_frame.run_if(in_state(AppState::InGame)), write_report_on_exit));
    }
}

fn record_frame(mut stats: ResMut<BenchStats>, time: Res<Time>, sim: Res<GameSim>, cli: Res<CliOptions>) {
    if cli.bench_units.is_none() {
        return;
    }
    // skip the first second (asset spawning)
    if time.elapsed_secs() < 1.0 {
        return;
    }
    stats.frame_times.push(time.delta_secs());
    stats.sim_ms.push(sim.step_ms);
    stats.units.push(sim.world.living_units().count() as u32);
}

fn write_report_on_exit(mut exits: MessageReader<AppExit>, mut stats: ResMut<BenchStats>, cli: Res<CliOptions>, info: Option<Res<SystemInfo>>, sim: Option<Res<GameSim>>) {
    if exits.read().next().is_none() || stats.written || cli.bench_units.is_none() {
        return;
    }
    stats.written = true;
    let n = stats.frame_times.len().max(1);
    let total: f32 = stats.frame_times.iter().sum();
    let avg_fps = n as f32 / total.max(1e-6);
    let mut sorted = stats.frame_times.clone();
    sorted.sort_by(|a, b| b.partial_cmp(a).unwrap());
    let worst_1pct = sorted.iter().take((n / 100).max(1)).sum::<f32>() / (n / 100).max(1) as f32;
    let low_1pct_fps = 1.0 / worst_1pct.max(1e-6);
    let sim_avg = stats.sim_ms.iter().sum::<f32>() / n as f32;
    let sim_max = stats.sim_ms.iter().cloned().fold(0.0, f32::max);
    let units_avg = stats.units.iter().sum::<u32>() as f32 / n as f32;
    let units_max = stats.units.iter().cloned().max().unwrap_or(0);
    let hw = info.map(|i| format!("os: {}\nkernel: {}\ncpu: {} ({} cores)\nmemory: {}", i.os, i.kernel, i.cpu, i.core_count, i.memory)).unwrap_or_else(|| "hardware: unknown".into());
    let renderer = std::env::var("SA_RENDERER_NOTE").unwrap_or_default();
    let map = sim.as_ref().map(|s| s.world.map.name.clone()).unwrap_or_default();
    let report = format!(
        "Swarm Assault 3D benchmark\nmap: {map}\nextra units per team (--bench): {}\n{hw}\n{renderer}\nframes measured: {n}\nwall time: {total:.1} s\naverage fps: {avg_fps:.1}\n1% low fps: {low_1pct_fps:.1}\nsim step ms per frame: avg {sim_avg:.2}  max {sim_max:.2}\nliving units: avg {units_avg:.0}  max {units_max}\n",
        cli.bench_units.unwrap_or(0)
    );
    info!("BENCHMARK\n{report}");
    std::fs::create_dir_all(crate::user_path("benchmarks")).ok();
    let ts = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
    let path = crate::user_path(&format!("benchmarks/bench_{}_{ts}.txt", cli.bench_units.unwrap_or(0))).to_string_lossy().to_string();
    if let Err(e) = std::fs::write(&path, &report) {
        error!("could not write {path}: {e}");
    } else {
        info!("benchmark written to {path}");
    }
}
