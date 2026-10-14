//! Audio hooks. The simulation emits named sound ids (weapon `fire_sound`/`impact_sound`,
//! `Sound { id }` events for colony/bit events). This plugin plays `assets/audio/<id>.ogg` (or .wav)
//! when such a file exists and silently ignores ids without a file, so the game ships without any
//! original audio but every hook is in place (see docs/AUDIO_HOOKS.md).

use std::collections::{HashMap, HashSet};

use bevy::audio::{AudioPlayer, AudioSource, PlaybackSettings, Volume};
use bevy::prelude::*;
use sa_sim::{SimEvent, Target};

use crate::AppState;
use crate::asset_root;
use crate::camera::RtsCamera;
use crate::sim_plugin::GameSim;

#[derive(Resource, Default)]
pub struct AudioLibrary {
    pub sounds: HashMap<String, Handle<AudioSource>>,
    /// ids requested at least once (listed in the benchmark/test logs so missing files are visible)
    pub requested: HashSet<String>,
    pub enabled: bool,
    pub master_volume: f32,
    /// per-frame limiter so a big battle does not spawn hundreds of players
    budget: u32,
}

impl AudioLibrary {
    pub fn load(asset_server: &AssetServer) -> Self {
        let dir = std::path::PathBuf::from(asset_root()).join("audio");
        let mut sounds = HashMap::new();
        if let Ok(rd) = std::fs::read_dir(&dir) {
            for entry in rd.flatten() {
                let path = entry.path();
                let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("").to_ascii_lowercase();
                if ext == "ogg" || ext == "wav" {
                    if let Some(stem) = path.file_stem().and_then(|s| s.to_str()) {
                        let rel = format!("audio/{}", path.file_name().unwrap().to_string_lossy());
                        sounds.insert(stem.to_string(), asset_server.load::<AudioSource>(rel));
                    }
                }
            }
        }
        info!("audio: {} sound files found in {}", sounds.len(), dir.display());
        Self { sounds, requested: HashSet::new(), enabled: true, master_volume: 0.8, budget: 0 }
    }
}

pub struct GameAudioPlugin;

impl Plugin for GameAudioPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, setup_audio).add_systems(Update, play_sim_sounds.run_if(in_state(AppState::InGame)));
    }
}

fn setup_audio(mut commands: Commands, asset_server: Res<AssetServer>, settings: Res<crate::settings::Settings>) {
    let mut lib = AudioLibrary::load(&asset_server);
    lib.master_volume = settings.master_volume.clamp(0.0, 1.0);
    lib.enabled = settings.sound_enabled;
    commands.insert_resource(lib);
}

/// Translate simulation events into sound ids and play the ones that have files.
fn play_sim_sounds(mut commands: Commands, sim: Res<GameSim>, mut lib: ResMut<AudioLibrary>, cam: Option<Res<RtsCamera>>) {
    lib.budget = 12;
    let focus = cam.as_ref().map(|c| Vec2::new(c.focus.x, c.focus.z)).unwrap_or(Vec2::ZERO);
    let zoom = cam.as_ref().map(|c| c.distance).unwrap_or(26.0);
    let mut requests: Vec<(String, Vec2)> = Vec::new();
    for e in &sim.events {
        match e {
            SimEvent::Sound { id, pos } => requests.push((id.clone(), *pos)),
            SimEvent::Impact { pos, sound, .. } if !sound.is_empty() => requests.push((sound.clone(), *pos)),
            SimEvent::AttackStarted { unit, .. } => {
                if let Some(u) = sim.world.unit(*unit)
                    && let Some(wn) = &sim.world.unit_def(u).weapon
                    && let Some(wi) = sim.world.defs.weapon(wn)
                {
                    let w = &sim.world.defs.weapons[wi as usize];
                    if !w.fire_sound.is_empty() {
                        requests.push((w.fire_sound.clone(), u.pos));
                    }
                }
            }
            SimEvent::TurretFired { colony, turret } => {
                if let Some(c) = sim.world.colonies.get(*colony as usize)
                    && let Some(t) = sim.world.colony_def(c).turrets.get(*turret)
                    && let Some(wi) = sim.world.defs.weapon(&t.weapon)
                {
                    let w = &sim.world.defs.weapons[wi as usize];
                    if !w.fire_sound.is_empty() {
                        requests.push((w.fire_sound.clone(), c.pos));
                    }
                }
            }
            SimEvent::UnitDied(id) => {
                if let Some(u) = sim.world.unit(*id) {
                    requests.push((format!("death_{:?}", sim.world.unit_def(u).family).to_ascii_lowercase(), u.pos));
                }
            }
            SimEvent::UnitSpawned(id) => {
                if let Some(u) = sim.world.unit(*id)
                    && u.team == sim.human_team()
                {
                    requests.push(("unit_ready".into(), u.pos));
                }
            }
            SimEvent::Victory(_) => requests.push(("victory".into(), focus)),
            SimEvent::TeamDefeated(t) if *t == sim.human_team() => requests.push(("defeat".into(), focus)),
            SimEvent::UnitParalyzed(id) => {
                if let Some(u) = sim.world.unit(*id) {
                    requests.push(("paralysis".into(), u.pos));
                }
            }
            SimEvent::BitPicked { unit, .. } => {
                if let Some(u) = sim.world.unit(*unit) {
                    requests.push(("bit_pickup".into(), u.pos));
                }
            }
            _ => {}
        }
    }
    for (id, pos) in requests {
        lib.requested.insert(id.clone());
        if !lib.enabled || lib.budget == 0 {
            continue;
        }
        let Some(handle) = lib.sounds.get(&id).cloned() else { continue };
        // simple distance attenuation relative to the camera focus
        let d = pos.distance(focus);
        let vol = (1.0 - (d / (zoom * 1.6)).clamp(0.0, 0.9)) * lib.master_volume;
        if vol <= 0.05 {
            continue;
        }
        lib.budget -= 1;
        commands.spawn((AudioPlayer::new(handle), PlaybackSettings::DESPAWN.with_volume(Volume::Linear(vol))));
    }
}

/// Target helper kept for future per-target hit sounds.
#[allow(dead_code)]
fn target_pos(sim: &GameSim, t: Target) -> Option<Vec2> {
    sim.world.target_pos(t)
}
