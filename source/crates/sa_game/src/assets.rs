//! Loads the glTF models referenced by the data files, builds animation graphs and team materials.
//! Models that do not exist yet fall back to a labelled placeholder mesh so every unit is visible.

use std::collections::HashMap;

use bevy::asset::LoadState;
use bevy::gltf::Gltf;
use bevy::prelude::*;
use bevy::world_serialization::WorldAsset;

use crate::sim_plugin::GameSim;
use crate::{AppState, asset_root};

/// Clip names the simulation can request (see docs/ASSET_CHECKLIST.md).
pub const CLIP_NAMES: [&str; 6] = ["idle", "move", "fly", "attack", "death", "turret_fire"];

pub struct ModelAssets {
    pub path: String,
    pub gltf: Option<Handle<Gltf>>,
    pub scene: Option<Handle<WorldAsset>>,
    pub graph: Option<Handle<AnimationGraph>>,
    pub clips: HashMap<String, AnimationNodeIndex>,
    /// Seconds per clip (for one-shot clips like attack/death).
    pub clip_len: HashMap<String, f32>,
    pub ready: bool,
    pub missing: bool,
}

#[derive(Resource)]
pub struct GameAssets {
    pub models: HashMap<String, ModelAssets>,
    pub team_materials: HashMap<u8, Handle<StandardMaterial>>,
    pub team_colony_materials: HashMap<u8, Handle<StandardMaterial>>,
    pub neutral_material: Handle<StandardMaterial>,
    pub neutral_colony_material: Handle<StandardMaterial>,
    pub placeholder_body: Handle<Mesh>,
    pub placeholder_head: Handle<Mesh>,
    pub placeholder_colony: Handle<Mesh>,
    pub bit_mesh: Handle<Mesh>,
    pub bit_material: Handle<StandardMaterial>,
    pub projectile_mesh: Handle<Mesh>,
    pub projectile_material: Handle<StandardMaterial>,
    pub impact_mesh: Handle<Mesh>,
    pub impact_materials: HashMap<String, Handle<StandardMaterial>>,
    pub dark_material: Handle<StandardMaterial>,
    pub corpse_material: Handle<StandardMaterial>,
    /// team colour factors (sRGB) used to tint baked glTF materials
    pub team_colors: HashMap<u8, Color>,
    pub team_colony_colors: HashMap<u8, Color>,
    /// (original glTF material, team key) -> tinted copy
    pub tint_cache: HashMap<(AssetId<StandardMaterial>, u32), Handle<StandardMaterial>>,
    /// tinted copy -> original glTF material
    pub tint_origin: HashMap<AssetId<StandardMaterial>, Handle<StandardMaterial>>,
}

impl GameAssets {
    pub fn team_color(&self, team: u8) -> Color {
        self.team_colors.get(&team).copied().unwrap_or(Color::srgb(0.16, 0.16, 0.16))
    }

    pub fn colony_color(&self, team: u8) -> Color {
        self.team_colony_colors.get(&team).copied().unwrap_or(Color::srgb(0.78, 0.72, 0.66))
    }

    /// The muted colony colour of the towers (`M_ColonyPale`): the team colour a fifth of the way to
    /// its own grey and a quarter darker, as the original's towers are a duller shade of the team
    /// colour (dark red for red, beige for yellow).  Mirrors `pale_lin()` in
    /// source/blender/scripts/colony_tripo.py (both in linear light).
    pub fn colony_pale_color(&self, team: u8) -> Color {
        let c = self.colony_color(team).to_linear();
        let l = 0.2126 * c.red + 0.7152 * c.green + 0.0722 * c.blue;
        let pale = |v: f32| (v * 0.8 + l * 0.2) * 0.75;
        Color::linear_rgb(pale(c.red), pale(c.green), pale(c.blue))
    }

    pub fn team_material(&self, team: u8) -> Handle<StandardMaterial> {
        self.team_materials.get(&team).cloned().unwrap_or_else(|| self.neutral_material.clone())
    }

    pub fn colony_material(&self, team: u8) -> Handle<StandardMaterial> {
        self.team_colony_materials.get(&team).cloned().unwrap_or_else(|| self.neutral_colony_material.clone())
    }

    pub fn model(&self, name: &str) -> Option<&ModelAssets> {
        self.models.get(name)
    }
}

pub struct GameAssetsPlugin;

impl Plugin for GameAssetsPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(AppState::Loading), load_assets.after(crate::sim_plugin::load_sim))
            .add_systems(Update, poll_assets.run_if(in_state(AppState::Loading)));
    }
}

fn load_assets(
    mut commands: Commands,
    sim: Res<GameSim>,
    asset_server: Res<AssetServer>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    let root = std::path::PathBuf::from(asset_root());
    let mut models = HashMap::new();
    let mut names: Vec<String> = sim.world.defs.units.iter().map(|u| u.model.clone()).collect();
    names.extend(sim.world.defs.colonies.iter().map(|c| c.model.clone()));
    for kind in ["rock_large", "rock_small", "mushroom", "flower", "grass_tuft", "colony_bit", "ant_hole", "candy_jelly_bean", "candy_gumnut", "candy_choc_chip", "candy_smarty", "candy_jaffa"] {
        names.push(kind.to_string());
    }
    names.sort();
    names.dedup();
    for name in names {
        if name.is_empty() {
            continue;
        }
        let rel = format!("models/{name}.glb");
        let exists = root.join(&rel).exists();
        let gltf = if exists { Some(asset_server.load::<Gltf>(rel.clone())) } else { None };
        // creep plants are built in code (plants.rs) unless a model file is supplied
        if !exists && !name.starts_with("plant_") {
            warn!("model {rel} not found: using placeholder geometry");
        }
        models.insert(name, ModelAssets { path: rel, gltf, scene: None, graph: None, clips: HashMap::new(), clip_len: HashMap::new(), ready: false, missing: !exists });
    }

    let mut team_materials = HashMap::new();
    let mut team_colony_materials = HashMap::new();
    let mut team_colors = HashMap::new();
    let mut team_colony_colors = HashMap::new();
    // team 0 (neutral, colour "X") keeps the defaults below: near-black creatures, but colonies in
    // the original's pale beige (tinting them like the units made neutral colonies near-black)
    for t in sim.world.teams.iter().filter(|t| t.def.id != 0) {
        let [r, g, b] = sa_sim::team_rgb(&t.def.color);
        team_materials.insert(t.def.id, materials.add(StandardMaterial { base_color: Color::srgb(r, g, b), perceptual_roughness: 0.5, ..default() }));
        team_colors.insert(t.def.id, Color::srgb(r, g, b));
        // colony bodies take the team colour as it is: their textures bake their own shading on
        // near-white (a lighter tint washed the campaign gold out to cream)
        team_colony_materials.insert(t.def.id, materials.add(StandardMaterial { base_color: Color::srgb(r, g, b), perceptual_roughness: 0.55, ..default() }));
        team_colony_colors.insert(t.def.id, Color::srgb(r, g, b));
    }
    // neutral (team 0): near-black units, grey colony bodies
    team_colors.entry(0).or_insert(Color::srgb(0.16, 0.16, 0.16));
    team_colony_colors.entry(0).or_insert(Color::srgb(0.78, 0.72, 0.66));
    let neutral_material = materials.add(StandardMaterial { base_color: Color::srgb(0.16, 0.16, 0.16), perceptual_roughness: 0.6, ..default() });
    let neutral_colony_material = materials.add(StandardMaterial { base_color: Color::srgb(0.78, 0.72, 0.66), perceptual_roughness: 0.6, ..default() });
    let mut impact_materials = HashMap::new();
    for (name, color) in [
        ("hit_small", Color::srgba(1.0, 0.9, 0.5, 0.8)),
        ("bite", Color::srgba(1.0, 0.3, 0.2, 0.7)),
        ("explosion_medium", Color::srgba(1.0, 0.55, 0.15, 0.85)),
        ("explosion_big", Color::srgba(1.0, 0.4, 0.1, 0.9)),
        ("explosion_shrapnel", Color::srgba(1.0, 0.7, 0.2, 0.8)),
        ("paralyze", Color::srgba(0.6, 0.3, 1.0, 0.8)),
        ("hit_spear", Color::srgba(0.9, 0.9, 1.0, 0.7)),
        ("hit_star", Color::srgba(0.8, 1.0, 0.8, 0.7)),
        ("hit_sonic", Color::srgba(0.4, 0.9, 1.0, 0.7)),
        ("colony_explode", Color::srgba(1.0, 0.5, 0.1, 0.9)),
    ] {
        impact_materials.insert(name.to_string(), materials.add(StandardMaterial { base_color: color, emissive: LinearRgba::from(color) * 2.0, alpha_mode: AlphaMode::Blend, unlit: true, ..default() }));
    }
    let assets = GameAssets {
        models,
        team_materials,
        team_colony_materials,
        neutral_material,
        neutral_colony_material,
        placeholder_body: meshes.add(Capsule3d::new(0.28, 0.6).mesh().build()),
        placeholder_head: meshes.add(Sphere::new(0.2).mesh().ico(2).unwrap()),
        placeholder_colony: meshes.add(Sphere::new(2.6).mesh().ico(3).unwrap()),
        bit_mesh: meshes.add(Sphere::new(0.28).mesh().ico(1).unwrap()),
        bit_material: materials.add(StandardMaterial { base_color: Color::srgb(1.0, 0.85, 0.2), emissive: LinearRgba::new(0.8, 0.6, 0.1, 1.0), perceptual_roughness: 0.3, ..default() }),
        projectile_mesh: meshes.add(Sphere::new(0.09).mesh().ico(1).unwrap()),
        projectile_material: materials.add(StandardMaterial { base_color: Color::srgb(0.95, 0.9, 0.7), emissive: LinearRgba::new(1.5, 1.2, 0.5, 1.0), unlit: true, ..default() }),
        impact_mesh: meshes.add(Sphere::new(1.0).mesh().ico(2).unwrap()),
        impact_materials,
        dark_material: materials.add(StandardMaterial { base_color: Color::srgb(0.12, 0.1, 0.08), perceptual_roughness: 0.7, ..default() }),
        corpse_material: materials.add(StandardMaterial { base_color: Color::srgb(0.3, 0.28, 0.22), perceptual_roughness: 0.9, ..default() }),
        team_colors,
        team_colony_colors,
        tint_cache: HashMap::new(),
        tint_origin: HashMap::new(),
    };
    commands.insert_resource(assets);
}

fn poll_assets(
    mut assets: ResMut<GameAssets>,
    asset_server: Res<AssetServer>,
    gltfs: Res<Assets<Gltf>>,
    clips: Res<Assets<AnimationClip>>,
    mut graphs: ResMut<Assets<AnimationGraph>>,
    mut next: ResMut<NextState<AppState>>,
    time: Res<Time>,
    mut waited: Local<f32>,
) {
    *waited += time.delta_secs();
    let mut all_ready = true;
    for (name, m) in assets.models.iter_mut() {
        if m.ready || m.missing {
            continue;
        }
        let Some(handle) = &m.gltf else { continue };
        match asset_server.load_state(handle.id()) {
            LoadState::Failed(e) => {
                error!("failed to load {}: {e}", m.path);
                m.missing = true;
                continue;
            }
            LoadState::Loaded => {}
            _ => {
                all_ready = false;
                continue;
            }
        }
        let Some(gltf) = gltfs.get(handle) else {
            all_ready = false;
            continue;
        };
        m.scene = gltf.default_scene.clone().or_else(|| gltf.scenes.first().cloned());
        if !gltf.named_animations.is_empty() {
            let mut graph = AnimationGraph::new();
            let mut clip_nodes = HashMap::new();
            let mut lens = HashMap::new();
            let mut pending = false;
            for (clip_name, clip_handle) in &gltf.named_animations {
                let node = graph.add_clip(clip_handle.clone(), 1.0, graph.root);
                clip_nodes.insert(clip_name.to_string(), node);
                match clips.get(clip_handle) {
                    Some(c) => {
                        lens.insert(clip_name.to_string(), c.duration());
                    }
                    None => pending = true,
                }
            }
            if pending {
                all_ready = false;
                continue;
            }
            m.graph = Some(graphs.add(graph));
            m.clips = clip_nodes;
            m.clip_len = lens;
        }
        m.ready = true;
        info!("model {name} ready ({} clips: {:?})", m.clips.len(), m.clips.keys().collect::<Vec<_>>());
    }
    if all_ready || *waited > 60.0 {
        if !all_ready {
            warn!("asset loading timed out; continuing with placeholders");
            for m in assets.models.values_mut() {
                if !m.ready {
                    m.missing = true;
                }
            }
        }
        next.set(AppState::InGame);
    }
}
