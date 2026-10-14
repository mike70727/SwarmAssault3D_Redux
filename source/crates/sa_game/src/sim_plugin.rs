//! Owns the `sa_sim::World`, steps it at a fixed rate and exposes the events of the last step.

use std::path::PathBuf;

use bevy::prelude::*;
use sa_sim::{Defs, MapDef, Order, SimEvent, UnitId, World};

use crate::{AppState, CliOptions, asset_root};

#[derive(Resource)]
pub struct GameSim {
    pub world: World,
    pub paused: bool,
    pub speed: f32,
    /// Fraction of the way from the previous to the current sim state (for interpolation).
    pub alpha: f32,
    /// Events produced by the most recent `step`s (consumed by the view systems each frame).
    pub events: Vec<SimEvent>,
    /// Wall-clock milliseconds spent in `World::step` since the last frame (perf HUD).
    pub step_ms: f32,
    pub assets_dir: PathBuf,
}

impl GameSim {
    pub fn human_team(&self) -> u8 {
        self.world.teams.iter().find(|t| t.def.controller == sa_sim::Controller::Human).map(|t| t.def.id).unwrap_or(1)
    }
}

/// Queue of orders the input layer wants to send to the simulation (applied before the next step).
#[derive(Resource, Default)]
pub struct PendingOrders(pub Vec<(Vec<UnitId>, Order)>);

pub struct SimPlugin;

impl Plugin for SimPlugin {
    fn build(&self, app: &mut App) {
        app.insert_resource(Time::<Fixed>::from_hz(30.0))
            .init_resource::<PendingOrders>()
            .add_systems(OnEnter(AppState::Loading), load_sim)
            .add_systems(FixedUpdate, step_sim.run_if(in_state(AppState::InGame)))
            .add_systems(Update, update_alpha.run_if(in_state(AppState::InGame)))
            // typing in the console (a space, brackets) must not pause the game or change its speed
            .add_systems(Update, pause_keys.run_if(in_state(AppState::InGame)).run_if(|c: Res<crate::console::ConsoleState>| !c.open))
            // every consumer (views, audio, HUD) reads `GameSim::events` during Update; drop them
            // afterwards so an event is handled exactly once
            .add_systems(Last, clear_sim_events.run_if(in_state(AppState::InGame)));
    }
}

pub fn load_sim(mut commands: Commands, cli: Res<CliOptions>, mut ground: Local<Option<sa_sim::procgen::GroundModel>>) {
    let assets_dir = PathBuf::from(asset_root());
    let world = if let Some(save) = &cli.load {
        match sa_sim::save::load(&PathBuf::from(save)) {
            Ok(w) => w,
            Err(e) => {
                error!("could not load save {save}: {e}");
                std::process::exit(2);
            }
        }
    } else {
        let defs = match Defs::load_dir(&assets_dir.join("data")) {
            Ok(d) => d,
            Err(e) => {
                error!("could not load game data from {}: {e}", assets_dir.display());
                std::process::exit(2);
            }
        };
        let mut map = if let Some((level, seed)) = crate::progress::parse_procedural(&cli.map) {
            // procedural mode: a new level from the run's seed, its ground learned from the levels
            if ground.is_none() {
                match sa_sim::procgen::GroundModel::from_dir(&assets_dir.join("data/maps")) {
                    Ok(m) => *ground = Some(m),
                    Err(e) => {
                        error!("could not read the levels for procedural mode: {e}");
                        std::process::exit(2);
                    }
                }
            }
            match sa_sim::procgen::generate(ground.as_ref().unwrap(), &defs, level, seed) {
                Ok(m) => m,
                Err(e) => {
                    error!("could not make procedural level {level}: {e}");
                    std::process::exit(2);
                }
            }
        } else {
            // a map name from the level list, or any path to a map file (test and showcase maps)
            let direct = PathBuf::from(&cli.map);
            let map_path = if direct.is_absolute() || direct.components().count() > 1 { direct } else { assets_dir.join("data/maps").join(&cli.map) };
            match MapDef::load(&map_path) {
                Ok(m) => m,
                Err(e) => {
                    error!("could not load map {}: {e}", cli.map);
                    std::process::exit(2);
                }
            }
        };
        if let Some(n) = cli.bench_units {
            for spawn in map.units.iter_mut() {
                spawn.count += n;
                spawn.spread = (n as f32).sqrt() * 0.9 + 2.0;
            }
            map.rules.unit_cap = Some(map.rules.unit_cap.unwrap_or(60).max(n * 2 + 40));
        }
        if cli.autoplay {
            for t in map.teams.iter_mut() {
                if t.controller == sa_sim::Controller::Human {
                    t.controller = sa_sim::Controller::Bot;
                    t.bot_profile = "hard".into();
                }
            }
        }
        match World::new(defs, map) {
            Ok(w) => w,
            Err(e) => {
                error!("could not build world: {e}");
                std::process::exit(2);
            }
        }
    };
    info!("map '{}' loaded: {} units, {} colonies", world.map.name, world.living_units().count(), world.colonies.len());
    commands.insert_resource(GameSim { world, paused: cli.paused, speed: cli.speed.max(0.05), alpha: 1.0, events: Vec::new(), step_ms: 0.0, assets_dir });
}

fn step_sim(mut sim: ResMut<GameSim>, mut pending: ResMut<PendingOrders>, mut fixed: ResMut<Time<Fixed>>, settings: Res<crate::settings::Settings>) {
    // keep the fixed clock in sync with the data-driven tick rate and the speed multiplier
    let base_hz = if settings.tick_hz > 0.0 { settings.tick_hz } else { sim.world.defs.rules.tick_hz };
    let hz = (base_hz as f64 * sim.speed as f64).max(1.0);
    if (fixed.timestep().as_secs_f64() - 1.0 / hz).abs() > 1e-6 {
        fixed.set_timestep_hz(hz);
    }
    for (ids, order) in pending.0.drain(..) {
        sim.world.issue(&ids, order);
    }
    if sim.paused {
        return;
    }
    let t0 = std::time::Instant::now();
    sim.world.step();
    sim.step_ms += t0.elapsed().as_secs_f32() * 1000.0;
    let mut ev = sim.world.drain_events();
    sim.events.append(&mut ev);
}

fn clear_sim_events(mut sim: ResMut<GameSim>) {
    sim.events.clear();
}

fn update_alpha(mut sim: ResMut<GameSim>, fixed: Res<Time<Fixed>>) {
    sim.alpha = if sim.paused { 1.0 } else { fixed.overstep_fraction() };
}

fn pause_keys(keys: Res<ButtonInput<KeyCode>>, controls: Res<crate::controls::Controls>, mut sim: ResMut<GameSim>) {
    if controls.just_pressed(&keys, "pause") {
        sim.paused = !sim.paused;
    }
    if controls.just_pressed(&keys, "speed_up") {
        sim.speed = (sim.speed * 1.5).min(8.0);
    }
    if controls.just_pressed(&keys, "speed_down") {
        sim.speed = (sim.speed / 1.5).max(0.25);
    }
}
