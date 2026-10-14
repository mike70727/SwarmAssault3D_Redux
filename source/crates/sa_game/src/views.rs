//! Mirrors simulation state into Bevy entities: units (skinned glTF or placeholder), colonies with
//! rotating turret nodes, colony bits, projectiles and impact effects. Animation clips are chosen
//! from the unit's simulation state.

use std::collections::HashMap;
use std::time::Duration;

use bevy::gltf::GltfMaterialName;
use bevy::prelude::*;
use bevy::state::state_scoped::DespawnOnExit;
use bevy::world_serialization::WorldInstanceReady;
use sa_sim::{Anim, SimEvent, UnitId, UnitState};

use crate::AppState;
use crate::assets::GameAssets;
use crate::sim_plugin::GameSim;

#[derive(Component)]
pub struct UnitView {
    pub id: UnitId,
    pub model: String,
    pub placeholder: bool,
}

/// Animation bookkeeping for a unit view.
#[derive(Component, Default)]
pub struct AnimState {
    pub player: Option<Entity>,
    pub current: Option<Anim>,
    pub attack_seq: u32,
    pub ready: bool,
}

#[derive(Component)]
pub struct ColonyView {
    pub id: u32,
    pub team: u8,
    pub defeated: bool,
}

#[derive(Component)]
pub struct TurretNode {
    pub colony: u32,
    pub index: usize,
    pub fire_seq: u32,
    pub recoil: f32,
}

#[derive(Component)]
pub struct BitView(pub u32);

#[derive(Component)]
pub struct ProjectileView(pub u32);

#[derive(Component)]
pub struct ImpactFx {
    pub t: f32,
    pub life: f32,
    pub size: f32,
}

/// Marker: this scene root belongs to a team-coloured object (materials get replaced when ready).
#[derive(Component, Clone)]
pub struct TeamTint {
    pub team: u8,
    pub colony: bool,
}

/// Counters proving that animation clips were actually started (logged at quit by the test runs).
#[derive(Resource, Default, Debug)]
pub struct AnimStats {
    pub clip_starts: HashMap<String, u32>,
    pub players_bound: u32,
    pub turret_rotations: u32,
}

#[derive(Resource, Default)]
pub struct ViewIndex {
    pub units: HashMap<UnitId, Entity>,
    pub colonies: HashMap<u32, Entity>,
    pub bits: HashMap<u32, Entity>,
    pub projectiles: HashMap<u32, Entity>,
    /// Bumped by quick-load to force a full respawn.
    pub generation: u32,
}

pub struct ViewsPlugin;

impl Plugin for ViewsPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<ViewIndex>().init_resource::<AnimStats>().add_systems(
            Update,
            (sync_units, sync_colonies, sync_bits, sync_projectiles, spawn_impacts, animate_impacts, sync_animations, animate_turrets, draw_status_rings)
                .chain()
                .run_if(in_state(AppState::InGame)),
        );
    }
}

/// Paralysed units get a pulsing purple ring; defeated colonies a grey ring with the bit count.
fn draw_status_rings(sim: Res<GameSim>, time: Res<Time>, mut gizmos: Gizmos) {
    let flat = Quat::from_rotation_x(-std::f32::consts::FRAC_PI_2);
    let t = time.elapsed_secs();
    for u in sim.world.living_units() {
        if u.paralyzed > 0.0 {
            let r = sim.world.unit_def(u).radius + 0.25 + 0.08 * (t * 10.0).sin();
            gizmos.circle(Isometry3d::new(Vec3::new(u.pos.x, 0.12, u.pos.y), flat), r, Color::srgb(0.7, 0.35, 1.0));
        }
    }
    for c in &sim.world.colonies {
        if !c.active() {
            let half = sim.world.colony_def(c).half_extent + 0.6 + 0.2 * (t * 3.0).sin();
            gizmos.circle(Isometry3d::new(Vec3::new(c.pos.x, 0.1, c.pos.y), flat), half, Color::srgb(0.8, 0.8, 0.8));
        }
    }
}

pub fn sim_to_world(p: Vec2, height: f32) -> Vec3 {
    Vec3::new(p.x, height, p.y)
}

/// Rotation that points a model's forward axis along a simulation heading.
///
/// A heading `h` is the direction `(sin h, cos h)` in simulation space, which maps to Bevy
/// `(sin h, 0, cos h)`. The models face +z in their rest pose, and a right-handed rotation about Y
/// by `h` takes +z to exactly `(sin h, 0, cos h)`. (Rotating by `-h` instead mirrors the x
/// component: units heading east then faced west, so they walked and flew backwards whenever they
/// moved east or west.)
pub fn heading_to_quat(heading: f32) -> Quat {
    Quat::from_rotation_y(heading)
}

#[cfg(test)]
mod facing_tests {
    use super::*;

    #[test]
    fn model_forward_follows_the_heading() {
        for i in 0..16 {
            let h = i as f32 * std::f32::consts::TAU / 16.0;
            let dir = sa_sim::heading_to_dir(h);
            let forward = heading_to_quat(h) * Vec3::Z;
            let expected = Vec3::new(dir.x, 0.0, dir.y);
            assert!(forward.distance(expected) < 1e-4, "heading {h}: model faces {forward:?}, moves {expected:?}");
        }
    }
}

fn lerp_angle(a: f32, b: f32, t: f32) -> f32 {
    a + sa_sim::angle_diff(a, b) * t
}

/// Material name without Blender's `.001` style suffix (several objects of one colony each carry
/// their own baked copy of `M_Colony`).
pub fn base_material_name(name: &str) -> &str {
    name.split('.').next().unwrap_or(name)
}

/// Tinted copy of a loaded glTF material: keeps its baked colour/roughness/normal textures and
/// only replaces the colour factor (the textures of `M_Team`/`M_Colony` are baked untinted).
fn tinted_material(
    original: &Handle<StandardMaterial>,
    tint: Color,
    materials: &mut Assets<StandardMaterial>,
    cache: &mut HashMap<(AssetId<StandardMaterial>, u32), Handle<StandardMaterial>>,
    key: u32,
) -> Option<Handle<StandardMaterial>> {
    if let Some(h) = cache.get(&(original.id(), key)) {
        return Some(h.clone());
    }
    let mut m = materials.get(original)?.clone();
    m.base_color = tint;
    let h = materials.add(m);
    cache.insert((original.id(), key), h.clone());
    Some(h)
}

/// Apply team materials to every primitive of a spawned scene and register the animation player.
#[allow(clippy::too_many_arguments)]
fn on_scene_ready(
    ready: On<WorldInstanceReady>,
    mut commands: Commands,
    children: Query<&Children>,
    tints: Query<&TeamTint>,
    mat_names: Query<&GltfMaterialName>,
    mat_handles: Query<&MeshMaterial3d<StandardMaterial>>,
    names: Query<&Name>,
    players: Query<Entity, With<AnimationPlayer>>,
    parents: Query<&ChildOf>,
    mut anim_states: Query<&mut AnimState>,
    views: Query<&UnitView>,
    colony_views: Query<&ColonyView>,
    mut assets: ResMut<GameAssets>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    mut stats: ResMut<AnimStats>,
) {
    let root = ready.entity;
    let tint = tints.get(root).ok().cloned();
    // the view entity is the parent of the scene root
    let view_entity = parents.get(root).ok().map(|p| p.parent());
    let model_name = view_entity.and_then(|v| views.get(v).ok()).map(|v| v.model.clone());
    let colony_id = view_entity.and_then(|v| colony_views.get(v).ok()).map(|c| c.id);
    for child in children.iter_descendants(root) {
        if let (Some(t), Ok(name)) = (&tint, mat_names.get(child)) {
            let (tint_color, key) = match base_material_name(&name.0) {
                "M_Team" => (Some(assets.team_color(t.team)), t.team as u32),
                "M_Colony" => (Some(assets.colony_color(t.team)), 100 + t.team as u32),
                _ => (None, 0),
            };
            if let Some(color) = tint_color {
                let original = mat_handles.get(child).ok().map(|h| h.0.clone());
                let replacement = original
                    .as_ref()
                    .and_then(|h| tinted_material(h, color, &mut materials, &mut assets.tint_cache, key))
                    .unwrap_or_else(|| if key >= 100 { assets.colony_material(t.team) } else { assets.team_material(t.team) });
                if let Some(o) = original {
                    assets.tint_origin.insert(replacement.id(), o);
                }
                commands.entity(child).insert(MeshMaterial3d(replacement));
            }
        }
        if players.get(child).is_ok() {
            if let Some(model) = &model_name
                && let Some(m) = assets.model(model)
                && let Some(graph) = &m.graph
            {
                commands.entity(child).insert((AnimationGraphHandle(graph.clone()), AnimationTransitions::new()));
            }
            if let Some(v) = view_entity
                && let Ok(mut st) = anim_states.get_mut(v)
            {
                st.player = Some(child);
                st.ready = true;
                stats.players_bound += 1;
            }
        }
        if let (Some(cid), Ok(n)) = (colony_id, names.get(child)) {
            let n = n.as_str();
            if let Some(idx) = n.strip_prefix("Turret_").and_then(|s| s.parse::<usize>().ok()) {
                commands.entity(child).insert(TurretNode { colony: cid, index: idx.saturating_sub(1), fire_seq: 0, recoil: 0.0 });
            }
        }
    }
}

fn spawn_unit_view(commands: &mut Commands, assets: &GameAssets, sim: &GameSim, id: UnitId) -> Option<Entity> {
    let u = sim.world.unit(id)?;
    let def = sim.world.unit_def(u);
    let height = def.altitude;
    let tf = Transform::from_translation(sim_to_world(u.pos, height)).with_rotation(heading_to_quat(u.heading));
    let model = assets.model(&def.model);
    let use_model = model.is_some_and(|m| m.ready && m.scene.is_some());
    let mut e = commands.spawn((UnitView { id, model: def.model.clone(), placeholder: !use_model }, DespawnOnExit(AppState::InGame), AnimState::default(), tf, Visibility::default(), Name::new(format!("{} #{}", def.name, id.idx))));
    if use_model {
        let m = model.unwrap();
        let scene = m.scene.clone().unwrap();
        let scale = def.model_scale;
        e.with_children(|p| {
            p.spawn((WorldAssetRoot(scene), TeamTint { team: u.team, colony: false }, Transform::from_scale(Vec3::splat(scale)))).observe(on_scene_ready);
        });
    } else {
        let body = assets.placeholder_body.clone();
        let head = assets.placeholder_head.clone();
        let mat = assets.team_material(u.team);
        let dark = assets.dark_material.clone();
        let r = def.radius;
        e.with_children(|p| {
            p.spawn((Mesh3d(body), MeshMaterial3d(mat.clone()), Transform::from_xyz(0.0, 0.3, 0.0).with_rotation(Quat::from_rotation_x(std::f32::consts::FRAC_PI_2)).with_scale(Vec3::splat(r / 0.38))));
            p.spawn((Mesh3d(head), MeshMaterial3d(dark), Transform::from_xyz(0.0, 0.32, r * 1.5).with_scale(Vec3::splat(r / 0.38 * 0.8))));
        });
    }
    Some(e.id())
}

fn sync_units(mut commands: Commands, sim: Res<GameSim>, assets: Res<GameAssets>, mut index: ResMut<ViewIndex>, mut q: Query<(&UnitView, &mut Transform)>) {
    // spawn views for new units, despawn removed ones
    let mut present: Vec<UnitId> = Vec::with_capacity(index.units.len());
    for u in sim.world.units_iter() {
        present.push(u.id);
        if !index.units.contains_key(&u.id)
            && let Some(e) = spawn_unit_view(&mut commands, &assets, &sim, u.id)
        {
            index.units.insert(u.id, e);
        }
    }
    let gone: Vec<UnitId> = index.units.keys().filter(|id| sim.world.unit(**id).is_none()).copied().collect();
    for id in gone {
        if let Some(e) = index.units.remove(&id) {
            commands.entity(e).despawn();
        }
    }
    let alpha = sim.alpha;
    for (view, mut tf) in q.iter_mut() {
        let Some(u) = sim.world.unit(view.id) else { continue };
        let def = sim.world.unit_def(u);
        let pos = u.prev_pos.lerp(u.pos, alpha);
        let heading = lerp_angle(u.prev_heading, u.heading, alpha);
        let mut height = def.altitude;
        if def.flying && u.alive() {
            height += 0.08 * (sim.world.time as f32 * 6.0 + u.id.idx as f32).sin();
        }
        let mut rot = heading_to_quat(heading);
        match u.state {
            UnitState::Dying => {
                if view.placeholder {
                    rot *= Quat::from_rotation_z((u.death_timer * 2.0).min(1.3));
                }
                if def.flying {
                    height = (def.altitude * (1.0 - u.death_timer / 1.2)).max(0.0);
                }
            }
            UnitState::Corpse => {
                // corpses sink into the ground over their lifetime
                let sink = (u.death_timer / sim.world.defs.rules.corpse_time.max(0.1)).clamp(0.0, 1.0);
                height = -0.45 * sink;
                if view.placeholder {
                    rot *= Quat::from_rotation_z(1.3);
                }
            }
            UnitState::Alive => {}
        }
        tf.translation = sim_to_world(pos, height);
        tf.rotation = rot;
    }
}

#[allow(clippy::too_many_arguments)]
fn sync_colonies(
    mut commands: Commands,
    sim: Res<GameSim>,
    mut assets: ResMut<GameAssets>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    mut index: ResMut<ViewIndex>,
    mut q: Query<(Entity, &mut ColonyView, &Children)>,
    tints: Query<Entity, With<TeamTint>>,
    mat_names: Query<(Entity, &GltfMaterialName)>,
    descendants: Query<&Children>,
    mut materials_q: Query<&mut MeshMaterial3d<StandardMaterial>>,
) {
    for c in &sim.world.colonies {
        if index.colonies.contains_key(&c.id) {
            continue;
        }
        let def = sim.world.colony_def(c);
        let tf = Transform::from_translation(sim_to_world(c.pos, 0.0));
        let model = assets.model(&def.model);
        let use_model = model.is_some_and(|m| m.ready && m.scene.is_some());
        let mut e = commands.spawn((ColonyView { id: c.id, team: c.team, defeated: !c.active() }, DespawnOnExit(AppState::InGame), tf, Visibility::default(), Name::new(format!("{} #{}", def.name, c.id))));
        if use_model {
            let scene = model.unwrap().scene.clone().unwrap();
            e.with_children(|p| {
                p.spawn((WorldAssetRoot(scene), TeamTint { team: c.team, colony: true })).observe(on_scene_ready);
            });
        } else {
            let mesh = assets.placeholder_colony.clone();
            let mat = assets.colony_material(c.team);
            let turret_mesh = assets.placeholder_head.clone();
            let dark = assets.dark_material.clone();
            e.with_children(|p| {
                p.spawn((Mesh3d(mesh), MeshMaterial3d(mat), Transform::from_xyz(0.0, -0.9, 0.0).with_scale(Vec3::new(1.0, 0.55, 1.0))));
                for (i, t) in def.turrets.iter().enumerate() {
                    p.spawn((Mesh3d(turret_mesh.clone()), MeshMaterial3d(dark.clone()), TurretNode { colony: c.id, index: i, fire_seq: 0, recoil: 0.0 }, Transform::from_xyz(t.offset.x, t.height, t.offset.y).with_scale(Vec3::splat(2.2))));
                }
            });
        }
        index.colonies.insert(c.id, e.id());
    }
    // ownership / defeat changes: swap team materials on the body
    for (entity, mut view, children) in q.iter_mut() {
        let Some(c) = sim.world.colonies.get(view.id as usize) else { continue };
        let defeated = !c.active();
        if view.team == c.team && view.defeated == defeated {
            continue;
        }
        view.team = c.team;
        view.defeated = defeated;
        let team_for_material = if defeated { 0 } else { c.team };
        for child in descendants.iter_descendants(entity) {
            if tints.get(child).is_ok() {
                commands.entity(child).insert(TeamTint { team: team_for_material, colony: true });
            }
            if let Ok((_, name)) = mat_names.get(child)
                && let Ok(mut m) = materials_q.get_mut(child)
            {
                let (color, key) = match base_material_name(&name.0) {
                    "M_Team" => (Some(assets.team_color(team_for_material)), team_for_material as u32),
                    "M_Colony" => (Some(assets.colony_color(team_for_material)), 100 + team_for_material as u32),
                    _ => (None, 0),
                };
                if let Some(color) = color {
                    // the current handle is itself a tinted copy; tint from its cached original if known
                    let original = assets.tint_origin.get(&m.0.id()).cloned().unwrap_or_else(|| m.0.clone());
                    if let Some(h) = tinted_material(&original, color, &mut materials, &mut assets.tint_cache, key) {
                        assets.tint_origin.insert(h.id(), original.clone());
                        m.0 = h;
                    }
                }
            }
        }
        // placeholder colonies: first mesh child is the body
        if let Some(first) = children.iter().next()
            && let Ok(mut m) = materials_q.get_mut(first)
        {
            m.0 = assets.colony_material(team_for_material);
        }
    }
}

fn animate_turrets(sim: Res<GameSim>, time: Res<Time>, mut stats: ResMut<AnimStats>, mut q: Query<(&mut TurretNode, &mut Transform)>) {
    for (mut node, mut tf) in q.iter_mut() {
        let Some(c) = sim.world.colonies.get(node.colony as usize) else { continue };
        let Some(t) = c.turrets.get(node.index) else { continue };
        if t.fire_seq != node.fire_seq {
            node.fire_seq = t.fire_seq;
            node.recoil = 1.0;
        }
        node.recoil = (node.recoil - time.delta_secs() * 6.0).max(0.0);
        // turret yaw: sim heading 0 = +z; same mapping as units
        let rot = heading_to_quat(t.yaw);
        if rot != tf.rotation {
            stats.turret_rotations += 1;
        }
        tf.rotation = rot;
    }
}

fn sync_bits(mut commands: Commands, sim: Res<GameSim>, assets: Res<GameAssets>, mut index: ResMut<ViewIndex>, mut q: Query<(&BitView, &mut Transform)>) {
    for b in &sim.world.bits {
        if !b.alive || index.bits.contains_key(&b.id) {
            continue;
        }
        let (p, h) = b.pos_height();
        let model = assets.model("colony_bit");
        let mut e = commands.spawn((BitView(b.id), DespawnOnExit(AppState::InGame), Transform::from_translation(sim_to_world(p, h + 0.25)), Visibility::default(), Name::new(format!("Bit {}", b.id))));
        if let Some(m) = model.filter(|m| m.ready && m.scene.is_some()) {
            let scene = m.scene.clone().unwrap();
            e.with_children(|c| {
                c.spawn(WorldAssetRoot(scene));
            });
        } else {
            e.with_children(|c| {
                c.spawn((Mesh3d(assets.bit_mesh.clone()), MeshMaterial3d(assets.bit_material.clone())));
            });
        }
        index.bits.insert(b.id, e.id());
    }
    let alive: Vec<u32> = sim.world.bits.iter().filter(|b| b.alive).map(|b| b.id).collect();
    let gone: Vec<u32> = index.bits.keys().filter(|id| !alive.contains(id)).copied().collect();
    for id in gone {
        if let Some(e) = index.bits.remove(&id) {
            commands.entity(e).despawn();
        }
    }
    let t = sim.world.time as f32;
    for (view, mut tf) in q.iter_mut() {
        if let Some(b) = sim.world.bit(view.0) {
            let (p, h) = b.pos_height();
            let bob = if b.landed() { 0.25 + 0.08 * (t * 4.0 + view.0 as f32).sin() } else { 0.25 };
            tf.translation = sim_to_world(p, h + bob);
            tf.rotation = Quat::from_rotation_y(t * 2.0 + view.0 as f32);
        }
    }
}

fn sync_projectiles(mut commands: Commands, sim: Res<GameSim>, assets: Res<GameAssets>, mut index: ResMut<ViewIndex>, mut q: Query<(&ProjectileView, &mut Transform)>) {
    for p in &sim.world.projectiles {
        if !p.alive || index.projectiles.contains_key(&p.id) {
            continue;
        }
        let scale = match sim.world.defs.weapons[p.weapon as usize].projectile {
            sa_sim::ProjectileKind::Missile { .. } => Vec3::new(1.0, 1.0, 3.0),
            sa_sim::ProjectileKind::Bomb { .. } | sa_sim::ProjectileKind::Bouncing { .. } => Vec3::splat(2.2),
            _ => Vec3::splat(1.0),
        };
        let e = commands
            .spawn((ProjectileView(p.id), DespawnOnExit(AppState::InGame), Mesh3d(assets.projectile_mesh.clone()), MeshMaterial3d(assets.projectile_material.clone()), Transform::from_translation(sim_to_world(p.pos, p.height)).with_scale(scale), Name::new("Projectile")))
            .id();
        index.projectiles.insert(p.id, e);
    }
    let alive: Vec<u32> = sim.world.projectiles.iter().filter(|p| p.alive).map(|p| p.id).collect();
    let gone: Vec<u32> = index.projectiles.keys().filter(|id| !alive.contains(id)).copied().collect();
    for id in gone {
        if let Some(e) = index.projectiles.remove(&id) {
            commands.entity(e).despawn();
        }
    }
    for (view, mut tf) in q.iter_mut() {
        if let Some(p) = sim.world.projectiles.iter().find(|p| p.id == view.0) {
            tf.translation = sim_to_world(p.pos, p.height.max(0.05));
            tf.rotation = heading_to_quat(p.heading);
        }
    }
}

fn spawn_impacts(mut commands: Commands, mut sim: ResMut<GameSim>, assets: Res<GameAssets>) {
    let events = std::mem::take(&mut sim.events);
    for e in &events {
        match e {
            SimEvent::Impact { pos, effect, .. } => {
                let (size, life) = match effect.as_str() {
                    "explosion_big" | "colony_explode" => (1.6, 0.5),
                    "explosion_medium" | "explosion_shrapnel" => (1.0, 0.4),
                    "paralyze" => (2.0, 0.6),
                    "bite" => (0.35, 0.2),
                    _ => (0.4, 0.25),
                };
                let mat = assets.impact_materials.get(effect).cloned().unwrap_or_else(|| assets.impact_materials["hit_small"].clone());
                commands.spawn((ImpactFx { t: 0.0, life, size }, DespawnOnExit(AppState::InGame), Mesh3d(assets.impact_mesh.clone()), MeshMaterial3d(mat), Transform::from_translation(sim_to_world(*pos, 0.3)).with_scale(Vec3::splat(0.05)), Name::new("Impact")));
            }
            SimEvent::ColonyScattered(cid) => {
                if let Some(c) = sim.world.colonies.get(*cid as usize) {
                    commands.spawn((ImpactFx { t: 0.0, life: 1.0, size: 4.0 }, DespawnOnExit(AppState::InGame), Mesh3d(assets.impact_mesh.clone()), MeshMaterial3d(assets.impact_materials["colony_explode"].clone()), Transform::from_translation(sim_to_world(c.pos, 1.0)).with_scale(Vec3::splat(0.1))));
                }
            }
            SimEvent::PirateSpawn { pos, .. } => {
                // leave an ant-hole prop where the pirates came out
                let mut e = commands.spawn((Name::new("AntHole"), DespawnOnExit(AppState::InGame), Transform::from_translation(sim_to_world(*pos, 0.0)), Visibility::default()));
                if let Some(m) = assets.model("ant_hole").filter(|m| m.ready && m.scene.is_some()) {
                    let scene = m.scene.clone().unwrap();
                    e.with_children(|c| {
                        c.spawn(WorldAssetRoot(scene));
                    });
                } else {
                    e.with_children(|c| {
                        c.spawn((Mesh3d(assets.placeholder_head.clone()), MeshMaterial3d(assets.dark_material.clone()), Transform::from_xyz(0.0, 0.0, 0.0).with_scale(Vec3::new(2.5, 0.4, 2.5))));
                    });
                }
            }
            _ => {}
        }
    }
    // keep the events for other consumers this frame (HUD/audio read them after this system)
    sim.events = events;
}

fn animate_impacts(mut commands: Commands, time: Res<Time>, mut q: Query<(Entity, &mut ImpactFx, &mut Transform)>) {
    for (e, mut fx, mut tf) in q.iter_mut() {
        fx.t += time.delta_secs();
        let f = (fx.t / fx.life).clamp(0.0, 1.0);
        let s = fx.size * (0.2 + 0.8 * (1.0 - (1.0 - f) * (1.0 - f)));
        tf.scale = Vec3::splat(s);
        if f >= 1.0 {
            commands.entity(e).despawn();
        }
    }
}

fn sync_animations(sim: Res<GameSim>, assets: Res<GameAssets>, mut stats: ResMut<AnimStats>, mut views: Query<(&UnitView, &mut AnimState)>, mut players: Query<(&mut AnimationPlayer, &mut AnimationTransitions)>) {
    for (view, mut st) in views.iter_mut() {
        if !st.ready {
            continue;
        }
        let Some(player_entity) = st.player else { continue };
        let Some(u) = sim.world.unit(view.id) else { continue };
        let Some(model) = assets.model(&view.model) else { continue };
        let def = sim.world.unit_def(u);
        let want = match u.state {
            UnitState::Alive => u.anim,
            _ => Anim::Death,
        };
        let retrigger = want == Anim::Attack && u.attack_seq != st.attack_seq;
        if st.current == Some(want) && !retrigger {
            continue;
        }
        let Ok((mut player, mut transitions)) = players.get_mut(player_entity) else { continue };
        let clip_name = match want {
            Anim::Idle => {
                if def.flying && model.clips.contains_key("fly") { "fly" } else { "idle" }
            }
            Anim::Move => {
                if def.flying && model.clips.contains_key("fly") { "fly" } else { "move" }
            }
            Anim::Attack => "attack",
            Anim::Death => "death",
        };
        let Some(node) = model.clips.get(clip_name).or_else(|| model.clips.get("idle")) else { continue };
        let blend = if want == Anim::Attack { 0.05 } else { 0.15 };
        *stats.clip_starts.entry(clip_name.to_string()).or_insert(0) += 1;
        let anim = transitions.play(&mut player, *node, Duration::from_secs_f32(blend));
        match want {
            Anim::Idle | Anim::Move => {
                anim.repeat();
                if want == Anim::Move {
                    // scale the walk cycle with the unit's actual speed (2.5 cells/s = nominal)
                    anim.set_speed((def.speed / 2.5).clamp(0.6, 1.8));
                }
            }
            Anim::Attack => {
                let len = model.clip_len.get("attack").copied().unwrap_or(0.5).max(0.05);
                anim.set_speed((len / def.attack_anim_time.max(0.1)).clamp(0.5, 3.0));
            }
            Anim::Death => {
                let len = model.clip_len.get("death").copied().unwrap_or(1.0).max(0.05);
                anim.set_speed((len / 1.2).clamp(0.5, 2.0));
            }
        }
        st.current = Some(want);
        st.attack_seq = u.attack_seq;
    }
}

/// Despawn every view (quick-load) so the next frame rebuilds them from the new world.
pub fn reset_views(commands: &mut Commands, index: &mut ViewIndex, views: &Query<Entity, Or<(With<UnitView>, With<ColonyView>, With<BitView>, With<ProjectileView>)>>) {
    for e in views.iter() {
        commands.entity(e).despawn();
    }
    index.units.clear();
    index.colonies.clear();
    index.bits.clear();
    index.projectiles.clear();
    index.generation += 1;
}
