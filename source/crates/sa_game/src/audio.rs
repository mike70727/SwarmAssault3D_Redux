//! Audio. The simulation emits named sound hooks (weapon `fire_sound` / `impact_sound`,
//! `Sound { id }` events for colony and bit events); this plugin turns them into sounds.
//!
//! With the player's copy of the original game (see original.rs) the original sounds play: the
//! weapons and impacts as OpenSA wired them, colony and bit events, the bugs' acknowledgements when
//! they are selected or ordered, a looping ambience per tileset (frogs, wind, crickets, the candy
//! dreamscape) and the menu theme. Without a copy the synthesized set in `assets/audio` plays
//! (docs/AUDIO_HOOKS.md); hooks without a sound stay silent.

use std::collections::{HashMap, HashSet};
use std::sync::Arc;

use bevy::audio::{AudioPlayer, AudioSink, AudioSinkPlayback, AudioSource, PlaybackSettings, Volume};
use bevy::prelude::*;
use bevy::state::state_scoped::DespawnOnExit;
use sa_sim::{Anim, SimEvent, UnitId};

use crate::AppState;
use crate::asset_root;
use crate::camera::RtsCamera;
use crate::original::Original;
use crate::selection::{OrderMode, Selection};
use crate::sim_plugin::GameSim;

/// Sound hook -> original sound names (several = a random variant each time).
const ORIGINAL_SOUNDS: &[(&str, &[&str])] = &[
    ("ant_crunch", &["ANTCRUNCH"]),
    ("savage_attack", &["SAVAGEATTACK"]),
    ("rocket_launch", &["ROCKETLAUNCH"]),
    ("minigun", &["MINIGUN"]),
    ("shrapnel_fire", &["SHRAPNELFIRE"]),
    ("cannon", &["CANNON"]),
    ("sniper_fire", &["SNIPERFIRE"]),
    ("sniper_hit", &["SNIPERHIT"]),
    ("missile_launch", &["MISSILELAUNCH"]),
    ("spear", &["SPEAR"]),
    ("star_launch", &["STARLAUNCH"]),
    ("star_hit", &["STARHIT"]),
    ("machinegun", &["MACHINEGUN"]),
    ("arrow", &["ARROW"]),
    ("paralysis", &["PARALYSIS"]),
    ("sonic", &["SONIC"]),
    ("turret_mg", &["TURRETMACHINEGUN"]),
    ("chaingun", &["CHAINGUN"]),
    ("explosion1", &["EXPLOSION1"]),
    ("explosion2", &["EXPLOSION2"]),
    ("explosion3", &["EXPLOSION3"]),
    ("ricochet", &["RIC1", "RIC2", "RIC3", "RIC4"]),
    ("brakebomb_explode", &["BRAKEBOMBEXPLODE"]),
    ("bouncebomb_explode", &["BOUNCEBOMBEXPLODE"]),
    ("gobstopper_explode", &["GOBSTOPPEREXPLODE"]),
    ("bounce", &["BOUNCE"]),
    ("whip_fire", &["WHIPFIRE"]),
    ("puffball_spawn", &["PUFFBALLSPAWN"]),
    ("freckle_fire", &["FRECKLEFIRE"]),
    ("bomber_buzz", &["BOMBERBUZZ"]),
    ("fly_buzz", &["FLYBUZZ"]),
    ("moth_flutter", &["MOTHFLUTTER"]),
    ("flying_machine", &["FLYINGMACHINE"]),
    ("steam_puff", &["STEAMPUFF"]),
    ("colony_lost", &["POWERDOWN"]),
    ("colony_captured", &["POWERUP"]),
    ("colony_explode", &["COLONYEXPLODE"]),
    ("bit_pickup", &["COLONYPICKUP"]),
    ("bit_land", &["COLONYPICKUPLAND"]),
    ("bit_expired", &["COLONYPICKUPTIMEOUT"]),
    ("ant_hole", &["ANTHOLEOPEN"]),
    ("production_change", &["PRODUCTIONCHANGE"]),
    ("production_stop", &["SELECT"]),
    ("victory", &["GAMEOVERWOW"]),
    ("defeat", &["GAMEOVERBOOM"]),
    ("crash", &["CRASH"]),
    ("ui_click", &["CLICK"]),
    ("voice_ant", &["STANDANTA", "STANDANTB", "STANDANTC"]),
    ("voice_beetle", &["STANDBEETLEA", "STANDBEETLEB", "STANDBEETLEC"]),
    ("voice_spider", &["STANDSPIDERA", "STANDSPIDERB", "STANDSPIDERC"]),
    ("voice_scorpion", &["STANDSCORPIONA", "STANDSCORPIONB", "STANDSCORPIONC"]),
    ("voice_wasp", &["STANDWASPA", "STANDWASPB", "STANDWASPC"]),
    ("voice_neutral", &["COMMAND"]),
    ("ambient_normal", &["FROGS"]),
    ("ambient_desert", &["WIND"]),
    ("ambient_swamp", &["CRICKETS"]),
    ("ambient_candy", &["DREAMSCAPE"]),
    ("menu_music", &["STARTBACKGROUND"]),
];

/// Hooks of the synthesized set that the original game does not have: silent with the originals
/// (bugs die without a scream, a new unit appears without a chime, as in the original).
const SILENT_WITH_ORIGINAL: &[&str] = &["death_ant", "death_beetle", "death_spider", "death_scorpion", "death_wasp", "death_neutral", "unit_ready"];

#[derive(Resource, Default)]
pub struct AudioLibrary {
    /// hook id -> sound variants
    pub sounds: HashMap<String, Vec<Handle<AudioSource>>>,
    /// ids requested at least once (listed in the benchmark/test logs so missing files are visible)
    pub requested: HashSet<String>,
    pub enabled: bool,
    pub master_volume: f32,
    /// the sounds come from the player's copy of the original game
    pub original: bool,
    /// per-frame limiter so a big battle does not spawn hundreds of players
    budget: u32,
    rng: u32,
}

impl AudioLibrary {
    /// A variant of a hook's sound (random when there are several).
    pub fn pick(&mut self, id: &str) -> Option<Handle<AudioSource>> {
        let v = self.sounds.get(id)?;
        if v.is_empty() {
            return None;
        }
        self.rng = self.rng.wrapping_mul(1_664_525).wrapping_add(1_013_904_223);
        Some(v[(self.rng >> 16) as usize % v.len()].clone())
    }

    /// Play a hook once (interface sounds: no distance attenuation).
    pub fn play_ui(&mut self, commands: &mut Commands, id: &str, volume: f32) {
        self.requested.insert(id.to_string());
        if !self.enabled {
            return;
        }
        if let Some(h) = self.pick(id) {
            commands.spawn((AudioPlayer::new(h), PlaybackSettings::DESPAWN.with_volume(Volume::Linear(self.master_volume * volume))));
        }
    }
}

fn load_library(asset_server: &AssetServer, sources: &mut Assets<AudioSource>, original: &Original) -> AudioLibrary {
    let mut sounds: HashMap<String, Vec<Handle<AudioSource>>> = HashMap::new();
    // the game's own synthesized set
    let dir = std::path::PathBuf::from(asset_root()).join("audio");
    let mut own = 0;
    if let Ok(rd) = std::fs::read_dir(&dir) {
        for entry in rd.flatten() {
            let path = entry.path();
            let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("").to_ascii_lowercase();
            if (ext == "ogg" || ext == "wav")
                && let Some(stem) = path.file_stem().and_then(|s| s.to_str())
            {
                let rel = format!("audio/{}", path.file_name().unwrap().to_string_lossy());
                sounds.insert(stem.to_string(), vec![asset_server.load::<AudioSource>(rel)]);
                own += 1;
            }
        }
    }
    // the original sounds replace them where they exist
    let mut from_original = 0;
    let is_original = original.get().is_some();
    if let Some(orig) = original.get() {
        for id in SILENT_WITH_ORIGINAL {
            sounds.remove(*id);
        }
        let mut cache: HashMap<&str, Vec<Handle<AudioSource>>> = HashMap::new();
        for (hook, names) in ORIGINAL_SOUNDS {
            let mut variants = Vec::new();
            for name in names.iter() {
                let hs = cache.entry(name).or_insert_with(|| {
                    orig.sound(name)
                        .map(|takes| takes.iter().map(|s| sources.add(AudioSource { bytes: Arc::clone(&s.wav) })).collect())
                        .unwrap_or_default()
                });
                variants.extend(hs.iter().cloned());
            }
            if !variants.is_empty() {
                sounds.insert(hook.to_string(), variants);
                from_original += 1;
            }
        }
    }
    info!("audio: {own} sound files in {}, {from_original} hooks use the original sounds", dir.display());
    AudioLibrary { sounds, requested: HashSet::new(), enabled: true, master_volume: 0.0, original: is_original, budget: 0, rng: 12345 }
}

pub struct GameAudioPlugin;

impl Plugin for GameAudioPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, setup_audio)
            .add_systems(OnEnter(AppState::Menu), start_menu_music)
            .add_systems(OnEnter(AppState::InGame), start_ambience)
            .add_systems(Update, (play_sim_sounds, play_voices, creature_loops).run_if(in_state(AppState::InGame)))
            .add_systems(Update, update_loop_volume);
    }
}

fn setup_audio(mut commands: Commands, asset_server: Res<AssetServer>, mut sources: ResMut<Assets<AudioSource>>, original: Res<Original>, settings: Res<crate::settings::Settings>) {
    let mut lib = load_library(&asset_server, &mut sources, &original);
    lib.master_volume = settings.master_volume.clamp(0.0, 1.0);
    lib.enabled = settings.sound_enabled;
    commands.insert_resource(lib);
}

/// A looping sound (menu theme, ambience): its volume follows the settings.
#[derive(Component)]
struct LoopSound {
    volume: f32,
}

fn spawn_loop(commands: &mut Commands, lib: &mut AudioLibrary, id: &str, volume: f32, state: AppState) {
    lib.requested.insert(id.to_string());
    let Some(h) = lib.pick(id) else { return };
    let v = if lib.enabled { lib.master_volume * volume } else { 0.0 };
    commands.spawn((LoopSound { volume }, DespawnOnExit(state), AudioPlayer::new(h), PlaybackSettings::LOOP.with_volume(Volume::Linear(v))));
}

fn start_menu_music(mut commands: Commands, lib: Option<ResMut<AudioLibrary>>) {
    if let Some(mut lib) = lib {
        spawn_loop(&mut commands, &mut lib, "menu_music", 0.55, AppState::Menu);
    }
}

fn start_ambience(mut commands: Commands, lib: Option<ResMut<AudioLibrary>>, sim: Res<GameSim>) {
    let Some(mut lib) = lib else { return };
    let id = format!("ambient_{}", sim.world.map.tileset);
    spawn_loop(&mut commands, &mut lib, &id, 0.3, AppState::InGame);
}

fn update_loop_volume(lib: Option<Res<AudioLibrary>>, mut sinks: Query<(&LoopSound, &mut AudioSink)>) {
    let Some(lib) = lib else { return };
    if !lib.is_changed() {
        return;
    }
    for (l, mut sink) in &mut sinks {
        sink.set_volume(Volume::Linear(if lib.enabled { lib.master_volume * l.volume } else { 0.0 }));
    }
}

/// Translate simulation events into sound hooks and play the ones that have sounds.
fn play_sim_sounds(mut commands: Commands, sim: Res<GameSim>, mut lib: ResMut<AudioLibrary>, cam: Option<Res<RtsCamera>>, mut landed: Local<HashSet<u32>>) {
    lib.budget = 12;
    let focus = cam.as_ref().map(|c| Vec2::new(c.focus.x, c.focus.z)).unwrap_or(Vec2::ZERO);
    let zoom = cam.as_ref().map(|c| c.distance).unwrap_or(26.0);
    let mut requests: Vec<(String, Vec2)> = Vec::new();
    for e in &sim.events {
        match e {
            SimEvent::Sound { id, pos } => requests.push((id.clone(), *pos)),
            SimEvent::Impact { pos, sound, .. } if !sound.is_empty() => requests.push((sound.clone(), *pos)),
            // (weapon sounds arrive as SimEvent::Sound when the shot is released: World::fire_weapon)
            SimEvent::UnitDied(id) => {
                if let Some(u) = sim.world.unit(*id) {
                    let def = sim.world.unit_def(u);
                    if def.model == "neutral_flying_machine" {
                        requests.push(("crash".into(), u.pos));
                    } else {
                        requests.push((format!("death_{:?}", def.family).to_ascii_lowercase(), u.pos));
                    }
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
            SimEvent::BitExpired(id) => {
                if let Some(b) = sim.world.bit(*id) {
                    requests.push(("bit_expired".into(), b.end));
                }
            }
            _ => {}
        }
    }
    // colony bits thud when they land
    for b in &sim.world.bits {
        if b.alive && b.landed() && landed.insert(b.id) {
            requests.push(("bit_land".into(), b.end));
        }
    }
    landed.retain(|id| sim.world.bit(*id).is_some_and(|b| b.alive));
    for (id, pos) in requests {
        lib.requested.insert(id.clone());
        if !lib.enabled || lib.budget == 0 {
            continue;
        }
        // simple distance attenuation relative to the camera focus
        let d = pos.distance(focus);
        let vol = (1.0 - (d / (zoom * 1.6)).clamp(0.0, 0.9)) * lib.master_volume;
        if vol <= 0.05 {
            continue;
        }
        let Some(handle) = lib.pick(&id) else { continue };
        lib.budget -= 1;
        commands.spawn((AudioPlayer::new(handle), PlaybackSettings::DESPAWN.with_volume(Volume::Linear(vol))));
    }
}

/// A looped creature sound: one player per hook, as loud as the nearest such creature is close.
#[derive(Component)]
struct CreatureLoop {
    hook: String,
}

/// Looped creature sounds (OpenSA AmbientSound / WithLoopedAttackSound): a flyer's buzz while it is
/// on the map, the Choc Freckle's spray while it attacks.
fn creature_loops(
    mut commands: Commands,
    sim: Res<GameSim>,
    mut lib: ResMut<AudioLibrary>,
    cam: Option<Res<RtsCamera>>,
    mut playing: Query<(Entity, &CreatureLoop, Option<&mut AudioSink>)>,
) {
    let focus = cam.as_ref().map(|c| Vec2::new(c.focus.x, c.focus.z)).unwrap_or(Vec2::ZERO);
    let zoom = cam.as_ref().map(|c| c.distance).unwrap_or(26.0);
    let mut want: HashMap<String, f32> = HashMap::new();
    for u in sim.world.living_units() {
        let def = sim.world.unit_def(u);
        let hook = if !def.ambient_sound.is_empty() {
            &def.ambient_sound
        } else if !def.attack_loop_sound.is_empty() && u.anim == Anim::Attack {
            &def.attack_loop_sound
        } else {
            continue;
        };
        let near = 1.0 - (u.pos.distance(focus) / (zoom * 1.6)).clamp(0.0, 1.0);
        let v = want.entry(hook.clone()).or_insert(0.0);
        *v = v.max(near);
    }
    let level = |near: f32, lib: &AudioLibrary| if lib.enabled { lib.master_volume * near * 0.6 } else { 0.0 };
    for (e, l, sink) in &mut playing {
        match want.remove(&l.hook) {
            Some(near) if near > 0.02 => {
                if let Some(mut sink) = sink {
                    sink.set_volume(Volume::Linear(level(near, &lib)));
                }
            }
            _ => commands.entity(e).despawn(),
        }
    }
    for (hook, near) in want {
        lib.requested.insert(hook.clone());
        if near <= 0.02 {
            continue;
        }
        if let Some(h) = lib.pick(&hook) {
            let v = level(near, &lib);
            commands.spawn((CreatureLoop { hook }, DespawnOnExit(AppState::InGame), AudioPlayer::new(h), PlaybackSettings::LOOP.with_volume(Volume::Linear(v))));
        }
    }
}

/// The bugs answer when the player selects them or gives them an order (the original's
/// STAND<family><A/B/C> acknowledgements), at most a few times a second.
fn play_voices(
    mut commands: Commands,
    sim: Res<GameSim>,
    selection: Res<Selection>,
    mode: Res<OrderMode>,
    time: Res<Time>,
    mut lib: ResMut<AudioLibrary>,
    mut last_sel: Local<Vec<UnitId>>,
    mut last_order: Local<f32>,
    mut last_voice: Local<f32>,
) {
    let now = time.elapsed_secs();
    let added = selection.units.iter().any(|id| !last_sel.contains(id));
    let ordered = mode.last_order.is_some_and(|(_, t, _)| t > *last_order);
    if let Some((_, t, _)) = mode.last_order {
        *last_order = last_order.max(t);
    }
    last_sel.clone_from(&selection.units);
    if !(added || ordered) || now - *last_voice < 0.3 {
        return;
    }
    let Some(u) = selection.units.iter().find_map(|id| sim.world.unit(*id)) else { return };
    if u.team != sim.human_team() {
        return;
    }
    let id = format!("voice_{:?}", sim.world.unit_def(u).family).to_ascii_lowercase();
    *last_voice = now;
    lib.play_ui(&mut commands, &id, 0.8);
}
